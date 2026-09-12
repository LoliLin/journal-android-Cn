#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 EUDA 的 NPS 通报表补全 substance 条目（独立工具）。

EUDA（原 EMCDDA）欧洲毒品报告里最有价值的机读入口是 NPS 通报表（CSV）：

    "Common name","IUPAC name","EUDA classification","Date of formal notification","Country"

本工具默认**不联网**：EUDA 站点有 Cloudflare 挑战，脚本直接下载拿不到 CSV，请先在浏览器里
下载好再喂进来（`--csv`）。`--url` 仅作尽力尝试，失败会给出明确提示。

写入内容：
    name        通报的 Common name
    url         EUDA 报告页（与 Klop233 那轮一致）
    categories  由 EUDA classification 映射（见 EUDA_CLASS_CATEGORIES）
    isApproved  false

`--mark-nps` 会额外加上 `research-chemical` + `tentative`（复刻参考目录对新通报 NPS 的做法）；
`--with-template-summary` 写 "Name. Classification: …" 模板摘要。默认只补空缺、不覆盖人工内容。

用法：
    python docs/scripts/fetch_euda.py --csv ~/Downloads/edr2026-nps-table-6-notifications_en.csv
    python docs/scripts/fetch_euda.py --csv …csv --dry-run --verbose

