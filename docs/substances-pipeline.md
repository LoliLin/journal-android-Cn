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
- 从外部来源（PsychonautWiki / ATC / TripSit / EUDA）抓取与补全结构化字段是**独立工具**：
  `fetch_psychonautwiki.py`、`fetch_atc.py`、`fetch_tripsit.py`、`fetch_euda.py`，
  见 [`substances-catalog-sources.md`](substances-catalog-sources.md)

## 目录与文件约定

```
app/src/main/assets/substances/
├── root/                 # 基础层：结构字段 + 英文文本（合并时的默认来源）
│   ├── _categories.json
│   └── Armodafinil.json
├── zh_cn/                # 覆盖层：只放需要翻译的文本字段
├── zh_cn_replaced/       # apply 的默认输出（校对通过后再替换 zh_cn/）
└── ...

docs/scripts/_work/       # 中间产物，已 gitignore
├── zh_cn_constants.json
├── zh_cn_constants_translated.json
└── pw-cache/             # fetch_psychonautwiki.py 的响应缓存
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
| `fix-interactions` | 规范化 `interactions` 的写法（分类键 / 规范物质名） | —（新功能） |
| `convert` | 语言之间本机转换（简繁等），不走 API | —（新功能） |
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
> 在第 5 步加 `--skip-pattern`（见下）。

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
| `--batch N` | 一次请求翻 N 条（默认 1；**建议 20**，1148 条从 1148 次请求降到约 58 次） |
| `--glossary FILE` | 术语表 `{原文: 译名}`，注入提示词保证译名一致（如 `docs/glossary/en_to_zh.json`） |
| `--skip-ascii` | 跳过纯 ASCII 且不含空格的字符串（物质名/缩写/单位/URL），避免把 `2C-B`、`mg` 翻坏 |
| `--dry-run` | 只列出将翻译的条目与预计请求数，不调 API、不写文件 |
| `--limit N` | 只处理前 N 条，用于试跑 |
| `--skip-pattern REGEX` | 命中则原样保留，可重复；例如 `--skip-pattern '^https?://'` 跳过 URL |
| `--resume` | 接着已有输出继续，跳过已翻译条目（中断后重跑用） |
| `--delay` | 请求间隔秒数（默认 0.1） |
| `--model` / `--output` | 模型与输出路径（输出默认 `<input>_translated.json`） |

批量模式的返回契约是"等长 JSON 字符串数组"；模型一旦返回长度不符或无法解析，会**自动退回逐条翻译**
（只是慢一点，不会丢条目）。翻译失败的条目保留 `[翻译失败] 原文` 前缀并在结尾汇总——补齐的方式是
`--resume` 重跑，或手工编辑常量表。

> **能转换就别翻译**：目标语言是 `zh_tw` 而 `zh_cn` 已有内容时，用下面的 `convert` 更快也更一致。

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

### 8. 规范化 interactions 的写法

`interactions`（`dangerous`/`unsafe`/`uncertain`）里的字符串必须能被应用匹配上。应用的
`InteractionChecker` 有两条规则：

```kotlin
isDirectMatch : extendedInteractions.contains(substanceName)                  // 物质名：精确相等
isClassMatch  : interactionName.contains(categoryKey, ignoreCase = true)      // 分类：包含即可
```

也就是说**物质名必须与 `root/<Name>.json` 的 `name` 完全一致**（大小写敏感），而分类只要"包含"分类键就行。
实测 2268 条里混着 100 种写法：`Stimulants`、`MAOIs`、`SSRIs`（复数分类）、`DXM`/`aMT`/`DPH`（简称）、
`alcohol`/`cocaine`（大小写不对）、`amphetamines`/`5-meo-xxt`（大小写不统一）等。

```bash
python docs/scripts/substances_pipeline.py fix-interactions --dry-run
python docs/scripts/substances_pipeline.py fix-interactions
```

规范化优先级（`fix-interactions`，可重复执行，无变化时不写文件）：

1. **目录里的物质名**：只修大小写，让它与 `root` 完全一致（`alcohol → Alcohol`、`cocaine → Cocaine`、
   `cannabis → Cannabis`）。**类目条目也算物质名**——目录里确实有 `Stimulants`、`Opioids`、
   `Benzodiazepines`、`Dissociatives`、`MAOI`、`Depressant`、`Psychedelic`、`Antipsychotic`、`Deliriant`
   这些条目，而且它们自己没有 `categories`，改动它们会丢掉精确匹配，所以保持条目名（这些名字本身就是规范写法）；
   **不合并**两个都存在的条目（`MXE`/`Methoxetamine`、`THC`/`Cannabis`、`N2O`/`Nitrous` 各留各的）；
2. **分类键**（`_categories.json`）及其复数写法：`SSRIs → ssri`（没有同名条目时用分类键）、
   `Depressants → Depressant`、`Psychedelics → Psychedelic`、`Antipsychotics → Antipsychotic`、
   `Deliriants → Deliriant`、`MAOIs → MAOI`（有同名条目时用条目名——应用对分类是
   `interactionName.contains(categoryKey, ignoreCase = true)`，大小写不敏感，所以 `MAOI` 照样命中 `maoi` 分类）；
3. **只被一个条目登记的别名**：`DXM → Dextromethorphan`、`DPH → Diphenhydramine`、`aMT → ΑMT`；
4. **其余只统一大小写**：同一折叠形式取出现最多的拼法（`amphetamines → Amphetamines`、
   `5-meo-xxt`/`5-MeO-xxt → 5-MeO-xxT`）。

**必须原样保留**（应用用代码展开，不能规范化）：`Substituted amphetamines`、`Serotonin releasers`、
`Tricyclic antidepressants`（最后一个在应用里被有意清空，避免被 `contains("depressant")` 误匹配）。

本轮结果（在完整目录上跑一遍）：

| 指标 | 之前 | 之后 |
|---|---|---|
| interactions 列表被规范化 | — | **317 个（188 个 root 文件）** |
| 不同写法 | 100 种 | **80 种**（折叠后重复 0 组） |
| 「完全匹配不到任何物质」的条目 | 312 条 | **160 条（−152）** |
| 命中组合（按出现次数加权，模拟应用的匹配规则） | 50 219 | **50 575（+356）** |

再跑一次输出 `0`，即一轮收敛、幂等。

**55 个写法有歧义**（被两个以上条目登记为别名，如 `nitrous oxide → {N2O, Nitrous}`、
`2ai → {2-AI, 2-Aminoindane}`），工具保持原样并记进报告——它们暴露的是**重复条目**问题，需要单独合并，
不在这个子命令的范围内。

**33 种写法无法归类**（目录里没有对应分类或物质），保持原样。它们要么是我们没收录的类别，
要么是"含分类词的组合写法"（后者靠 `contains` 依然生效）：

```
5-MeO-xxT              ALDH2 inhibitors       Amphetamines           Anticholinergics
Antihistamines         CNS depressants        CYP2C19-substrates     Cholinergics
Classical psychedelics (seizure risk)         Diuretics              Dopaminergic agonists
GHB/GBL                Grapefruit             Hepatotoxic drugs      Hormonal Birth Control
NBOMe                  NBOMes                 NSAIDs                 Other CNS depressants
Other NMDA antagonists Other anticholinergics Other antipsychotics   Other benzodiazepines
Other mood stabilizers Other seizure threshold lowering drugs        Other stimulants
Protease Inhibitors    Ritonavir              SNRIs                  nitrous oxide
other dissociatives    other substances that can increase the risk of psychosis or seizures
serotonergic drugs
```

### 9. 语言之间本机转换（convert，不走 API）

简繁之间是**字符级映射 + 少量用词差异**，机器翻译是浪费：`zh_cn` 已有内容时，`zh_tw` 直接转。

```bash
# 先看影响面（零副作用，不建目录）
python docs/scripts/substances_pipeline.py convert zh_cn zh_tw --dry-run
# 默认输出 <assets>/zh_tw_converted/，校对后再决定是否 --in-place
python docs/scripts/substances_pipeline.py convert zh_cn zh_tw \
    --glossary docs/glossary/zh_cn_to_zh_tw.json
