#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Substances 多语言数据流水线（单文件版）。

本脚本把原先 docs/scripts/ 下 0~6 七个分步脚本合并为一个带子命令的工具，
各子命令与旧脚本一一对应：

    split            拆分 Substances.json -> root/          (原 0_spiltSubstanceJson.py)
    scaffold         生成语言覆盖层骨架 -> <lang>/           (原 1_copySubstances.py)
    constants        收集待翻译文案 -> <lang>_constants.json (原 2_extraCommonConstants.py)
    translate        调用 DeepSeek 翻译常量表                (原 3_translator.py)
    apply            把译文回填进 <lang>/                    (原 4_replaceCommonConstants.py)
    review           三语并排人工校对 GUI                    (原 5_translateFixViewer.py)
    fix-tolerances   批量修正 crossTolerances 历史变体       (原 6.fixTolencesTypes.py)
    guide            打印完整流程（不知道该干什么时先看这个）

除 `translate` 需要 requests（外加网络与 API Key）外，只依赖标准库。

数据格式与合并规则：docs/substances-translation-protocol.md
完整操作流程与排错：docs/substances-pipeline.md

从 PsychonautWiki 取数是独立工具：docs/scripts/fetch_psychonautwiki.py
（字段映射与坑见 docs/substances-pw-extraction.md）
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from pathlib import Path

from _common import (
    CROSS_TOLERANCE_FIXES,
    DEFAULT_WORK_DIR,
    REPO_ASSETS_HINT,
    die,
    read_json,
    resolve_assets_dir,
    resolve_work_dir,
    sanitize_filename,
    write_json,
)

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

#: scaffold 默认抽取的文本字段（root -> <lang> 覆盖层）
DEFAULT_TEXT_FIELDS = (
    "tolerance",
    "addictionPotential",
    "toxicities",
    "summary",
    "effectsSummary",
    "dosageRemark",
    "generalRisks",
    "longtermRisks",
    "saferUse",
)

#: fix-tolerances 默认处理的目录
DEFAULT_TOLERANCE_DIRS = ("en_us", "zh_cn", "zh_tw", "root")

#: review 默认并排打开的目录
DEFAULT_REVIEW_DIRS = ("zh_cn", "en_us", "zh_tw")

#: translate 相关
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0
DEFAULT_REQUEST_DELAY = 0.1
TRANSLATION_FAILURE_MARKER = "[翻译失败]"

GUIDE_TEXT = """\
Substances 多语言数据流水线 —— 推荐顺序

  0) 准备：确认 Python 3，`translate` 还需要 `pip install requests`
     全部命令都在仓库根目录执行；默认操作 app/src/main/assets/substances
     可用 --assets-dir 指定别的数据目录，用 -h 查看每个子命令的参数

  1) 拆分上游 Substances.json（含 categories + substances 两个字段）
       python docs/scripts/substances_pipeline.py split Substances.json

  2) 为新语言生成覆盖层骨架（只抽需要翻译的文本字段 + localizedName）
       python docs/scripts/substances_pipeline.py scaffold zh_cn

  3) 收集该语言目录下所有待翻译字符串
       python docs/scripts/substances_pipeline.py constants zh_cn

  4) 翻译（需要 DeepSeek API Key；可用环境变量避免密钥进 shell 历史）
       export DEEPSEEK_API_KEY=sk-...        # Windows: set DEEPSEEK_API_KEY=sk-...
       python docs/scripts/substances_pipeline.py translate \\
           docs/scripts/_work/zh_cn_constants.json --target-lang 简体中文

  5) 回填译文（默认输出到 <lang>_replaced/，先 --dry-run 看影响面）
       python docs/scripts/substances_pipeline.py apply zh_cn \\
           --constants docs/scripts/_work/zh_cn_constants_translated.json --dry-run
       # 确认无误后去掉 --dry-run；确认满意再考虑 --in-place

  6) 人工校对：三语并排编辑器，逐文件对比修改
       python docs/scripts/substances_pipeline.py review

  7) 收尾（一次性历史数据修正，可重复执行，无变化时不会写文件）
       python docs/scripts/substances_pipeline.py fix-tolerances

  相关工具（独立脚本，不在此流水线内）
   * 从 PsychonautWiki 补全结构化字段（剂量/时长/耐受/相互作用/别名）：
       python docs/scripts/fetch_psychonautwiki.py --dry-run --verbose
     字段映射与坑见 docs/substances-pw-extraction.md

  常见问题
   * 翻译结果里出现 "[翻译失败] ..."：重跑 translate --resume，或手工补齐后再 apply
   * 想只翻译一部分：translate --limit 20 试跑；--skip-pattern 可跳过 URL/单位等
   * apply 之后发现有问题：不要用 --in-place，重新 apply 覆盖 <lang>_replaced/ 即可
   * 数据合并规则（对象深合并、数组整体覆盖）见 docs/substances-translation-protocol.md
"""


