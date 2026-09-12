#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 FreeODwiki 补全中文（zh_cn/zh_tw）覆盖层（独立工具）。

FreeODwiki（https://github.com/SalviaSWC/FreeODwiki，CC-BY-SA 4.0）是 PsychonautWiki 的
中文翻译集：`药物/<名称>.md` 里是中文正文 + 信息表（常用名/系统命名/类别归属）+
**按给药途径的剂量表与时长表**。因为内容已经是中文，**这里的产出直接进语言覆盖层，
不需要走机器翻译**。

默认行为（保守）：
- 只写 `<lang>/<Name>.json` 覆盖层，字段默认 `summary`；`--fields` 可加
  `saferUse`/`generalRisks`/`commonNames`/`localizedName`；
- **不动** `root/`（结构化剂量/时长要显式 `--structure fill|check|overwrite`）；
- 不写 `isApproved`、不覆盖已有值（`--overwrite` 才覆盖）。
- 纯中文页名用 `--name-map`（默认 docs/freeodwiki-name-map.json）人工对照；
  加 `--create-root` 才会为仓库里没有的英文名建最小 root 条目。

用法：
    python docs/scripts/fetch_freeodwiki.py --repo <FreeODwiki 检出目录> --dry-run --verbose
    python docs/scripts/fetch_freeodwiki.py --repo … --fields summary,saferUse
    python docs/scripts/fetch_freeodwiki.py --repo … --create-root   # 含对照表里的新物质
    python docs/scripts/fetch_freeodwiki.py --repo … --structure check     # 与 root 交叉校验剂量/时长

