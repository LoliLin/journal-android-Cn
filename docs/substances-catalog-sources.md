# Substance 目录扩充：外部来源怎么取数

本文件说明 PsychonautWiki 之外的来源（ATC / TripSit / EUDA / FreeODwiki）怎么用、能填哪些字段、
有什么坑，以及**不同语言的来源怎么快速处理**。每个来源一个脚本，共用 `_common.py` 与同一份台账；
PsychonautWiki 的字段映射与实测见 [`substances-pw-extraction.md`](substances-pw-extraction.md)。

## 分工与取数方式（均实测）

| 源 | 语言 | 能提供 | 取数方式 | 许可 |
|---|---|---|---|---|
| **PsychonautWiki** | en | 剂量、时长、生物利用度、耐受、交叉耐受、毒性、成瘾性、相互作用、别名 | GraphQL `api.psychonautwiki.org`（`fetch_psychonautwiki.py`） | CC BY-SA 4.0 |
| **TripSit** | en | 名称、别名、分类、按途径的剂量字符串、时长字符串、组合矩阵、短摘要 | 单文件 `raw.githubusercontent.com/TripSit/drugs/main/drugs.json`（555 条，1.6 MB，一次 GET） | ⚠️ **仓库无 LICENSE 文件**（默认保留所有权利）：只当名称/别名/分类的核对来源，不要逐字搬文案 |
| **ATC**（WHOCC） | en | INN 名称、ATC 码、层级归属、DDD（统计口径，**不能当剂量**） | `?code=<5位亚组>` 的 HTML 表格（iso-8859-1）；2/4 位页只列子级，需逐层下钻 | © WHOCC：**使用须注明来源**、**不得复制/分发用于商业目的**、**不得改变或操纵材料**（原文：atcddd.fhi.no/copyright_disclaimer/）。我们只存名称/ATC 码/层级，**没有存储 DDD 数值** |
| **EUDA** | en | 当年新通报 NPS：Common name、**IUPAC name**、classification、通报日期、国家 | 通报表 CSV；⚠️ 站点有 Cloudflare，脚本直连拿不到，需浏览器会话 | EUDA 拥有版权，但**允许复制/改编/分发（含部分）、任何介质与格式，条件是每一份副本都注明 EUDA 为来源**；其 legal notice 同时声明内容非专业/临床建议 |
| **FreeODwiki** | **zh** | 中文正文（概述/风险）、常用名与系统命名、精神活性类别、**按途径的剂量与时长表** | GitHub 仓库 `药物/*.md`（391 条，markdown + 表格） | CC BY-SA 4.0（`LICENSE`、README、index、常见问题一致，CODE_OF_CONDUCT 还写明允许商业使用）；⚠️ `LICENSE-STRICT`＝CC BY-ND 4.0 **只覆盖少数文件**（`文档/观点讨论/*`、`文档/od.md`、`关于本站/文档翻译指南和提示词.md`）——391 个 `药物/*.md` 里没有任何 ND 声明，我们取的正文与中文名都在 BY-SA 部分；术语表取自被标记 ND 的那份翻译指南，属事实性词对，风险低但可直接与维护者确认 |

几个实测细节：

- **ATC 层级**：`?code=N05` 只返回表单页（0 行），`?code=N05A` 列子级，`?code=N05BA` 才出行
  `['N05BA01','diazepam','10','mg','O','']`（多途径 DDD 会重复出现、码列留空，需向下填充）。
- **TripSit 剂量**是**按途径**的档位字符串：`{"Oral":{"Light":"40-75mg","Common":"75-125mg",
  "Strong":"125-175mg","Heavy":"175mg+"}}`，可解析成数值；脏值形如 `mg+`、`100+mg.`、`0.5mg-1mg`、
  `1-2 seeds`、`unknown`（后三者按设计跳过）。**时长字符串不分途径**，无法映射到 `roas[].duration`。
- **EUDA**：直连 CSV 会拿到 `Just a moment...`（Cloudflare 403）；用浏览器先打开报告页、
  再同源 `fetch(csvUrl, {credentials:"include"})` 可以拿到 200（实测 50 行）。
  因此工具默认要求 `--csv <本地文件>`。

## 台账（可审计的核心）

四个工具都支持 `--ledger docs/substance-catalog-expansion.json`（默认开），按来源幂等合并，
重复运行不会产生重复条目：

