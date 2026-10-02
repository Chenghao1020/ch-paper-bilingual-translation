# 每篇论文的数据格式

代码、样式和浏览器检查可复用。每篇论文仅需填写以下数据；这些是任务结果，不是新脚本。使用 UTF-8 JSON。

## 任务文件

`init` 创建 `analysis/paper-translations/<name>/paper.json`、空 `records.json`、原文副本 `source.pdf`、提取文本和页面链接。`render` 创建 `pages/page-001.png` 等页面图像。脚本只允许任务目录在配置工作区内，输出文件名不得包含路径。

`paper.json` 中保留 `init` 生成的版本、工作区路径、源文件、哈希及页数。填写以下字段：

```json
{
  "title": {"source": "Source Paper Title", "target": "论文中文标题"},
  "languages": {
    "source": {"code": "en", "label": "English"},
    "target": {"code": "zh-CN", "label": "中文"}
  },
  "records_file": "records.json",
  "output_prefix": "论文短名_论文中英对照",
  "expected_ids": ["paper-title", "abstract-heading", "abstract-p1", "eq-1", "table-1", "ref-a"],
  "glossary": [{"source": "reference point", "target": "参考点"}],
  "editorial_notes": ["跨页段落已合并。公式保留原图，译者补充说明与原文分开。"],
  "review": {
    "reading_order": false,
    "translation_complete": false,
    "formulas_tables": false,
    "visual_assets": false
  }
}
```

这是部分字段示例，不应替换整个 `init` 生成的文件。编辑核对四项分别表示：已核对阅读顺序与来源覆盖；已完成所要求范围的翻译；已核对公式、表格、数值、引文；已检查需要保留的图像及裁切。没有某类内容时，确认确实不存在后可将相关项设为 true。

`expected_ids` 是按原文建立的清单。ID 命名只需稳定、唯一，以字母开头，仅包含英文字母、数字、下划线或连字符。顺序由 `records.json` 控制，不从页码自动排序，因为跨栏、跨页内容需要人工核对。

## 内容条目

每项使用 `id`、`kind`、`pages`、`source`、`target`。`pages` 是原始 PDF 的从 1 开始的页码列表，不是论文页脚印刷编号。

```json
[
  {"id": "paper-title", "kind": "title", "pages": [1], "source": "Source Paper Title", "target": "论文中文标题"},
  {"id": "abstract-heading", "kind": "heading", "level": 1, "pages": [1], "source": "Abstract", "target": "摘要"},
  {"id": "abstract-p1", "kind": "paragraph", "pages": [1, 2], "source": "The measured delay is 3.2 ms [7].", "target": "测得的时延为 3.2 ms [7]。"}
]
```

类型为 `title`、`heading`、`paragraph`、`equation`、`figure`、`table`、`reference`。脚注、作者单位或附录正文通常使用 paragraph，并按原文用 heading 分节。heading 的 level 为 1、2、3。

## 句子级对应高亮

paragraph 和 figure 必须提供已核对的 `alignment`。其 source/target 分别为按原顺序切分的句子文本数组（必要时可切分语义明确的分句），拼接后必须与条目的原文及译文逐字一致，保留句间空白和标点。每个 pairs 元素为 `[原文句子索引, 译文句子索引]`，索引从 0 开始。

```json
{
  "source": "The link remains available. The delay stays stable.",
  "target": "时延保持稳定。链路保持可用。",
  "alignment": {
    "source": ["The link remains available. ", "The delay stays stable."],
    "target": ["时延保持稳定。", "链路保持可用。"],
    "pairs": [[0, 1], [1, 0]],
    "reviewed": true
  }
}
```

对应关系由翻译者核对语义后填写，不由浏览器猜测。一个索引可在多个 pairs 中出现，表达一对多或多对一；使用必要分句可进一步缩小高亮范围。完整段落保留原有排版，只为句子增加内联高亮。

确实没有另一侧对应内容的译者辅助句子，分别用 `unpaired_source` 或 `unpaired_target` 列出索引；这些句子不产生对侧高亮。每个索引必须有配对或明确列为 unpaired，禁止缺漏或同时处于两者。未核对映射不能发布正式版；缺少映射的草稿不做整段联动。

标题、章节标签、短表题、文献条目和表格短单元格默认作为一个对应单元；多句表题或表格单元格也应填写同样的 alignment。公式仅有原式而没有双语句子时无需句子映射。正文重建前应先给旧数据补齐句子映射。

## 公式与图像

```json
{
  "id": "eq-1", "kind": "equation", "pages": [2],
  "source": "x = a + b    (1)", "target": "",
  "visuals": [{"page": 2, "bbox": [0.12, 0.30, 0.88, 0.37]}],
  "translator_note": "可选的辅助说明，明确不属于论文原文。"
}
```

`bbox` 为 `[左, 上, 右, 下]`，使用渲染页面宽高的 0–1 比例，原点在左上角。页面不同尺寸、分辨率或旋转时，不得复制旧论文坐标。公式的 target 可为空，因为数学式通常无需译成另一语言；不要将解释文字冒充原文。

figure 使用相同 visuals 结构，source 与 target 分别为原图注与译文，可在译文中补充图内标签的对照。一个条目可有多个裁切区域。

已有图像可用 `{"page": 2, "file": "assets/source-image.png"}`。该路径相对任务目录，必须位于其中；先复制参考目录的图片。最终 HTML 嵌入生成图片，Markdown 引用工作区内图片。

## 表格

```json
{
  "id": "table-1", "kind": "table", "pages": [2],
  "source": "Table I. Experimental settings.", "target": "表 I. 实验设置。",
  "table": {
    "headers": [{"source": "Parameter", "target": "参数"}, {"source": "Value", "target": "数值"}],
    "rows": [[{"source": "Delay", "target": "时延"}, {"source": "3.2 ms", "target": "3.2 ms"}]]
  },
  "visuals": [{"page": 2, "bbox": [0.08, 0.12, 0.92, 0.25]}]
}
```

表格每行宽度必须与表头相同，每格都提供原文和译文。数值与符号可在两侧重复。原表图像可选但建议保留以核对特殊符号；复杂合并表格可保留原图，并用可读记录表达译文，不得为了规整而改变数据关系。

## 参考文献

```json
{
  "id": "ref-a", "kind": "reference", "pages": [4],
  "source": "[A] J. Doe, A model, Example Journal, 2024, pp. 10–12.",
  "target": "[A] J. Doe，《一种模型》，Example Journal，2024 年，第 10–12 页。"
}
```

编号可以是数字、字母或作者年份，不要求 46 条或连续编号。PDF URL 位于 `source_pages.json` 的 page.links 中，带原 PDF 坐标；按相关原文位置核对链接归属，不能依顺序强配。脚本不会重建 URL 或更改出版年份。

## 草稿与重建

- `build --draft` 可预览尚未翻译的内容，但页面和文件名均标记草稿。
- 正式 build 要求 ID 清单匹配、必要内容齐全、原文哈希一致、四项编辑核对已完成。
- 阅读器审计是加载、结构与布局检查。`audit.json` 明确表示语义正确性没有被自动认证。
- 修改数据后使用同一任务目录重建；需要覆盖既有成果时，在有任务授权的前提下使用 `--overwrite`。
