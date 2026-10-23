import os
import sys
import json
import subprocess
import configparser

from openai import OpenAI

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

config = configparser.ConfigParser()
if not config.read(config_path):
    sys.exit("错误：找不到配置文件 config.ini")

if not config.has_section("default"):
    sys.exit("错误：配置文件缺少 [default] section")

try:
    base_url = config.get("default", "base_url")
    model = config.get("default", "model")
    api_key = config.get("default", "api_key")
except configparser.NoOptionError as e:
    sys.exit(f"错误：配置文件缺少字段 {e.option}")

client = OpenAI(base_url=base_url, api_key=api_key)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间。通过调用本地 date/time 命令实现，无需传入任何参数。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "isLeapYear",
            "description": "判断输入的年份是否为闰年。闰年规则：能被 4 整除但不能被 100 整除，或者能被 400 整除。",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "需要判断的年份，例如 2000、2024。"
                    }
                },
                "required": ["year"]
            }
        }
    }
]


def get_date():
    """通过调用本地 date/time 命令获取当前日期和时间。"""
    if os.name == "nt":
        date_out = subprocess.run(
            ["cmd", "/c", "date", "/t"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        time_out = subprocess.run(
            ["cmd", "/c", "time", "/t"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        return f"{date_out} {time_out}"

    result = subprocess.run(["date"], capture_output=True, text=True)
    return result.stdout.strip()


def is_leap_year(year):
    """通过 Python 代码计算输入的年份是否为闰年。"""
    year = int(year)
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        return f"{year} 年是闰年"
    return f"{year} 年不是闰年"


def run_tool(name, arguments):
    if name == "getDate":
        return get_date()
    if name == "isLeapYear":
        return is_leap_year(arguments.get("year"))
    return f"未知的工具：{name}"


print("你好，我是AI助手")

messages = []

while True:
    try:
        prompt = input("请输入提示词：")
    except (EOFError, KeyboardInterrupt):
        print("\n已退出。")
        break

    if not prompt.strip():
        continue

    print("---")

    messages.append({"role": "user", "content": prompt})

    try:
        while True:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
            )
            message = response.choices[0].message

            if message.tool_calls:
                messages.append(
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
                    result = run_tool(tc.function.name, args)
                    print(f"[调用工具 {tc.function.name}] -> {result}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
                continue

            content = message.content or ""
            print(content)
            messages.append({"role": "assistant", "content": content})
            break
    except Exception as e:
        print(f"错误：API 调用失败：{e}")
        messages.pop()
