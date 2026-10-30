"""TUI 界面层（Textual）。

这是 Agent 的一个前端实现，参考 opencode 的终端布局：
    ┌ topbar：品牌 + 模型 + 工作目录
    │ 对话区：用户消息、Markdown 回答、紧凑的工具调用行
    │ 输入框：圆角边框 + 行内命令提示
    └ 状态栏：运行状态（含 spinner）+ 工具数 + 累计 token

本层只负责把用户输入交给 core.Agent，并消费 Agent 产出的事件渲染，
不含任何业务逻辑，因此可在此之外并行开发 Web / Desktop 等其它前端。
"""

from rich.markdown import Markdown as RichMarkdown
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Input, RichLog, Static

from core.agent import Agent
from core.events import (
    AssistantMessage,
    ErrorOccurred,
    ToolCall,
    UsageUpdate,
    UserMessage,
)

# ----------------------------------------------------------------------
# 视觉常量（与 CSS 中的色值保持一致）
# ----------------------------------------------------------------------
BRAND = "#f5a97f"   # 品牌色（暖橙）
ACCENT = "#78b4f2"  # 强调色（蓝）
MUTED = "#6e7683"   # 次要文本
RESULT = "#8b95a5"  # 工具输出
SUCCESS = "#9ece6a"
ERROR = "#f7768e"

# 工具名 -> 简短动作标签，让工具行更像 opencode 的紧凑记录
TOOL_LABELS = {
    "getCurrentDir": "cwd",
    "getCurrentTime": "time",
    "listDir": "ls",
    "getFileType": "file",
    "readFile": "read",
    "createFile": "create",
    "editFile": "edit",
    "createDir": "mkdir",
    "deleteDir": "rmdir",
    "deleteFile": "rm",
    "renamePath": "move",
    "RunCil": "run",
    "execCommand": "exec",
    "fetchweb": "fetch",
    "searchWeb": "search",
    "loadSkill": "skill",
}


def _clip(text: str, limit: int) -> str:
    """超出长度则截断并追加省略号。"""
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


