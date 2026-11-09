---
name: officecli
description: 操作 Office 文档（.docx/.xlsx/.pptx）的本地 CLI 工具，无需安装 Office 或其它依赖；当用户需要创建、读取、编辑、查询或校验 Word/Excel/PowerPoint 文档时使用。
---

# officecli — Office 文档操作 CLI

`officecli` 是一个 AI 友好的 Office 文档命令行工具（单二进制、无依赖、无需安装 Office），
支持 `.docx`（Word）、`.xlsx`（Excel）、`.pptx`（PowerPoint）的创建、读取、DOM 编辑与原始 XML 操作。

## 如何调用（重要）

本技能不自带任何 Lagent 工具，所有操作都必须通过 **`RunCil`** 工具执行本目录下的二进制文件：

- `command`：`E:/github/Agent/office/.agents/.skills/officecli/bin/officecli.exe`（office 技能根目录，见 `config.ini` 的 `skills_root`）
- `args`：参数列表，**逐项传入**，不要拼接成一条 shell 字符串（`RunCil` 不支持管道/重定向）

```text
RunCil(command="E:/github/Agent/office/.agents/.skills/officecli/bin/officecli.exe", args=["create", "report.docx"])
RunCil(command="E:/github/Agent/office/.agents/.skills/officecli/bin/officecli.exe", args=["get", "report.docx", "/body/p[1]", "--json"])
```

注意：`RunCil` 输出会被截断到约 4KB，读取长文档时请用 `view text --max-lines N` 或
`get <file> <path> --depth N` 控制输出范围。

## 核心命令速览

| 命令 | 作用 |
| --- | --- |
| `create <file>` | 按扩展名创建空白 .docx/.xlsx/.pptx |
| `view <file> <mode>` | 视图：`outline` / `stats` / `issues` / `text` / `annotated` / `html` |
| `get <file> <path> --depth N` | 按路径读取节点及其子节点（加 `--json` 结构化输出） |
| `query <file> <selector>` | CSS 风格选择器检索元素 |
| `set <file> <path> --prop k=v ...` | 修改节点属性 |
| `add <file> <parent> --type T --prop k=v` | 在父节点下新增元素（可 `--after`/`--before`） |
| `remove <file> <path>` | 删除元素 |
| `move` / `swap` | 移动 / 交换元素 |
| `dump <file> [<path>]` | 把文档序列化为可回放的 batch JSON |
| `batch <file> --commands '<json>'` | 一次执行多条操作 |
| `validate <file>` | 校验文档是否符合 OpenXML schema |
| `help <format> [<verb>] [<element>]` | 查询元素/属性 schema（不确定时先查） |

格式别名：`word`→`docx`，`excel`→`xlsx`，`ppt`/`powerpoint`→`pptx`。

## 工作原则

1. **层级优先 L1（读）→ L2（DOM 编辑）→ L3（raw XML）**，能用高层就用高层。
2. **不确定属性名、值格式或语法时，先 `help` 再动手，不要猜**：
   `help docx paragraph` 看元素全部属性；`help docx set paragraph` 看 set 可用属性。
3. **多步工作流优先用 `--json`** 拿结构化结果，便于解析路径。
4. 元素带稳定 ID 时用 `@id=` / `@paraId=` 形式寻址（位置索引在增删后会漂移）。

## 路径与属性规则

- 路径 **1-based**（XPath 约定）：`/body/p[3]` = 第 3 段；`/slide[1]` = 第 1 页。
- `--index` **0-based**（数组约定）；**例外**：Excel 的 `add --type row/col` 的 `--index` 是 1-based。
- 所有属性都通过 `--prop key=value` 传入，不要用 `--name foo` 这种独立参数。
- 值格式：颜色 `FF0000` / `red` / `rgb(255,0,0)`；间距/尺寸带单位 `12pt` / `2.54cm` / `1in`。
- 文本换行：`--prop text="..."` 里用 `\n`（新段）或 `\v`（段内换行）。

## 常见陷阱

- 路径含 `[ ]` 必须用引号包起来（shell 会展开方括号）。
- PPT 里 `shape[1]` 通常是标题占位符，正文形状从 `shape[2]` 起；名字索引用 `@name=`。
- 修改文件前，先在 PowerPoint/WPS/Word 里关闭该文件。
- 路径结尾无匹配、无匹配 `find` 等属于静默成功，必要时用 `--json` 的 `matched`/`success` 字段确认。
- 改完记得 `validate` 或 `view issues` 自检。

## 快速示例

```text
# 创建并写入一个 Word 段落
create demo.docx
add demo.docx /body --type paragraph --prop text="Executive Summary" --prop style=Heading1

# 读取 Excel 单元格 / 写入值
get data.xlsx /Sheet1/A1 --json
set data.xlsx /Sheet1/A1 --prop value="Name" --prop bold=true

# 创建 PPT 并加一页 + 文本框
create slides.pptx
add slides.pptx / --type slide --prop title="Q4 Report"
add slides.pptx /slide[1] --type shape --prop text="Revenue grew 25%" --prop x=2cm --prop y=5cm
```
