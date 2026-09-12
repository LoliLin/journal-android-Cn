#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 TripSit 的药物数据库补全 substance 条目（独立工具）。

TripSit 提供：名称、别名、分类（17 个值，与仓库词表高度重合）、按给药途径的剂量字符串、
时长字符串、组合矩阵、短摘要。

本工具默认**只用名称/别名/分类/来源链接**，并默认**只补空缺、不覆盖已有值**：
- 分类是仓库 `common`/`tentative`/`habit-forming`/`research-chemical` 等标签的来源之一；
- `--with-doses` 可额外把剂量字符串解析成数值（PW 没有覆盖的物质可用，质量不如 PW）；
- 时长字符串不分给药途径，组合矩阵与摘要涉及许可问题，**都不写入**（见文档）。

⚠️ TripSit/drugs 仓库**没有 LICENSE 文件**（默认保留所有权利）：只把这里当名称/别名/分类的
核对来源，不要逐字搬运它的文案。

用法速览：
    python docs/scripts/fetch_tripsit.py --dry-run --verbose
    python docs/scripts/fetch_tripsit.py --with-doses
    python docs/scripts/fetch_tripsit.py --only-existing      # 只补已有条目，不新增

字段与来源说明：docs/substances-catalog-sources.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
    write_json,
)

DEFAULT_TRIPSIT_URL = "https://raw.githubusercontent.com/TripSit/drugs/main/drugs.json"
TRIPSIT_SOURCE = "TripSit"
DEFAULT_USER_AGENT = (
    "journal-android-multilingual/0.1 "
    "(+https://github.com/LoliLin/journal-android-multilingual)"
)

#: 本工具允许写入的字段（categories 只对新建条目写，见 run()）
TRIPSIT_MANAGED_FIELDS = ("url", "commonNames", "roas")

#: TripSit 分类 -> 仓库词表；值为 None 表示丢弃
TRIPSIT_CATEGORY_MAP = {
    "empathogen": "entactogen",
    "inactive": None,
    "supplement": None,
}

#: TripSit 给药途径 -> 仓库 AdministrationRoute 名（小写）。未列出的（Vapourized、
#: 植物专用的 Dry/Wet/HBWR/Morning_Glory、带 (Pure) 后缀的）一律跳过并记入报告。
TRIPSIT_ROUTE_MAP = {
    "Oral": "oral",
    "Insufflated": "insufflated",
    "Intranasal": "insufflated",
    "Rectal": "rectal",
    "Sublingual": "sublingual",
    "Buccal": "buccal",
    "Smoked": "smoked",
    "Inhaled": "inhaled",
    "Intravenous": "intravenous",
    "Intramuscular": "intramuscular",
    "Subcutaneous": "subcutaneous",
    "Transdermal": "transdermal",
}

#: 只接受这几种剂量单位（其余如 seeds/drops 跳过并记入报告）
UNIT_MAP = {"mg": "mg", "g": "g", "ml": "ml", "ug": "µg", "µg": "µg", "μg": "µg", "mcg": "µg"}

#: 剂量档位 -> 仓库字段（取区间下限，与 PW 的 *_Min 约定一致）
LEVEL_FIELDS = {"light": "lightMin", "common": "commonMin", "strong": "strongMin", "heavy": "heavyMin"}

DOSE_RE = re.compile(
    r"^(?P<min>\.?[0-9]+(?:\.[0-9]+)?)\s*\+?\s*(?P<unit1>[A-Za-zµμ]+)?"
    r"(?:\s*-\s*(?P<max>\.?[0-9]+(?:\.[0-9]+)?)\s*\+?\s*(?P<unit2>[A-Za-zµμ]+)?)?"
    r"\s*\+?\s*\.?$"
)


def parse_dose(value) -> tuple[float, float | None, str] | None:
    """解析 TripSit 的剂量字符串。

    "40-75mg" -> (40.0, 75.0, "mg")；"50mg" -> (50.0, None, "mg")；
    "175mg+" / "100+mg." / "150mg-300mg+" -> 取区间下限；
    缺单位（"10-15"）、两侧单位不同（"750ug-1mg"）、非质量单位（"1-2 seeds"）、
    "unknown" 一律返回 None（跳过并记入报告，不猜单位）。
    """
    if not isinstance(value, str):
        return None
    match = DOSE_RE.match(value.strip())
    if not match:
        return None
    unit = (match.group("unit1") or match.group("unit2") or "").lower()
    if match.group("unit1") and match.group("unit2") and match.group("unit1").lower() != match.group("unit2").lower():
        return None
    if unit not in UNIT_MAP:
        return None
    low = float(match.group("min"))
    high = float(match.group("max")) if match.group("max") else None
    return low, high, UNIT_MAP[unit]