```

| 参数 | 用途 |
|---|---|
| `from_lang` / `to_lang` | 语言键（如 `zh_cn` / `zh_tw`），决定 OpenCC preset 或 zhconv target |
| `--source` | 源目录或单个 JSON 文件（默认 `<assets>/<from_lang>`） |
| `--target` | 输出目录（默认 `<assets>/<to_lang>_converted`） |
| `--in-place` | 直接覆盖目标语言目录（不可恢复） |
| `--glossary FILE` | 术语表 `{原词: 替换词}`，**在字符转换之前**按源语言写法匹配（长词优先） |
| `--dry-run` / `--verbose` | 报告改动处数 / 逐文件打印 |

依赖：优先 OpenCC（`s2twp`/`tw2sp`，带台湾用词本地化），没有就退回 `zhconv`（逐字转换，用词较弱，
会打印提示）。两者都没有时报错并给出安装命令。实测 1148 条 `zh_cn` 常量繁化后 236 条（20%）不变，
其余本地瞬时完成。术语表种子在 `docs/glossary/`（`en_to_zh.json` 42 条、
`zh_cn_to_zh_tw.json` 32 条），需要人工审校后再用。

## 与旧脚本的差异

行为语义保持不变，以下是要注意的变化：

1. **一个入口**：旧脚本按 0~6 命名、各自解析 `sys.argv` / `input()`；现在统一为子命令，
   `-h` 可查每个步骤的参数，`guide` 给出完整顺序。
2. **中间文件位置**：常量表默认落在 `docs/scripts/_work/`（旧版落在当前目录），已加入
   `.gitignore`，不会再混进 assets。
3. **`split` 自举**：`--assets-dir` 指向的目录不存在时会提示并按需创建（其余子命令仍要求目录存在）。
4. **`translate`** 新增环境变量取 Key、`--dry-run`、`--limit`、`--skip-pattern`、`--resume`、
   `--batch`、`--glossary`、`--skip-ascii`；默认行为（逐条翻译、失败标记、`--delay 0.1`）与旧版一致
   ——不传 `--batch` 时就是原来的逐条请求。
5. **`apply`** 新增 `--dry-run` 与 `--strict`；默认输出目录与 `--in-place` 语义与旧版一致，
   且 `--dry-run` 不会创建/清空任何目录。
6. **`fix-tolerances`** 不再在脚本被 import 时自动执行（旧 `6.fixTolencesTypes.py` 一 import 就跑
   四个目录），现在只在显式调用子命令时执行。
7. **抓取工具独立**：从 PsychonautWiki / ATC / TripSit / EUDA / FreeODwiki 补全字段是另外五个脚本
   （`fetch_psychonautwiki.py`、`fetch_atc.py`、`fetch_tripsit.py`、`fetch_euda.py`、
   `fetch_freeodwiki.py`，见 [`substances-catalog-sources.md`](substances-catalog-sources.md)），
   各工具共用 `docs/scripts/_common.py` 里的路径/JSON/合并/台账辅助函数；目标是**一个来源一个脚本**。
8. **`convert` 是新子命令**（旧脚本没有）：简繁等语言间本机转换，替代"再翻一遍"的做法。

## 排错

| 现象 | 处理 |
|---|---|
| `错误：--assets-dir '…' 不存在或不是目录。` | 确认路径，或省略该参数让脚本自动探测 |
| 翻译结果里大量 `[翻译失败]` | 检查 Key/网络/额度；用 `translate --resume` 重跑失败条目 |
| 不想让 URL、`mg` 等单位被翻译 | `--skip-pattern '^https?://' --skip-pattern '^\d+(\.\d+)? ?(mg\|g\|ml)$'` |
| `review` 报错说没有 tkinter | 安装带 tk 的 Python（Windows 官方安装包默认自带） |
| `apply` 之后发现译错了 | 不要用 `--in-place`；重新 `apply` 即可覆盖 `<lang>_replaced/` |
| assets 里出现了 `zh_cn_replaced/` 之类的目录 | 那是 `apply` 的输出目录，校对合并后自行删除；它不该提交 |
| `convert` 报"没有 … 的可用转换器" | 装 OpenCC 或 zhconv：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple opencc`（国内默认 PyPI 连不上） |
