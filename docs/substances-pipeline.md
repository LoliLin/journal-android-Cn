# Substances 数据流水线（工具说明）

本文件说明 `docs/scripts/substances_pipeline.py` 的用法。它把原先 0~6 七个分步脚本合并为
一个入口，数据格式与合并规则见 [`substances-translation-protocol.md`](substances-translation-protocol.md)。

想知道从哪开始，直接跑：

```bash
python docs/scripts/substances_pipeline.py guide
```

## 前置条件

- Python 3（脚本只用标准库；`review` 需要 tkinter，通常随 Python 一起安装）
- `translate` 子命令额外需要 `pip install requests`、网络，以及一个 DeepSeek API Key
- 命令都在**仓库根目录**执行；数据目录默认自动探测 `app/src/main/assets/substances`
  （找不到时退回当前目录，兼容“先 cd 进 substances 再跑”的旧习惯），也可用 `--assets-dir` 指定

## 目录与文件约定

```
app/src/main/assets/substances/
├── root/                 # 基础层：结构字段 + 英文文本（合并时的默认来源）
│   ├── _categories.json
│   └── Armodafinil.json
├── zh_cn/                # 覆盖层：只放需要翻译的文本字段
├── zh_cn_replaced/       # apply 的默认输出（校对通过后再替换 zh_cn/）
└── ...

docs/scripts/_work/       # 中间产物（常量表），已 gitignore
├── zh_cn_constants.json
└── zh_cn_constants_translated.json
```

## 子命令与旧脚本对照

| 子命令 | 作用 | 原脚本 |
|---|---|---|
| `split` | 拆分上游 `Substances.json` → `root/` | `0_spiltSubstanceJson.py` |
| `scaffold` | 由 `root/` 生成语言覆盖层骨架 | `1_copySubstances.py` |
| `constants` | 收集语言目录下所有待翻译字符串 | `2_extraCommonConstants.py` |
| `translate` | 调用 DeepSeek 翻译常量表 | `3_translator.py` |
| `apply` | 把译文回填进语言目录 | `4_replaceCommonConstants.py` |
| `review` | 三语并排人工校对 GUI | `5_translateFixViewer.py` |
| `fix-tolerances` | 修正 `crossTolerances` 历史变体 | `6.fixTolencesTypes.py` |
| `guide` | 打印完整流程 | — |

## 完整流程

### 1. 拆分上游数据

`split` 读入含 `categories` 与 `substances` 两个字段的导出文件，输出 `_categories.json`
和每个物质一个文件（文件名取自 `name`，非法字符替换为下划线）。

```bash
python docs/scripts/substances_pipeline.py split Substances.json
# 默认输出到 app/src/main/assets/substances/root/，可用 --out 改
```

### 2. 生成语言覆盖层骨架

从 `root/` 抽取需要翻译的文本字段，加上 `localizedName`（默认等于 `name`，物质名本身不翻译），
写到 `<lang>/`。默认字段见脚本里的 `DEFAULT_TEXT_FIELDS`，可用 `--fields` 覆盖：

```bash
python docs/scripts/substances_pipeline.py scaffold zh_cn
python docs/scripts/substances_pipeline.py scaffold zh_cn --fields ""     # 只生成 localizedName
```

### 3. 收集待翻译字符串

生成 `{原文: 原文}` 形式的常量表，供下一步翻译：

```bash
python docs/scripts/substances_pipeline.py constants zh_cn
# 输出 docs/scripts/_work/zh_cn_constants.json
```

> 注意：常量表是**整个语言目录**里所有字符串值的集合。要让 URL、单位等不被翻译，
> 在第 4 步加 `--skip-pattern`（见下）。

### 4. 翻译

```bash
export DEEPSEEK_API_KEY=sk-...      # Windows: set DEEPSEEK_API_KEY=sk-...
python docs/scripts/substances_pipeline.py translate \
    docs/scripts/_work/zh_cn_constants.json --target-lang 简体中文
```

常用参数：