# --------------------------------------------------------------------------
# 公共工具（与数据来源无关的部分见 _common.py）
# --------------------------------------------------------------------------


def substance_files(directory: Path, recursive: bool = False):
    """列出语言目录下的 substance JSON（跳过 _categories.json），按文件名排序。"""
    if not directory.is_dir():
        die(f"目录 '{directory}' 不存在。")
    pattern = "**/*.json" if recursive else "*.json"
    return sorted(
        path
        for path in directory.glob(pattern)
        if path.name != "_categories.json"
    )


def collect_strings(obj, out: set) -> None:
    """递归收集 JSON 中所有字符串值（键名不算），用于生成常量表。"""
    if isinstance(obj, dict):
        for value in obj.values():
            collect_strings(value, out)
    elif isinstance(obj, list):
        for item in obj:
            collect_strings(item, out)
    elif isinstance(obj, str):
        out.add(obj)


def apply_mapping(obj, mapping: dict):
    """递归替换字符串值（键名不动），返回 (新对象, 实际替换次数)。"""
    if isinstance(obj, dict):
        replaced = 0
        new_dict = {}
        for key, value in obj.items():
            new_dict[key], count = apply_mapping(value, mapping)
            replaced += count
        return new_dict, replaced
    if isinstance(obj, list):
        replaced = 0
        new_list = []
        for item in obj:
            converted, count = apply_mapping(item, mapping)
            new_list.append(converted)
            replaced += count
        return new_list, replaced
    if isinstance(obj, str):
        translated = mapping.get(obj)
        if translated is not None and translated != obj:
            return translated, 1
        return obj, 0
    return obj, 0


def parse_fields(value: str) -> list[str]:
    """解析 --fields a,b,c 形式；空串表示不抽取文本字段。"""
    return [item.strip() for item in value.split(",") if item.strip()]


# --------------------------------------------------------------------------
# 1) split —— 拆分上游 Substances.json
# --------------------------------------------------------------------------


def cmd_split(args: argparse.Namespace) -> int:
    assets_dir = resolve_assets_dir(args.assets_dir, must_exist=False)
    output_dir = Path(args.out) if args.out else assets_dir / "root"
    data = read_json(Path(args.input))

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"输入：{args.input}")
    print(f"输出：{output_dir}")

    if "categories" in data:
        write_json(output_dir / "_categories.json", data["categories"])
        print(f"已输出 categories -> {output_dir / '_categories.json'}")
    else:
        print("警告：输入 JSON 中没有 'categories' 字段，跳过。")

    substances = data.get("substances")
    if not isinstance(substances, list):
        print("警告：输入 JSON 中没有 'substances' 数组，跳过。")
        return 0

    written = 0
    for index, obj in enumerate(substances):
        if not isinstance(obj, dict):
            print(f"警告：substances[{index}] 不是对象，跳过。")
            continue
        name = obj.get("name")
        if not name:
            print(f"警告：substances[{index}] 缺少 'name' 字段，跳过。")
            continue
        path = output_dir / f"{sanitize_filename(str(name))}.json"
        write_json(path, obj)
        written += 1
        if args.verbose:
            print(f"已输出 substance '{name}' -> {path}")

    print(f"\n完成：{written} 个 substance 文件 + 1 个 _categories.json")
    return 0


# --------------------------------------------------------------------------
# 2) scaffold —— 生成语言覆盖层骨架
# --------------------------------------------------------------------------