来源与映射依据：docs/substances-catalog-sources.md
"""

from __future__ import annotations

import argparse
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

FREEOD_SOURCE = "FreeODwiki"
FREEOD_REPO_URL = "https://github.com/SalviaSWC/FreeODwiki"
FREEOD_DRUG_DIR = "药物"

#: 结构化数据写入 root 时允许改动的字段
FREEOD_STRUCTURE_FIELDS = ("url", "roas")

#: 人工对照表：纯中文页名 -> 仓库英文名；skipped 里的页直接跳过
DEFAULT_NAME_MAP = Path("docs/freeodwiki-name-map.json")

#: 覆盖层允许写入的字段
OVERLAY_FIELDS = ("summary", "saferUse", "generalRisks", "commonNames", "localizedName")

#: 信息表里可能出现的名称行 / 分类行（各家条目用词不统一）
LABEL_NAME_ROWS = ("常用名", "通用名", "取代名称", "系统命名", "系统名", "英文名")
LABEL_CATEGORY_ROWS = ("精神活性类别", "精神活性分类", "类别归属", "分类归属")

#: 中文给药途径 -> 仓库 AdministrationRoute 名（小写）
ROUTE_MAP = {
    "口服": "oral",
    "鼻吸": "insufflated",
    "吸鼻": "insufflated",
    "抽吸": "smoked",
    "吸入": "inhaled",
    "静脉注射": "intravenous",
    "肌肉注射": "intramuscular",
    "皮下注射": "subcutaneous",
    "舌下含服": "sublingual",
    "舌下": "sublingual",
    "颊黏膜": "buccal",
    "直肠给药": "rectal",
    "直肠": "rectal",
    "经皮": "transdermal",
}

#: 中文剂量档位 -> 仓库字段（阈值优先；与 PW 一样丢弃"轻微"区间）
LEVEL_FIELDS = {"阈值": "lightMin", "中等": "commonMin", "强烈": "strongMin", "严重": "heavyMin"}
LEVEL_FALLBACK = {"轻微": "lightMin"}

#: 中文时长段 -> 仓库 duration 段
SEGMENT_MAP = {"总时长": "total", "药效发作": "onset", "药效上升": "comeup", "药效达峰": "peak",
               "药效褪去": "offset", "药效残余": "afterglow", "残留效应": "afterglow"}

#: 时长单位 -> 仓库单位
DURATION_UNITS = {"秒": "seconds", "分钟": "minutes", "分": "minutes", "小时": "hours", "时": "hours"}
DOSE_UNIT_FIX = {"ml": "ml", "毫升": "ml", "l": "l", "mg": "mg", "g": "g", "ug": "µg", "µg": "µg", "mcg": "µg"}

#: 中文精神活性类别 -> 仓库分类
CATEGORY_MAP = {
    "致幻剂": "psychedelic", "迷幻剂": "psychedelic", "兴奋剂": "stimulant", "抑制剂": "depressant",
    "解离剂": "dissociative", "阿片类药物": "opioid", "阿片类": "opioid",
    "苯二氮䓬类物质": "benzodiazepine", "苯二氮卓类物质": "benzodiazepine",
    "大麻素类物质": "cannabinoid", "大麻类": "cannabinoid", "共情剂": "entactogen",
    "谵妄剂": "deliriant", "益智药": "nootropic", "促醒剂": "eugeroic", "促梦剂": "oneirogen",
    "巴比妥类物质": "barbiturate", "抗精神病药": "antipsychotic", "抗抑郁药": "antidepressant",
    "抗焦虑药": "anxiolytic", "抗癫痫药": "antiepileptic", "镇静催眠药": "hypnotic",
    "研究用化学品": "research-chemical",
}

SAFER_USE_HEADINGS = ("减害", "伤害减少", "负责任的用药", "安全使用")
RISK_HEADINGS = ("毒性", "危害", "风险", "滥用潜力", "致死", "过量")

IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
TAG_RE = re.compile(r"<[^>]+>")
BOLD_RE = re.compile(r"\*+")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
ROUTE_MARKER_RE = re.compile(r"⇣\s*[\[［]\s*([^\]］]+?)\s*[\]］]")
RANGE_RE = re.compile(
    r"<?\s*(?P<min>[0-9]+(?:\.[0-9]+)?)"
    r"(?:\s*[-~～]\s*(?P<max>[0-9]+(?:\.[0-9]+)?))?"
    r"\s*(?P<unit>[A-Za-zµμ%]+|毫升|小时|分钟|秒钟?|秒)?"
)


FOOTNOTE_RE = re.compile(r"\[\\?\[\d+\\?\]\]|\[\^?\d+\]")


def plain(text: str) -> str:
    """markdown -> 纯文本：去图片、链接保留文字、去粗体/脚注/行内代码，压缩空白。

    仓库的语言覆盖层是纯文本（应用用 Text 直接渲染），不能留 markdown 语法。
    """
    text = re.sub(r"\[\\?\[\d+\\?\]\]\([^)]*\)", "", text)  # 脚注链接 [\[12\]](#cite_note-12)
    text = IMAGE_RE.sub(" ", text)
    text = LINK_RE.sub(lambda m: m.group(1), text)
    text = re.sub(r"\(#cite_(?:note|ref)[^)]*\)", "", text)  # 兜底：残留的引用锚点
    text = TAG_RE.sub(" ", text)
    text = FOOTNOTE_RE.sub("", text)
    text = re.sub(r"\*+|__|`", "", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def number(value):
    return int(value) if float(value).is_integer() else value


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    front = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            front[key.strip()] = value.strip()
    return front


def parse_tables(text: str) -> list:
    """把文本里的每一张表解析成 [[cell, ...], ...]（按出现顺序，跳过分隔行）。"""
    tables, current = [], []
    for line in text.splitlines():
        if TABLE_ROW_RE.match(line):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
                continue
            current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def parse_h1(text: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, flags=re.M)
    return plain(match.group(1)) if match else ""


def lead_text(text: str) -> str:
    """首个 2–4 级标题之前的部分（各条目用 ## 或 ### 不统一）。"""
    match = re.search(r"^#{2,4}\s", strip_frontmatter(text), flags=re.M)
    return strip_frontmatter(text)[: match.start()] if match else strip_frontmatter(text)


def split_sections(text: str) -> list:
    """返回 [(level, 标题, 正文)]，层级 2–4（FreeODwiki 各条目用 ## 或 ### 不统一）。"""
    pattern = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
    sections, current = [], None
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            if current:
                sections.append(current)
            current = [len(match.group(1)), plain(match.group(2)), []]
            continue
        if current is not None:
            current[2].append(line)
    if current:
        sections.append(current)
    return [(level, title, "\n".join(body)) for level, title, body in sections]


