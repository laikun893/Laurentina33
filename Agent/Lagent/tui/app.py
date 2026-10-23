"""TUI 界面层（Textual）。

这是 Agent 的一个前端实现。它只负责：
- 把用户输入交给 core.Agent；
- 消费 core.Agent 产出的事件并渲染到界面。

不含任何业务逻辑，因此将来可以在此基础上并行开发 Web / Desktop 等其它前端。
"""

from textual import on, work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, RichLog

from core.agent import Agent
from core.events import AssistantMessage, ErrorOccurred, ToolCall, UserMessage


class AgentChatApp(App):
    """基于 Textual 的聊天式 TUI。"""

    TITLE = "Lagent · AI 文件操作助手"
    SUB_TITLE = "core + tui 分层示例"

    CSS = """
    #chat-log {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
    }
    """

    def __init__(self, agent: Agent):
        super().__init__()
        self.agent = agent
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
        yield Input(placeholder="请输入提示词，回车发送（Ctrl+C 退出）", id="prompt-input")
        yield Footer()

    def on_mount(self) -> None:
        self._log().write("你好，我是 AI 助手。输入提示词开始对话。")

    @on(Input.Submitted, "#prompt-input")
    def handle_input(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt:
            return
        event.input.value = ""
        self.run_prompt(prompt)

    @work
    async def run_prompt(self, prompt: str) -> None:
        if self._busy:
            self._log().write("[dim]（上一条仍在处理中，请稍候）[/dim]")
            return

        self._busy = True
        try:
            async for event in self.agent.chat(prompt):
                if isinstance(event, UserMessage):
                    self._log().write(f"[bold cyan]你：[/bold cyan] {event.content}")
                elif isinstance(event, ToolCall):
                    self._log().write(
                        f"[bold yellow][调用工具 {event.name}][/bold yellow]\n{event.result}"
                    )
                elif isinstance(event, AssistantMessage):
                    self._log().write(f"[bold green]助手：[/bold green] {event.content}")
                elif isinstance(event, ErrorOccurred):
                    self._log().write(f"[bold red]错误：[/bold red] {event.message}")
        finally:
            self._busy = False

    def _log(self) -> RichLog:
        return self.query_one("#chat-log", RichLog)
