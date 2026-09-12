# 从 PsychonautWiki 提取 substance JSON

本文件是 `docs/scripts/fetch_psychonautwiki.py` 的实现依据：数据源、字段映射、实测通过率、
拿不到的字段，以及许可与礼仪要求。抓取日期基准：2026-09-12。

## 数据源与分工

| 源 | 端点 | 负责 |
|---|---|---|
| GraphQL API | `https://api.psychonautwiki.org/` | 剂量、时长、生物利用度、耐受、交叉耐受、毒性、成瘾性、相互作用、别名 |
| MediaWiki API | `https://psychonautwiki.org/w/api.php` | 索引页渲染、`Category:*`、重定向解析、正文 |
| 页面 | `Psychoactive substance index` | 只适合做枚举与人工分组，没有数值 |

索引页本身是壳（`{{Substances/Content}}` + `{{:List/substances}}`），wikitext 里没有列表，
所以 `fetch --source index` 解析的是它的**渲染 HTML**：按 `<h2..h4>` 标题给链接分组，
得到 344 个条目、标题即分组名（`Lysergamides` / `2C-x` / `Arylcyclohexylamines` …）。
其中 274 条能在 GraphQL 目录里找到对应数据，其余多为别名差异（`AMT` vs `aMT`、
`5-HTP` vs `5-Hydroxytryptophan`）或纯导航页；这些会写进报告等你人工处理。

枚举全量直接用 GraphQL 分页（`substances(limit: 500, offset: n)`），实测 **373 条**，
两个请求就能拉完，不必爬页面。

### 名字对齐

仓库 291 条里 **281 条**能按名字直接命中 API，剩下 10 条是 PW 用了别的页面名：

```
3-Me-PCPy  Amantadine  Atropine  Bupropion  Lithium
Olanzapine Phenazepam  Pseudoephedrine  Psilocybin  THC
```

`fetch` 会用 MediaWiki `redirects=1`（每批 50 个）把仓库文件名解析到实际页面，
命中后仍然写回**原文件名**，不会产生重名条目。

## 字段映射（实测）

以 281 个可匹配物质、**349 个 (物质, 给药途径)** 对做全量核对：

| 仓库字段 | API 来源 | 实测 |
|---|---|---|
| `name` `url` `commonNames` | 同名 | 一致 |
| `roas[].name` | `roas[].name`（小写；`SubstanceParser` 会 uppercase 后匹配 `AdministrationRoute`） | 349 对全中 |
| `dose.units` | `dose.units` | 需归一化，见坑 2 |
| `dose.lightMin` | **`dose.threshold`** | ← 不是 `light.min`，见坑 4 |
| `dose.commonMin` `strongMin` `heavyMin` | `dose.common.min` `strong.min` `heavy` | 342/349 完全一致（其余差异是 API 现在返回 null） |
| `roas[].duration.*` | 同名（`onset/comeup/peak/offset/total/afterglow`） | 一致；`units` 需小写化，`min`/`max` 为空时省略该键 |
| `roas[].bioavailability.{min,max}` | `roas[].bioavailability` | 形状一致（仓库仅 10 条用到） |
| `tolerance.{full,half,zero}` | `tolerance` | 217/281 双方都有 |
| `crossTolerances` | `crossTolerances` | 204/281；需复数归一，见坑 3 |
| `toxicities` | `toxicity` | 214/281 |
| `addictionPotential` | `addictionPotential` | 235/281（原文照搬） |
| `interactions.{dangerous,unsafe,uncertain}` | `*Interactions[].name` | 196/281 |
| `categories` | API `class.psychoactive`（复数）→ 归一化到仓库词表 | 只用于**新建条目**，见下 |

`fetch` 实现后的端到端核对：**161/281 个物质在受管字段上语义完全一致**，其余差异全部可解释：