来源与映射依据：docs/substances-catalog-sources.md
"""

from __future__ import annotations

import argparse
import csv
import io
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

EUDA_SOURCE = "EUDA"
EUDA_REPORT_URL = (
    "https://www.euda.europa.eu/publications/european-drug-report/2026/"
    "new-psychoactive-substances_en"
)
#: 欧洲毒品报告 2026 的 NPS 通报表（表 7.1 / 数据节点 33313）
DEFAULT_EUDA_CSV_URL = (
    "https://www.euda.europa.eu/sites/default/files/data/data-nodes/33313/versions/56/"
    "edr2026-nps-table-6-notifications_en.csv"
)
DEFAULT_USER_AGENT = (
    "journal-android-multilingual/0.1 "
    "(+https://github.com/LoliLin/journal-android-multilingual)"
)

EUDA_MANAGED_FIELDS = ("url",)

#: EUDA classification -> 仓库分类（有先例的才映射，其余交给人工）
EUDA_CLASS_CATEGORIES = {
    "arylcyclohexylamine": "dissociative",
    "benzodiazepines": "benzodiazepine",
    "cannabinoids": "cannabinoid",
    "cathinones": "stimulant",
    "opioids": "opioid",
    "others": None,
}

#: 模板摘要用的英文标签（与参考目录一致）
EUDA_CLASS_LABELS = {
    "arylcyclohexylamine": "Arylcyclohexylamine",
    "benzodiazepine": "Benzodiazepine",
    "cannabinoid": "Cannabinoid",
    "opioid": "Opioid",
    "stimulant": "Stimulant",
}

COLUMN_ALIASES = {
    "name": ("common name", "name", "substance"),
    "iupac": ("iupac name", "iupac"),
    "classification": ("euda classification", "classification", "category"),
    "date": ("date of formal notification", "notification date", "date"),
    "country": ("country", "country of notification"),
}

CSV_RE = re.compile(r"^[A-Za-z0-9._-]+\.csv$", re.I)


def pick_columns(fieldnames: list) -> dict:
    """按别名匹配 CSV 列名（大小写无关）。"""
    lowered = {name.strip().lower(): name for name in fieldnames if name}
    mapping = {}
    for key, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[key] = lowered[alias]
                break
    return mapping


def read_csv(path: Path) -> tuple[list, dict]:
    """读取 CSV；返回 (行列表, 列映射)。UTF-8 优先，回退到常见编码。"""
    raw = path.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        die(f"无法解码 '{path}'。")
    reader = csv.DictReader(io.StringIO(text))
    columns = pick_columns(reader.fieldnames or [])
    if "name" not in columns:
        die(f"'{path}' 里找不到名称列（现有列：{reader.fieldnames}）。")
    return list(reader), columns


def euda_categories(classification: str, mark_nps: bool) -> list:
    """EUDA classification -> 仓库分类；`Others`/未知分类返回空。"""
    key = (classification or "").strip().lower()
    if key not in EUDA_CLASS_CATEGORIES:
        return []
    mapped = EUDA_CLASS_CATEGORIES[key]
    if mapped is None:
        return []
    categories = [mapped]
    if mark_nps:
        for extra in ("research-chemical", "tentative"):
            if extra not in categories:
                categories.append(extra)
    return categories


def load_rows(args) -> list:
    """从 --csv 或 --url 取数据行。"""
    if args.csv:
        path = Path(args.csv)
        if not path.exists():
            die(f"CSV 不存在：{path}")
        rows, columns = read_csv(path)
        print(f"本地 CSV：{path}（{len(rows)} 行，列映射：{columns}）")
        return rows
    try:
        import requests
    except ImportError:
        die("本工具需要 requests：pip install requests")
    print(f"尝试下载：{args.url}")
    response = requests.get(
        args.url, headers={"User-Agent": args.user_agent, "Accept": "text/csv,*/*"}, timeout=120
    )
    if response.status_code != 200:
        die(f"下载失败 {response.status_code}。EUDA 有 Cloudflare 挑战，"
            "请在浏览器里下载 CSV 后用 --csv 传入。")
    body = response.content
    if body[:512].lstrip().lower().startswith(b"<!doctype html") or b"Just a moment" in body[:2048]:
        die("拿到的是 Cloudflare 挑战页而不是 CSV：请在浏览器里下载后用 --csv 传入。")
    if not args.dry_run:
        cache = Path(args.cache_dir) if args.cache_dir else DEFAULT_WORK_DIR / "euda-notifications.csv"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(body)
        print(f"已缓存 -> {cache}")
    text = body.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def run(args) -> int:
    assets_dir = resolve_assets_dir(args.assets_dir, must_exist=False)
    out_dir = Path(args.out) if args.out else assets_dir / "root"
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(args)
    if args.limit:
        rows = rows[: args.limit]
    columns = pick_columns(list(rows[0].keys())) if rows else {}
    print(f"本次处理 {len(rows)} 行" + ("（--dry-run：不写文件）" if args.dry_run else ""))

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": EUDA_SOURCE,
        "url": args.url,
        "csv": args.csv,
        "out_dir": str(out_dir),
        "overwrite": args.overwrite,
        "substances": [],
    }
    added, excluded, resolved = [], [], []
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    used_categories: set = set()

    for row in rows:
        name = (row.get(columns.get("name", "")) or "").strip()
        if not name:
            continue
        classification = (row.get(columns.get("classification", "")) or "").strip()
        iupac = (row.get(columns.get("iupac", "")) or "").strip()
        date = (row.get(columns.get("date", "")) or "").strip()
        country = (row.get(columns.get("country", "")) or "").strip()
        resolved.append({"source": EUDA_SOURCE, "key": name, "name": name})

        categories = euda_categories(classification, args.mark_nps)
        item = {
            "name": name, "classification": classification, "iupac": iupac,
            "notified": date, "country": country, "file": f"{sanitize_filename(name)}.json",
        }
        if not categories:
            excluded.append({
                "source": EUDA_SOURCE,
                "key": name,
                "name": name,
                "reason": f"EUDA 分类 '{classification or '(空)'}' 没有对应仓库分类，需人工归类。",
            })
            report["substances"].append(item)
            continue
        used_categories.update(categories)

        path = out_dir / f"{sanitize_filename(name)}.json"
        existing = read_json(path) if path.exists() else None
        if existing is None and args.only_existing:
            continue
        if existing is None:
            incoming: dict = {"name": name, "url": EUDA_REPORT_URL, "isApproved": False}
            if categories:
                incoming["categories"] = categories
            if args.with_template_summary:
                label = ", ".join(
                    EUDA_CLASS_LABELS.get(category, category) for category in categories
                    if category in EUDA_CLASS_LABELS
                ) or EUDA_SOURCE
                incoming["summary"] = f"{name}. Classification: {label}."
            merged, changed, kept = incoming, sorted(incoming), []
            counts["created"] += 1
            added.append({"name": name, "sources": [{
                "source": EUDA_SOURCE, "key": name, "url": EUDA_REPORT_URL,
            }]})
        else:
            merged, changed, kept = fill_gaps(
                existing, {"url": EUDA_REPORT_URL}, EUDA_MANAGED_FIELDS, args.overwrite
            )
            counts["updated" if changed else "unchanged"] += 1
        if not args.dry_run and changed:
            write_json(path, merged)
        item["changed"] = changed
        item["kept"] = kept
        report["substances"].append(item)
        if args.verbose and changed:
            print(f"  {item['file']}: {', '.join(changed[:6])}")

    report["counts"] = counts
    report_path = Path(args.report) if args.report else (
        (Path(args.cache_dir) if args.cache_dir else DEFAULT_WORK_DIR) / "euda-report.json"
    )
    if not args.dry_run:
        write_json(report_path, report)
        if args.ledger:
            merge_ledger(
                Path(args.ledger), source=EUDA_SOURCE,
                snapshot={"source": EUDA_SOURCE, "url": args.url},
                added=added, excluded=excluded, resolved=resolved,
            )

    warn_unknown_categories(sorted(used_categories), EUDA_SOURCE)
    print(f"\n完成：新建 {counts['created']}，更新 {counts['updated']}，无变化 {counts['unchanged']}，"
          f"待人工归类 {len(excluded)}")
    if args.dry_run:
        print("--dry-run：没有写任何文件。")
    else:
        print(f"报告：{report_path}")
        if args.ledger:
            print(f"台账：{args.ledger}（added {len(added)} / excluded {len(excluded)} / resolved {len(resolved)}）")
        print("注意：EUDA 只提供名称/分类/通报信息，不含剂量、时长与文案。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch_euda.py",
        description=(
            "解析 EUDA 的 NPS 通报表（CSV），补全名称、分类与来源链接。"
            "默认不联网：请先用浏览器下载 CSV，再用 --csv 传入。"
        ),
        epilog="来源说明：docs/substances-catalog-sources.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--csv", help="本地 CSV（推荐；EUDA 有 Cloudflare 挑战）")
    parser.add_argument("--url", default=DEFAULT_EUDA_CSV_URL, help="CSV 直链（尽力尝试）")
    parser.add_argument("--cache-dir", help="缓存目录（默认 docs/scripts/_work）")
    parser.add_argument("--out", help="输出目录（默认 <assets>/root）")
    parser.add_argument("--assets-dir", help=f"assets/substances 目录（默认自动探测 {REPO_ASSETS_HINT}）")
    parser.add_argument("--mark-nps", action="store_true",
                        help="额外加 research-chemical + tentative（复刻参考目录的做法）")
    parser.add_argument("--with-template-summary", action="store_true",
                        help="为新条目写 'Name. Classification: …' 模板摘要（默认不写）")
    parser.add_argument("--only-existing", action="store_true", help="只补已有条目，不新建文件")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有结构化字段")
    parser.add_argument("--dry-run", action="store_true", help="不写文件、不建目录，只报告")
    parser.add_argument("--limit", type=int, help="只处理前 N 行（试跑用）")
    parser.add_argument("--report", help="报告文件（默认 <cache-dir>/euda-report.json）")
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