```json
{
  "checkedOn": "2026-09-12",
  "sourceSnapshots": [ { "source": "TripSit", "url": "…", "sha256": "…", "hashNote": "…" } ],
  "added":    [ { "name": "2-Chloroephenidine", "sources": [ {"source":"TripSit","key":"…","url":"…"} ] } ],
  "excluded": [ { "source": "ATC", "key": "N02AJ06", "name": "Codeine and paracetamol", "reason": "复方/合剂" } ],
  "resolved": [ { "source": "ATC", "key": "N05BA01", "name": "Diazepam" } ],
  "normalizationNotes": [ { "source": "ATC", "key": "N06DX02", "name": "Ginkgo biloba", "note": "ATC 原名 Ginkgo folium" } ]
}
```

- `resolved` 是「来源键 → 规范名」对照，用途是对齐重名/改名（ATC 码、TripSit key、EUDA 名称）。
- `excluded` 必须带 `reason`，这是"为什么没收"的唯一记录。
- `--no-ledger` 可关闭；报告文件另外落在 `docs/scripts/_work/`（不会写进 assets）。

## 各源写入什么

| 仓库字段 | ATC | TripSit | EUDA | PW |
|---|---|---|---|---|
| `name` | ✅（句子化 INN 名） | ✅（`pretty_name`） | ✅（Common name） | ✅ |
| `commonNames` | ❌ | ✅（含 aliases） | ❌（IUPAC 只进报告，便于去重） | ✅ |
| `categories` | ✅（类目映射，见下） | ✅（映射后直接可用） | ✅（分类映射） | ✅（class.psychoactive） |
| `url` | ✅ code 页 | ✅ factsheet 页 | ✅ 报告页 | ✅ wiki 页 |
| `roas[].dose` | ❌ | ⚠️ 需 `--with-doses`，字符串解析 | ❌ | ✅ 数值 |
| `roas[].duration` | ❌ | ❌（不分途径） | ❌ | ✅ |
| `tolerance`/`crossTolerances`/`toxicities`/`addictionPotential` | ❌ | ❌ | ❌ | ✅ |
| `interactions` | ❌ | ⚠️ 有 combo 矩阵，**不建议引入** | ❌ | ✅ |
| `summary` 等文案 | ❌（`--with-template-summary` 可写模板句） | ❌（无许可，不写） | ❌（同上） | ❌ |

所有工具默认**只补空缺、不覆盖已有值**（`--overwrite` 才覆盖），**永不改动** `summary`、
`effectsSummary`、`dosageRemark`、`generalRisks`、`longtermRisks`、`saferUse`、`isApproved`、
`localizedName`、`metabolism*`，以及**已有条目的 `categories`**（分类只写进新建条目）。
新条目一律 `isApproved: false`。

### ATC 类目 → 仓库分类

按参考目录（332 条 ATC 来源条目）反推，4 位类目做兜底、5 位亚组覆盖：

```
N02A opioid | N03A antiepileptic | N04A/N04B antiparkinsonian | N05A antipsychotic
N05B anxiolytic | N05C hypnotic | N06A antidepressant | N06B stimulant | N06D antidementia
N07B addiction-treatment | A08AA/C02AC centrally-acting-medication
追加：N03AA/N05CA barbiturate | N05BA/N05CD benzodiazepine | N06AB ssri
      N06AF/N06AG/N04BD maoi | N06BX nootropic | N06DA/N06DX antidementia
```

实测：与参考目录共同条目 328 条，其中 **313 条 `categories`+`url` 完全一致**（95%）。差异都是
人工补充（`adhd-medication`、`mood-stabilizer`、`botanical` 等）或按药理做的修正（如 N06AB 里
并非 SSRI 的 Etoperidone）。

### TripSit 分类 → 仓库分类

TripSit 的 17 个分类与仓库词表高度重合（`common`/`tentative`/`habit-forming`/`research-chemical`
等仓库标签本就来自这里），只需映射 `empathogen → entactogen`，并丢弃 `inactive`/`supplement`。
映射后为空（即只有这两种或没有分类）的条目会记入 `excluded`。

### EUDA 分类 → 仓库分类

`Arylcyclohexylamine → dissociative`（芳基环己胺类就是解离剂，写自造分类会让分类芯片消失）、
`Benzodiazepines → benzodiazepine`、`Cannabinoids → cannabinoid`、`Opioids → opioid`、
`Cathinones → stimulant`；`Others` 与其它（如 `Phenethylamines`）**不猜**，记入 `excluded` 待人工归类。
`--mark-nps` 会按参考目录的做法追加 `research-chemical` + `tentative`。

## 已知限制

1. **ATC 亚组 ≠ 药理**：同一个 5 位亚组里可能有例外（例如 N06AB 并非全部是 SSRI），
   自动映射只是起点，`resolved`/报告就是留给人工复核的。