def cmd_scaffold(args: argparse.Namespace) -> int:
    assets_dir = resolve_assets_dir(args.assets_dir)
    source_dir = Path(args.source) if args.source else assets_dir / "root"
    target_dir = Path(args.target) if args.target else assets_dir / args.lang
    fields = parse_fields(args.fields) if args.fields is not None else list(DEFAULT_TEXT_FIELDS)

    if not source_dir.is_dir():
        die(f"基础层目录 '{source_dir}' 不存在；先用 split 生成 root/。")

    files = substance_files(source_dir)
    if not files:
        print(f"警告：'{source_dir}' 下没有可处理的 JSON（已排除 _categories.json）。")
        return 0

    print(f"基础层：{source_dir}")
    print(f"输出到：{target_dir}")
    print(f"抽取字段：{', '.join(fields) if fields else '(仅 localizedName)'}")

    written = 0
    for json_file in files:
        data = read_json(json_file)
        if not isinstance(data, dict):
            print(f"跳过 '{json_file.name}'：内容不是 JSON 对象。")
            continue

        extracted = {field: data[field] for field in fields if field in data}
        if "name" in data:
            # 覆盖层不翻译物质名本身，localizedName 默认与 name 相同
            extracted["localizedName"] = data["name"]
        else:
            print(f"警告：'{json_file.name}' 没有 'name'，不添加 localizedName。")

        write_json(target_dir / json_file.name, extracted)
        written += 1
        if args.verbose:
            print(f"已生成: {target_dir / json_file.name}")

    print(f"\n完成：{written} 个文件 -> {target_dir}")
    return 0


# --------------------------------------------------------------------------
# 3) constants —— 收集待翻译字符串
# --------------------------------------------------------------------------


def cmd_constants(args: argparse.Namespace) -> int:
    assets_dir = resolve_assets_dir(args.assets_dir)
    source_dir = Path(args.source) if args.source else assets_dir / args.lang
    work_dir = resolve_work_dir(args.work_dir)
    output_path = Path(args.out) if args.out else work_dir / f"{args.lang}_constants.json"

    files = substance_files(source_dir, recursive=True)
    if not files:
        print(f"警告：'{source_dir}' 下没有 JSON 文件。")
        return 0

    strings: set[str] = set()
    for json_file in files:
        collect_strings(read_json(json_file), strings)
        if args.verbose:
            print(f"已处理：{json_file}")

    # 键与值相同：翻译后的表本身就是“原文 -> 译文”的映射
    write_json(output_path, {text: text for text in strings})

    print(f"\n完成：{len(files)} 个文件，{len(strings)} 条唯一字符串")
    print(f"输出：{output_path}")
    print("下一步：用 translate 子命令翻译该常量表。")
    return 0


# --------------------------------------------------------------------------
# 4) translate —— 调用 DeepSeek 翻译常量表
# --------------------------------------------------------------------------


def translate_text(text: str, api_key: str, target_lang: str, model: str) -> str:
    """翻译单个字符串；失败返回 "[翻译失败] 原文"。"""
    if not text or not text.strip():
        return text

    import requests  # 延迟导入：其它子命令不需要 requests

    system_prompt = (
        f"你是一个专业的翻译助手。请将用户提供的文本逐字逐句翻译成{target_lang}。"
        "不要添加任何额外的解释、警告、评论或拒绝翻译。"
        "如果文本包含专业术语（包括药物名称、化学物质等），请采用公认的译名。"
        "只输出翻译结果，不要输出任何其他内容。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请将以下文本翻译成{target_lang}：\n{text}"},
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(DEFAULT_MAX_RETRIES):
        try:
            response = requests.post(
                DEEPSEEK_ENDPOINT, json=payload, headers=headers, timeout=60
            )
            if response.status_code == 200:
                translated = response.json()["choices"][0]["message"]["content"].strip()
                # 模型偶尔会回复“抱歉，我无法翻译…”，重试几次再放弃
                refusal = any(
                    marker in translated.lower() for marker in ("sorry", "无法翻译", "拒绝")
                )
                if refusal and attempt < DEFAULT_MAX_RETRIES - 1:
                    time.sleep(DEFAULT_RETRY_DELAY)
                    continue
                return translated
            print(f"API 错误 {response.status_code}: {response.text}")
            if attempt < DEFAULT_MAX_RETRIES - 1:
                time.sleep(DEFAULT_RETRY_DELAY)
            else:
                return f"{TRANSLATION_FAILURE_MARKER} {text}"
        except Exception as exc:  # 网络抖动等，重试后再放弃
            print(f"请求异常：{exc}")
            if attempt < DEFAULT_MAX_RETRIES - 1:
                time.sleep(DEFAULT_RETRY_DELAY)
            else:
                return f"{TRANSLATION_FAILURE_MARKER} {text}"
    return f"{TRANSLATION_FAILURE_MARKER} {text}"


