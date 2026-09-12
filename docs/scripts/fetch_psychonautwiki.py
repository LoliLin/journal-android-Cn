#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 PsychonautWiki 抓取 substance 结构化字段（独立工具）。

只补 PW 有的**结构化数据**：剂量、时长、生物利用度、耐受、交叉耐受、毒性、成瘾性、
相互作用、别名。默认**只补空缺、不覆盖任何已有值**；文案、审核状态、翻译、代谢来源
一律不碰（见 FETCH_MANAGED_FIELDS）。

字段映射、实测通过率、拿不到的字段与许可要求：docs/substances-pw-extraction.md
本地数据流水线（拆分/翻译/回填/校对）是另一个工具：docs/scripts/substances_pipeline.py

用法速览：
    python docs/scripts/fetch_psychonautwiki.py --dry-run --verbose
    python docs/scripts/fetch_psychonautwiki.py                    # 只补空缺
    python docs/scripts/fetch_psychonautwiki.py --source index     # 只用索引页列出的物质
    python docs/scripts/fetch_psychonautwiki.py --overwrite        # 覆盖结构化字段
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from _common import (
    CROSS_TOLERANCE_FIXES,
    DEFAULT_LEDGER,
    DEFAULT_WORK_DIR,
    REPO_ASSETS_HINT,
    die,
    fill_gaps,
    merge_ledger,
    number,
    read_json,
    resolve_assets_dir,
    sanitize_filename,
    write_json,
)

#: PsychonautWiki 的两个入口
PW_GRAPHQL_ENDPOINT = "https://api.psychonautwiki.org/"
PW_MEDIAWIKI_API = "https://psychonautwiki.org/w/api.php"
PW_INDEX_PAGE = "Psychoactive substance index"
PW_PAGE_SIZE = 500

DEFAULT_USER_AGENT = (
    "journal-android-multilingual/0.1 "
    "(+https://github.com/LoliLin/journal-android-multilingual)"
)
DEFAULT_FETCH_DELAY = 0.5

#: 允许写入的字段。其余字段属于人工内容（文案、审核状态、翻译、代谢来源），永不改动。
FETCH_MANAGED_FIELDS = (
    "url",
    "commonNames",
    "tolerance",
    "crossTolerances",
    "toxicities",
    "addictionPotential",
    "interactions",
    "roas",
)

#: 只给“新建条目”写 categories 时允许的词表（PW 的 psychoactive class 归一化后必须命中）
FETCH_CATEGORY_VOCAB = {
    "psychedelic",
    "stimulant",
    "depressant",
    "entactogen",
    "dissociative",
    "opioid",
    "benzodiazepine",
    "cannabinoid",
    "deliriant",
    "hallucinogen",
    "nootropic",
    "eugeroic",
    "antipsychotic",
    "antidepressant",
    "barbiturate",
    "oneirogen",
    "hypnotic",
    "mood-stabilizer",
    "arylcyclohexylamine",
}

#: 索引页里不是物质的链接（导航/索引页自身）
PW_INDEX_SKIP = {
    "Psychoactive substance index",
    "Summary index",
    "Subjective effect index",
    "Tutorial index",
    "List of pharmaceuticals",
    "List/substances",
    "List/substances-drafts",
    "Nootropics",
    "Entheogens",
    "Inhalants",
    "Oneirogens",
    "Guidelines",
    "Psychonautics",
}

#: API 全量遍历里不是具体物质的页面：PW 的 "Substituted X" 类目页与消歧页
PW_NON_SUBSTANCE_RE = re.compile(r"^Substituted\b|\(disambiguation\)\s*$", re.IGNORECASE)

PW_GRAPHQL_CATALOG_QUERY = """
{
  substances(limit: %d, offset: %d) {
    name url featured systematicName commonNames
    class { chemical psychoactive }
    tolerance { full half zero }
    crossTolerances toxicity addictionPotential
    dangerousInteractions { name }
    unsafeInteractions { name }
    uncertainInteractions { name }
    roas {
      name
      dose { units threshold heavy light { min max } common { min max } strong { min max } }
      duration { onset { min max units } comeup { min max units } peak { min max units }
                 offset { min max units } total { min max units } afterglow { min max units } }
      bioavailability { min max }
    }
  }
}
"""


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


