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
