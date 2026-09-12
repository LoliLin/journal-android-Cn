Copyright (C) 2022 Isaak Hanimann.

Copyright (C) 2024 Oriyukisuzumiya.

Copyright (C) 2026 Lolin Verse.

Licensed, GPLv3-Only

# Journal Android Multilingual

<a href='https://f-droid.org/en/packages/in.kawaiis.journal/'><img src="https://fdroid.gitlab.io/artwork/badge/get-it-on-zh-cn.png" height="100" /></a>

Journal 是一个著名的用于记录药物使用情况的应用，广泛流传于 Oder 之间。Journal 自 ~~9.0~~ 11.1 起转闭源程序，并对其高级功能收费。与此同时，Journal 以全英文的方式呈现，对其他语言使用者晦涩难懂。

Journal 的数据来自 PsychonautWiki，这是一个全英文 wiki。

相比于 Journal 的其他分支，Journal Android Multilingual 尽可能多地完成了多语言的框架搭建和翻译工作。在借助 Deepseek v4 pro 的协助下，我们几乎翻译了全部物质条目和界面控件——包括物质描述、剂量参考、类别说明等。不过，由于部分物质名和类型名被深度嵌入在复杂的代码传参结构中（例如用于数据关联和搜索匹配的 key），直接替换会导致功能异常，因此这些字段仍然保留了原始英文名称。你可用使用 Issue 进行反馈

同时，Journal Android Multilingual 目前也添加了一些趣味性内容，并以趣味性的版本命名法。例如：v9.3 - 鸡哥奇遇记

[从此，获得更多](https://github.com/LoliLin/journal-android-multilingual/releases)  

[拓展包开发模板](https://github.com/LoliLin/journal-android-multilingual-ext_template)

## Thanks

物质目录与条目文案来自下面这些公开来源，分别致谢：

- **[PsychonautWiki](https://psychonautwiki.org/)** —— 应用的基础数据来源（剂量、时长、生物利用度、耐受与交叉耐受、毒性、成瘾性、相互作用、别名），内容依 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 使用并保留署名。
- **[TripSit](https://tripsit.me/)**（[drugs 资料库](https://github.com/TripSit/drugs)）—— 用于核对物质名称、别名与分类。该仓库未声明许可证，因此只取名称/别名/分类这类事实性字段，不复制它的文案。
- **WHO 协作中心 [ATC/DDD 索引](https://atcddd.fhi.no/atc_ddd_index/)** —— 用于补充精神科药物的 INN 名称、ATC 码与分类归属。ATC 的 DDD 是统计口径，没有当作剂量使用。
- **[EUDA](https://www.euda.europa.eu/)**（欧洲毒品局，《2026 年欧洲毒品报告》）—— 用于补充当年新通报的精神活性物质：名称、IUPAC 名、分类、通报日期与国家。
- **[FreeODwiki](https://github.com/SalviaSWC/FreeODwiki)** —— PsychonautWiki 的中文翻译集，用于简体中文条目的正文与中文显示名（其仓库标注 CC BY-SA 4.0，以其说明为准）。

代谢与排泄条目逐条标注了说明书来源（DailyMed、EMA 产品资料、厂商 SmPC、CPIC 指南及原始研究），链接随条目保存在数据中，清单见 [docs/substance-metabolism-sources.json](docs/substance-metabolism-sources.json)。

多语言的简繁转换借助 [OpenCC](https://github.com/BYVoid/OpenCC) 与 [zhconv](https://github.com/gumblex/zhconv) 完成；条目与界面文案的翻译由 DeepSeek 协助。