def prose_block(text: str) -> str:
    """段落级纯文本（跳过表格/标题/图片/纯链接/套话），用于风险一类章节。"""
    lines = []
    for line in strip_frontmatter(text).splitlines():
        raw = line.strip()
        if not raw or raw.startswith(("|", ">", "#", "!", "<", "[◀")):
            continue
        if PURE_LINK_RE.match(raw) or HEADING_UNDERLINE_RE.match(raw) or BOILERPLATE_RE.match(plain(raw)):
            continue
        if LABEL_LINE_RE.match(plain(raw)) or WARNING_RE.search(plain(raw)):
            continue
        cleaned = plain(raw)
        if cleaned:
            lines.append(cleaned)
    return "\n\n".join(lines)


LIST_ITEM_RE = re.compile(r"^[-*+]\s")
PURE_LINK_RE = re.compile(r"^\[[^\]]*\]\([^)]*\)\s*$")
BOILERPLATE_RE = re.compile(r"^(强烈建议|更多信息|参见|另见|主条目)")
HEADING_UNDERLINE_RE = re.compile(r"^[=\-]{2,}\s*$")

#: 免责声明/剂量警告这类套话不是正文（FreeODwiki 每条前面都有一段）
WARNING_RE = re.compile(
    r"免责声明|本网站的给药剂量信息|本站的剂量信息|由于个体体重|由于个体间体重|"
    r"请务必从低剂量开始|请参阅负责任|请参阅负责任的用药"
)

#: 信息表的标签行（部分是 **粗体** 伪表格，没有 | 管道）
LABEL_LINE_RE = re.compile(
    r"^(化学名称|常见名称|常用名称|系统名称|系统命名|取代名称|分类|分类归属|精神活性类别|化学类别|给药途径)\s*[：:]"
)

#: localizedName 只在真是中文名时才写（否则会显示成 "DPD" 这样的缩写）
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

#: 剂量表附近的“给药途径”碎片不是摘要（页面没有正文时会把表格当首段）
ROUTE_ONLY_WORDS = {
    "给药途径", "途径", "口服", "抽吸", "鼻吸", "吸入", "舌下", "颊部", "直肠", "经皮",
    "注射", "静脉注射", "肌肉注射", "皮下注射", "口服/鼻吸", "抽吸/吸入",
}


def looks_like_route_fragment(text: str) -> bool:
    if not text:
        return False
    if "⇣" in text:
        return True
    lines = [line.strip().strip("：:") for line in text.splitlines() if line.strip()]
    return bool(lines) and all(line in ROUTE_ONLY_WORDS for line in lines)


def strip_frontmatter(text: str) -> str:
    """去掉 YAML 头、开头的一级标题（含 Setext 下划线）与分隔线。"""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        text = text[end + 4:] if end >= 0 else text
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line or HEADING_UNDERLINE_RE.match(line) or line.startswith("#"):
            index += 1
            continue
        # Setext 标题：标题行 + 紧跟一行 === / --- 下划线（FreeODwiki 的条目名就是这样）
        if index + 1 < len(lines) and HEADING_UNDERLINE_RE.match(lines[index + 1].strip()):
            index += 2
            continue
        break
    return "\n".join(lines[index:])


def prose_paragraphs(text: str, limit: int = 3) -> str:
    """取正文里最前面的连贯段落（跳过表格/引用/列表/标题/图片/纯链接行），返回纯文本。

    注意：以 `**粗体**` 开头的段落是正文，不能当列表项跳过。
    """
    paragraphs, buffer = [], []
    for line in strip_frontmatter(text).splitlines():
        raw = line.strip()
        skip = (
            not raw
            or raw.startswith(("|", ">", "#", "!", "<", "[◀"))
            or LIST_ITEM_RE.match(raw)
            or PURE_LINK_RE.match(raw)
            or HEADING_UNDERLINE_RE.match(raw)
            or BOILERPLATE_RE.match(plain(raw))
            or LABEL_LINE_RE.match(plain(raw))
            or WARNING_RE.search(plain(raw))
        )
        cleaned = "" if skip else plain(raw)
        if not cleaned:
            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []
            if len(paragraphs) >= limit:
                break
            continue
        buffer.append(cleaned)
    if buffer and len(paragraphs) < limit:
        paragraphs.append(" ".join(buffer))
    return "\n\n".join(p.strip() for p in paragraphs[:limit] if p.strip())


