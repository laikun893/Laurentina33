"""Agent 运行时层。

职责：管理对话历史，编排「模型 -> 工具 -> 模型」的多轮调用，
并通过异步生成器向 UI 产出事件。本层只依赖 LLMClient 与 ToolService，
不依赖任何具体前端。
"""

import asyncio
import json
from typing import AsyncIterator, List

from .events import AssistantMessage, ErrorOccurred, ToolCall, Usage, UsageUpdate, UserMessage
from .llm import LLMClient
from .tools import ToolService

DEFAULT_SYSTEM_PROMPT = (
    "你是运行在用户本机上的文件操作助手。重要规则："
    "凡是涉及当前日期、时间、星期几的问题，必须调用 getCurrentTime 工具获取本机真实时间，"
    "严禁凭训练记忆或自身知识臆测任何时间信息。"
)


class Agent:
    """文件操作 AI 助手的核心编排器。"""

    def __init__(self, llm: LLMClient, tools: ToolService, tool_schemas,
                 system_prompt: str = DEFAULT_SYSTEM_PROMPT):
        self._llm = llm
        self._tools = tools
        self._tool_schemas = tool_schemas
        self._system_prompt = system_prompt
        self.messages: List[dict] = self._build_history()
        self._usage = Usage()

    @property
    def usage(self) -> Usage:
        """累计 token 消耗。"""
        return self._usage

    @property
    def model(self) -> str:
        return self._llm.model

    @property
    def base_url(self) -> str:
        return self._llm.base_url

    @property
    def work_root(self) -> str:
        return self._tools.work_root

    def reset(self):
        """清空对话历史与累计消耗（保留系统提示词）。"""
        self.messages = self._build_history()
        self._usage = Usage()

    def _build_history(self) -> List[dict]:
        if self._system_prompt:
            return [{"role": "system", "content": self._system_prompt}]
        return []

    @staticmethod
    def _extract_usage(response) -> Usage:
        """从模型响应中提取 token 消耗（兼容 usage 缺失的供应商）。"""
        u = getattr(response, "usage", None)
        if not u:
            return Usage()
        return Usage(
            prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(u, "completion_tokens", 0) or 0,
            total_tokens=getattr(u, "total_tokens", 0) or 0,
        )

    async def chat(self, prompt: str) -> AsyncIterator[object]:
        """处理一轮用户输入，逐步产出事件供 UI 消费。

        阻塞的模型请求通过 asyncio.to_thread 放入线程池执行，
        保证事件循环不被阻塞（TUI / Web 等异步前端均可流畅运行）。
        """
        prompt = (prompt or "").strip()
        if not prompt:
            return

        yield UserMessage(prompt)
        self.messages.append({"role": "user", "content": prompt})
        base_len = len(self.messages) - 1

        try:
            while True:
                response = await asyncio.to_thread(
                    self._llm.create, self.messages, self._tool_schemas
                )
                self._usage = self._usage + self._extract_usage(response)
                yield UsageUpdate(self._usage)
                message = response.choices[0].message

                if message.tool_calls:
                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": message.content or "",
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in message.tool_calls
                            ],
                        }
                    )

                    for tc in message.tool_calls:
                        args = json.loads(tc.function.arguments or "{}")
                        result = self._tools.dispatch(tc.function.name, args)
                        yield ToolCall(tc.function.name, args, result)
                        self.messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": result,
                            }
                        )
                    continue

                content = message.content or ""
                self.messages.append({"role": "assistant", "content": content})
                yield AssistantMessage(content)
                break
        except Exception as e:
            # 回滚本轮产生的消息，避免污染后续对话历史。
            del self.messages[base_len:]
            yield ErrorOccurred(f"API 调用失败：{e}")
