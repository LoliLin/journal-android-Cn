#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 WHOCC 的 ATC/DDD 索引补全 substance 条目（独立工具）。

ATC 提供：INN 名称、ATC 码、层级归属，以及 DDD（**统计用指标，不能当剂量或处方建议**）。
本工具用 ATC 码穷举指定类目下的单一成分物质，写成 `root/<Name>.json`：

    name        句子化后的 INN 名（"diazepam" -> "Diazepam"）
    url         https://atcddd.fhi.no/atc_ddd_index/?code=<CODE>&showdescription=yes
    categories  由 ATC 类目映射（见 ATC_CLASS_CATEGORIES / ATC_SUBGROUP_CATEGORIES）
    isApproved  false

默认**不写 summary**（文案属人工内容）；`--with-template-summary` 可写 Klop233 那种
"Name. Classification: …" 的模板句。默认只补空缺、不覆盖已有值。

数据来源与映射依据：docs/substances-catalog-sources.md
用法：
    python docs/scripts/fetch_atc.py --dry-run --verbose
    python docs/scripts/fetch_atc.py --atc-prefix N05,N06,N03A,N02A,N07B,A08AA,C02AC,N04AA,N04BD
"""

from __future__ import annotations

import argparse
import html
import re
import time
from pathlib import Path

from _common import (
    DEFAULT_LEDGER,
    DEFAULT_WORK_DIR,
    REPO_ASSETS_HINT,
    die,
    fill_gaps,
    merge_ledger,
    read_json,
    resolve_assets_dir,
    sanitize_filename,
    warn_unknown_categories,
    write_json,
)

ATC_SOURCE = "ATC"
ATC_INDEX_URL = "https://atcddd.fhi.no/atc_ddd_index/"
DEFAULT_USER_AGENT = (
    "journal-android-multilingual/0.1 "
    "(+https://github.com/LoliLin/journal-android-multilingual)"
)

#: Klop233 那轮使用的类目范围（N05 精神安定药、N06 精神兴奋药、N03A 抗癫痫、
#: N02A 阿片类、N07B 成瘾治疗、A08AA/C02AC/N04AA/N04BD 相关中枢药物）
DEFAULT_ATC_PREFIXES = ("N05", "N06", "N03A", "N02A", "N07B", "A08AA", "C02AC", "N04AA", "N04BD")

#: 本工具允许写入的字段（categories 只对新建条目写）
ATC_MANAGED_FIELDS = ("url",)

#: ATC 4 位类目 -> 仓库分类（5 位亚组没有专项映射时的兜底）
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

#: ATC 5 位亚组 -> 仓库分类（存在则**替换**上面的兜底）
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

#: ATC 分类名称（给模板摘要用）
ATC_CLASS_LABELS = {
    "antipsychotic": "Antipsychotic",
    "anxiolytic": "Anxiolytic",
    "hypnotic": "Hypnotic",
    "antidepressant": "Antidepressant",
    "stimulant": "Stimulant",
    "antidementia": "Dementia medication",
    "antiepileptic": "Antiepileptic",
    "opioid": "Opioid",
    "antiparkinsonian": "Antiparkinsonian",
    "addiction-treatment": "Addiction treatment",
    "centrally-acting-medication": "Other central nervous system medication",
}

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
LINK_RE = re.compile(r"\?code=([A-Z0-9]{2,7})&")
TAG_RE = re.compile(r"<[^>]+>")


def atc_categories(code: str) -> list:
    """ATC 码 -> 仓库分类（先看 5 位亚组，再退回 4 位类目）。"""
    subgroup = ATC_SUBGROUP_CATEGORIES.get(code[:5])
    if subgroup is not None:
        return list(subgroup)
    return list(ATC_CLASS_CATEGORIES.get(code[:4], []))


def atc_url(code: str) -> str:
    return f"{ATC_INDEX_URL}?code={code}&showdescription=yes"


def atc_name(raw: str, rename_map: dict | None = None) -> tuple[str, str | None]:
    """ATC 用小写 INN 名；返回 (句子化后的名字, 规范化说明或 None)。"""
    name = " ".join(raw.split())
    original = name
    if original in ATC_NAME_OVERRIDES:
        name = ATC_NAME_OVERRIDES[original]
    if rename_map and original in rename_map:
        name = rename_map[original]
    name = name[:1].upper() + name[1:] if name else name
    note = None
    if name != original[:1].upper() + original[1:]:
        note = {"source": ATC_SOURCE, "key": original, "name": name,
                "note": f"ATC 原名为 '{original}'，按规范化表改名为 '{name}'。"}
    return name, note


def parse_atc_page(markup: str):
    """解析一个 ATC 层级页：返回 (substances, children)。

    substances: [(code, name)]；children: [子级 code]。
    """
    substances, children = [], []
    for row in ROW_RE.findall(markup):
        cells = [
            html.unescape(TAG_RE.sub("", cell)).strip()
            for cell in CELL_RE.findall(row)
        ]
        if len(cells) >= 2 and re.fullmatch(r"[A-Z][0-9]{2}[A-Z]{2}[0-9]{2}", cells[0]):
            substances.append((cells[0], cells[1]))
    for code in LINK_RE.findall(markup):
        if code not in children:
            children.append(code)
    return substances, children


def fetch_page(session, cache_dir: Path, code: str, args) -> str:
    """取一个 ATC 层级页（iso-8859-1），带本地缓存。"""
    cache_file = cache_dir / f"atc-{code}.html"
    if cache_file.exists() and not args.refresh:
        return cache_file.read_text(encoding="iso-8859-1")
    url = f"{ATC_INDEX_URL}?code={code}&showdescription=no"
    response = session.get(url, timeout=60)
    if response.status_code != 200:
        die(f"ATC {code} 返回 {response.status_code}：{url}")
    markup = response.content.decode("iso-8859-1", errors="replace")
    if not args.dry_run:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(markup, encoding="iso-8859-1")
    time.sleep(args.delay)
    return markup


def walk(session, cache_dir: Path, prefix: str, args, seen: set) -> list:
    """递归遍历某个 ATC 前缀，返回 [(code, name)]。"""
    if prefix in seen:
        return []
    seen.add(prefix)
    markup = fetch_page(session, cache_dir, prefix, args)
    substances, children = parse_atc_page(markup)
    if substances:
        return substances
    collected = []
    deeper = sorted(child for child in children if child.startswith(prefix) and child != prefix)
    for child in deeper:
        collected.extend(walk(session, cache_dir, child, args, seen))
    return collected


def is_combination_code(code: str) -> bool:
    """ATC 用末两位 51…99 表示复方/合剂层级（90 表示各类）。"""
    return code[-2:].isdigit() and int(code[-2:]) >= 51


#: 生物制品（单抗等）不是精神活性小分子，按 Klop233 那轮的排除口径跳过
BIOLOGIC_SUFFIXES = ("mab",)

#: 名称形式的复方/合剂（ATC 里 N02AJ/N06CA 这类组的子码不以 51–99 结尾，
#: 命名有 "A and B"、"X in combination with Y"、"Combinations of …"、"X, combinations"）
COMBINATION_NAME_RE = re.compile(r"\bin combination\b|\band\b|\bcombinations?\b", re.I)

#: ATC 用拉丁药名，参考目录里做过的名称规范化（可在台账 normalizationNotes 里追溯）
ATC_NAME_OVERRIDES = {
    "Ginkgo folium": "Ginkgo biloba",
    "Valerianae radix": "Valerian",
    "Lavandulae aetheroleum": "Lavender oil",
    "Hyperici herba": "St. John's wort",
}


def is_biologic(name: str) -> bool:
    return name.lower().endswith(BIOLOGIC_SUFFIXES)


def is_named_combination(name: str) -> bool:
    return bool(COMBINATION_NAME_RE.search(name))


def run(args) -> int:
    try:
        import requests
    except ImportError:
        die("本工具需要 requests：pip install requests")

    assets_dir = resolve_assets_dir(args.assets_dir, must_exist=False)
    out_dir = Path(args.out) if args.out else assets_dir / "root"
    cache_dir = Path(args.cache_dir) if args.cache_dir else DEFAULT_WORK_DIR / "atc-cache"
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": args.user_agent})

    prefixes = [
        token.strip().upper()
        for group in (args.atc_prefix or list(DEFAULT_ATC_PREFIXES))
        for token in group.split(",")
        if token.strip()
    ]
    print(f"输出目录：{out_dir}")
    print(f"缓存目录：{cache_dir}")
    print(f"ATC 类目：{', '.join(prefixes)}")

    seen: set = set()
    substances: list = []
    for prefix in prefixes:
        found = walk(session, cache_dir, prefix, args, seen)
        print(f"  {prefix}: {len(found)} 条")
        substances.extend(found)

    unique = {}
    for code, name in substances:
        unique.setdefault(code, name)
    if args.limit:
        unique = dict(sorted(unique.items())[: args.limit])
    print(f"本次处理 {len(unique)} 条" + ("（--dry-run：不写文件）" if args.dry_run else ""))

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": ATC_SOURCE,
        "out_dir": str(out_dir),
        "prefixes": prefixes,
        "overwrite": args.overwrite,
        "substances": [],
    }
    added, excluded, resolved, notes = [], [], [], []
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    used_categories: set = set()
    rename_map = read_json(Path(args.rename_map)) if args.rename_map else {}
    if rename_map and not isinstance(rename_map, dict):
        die(f"--rename-map '{args.rename_map}' 应是 {{原ATC名: 仓库名}} 的 JSON 对象。")

    for code, raw_name in sorted(unique.items()):
        name, note = atc_name(raw_name, rename_map)
        resolved.append({"source": ATC_SOURCE, "key": code, "name": name})
        if note:
            notes.append({**note, "key": code})
        if is_combination_code(code):
            excluded.append({
                "source": ATC_SOURCE,
                "key": code,
                "name": name,
                "reason": "ATC 复方/合剂层级（末两位 51–99），不是单一成分。",
            })
            continue
        if is_named_combination(name):
            excluded.append({
                "source": ATC_SOURCE,
                "key": code,
                "name": name,
                "reason": "ATC 名称为复方/合剂（含 'and' 或 'in combination'）。",
            })
            continue
        if is_biologic(name):
            excluded.append({
                "source": ATC_SOURCE,
                "key": code,
                "name": name,
                "reason": "生物制品（单抗类），不是精神活性小分子。",
            })
            continue

        categories = atc_categories(code)
        used_categories.update(categories)

        path = out_dir / f"{sanitize_filename(name)}.json"
        existing = read_json(path) if path.exists() else None
        if existing is None and args.only_existing:
            continue
        item = {"code": code, "file": path.name, "name": name, "categories": categories}
        if existing is None:
            incoming: dict = {"name": name, "url": atc_url(code), "isApproved": False}
            if categories:
                incoming["categories"] = categories
            if args.with_template_summary:
                label = ", ".join(
                    ATC_CLASS_LABELS.get(category, category) for category in categories
                ) or ATC_SOURCE
                incoming["summary"] = f"{name}. Classification: {label}."
            merged, changed, kept = incoming, sorted(incoming), []
            counts["created"] += 1
            added.append({"name": name, "sources": [{
                "source": ATC_SOURCE, "key": code, "url": atc_url(code),
            }]})
        else:
            incoming = {"url": atc_url(code)}
            merged, changed, kept = fill_gaps(existing, incoming, ATC_MANAGED_FIELDS, args.overwrite)
            counts["updated" if changed else "unchanged"] += 1
        if not args.dry_run and changed:
            write_json(path, merged)
        item["changed"] = changed
        item["kept"] = kept
        report["substances"].append(item)
        if args.verbose and changed:
            print(f"  {path.name}: {', '.join(changed[:6])}")

    report["counts"] = counts
    warn_unknown_categories(sorted(used_categories), ATC_SOURCE)
    report_path = Path(args.report) if args.report else cache_dir / "atc-report.json"
    if not args.dry_run:
        write_json(report_path, report)
        if args.ledger:
            merge_ledger(
                Path(args.ledger), source=ATC_SOURCE,
                snapshot={"source": ATC_SOURCE, "url": ATC_INDEX_URL, "version": args.atc_version},
                added=added, excluded=excluded, resolved=resolved, notes=notes,
            )

    print(f"\n完成：新建 {counts['created']}，更新 {counts['updated']}，无变化 {counts['unchanged']}，"
          f"排除复方 {len(excluded)}")
    if args.dry_run:
        print("--dry-run：没有写任何文件（缓存除外）；加 --verbose 可看到将变更的字段。")
    else:
        print(f"报告：{report_path}")
        if args.ledger:
            print(f"台账：{args.ledger}（added {len(added)} / excluded {len(excluded)} / resolved {len(resolved)}）")
        print("提醒：ATC 的 DDD 只作统计口径，不要当剂量；新条目一律 isApproved=false。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch_atc.py",
        description=(
            "按 ATC 类目穷举 WHOCC 索引里的单一成分物质，写 name/url/categories 与来源链接。"
            "默认只补空缺、不覆盖人工内容，也不写文案。"
        ),
        epilog="类目映射依据：docs/substances-catalog-sources.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--atc-prefix", action="append", default=None,
                        help="ATC 类目前缀，可用逗号分隔或重复多次；"
                             "默认就是那轮扩张用的 9 个：" + ",".join(DEFAULT_ATC_PREFIXES))
    parser.add_argument("--atc-version", default="", help="索引版本（写进台账快照，如 2026-01-20）")
    parser.add_argument("--rename-map", help="自定义改名表 JSON：{ATC 名: 仓库名}（会记入台账）")
    parser.add_argument("--cache-dir", help="缓存目录（默认 docs/scripts/_work/atc-cache）")
    parser.add_argument("--out", help="输出目录（默认 <assets>/root）")
    parser.add_argument("--assets-dir", help=f"assets/substances 目录（默认自动探测 {REPO_ASSETS_HINT}）")
    parser.add_argument("--with-template-summary", action="store_true",
                        help="为新条目写 'Name. Classification: …' 模板摘要（默认不写）")
    parser.add_argument("--only-existing", action="store_true", help="只补已有条目，不新建文件")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有结构化字段")
    parser.add_argument("--dry-run", action="store_true", help="不写文件、不建目录，只报告")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存重新抓取")
    parser.add_argument("--limit", type=int, help="只处理前 N 条（试跑用）")
    parser.add_argument("--delay", type=float, default=0.5, help="请求间隔秒数（默认 0.5）")
    parser.add_argument("--report", help="报告文件（默认 <cache-dir>/atc-report.json）")
    parser.add_argument("--ledger", nargs="?", const=str(DEFAULT_LEDGER), default=str(DEFAULT_LEDGER),
                        help=f"目录扩充台账（默认 {DEFAULT_LEDGER}）")
    parser.add_argument("--no-ledger", action="store_true", help="不写台账")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="请求 UA")
    parser.add_argument("--verbose", action="store_true", help="逐条打印变更字段")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.no_ledger:
        args.ledger = None
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
