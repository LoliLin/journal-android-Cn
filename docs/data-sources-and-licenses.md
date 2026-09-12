# 数据来源、许可义务与免责声明

物质目录（`app/src/main/assets/substances/`）与界面语言文件（`app/src/main/assets/lang/`）的来源、
使用条件与免责声明以本文为准。代码本身是 **GPLv3-only**（见 `README.md`），与数据许可相互独立。

## 来源与用途

| 来源 | 我们取用了什么 | 许可 | 必须遵守 |
|---|---|---|---|
| [PsychonautWiki](https://psychonautwiki.org/) | 剂量、时长、生物利用度、耐受与交叉耐受、毒性、成瘾性、相互作用、别名（`fetch_psychonautwiki.py`） | CC BY-SA 4.0 | 署名；改编内容同协议共享；不得暗示其背书 |
| [TripSit](https://tripsit.me/)（[drugs](https://github.com/TripSit/drugs)） | 仅名称、别名、分类（`fetch_tripsit.py`） | **仓库未声明许可证**（默认保留所有权利） | 不复制其文案与数值；标注来源；商业分发前建议先取得许可 |
| WHO 协作中心 [ATC/DDD 索引](https://atcddd.fhi.no/atc_ddd_index/) | 仅 INN 名称、ATC 码、层级归属（`fetch_atc.py`） | © WHOCC（copyright/disclaimer 原文） | **不得复制/分发用于商业目的**；**不得改变或操纵材料**；使用须注明 WHOCC |
| [EUDA](https://www.euda.europa.eu/)（欧洲毒品报告） | 当年新通报 NPS 的名称、IUPAC 名、分类、通报日期、国家（`fetch_euda.py`） | EUDA 版权 + 再利用条款 | **每一份副本都要注明 EUDA 为来源**；其条款声明内容非临床/专业建议 |
| [FreeODwiki](https://github.com/SalviaSWC/FreeODwiki) | 简体中文正文、中文显示名、术语表 | CC BY-SA 4.0（`LICENSE`、README、index、常见问题一致；`CODE_OF_CONDUCT` 明确允许商业使用）。`LICENSE-STRICT`＝CC BY-ND 4.0 只覆盖 `文档/观点讨论/*`、`文档/od.md`、`关于本站/文档翻译指南和提示词.md` 等少数文件，**391 个 `药物/*.md` 均无 ND 声明** | 署名；改编内容同协议共享。术语表取自被标记 ND 的那份翻译指南，属事实性词对，需要时可与维护者确认 |
| DailyMed / EMA / SmPC / CPIC / PubMed | 代谢与排泄条目的**逐条**说明书来源，保存为数据里的 `metabolismSources` 链接 | NLM：美国政府作品不受版权保护，但站内含厂商提交内容；EMA 等允许再利用并注明来源 | 只做简短事实性摘述并保留原文链接，不整段转载 |
| [OpenCC](https://github.com/BYVoid/OpenCC) / [zhconv](https://github.com/gumblex/zhconv) | 简繁转换工具（不产生内容） | Apache-2.0 / GPLv2+ | 随依赖保留其许可声明（GPLv2+ 可升到 GPLv3，与本项目兼容） |

## 许可义务 ↔ 取数决策

- **TripSit 无许可证** → 只取「名称/别名/分类」这类事实字段；**文案、摘要、组合矩阵（`combos`）、
  剂量与时长字符串一律没拿**，工具里连解析都没有（只有显式 `--with-doses` 才会解析剂量，本仓库未启用）。
- **WHOCC 禁止商用、禁止修改** → 只存名称与 ATC 码，以及由码的层级映射出的应用分类；
  **DDD 数值与给药途径一个字都没进数据**（已核实：0 个文件含 `ddd` 字段）——这两列最容易触发
  「复制材料」与「当剂量用」两个问题。
- **署名要求** → PsychonautWiki、FreeODwiki（CC BY-SA）、WHOCC、EUDA、TripSit、NLM 的出处说明都在
  本文件与 `docs/substances-catalog-sources.md` 的许可列里；每条物质自己的 `url` 与每条代谢条目的
  `metabolismSources` 也直接指向来源页面。
- **EUDA「每一份副本都要署名」** → 目前落在本文件与仓库文档；如果要独立分发应用（APK、F-Droid），
  建议在应用内的「关于/FAQ」页再加一处数据来源说明。
- **混合来源的边界** → 一个物质条目可能同时含 PW 的结构化数值、ATC 的名称与分类、FreeODwiki 的中文正文；
  台账 `docs/substance-catalog-expansion.json` 的 `added[].sources` 逐条记录每个名字来自哪些来源。

## 你可以做什么

- **可以修改**：物质 JSON、语言文件、分类词表都可以自由改动、扩充、重新翻译。
- **可以自由分发**：连同应用一起分发，或单独提取数据分发，都可以。
- **可以商用**：PW / FreeODwiki 派生内容（占绝大多数）允许商业使用，条件是**署名 + 相同方式共享**
  （CC BY-SA 4.0；它与 GPLv3 单向兼容，所以并入本应用没有问题）。
- **例外与前提**：
  1. **ATC 来源的名称、码与层级**受 WHOCC 条款限制（禁商用、禁修改）。若你的分发是商业性的，
     建议就这部分与 WHOCC 确认，或把这几百条的名称与码替换成其它来源（INN 名称本身是公开事实，
     但 WHOCC 对其索引材料声明了版权）；
  2. **TripSit** 未声明许可证。我们只保留事实性字段并标注来源；出于 EU 数据库权（sui generis）的谨慎，
     商业分发前建议先向其社区确认；
  3. **逐条说明书来源**是第三方内容，转载时请只保留链接与简短事实性表述，不要整段复制；
  4. 我们无法替你授予超出上游许可的权利：上游权利人若提出异议，相关内容会被移除。
- **相同方式共享的含义**：以本目录数据为基础做出的改编（翻译、简繁转换、合并、改写）需以
  CC BY-SA 4.0 或兼容许可发布，并保留署名（可写「数据来自 Journal Android Multilingual 及其列出的来源」）。

## 免责声明

- **不是医疗建议**：剂量、时长、相互作用、代谢与排泄等信息仅供记录与参考，不能替代医生、药师或其它
  专业判断；请勿据此自行用药。EUDA 与 NLM 的条款同样声明其内容不构成临床建议。
- **不保证准确性、完整性与时效**：数据来自社区 wiki、厂商说明书与官方通报，可能有误、过时或缺失。
  新条目一律标记 `isApproved: false`，这表示「尚未人工复核」，不是监管批准状态。
- **无担保**：数据按「现状」提供，不作任何明示或默示担保（CC BY-SA 4.0 §5）。
- **责任限制**：作者与贡献者不对因使用这些数据造成的任何损害负责。
- **不表示背书**：PsychonautWiki、TripSit、WHOCC、EUDA、FreeODwiki、NLM/EMA 均未认可本项目。
- **商标**：文中出现的商品名与商标归各自所有者。
- **纠错与下架**：发现错误或权利问题请提 issue，我们会修正或移除相应内容。

## 如何核对

- 台账 `docs/substance-catalog-expansion.json`：`added`（谁新增了哪个名字）、`excluded`（为什么没收，
  含复方、生物制品、外周药等理由）、`resolved`（来源键 → 规范名）、`normalizationNotes`（改名与规范化）。
- 每条物质的 `url` 指向其来源页面；代谢与排泄条目的 `metabolismSources` 是逐条说明书链接。
- 取数口径与字段映射：`docs/substances-catalog-sources.md`（各源对照）、
  `docs/substances-pw-extraction.md`（PW 字段与坑）、`docs/substances-translation-protocol.md`（数据格式）。