2. **ATC 用拉丁药名与盐名/INN 拼写**：`Ginkgo folium`、`Valerianae radix`、`Lavandulae aetheroleum`、
   `Hyperici herba`，以及 `amfetamine`/`metamfetamine`/`dexamfetamine`/`potassium clorazepate`
   （仓库用 USAN/母体名）都已在 `ATC_NAME_OVERRIDES` 里改名（大小写不敏感，逐条记入
   `normalizationNotes` 并带 ATC 码）；其它盐名/拼写差异用 `--rename-map {ATC 名: 仓库名}`，
   否则会建出重复条目（如 `Amfetamine` 与 `Amphetamine` 并存）。
3. **EUDA 通报表只有当年**：EDR2026 的表 6 是 2025 年新通报的 50 条；参考目录里那 7 条
   （HHC、HHC-P、Isotonitazene 等）来自**报告正文**，不在表里。两者互补：表用于发现新物质，
   正文用于补充既有物质。
4. **TripSit 无许可**：不要逐字复制其 `properties.summary`；工具只把它写进报告供人工参考。
5. **分类词表**：`categories` 的值要同时满足两处，否则界面上有可见损失——① 在
   `root/_categories.json` 里有定义：`SubstanceRepository` 按它过滤，缺定义的分类**芯片整个
   不显示**；② 在 `assets/lang/<语言>.json` 里有 `categories.<name>` 键：缺键时
   `translateOrDefault` 回退显示英文原名。工具会提示写入的分类是否超出已采用的 33 个。
6. **不要引入剂量建议**：ATC 的 DDD 是统计口径；TripSit 的剂量字符串仅在 `--with-doses`
   时写入，质量不如 PW。

## FreeODwiki（中文源）

它是 PsychonautWiki 的**中文翻译集**（自己的翻译指南里写明"以 psywiki 为例，因为 CC 协议兼容"），
所以结构化数值与 PW 同构，映射规则一模一样：**阈值→`lightMin`、中等→`commonMin`、
强烈→`strongMin`、严重→`heavyMin`**；**总时长/药效发作/药效上升/药效达峰/药效褪去/药效残余**
→ `total/onset/comeup/peak/offset/afterglow`（实测 2C-B 口服与仓库现有资产逐项一致）。

`fetch_freeodwiki.py` 的默认行为（保守）：

- 只写 `<lang>/<Name>.json` 覆盖层，字段默认 `summary`；`--fields summary,saferUse,generalRisks,commonNames,localizedName`
  可选（`generalRisks` 会把"毒性/危害/风险/致死/滥用潜力"类章节的正文合并进来，是**原始素材**，
  需要人工删减；`saferUse` 只在条目真有减害列表时才有内容——多数条目没有，别指望它）；
- **不动 `root/`**：结构化数据要显式 `--structure check|fill|overwrite`。`check` 只报告差异，
  实测 2C-B 的 insufflated 时长与当前 PW 有出入（PW/仓库 4–6 h、onset 1–5 min；
  译文页 4–7 h、onset 0–20 min）——**说明译文页会滞后或经过编辑，先看差异再决定**；
- 输出是**纯文本**（去掉了 markdown 链接/粗体/脚注），因为应用用 `Text` 直接渲染；
- **名字对齐**按优先级：`root/` 同名 → 人工对照表 → 中文名反查（语言文件的 `localizedName`
  → 对应条目）→ 页面英文名按「物质名 → 别名」两轮反查（先 `name` 再 `commonNames`，
  避免 `DPD` 这类缩写把页面配到别的物质）→ 才当新名字。
  实测只有这条路才对：FreeODwiki 用「系统命名」当标题的页面（`1,3,7-Trimethylxanthine` = 咖啡因、
  `(RS)-1-Phenylpropan-2-amine` = 安非他命）如果直接拿标题建条目，会写出**应用根本不加载的孤立覆盖层**。
- **人工对照表** `docs/freeodwiki-name-map.json`：`{map: {页名: 仓库名}, skipped: {页名: 原因}}`。
  已覆盖全部 391 个条目（145 条映射、19 条跳过），纯中文页名（`鼠尾草素甲` → `Salvinorin A`、
  `苄达明` → `Benzydamine`）、代号/商品名页（`Ro5-3448` → `Diclazepam`、`洛哌丁胺` → `Loperamide`）
  都在里面。跳过的都是索引页、分类页、植物属页、复方制剂、讨论页。
- **`--create-root`**：对照表映射到仓库里没有的英文名时（`Thujone`、`Flumazenil`、`Yohimbine`、
  `Tobacco`、`Psilocybe cyanescens` 等），建一个最小 root 条目（只写 `name`/`url`/`categories`/
  `isApproved:false`，正文仍走覆盖层）——否则覆盖层没有对应物质、应用不会加载。
  没有可写内容的页面（无正文、无剂量表）不会建条目。