def pw_session(user_agent: str):
    """带 User-Agent 的 requests.Session（站点礼仪要求可联系的 UA）。"""
    try:
        import requests
    except ImportError:
        die("本工具需要 requests：pip install requests")
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    return session


def pw_graphql(session, query: str):
    response = session.post(PW_GRAPHQL_ENDPOINT, json={"query": query}, timeout=60)
    if response.status_code != 200:
        die(f"GraphQL 返回 {response.status_code}：{response.text[:200]}")
    payload = response.json()
    if payload.get("errors"):
        die(f"GraphQL 报错：{payload['errors']}")
    return payload["data"]


def pw_catalog(session, cache_dir: Path, refresh: bool, delay: float, write_cache: bool = True) -> list:
    """拉取全量物质（分页 500），结果缓存到 <cache-dir>/pw-cache-catalog.json。

    write_cache=False（--dry-run）时只读缓存、不落盘，保证 dry-run 完全只读。
    """
    cache_file = cache_dir / "pw-cache-catalog.json"
    if cache_file.exists() and not refresh:
        cached = read_json(cache_file)
        print(f"缓存：{cache_file}（{len(cached['substances'])} 条，抓取于 {cached.get('fetched_at')}）")
        return cached["substances"]

    substances: list = []
    offset = 0
    while True:
        page = pw_graphql(session, PW_GRAPHQL_CATALOG_QUERY % (PW_PAGE_SIZE, offset))["substances"] or []
        if not page:
            break
        substances.extend(page)
        offset += len(page)
        if len(page) < PW_PAGE_SIZE:
            break
        print(f"已抓取 {len(substances)} 条…")
        time.sleep(delay)

    if write_cache:
        write_json(cache_file, {
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "endpoint": PW_GRAPHQL_ENDPOINT,
            "substances": substances,
        })
    print(f"从 API 抓取 {len(substances)} 条" + (f" -> {cache_file}" if write_cache else "（--dry-run：不写缓存）"))
    return substances


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


def pw_index_entries(session, cache_dir: Path, refresh: bool, delay: float, write_cache: bool = True) -> list:
    """解析索引页渲染后的 HTML，得到 [{'page': ..., 'groups': [...]}]。

    索引页本身只是壳（`{{:List/substances}}`），所以直接解析渲染结果而不是 wikitext。
    """
    cache_file = cache_dir / "pw-cache-index.json"
    if cache_file.exists() and not refresh:
        cached = read_json(cache_file)
        print(f"缓存：{cache_file}（{len(cached['entries'])} 条，抓取于 {cached.get('fetched_at')}）")
        return cached["entries"]

    import urllib.parse

    response = session.get(
        PW_MEDIAWIKI_API,
        params={"action": "parse", "page": PW_INDEX_PAGE, "prop": "text",
                "format": "json", "formatversion": "2"},
        timeout=60,
    )
    html = response.json()["parse"]["text"]

    token = re.compile(
        r"<h([2-4])[^>]*>(.*?)</h\1>|<a\s+href=\"/wiki/([^\"#?]+)\"[^>]*title=\"([^\"]*)\"",
        flags=re.S,
    )
    heading = ""
    order: list = []
    groups: dict = {}
    for match in token.finditer(html):
        if match.group(1):
            heading = _strip_html(match.group(2))
            continue
        page = urllib.parse.unquote(match.group(3)).replace("_", " ")
        if ":" in page or page in PW_INDEX_SKIP:
            continue
        if page not in groups:
            groups[page] = []
            order.append(page)
        if heading and heading not in groups[page]:
            groups[page].append(heading)

    entries = [{"page": page, "groups": groups[page]} for page in order]
    if write_cache:
        write_json(cache_file, {
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "page": PW_INDEX_PAGE,
            "entries": entries,
        })
    print(f"索引页解析出 {len(entries)} 个条目" + (f" -> {cache_file}" if write_cache else "（--dry-run：不写缓存）"))
    return entries


def pw_resolve_names(session, names: list, delay: float) -> dict:
    """用 MediaWiki redirects 把页面名解析到实际条目（每批 50 个）。"""
    resolved: dict = {}
    for start in range(0, len(names), 50):
        batch = names[start:start + 50]
        response = session.get(
            PW_MEDIAWIKI_API,
            params={
                "action": "query",
                "titles": "|".join(batch),
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            },
            timeout=60,
        )
        for redirect in response.json().get("query", {}).get("redirects", []):
            resolved[redirect["from"]] = redirect["to"]
        if start + 50 < len(names):
            time.sleep(delay)
    return resolved


