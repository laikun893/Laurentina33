"""Lagent 程序入口。

职责：组装 core 各层并启动 TUI 前端。
- 依赖注入：core 与 tui 互不直接引用实现细节；
- 未来如需切换前端，只需替换最后启动的 App 即可。
"""

import os
import sys
from pathlib import Path

from core import Agent, LLMClient, TOOL_SCHEMAS, ToolService, load_config
from core.agent import DEFAULT_SYSTEM_PROMPT
from core.skills import build_system_prompt, discover_skills
from tui import AgentChatApp

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config.ini"


def build_agent() -> Agent:
    """从配置文件与当前工作目录组装 Agent。"""
    config = load_config(CONFIG_PATH)
    llm = LLMClient(config)
    project_root = os.getcwd()
    skills = discover_skills(project_root)
    tools = ToolService(
        work_root=project_root,
        baidu_qianfan_api_key=config.baidu_qianfan_api_key,
        skills=skills,
    )
    system_prompt = build_system_prompt(DEFAULT_SYSTEM_PROMPT, skills)
    return Agent(
        llm=llm,
        tools=tools,
        tool_schemas=TOOL_SCHEMAS,
        system_prompt=system_prompt,
    )


def main() -> None:
    try:
        agent = build_agent()
    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)

    AgentChatApp(agent).run()


if __name__ == "__main__":
    main()