def number(value):
    """40.0 -> 40；2.5 -> 2.5。"""
    return int(value) if float(value).is_integer() else value


def tripsit_doses(entry: dict, report: dict) -> list:
    """把 formatted_dose 解析成仓库的 roas 结构（跳过无法解析的档位/途径）。"""
    formatted = entry.get("formatted_dose")
    if not isinstance(formatted, dict):
        return []
    roas, skipped = [], []
    for route_key, buckets in sorted(formatted.items()):
        route = TRIPSIT_ROUTE_MAP.get(route_key)
        if not route:
            skipped.append(f"route:{route_key}")
            continue
        if not isinstance(buckets, dict):
            continue
        dose, units = {}, None
        for level, raw in buckets.items():
            field = LEVEL_FIELDS.get(str(level).strip().lower())
            if not field:
                continue
            parsed = parse_dose(raw)
            if not parsed:
                skipped.append(f"{route_key}.{level}={raw}")
                continue
            low, _high, parsed_unit = parsed
            units = units or parsed_unit
            dose[field] = number(low)
        if dose:
            dose = {"units": units or "mg", **dose}
            roas.append({"name": route, "dose": dose})
    if skipped:
        report["skippedDoses"] = skipped
    return roas


def tripsit_categories(entry: dict) -> list:
    """TripSit categories -> 仓库词表（映射后去重；映射为 None 的丢弃）。"""
    out = []
    for name in entry.get("categories") or []:
        mapped = TRIPSIT_CATEGORY_MAP.get(name, name)
        if mapped and mapped not in out:
            out.append(mapped)
    return out


def tripsit_asset(entry: dict, key: str, with_categories: bool, with_doses: bool, report: dict) -> dict:
    """一条 TripSit 记录 -> 仓库 root/<Name>.json 结构。"""
    pretty = entry.get("pretty_name") or entry.get("name") or key
    record: dict = {"name": pretty, "url": f"https://tripsit.me/factsheets/?name={key}&p=substance"}
    common_names = [pretty]
    for alias in entry.get("aliases") or []:
        if isinstance(alias, str) and alias not in common_names:
            common_names.append(alias)
    if len(common_names) > 1:
        record["commonNames"] = common_names
    if with_categories:
        categories = tripsit_categories(entry)
        if categories:
            record["categories"] = categories
    record["isApproved"] = False
    if with_doses:
        roas = tripsit_doses(entry, report)
        if roas:
            record["roas"] = roas
    return record


def load_drugs(args) -> tuple[dict, dict]:
    """读取 TripSit 数据库；返回 (数据, 快照信息)。"""
    if args.file:
        raw = Path(args.file).read_bytes()
        print(f"本地快照：{args.file}")
    else:
        try:
            import requests
        except ImportError:
            die("本工具需要 requests：pip install requests")
        cache_file = Path(args.cache_dir) if args.cache_dir else DEFAULT_WORK_DIR / "tripsit-drugs.json"
        if cache_file.exists() and not args.refresh:
            raw = cache_file.read_bytes()
            print(f"缓存：{cache_file}（{len(raw) // 1024} KB）")
        else:
            if not args.dry_run:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
            print(f"下载：{args.url}")
            response = requests.get(args.url, headers={"User-Agent": args.user_agent}, timeout=120)
            if response.status_code != 200:
                die(f"下载失败 {response.status_code}：{args.url}")
            raw = response.content
            if not args.dry_run:
                cache_file.write_bytes(raw)
                print(f"已缓存 -> {cache_file}")
            else:
                print("--dry-run：不写缓存")
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = {
        "source": TRIPSIT_SOURCE,
        "url": args.url,
        "sha256": digest,
        "hashNote": "本题对下载到的原始字节取哈希（Klop233 的台账对重新序列化后的快照取哈希，故数值不同）。",
    }
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        die(f"解析 TripSit 数据库失败：{exc}")
    if not isinstance(data, dict):
        die("TripSit 数据库根元素不是对象。")
    print(f"条目：{len(data)}，sha256={digest[:16]}…")
    return data, snapshot