class AgentChatApp(App):
    """基于 Textual 的聊天式 TUI。"""

    TITLE = "Lagent · AI 文件操作助手"
    SUB_TITLE = "core + tui 分层示例"

    BINDINGS = [
        Binding("ctrl+c", "quit", "退出", priority=True),
        Binding("ctrl+l", "clear", "清屏"),
    ]

    CSS = """
    Screen {
        background: #0b0e13;
        color: #c9d1d9;
    }

    /* ---------- 顶部信息栏 ---------- */
    #topbar {
        height: 1;
        width: 100%;
        background: #10141b;
        padding: 0 1;
    }
    #brand {
        width: auto;
        height: 1;
        color: #f5a97f;
        text-style: bold;
    }
    #top-model {
        width: auto;
        height: 1;
        color: #78b4f2;
        text-style: bold;
        padding: 0 1;
    }
    #top-dir {
        width: 1fr;
        height: 1;
        color: #6e7683;
        text-align: right;
    }

    /* ---------- 对话区 ---------- */
    #chat-log {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        background: #0b0e13;
        overflow-y: auto;
        scrollbar-background: #10141b;
        scrollbar-color: #2a3140;
        scrollbar-color-hover: #78b4f2;
        scrollbar-color-active: #78b4f2;
    }

    /* ---------- 输入区 ---------- */
    #prompt-input {
        margin: 0 1;
        height: 3;
        background: #14181f;
        border: round #2a3140;
        padding: 0 1;
    }
    #prompt-input:focus {
        border: round #78b4f2;
    }
    #prompt-input > .input--placeholder {
        color: #6e7683;
    }
    #input-hint {
        height: 1;
        margin: 0 2;
        color: #6e7683;
    }

    /* ---------- 状态栏 ---------- */
    #status-bar {
        height: 1;
        width: 100%;
        background: #10141b;
        padding: 0 1;
    }
    """

    SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, agent: Agent):
        super().__init__()
        self.agent = agent
        self._busy = False
        self._timer = None
        self._spin_frame = 0
        self._spin_label = "思考中"
        self._status_frame = "●"
        self._status_state = "就绪"
        self._status_color = SUCCESS

    # ------------------------------------------------------------------
    # 布局
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("⬢ LAGENT", id="brand")
            yield Static(self.agent.model, id="top-model")
            yield Static(self.agent.work_root, id="top-dir")
        yield RichLog(
            id="chat-log",
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
        )
        yield Input(placeholder="询问或输入命令…（/help 查看命令）", id="prompt-input")
        yield Static(
            "Enter 发送   ·   /help 命令   ·   Ctrl+L 清屏   ·   Ctrl+C 退出",
            id="input-hint",
        )
        yield Static(id="status-bar")

    def on_mount(self) -> None:
        self._write_welcome()
        self._render_status()
        self.query_one("#prompt-input", Input).focus()

    # ------------------------------------------------------------------
    # 渲染：欢迎语 / 消息 / 工具
    # ------------------------------------------------------------------
    def _write_welcome(self) -> None:
        self._log().write(
            Text.assemble(
                ("⬢ ", f"bold {BRAND}"),
                ("Lagent", f"bold {BRAND}"),
                ("   AI 文件操作助手\n\n", MUTED),
                ("工作目录  ", MUTED),
                (self.agent.work_root, ACCENT),
                ("\n", ""),
                ("模型      ", MUTED),
                (self.agent.model, ACCENT),
                ("\n\n", ""),
                ("输入提示词开始对话，或输入 ", MUTED),
                ("/help", ACCENT),
                (" 查看可用命令。", MUTED),
            )
        )
        self._log().write(Text(""))

    def _write_user(self, content: str) -> None:
        body = content.replace("\n", "\n  ")
        self._log().write(
            Text.assemble(("▌ ", f"bold {ACCENT}"), (body, "bold #e6edf3"))
        )

    def _write_assistant(self, content: str) -> None:
        content = (content or "").strip()
        if not content:
            return
        self._log().write(RichMarkdown(content))
        self._log().write(Text(""))

    def _write_tool(self, event: ToolCall) -> None:
        label = TOOL_LABELS.get(event.name, event.name)
        head = Text.assemble(("  ⏺ ", MUTED), (label, f"bold #a6b0c0"))
        if event.arguments:
            head.append("  " + self._format_args(event.arguments), style=MUTED)
        self._log().write(head)
        self._log().write(self._format_result(event.result))
        self._log().write(Text(""))

    def _write_error(self, message: str) -> None:
        self._log().write(
            Text.assemble(("✗ 错误：", f"bold {ERROR}"), (message, ERROR))
        )
        self._log().write(Text(""))

    def _write_notice(self, message: str) -> None:
        self._log().write(Text.assemble(("· ", MUTED), (message, MUTED)))

    @staticmethod
    def _format_args(arguments: dict) -> str:
        parts = []
        for key, value in arguments.items():
            if isinstance(value, str):
                parts.append(f'{key}="{_clip(value, 40)}"')
            else:
                parts.append(f"{key}={value}")
        return _clip(", ".join(parts), 70)

    @staticmethod
    def _format_result(result: str) -> Text:
        raw = (result or "").strip()
        text = Text()
        if not raw:
            text.append("   └ （无输出）", style=MUTED)
            return text

        is_error = raw.startswith(("错误：", "错误:"))
        style = ERROR if is_error else RESULT
        lines = [line.rstrip() for line in raw.splitlines()]
        while lines and not lines[-1].strip():
            lines.pop()

        for index, line in enumerate(lines[:8]):
            if index:
                text.append("\n")
            prefix = "   └ " if index == 0 else "     "
            text.append(prefix, style=MUTED)
            text.append(_clip(line, 120) or " ", style=style)
        if len(lines) > 8:
            text.append(f"\n     … 其余 {len(lines) - 8} 行已省略", style=MUTED)
        return text

    # ------------------------------------------------------------------
    # 状态栏 / spinner
    # ------------------------------------------------------------------
    def _render_status(self) -> None:
        usage = self.agent.usage
        bar = Text()
        bar.append(f"{self._status_frame} ", style=self._status_color)
        bar.append(self._status_state, style=self._status_color)
        bar.append("    ", style="")
        bar.append(f"{self.agent.tool_count} 工具", style=MUTED)
        bar.append("   ·   ", style=MUTED)
        bar.append(f"{usage.total_tokens:,} tokens", style=ACCENT)
        bar.append("   ·   ", style=MUTED)
        bar.append(f"↑{usage.prompt_tokens:,} ↓{usage.completion_tokens:,}", style=MUTED)
        self.query_one("#status-bar", Static).update(bar)

    def _start_spinner(self, label: str = "思考中") -> None:
        self._busy = True
        self._spin_label = label
        self._spin_frame = 0
        self._status_color = BRAND
        if self._timer is not None:
            self._timer.stop()
        self._tick_spinner()
        self._timer = self.set_interval(0.1, self._tick_spinner)

    def _tick_spinner(self) -> None:
        frame = self.SPINNER[self._spin_frame % len(self.SPINNER)]
        self._spin_frame += 1
        self._status_frame = frame
        self._status_state = self._spin_label
        self._status_color = BRAND
        self._render_status()

    def _stop_spinner(self, state: str = "就绪", color: str = SUCCESS) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._busy = False
        self._status_frame = "●"
        self._status_state = state
        self._status_color = color
        self._render_status()

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    @on(Input.Submitted, "#prompt-input")
    def handle_input(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        event.input.value = ""
        if not prompt:
            return
        if prompt.startswith("/"):
            self._handle_command(prompt)
            return
        self.run_prompt(prompt)

    def action_clear(self) -> None:
        self._log().clear()
        self.agent.reset()
        self._write_welcome()
        self._render_status()

    def _handle_command(self, raw: str) -> None:
        cmd = raw[1:].strip().lower()
        if cmd in ("help", "?"):
            self._write_help()
        elif cmd in ("clear", "cls"):
            self.action_clear()
        elif cmd in ("model", "info"):
            self._log().write(
                Text.assemble(
                    ("模型      ", MUTED),
                    (self.agent.model, ACCENT),
                    ("\n", ""),
                    ("接口      ", MUTED),
                    (self.agent.base_url, ACCENT),
                    ("\n", ""),
                    ("工作目录  ", MUTED),
                    (self.agent.work_root, ACCENT),
                )
            )
        elif cmd == "tools":
            names = self.agent.tool_names
            self._write_notice(f"共 {len(names)} 个可用工具：")
            for name in names:
                self._log().write(
                    Text.assemble(
                        ("  · ", MUTED),
                        (TOOL_LABELS.get(name, name), ACCENT),
                        (f"  {name}", MUTED),
                    )
                )
        elif cmd in ("quit", "exit", "q"):
            self.exit()
        elif cmd:
            self._write_notice(f"未知命令：{raw}（输入 /help 查看可用命令）")

    def _write_help(self) -> None:
        self._log().write(
            RichMarkdown(
                "### 可用命令\n"
                "- `/help` — 显示本帮助\n"
                "- `/clear` — 清空对话与上下文，重置 token 统计\n"
                "- `/model` — 查看当前模型、接口与工作目录\n"
                "- `/tools` — 列出全部可用工具\n"
                "- `/quit` — 退出程序\n"
                "\n快捷键：`Ctrl+L` 清屏，`Ctrl+C` 退出。"
            )
        )
        self._log().write(Text(""))

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    @work
    async def run_prompt(self, prompt: str) -> None:
        if self._busy:
            self._write_notice("上一条仍在处理中，请稍候。")
            return

        self._start_spinner("思考中")
        failed = False
        try:
            async for event in self.agent.chat(prompt):
                if isinstance(event, UserMessage):
                    self._write_user(event.content)
                elif isinstance(event, UsageUpdate):
                    self._render_status()
                elif isinstance(event, ToolCall):
                    self._spin_label = f"调用 {TOOL_LABELS.get(event.name, event.name)}"
                    self._write_tool(event)
                elif isinstance(event, AssistantMessage):
                    self._write_assistant(event.content)
                elif isinstance(event, ErrorOccurred):
                    failed = True
                    self._write_error(event.message)
        finally:
            if failed:
                self._stop_spinner("出错", ERROR)
            else:
                self._stop_spinner()
            self.query_one("#prompt-input", Input).focus()

    def _log(self) -> RichLog:
        return self.query_one("#chat-log", RichLog)
