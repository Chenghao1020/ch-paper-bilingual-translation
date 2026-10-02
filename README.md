# ch-paper-bilingual-translation

用于 Codex 的通用论文中英对照翻译技能。复用 PDF 提取、对照排版、句子高亮和质量检查代码，每篇论文的内容使用独立 JSON 数据保存。

## 翻译分工

英文到中文的翻译由 AI（Codex）完成：理解原文、翻译正文与图表文字、统一术语并核对中英句子对应关系。程序负责提取 PDF、保留原图、检查数据结构以及生成阅读文件，不调用额外的翻译 API，也不需要翻译服务密钥。

自动检查不能证明译文语义准确；专业术语、公式解释和句子对应关系仍需核对。

## 功能

- 逐段中英对照，保留章节、来源页码、公式、图表和参考文献。
- 自包含 HTML 阅读版与可编辑 Markdown 对照文本。
- 在任一侧选中一句中的文字，只高亮另一侧对应句子；跨句选择支持多个对应句子。
- 通过经过核对的句子或必要分句映射处理拆句、合句和语序变化，不按句号数量猜测。
- 目录、检索、语言切换及手机布局。
- 原文哈希、条目清单、图片、表格结构及部分数值和引用检查。

## 安装到个人 Codex 技能目录

将本仓库放到 `$CODEX_HOME/skills/ch-paper-bilingual-translation`；未设置 `CODEX_HOME` 时使用 `~/.codex/skills/ch-paper-bilingual-translation`。目录根部应包含 `SKILL.md`。

仓库为私有时，需要当前 GitHub 账号具有访问权限。已有同名技能目录时先检查已有内容，不直接覆盖。

```bash
git clone https://github.com/Chenghao1020/ch-paper-bilingual-translation.git ~/.codex/skills/ch-paper-bilingual-translation
```

安装后提供论文，并在 Codex 中说：

> 使用 $ch-paper-bilingual-translation 翻译这篇论文，生成全文逐段中英对照文本。

如当前聊天未发现新技能，可在新聊天中调用。

## 运行依赖

优先使用 Codex 工作区提供的运行时；脚本不固定依赖本机路径。

- Python：`pypdf`、`Pillow`；开发用合成 PDF 测试另外使用 `reportlab`。
- Poppler：需要页面渲染或裁切时使用 `pdftoppm`。
- 阅读器检查：Node.js、Playwright 包，以及可用的 Chromium、Chrome 或 Edge 浏览器程序。

已有运行时可直接使用。确需自行配置时，Python 依赖见 `requirements.txt`，其余运行时单独配置。

## 工作流程

详见 [SKILL.md](SKILL.md) 与 [每篇论文的数据格式](references/data-format.md)。

```text
python -B scripts/paper_translate.py init --workspace <workspace> --pdf <paper.pdf> --name <paper-name>
python -B scripts/paper_translate.py check --job <job>
python -B scripts/paper_translate.py build --job <job>
```

`init` 后由 Codex 阅读原文、填写译文与句子映射并完成核对；程序不会自动翻译。生成任务的数据、缓存和结果均放在实际工作区，不写入技能目录。默认成果在工作区根目录，中间数据在 `analysis/paper-translations/<paper-name>`。

## 检查与开发

```text
python -B scripts/smoke_test.py --workspace <fresh-test-workspace> --poppler-bin <poppler-bin>
node scripts/qa_reader.cjs --workspace <workspace> --html <reader.html> --out <qa-output> --playwright <playwright-package> --browser <browser-executable>
```

开发检查覆盖构建、路径保护、草稿、缺失/损坏句子映射、双向句子高亮、同段换句、跨句选择、语序变化、一对多对应、鼠标拖选、键盘扩选和手机布局。生成截图仍需进行视觉检查。

本仓库仅包含通用技能及说明；论文原文和具体论文的译文数据由各自工作区管理。