def run(args) -> int:
    assets_dir = resolve_assets_dir(args.assets_dir, must_exist=False)
    out_dir = Path(args.out) if args.out else assets_dir / "root"
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    database, snapshot = load_drugs(args)
    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": TRIPSIT_SOURCE,
        "out_dir": str(out_dir),
        "with_doses": args.with_doses,
        "overwrite": args.overwrite,
        "snapshot": snapshot,
        "substances": [],
    }
    added, excluded, resolved = [], [], []
    counts = {"created": 0, "updated": 0, "unchanged": 0}

    items = sorted(database.items())
    if args.limit:
        items = items[: args.limit]
    print(f"本次处理 {len(items)} 条" + ("（--dry-run：不写文件）" if args.dry_run else ""))

    for key, entry in items:
        if not isinstance(entry, dict):
            continue
        pretty = entry.get("pretty_name") or entry.get("name") or key
        resolved.append({"source": TRIPSIT_SOURCE, "key": key, "name": pretty})
        categories = tripsit_categories(entry)
        if not categories:
            excluded.append({
                "source": TRIPSIT_SOURCE,
                "key": key,
                "name": pretty,
                "reason": "TripSit 未标注精神活性分类（inactive/supplement 或为空）。",
            })
            continue

        path = out_dir / f"{sanitize_filename(pretty)}.json"
        existing = read_json(path) if path.exists() else None
        if existing is None and args.only_existing:
            continue
        item_report = {"key": key, "file": path.name, "name": pretty}
        if existing is None:
            incoming = tripsit_asset(entry, key, with_categories=True, with_doses=args.with_doses,
                                     report=item_report)
            merged, changed, kept = incoming, sorted(incoming), []
            counts["created"] += 1
            added.append({"name": pretty, "sources": [{
                "source": TRIPSIT_SOURCE, "key": key, "url": incoming["url"],
            }]})
        else:
            incoming = tripsit_asset(entry, key, with_categories=False, with_doses=args.with_doses,
                                     report=item_report)
            merged, changed, kept = fill_gaps(
                existing, incoming, TRIPSIT_MANAGED_FIELDS, args.overwrite
            )
            counts["updated" if changed else "unchanged"] += 1
        if not args.dry_run and changed:
            write_json(path, merged)
        item_report["changed"] = changed
        item_report["kept"] = kept
        report["substances"].append(item_report)
        if args.verbose and changed:
            print(f"  {path.name}: {', '.join(changed[:6])}{' …' if len(changed) > 6 else ''}")

    report["counts"] = counts
    report_path = Path(args.report) if args.report else (
        (Path(args.cache_dir) if args.cache_dir else DEFAULT_WORK_DIR) / "tripsit-report.json"
    )
    if not args.dry_run:
        write_json(report_path, report)
        if args.ledger:
            merge_ledger(Path(args.ledger), source=TRIPSIT_SOURCE, snapshot=snapshot,
                         added=added, excluded=excluded, resolved=resolved)

    print(f"\n完成：新建 {counts['created']}，更新 {counts['updated']}，无变化 {counts['unchanged']}，"
          f"排除 {len(excluded)}")
    if args.dry_run:
        print("--dry-run：没有写任何文件（缓存除外）；加 --verbose 可看到将变更的字段。")
    else:
        print(f"报告：{report_path}")
        if args.ledger:
            print(f"台账：{args.ledger}（added {len(added)} / excluded {len(excluded)} / resolved {len(resolved)}）")
        print("注意：新条目一律 isApproved=false；未有许可证，未写入 TripSit 的文案。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch_tripsit.py",
        description=(
            "从 TripSit/drugs 的 drugs.json 补全名称、别名、分类与来源链接；"
            "--with-doses 额外把剂量字符串解析成数值。默认只补空缺、不覆盖人工内容。"
        ),
        epilog="字段映射与许可说明：docs/substances-catalog-sources.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", default=DEFAULT_TRIPSIT_URL, help="drugs.json 地址")
    parser.add_argument("--file", help="改用本地快照文件（不下载）")
    parser.add_argument("--cache-dir", help="缓存目录（默认 docs/scripts/_work）")
    parser.add_argument("--out", help="输出目录（默认 <assets>/root）")
    parser.add_argument("--assets-dir", help=f"assets/substances 目录（默认自动探测 {REPO_ASSETS_HINT}）")
    parser.add_argument("--with-doses", action="store_true", help="解析并写入按途径的数值剂量")
    parser.add_argument("--only-existing", action="store_true", help="只补已有条目，不为新物质建文件")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有结构化字段")
    parser.add_argument("--dry-run", action="store_true", help="不写文件、不建目录，只报告会改哪些字段")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存重新下载")
    parser.add_argument("--limit", type=int, help="只处理前 N 条（试跑用）")
    parser.add_argument("--report", help="报告文件（默认 <cache-dir>/tripsit-report.json）")
    parser.add_argument("--ledger", nargs="?", const=str(DEFAULT_LEDGER), default=str(DEFAULT_LEDGER),
                        help=f"目录扩充台账（默认 {DEFAULT_LEDGER}）")
    parser.add_argument("--no-ledger", action="store_true", help="不写台账")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="请求 UA（请保留可联系方式）")
    parser.add_argument("--verbose", action="store_true", help="逐条打印变更字段")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.no_ledger:
        args.ledger = None
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
