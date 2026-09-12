#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 Wikidata 核对物质条目并记录来源（独立工具）。

作用：
  * 把每个物质的 `url` 指向 Wikidata 条目或对应的维基百科文章（默认只改这一个字段）；
  * 把 **Wikidata 作为数据来源**记进台账（`resolved` / `added` / `normalizationNotes`）；
  * 用 Wikidata 记录的 ATC 分类码复核我们自己的类别映射——映射表
    （`ATC_CLASS_CATEGORIES` / `ATC_SUBGROUP_CATEGORIES`）是本仓库自己的推导逻辑，
    码值本身是公开事实，从 Wikidata 取得（CC0）。

Wikidata 数据是 **CC0**：无署名义务、可商用、可再分发。许可义务见
docs/data-sources-and-licenses.md；字段口径见 docs/substances-catalog-sources.md。

用法：
    python docs/scripts/fetch_wikidata.py --names-file <文件> --dry-run   # 只看影响面
    python docs/scripts/fetch_wikidata.py --names "Acamprosate,Amfepramone"
    python docs/scripts/fetch_wikidata.py                                  # 遍历 root 全部条目
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from _common import (
    DEFAULT_LEDGER,
    DEFAULT_WORK_DIR,
    REPO_ASSETS_HINT,
    die,
    merge_ledger,
    read_json,
    resolve_assets_dir,
    sanitize_filename,
    write_json,
)

WIKIDATA_SOURCE = "Wikidata"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_ITEM_URL = "https://www.wikidata.org/wiki/"
WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/"
DEFAULT_USER_AGENT = (
    "journal-android-multilingual/0.1 "
    "(+https://github.com/LoliLin/journal-android-multilingual)"
)
DEFAULT_DELAY = 0.35
ATC_CODE_PROPERTY = "P267"          # ATC code（事实性码值，Wikidata 以 CC0 提供）

#: 本仓库自己的 ATC 码 → 应用分类推导表（4 位类目兜底）
ATC_CLASS_CATEGORIES = {
    "N02A": ["opioid"],
    "N03A": ["antiepileptic"],
    "N04A": ["antiparkinsonian"],
    "N04B": ["antiparkinsonian"],
    "N05A": ["antipsychotic"],
    "N05B": ["anxiolytic"],
    "N05C": ["hypnotic"],
    "N06A": ["antidepressant"],
    "N06B": ["stimulant"],
    "N06D": ["antidementia"],
    "N07B": ["addiction-treatment"],
}

#: 5 位亚组优先（比 4 位类目更精确）
ATC_SUBGROUP_CATEGORIES = {
    "A08AA": ["centrally-acting-medication"],
    "C02AC": ["centrally-acting-medication"],
    "N03AA": ["antiepileptic", "barbiturate"],
    "N04BD": ["antiparkinsonian", "maoi"],
    "N05BA": ["anxiolytic", "benzodiazepine"],
    "N05CA": ["hypnotic", "barbiturate"],
    "N05CD": ["hypnotic", "benzodiazepine"],
    "N06AB": ["antidepressant", "ssri"],
    "N06AF": ["antidepressant", "maoi"],
    "N06AG": ["antidepressant", "maoi"],
    "N06BX": ["nootropic"],
    "N06DA": ["antidementia"],
    "N06DX": ["antidementia"],
    "N07BA": ["addiction-treatment"],
    "N07BB": ["addiction-treatment"],
    "N07BC": ["addiction-treatment"],
}

#: INN 拼写 / 盐名 -> 仓库名（大小写不敏感）；与仓库既有条目对齐，免得同一物质建两份
NAME_OVERRIDES = {
    "amfetamine": "Amphetamine",
    "metamfetamine": "Methamphetamine",
    "dexamfetamine": "Dextroamphetamine",
    "potassium clorazepate": "Clorazepate",
    "ginkgo folium": "Ginkgo biloba",
    "valerianae radix": "Valerian",
    "lavandulae aetheroleum": "Lavender oil",
    "hyperici herba": "St. John's wort",
}

#: Wikidata 描述里出现这些词才算“物质/药物”条目（排除论文、疾病、公司等同名条目）
SUBSTANCE_DESC_RE = re.compile(
    r"chemical compound|chemical substance|medication|pharmaceutical|drug|"
    r"anxiolytic|antidepressant|antipsychotic|opioid|stimulant|sedative|hypnotic|"
    r"benzodiazepine|barbiturate|amino acid|alkaloid|hormone|"
    r"plant|species|narcotic|analgesic|anesthetic|anticonvulsant|antidote|"
    r"nootropic|supplement|mixture|latex|resin",
    re.IGNORECASE,
)

