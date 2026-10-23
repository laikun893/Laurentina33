"""Agent 与 UI 之间的事件契约。

core.Agent 以异步生成器产出这些事件，任何前端（TUI / Web / Desktop）
只需消费事件并自行渲染，从而做到核心逻辑与界面完全解耦。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Usage:
    """一次或累计的 token 消耗统计。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass
class UsageUpdate:
    """每次模型调用后产出的累计消耗快照。"""

    usage: Usage


@dataclass
class UserMessage:
    """用户本轮输入的内容。"""

    content: str


@dataclass
class ToolCall:
    """一次工具调用的名称、入参与执行结果。"""

    name: str
    arguments: dict
    result: str


@dataclass
class AssistantMessage:
    """模型给出的最终自然语言回答。"""

    content: str


@dataclass
class ErrorOccurred:
    """本轮对话过程中出现的错误信息。"""

    message: str