def cmd_translate(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    data = read_json(input_path)
    if not isinstance(data, dict):
        die(f"'{input_path}' 的根元素不是对象；它应该是 constants 生成的常量表。")

    output_path = (
        Path(args.output)
        if args.output
        else input_path.parent / f"{input_path.stem}_translated{input_path.suffix}"
    )

    api_key = args.api_key
    if not api_key and not args.dry_run:
        import os

        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            die(
                "缺少 API Key：用 --api-key 传入，或设置环境变量 "
                f"{args.api_key_env}（推荐，避免密钥写进 shell 历史）。"
            )

    skip_patterns = [re.compile(pattern) for pattern in args.skip_pattern]

    def should_skip(text: str) -> bool:
        return any(pattern.search(text) for pattern in skip_patterns)

    translated_data = {}
    if args.resume and output_path.exists():
        existing = read_json(output_path)
        if isinstance(existing, dict):
            translated_data = existing
            print(f"续跑：已有 {len(translated_data)} 条译文，将跳过这些条目。")

    pending = [
        (key, value)
        for key, value in data.items()
        if key not in translated_data
    ]
    if args.limit:
        pending = pending[: args.limit]

    skipped = sum(1 for key, _ in pending if should_skip(key))
    print(f"输入：{input_path}（共 {len(data)} 条，本次处理 {len(pending)} 条，跳过 {skipped} 条）")
    print(f"目标语言：{args.target_lang}，模型：{args.model}")

    if args.dry_run:
        for index, (key, _) in enumerate(pending, 1):
            action = "跳过" if should_skip(key) else "翻译"
            print(f"[{index}/{len(pending)}] {action}: {key[:60]}")
        print(f"\n--dry-run：没有调用 API，也没有写文件。输出本应为 {output_path}")
        return 0

    failures = 0
    for index, (key, value) in enumerate(pending, 1):
        if should_skip(key):
            translated_data[key] = key  # 原样保留（URL、单位等）
            continue
        print(f"[{index}/{len(pending)}] 正在翻译: {value[:50]}...")
        translated = translate_text(value, api_key, args.target_lang, args.model)
        if translated.startswith(TRANSLATION_FAILURE_MARKER):
            failures += 1
        translated_data[key] = translated
        print(f"> {translated}")
        if index < len(pending):
            time.sleep(args.delay)

    write_json(output_path, translated_data)
    print(f"\n完成：{len(translated_data)} 条，失败 {failures} 条")
    print(f"输出：{output_path}")
    if failures:
        print("提示：失败条目保留了 '[翻译失败]' 前缀，可稍后 translate --resume 重试。")
    print("下一步：用 apply 子命令回填（先加 --dry-run 看看影响面）。")
    return 0


# --------------------------------------------------------------------------
# 5) apply —— 把译文回填进语言目录
# --------------------------------------------------------------------------


def cmd_apply(args: argparse.Namespace) -> int:
    assets_dir = resolve_assets_dir(args.assets_dir)
    source_dir = Path(args.source) if args.source else assets_dir / args.lang
    work_dir = resolve_work_dir(args.work_dir)
    constants_path = (
        Path(args.constants) if args.constants else work_dir / f"{args.lang}_constants.json"
    )

    mapping = read_json(constants_path)
    if not isinstance(mapping, dict):
        die(f"'{constants_path}' 的内容不是 JSON 对象。")

    failures = [
        key for key, value in mapping.items()
        if isinstance(value, str) and value.startswith(TRANSLATION_FAILURE_MARKER)
    ]
    print(f"映射：{constants_path}（{len(mapping)} 条）")
    if failures:
        print(f"警告：其中 {len(failures)} 条仍未翻译成功（形如 '[翻译失败] …'）。")
        for key in failures[:5]:
            print(f"  - {key[:60]}")
        if len(failures) > 5:
            print(f"  ... 其余 {len(failures) - 5} 条省略")
        if args.strict:
            die("存在未翻译条目（--strict）。请先补齐或重跑 translate --resume。")
        print("继续回填会把 '[翻译失败]' 写进数据，建议先补齐；确认可接受请忽略本提示。")

    files = substance_files(source_dir, recursive=True)
    if not files:
        print(f"警告：'{source_dir}' 下没有 JSON 文件。")
        return 0

    if args.in_place:
        output_dir = source_dir
        if args.dry_run:
            print(f"--dry-run：将原地覆盖 '{source_dir}'（未修改）。")
        else:
            print(f"警告：--in-place 将原地覆盖 '{source_dir}'（不可恢复）。")
    else:
        output_dir = Path(args.output) if args.output else assets_dir / f"{args.lang}_replaced"
        if args.dry_run:
            print(f"--dry-run：输出本应为 {output_dir}（未创建、未修改）。")
        else:
            if output_dir.exists():
                print(f"清空已存在的输出目录：{output_dir}")
                shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"输出目录：{output_dir}")

    changed_files = 0
    replaced_values = 0
    for json_file in files:
        data = read_json(json_file)
        new_data, count = apply_mapping(data, mapping)
        replaced_values += count
        # 保持相对结构（语言目录下若有子目录，一并还原）
        relative = json_file.relative_to(source_dir)
        out_file = json_file if args.in_place else output_dir / relative
        if args.dry_run:
            if count:
                changed_files += 1
                print(f"将修改：{relative}（{count} 处）")
            continue
        write_json(out_file, new_data)
        if count:
            changed_files += 1
        if args.verbose:
            print(f"已处理：{json_file} -> {out_file}")

    if args.dry_run:
        print(f"\n--dry-run：{changed_files} 个文件会被修改，共 {replaced_values} 处替换；没有写任何文件。")
    else:
        print(f"\n完成：{len(files)} 个文件，{changed_files} 个有改动，共替换 {replaced_values} 处")
        print(f"输出：{output_dir}")
        if not args.in_place:
            print("校对无误后可整体替换语言目录，或改用 --in-place 重跑。")
    return 0