- `interactions` 87 条：PW 改了页面名（仓库 `THC`，PW 现在叫 `Cannabis`）——默认不覆盖，留在报告里。
- `dose` 50 条：仓库有值而 API 现在返回 `null`（如 `25B-NBOMe.insufflated.heavyMin=500`）——不覆盖。
- `crossTolerances` 3 条、`tolerance`/`addictionPotential`/`commonNames`/`url` 各 2~3 条：
  来自非 PW 来源的人工整理（Klop233 那批 ATC/TripSit/EUDA 条目）——不覆盖。

## PW 给不了的字段

| 字段 | 情况 |
|---|---|
| `summary` | **API 的 `summary` 字段是坏的**，恒返回 `"Summary sheet: 2C-B 2C-B"`；`<Name>/Summary` 面板只有剂量表格；正文 `prop=extracts&exintro` 是另一段导语。仓库现有文案不在当前 PW 页面上。 |
| `effectsSummary` `dosageRemark` `generalRisks` `longtermRisks` `saferUse` | 不在 PW（文案来自德文减害资料），需人工或另找来源 |
| `categories` 里的 `common` `tentative` `habit-forming` | 实测 `Category:Common` / `Tentative` / `Habit-forming` **都不存在**，也不等于 API 的 `featured`（`1B-LSD` 是 `featured=true` 却没有 `common`）——属于 app 侧自建词表 |
| `isApproved` `localizedName` | 仓库自管（审核状态 / 翻译覆盖层） |
| `metabolism` `metabolismSources` | 不在 PW，见 `substance-catalog-expansion.md`（DailyMed / EMA / SmPC） |

因此 `fetch` 的定位是**补结构化数字字段**，不负责文案，也不负责审核状态。

## 已知坑

1. **索引页不是数据源**：`Psychoactive_substance_index` 的 wikitext 只有模板调用，要用渲染 HTML。
   同理，API 全量遍历里混着 PW 的类目页与消歧页（`Substituted cathinones`、`Substituted
   tryptamines`、`Amphetamine (disambiguation)` 等 8 个），工具按
   `PW_NON_SUBSTANCE_RE`（`^Substituted…` / `…(disambiguation)`）跳过并列进报告，
   否则会建出没有任何剂量数据的“物质”。
2. **单位字形**：API 用 `μg`(U+03BC)，仓库用 `µg`(U+00B5)。不归一化就会有 6/349 的假差异。
3. **复数**：API 交叉耐受用 `opioids`/`stimulants`/`benzodiazepines`/`entactogens`，
   仓库用单数。`fetch` 复用 `fix-tolerances` 的映射表，避免刚清掉的复数又被写回去。
4. **`lightMin` 存的是 threshold**：`dose.light` 的区间被丢弃，`lightMin ← threshold`。
   这是上游既有约定（比对 11 条途径全部吻合），改动它会让全量数据漂移，所以沿用并在此写明。
5. **`inhaled` 是仓库专有途径**：PW 的 `SubstanceRoaTypes` 只有 10 个、没有 inhaled，
   仓库却用了 39 次（如 DMT）。`fetch` 不会猜测映射，DMT 会保留 `inhaled` 并追加 PW 的 `smoked`。
6. **空值表示**：仓库有时写 `"toxicities": []`、有时省略键；`roa` 的 `min`/`max` 为空时省略键。
   两者对解析器等价（`SubstanceParser` 一律宽容处理）。
7. **覆盖面**：仍有 61/281 没有 `tolerance`、63 没有 `toxicity`、74 没有 `crossTolerances`。
   **缺字段 ≠ 没有该性质**，不要据此下结论。
8. **PW 不是唯一来源**：PW 目录 373 条；仓库当前 291 条 + Klop233 扩到 865 条，
   后者主要来自 ATC(332)/TripSit(225)/EUDA(7)，且明确没有引入 PW 的剂量分级。

## 许可与礼仪

- 实测 `action=query&meta=siteinfo&siprop=rightsinfo` → **CC BY-SA 4.0**。
  必须署名 + 同协议共享，并保留来源页面链接（PW 页面常带 `Category:All accuracy disputes`、
  `Articles with unsourced statements`，社区众包质量参差）。