# --------------------------------------------------------------------------
# API 记录 -> 仓库格式
# --------------------------------------------------------------------------


def _norm_dose_units(units):
    """仓库用 MICRO SIGN(U+00B5)，API 用 GREEK SMALL LETTER MU(U+03BC)。"""
    return units.replace("\u03bc", "\u00b5") if isinstance(units, str) else units


def pw_dose(dose) -> dict | None:
    """API dose -> 仓库 dose。

    注意：lightMin 取的是 API 的 `threshold`（上游既有约定，`light.min` 被丢弃）。
    """
    if not isinstance(dose, dict):
        return None
    out = {}
    if dose.get("units") is not None:
        out["units"] = _norm_dose_units(dose["units"])
    if dose.get("threshold") is not None:
        out["lightMin"] = number(dose["threshold"])
    if (dose.get("common") or {}).get("min") is not None:
        out["commonMin"] = number(dose["common"]["min"])
    if (dose.get("strong") or {}).get("min") is not None:
        out["strongMin"] = number(dose["strong"]["min"])
    if dose.get("heavy") is not None:
        out["heavyMin"] = number(dose["heavy"])
    return out or None


def pw_duration(duration) -> dict | None:
    """API duration -> 仓库 duration（单位小写；min/max 为空时不写该键；整段为空则省略）。"""
    if not isinstance(duration, dict):
        return None
    out = {}
    for segment in ("onset", "comeup", "peak", "offset", "total", "afterglow"):
        value = duration.get(segment)
        if not isinstance(value, dict):
            continue
        segment_out = {}
        if value.get("min") is not None:
            segment_out["min"] = number(value["min"])
        if value.get("max") is not None:
            segment_out["max"] = number(value["max"])
        if not segment_out:
            continue
        if value.get("units"):
            segment_out["units"] = value["units"].lower()
        out[segment] = segment_out
    return out or None


def pw_bioavailability(value) -> dict | None:
    if not isinstance(value, dict) or (value.get("min") is None and value.get("max") is None):
        return None
    out = {}
    if value.get("min") is not None:
        out["min"] = number(value["min"])
    if value.get("max") is not None:
        out["max"] = number(value["max"])
    return out


def pw_cross_tolerances(values) -> list | None:
    """PW 用复数写法（opioids/stimulants），仓库用单数。

    复用 _common 的映射表并去重，避免抓取时把 fix-tolerances 刚清掉的复数又写回去。
    """
    out = []
    for name in values or []:
        normalized = CROSS_TOLERANCE_FIXES.get(name, name)
        if normalized not in out:
            out.append(normalized)
    return out or None


def pw_interactions(pw) -> dict | None:
    out = {}
    for key, api_key in (("dangerous", "dangerousInteractions"),
                         ("unsafe", "unsafeInteractions"),
                         ("uncertain", "uncertainInteractions")):
        names = [item["name"] for item in (pw.get(api_key) or []) if item.get("name")]
        if names:
            out[key] = names
    return out or None


def pw_categories(pw) -> list:
    """API 的 psychoactive class -> 仓库词表（仅用于新建条目）。"""
    categories = []
    for name in ((pw.get("class") or {}).get("psychoactive") or []):
        slug = name.strip().lower().replace(" ", "-")
        if slug not in FETCH_CATEGORY_VOCAB and slug.endswith("s") and slug[:-1] in FETCH_CATEGORY_VOCAB:
            slug = slug[:-1]
        if slug in FETCH_CATEGORY_VOCAB and slug not in categories:
            categories.append(slug)
    return categories


