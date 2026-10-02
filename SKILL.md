---
name: ch-paper-bilingual-translation
description: Translate academic papers into paragraph-aligned bilingual editions while preserving equations, figures, tables, and references. Reuse the bundled PDF preparation, HTML and Markdown publishing, and reader checks instead of writing per-paper scripts. Use for full-paper translation or bilingual comparison text; honor explicitly requested output formats.
---

# 论文双语对照翻译

把论文原文与译文逐段对应，保留技术含义、条件、不确定性、数值、公式、图表和引文。默认英译中；可按用户要求更换语言。复用本技能脚本，论文差异写入 JSON 数据文件，不另写同功能脚本。

## 使用范围与输出

- 未指定格式时，优先生成自包含 HTML 双栏阅读版与可编辑 Markdown 对照文本。HTML 支持检索、语言切换、目录和手机单栏阅读；选中任一侧句子中的文字时，仅高亮另一侧对应句子，跨句选择则高亮对应的多句，取消选择即清除。对应关系使用经过核对的句子或必要分句映射，不退回整段高亮。表格按对应单元格内的句子联动，短标签或数值作为单个单元。Markdown 不提供交互高亮。
- 用户明确要求 Word、PDF 或其他格式时，按其要求使用对应文档工具；可先复用提取和内容数据，但不要把 HTML 当作指定格式的完成结果。
- 所有输入副本、数据、缓存、截图和结果位于当前任务工作区。脚本的 `--workspace` 传入本次任务的实际目录；成果默认在其根目录，中间文件在 `analysis/paper-translations/<name>`。
- 技能目录是代码资源，执行时不要向其中写入任务数据。参考文件位于只读目录时，先由 `init` 复制，再处理工作区副本。

## 准备原文

先确定用户提供的论文文件，优先使用本地或用户附件。仅在未提供原文且任务需要时查找原文；不能用摘要或检索片段冒充全文。读取项目操作规则，并通过工作区依赖工具取得 Python、Node、Poppler 和可用浏览器路径；命令示例中的运行时路径由当前环境提供，不写死在脚本中。

```text
python -B <skill>/scripts/paper_translate.py init --workspace <workspace> --pdf <source.pdf> --name <paper-name> --render --poppler-bin <poppler-bin>
```

`init` 复制原文、按页提取文本及 PDF 原有 URL、记录哈希并初始化数据文件。`--render` 可选；公式和图像裁切需要先渲染页面。已有任务继续使用原数据，不重新初始化。

提取文本只是阅读辅助。检查原文页面，确认单栏、双栏、跨栏标题、跨页段落、脚注及参考文献的阅读顺序。不要套用固定双栏拼接，也不要按 PDF 链接出现次序猜测文献归属。稀少或无可提取文字的页面需要 OCR 或逐页视觉阅读；在取得内容前不得宣布全文已译。

## 翻译与论文配置

开始写数据前，读取 [references/data-format.md](references/data-format.md)。在任务目录中维护 `paper.json` 与 `records.json`：