def parse_range(value: str) -> tuple[float | None, float | None, str | None]:
    """'10 - 15 mg' / '0.5 ~ 1 mL' / '< 0.5 mL' / '4 mL +' / '3 ~ 5 小时' -> (min, max, unit)。"""
    match = RANGE_RE.search(plain(value))
    if not match:
        return None, None, None
    low = float(match.group("min"))
    high = float(match.group("max")) if match.group("max") else None
    return low, high, (match.group("unit") or "").strip() or None


def route_sections(text: str) -> list:
    """按 `⇣ [途径]` 标记切段（兼容两种版式），返回 [(route, 该段文本)]。"""
    markers = list(ROUTE_MARKER_RE.finditer(text))
    sections = []
    for index, marker in enumerate(markers):
        raw = marker.group(1)
        route = None
        for chinese, mapped in ROUTE_MAP.items():
            if chinese in raw:
                route = mapped
                break
        if not route:
            continue
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        sections.append((route, text[marker.end():end]))
    return sections


def parse_roas(text: str) -> dict:
    """按途径归集剂量与时长。"""
    roas: dict = {}
    for route, section in route_sections(text):
        entry = roas.setdefault(route, {})
        for table in parse_tables(section):
            for cells in table:
                if len(cells) < 2:
                    continue
                label, value = plain(cells[0]), cells[1]
                if "给药途径" in label or label in ("阶段", "给药剂量", "药效时长", "剂量范围", "时长"):
                    continue
                low, high, unit = parse_range(value)
                if low is None:
                    continue
                field = LEVEL_FIELDS.get(label) or (
                    LEVEL_FALLBACK.get(label) if "lightMin" not in entry.get("dose", {}) else None
                )
                if field:
                    dose = entry.setdefault("dose", {})
                    if field in dose:
                        continue
                    dose[field] = number(low)
                    if unit and "units" not in dose:
                        dose["units"] = DOSE_UNIT_FIX.get(unit.lower(), unit)
                    continue
                segment = SEGMENT_MAP.get(label)
                if segment:
                    duration = entry.setdefault("duration", {})
                    parsed = {k: number(v) for k, v in (("min", low), ("max", high)) if v is not None}
                    if unit:
                        parsed["units"] = DURATION_UNITS.get(unit, unit.lower())
                    duration[segment] = parsed
    return {route: data for route, data in roas.items() if len(data) > 1}


def parse_info(text: str) -> dict:
    """信息表：名称行与类别行。"""
    info = {"names": [], "categories": []}
    for table in parse_tables(text):
        for cells in table:
            if len(cells) < 2:
                continue
            label, value = plain(cells[0]), plain(cells[1])
            if not value:
                continue
            if label in LABEL_NAME_ROWS:
                for part in re.split(r"\s+or\s+|[、]|,\s+", value):
                    part = part.strip(" .")
                    if part and part not in info["names"] and not part.isdigit():
                        info["names"].append(part)
            elif label in LABEL_CATEGORY_ROWS or "精神活性" in label:
                for part in re.split(r"[,，、]", value):
                    part = part.strip(" .")
                    if part and part not in info["categories"]:
                        info["categories"].append(part)
    return info


def build_catalog_index(assets_dir: Path, root_stems: set) -> tuple[dict, dict, dict]:
    """用现有资产建反查表：中文名 -> root 名、物质名 -> root 名、别名 -> root 名。

    覆盖层要写到应用真正加载的名字上：语言文件里的 `localizedName` 与 root 的
    `commonNames` 都能把 FreeODwiki 的中文标题/英文别名对回已有的物质条目，
    避免写出没有人加载的孤立覆盖层，也避免把系统命名当成新物质。
    只统计有对应 root 条目的覆盖层——孤立覆盖层（应用不加载）不能作为命名依据。
    """
    zh_index: dict = {}
    name_index: dict = {}
    alias_index: dict = {}
    for lang in ("zh_cn", "zh_tw"):
        for path in sorted((assets_dir / lang).glob("*.json")):
            if path.stem not in root_stems:
                continue
            localized = (read_json(path).get("localizedName") or "").strip()
            if localized:
                zh_index.setdefault(localized, path.stem)
    for path in sorted((assets_dir / "root").glob("*.json")):
        if path.name == "_categories.json":
            continue
        data = read_json(path)
        name_index.setdefault(fold_name(data.get("name") or path.stem), path.stem)
        for alias in data.get("commonNames") or []:
            if isinstance(alias, str) and alias.strip():
                alias_index.setdefault(fold_name(alias), path.stem)
    return zh_index, name_index, alias_index


