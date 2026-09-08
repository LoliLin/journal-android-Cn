# Substance 多语言翻译协议（草案）

本协议用于拆分 `substances` 的结构与文本，以便多语言翻译时只覆盖需要翻译的字段。

## 目录结构

```
app/src/main/assets/substances/
├── root/
│   ├── _categories.json
│   ├── Pregabalin.json
│   └── ...
└── <current_Lang>/
    ├── _categories.json
    ├── Pregabalin.json
    └── ...
```

- `root/`：基础数据层（结构字段 + 英文文本），作为默认内容来源。
- `<current_Lang>/`：当前语言覆盖层，只放需要翻译的文本字段。

## 加载与覆盖规则

应用会按照下列顺序读取并合并 JSON（后者覆盖前者）：

1. `root`
2. `<current_Lang>`

合并规则：
- **对象字段**会递归合并（例如 `tolerance`、`interactions`）。
- **数组字段**（如 `roas`）会整体覆盖。
- 文件名（如 `Pregabalin.json`）是合并键：同名文件会被后者覆盖并合并。

## Substance JSON 拆分规则

### root（基础层）
- 必须包含：
  - `name`
  - `localizedName`（默认与 `name` 相同）
  - `url`
  - 结构字段（如 `tolerance`、`interactions`、`roas` 等）
- 可包含英文文本字段，作为默认展示内容。
- 可选结构字段 `oralReleaseForms` 留在 `root`，选项通过 UI 语言文件翻译，参见 `extended-release-formulations.md`。

### <current_Lang>（文本覆盖层）
- 仅放需要翻译的文本字段，例如：
  - `summary`
  - `effectsSummary`
  - `metabolism`（代谢与排泄说明；来源 URL 数组 `metabolismSources` 留在 `root`）
  - `dosageRemark`
  - `generalRisks`
  - `longtermRisks`
  - `saferUse`（数组）
  - 以及其它需要翻译的字符串字段

### 示例

**root/Pregabalin.json**（结构层，含关键字段）
```json
{
  "name": "Pregabalin",
  "localizedName": "Pregabalin",
  "commonNames": [
    "Pregabalin",
    "Lyrica",
    "Nervalin"
  ],
  "url": "https://psychonautwiki.org/wiki/Pregabalin",
  "isApproved": true,
  "tolerance": {
    "full": "within several months of continuous use",
    "zero": "7 - 14 days"
  },
  "crossTolerances": [],
  "toxicities": [
    "low toxicity"
  ],
  "categories": [
    "depressant",
    "habit-forming",
    "common"
  ],
  "interactions": {
    "dangerous": [],
    "unsafe": [],
    "uncertain": [
      "Oxycodone",
      "SSRIs",
      "MDMA"
    ]
  },
  "roas": [
    {
      "name": "oral",
      "dose": {
        "units": "mg",
        "lightMin": 50,
        "commonMin": 225,
        "strongMin": 600,
        "heavyMin": 900
      },
      "duration": {
        "onset": {
          "min": 30,
          "max": 45,
          "units": "minutes"
        },
        "comeup": {
          "min": 1,
          "max": 2,
          "units": "hours"
        },
        "peak": {
          "min": 4,
          "max": 6,
          "units": "hours"
        },
        "offset": {
          "min": 4,
          "max": 8,
          "units": "hours"
        },
        "total": {
          "min": 9,
          "max": 17,
          "units": "hours"
        },
        "afterglow": {
          "min": 4,
          "max": 10,
          "units": "hours"
        }
      },
      "bioavailability": {
        "max": 90
      }
    },
    {
      "name": "rectal",
      "dose": {
        "units": "mg",
        "lightMin": 40,
        "commonMin": 200,
        "strongMin": 450,
        "heavyMin": 600
      },
      "duration": {
        "onset": {
          "min": 15,
          "max": 30,
          "units": "minutes"
        },
        "comeup": {
          "min": 30,
          "max": 120,
          "units": "minutes"
        },
        "peak": {
          "min": 2,
          "max": 3,
          "units": "hours"
        },
        "offset": {
          "min": 3,
          "max": 5,
          "units": "hours"
        },
        "total": {
          "min": 5,
          "max": 8,
          "units": "hours"
        },
        "afterglow": {
          "min": 6,
          "max": 12,
          "units": "hours"
        }
      }
    }
  ]
}
```

**<current_Lang>/Pregabalin.json**（文本层，仅覆盖 summary）
```json
{
  "summary": "Pregabalin (Lyrica) is a GABA derivative that is used to treat neuropathic pain and seizures, as well as anxiety."
}
```