- 根据原文清点章节、段落、公式、图表、脚注和文献，为对应条目建立稳定 ID 与 `expected_ids` 清单。该清单来自原文检查，不能仅从已完成译文反推完整性。
- 用 Codex 翻译正文，逐条填写 `source` 与 `target`。脚本不调用翻译 API，不需要密钥，也不会自行生成译文。
- 为正文段落和图注填写 `alignment` 句子映射，逐一核对实际语义对应后设置 `reviewed: true`。英文一句被拆成中文多句或多句合并时，可使用必要分句或一对多映射；不能按句号数量、相同索引或等比例猜测。保留全部原始文字和空白。仅有一侧的译者补充说明明确列为 unpaired，不编造另一侧的对应句子。
- 英文只修正已核对的换行和提取错误；不要全局删除连字符或改动技术表述。跨页段落可合并，并列出全部来源页码。
- 统一本篇论文的术语和缩略语；保存到 `glossary`。不同论文可有不同译法，不固定沿用通信领域词表。
- 公式及正文、表格中的数学记号使用正常数学排版：下标在下方，上标在上方，希腊字母显示为对应符号，分式、根号、矩阵和重音按原文保留。对照原页转写 LaTeX；编号公式填写 `equations`，正文及表格单元格填写经过核对的 `math` 注释，格式见数据说明。保留原始文字及句子映射，避免用 `_`、`^` 等提取记法直接充当最终显示，也不要靠全局替换猜测变量含义。无法核实的符号标明具体疑点。
- HTML 构建脚本把已核对的 LaTeX 转成浏览器原生 MathML，自包含且离线可读；Markdown 使用行内 `$…$` 和独立 `$$…$$` 公式。原公式裁切图与提取文本保留在可展开的核对区。公式不需杜撰中文解释；确有帮助的补充说明写在 `translator_note`，与原文分开。
- 图注、表题、表格各单元格和重要图内文字应译出或提供对应说明。裁切坐标用当前页宽高的比例，检查上下标、编号、坐标轴和边缘标签完整。
- 参考文献保留编号、作者、刊物、版本、年份、页码和原链接；题名可翻译。参考文献数量和编号规则由本篇论文决定，不要求始终从 1 连续编号。
- 正文译文与作者单位、脚注、附录等都依用户请求范围处理。全文任务不得静默省略这些内容。

缺失原文、OCR 不清或技术含义存在歧义时，标明具体位置并继续独立部分。必要时输出明确标记的草稿；不得编造文本或把部分翻译当作完整交付。

## 构建与核对

逐项完成编辑核对后，在 `paper.json.review` 中填写实际核对结果。结构检查不能证明语义正确，禁止仅因脚本通过就勾选全部编辑核对项。

```text
python -B <skill>/scripts/paper_translate.py check --job <job>
python -B <skill>/scripts/paper_translate.py build --job <job>
```

`check` 检查 ID 清单、源页码、表格宽度、图片、原文哈希和编辑核对状态，并提示部分数值或引文差异。逐条审阅警告，允许已核实的格式差异。`build` 将最终 HTML 和 Markdown 写到工作区根目录；未通过核对时不能生成正式版。需要预览未完成翻译时加 `--draft`，输出带草稿标识。覆盖原成果需有本次任务授权，再加 `--overwrite`。

检查自包含 HTML 的图片加载、长公式、目录、双向句子选区联动与桌面和手机排版。在至少含两句的段落中选取一句的一部分，确认仅对应句子高亮；移动到另一句和跨句选择时核对高亮变化。可用以下通用检查脚本，它会输出审计与原图/表截图；打开截图进行视觉检查，修正后重建。图像裁切边缘必须额外与原页对比。

```text
node <skill>/scripts/qa_reader.cjs --workspace <workspace> --html <result.html> --out <job>/qa --playwright <runtime-playwright-package> --browser <browser-executable>
```

额外核对公式的上下标、希腊字母、分式及矢量字体，检查公式内选择文字仍只联动对应句子；长公式可在公式区域横向滚动，不能撑宽整页。数学转换器已随技能附带，无需额外安装 TeX、联网加载公式脚本或调用外部公式服务。

没有可用渲染依赖时保留文本与数据，明确报告未验证的排版范围；不得无授权安装程序。扫描件 OCR、Word/PDF 排版和外部翻译服务是条件需求，不是每次都强制增加的步骤。

交付时链接正式结果，说明内容范围及实际尚存缺口。不要交付缓存或把自动结构核对描述成翻译准确性认证。

## 维护脚本

修改本技能脚本或模板后，运行 `scripts/smoke_test.py --workspace <test-workspace> --poppler-bin <poppler-bin>` 验证构建、草稿及路径保护，再运行阅读器检查。普通新论文只替换数据，不重复改代码或运行开发测试。
