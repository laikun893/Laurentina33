"""工具实现层。

将所有文件系统与系统命令工具封装为 ToolService 类：
- 持有沙箱根目录 work_root 与体积上限 max_text_size；
- 通过 dispatch(name, arguments) 路由到具体实现；
- 每个实现统一返回字符串（成功为可读提示，失败为「错误：」前缀文本）。
"""

import datetime
import mimetypes
import os
import subprocess

from ..constants import MAX_TEXT_SIZE
from ..safety import is_text_file, run_cmd, safe_path


class ToolService:
    """文件操作工具服务。"""

    def __init__(self, work_root, max_text_size=MAX_TEXT_SIZE):
        self.work_root = os.path.abspath(work_root)
        self.max_text_size = max_text_size

    # ------------------------------------------------------------------
    # 分发
    # ------------------------------------------------------------------
    def dispatch(self, name, arguments):
        """按工具名路由到具体实现。"""
        if name == "getCurrentDir":
            return self.get_current_dir()
        if name == "getCurrentTime":
            return self.get_current_time()
        if name == "listDir":
            return self.list_dir(arguments.get("path", "."))
        if name == "getFileType":
            return self.get_file_type(arguments.get("path"))
        if name == "readFile":
            return self.read_file(arguments.get("path"))
        if name == "createFile":
            return self.create_file(
                arguments.get("directory"),
                arguments.get("filename"),
                arguments.get("content", ""),
            )
        if name == "editFile":
            return self.edit_file(
                arguments.get("path"),
                arguments.get("content", ""),
                arguments.get("mode", "overwrite"),
            )
        if name == "createDir":
            return self.create_dir(arguments.get("path"))
        if name == "deleteDir":
            return self.delete_dir(arguments.get("path"))
        if name == "deleteFile":
            return self.delete_file(arguments.get("path"))
        if name == "renamePath":
            return self.rename_path(
                arguments.get("old_path"), arguments.get("new_path")
            )
        if name == "execCommand":
            return self.exec_command(arguments.get("command", ""))
        return f"未知的工具：{name}"

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    def _safe_path(self, path):
        return safe_path(self.work_root, path)

    # ------------------------------------------------------------------
    # 工具实现
    # ------------------------------------------------------------------
    def get_current_dir(self):
        stdout, stderr, code = run_cmd(["cmd", "/c", "cd"])
        out = stdout.strip()
        if code != 0 or not out:
            return f"错误：获取当前目录失败：{stderr.strip() or '未知错误'}"
        return f"当前工作目录：{out}"

    def get_current_time(self):
        now = datetime.datetime.now()
        weekday_cn = "一二三四五六日"[now.weekday()]
        return (
            f"当前日期：{now.strftime('%Y-%m-%d')}\n"
            f"当前时间：{now.strftime('%H:%M:%S')}\n"
            f"星期：星期{weekday_cn}\n"
            f"带时区时间：{now.astimezone().isoformat(timespec='seconds')}"
        )

    def list_dir(self, path="."):
        target, err = self._safe_path(path)
        if err:
            return err
        if not os.path.isdir(target):
            return f"错误：路径不是目录或目录不存在：{path}"
        stdout, stderr, code = run_cmd(["cmd", "/c", "dir", target])
        if code != 0:
            return f"错误：无法列出目录：{stderr.strip() or stdout.strip()}"
        return stdout.rstrip()

    def get_file_type(self, path):
        target, err = self._safe_path(path)
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

    def read_file(self, path):
        target, err = self._safe_path(path)
        if err:
            return err
        if not os.path.isfile(target):
            return f"错误：文件不存在：{path}"
        size = os.path.getsize(target)
        if size > self.max_text_size:
            return f"错误：文件过大（{size} 字节），超过限制 {self.max_text_size} 字节，拒绝读取"
        ok, why = is_text_file(target)
        if not ok:
            return f"错误：仅支持纯文本文件，{why}"
        try:
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            return f"错误：读取失败：{e}"
        return content

    def create_file(self, directory, filename, content=""):
        dir_path, err = self._safe_path(directory)
        if err:
            return err
        if not filename or os.path.basename(filename) != filename:
            return f"错误：文件名无效（不允许包含路径分隔符）：{filename}"
        target = os.path.join(dir_path, filename)
        target, err = self._safe_path(target)
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

    def edit_file(self, path, content, mode="overwrite"):
        target, err = self._safe_path(path)
        if err:
            return err
        if not os.path.isfile(target):
            return f"错误：文件不存在：{path}"
        ok, why = is_text_file(target)
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

    def create_dir(self, path):
        target, err = self._safe_path(path)
        if err:
            return err
        if os.path.isdir(target):
            return f"目录已存在：{target}"
        stdout, stderr, code = run_cmd(["cmd", "/c", "mkdir", target])
        if code != 0:
            return f"错误：创建目录失败：{stderr.strip() or stdout.strip()}"
        return f"已创建目录：{target}"

    def delete_dir(self, path):
        target, err = self._safe_path(path)
        if err:
            return err
        if not os.path.isdir(target):
            return f"错误：目录不存在或不是目录：{path}"
        stdout, stderr, code = run_cmd(["cmd", "/c", "rmdir", "/s", "/q", target])
        if code != 0:
            return f"错误：删除目录失败：{stderr.strip() or stdout.strip()}"
        return f"已删除目录（含全部内容）：{target}"

    def delete_file(self, path):
        target, err = self._safe_path(path)
        if err:
            return err
        if not os.path.isfile(target):
            return f"错误：文件不存在或不是文件：{path}"
        stdout, stderr, code = run_cmd(["cmd", "/c", "del", "/q", target])
        if code != 0:
            return f"错误：删除文件失败：{stderr.strip() or stdout.strip()}"
        return f"已删除文件：{target}"

    def rename_path(self, old_path, new_path):
        old_target, err = self._safe_path(old_path)
        if err:
            return err
        new_target, err = self._safe_path(new_path)
        if err:
            return err
        if not os.path.exists(old_target):
            return f"错误：原路径不存在：{old_path}"
        if os.path.exists(new_target):
            return f"错误：目标路径已存在：{new_path}"
        stdout, stderr, code = run_cmd(
            ["cmd", "/c", "move", "/y", old_target, new_target]
        )
        if code != 0:
            return f"错误：重命名失败：{stderr.strip() or stdout.strip()}"
        return f"已重命名：{old_target} -> {new_target}"

    def exec_command(self, command):
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