def fold_name(text: str) -> str:
    """去大小写与标点，用于反查（1,3,7-Trimethylxanthine == 137trimethylxanthine）。"""
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def canonical_name(stem: str, front: dict, h1: str, names: list, root_stems: set,
                   name_map: dict | None = None, zh_index: dict | None = None,
                   name_index: dict | None = None,
                   alias_index: dict | None = None) -> tuple[str, str]:
    """确定条目名与依据。优先级：root 同名 → 人工对照表 → 中文名反查 → 页面上的英文名按
    「物质名 → 别名」两轮反查（物质名优先，避免 "DPD" 这类缩写把页面配到别的物质）→
    最后才当新名字（仅当它不像系统命名）。"""
    if stem in root_stems:
        return stem, "root-stem"
    if name_map and stem in name_map:
        return name_map[stem], "name-map"
    zh_index = zh_index or {}
    name_index = name_index or {}
    alias_index = alias_index or {}
    for candidate in [stem, front.get("title", ""), h1] + list(names):
        text = (candidate or "").strip()
        if text and text in zh_index:
            return zh_index[text], "zh-localizedName"
        base = re.sub(r"[（(].*?[)）]\s*$", "", text).strip()
        if base and base in zh_index:
            return zh_index[base], "zh-localizedName"
    candidates = [(c or "").strip() for c in [front.get("title", ""), h1] + list(names)]
    for text in candidates:
        if len(text) < 2 or text.isdigit():
            continue
        if text in root_stems:
            return text, "root-stem"
        folded = fold_name(text)
        if folded in name_index:
            return name_index[folded], "name-fold"
    for text in candidates:
        if len(text) < 2:
            continue
        folded = fold_name(text)
        if folded and folded in alias_index:
            return alias_index[folded], "alias-fold"
    for text in candidates:
        # 不像系统命名（无括号/逗号）才接受为新英文名，否则交人工对照表
        if len(text) >= 2 and text.isascii() and not text.isdigit() and not re.search(r"[(),\[\]]", text):
            return text, "ascii-name"
    return stem, "unresolved-name"


def load_name_map(path) -> tuple[dict, dict, str]:
    """加载人工对照表 {map: {页名: 仓库名}, skipped: {页名: 原因}}。"""
    if not path:
        return {}, {}, ""
    target = Path(path)
    if not target.exists():
        return {}, {}, ""
    data = read_json(target)
    if not isinstance(data, dict):
        die(f"名称对照表 '{target}' 应该是对象。")
    mapping = {k: v for k, v in (data.get("map") or {}).items() if isinstance(v, str)}
    skipped = {k: str(v) for k, v in (data.get("skipped") or {}).items()}
    return mapping, skipped, str(target)


def parse_entry(path: Path, root_stems: set, name_map: dict | None = None,
                zh_index: dict | None = None, name_index: dict | None = None,
                alias_index: dict | None = None) -> dict:
    text = path.read_text(encoding="utf-8")
    front = parse_frontmatter(text)
    h1 = parse_h1(text)
    info = parse_info(text)
    name, name_source = canonical_name(path.stem, front, h1, info["names"], root_stems,
                                       name_map, zh_index, name_index, alias_index)
    sections = split_sections(text)
    safer_use, risk_blocks = [], []
    for _level, title, body in sections:
        if any(key in title for key in SAFER_USE_HEADINGS):
            safer_use.extend(
                item for item in (
                    plain(line.strip().lstrip("-*+").strip())
                    for line in body.splitlines() if LIST_ITEM_RE.match(line.strip())
                ) if item and not BOILERPLATE_RE.match(item)
            )
        elif any(key in title for key in RISK_HEADINGS):
            block = prose_block(body)
            if block:
                risk_blocks.append(f"{title}\n{block}")

    categories = []
    for raw in info["categories"]:
        mapped = CATEGORY_MAP.get(raw)
        if mapped and mapped not in categories:
            categories.append(mapped)
    summary = prose_paragraphs(lead_text(text), limit=2)
    if looks_like_route_fragment(summary):
        summary = ""
    localized_name = ""
    for candidate in [front.get("title"), h1, path.stem] + list(info["names"]):
        text_value = (candidate or "").strip()
        if text_value and CJK_RE.search(text_value):
            localized_name = text_value
            break
    return {
        "file": path.name,
        "stem": path.stem,
        "name": name,
        "name_source": name_source,
        "localized_name": localized_name,
        "names": info["names"],
        "categories": categories,
        "unmapped_categories": [c for c in info["categories"] if c not in CATEGORY_MAP],
        "summary": summary,
        "saferUse": safer_use,
        "risks": "\n\n".join(risk_blocks),
        "sections": [title for _level, title, _body in sections],
        "roas": parse_roas(text),
    }


