#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docs/scripts 下各工具共用的最小工具集。

只放跨工具共用的东西：路径定位、JSON 读写、数字归一化，以及被多个工具引用的映射表。
各工具自己负责参数解析与业务逻辑，互不导入。

现有工具：
  substances_pipeline.py   本地数据流水线（拆分/骨架/常量/翻译/回填/校对）
  fetch_psychonautwiki.py  从 PsychonautWiki 抓取结构化字段
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

#: 从仓库根目录运行时，assets 的默认位置
REPO_ASSETS_HINT = Path("app/src/main/assets/substances")

#: 中间产物默认目录，跟随本文件位置，已在 .gitignore 中
DEFAULT_WORK_DIR = Path(__file__).resolve().parent / "_work"

#: crossTolerances 历史变体 -> 标准名称（substances_pipeline 的 fix-tolerances 与
#: fetch_psychonautwiki 共用：前者修历史数据，后者避免把复数写法写回去）
CROSS_TOLERANCE_FIXES = {
    "psychedelics": "psychedelic",
    "stimulants": "stimulant",
    "Stimulants": "stimulant",
    "entactogens": "entactogen",
    "opioids": "opioid",
    "dissociatives": "dissociative",
    "Dissociatives": "dissociative",
    "dissociative|dissociatives": "dissociative",
    "benzodiazepines": "benzodiazepine",
    "Benzodiazepines": "benzodiazepine",
    "cannabinoids": "cannabinoid",
    "nootropic|nootropics": "nootropic",
    "Deliriants": "deliriant",
    "Barbiturates": "barbiturate",
    "Antipsychotics": "antipsychotic",
    "trycyclic antidepressants": "antidepressant",
}


# --------------------------------------------------------------------------
# 分类词表：各来源工具写入 categories 前先对照，避免 UI 出现 missing_key
# --------------------------------------------------------------------------

#: 应用已采用并已翻译的分类（Klop233 的扩充分支；对应 lang/*.json 里的 categories.<name>）
KNOWN_CATEGORIES = {
    "common", "psychedelic", "stimulant", "entactogen", "depressant", "opioid",
    "habit-forming", "research-chemical", "tentative", "dissociative", "benzodiazepine",
    "cannabinoid", "nootropic", "deliriant", "barbiturate", "eugeroic", "hallucinogen",
    "oneirogen", "antipsychotic", "antidepressant", "hypnotic", "mood-stabilizer",
    "antiparkinsonian", "anxiolytic", "adhd-medication", "antiepileptic", "antidementia",
    "addiction-treatment", "centrally-acting-medication", "ssri", "maoi", "botanical",
    "anesthetic",
}


def warn_unknown_categories(categories, source: str) -> list:
    """返回不在 KNOWN_CATEGORIES 里的分类，并提示需要补 lang/*.json 的翻译键。"""
    unknown = [name for name in categories if name not in KNOWN_CATEGORIES]
    if unknown:
        print(
            f"警告：{source} 产生的分类 {', '.join(unknown)} 不在已知词表内；"
            "写入后需要在 app/src/main/assets/lang/*.json 补 categories.<name> 翻译键，"
            "否则界面会显示 missing_key。"
        )
    return unknown


def fold_key(text: str) -> str:
    """折叠写法：去大小写与非字母数字，用来把不同写法对到同一个键。

    例：'Stimulants'/'stimulants' -> 'stimulants'，'aMT'/'ΑMT'/'amt' -> 'mt'（希腊字母被去掉）。
    """
    return re.sub(r"[^a-z0-9]", "", (text or "").casefold())


def die(message: str, code: int = 1):
    """打印错误并退出。"""
    print(f"错误：{message}", file=sys.stderr)
    raise SystemExit(code)


def resolve_assets_dir(cli_value: str | None, must_exist: bool = True) -> Path:
    """定位 assets/substances 目录。

    优先用 --assets-dir；否则若当前目录下存在 app/src/main/assets/substances 就用它；
    否则退回当前目录（兼容“先 cd 进 substances 目录再跑”的旧习惯）。

    must_exist=False 用于自举命令：目录不存在时提示并继续（稍后按需创建）。
    """
    if cli_value:
        candidate = Path(cli_value)
        if not candidate.is_dir():
            if must_exist:
                die(f"--assets-dir '{cli_value}' 不存在或不是目录。")
            print(f"提示：'{candidate}' 尚不存在，将按需创建。")
        return candidate
    from_cwd = Path.cwd() / REPO_ASSETS_HINT
    if from_cwd.is_dir():
        return from_cwd
    return Path.cwd()


def resolve_work_dir(cli_value: str | None) -> Path:
    """中间产物目录，默认 docs/scripts/_work/。"""
    work_dir = Path(cli_value) if cli_value else DEFAULT_WORK_DIR
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def sanitize_filename(name: str) -> str:
    """把字符串中的非法文件名字符替换为下划线。"""
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def read_json(path: Path):
    """读取 JSON，失败时给出可操作的报错。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        die(f"文件 '{path}' 不存在。")
    except json.JSONDecodeError as exc:
        die(f"'{path}' 不是合法 JSON：{exc}")


def write_json(path: Path, data) -> None:
    """按项目约定写 JSON（2 空格缩进、不转义非 ASCII）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except IOError as exc:
        die(f"写入 '{path}' 失败：{exc}")


def number(value):
    """浮点整数化：接口常返回 20.0，仓库里存的是 20。"""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# --------------------------------------------------------------------------
# 资产合并：默认只补空缺，绝不覆盖人工内容
# --------------------------------------------------------------------------