| 参数 | 用途 |
|---|---|
| `--api-key` | 直接传 Key（不推荐，会进 shell 历史；默认读 `DEEPSEEK_API_KEY`） |
| `--api-key-env` | 换一个环境变量名 |
| `--target-lang` | 目标语言，如 `简体中文` / `繁體中文` / `日本語`（默认 `简体中文`） |
| `--dry-run` | 只列出将翻译的条目，不调 API、不写文件 |
| `--limit N` | 只处理前 N 条，用于试跑 |
| `--skip-pattern REGEX` | 命中则原样保留，可重复；例如 `--skip-pattern '^https?://'` 跳过 URL |
| `--resume` | 接着已有输出继续，跳过已翻译条目（中断后重跑用） |
| `--delay` | 请求间隔秒数（默认 0.1） |
| `--model` / `--output` | 模型与输出路径（输出默认 `<input>_translated.json`） |

翻译失败的条目会保留 `[翻译失败] 原文` 前缀，并在结尾汇总数量——补齐的方式是
`--resume` 重跑，或手工编辑常量表。

### 5. 回填译文

默认**不覆盖**原语言目录，而是写到 `<lang>_replaced/`，先看影响面再决定：

```bash
python docs/scripts/substances_pipeline.py apply zh_cn \
    --constants docs/scripts/_work/zh_cn_constants_translated.json --dry-run
# 确认无误后去掉 --dry-run
```

| 参数 | 用途 |
|---|---|
| `--constants` | 映射文件（默认 `<work-dir>/<lang>_constants.json`） |
| `--output` | 输出目录（默认 `<assets>/<lang>_replaced`） |
| `--in-place` | 直接覆盖 `<lang>/`（不可恢复，确认无误再用） |
| `--dry-run` | 只报告会改动哪些文件、多少处，零副作用 |
| `--strict` | 映射里还有 `[翻译失败]` 条目时直接报错退出 |

替换只作用于**字符串值，不动键名**；数组、对象递归处理。

### 6. 人工校对

三语并排编辑器，按同名文件逐个对照修改，`保存全部三个文件` 会同时覆盖三个目录：

```bash
python docs/scripts/substances_pipeline.py review
# 默认打开 zh_cn / en_us / zh_tw，也可显式传三个目录
```

### 7. 收尾修正（可选，可重复执行）

把 `crossTolerances` 的历史变体（`psychedelics`、`Stimulants`、
`dissociative|dissociatives` 等）统一成单数标准名并去重：

```bash
python docs/scripts/substances_pipeline.py fix-tolerances --dry-run
python docs/scripts/substances_pipeline.py fix-tolerances
# 默认处理 en_us zh_cn zh_tw root，可显式指定目录
```

## 与旧脚本的差异

行为语义保持不变，以下是要注意的变化：

1. **一个入口**：旧脚本按 0~6 命名、各自解析 `sys.argv` / `input()`；现在统一为子命令，
   `-h` 可查每个步骤的参数，`guide` 给出完整顺序。
2. **中间文件位置**：常量表默认落在 `docs/scripts/_work/`（旧版落在当前目录），已加入
   `.gitignore`，不会再混进 assets。
3. **`split` 自举**：`--assets-dir` 指向的目录不存在时会提示并按需创建（其余子命令仍要求目录存在）。
4. **`translate`** 新增环境变量取 Key、`--dry-run`、`--limit`、`--skip-pattern`、`--resume`；
   默认行为（全量翻译、失败标记、`--delay 0.1`）与旧版一致。
5. **`apply`** 新增 `--dry-run` 与 `--strict`；默认输出目录与 `--in-place` 语义与旧版一致，
   且 `--dry-run` 不会创建/清空任何目录。
6. **`fix-tolerances`** 不再在脚本被 import 时自动执行（旧 `6.fixTolencesTypes.py` 一 import 就跑
   四个目录），现在只在显式调用子命令时执行。

## 排错

| 现象 | 处理 |
|---|---|
| `错误：--assets-dir '…' 不存在或不是目录。` | 确认路径，或省略该参数让脚本自动探测 |
| 翻译结果里大量 `[翻译失败]` | 检查 Key/网络/额度；用 `translate --resume` 重跑失败条目 |
| 不想让 URL、`mg` 等单位被翻译 | `--skip-pattern '^https?://' --skip-pattern '^\d+(\.\d+)? ?(mg\|g\|ml)$'` |
| `review` 报错说没有 tkinter | 安装带 tk 的 Python（Windows 官方安装包默认自带） |
| `apply` 之后发现译错了 | 不要用 `--in-place`；重新 `apply` 即可覆盖 `<lang>_replaced/` |
| assets 里出现了 `zh_cn_replaced/` 之类的目录 | 那是 `apply` 的输出目录，校对合并后自行删除；它不该提交 |