def build_overlay(entry: dict, fields: list) -> dict:
    overlay: dict = {}
    if "commonNames" in fields and entry["names"]:
        names = [entry["name"]] + [n for n in entry["names"] if n != entry["name"]]
        if len(names) > 1:
            overlay["commonNames"] = names
    if "summary" in fields and entry["summary"]:
        overlay["summary"] = entry["summary"]
    if "saferUse" in fields and entry["saferUse"]:
        overlay["saferUse"] = entry["saferUse"]
    if "generalRisks" in fields and entry["risks"]:
        overlay["generalRisks"] = entry["risks"]
    if "localizedName" in fields and entry["localized_name"]:
        # 与英文名相同就没有信息量（应用本来就会回退到 name），不写冗余键
        if entry["localized_name"] != entry["name"]:
            overlay["localizedName"] = entry["localized_name"]
    return overlay


def compare_structure(root_roas: list, freeod_roas: dict) -> list:
    """比较 root 与 FreeODwiki 的剂量/时长（只比共同途径，报告用）。"""
    diffs = []
    by_name = {r.get("name"): r for r in root_roas if isinstance(r, dict)}
    for route, data in sorted(freeod_roas.items()):
        target = by_name.get(route)
        if not target:
            diffs.append({"route": route, "kind": "route-missing-in-root"})
            continue
        for block in ("dose", "duration"):
            for key, value in (data.get(block) or {}).items():
                current = (target.get(block) or {}).get(key)
                if current != value:
                    diffs.append({"route": route, "field": f"{block}.{key}",
                                  "root": current, "freeod": value})
    return diffs


