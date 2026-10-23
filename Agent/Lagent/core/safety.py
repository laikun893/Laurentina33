"""安全与校验辅助层。

提供路径沙箱校验、纯文本判定、本地命令执行等基础能力，
供工具实现层复用，与 UI 无关。
"""

import codecs
import os
import subprocess


def safe_path(work_root, path):
    """归一化路径并校验其必须位于工作根目录内。

    :return: (绝对路径, 错误信息)；失败时绝对路径为 None。
    """
    if not path:
        return None, "路径不能为空"

    abs_path = os.path.abspath(path)
    root = os.path.abspath(work_root)
    try:
        common = os.path.commonpath([root, abs_path])
    except ValueError:
        return None, f"路径无效：{path}"
    if common != root:
        return None, f"安全限制：路径越界，禁止访问工作目录之外的路径：{path}"
    return abs_path, None


def is_text_file(path):
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


def run_cmd(args):
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
