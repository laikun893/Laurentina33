<!--
================================================================================
README for chat_fileops.py -- AI file-operation assistant
================================================================================

This document body is written in Chinese. The ASCII block above and below is
intentional padding: some tools sample only the first 1024 bytes of a file to
decide whether it is text or binary, and a sample that cuts a multibyte CJK
character in half can be mistaken for a UTF-8 decode error. Keeping the leading
bytes ASCII-only avoids that false positive. Keep this header ASCII-only.

--------------------------------------------------------------------------------
SECTION MAP
--------------------------------------------------------------------------------

  1. Features
  2. Requirements and installation  (includes the config.ini format)
  3. Usage
  4. Architecture
       4.1 Config layer
       4.2 Global constants
       4.3 Safety and validation helpers
       4.4 Tool implementations
       4.5 Dispatcher
       4.6 Agent main loop
  5. Caveats and limitations
  6. File list

--------------------------------------------------------------------------------
TOOL NAME INDEX
--------------------------------------------------------------------------------

  getCurrentDir   -> get_current_dir()    returns os.getcwd()
  getCurrentTime  -> get_current_time()   local date, time, weekday, ISO string
  listDir         -> list_dir()           entries tagged [DIR] / [FILE]
  getFileType     -> get_file_type()      MIME type + extension via mimetypes
  readFile        -> read_file()          size cap + text check, UTF-8 read
  createFile      -> create_file()        makedirs + write, refuses overwrite
  editFile        -> edit_file()          overwrite or append mode
  createDir       -> create_dir()         os.makedirs, multi-level
  deleteDir       -> delete_dir()         shutil.rmtree, recursive
  deleteFile      -> delete_file()        os.remove
  renamePath      -> rename_path()        os.rename, target must not exist

--------------------------------------------------------------------------------
PIPELINE OVERVIEW
--------------------------------------------------------------------------------

  config.ini --> configparser --> OpenAI client
                             --> WORK_ROOT / MAX_TEXT_SIZE
                             --> TOOLS schema list
                             --> helpers (_safe_path, _is_text_file)
                             --> tool implementations
                             --> run_tool dispatcher
                             --> agent loop (input -> model -> tools -> answer)

--------------------------------------------------------------------------------
END OF ASCII HEADER
================================================================================
-->

# chat_fileops.py — AI 文件操作助手

一个基于 OpenAI 兼容接口（示例配置为 **DeepSeek**）的命令行 AI 助手，通过 **Function Calling / Tools** 机制让大模型直接操作本机文件系统：查看目录、获取当前时间、读文件、创建/编辑/删除文件与目录、重命名等。

架构图见 [`architecture.mmd`](architecture.mmd)（Mermaid 格式，可在支持 Mermaid 的编辑器 / GitHub / VS Code 插件中直接预览）。

---

## 1. 功能特性

- **配置驱动**：从同目录 `config.ini` 读取 `base_url` / `model` / `api_key`，缺失即退出并给出提示。
- **11 个工具**：10 个文件系统工具 + 1 个时间工具，由模型根据用户意图自动选择调用。
- **安全沙箱**：所有路径操作都被限制在工作根目录（启动时的 `os.getcwd()`）内，防止路径越界。
- **纯文本保护**：读取/写入前检查文件是否为纯文本（空字节 + 增量 UTF-8 解码检测），并限制最大读取体积 1 MB。
- **本地时间获取**：`getCurrentTime` 返回本机日期、时间与星期，避免模型凭训练数据臆测「今天」。
- **多轮工具调用**：支持模型连续多次调用工具，直到给出最终自然语言回答。
- **异常兜底**：API 调用异常时打印错误并回滚本轮用户消息，不会污染对话历史。

---

## 2. 运行环境与安装

```bash
pip install openai
```

> Python 3.8+。仅依赖第三方库 `openai`，其余均为标准库。

### 配置文件 `config.ini`

必须与本脚本位于同一目录：

```ini
[default]
base_url = https://api.deepseek.com
model = deepseek-chat
api_key = sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

> ⚠️ 请勿将真实 `api_key` 提交到公开仓库，建议改用环境变量或本地私有配置文件。

---

## 3. 使用方法

```bash
python chat_fileops.py
```

交互示例：

```
你好，我是AI助手
请输入提示词：看看当前目录有什么文件
---
[调用工具 listDir] -> 目录内容：
[目录] __pycache__
[文件] chat.py
...
```

一个需要「当前日期」的场景：

```
请输入提示词：创建文件夹 12，并在其中创建 11.txt，内容为今天的日期
[调用工具 createDir] -> 已创建目录：.../12
[调用工具 getCurrentTime] -> 当前日期：2025-06-17
当前时间：14:03:22
...
[调用工具 createFile] -> 已创建文件：.../12/11.txt
```

- 输入空行会被忽略。
- `Ctrl+C` 或 `Ctrl+D` 退出。

---

## 4. 代码架构

```
(1) 配置加载 → (2) 全局常量 / TOOLS 声明 → (3) 安全校验 helpers
                                                 ↓
(6) Agent 主循环 ← (5) 工具分发 run_tool ← (4) 11 个工具实现函数
                                                 ↓
                                        (7) 外部依赖（DeepSeek API + 标准库）