def fill_roas(existing_roas: list, incoming_roas: list, overwrite: bool = False):
    """按途径逐个补齐 dose/duration/bioavailability 里缺失的小项。

    返回 (合并后的 roas, 变更说明, 因已存在而保留的说明)。overwrite=True 时整条替换。
    """
    if overwrite or not existing_roas:
        return incoming_roas, [f"{r['name']}(整条)" for r in incoming_roas], []
    merged = list(existing_roas)
    index = {r.get("name"): i for i, r in enumerate(merged) if isinstance(r, dict)}
    notes, kept = [], []
    for incoming in incoming_roas:
        name = incoming.get("name")
        if name not in index:
            merged.append(incoming)
            notes.append(f"{name}(新增)")
            continue
        target = merged[index[name]]
        for block in ("dose", "duration", "bioavailability"):
            value = incoming.get(block)
            if not value:
                continue
            if not target.get(block):
                target[block] = value
                notes.append(f"{name}.{block}")
                continue
            for key, sub_value in value.items():
                if key not in target[block]:
                    target[block][key] = sub_value
                    notes.append(f"{name}.{block}.{key}")
                else:
                    kept.append(f"{name}.{block}.{key}")
    return merged, notes, kept


def fill_gaps(existing: dict, incoming: dict, managed_fields, overwrite: bool = False):
    """把 incoming 中 managed_fields 的值合并进 existing。

    返回 (合并结果, 变更说明, 因已存在而保留的说明)。未列在 managed_fields 里的字段
    （文案、审核状态、翻译、代谢来源等）一律不参与合并。
    """
    merged = dict(existing)
    changed, kept = [], []
    for field, value in incoming.items():
        if field not in managed_fields:
            continue
        if field == "roas":
            new_roas, notes, skipped = fill_roas(existing.get("roas") or [], value or [], overwrite)
            if notes:
                merged["roas"] = new_roas
                changed.extend(f"roas[{note}]" for note in notes)
            kept.extend(f"roas[{sub}]" for sub in skipped)
            continue
        if field in existing and not overwrite:
            kept.append(field)
            continue
        if existing.get(field) == value:
            continue
        merged[field] = value
        changed.append(field)
    return merged, changed, kept


# --------------------------------------------------------------------------
# 目录扩充台账（docs/substance-catalog-expansion.json）
# --------------------------------------------------------------------------
#
# 多个来源工具共用同一份台账，结构（与既有文件一致）：
#   checkedOn            本轮核对日期
#   scope                本轮范围说明
#   sourceSnapshots      [{source, url, version?, sha256?, hashNote?, query?}]
#   added                [{name, sources: [{source, key?, url?}]}]
#   excluded             [{source, key, name?, reason}]
#   resolved             [{source, key, name}]
#   normalizationNotes   [{source, key, name, note}]

LEDGER_LIST_KEYS = ("sourceSnapshots", "added", "excluded", "resolved", "normalizationNotes")

DEFAULT_LEDGER = Path("docs/substance-catalog-expansion.json")


def load_ledger(path: Path) -> dict:
    """读台账；不存在时返回空骨架。"""
    path = Path(path)
    if not path.exists():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        die(f"台账 '{path}' 的根元素不是对象。")
    return data


def merge_ledger(path: Path, *, source: str, snapshot: dict | None = None,
                 added=(), excluded=(), resolved=(), notes=()) -> dict:
    """把本轮结果并入台账，按 (source, key/name) 幂等去重后排序写回。

    重复执行同一个来源不会产生重复条目；`added` 会合并同一个物质的多来源记录。
    """
    import datetime

    path = Path(path)
    ledger = load_ledger(path)
    for key in LEDGER_LIST_KEYS:
        if not isinstance(ledger.get(key), list):
            ledger[key] = []
    ledger["checkedOn"] = datetime.date.today().isoformat()

    if snapshot:
        ledger["sourceSnapshots"] = [
            item for item in ledger["sourceSnapshots"] if item.get("source") != source
        ]
        ledger["sourceSnapshots"].append(snapshot)

    for item in added:
        name = item.get("name")
        found = next((a for a in ledger["added"] if a.get("name") == name), None)
        if found is None:
            ledger["added"].append({"name": name, "sources": list(item.get("sources") or [])})
            continue
        known = {(s.get("source"), s.get("key")) for s in found.get("sources") or []}
        for entry in item.get("sources") or []:
            if (entry.get("source"), entry.get("key")) not in known:
                found.setdefault("sources", []).append(entry)

    for key, items in (("excluded", excluded), ("resolved", resolved)):
        for item in items:
            found = next(
                (existing for existing in ledger[key]
                 if existing.get("source") == item.get("source") and existing.get("key") == item.get("key")),
                None,
            )
            if found is None:
                ledger[key].append(item)
            elif key == "resolved" and found.get("name") != item.get("name"):
                # 「来源键 → 规范名」要反映最新一轮的对照（改名/人工对照表会改结果）
                found["name"] = item.get("name")

    for item in notes:
        if not any(
            existing.get("source") == item.get("source")
            and existing.get("key") == item.get("key")
            and existing.get("note") == item.get("note")
            for existing in ledger["normalizationNotes"]
        ):
            ledger["normalizationNotes"].append(item)

    ledger["added"].sort(key=lambda item: (item.get("name") or "").lower())
    ledger["excluded"].sort(key=lambda item: (item.get("source") or "", item.get("key") or ""))
    ledger["resolved"].sort(key=lambda item: (item.get("source") or "", item.get("key") or ""))
    ledger["normalizationNotes"].sort(
        key=lambda item: (item.get("source") or "", item.get("key") or "")
    )
    ledger["sourceSnapshots"].sort(key=lambda item: item.get("source") or "")

    write_json(path, ledger)
    return ledger
