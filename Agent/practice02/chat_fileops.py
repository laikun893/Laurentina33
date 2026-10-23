import os
import sys
import json
import shutil
import codecs
import datetime
import subprocess
import mimetypes
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

WORK_ROOT = os.getcwd()
MAX_TEXT_SIZE = 1024 * 1024

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "getCurrentDir",
            "description": "获取当前电脑的工作目录。通过调用本地 cd 命令实现，无需传入任何参数。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "getCurrentTime",
            "description": "获取本机的当前日期和时间。通过调用 Python 的 datetime.datetime.now() 实现，返回本地时区的日期、时间与星期，无需传入任何参数。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listDir",
            "description": "列出指定目录下的所有文件和子目录。通过调用本地 dir 命令实现。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "需要列出的目录路径，可以是相对路径或绝对路径。默认是当前工作目录。"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "getFileType",
            "description": "获取指定文件的文件类型（MIME 类型和扩展名）。通过调用 Python 的 mimetypes 模块实现。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "需要判断类型的文件路径。"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "readFile",
            "description": "获取指定纯文本文件的内容。仅支持纯文本格式文件，不支持二进制文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "需要读取的文本文件路径。"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "createFile",
            "description": "根据指定的目录和文件名创建新文件。如果目录不存在会自动创建目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "新文件所在的目录路径。"
                    },
                    "filename": {
                        "type": "string",
                        "description": "新文件的文件名。"
                    },
                    "content": {
                        "type": "string",
                        "description": "可选，新文件的初始内容。不填则为空文件。"
                    }
                },
                "required": ["directory", "filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "editFile",
            "description": "编辑指定纯文本文件的内容，支持覆盖或追加模式。仅支持纯文本格式文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "需要编辑的文本文件路径。"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入文件的新内容。"
                    },
                    "mode": {
                        "type": "string",
                        "description": "写入模式，可选 overwrite（覆盖，默认）或 append（追加）。",
                        "enum": ["overwrite", "append"]
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "createDir",
            "description": "创建新目录，支持创建多级目录。通过调用本地 mkdir 命令实现。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "需要创建的目录路径。"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deleteDir",
            "description": "删除目录，支持删除非空目录（目录内所有内容都会被删除）。通过调用本地 rmdir /s /q 命令实现。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "需要删除的目录路径。"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deleteFile",
            "description": "删除指定的文件。通过调用本地 del 命令实现。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "需要删除的文件路径。"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "renamePath",
            "description": "重命名文件或目录。通过调用本地 move 命令实现。",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_path": {
                        "type": "string",
                        "description": "原文件或目录的路径。"
                    },
                    "new_path": {
                        "type": "string",
                        "description": "新的文件或目录路径。"
                    }
                },
                "required": ["old_path", "new_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execCommand",
            "description": "执行一条任意的本地命令（Windows cmd 命令），返回标准输出、标准错误和退出码。支持管道和重定向等 shell 语法。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "需要执行的本地命令，例如 dir、type test.txt、echo hello > a.txt。"
                    }
                },
                "required": ["command"]
            }
        }
    }
]


def _safe_path(path):
    """归一化路径并校验其必须位于工作根目录内，返回 (绝对路径, 错误信息)。"""
    if not path:
        return None, "路径不能为空"
    abs_path = os.path.abspath(path)
    try:
        common = os.path.commonpath([WORK_ROOT, abs_path])
    except ValueError:
        return None, f"路径无效：{path}"
    if common != os.path.abspath(WORK_ROOT):
        return None, f"安全限制：路径越界，禁止访问工作目录之外的路径：{path}"
    return abs_path, None


def _is_text_file(path):
    """判断文件是否为纯文本：读取前 1024 字节，检测空字节和 UTF-8 可解码性。

    采样 1024 字节可能把多字节字符截断在末尾，此时尾部抛出的 UnicodeDecodeError
    并不代表文件是二进制，因此使用增量解码器并忽略不完整的尾部字节。
    """
    try:
        with open(path, "rb") as f:
            head = f.read(1024)
    except OSError as e:
        return False, str(e)
    if b"\x00" in head:
        return False, "文件包含二进制空字节，判定为二进制文件"
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        decoder.decode(head, final=False)
    except UnicodeDecodeError:
        return False, "文件无法按 UTF-8 解码，判定为二进制文件"
    return True, None


def _run_cmd(args):
    """执行本地命令并返回 (stdout, stderr, returncode)。args 为参数列表。"""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            errors="replace",
        )
    except OSError as e:
        return "", str(e), -1
    return proc.stdout or "", proc.stderr or "", proc.returncode


def get_current_dir():
    stdout, stderr, code = _run_cmd(["cmd", "/c", "cd"])
    out = stdout.strip()
    if code != 0 or not out:
        return f"错误：获取当前目录失败：{stderr.strip() or '未知错误'}"
    return f"当前工作目录：{out}"


def get_current_time():
    """返回本机当前日期时间：日期、时间、星期与带时区的 ISO 字符串。"""
    now = datetime.datetime.now()
    weekday_cn = "一二三四五六日"[now.weekday()]
    return (
        f"当前日期：{now.strftime('%Y-%m-%d')}\n"
        f"当前时间：{now.strftime('%H:%M:%S')}\n"
        f"星期：星期{weekday_cn}\n"
        f"带时区时间：{now.astimezone().isoformat(timespec='seconds')}"
    )


def list_dir(path="."):
    target, err = _safe_path(path)
    if err:
        return err
    if not os.path.isdir(target):
        return f"错误：路径不是目录或目录不存在：{path}"
    stdout, stderr, code = _run_cmd(["cmd", "/c", "dir", target])
    if code != 0:
        return f"错误：无法列出目录：{stderr.strip() or stdout.strip()}"
    return stdout.rstrip()