def pw_to_asset(pw, with_categories: bool) -> dict:
    """把一条 API 记录转成仓库 root/<Name>.json 的结构（键序与现有资产一致）。"""
    record: dict = {
        "name": pw["name"],
        "url": pw.get("url"),
        "isApproved": False,
    }
    if pw.get("commonNames"):
        record["commonNames"] = pw["commonNames"]
    if with_categories:
        categories = pw_categories(pw)
        if categories:
            record["categories"] = categories
    tolerance = pw.get("tolerance") or {}
    if any(tolerance.get(key) for key in ("full", "half", "zero")):
        record["tolerance"] = {key: tolerance[key] for key in ("full", "half", "zero") if tolerance.get(key)}
    cross_tolerances = pw_cross_tolerances(pw.get("crossTolerances"))
    if cross_tolerances:
        record["crossTolerances"] = cross_tolerances
    if pw.get("addictionPotential"):
        record["addictionPotential"] = pw["addictionPotential"]
    if pw.get("toxicity"):
        record["toxicities"] = pw["toxicity"]
    interactions = pw_interactions(pw)
    if interactions:
        record["interactions"] = interactions
    roas = []
    for roa in sorted(pw.get("roas") or [], key=lambda item: item.get("name") or ""):
        entry: dict = {"name": roa.get("name")}
        dose = pw_dose(roa.get("dose"))
        if dose:
            entry["dose"] = dose
        duration = pw_duration(roa.get("duration"))
        if duration:
            entry["duration"] = duration
        bioavailability = pw_bioavailability(roa.get("bioavailability"))
        if bioavailability:
            entry["bioavailability"] = bioavailability
        if len(entry) > 1:
            roas.append(entry)
    if roas:
        record["roas"] = roas
    return record


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    assets_dir = resolve_assets_dir(args.assets_dir, must_exist=False)
    out_dir = Path(args.out) if args.out else assets_dir / "root"
    cache_dir = Path(args.cache_dir) if args.cache_dir else DEFAULT_WORK_DIR / "pw-cache"
    if not args.dry_run:
        cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"输出目录：{out_dir}")
    print(f"缓存目录：{cache_dir}")
    session = pw_session(args.user_agent)

    catalog = pw_catalog(session, cache_dir, args.refresh, args.delay, write_cache=not args.dry_run)
    by_name = {s["name"]: s for s in catalog if s.get("name")}

    index_entries = []
    if args.source == "index":
        index_entries = pw_index_entries(session, cache_dir, args.refresh, args.delay,
                                         write_cache=not args.dry_run)
        wanted = {entry["page"] for entry in index_entries}
        targets = [s for s in catalog if s["name"] in wanted]
        index_missing = sorted(wanted - set(by_name))
        print(f"索引页条目：{len(wanted)}，其中 API 有数据：{len(targets)}，缺：{len(index_missing)}")
    else:
        targets = list(catalog)
        index_missing = []
    if args.limit:
        targets = targets[: args.limit]
    if not targets:
        print("没有需要处理的条目。")
        return 0
    print(f"本次处理 {len(targets)} 条" + ("（--dry-run：不写文件）" if args.dry_run else ""))

    # 仓库已有文件名 → API 名 的对齐（处理 PW 改名/重定向，如 Psilocybin -> Psilocybin mushrooms）
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    repo_stems = [f.stem for f in sorted(out_dir.glob("*.json")) if f.name != "_categories.json"]
    alias, matched_by = {}, {}
    unmatched_repo = [stem for stem in repo_stems if stem not in by_name]
    if unmatched_repo:
        resolved = pw_resolve_names(session, unmatched_repo, args.delay)
        for stem in unmatched_repo:
            api_name = resolved.get(stem)
            if api_name in by_name and api_name not in alias:
                alias[api_name] = stem
                matched_by[api_name] = f"redirect:{stem}"

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": args.source,
        "out_dir": str(out_dir),
        "api_endpoint": PW_GRAPHQL_ENDPOINT,
        "user_agent": args.user_agent,
        "overwrite": args.overwrite,
        "substances": [],
    }
    counts = {"updated": 0, "created": 0, "unchanged": 0}
    skipped_pages: list = []
    ledger_added, ledger_resolved = [], []

    for api_record in targets:
        api_name = api_record["name"]
        if PW_NON_SUBSTANCE_RE.search(api_name):
            skipped_pages.append(api_name)
            continue
        stem = alias.get(api_name, api_name)
        path = out_dir / f"{sanitize_filename(stem)}.json"
        existing = read_json(path) if path.exists() else None
        if existing is None:
            incoming = pw_to_asset(api_record, with_categories=True)
            merged, changed, kept = incoming, sorted(incoming), []
            counts["created"] += 1
            ledger_added.append({"name": api_name, "sources": [{
                "source": "PsychonautWiki", "key": api_name, "url": api_record.get("url"),
            }]})
        else:
            incoming = pw_to_asset(api_record, with_categories=False)
            merged, changed, kept = fill_gaps(
                existing, incoming, FETCH_MANAGED_FIELDS, args.overwrite
            )
            counts["updated" if changed else "unchanged"] += 1
        if not args.dry_run and changed:
            write_json(path, merged)
        report["substances"].append({
            "name": api_name,
            "file": path.name,
            "matched_by": matched_by.get(api_name, "name"),
            "url": api_record.get("url"),
            "groups": next((e["groups"] for e in index_entries if e["page"] == api_name), []),
            "changed": changed,
            "kept": kept,
        })
        if args.verbose and changed:
            print(f"  {stem}: {', '.join(changed[:6])}{' …' if len(changed) > 6 else ''}")
        if api_name in matched_by:
            ledger_resolved.append({"source": "PsychonautWiki", "key": stem, "name": api_name})

    report["counts"] = counts
    # 与本次是否 --limit/--source 无关：以完整 API 目录为准
    report["repo_files_without_api_record"] = sorted(
        stem for stem in repo_stems if stem not in by_name and stem not in set(alias.values())
    )
    report["index_entries_missing_in_api"] = index_missing
    report["skipped_pages"] = sorted(skipped_pages)

    report_path = Path(args.report) if args.report else cache_dir / "pw-report.json"
    if not args.dry_run:
        write_json(report_path, report)
        if args.ledger:
            merge_ledger(
                Path(args.ledger), source="PsychonautWiki",
                snapshot={"source": "PsychonautWiki", "url": PW_GRAPHQL_ENDPOINT,
                          "query": PW_GRAPHQL_CATALOG_QUERY % (PW_PAGE_SIZE, 0)},
                added=ledger_added, resolved=ledger_resolved,
            )

    print(f"\n完成：新建 {counts['created']}，更新 {counts['updated']}，无变化 {counts['unchanged']}")
    if skipped_pages:
        print(f"跳过的非物质页面（{len(skipped_pages)}）：{'、'.join(sorted(skipped_pages))}")
    if report["repo_files_without_api_record"]:
        print(f"仓库中找不到 API 记录的：{'、'.join(report['repo_files_without_api_record'])}")
    if index_missing:
        print(f"索引页有、API 无数据的：{'、'.join(index_missing[:10])}")
    if args.dry_run:
        print("--dry-run：没有写任何文件；加 --verbose 可看到将变更的字段。")
    else:
        print(f"报告：{report_path}")
        print("注意：新条目一律 isApproved=false，categories 只对新建条目写入，人工字段从不改动。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch_psychonautwiki.py",
        description=(
            "用 PsychonautWiki 的 GraphQL/MediaWiki API 补全剂量、时长、耐受、交叉耐受、"
            "毒性、成瘾性、相互作用、别名。默认只补空缺、不覆盖人工内容。"
        ),
        epilog="字段映射与坑：docs/substances-pw-extraction.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source", choices=("api", "index"), default="api",
        help="api=遍历 API 全量（约 373 条）；index=只处理索引页列出的物质",
    )
    parser.add_argument("--out", help="输出目录（默认 <assets>/root）")
    parser.add_argument("--cache-dir", help="缓存目录（默认 docs/scripts/_work/pw-cache）")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="请求 UA（请保留可联系方式）")
    parser.add_argument("--delay", type=float, default=DEFAULT_FETCH_DELAY, help="请求间隔秒数（默认 0.5）")
    parser.add_argument("--limit", type=int, help="只处理前 N 条（试跑用）")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有的结构化字段（默认只补空缺）")
    parser.add_argument("--dry-run", action="store_true", help="不写文件、不建目录，只报告会改哪些字段")
    parser.add_argument("--refresh", action="store_true", help="忽略本地缓存重新抓取")
    parser.add_argument("--report", help="报告文件（默认 <cache-dir>/pw-report.json）")
    parser.add_argument("--ledger", nargs="?", const=str(DEFAULT_LEDGER), default=str(DEFAULT_LEDGER),
                        help=f"目录扩充台账（默认 {DEFAULT_LEDGER}）")
    parser.add_argument("--no-ledger", action="store_true", help="不写台账")
    parser.add_argument("--verbose", action="store_true", help="逐条打印变更字段")
    parser.add_argument(
        "--assets-dir",
        help=f"assets/substances 目录（默认自动探测 {REPO_ASSETS_HINT}，否则用当前目录）",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.no_ledger:
        args.ledger = None
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