- 请求礼仪：带可联系的 `User-Agent`（默认值已带仓库地址）、串行 + `--delay`（默认 0.5s）、
  结果缓存到 `docs/scripts/_work/pw-cache/`，MediaWiki 批量查询每批 50 个标题。
  全量刷新只需 3~4 个请求。

## 工具用法

抓取是**独立脚本** `docs/scripts/fetch_psychonautwiki.py`（与本地数据流水线
`substances_pipeline.py` 分开，两者共用 `docs/scripts/_common.py` 里的路径/JSON 辅助）：

```bash
# 先看会改什么（完全只读：不写文件、不建目录、不写缓存）
python docs/scripts/fetch_psychonautwiki.py --dry-run --verbose

# 默认：只补空缺，不覆盖任何已有值，人工字段永不改动
python docs/scripts/fetch_psychonautwiki.py

# 只处理索引页列出的物质，并把索引分组写进报告
python docs/scripts/fetch_psychonautwiki.py --source index

# 用 API 值覆盖已有结构化字段（仍不动文案/审核状态/翻译）
python docs/scripts/fetch_psychonautwiki.py --overwrite
```

| 参数 | 用途 |
|---|---|
| `--source api\|index` | `api`=遍历 API 全量（约 373 条，默认）；`index`=只处理索引页列出的物质 |
| `--out` | 输出目录（默认 `<assets>/root`） |
| `--cache-dir` | 缓存目录（默认 `docs/scripts/_work/pw-cache`）；有缓存时全量刷新只需 3~4 个请求 |
| `--limit` `--dry-run` `--verbose` | 试跑与预览 |
| `--overwrite` | 允许覆盖已有结构化字段（默认只补空缺） |
| `--refresh` `--delay` `--user-agent` | 忽略缓存 / 请求间隔 / 请求 UA |
| `--assets-dir` | 数据目录（默认自动探测 `app/src/main/assets/substances`） |

### 安全边界

只有 `FETCH_MANAGED_FIELDS`（`url` `commonNames` `tolerance` `crossTolerances` `toxicities`
`addictionPotential` `interactions` `roas`）会被写入，且默认**只补空缺**：`roas` 按途径逐个补齐
`dose`/`duration`/`bioavailability` 里缺失的小项，已有值一律不动（`--overwrite` 才覆盖整块）。

`summary`、`effectsSummary`、`dosageRemark`、`generalRisks`、`longtermRisks`、`saferUse`、
`isApproved`、`localizedName`、`metabolism*`，以及**已有条目的 `categories`** 永远不会被改动；
`categories` 只在新建条目时按 API 的 psychoactive class 写入（归一化后必须命中仓库词表）。
新条目一律 `isApproved: false`。

### 产出

默认报告文件是 `<cache-dir>/pw-report.json`（即 `docs/scripts/_work/pw-cache/pw-report.json`，
可用 `--report` 改）——**不要把它写进 assets**：那是随 APK 打包的目录，报告属于工作产物。
报告逐条记录 API 名、写回的文件名、对齐方式（`name` 或 `redirect:<原文件名>`）、索引分组、
`changed` 与 `kept` 字段，以及 `repo_files_without_api_record`（仓库有、API 无记录）和
`index_entries_missing_in_api`。

其他来源（ATC / TripSit / EUDA）见 [`substances-catalog-sources.md`](substances-catalog-sources.md)；
它们共用同一份台账 `docs/substance-catalog-expansion.json`。

### 排错

| 现象 | 处理 |
|---|---|
| `GraphQL 返回 …` 或超时 | 检查网络；已抓到的结果在 `<cache-dir>/` 里，不加 `--refresh` 就能复用 |
| 改了不该改的字段 | 默认只补空缺；只有显式 `--overwrite` 才覆盖结构化字段，文案/审核状态永远不动 |
| 抓不到某些物质 | 看报告里的 `repo_files_without_api_record` 与 `index_entries_missing_in_api` |
| 想把结果并进语言覆盖层 | 那是流水线的活：先 `scaffold`，再 `constants` / `translate` / `apply` |