def run(args) -> int:
    assets_dir = resolve_assets_dir(args.assets_dir, must_exist=False)
    repo_dir = Path(args.repo) if args.repo else None
    if repo_dir is None or not repo_dir.is_dir():
        die("需要 --repo 指向 FreeODwiki 的检出目录（工具不自动克隆；"
            f"仓库地址 {FREEOD_REPO_URL}）。")
    drug_dir = repo_dir / FREEOD_DRUG_DIR
    if not drug_dir.is_dir():
        die(f"--repo 下找不到 {FREEOD_DRUG_DIR}/ 目录：{repo_dir}")

    lang_dir = Path(args.out) if args.out else assets_dir / args.lang
    root_dir = assets_dir / "root"
    root_stems = {p.stem for p in root_dir.glob("*.json")} if root_dir.is_dir() else set()
    name_map, skipped_pages, name_map_path = load_name_map(args.name_map)
    zh_index, name_index, alias_index = build_catalog_index(assets_dir, root_stems)
    if not args.dry_run:
        lang_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(drug_dir.glob("*.md"))
    if args.limit:
        files = files[: args.limit]
    print(f"FreeODwiki：{drug_dir}（{len(files)} 个条目）")
    print(f"覆盖层输出：{lang_dir}（语言 {args.lang}）")
    print(f"字段：{', '.join(args.fields)} | root 结构：{args.structure}"
          + (f" | 名称对照表：{name_map_path}（{len(name_map)} 条映射，{len(skipped_pages)} 条跳过）"
             if name_map_path else ""))
    print(f"反查表：中文名 {len(zh_index)} 条、物质名 {len(name_index)} 条、别名 {len(alias_index)} 条")

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": FREEOD_SOURCE,
        "repo": str(repo_dir),
        "lang": args.lang,
        "out_dir": str(lang_dir),
        "fields": args.fields,
        "structure": args.structure,
        "entries": [],
    }
    added, resolved, notes, excluded = [], [], [], []
    counts = {"created": 0, "updated": 0, "unchanged": 0, "no_fields": 0,
              "skipped_by_map": 0, "root_created": 0}
    root_created: list = []
    structure_diffs, used_categories, no_dose = [], set(), 0

    for path in files:
        if path.stem in skipped_pages:
            excluded.append({"source": FREEOD_SOURCE, "key": path.stem, "name": "",
                             "reason": f"人工对照表标记跳过：{skipped_pages[path.stem]}"})
            counts["skipped_by_map"] += 1
            continue
        entry = parse_entry(path, root_stems, name_map, zh_index, name_index, alias_index)
        name = entry["name"]
        resolved.append({"source": FREEOD_SOURCE, "key": entry["stem"], "name": name})
        if entry["name_source"] == "unresolved-name":
            excluded.append({
                "source": FREEOD_SOURCE, "key": entry["stem"], "name": entry["localized_name"],
                "reason": "条目里找不到 ASCII 名称（常用名/系统命名均为中文），需要人工定英文名。",
            })
            continue
        if entry["stem"] != name:
            notes.append({"source": FREEOD_SOURCE, "key": entry["stem"], "name": name,
                          "note": f"文件名 '{entry['stem']}' 对应英文名 '{name}'。"})
        if not entry["roas"]:
            no_dose += 1
        used_categories.update(entry["categories"])

        # 对照表把纯中文页映射成了仓库里没有的英文名：建一个最小的 root 条目
        # （只有名称/来源/分类，正文仍走覆盖层），否则覆盖层没有对应物质、应用不会加载。
        if args.create_root and name not in root_stems:
            has_content = any(entry[key] for key in ("summary", "risks", "saferUse", "roas"))
            if not has_content:
                excluded.append({
                    "source": FREEOD_SOURCE, "key": entry["stem"], "name": name,
                    "reason": "对照表有英文名，但条目里没有可写内容（无正文、无剂量表），不建条目。",
                })
                counts["skipped_by_map"] += 1
                continue
            incoming = {"name": name, "isApproved": False,
                        "url": f"{FREEOD_REPO_URL}/blob/main/{FREEOD_DRUG_DIR}/{entry['file']}"}
            if entry["categories"]:
                incoming["categories"] = entry["categories"]
            if not args.dry_run:
                write_json(root_dir / f"{sanitize_filename(name)}.json", incoming)
                root_stems.add(name)
            root_created.append(name)
            counts["root_created"] += 1

        overlay = build_overlay(entry, args.fields)
        overlay_path = lang_dir / f"{sanitize_filename(name)}.json"
        existing = read_json(overlay_path) if overlay_path.exists() else None
        item = {"stem": entry["stem"], "name": name, "file": overlay_path.name,
                "routes": sorted(entry["roas"]), "sections": entry["sections"],
                "unmappedCategories": entry["unmapped_categories"]}
        if existing is None and not overlay:
            # 没有任何可写字段（例如 localizedName 与英文名相同）：不建空文件
            counts["no_fields"] += 1
            item.update(changed=False, kept=[])
            report["entries"].append(item)
            continue
        if existing is None:
            merged, changed, kept = overlay, sorted(overlay), []
            counts["created"] += 1
            added.append({"name": name, "sources": [{
                "source": FREEOD_SOURCE, "key": entry["stem"],
                "url": f"{FREEOD_REPO_URL}/blob/main/{FREEOD_DRUG_DIR}/{entry['file']}",
            }]})
        else:
            merged, changed, kept = fill_gaps(existing, overlay, OVERLAY_FIELDS, args.overwrite)
            counts["updated" if changed else "unchanged"] += 1
        if not args.dry_run and changed:
            write_json(overlay_path, merged)
        item["changed"] = changed
        item["kept"] = kept

        if args.structure != "skip" and entry["roas"] and name in root_stems:
            root_path = root_dir / f"{sanitize_filename(name)}.json"
            root = read_json(root_path)
            diffs = compare_structure(root.get("roas") or [], entry["roas"])
            item["structureDiffs"] = diffs
            structure_diffs.extend((name, diff) for diff in diffs)
            if args.structure in ("fill", "overwrite") and diffs and not args.dry_run:
                incoming = {"url": f"{FREEOD_REPO_URL}/blob/main/{FREEOD_DRUG_DIR}/{entry['file']}",
                            "roas": entry["roas"]}
                fill_gaps(root, incoming, FREEOD_STRUCTURE_FIELDS, args.structure == "overwrite")

        report["entries"].append(item)
        if args.verbose and changed:
            print(f"  {item['file']}: {', '.join(changed)}")

    warn_unknown_categories(sorted(used_categories), FREEOD_SOURCE)
    report["counts"] = counts
    report["nameMap"] = name_map_path
    report["createdRootEntries"] = root_created
    report["entriesWithoutDoseTables"] = no_dose
    report["structureDiffCount"] = len(structure_diffs)
    report_path = Path(args.report) if args.report else DEFAULT_WORK_DIR / "freeodwiki-report.json"
    if not args.dry_run:
        write_json(report_path, report)
        if args.ledger:
            merge_ledger(
                Path(args.ledger), source=FREEOD_SOURCE,
                snapshot={"source": FREEOD_SOURCE, "url": FREEOD_REPO_URL,
                          "version": args.version or "",
                          "hashNote": "解析本地检出，未记录快照哈希。"},
                added=added, excluded=excluded, resolved=resolved, notes=notes,
            )

    print(f"\n完成：新建 {counts['created']}，更新 {counts['updated']}，无变化 {counts['unchanged']}，"
          f"无字段可写 {counts['no_fields']}，新建 root {counts['root_created']}，"
          f"对照表跳过/无内容 {counts['skipped_by_map']}，待人工定名 {len(excluded) - counts['skipped_by_map']}")
    if root_created:
        print(f"新建的 root 条目：{'、'.join(root_created)}")
    print(f"没有剂量表的条目：{no_dose}；结构差异：{len(structure_diffs)}")
    if args.dry_run:
        print("--dry-run：没有写任何文件。")
    else:
        print(f"报告：{report_path}")
        if args.ledger:
            print(f"台账：{args.ledger}（added {len(added)} / resolved {len(resolved)} / notes {len(notes)}）")
        print("提醒：FreeODwiki 是 PW 的中文翻译，CC-BY-SA 4.0，请保留来源链接与署名。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch_freeodwiki.py",
        description=(
            "解析 FreeODwiki 的中文条目，写入语言覆盖层（默认 zh_cn）；内容已是中文，"
            "不需要机器翻译。默认只写 summary，不动 root。"
        ),
        epilog="来源与映射：docs/substances-catalog-sources.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo", help="FreeODwiki 检出目录（必填；工具不自动克隆）")
    parser.add_argument("--lang", default="zh_cn", help="目标语言覆盖层（默认 zh_cn）")
    parser.add_argument("--out", help="覆盖层输出目录（默认 <assets>/<lang>）")
    parser.add_argument("--assets-dir", help=f"assets/substances 目录（默认自动探测 {REPO_ASSETS_HINT}）")
    parser.add_argument("--fields", default="summary",
                        help="写入覆盖层的字段，逗号分隔：" + ",".join(OVERLAY_FIELDS))
    parser.add_argument("--structure", choices=("skip", "check", "fill", "overwrite"), default="skip",
                        help="对 root 的结构化剂量/时长：skip(默认)/check(只报告)/fill(只补空缺)/overwrite")
    parser.add_argument("--version", default="", help="FreeODwiki 版本说明（写进台账快照）")
    parser.add_argument("--name-map", default=str(DEFAULT_NAME_MAP),
                        help=f"人工名称对照表（默认 {DEFAULT_NAME_MAP}；"
                             "{{map: {{页名: 仓库名}}, skipped: {{页名: 原因}}}}）")
    parser.add_argument("--create-root", action="store_true",
                        help="对照表映射到仓库里没有的英文名时，建一个最小 root 条目（名称/来源/分类）")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖覆盖层里已有的值")
    parser.add_argument("--dry-run", action="store_true", help="不写文件、不建目录，只报告")
    parser.add_argument("--limit", type=int, help="只处理前 N 条（试跑用）")
    parser.add_argument("--report", help="报告文件（默认 docs/scripts/_work/freeodwiki-report.json）")
    parser.add_argument("--ledger", nargs="?", const=str(DEFAULT_LEDGER), default=str(DEFAULT_LEDGER),
                        help=f"目录扩充台账（默认 {DEFAULT_LEDGER}）")
    parser.add_argument("--no-ledger", action="store_true", help="不写台账")
    parser.add_argument("--verbose", action="store_true", help="逐条打印变更字段")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.no_ledger:
        args.ledger = None
    args.fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    for field in args.fields:
        if field not in OVERLAY_FIELDS:
            die(f"--fields 不支持 '{field}'；可选：{', '.join(OVERLAY_FIELDS)}")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