# --------------------------------------------------------------------------
# 6) review —— 三语并排人工校对
# --------------------------------------------------------------------------


def cmd_review(args: argparse.Namespace) -> int:
    assets_dir = resolve_assets_dir(args.assets_dir)
    directories = [Path(d) for d in args.directories] if args.directories else [
        assets_dir / name for name in DEFAULT_REVIEW_DIRS
    ]
    if len(directories) != 3:
        die("review 需要正好三个目录（例如 zh_cn en_us zh_tw）。")

    try:
        import tkinter as tk
    except ImportError:
        die("当前 Python 没有 tkinter，无法启动图形界面；请安装带 tk 的 Python。")

    missing = [str(d) for d in directories if not d.is_dir()]
    if missing:
        print(f"警告：以下目录不存在，界面里可以手动改选：{', '.join(missing)}")

    app = LocalizationEditor(tk.Tk(), directories)
    app.run()
    return 0


class LocalizationEditor:
    """三个语言目录下同名 JSON 的并排编辑器（原 5_translateFixViewer.py）。"""

    def __init__(self, root, directories):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.root.title("JSON 本地化对照编辑器")
        self.root.geometry("1200x700")

        self.dir_vars = [tk.StringVar(value=str(path)) for path in directories]
        self.common_files: list[str] = []
        self.current_index = -1

        dir_frame = ttk.LabelFrame(self.root, text="选择三个本地化目录", padding=10)
        dir_frame.pack(fill=tk.X, padx=10, pady=5)
        labels = ["目录 1 (如 zh_cn):", "目录 2 (如 en_us):", "目录 3 (如 zh_tw):"]
        for i in range(3):
            row = ttk.Frame(dir_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=labels[i], width=18).pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=self.dir_vars[i]).pack(
                side=tk.LEFT, fill=tk.X, expand=True
            )
            ttk.Button(row, text="浏览…", command=lambda idx=i: self.select_directory(idx)).pack(
                side=tk.LEFT, padx=5
            )

        nav_frame = ttk.Frame(self.root)
        nav_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(nav_frame, text="← 上一个", command=self.prev_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(nav_frame, text="下一个 →", command=self.next_file).pack(side=tk.LEFT, padx=5)
        self.file_label = ttk.Label(
            nav_frame, text="当前文件: ", font=("TkDefaultFont", 10, "bold")
        )
        self.file_label.pack(side=tk.LEFT, padx=20)
        ttk.Button(nav_frame, text="保存全部三个文件", command=self.save_all).pack(
            side=tk.RIGHT, padx=5
        )

        edit_frame = ttk.Frame(self.root)
        edit_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.text_widgets = []
        self.edit_labels = []
        for i in range(3):
            column = ttk.Frame(edit_frame)
            column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            label = ttk.Label(column, text=f"目录 {i + 1}")
            label.pack(anchor=tk.W)
            scroll = ttk.Scrollbar(column)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)
            text = tk.Text(column, wrap=tk.WORD, yscrollcommand=scroll.set)
            text.pack(fill=tk.BOTH, expand=True)
            scroll.config(command=text.yview)
            self.edit_labels.append(label)
            self.text_widgets.append(text)

        self.status = ttk.Label(self.root, text="请先选择三个目录", relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

        for var in self.dir_vars:
            var.trace_add("write", lambda *_: self.refresh_file_list())

    def run(self):
        self.refresh_file_list()
        self.root.mainloop()

    def select_directory(self, idx):
        from tkinter import filedialog

        path = filedialog.askdirectory(title=f"选择目录 {idx + 1}")
        if path:
            self.dir_vars[idx].set(path)

    def refresh_file_list(self):
        import os

        paths = [var.get().strip() for var in self.dir_vars]
        if not all(paths):
            return
        try:
            sets = [
                {f for f in os.listdir(path) if f.lower().endswith(".json")}
                for path in paths
            ]
            common = sorted(sets[0] & sets[1] & sets[2])
            self.common_files = common
            self.current_index = 0 if common else -1
            if common:
                self.load_current_file()
                self.status.config(text=f"已加载 {len(common)} 个同名 JSON 文件")
            else:
                for text in self.text_widgets:
                    text.delete("1.0", self.tk.END)
                self.file_label.config(text="当前文件: 无")
                self.status.config(text="三个目录下没有同名的 JSON 文件")
        except Exception as exc:
            from tkinter import messagebox

            messagebox.showerror("错误", f"读取目录失败:\n{exc}")

    def load_current_file(self):
        import os

        if self.current_index < 0 or not self.common_files:
            return
        filename = self.common_files[self.current_index]
        self.file_label.config(text=f"当前文件: {filename}")

        for i, var in enumerate(self.dir_vars):
            path = os.path.join(var.get(), filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = f.read()
                try:
                    pretty = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
                except json.JSONDecodeError:
                    pretty = raw  # 不是合法 JSON 时按原文显示，方便对照
            except Exception as exc:
                pretty = f"[读取失败] {exc}"
            widget = self.text_widgets[i]
            widget.delete("1.0", self.tk.END)
            widget.insert("1.0", pretty)

        for i, var in enumerate(self.dir_vars):
            self.edit_labels[i].config(text=os.path.basename(var.get()) or f"目录{i + 1}")
        self.status.config(text=f"正在编辑: {filename}")

    def save_all(self):
        import os
        from tkinter import messagebox

        if self.current_index < 0 or not self.common_files:
            messagebox.showwarning("提示", "没有打开的文件可供保存")
            return
        filename = self.common_files[self.current_index]
        paths = [os.path.join(var.get(), filename) for var in self.dir_vars]
        if not messagebox.askyesno(
            "确认保存", "确定要覆盖保存以下三个文件吗？\n\n" + "\n".join(paths)
        ):
            return

        success = True
        for i, path in enumerate(paths):
            content = self.text_widgets[i].get("1.0", "end-1c")  # 去掉末尾自动换行
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as exc:
                messagebox.showerror("保存失败", f"无法写入文件:\n{path}\n错误: {exc}")
                success = False
        self.status.config(text=f"已保存: {filename}" if success else "保存过程出现错误")

    def prev_file(self):
        if not self.common_files:
            return
        self.current_index = (self.current_index - 1) % len(self.common_files)
        self.load_current_file()

    def next_file(self):
        if not self.common_files:
            return
        self.current_index = (self.current_index + 1) % len(self.common_files)
        self.load_current_file()


# --------------------------------------------------------------------------
# 7) fix-tolerances —— 修正 crossTolerances 历史变体
# --------------------------------------------------------------------------


def fix_cross_tolerances(file_path: Path, dry_run: bool = False):
    """修正单个文件中的 crossTolerances；返回改动条数（0 表示未改动）。"""
    data = read_json(file_path)
    changes = 0

    def process_entry(entry) -> None:
        nonlocal changes
        if not isinstance(entry, dict) or "crossTolerances" not in entry:
            return
        old = entry["crossTolerances"]
        if not isinstance(old, list):
            return
        deduped = []
        seen = set()
        for item in old:
            text = str(item) if not isinstance(item, str) else item
            replaced = CROSS_TOLERANCE_FIXES.get(text, text)
            if replaced not in seen:
                seen.add(replaced)
                deduped.append(replaced)
        if deduped != old:
            entry["crossTolerances"] = deduped
            changes += 1

    if isinstance(data, dict):
        process_entry(data)
    elif isinstance(data, list):
        for entry in data:
            process_entry(entry)

    if changes and not dry_run:
        write_json(file_path, data)
    return changes


def cmd_fix_tolerances(args: argparse.Namespace) -> int:
    assets_dir = resolve_assets_dir(args.assets_dir)
    directories = args.directories or list(DEFAULT_TOLERANCE_DIRS)
    total = 0
    for name in directories:
        directory = Path(name) if "/" in name or "\\" in name else assets_dir / name
        if not directory.is_dir():
            print(f"跳过不存在的目录：{directory}")
            continue
        for json_file in sorted(directory.glob("*.json")):
            changes = fix_cross_tolerances(json_file, dry_run=args.dry_run)
            if changes:
                total += changes
                print(f"{'将修复' if args.dry_run else '已修复'}: {json_file}")
    print(f"\n完成：{total} 个条目{'需要' if args.dry_run else '已'}修正")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="substances_pipeline.py",
        description="Substances 多语言数据流水线（0~6 分步脚本的合并版）。",
        epilog="不知道从哪开始：先跑 `substances_pipeline.py guide`。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<子命令>")

    def add_assets_dir(sub):
        sub.add_argument(
            "--assets-dir",
            help=f"assets/substances 目录（默认自动探测 {REPO_ASSETS_HINT}，否则用当前目录）",
        )

    def add_work_dir(sub):
        sub.add_argument(
            "--work-dir",
            help=f"中间产物目录（默认 {DEFAULT_WORK_DIR}）",
        )

    # split
    split = subparsers.add_parser(
        "split", help="拆分上游 Substances.json 到 root/", description="原 0_spiltSubstanceJson.py"
    )
    split.add_argument("input", help="上游导出的 Substances.json（含 categories 与 substances）")
    split.add_argument("--out", help="输出目录（默认 <assets>/root）")
    split.add_argument("--verbose", action="store_true", help="逐文件打印")
    add_assets_dir(split)
    split.set_defaults(func=cmd_split)

    # scaffold
    scaffold = subparsers.add_parser(
        "scaffold",
        help="由 root/ 生成语言覆盖层骨架",
        description="原 1_copySubstances.py：抽取文本字段 + localizedName 到 <lang>/",
    )
    scaffold.add_argument("lang", help="语言键，如 zh_cn / zh_tw / en_us")
    scaffold.add_argument("--source", help="基础层目录（默认 <assets>/root）")
    scaffold.add_argument("--target", help="输出目录（默认 <assets>/<lang>）")
    scaffold.add_argument(
        "--fields",
        help="逗号分隔的字段列表（默认：" + ",".join(DEFAULT_TEXT_FIELDS) + "；传空串只生成 localizedName）",
    )
    scaffold.add_argument("--verbose", action="store_true", help="逐文件打印")
    add_assets_dir(scaffold)
    scaffold.set_defaults(func=cmd_scaffold)

    # constants
    constants = subparsers.add_parser(
        "constants",
        help="收集语言目录下所有待翻译字符串",
        description="原 2_extraCommonConstants.py：生成 {原文: 原文} 常量表",
    )
    constants.add_argument("lang", help="语言键，如 zh_cn")
    constants.add_argument("--source", help="语言目录（默认 <assets>/<lang>）")
    constants.add_argument("--out", help="输出文件（默认 <work-dir>/<lang>_constants.json）")
    constants.add_argument("--verbose", action="store_true", help="逐文件打印")
    add_assets_dir(constants)
    add_work_dir(constants)
    constants.set_defaults(func=cmd_constants)

    # translate
    translate = subparsers.add_parser(
        "translate",
        help="用 DeepSeek 翻译常量表",
        description="原 3_translator.py；需要 requests、网络与 API Key",
    )
    translate.add_argument("input", help="constants 生成的常量表，如 zh_cn_constants.json")
    translate.add_argument("--api-key", help=f"DeepSeek API Key（默认读环境变量）")
    translate.add_argument(
        "--api-key-env", default=DEFAULT_API_KEY_ENV, help=f"API Key 环境变量名（默认 {DEFAULT_API_KEY_ENV}）"
    )
    translate.add_argument("--model", default=DEFAULT_MODEL, help=f"模型（默认 {DEFAULT_MODEL}）")
    translate.add_argument(
        "--target-lang", default="简体中文", help="目标语言（默认 简体中文）"
    )
    translate.add_argument("--output", help="输出文件（默认 <input>_translated.json）")
    translate.add_argument(
        "--delay", type=float, default=DEFAULT_REQUEST_DELAY, help="每次请求间隔秒数（默认 0.1）"
    )
    translate.add_argument("--limit", type=int, help="只处理前 N 条（试跑用）")
    translate.add_argument(
        "--skip-pattern",
        action="append",
        default=[],
        metavar="REGEX",
        help="匹配到的字符串原样保留不翻译，可重复；如 '^https?://' 跳过 URL",
    )
    translate.add_argument("--resume", action="store_true", help="接着已有输出继续，跳过已翻译条目")
    translate.add_argument("--dry-run", action="store_true", help="只列出将要翻译的条目，不调用 API")
    translate.set_defaults(func=cmd_translate)

    # apply
    apply = subparsers.add_parser(
        "apply",
        help="把译文回填进语言目录",
        description="原 4_replaceCommonConstants.py：默认输出 <lang>_replaced/，加 --in-place 才覆盖原目录",
    )
    apply.add_argument("lang", help="语言键，如 zh_cn")
    apply.add_argument("--source", help="语言目录（默认 <assets>/<lang>）")
    apply.add_argument("--constants", help="映射文件（默认 <work-dir>/<lang>_constants.json）")
    apply.add_argument("--output", help="输出目录（默认 <assets>/<lang>_replaced）")
    apply.add_argument("--in-place", action="store_true", help="原地覆盖语言目录（危险）")
    apply.add_argument("--dry-run", action="store_true", help="只报告会改动哪些文件")
    apply.add_argument("--strict", action="store_true", help="存在 '[翻译失败]' 条目时直接报错退出")
    apply.add_argument("--verbose", action="store_true", help="逐文件打印")
    add_assets_dir(apply)
    add_work_dir(apply)
    apply.set_defaults(func=cmd_apply)

    # review
    review = subparsers.add_parser(
        "review",
        help="三语并排人工校对 GUI",
        description="原 5_translateFixViewer.py",
    )
    review.add_argument(
        "directories", nargs="*", help=f"三个目录（默认 {', '.join(DEFAULT_REVIEW_DIRS)}）"
    )
    add_assets_dir(review)
    review.set_defaults(func=cmd_review)

    # fix-tolerances
    fix = subparsers.add_parser(
        "fix-tolerances",
        help="修正 crossTolerances 历史变体",
        description="原 6.fixTolencesTypes.py：把 psychedelics/stimulants 等统一成单数形式",
    )
    fix.add_argument(
        "directories", nargs="*", help=f"要处理的目录（默认 {', '.join(DEFAULT_TOLERANCE_DIRS)}）"
    )
    fix.add_argument("--dry-run", action="store_true", help="只报告不写文件")
    add_assets_dir(fix)
    fix.set_defaults(func=cmd_fix_tolerances)


    # guide
    guide = subparsers.add_parser("guide", help="打印完整流程", description="推荐先看这个")
    guide.set_defaults(func=lambda args: (print(GUIDE_TEXT) or 0))

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
