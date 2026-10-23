"""工具声明层。

以 JSON Schema 形式向模型声明可用的 Function Calling 工具。
仅作声明，不包含实现，实现见 service.py。
"""

TOOL_SCHEMAS = [
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