#: 仓库名（折叠后）-> Wikidata 检索词：拼写/盐名/学名差异，只用于查找，不改数据
LOOKUP_ALIASES = {
    "cytisinicline": "Cytisine",
    "fenetylline": "Fenethylline",
    "potassiumclorazepate": "Clorazepate",
}

#: 搜索命中不了时直接指定的条目（人工核对过：同名条目缺失或首个结果不是物质）
QID_OVERRIDES = {
    "thiopental": "Q410179",            # sodium thiopental（麻醉用盐型）
    "fenetylline": "Q27887794",         # fenethylline
    "valerian": "Q157819",              # Valeriana officinalis（缬草）
}


def fold(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").casefold())


def atc_categories(code: str) -> list:
    """ATC 码 -> 应用分类（先看 5 位亚组，再退回 4 位类目）。"""
    if not code:
        return []
    code = code.strip().upper()
    if code[:5] in ATC_SUBGROUP_CATEGORIES:
        return list(ATC_SUBGROUP_CATEGORIES[code[:5]])
    return list(ATC_CLASS_CATEGORIES.get(code[:4], []))


def sentence_case(name: str) -> str:
    name = " ".join((name or "").split())
    return name[:1].upper() + name[1:] if name else name


def normalize_name(label: str) -> str:
    """Wikidata 标签（多为小写 INN）-> 仓库命名习惯。"""
    name = sentence_case(label)
    return NAME_OVERRIDES.get(name.casefold(), name)


class WikidataSession:
    """带缓存与限速的 Wikidata 客户端（缓存放在 work-dir，重跑不再打 API）。"""

    def __init__(self, cache_dir: Path, delay: float, user_agent: str, refresh: bool, dry_run: bool):
        self.cache_dir = cache_dir
        self.delay = delay
        self.user_agent = user_agent
        self.refresh = refresh
        self.dry_run = dry_run

    def _cached(self, key: str, loader):
        path = self.cache_dir / f"{sanitize_filename(key)}.json"
        if path.exists() and not self.refresh:
            return read_json(path)
        data = loader()
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, data)
        time.sleep(self.delay)
        return data

    def _get(self, params: dict, tries: int = 4):
        url = WIKIDATA_API + "?" + urllib.parse.urlencode({**params, "format": "json"})
        for attempt in range(tries):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code == 429 or attempt < tries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
            except Exception:
                if attempt < tries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
        return {}

    def search(self, name: str) -> list:
        """按名称搜索，返回候选 [{qid, label, description}]。"""
        def loader():
            data = self._get({
                "action": "wbsearchentities", "search": name, "language": "en",
                "uselang": "en", "limit": 5,
            })
            return [
                {"qid": hit.get("id"), "label": hit.get("label"),
                 "description": hit.get("description") or ""}
                for hit in (data.get("search") or [])
            ]

        return self._cached(f"search-{fold(name)}", loader)

    def entity(self, qid: str) -> dict:
        """取条目的标签、维基百科链接与 ATC 码声明。"""
        def loader():
            data = self._get({
                "action": "wbgetentities", "ids": qid, "languages": "en",
                "props": "labels|descriptions|sitelinks|claims",
            })
            entity = (data.get("entities") or {}).get(qid) or {}
            codes = []
            for claim in ((entity.get("claims") or {}).get(ATC_CODE_PROPERTY) or []):
                value = (((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value"))
                if isinstance(value, str) and value not in codes:
                    codes.append(value)
            sitelink = (entity.get("sitelinks") or {}).get("enwiki") or {}
            return {
                "qid": qid,
                "label": ((entity.get("labels") or {}).get("en") or {}).get("value") or "",
                "description": ((entity.get("descriptions") or {}).get("en") or {}).get("value") or "",
                "atcCodes": codes,
                "wikipediaTitle": sitelink.get("title") or "",
            }

        return self._cached(f"entity-{qid}", loader)


def pick_entity(session: WikidataSession, name: str, atc_hint: str) -> tuple[dict | None, str]:
    """选一个可信的 Wikidata 条目：ATC 码与提示一致 > 标签与仓库名一致 > 描述像物质。"""
    hint = (atc_hint or "").strip().upper()
    override = QID_OVERRIDES.get(fold(name))
    if override:
        entity = session.entity(override)
        if entity.get("label") or entity.get("atcCodes"):
            return entity, "qid-override"
    search_term = LOOKUP_ALIASES.get(fold(name), name)
    fallback = None
    for candidate in session.search(search_term)[:3]:
        qid = candidate.get("qid")
        if not qid:
            continue
        entity = session.entity(qid)
        codes = [code.upper() for code in entity.get("atcCodes") or []]
        if hint and hint in codes:
            return entity, "atc-hint"
        if fold(entity.get("label")) == fold(name):
            return entity, "label"
        if SUBSTANCE_DESC_RE.search(entity.get("description") or "") and fallback is None:
            fallback = entity
    if fallback is not None:
        return fallback, "description"
    return None, ""


def desired_url(entity: dict) -> str:
    title = (entity.get("wikipediaTitle") or "").strip()
    if title:
        return WIKIPEDIA_URL + urllib.parse.quote(title.replace(" ", "_"), safe="()_,'-")
    return WIKIDATA_ITEM_URL + (entity.get("qid") or "")


def load_targets(args) -> list:
    """返回 [(name, atc_hint)]；默认遍历 root 下所有条目。"""
    if args.names:
        return [(part.strip(), "") for part in args.names.split(",") if part.strip()]
    if args.names_file:
        path = Path(args.names_file)
        if not path.exists():
            die(f"--names-file '{path}' 不存在。")
        data = read_json(path)
        if not isinstance(data, list):
            die(f"--names-file '{path}' 应是数组。")
        targets = []
        for item in data:
            if isinstance(item, str):
                targets.append((item, ""))
            elif isinstance(item, dict) and item.get("name"):
                targets.append((str(item["name"]), str(item.get("atcHint") or "")))
        return targets
    assets_dir = resolve_assets_dir(args.assets_dir)
    root_dir = assets_dir / "root"
    return [(path.stem, "") for path in sorted(root_dir.glob("*.json")) if path.name != "_categories.json"]


def run(args) -> int:
    assets_dir = resolve_assets_dir(args.assets_dir, must_exist=False)
    root_dir = assets_dir / "root"
    cache_dir = Path(args.cache_dir) if args.cache_dir else DEFAULT_WORK_DIR / "wikidata-cache"
    if not args.dry_run:
        cache_dir.mkdir(parents=True, exist_ok=True)
    targets = load_targets(args)
    if args.limit:
        targets = targets[: args.limit]
    if not targets:
        print("没有需要处理的条目。")
        return 0
    session = WikidataSession(cache_dir, args.delay, args.user_agent, args.refresh, args.dry_run)
    print(f"输出目录：{root_dir}")
    print(f"缓存目录：{cache_dir}")
    print(f"本次处理 {len(targets)} 条" + ("（--dry-run：不写文件）" if args.dry_run else ""))

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": WIKIDATA_SOURCE,
        "api": WIKIDATA_API,
        "substances": [],
    }
    counts = {"updated": 0, "unchanged": 0, "unresolved": 0, "classMismatch": 0}
    added, resolved, notes = [], [], []

    for name, atc_hint in targets:
        entity, how = pick_entity(session, name, atc_hint)
        if entity is None:
            counts["unresolved"] += 1
            report["substances"].append({"name": name, "matched": False})
            print(f"  未匹配到 Wikidata 条目：{name}")
            continue
        url = desired_url(entity)
        path = root_dir / f"{sanitize_filename(name)}.json"
        existing = read_json(path) if path.exists() else None
        item = {
            "name": name, "qid": entity["qid"], "label": entity.get("label"),
            "matched_by": how, "url": url, "atcCodes": entity.get("atcCodes"),
            "file": path.name if existing is not None else None,
        }
        resolved.append({"source": WIKIDATA_SOURCE, "key": entity["qid"], "name": name})
        added.append({"name": name, "sources": [{
            "source": WIKIDATA_SOURCE, "key": entity["qid"],
            "url": WIKIDATA_ITEM_URL + entity["qid"],
        }]})
        if entity.get("label") and fold(entity["label"]) != fold(name):
            notes.append({"source": WIKIDATA_SOURCE, "key": entity["qid"], "name": name,
                          "note": f"Wikidata 标签为 '{entity['label']}'，仓库名为 '{name}'。"})

        if existing is None:
            item["changed"] = []
            report["substances"].append(item)
            continue

        # 用 Wikidata 记录的 ATC 码复核我们自己的类别映射（默认只报告；--apply-classes 才补上）
        wanted = set()
        for code in entity.get("atcCodes") or []:
            wanted.update(atc_categories(code))
        current = set(existing.get("categories") or [])
        missing = sorted(wanted - current)
        changed = []
        if missing:
            counts["classMismatch"] += 1
            item["classMismatch"] = missing
            if args.apply_classes:
                existing = dict(existing)
                existing["categories"] = sorted(current | set(missing))
                changed.append(f"categories(+{len(missing)})")
                if not args.dry_run:
                    write_json(path, existing)

        if url and existing.get("url") != url:
            existing = dict(existing)
            existing["url"] = url
            changed.append("url")
            if not args.dry_run:
                write_json(path, existing)
        item["changed"] = changed
        counts["updated" if changed else "unchanged"] += 1
        report["substances"].append(item)
        if args.verbose and changed:
            print(f"  {path.name}: {', '.join(changed)} -> {url}")

    report["counts"] = counts
    report_path = Path(args.report) if args.report else DEFAULT_WORK_DIR / "wikidata-report.json"
    if not args.dry_run:
        write_json(report_path, report)
        if args.ledger:
            merge_ledger(
                Path(args.ledger), source=WIKIDATA_SOURCE,
                snapshot={"source": WIKIDATA_SOURCE, "url": WIKIDATA_API, "version": "wikidata"},
                added=added, resolved=resolved, notes=notes,
            )
    print(f"\n完成：更新 {counts['updated']}，无变化 {counts['unchanged']}，"
          f"未匹配 {counts['unresolved']}，类别与码不一致 {counts['classMismatch']}")
    if counts["classMismatch"]:
        print("提示：类别不一致的条目见报告 classMismatch（我们自己的映射表可能与码的层级不吻合，需人工定夺）。")
    if args.dry_run:
        print("--dry-run：没有写任何文件。")
    else:
        print(f"报告：{report_path}")
        if args.ledger:
            print(f"台账：{args.ledger}（resolved {len(resolved)} / added {len(added)} / notes {len(notes)}）")
        print("来源：Wikidata（CC0，无署名义务，可商用）。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch_wikidata.py",
        description=(
            "用 Wikidata（CC0）核对物质条目：把 url 指向 Wikidata/维基百科条目、把来源记进台账，"
            "并用 Wikidata 记录的 ATC 码复核我们自己的类别映射。默认只改 url 一个字段。"
        ),
        epilog="许可义务：docs/data-sources-and-licenses.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--names", help="逗号分隔的物质名（默认遍历 root 全部条目）")
    parser.add_argument("--names-file",
                        help="JSON 数组，元素为名称或 {name, atcHint}；atcHint 仅用于挑选正确条目")
    parser.add_argument("--assets-dir", help=f"assets/substances 目录（默认自动探测 {REPO_ASSETS_HINT}）")
    parser.add_argument("--out", help="输出目录（默认 <assets>/root）")
    parser.add_argument("--cache-dir", help="缓存目录（默认 docs/scripts/_work/wikidata-cache）")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="请求 UA（请保留可联系方式）")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="请求间隔秒数（默认 0.35）")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存重新查询")
    parser.add_argument("--apply-classes", action="store_true",
                        help="把 Wikidata 的码所暗示、而条目缺失的类别补上（默认只报告差异）")
    parser.add_argument("--limit", type=int, help="只处理前 N 条（试跑用）")
    parser.add_argument("--dry-run", action="store_true", help="不写文件、不建目录，只报告")
    parser.add_argument("--report", help="报告文件（默认 docs/scripts/_work/wikidata-report.json）")
    parser.add_argument("--ledger", nargs="?", const=str(DEFAULT_LEDGER), default=str(DEFAULT_LEDGER),
                        help=f"目录扩充台账（默认 {DEFAULT_LEDGER}）")
    parser.add_argument("--no-ledger", action="store_true", help="不写台账")
    parser.add_argument("--verbose", action="store_true", help="逐条打印变更")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.no_ledger:
        args.ledger = None
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