## 不同语言的来源怎么快速处理

四个手段，按收益排序（数字均为实测）：

1. **按源语言路由，不搞一刀切**：中文源（FreeODwiki）直接写 `zh_cn` 覆盖层，**翻译调用为 0**；
   英文源（PW/TripSit/ATC/EUDA）写 `root`，只有需要中文时才翻译。
   现状：`zh_cn` 常量表 1148 条里 **1045 条已含汉字**（已译）、**101 条是纯 ASCII**（物质名/单位/
   缩写/URL，本就不该翻）——真正待翻的很少。
2. **转换代替第二遍翻译**：`zh_tw` = `convert zh_cn zh_tw`（OpenCC `s2twp` 优先，缺依赖则 zhconv）。
   实测 1148 条常量里 **236 条（20%）繁化后完全相同**（零成本），其余本地瞬时完成，不花 API。
   台湾用词 zhconv 覆盖不全（软件→軟體 ✔、数据库→資料庫 ✔，但 用户→用戶 ✗），所以要配
   `docs/glossary/zh_cn_to_zh_tw.json`（已备 32 条，需人工审校）；OpenCC 的 `s2twp` 本身就带用词转换
   （实测同一句 `导出`→**匯出**，zhconv 只给 `導出`）。两种转换器都实测跑通（`zhconv zh-tw` 回退 +
   `OpenCC s2twp`），输出无简体残留、术语全部命中。
   依赖装法（国内默认 PyPI 连不上，**清华镜像可用**，且有 cp313 Windows 轮子，免编译）：
   `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple opencc`。
3. **批量 + 术语表**：`translate --batch 20` 把 1148 条从 **1148 次请求压到 ~58 次**
   （`--dry-run` 会预告请求数）；`--glossary docs/glossary/en_to_zh.json` 把术语注入提示词
   （那 42 条来自 FreeODwiki 的术语表，含 threshold/light/common/strong/heavy、Total/Onset/Peak/
   Oral/insufflated 等剂量-时长-途径用词），保证跨条目译名一致。
4. **翻译记忆与跳过规则**：`--resume` 复用已有译文；`--skip-ascii` 跳过纯 ASCII 标识符/单位/URL；
   转换路径本身零成本，重复跑也只改有变化的地方。

## 命令速览

```bash
# 1) 从 TripSit 补名称/别名/分类（几秒；--with-doses 才解析剂量）
python docs/scripts/fetch_tripsit.py --dry-run --verbose
python docs/scripts/fetch_tripsit.py --with-doses

# 2) 从 ATC 按类目补精神科药物（默认就是那轮扩张用的 9 个类目）
python docs/scripts/fetch_atc.py --dry-run --verbose
python docs/scripts/fetch_atc.py --atc-version 2026-01-20

# 3) 从 EUDA 补当年新通报 NPS（先在浏览器下载 CSV）
python docs/scripts/fetch_euda.py --csv ~/Downloads/edr2026-nps-table-6-notifications_en.csv --mark-nps

# 4) 从 PsychonautWiki 补剂量/时长/耐受/相互作用
python docs/scripts/fetch_psychonautwiki.py --dry-run --verbose
python docs/scripts/fetch_psychonautwiki.py

# 5) 从 FreeODwiki（中文）直接补 zh_cn 覆盖层，不需要机器翻译
git clone --depth 1 https://github.com/SalviaSWC/FreeODwiki.git /tmp/freeod
python docs/scripts/fetch_freeodwiki.py --repo /tmp/freeod --dry-run --verbose
python docs/scripts/fetch_freeodwiki.py --repo /tmp/freeod --fields summary,generalRisks
python docs/scripts/fetch_freeodwiki.py --repo /tmp/freeod --structure check   # 只报告数值差异

# 6) 语言之间本机转换（省掉一整轮 API 翻译）
python docs/scripts/substances_pipeline.py convert zh_cn zh_tw --dry-run
python docs/scripts/substances_pipeline.py convert zh_cn zh_tw \
    --glossary docs/glossary/zh_cn_to_zh_tw.json
```

推荐顺序：**TripSit → ATC → EUDA → PW**（英文源进 `root`），**FreeODwiki → convert**（中文源直接进
`zh_cn`，再转 `zh_tw`），最后按 [`substances-pipeline.md`](substances-pipeline.md) 的
`scaffold`/`constants`/`translate --batch`/`apply` 补齐剩余的语言覆盖层。