```

### 4.1 配置层

| 项 | 说明 |
| --- | --- |
| `config_path` | 基于脚本自身路径定位 `config.ini`，与启动目录无关 |
| 校验 | 文件不存在 / 缺少 `[default]` / 缺少字段 → `sys.exit(错误信息)` |
| `client` | `OpenAI(base_url=..., api_key=...)`，可对接任意兼容 OpenAI 协议的服务 |

### 4.2 全局常量

| 常量 | 值 | 用途 |
| --- | --- | --- |
| `WORK_ROOT` | `os.getcwd()` | 沙箱根目录，所有路径必须位于其内 |
| `MAX_TEXT_SIZE` | `1024 * 1024`（1 MB） | `readFile` 的单文件体积上限 |

### 4.3 安全与校验 helpers

- **`_safe_path(path) -> (abs_path, err)`**
  将路径 `os.path.abspath` 归一化后用 `os.path.commonpath` 判断是否仍位于 `WORK_ROOT` 下；越界直接返回错误字符串。空路径同样被拒绝。
- **`_is_text_file(path) -> (bool, err)`**
  读取前 1024 字节：包含 `\x00` 判定为二进制；随后用 `codecs` 的**增量 UTF-8 解码器**（`final=False`）检测可解码性。

  > 这里必须用增量解码器：采样固定 1024 字节很可能把一个多字节汉字从中间截断，此时尾部抛出的 `UnicodeDecodeError` 并不代表文件是二进制。直接 `head.decode("utf-8")` 会把大量长中文文本（如 Mermaid 架构图、README）误判为二进制并拒绝读写。

### 4.4 工具实现（与 `TOOLS` 声明的 function name 一一对应）

| 工具名 | 实现函数 | 关键行为 |
| --- | --- | --- |
| `getCurrentDir` | `get_current_dir()` | 返回 `os.getcwd()`，无参数 |
| `getCurrentTime` | `get_current_time()` | `datetime.datetime.now()`，返回日期 / 时间 / 星期 / 带时区 ISO，无参数 |
| `listDir` | `list_dir(path=".")` | 排序后逐项标注 `[目录]` / `[文件]` |
| `getFileType` | `get_file_type(path)` | `mimetypes.guess_type` 推断 MIME + 扩展名 |
| `readFile` | `read_file(path)` | 体积限制 + 纯文本校验后按 UTF-8 读取 |
| `createFile` | `create_file(directory, filename, content="")` | 校验文件名不含路径分隔符、目标不存在，自动 `makedirs` |
| `editFile` | `edit_file(path, content, mode="overwrite")` | `mode` 仅接受 `overwrite` / `append`，写前做纯文本校验 |
| `createDir` | `create_dir(path)` | `os.makedirs(exist_ok=True)`，支持多级 |
| `deleteDir` | `delete_dir(path)` | `shutil.rmtree` 递归删除 |
| `deleteFile` | `delete_file(path)` | `os.remove` |
| `renamePath` | `rename_path(old_path, new_path)` | 要求原路径存在且目标不存在 |

所有实现统一返回**字符串**：成功为人类可读提示，失败为 `错误：...` 前缀文本，直接作为 `tool` 消息回灌给模型。

### 4.5 分发器

`run_tool(name, arguments)`：按 function name 逐一 `if` 路由，并用 `arguments.get(key, 默认值)` 提供缺省参数；未知工具名返回 `未知的工具：{name}`。

### 4.6 Agent 主循环

1. `input()` 读取提示词 → 追加为 `user` 消息。
2. 调用 `client.chat.completions.create(model, messages, tools=TOOLS)`。
3. 若返回 `message.tool_calls`：
   - 先以 `role=assistant`（含 `tool_calls` 字段）记录；
   - 逐个 `json.loads(arguments)` 执行 `run_tool`，打印结果；
   - 以 `role=tool` + `tool_call_id` 追加结果；
   - **`continue`** 重新请求模型（形成 agent 内循环）。
4. 否则打印最终 `content`，追加 `assistant` 消息并 `break` 等待下一次用户输入。
5. 任何 `Exception`：打印 `错误：API 调用失败：...`，并 `messages.pop()` 回滚本轮用户消息。

---

## 5. 注意事项与局限

- **删除不可撤销**：`deleteDir` 使用 `shutil.rmtree`，且提示词一旦被模型误判即会真实删除文件，建议在测试目录中使用。
- **沙箱依赖启动目录**：`WORK_ROOT` 取自 `os.getcwd()`，建议始终在希望被操作的目录内启动脚本。
- **无对话历史裁剪**：`messages` 会随轮次无限增长，长时间使用可能触及模型上下文上限，可考虑加入历史裁剪。
- **API Key 明文配置**：当前从 `config.ini` 明文读取，仅适合本地学习使用。
- **时间取自运行机器**：`getCurrentTime` 返回的是运行脚本那台电脑的本地时间，不受模型影响；若机器时区不正确，结果也会随之偏差。

---

## 6. 文件清单

| 文件 | 说明 |
| --- | --- |
| `chat_fileops.py` | 主程序：配置加载、工具声明与实现、agent 主循环 |
| `config.ini` | 模型服务配置（`base_url` / `model` / `api_key`） |
| `architecture.mmd` | 代码架构图（Mermaid 纯文本） |
| `README.md` | 本文档 |