def get_file_type(path):
    target, err = _safe_path(path)
    if err:
        return err
    if not os.path.exists(target):
        return f"错误：文件不存在：{path}"
    if os.path.isdir(target):
        return f"{path} 是目录，不是文件"
    mime, _ = mimetypes.guess_type(target)
    mime = mime or "未知类型"
    ext = os.path.splitext(target)[1] or "(无扩展名)"
    return f"文件：{target}\nMIME 类型：{mime}\n扩展名：{ext}"


def read_file(path):
    target, err = _safe_path(path)
    if err:
        return err
    if not os.path.isfile(target):
        return f"错误：文件不存在：{path}"
    size = os.path.getsize(target)
    if size > MAX_TEXT_SIZE:
        return f"错误：文件过大（{size} 字节），超过限制 {MAX_TEXT_SIZE} 字节，拒绝读取"
    ok, why = _is_text_file(target)
    if not ok:
        return f"错误：仅支持纯文本文件，{why}"
    try:
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        return f"错误：读取失败：{e}"
    return content


def create_file(directory, filename, content=""):
    dir_path, err = _safe_path(directory)
    if err:
        return err
    if not filename or os.path.basename(filename) != filename:
        return f"错误：文件名无效（不允许包含路径分隔符）：{filename}"
    target = os.path.join(dir_path, filename)
    target, err = _safe_path(target)
    if err:
        return err
    if os.path.exists(target):
        return f"错误：文件已存在：{target}"
    try:
        os.makedirs(dir_path, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content or "")
    except OSError as e:
        return f"错误：创建文件失败：{e}"
    return f"已创建文件：{target}"


def edit_file(path, content, mode="overwrite"):
    target, err = _safe_path(path)
    if err:
        return err
    if not os.path.isfile(target):
        return f"错误：文件不存在：{path}"
    ok, why = _is_text_file(target)
    if not ok:
        return f"错误：仅支持纯文本文件，{why}"
    if mode == "append":
        open_mode = "a"
    elif mode == "overwrite":
        open_mode = "w"
    else:
        return f"错误：未知的写入模式：{mode}"
    try:
        with open(target, open_mode, encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return f"错误：写入失败：{e}"
    return f"已{('追加' if mode == 'append' else '覆盖')}写入文件：{target}"


def create_dir(path):
    target, err = _safe_path(path)
    if err:
        return err
    if os.path.isdir(target):
        return f"目录已存在：{target}"
    stdout, stderr, code = _run_cmd(["cmd", "/c", "mkdir", target])
    if code != 0:
        return f"错误：创建目录失败：{stderr.strip() or stdout.strip()}"
    return f"已创建目录：{target}"


def delete_dir(path):
    target, err = _safe_path(path)
    if err:
        return err
    if not os.path.isdir(target):
        return f"错误：目录不存在或不是目录：{path}"
    stdout, stderr, code = _run_cmd(["cmd", "/c", "rmdir", "/s", "/q", target])
    if code != 0:
        return f"错误：删除目录失败：{stderr.strip() or stdout.strip()}"
    return f"已删除目录（含全部内容）：{target}"


def delete_file(path):
    target, err = _safe_path(path)
    if err:
        return err
    if not os.path.isfile(target):
        return f"错误：文件不存在或不是文件：{path}"
    stdout, stderr, code = _run_cmd(["cmd", "/c", "del", "/q", target])
    if code != 0:
        return f"错误：删除文件失败：{stderr.strip() or stdout.strip()}"
    return f"已删除文件：{target}"


def rename_path(old_path, new_path):
    old_target, err = _safe_path(old_path)
    if err:
        return err
    new_target, err = _safe_path(new_path)
    if err:
        return err
    if not os.path.exists(old_target):
        return f"错误：原路径不存在：{old_path}"
    if os.path.exists(new_target):
        return f"错误：目标路径已存在：{new_path}"
    stdout, stderr, code = _run_cmd(
        ["cmd", "/c", "move", "/y", old_target, new_target]
    )
    if code != 0:
        return f"错误：重命名失败：{stderr.strip() or stdout.strip()}"
    return f"已重命名：{old_target} -> {new_target}"


def exec_command(command):
    if not command or not command.strip():
        return "错误：命令不能为空"
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            errors="replace",
        )
    except OSError as e:
        return f"错误：执行命令失败：{e}"
    parts = []
    if proc.stdout:
        parts.append(proc.stdout.rstrip())
    if proc.stderr:
        parts.append("[stderr] " + proc.stderr.rstrip())
    out = "\n".join(parts) if parts else "(无输出)"
    return f"退出码：{proc.returncode}\n{out}"


def run_tool(name, arguments):
    if name == "getCurrentDir":
        return get_current_dir()
    if name == "getCurrentTime":
        return get_current_time()
    if name == "listDir":
        return list_dir(arguments.get("path", "."))
    if name == "getFileType":
        return get_file_type(arguments.get("path"))
    if name == "readFile":
        return read_file(arguments.get("path"))
    if name == "createFile":
        return create_file(
            arguments.get("directory"),
            arguments.get("filename"),
            arguments.get("content", ""),
        )
    if name == "editFile":
        return edit_file(
            arguments.get("path"),
            arguments.get("content", ""),
            arguments.get("mode", "overwrite"),
        )
    if name == "createDir":
        return create_dir(arguments.get("path"))
    if name == "deleteDir":
        return delete_dir(arguments.get("path"))
    if name == "deleteFile":
        return delete_file(arguments.get("path"))
    if name == "renamePath":
        return rename_path(arguments.get("old_path"), arguments.get("new_path"))
    if name == "execCommand":
        return exec_command(arguments.get("command", ""))
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
