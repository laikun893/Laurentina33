# Lagent — AI 文件操作助手（core + tui 分层架构）

基于 OpenAI 兼容接口（示例配置为 **DeepSeek**）的 AI 助手，通过 **Function Calling / Tools**
机制让大模型操作本机文件系统。本项目是对 `practice02/chat_fileops.py` 的重构，
将 **业务核心（core）** 与 **界面（tui）** 分离，并按软件工程的分层、模块化规范组织代码，
为将来扩展 Web / Desktop 等其它前端预留了清晰的接入点。

## 目录结构

```
Lagent/
├── main.py               # 程序入口：组装 core 并启动 TUI
├── config.ini            # 模型服务配置（已被 .gitignore 忽略）
├── config.ini.example    # 配置模板
├── requirements.txt      # 依赖清单
├── core/                 # 业务核心（与 UI 无关）
│   ├── constants.py      # 基础常量
│   ├── config.py         # 配置层
│   ├── llm.py            # 模型客户端封装层
│   ├── safety.py         # 安全与校验辅助层
│   ├── events.py         # Agent <-> UI 事件契约
│   ├── agent.py          # Agent 运行时编排层
│   └── tools/            # 工具子包
│       ├── schemas.py    # 工具声明（JSON Schema）
│       └── service.py    # 工具实现与分发
└── tui/                  # Textual 前端
    └── app.py            # TUI 应用
```

## 分层设计

自下而上，严格遵循「上层依赖下层、下层不感知上层」的原则：

| 层 | 文件 | 职责 |
| --- | --- | --- |
| 基础常量 | `core/constants.py` | 体积上限等基础常量 |
| 配置层 | `core/config.py` | 读取并校验 `config.ini`，产出 `Config` |
| 模型封装层 | `core/llm.py` | 屏蔽模型供应商差异，暴露统一 `create` 接口 |
| 安全辅助层 | `core/safety.py` | 路径沙箱、纯文本判定、命令执行 |
| 工具层 | `core/tools/` | 工具声明（`schemas.py`）与实现分发（`service.py`） |
| 事件契约 | `core/events.py` | `Agent` 与 UI 之间的数据传输对象 |
| 运行时编排 | `core/agent.py` | 管理对话历史，编排「模型 ⇄ 工具」多轮调用 |
| 界面层 | `tui/` | 消费事件并渲染，不含业务逻辑 |

### core 与 UI 解耦的关键：事件契约

`core.Agent.chat(prompt)` 是一个**异步生成器**，会依次产出以下事件：

```python
UserMessage(content)      # 用户输入
ToolCall(name, args, result)  # 一次工具调用及结果
AssistantMessage(content) # 最终回答
ErrorOccurred(message)    # 错误
```

任何前端只要 `async for event in agent.chat(prompt)` 并按类型渲染即可，
完全不接触模型调用、工具分发等业务细节。

## 安装与运行

```bash
pip install -r requirements.txt
```

1. 复制 `config.ini.example` 为 `config.ini`，填入你的 `api_key`。
2. 在希望被操作的目录下启动：

```bash
python main.py
```

- 输入提示词后回车发送；`Ctrl+C` 退出。
- 沙箱根目录为启动时的当前工作目录，所有文件操作都被限制在其中。

## 如何扩展其它前端（Web / Desktop）

core 已经与界面完全解耦，新增前端只需：

1. 复用 `core.Agent`（见 `main.py` 中的 `build_agent` 组装方式）。
2. 消费 `core.events` 中的事件渲染你自己的 UI。

例如一个最简前端骨架：

```python
from core import Agent

async def render(agent: Agent, prompt: str):
    async for event in agent.chat(prompt):
        # 按 event 类型渲染到你的 Web / Desktop 界面
        ...
```

## 安全与局限

- 删除操作不可撤销，请在测试目录中使用。
- `api_key` 以明文存于 `config.ini`，仅适合本地学习使用（已被 `.gitignore` 忽略）。
- 工具底层依赖 Windows 命令（`cmd` 的 `dir` / `mkdir` / `del` / `move` 等），当前仅支持 Windows。
