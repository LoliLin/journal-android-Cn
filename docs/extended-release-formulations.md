# 口服缓释剂型记录

新增记录的确认页与已有记录的编辑页提供「剂型」选择。只有目录里配置了口服剂型的物质才显示该选择；
已有剂型标记的记录，即使目录配置以后变化，仍可查看和清除这个标记。

## 支持的物质与说明书来源

首批 13 个品种，核对日期 2026-09-08：

| 物质 | 说明书来源（DailyMed） |
|---|---|
| Alprazolam（阿普唑仑） | https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=5d839a8b-0f45-42bf-acc1-2bd28f948e53 |
| Bupropion（安非他酮） | https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=439a7e93-f578-434f-943f-4b93c35450f5 |
| Carbamazepine（卡马西平） | https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=1fc170d7-db1a-486d-8c10-faa6e3da3b1e |
| Clonidine（可乐定） | https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=03a53175-d301-4001-b28b-78ecd763c4ae |
| Guanfacine（胍法辛） | https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=07a701e2-39b7-4bb1-a7c7-d9baed4ab18a |
| Lithium（锂） | https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=f7f5b69a-c2a1-4586-a189-1475d41387c0 |
| Methylphenidate（哌甲酯） | https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=1a88218c-5b18-4220-8f56-526de1a276cd |
| Paliperidone（帕利哌酮） | https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=463db841-297f-7692-e063-6394a90a8c14 |
| Paroxetine（帕罗西汀） | https://dailymed.nlm.nih.gov/dailymed/downloadpdffile.cfm?setId=a73cf8ee-f99b-4972-8939-0d394a527134 |
| Quetiapine（喹硫平） | https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=5e4a84b1-fb8c-44d0-8213-51e43d71db69 |
| Valproic acid（丙戊酸相关制剂） | https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=93d6ddb5-7143-4917-baf7-31cbf8a90e8d |
| Venlafaxine（文拉法辛） | https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=db1d16b3-d1a2-4f41-adff-a87c17689aa0 |
| Zolpidem（唑吡坦） | https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=0c64bc71-2e7f-4b15-a8e1-acb8de04395f |

可选值为：

- **未指定**：没有记录释放方式，旧记录保持这个状态。
- **普通 / 速释**：`IMMEDIATE_RELEASE`。
- **缓释 / 控释**：`EXTENDED_RELEASE`，作为 SR、ER、XR、CR 等标示的概括性记录。

帕利哌酮的口服选项只有**缓释 / 控释**（其余 12 个品种同时提供普通 / 速释）。
剂型依据实际包装记录；仅有肠溶包衣不代表缓释。此选项不换算剂量，也不保证不同品牌、盐型和释放系统
可按相同毫克数互换。

## 保存与回溯

- Room 数据库从 v7 自动迁移到 v8（`AutoMigration(from = 7, to = 8)`），为 `Ingestion` 添加可空
  `releaseForm` 列；旧数据不被推断为普通片，保持「未指定」。
- 日记记录行显示已指定的剂型，编辑时保留选择。
- 最近使用的快捷剂量包含剂型，因此相同物质、相同剂量的普通与缓释记录不会合并为同一个快捷项；
  再次使用快捷项会带入原剂型。
- 导出 / 导入使用可选 `releaseForm` 字段（`JournalExport.kt`）；旧备份省略该字段时按「未指定」读取。
- 当前没有剂型专用的剂量和时长数据：缓释记录不采用普通制剂的剂量分级、相对剂量参考或作用时间曲线，
  记录中的实际剂量和摄入时间仍原样保留。

## 目录格式

在对应 `root/<Name>.json` 添加结构字段（语言覆盖层不需要复制，选项名由 UI 语言文件翻译）：

```json
{
  "oralReleaseForms": ["IMMEDIATE_RELEASE", "EXTENDED_RELEASE"]
}
```

未配置时默认为空列表。解析器忽略无法识别的剂型值，保持宽容加载；该配置仅用于口服路线。

## 校验

- 目录：13 个品种的 `root/*.json` 都带 `oralReleaseForms`，取值只出现 `IMMEDIATE_RELEASE` 与
  `EXTENDED_RELEASE`，解析器与 `ReleaseForm.fromName` 一一对应。
- 语言键：`release_form_title` / `release_form_unspecified` / `release_form_immediate` /
  `release_form_extended` / `release_form_hint` / `release_form_no_reference` 在
  `assets/lang/{en_us,zh_cn,zh_tw}.json` 中各 6 条齐全，无 `missing_key`。
- JVM 测试：`gradlew.bat testDebugUnitTest` 全绿（47 个用例、0 失败，2026-09-12 实测），覆盖目录字段解析
  与导出 / 导入的剂型往返。

> 记录：原实现另在 Android API 28 模拟器上验证过 v7→v8 迁移（旧记录 `releaseForm` 为 `NULL`，
> 剂量与单位保留），以及新增缓释记录、改回普通剂型、同剂量两种剂型的快捷记录区分与恢复。
