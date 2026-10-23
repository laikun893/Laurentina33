"""LLM 客户端层。

职责：屏蔽具体模型供应商（当前为 OpenAI 兼容协议，例如 DeepSeek），
只向上层暴露统一的同步 create 接口。将来切换供应商只需替换本层。
"""

from openai import OpenAI

from .config import Config


class LLMClient:
    """OpenAI 兼容协议的模型客户端封装。"""

    def __init__(self, config: Config):
        self.model = config.model
        self.base_url = config.base_url
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=60.0,
        )

    def create(self, messages, tools):
        """同步发起一次补全请求。

        该方法为阻塞调用，上层（Agent）应放入线程池执行以避免阻塞事件循环。
        """
        return self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
        )
