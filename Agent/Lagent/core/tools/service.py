"""工具实现层。

将所有文件系统与系统命令工具封装为 ToolService 类：
- 持有沙箱根目录 work_root 与体积上限 max_text_size；
- 通过 dispatch(name, arguments) 路由到具体实现；
- 每个实现统一返回字符串（成功为可读提示，失败为「错误：」前缀文本）。
"""

import datetime
import json
import mimetypes
import os
import re
import subprocess
import urllib.error
import urllib.request
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from markdownify import markdownify

from ..constants import COMMAND_TIMEOUT, MAX_COMMAND_OUTPUT, MAX_TEXT_SIZE
from ..safety import is_text_file, run_cmd, safe_path

# ----------------------------------------------------------------------
# fetchweb 相关常量
# ----------------------------------------------------------------------
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_CURL_TIMEOUT = 30
# 正文 Markdown 体积上限，超过则截断，避免占用过多上下文 Token。
_MAX_WEB_MARKDOWN = 50 * 1024

# ----------------------------------------------------------------------
# searchWeb 相关常量
# ----------------------------------------------------------------------
# 百度千帆「百度搜索」API 地址。
_SEARCH_API_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"
_SEARCH_TIMEOUT = 30
_SEARCH_TOP_K = 10

# 无条件移除的标签：脚本、样式、媒体、表单、图片以及页面导航等非正文结构。
_ALWAYS_REMOVE = {
    "script", "style", "noscript", "template", "iframe", "frame", "frameset",
    "object", "embed", "applet", "svg", "canvas", "video", "audio", "source",
    "link", "meta", "base", "form", "input", "button", "select", "option",
    "textarea", "label", "fieldset", "legend", "datalist", "output",
    "img", "picture", "map", "area", "nav", "aside", "footer",
}

# 按 class / id 匹配的无关内容关键词（导航、广告、分享、评论区、弹窗等）。
_NOISE_PATTERN = re.compile(
    r"nav|menu|navbar|breadcrumb|crumb|pagination|pager|sidebar|side-bar|"
    r"footer|ad|ads|advert|advertisement|adslot|sponsor|sponsored|promo|"
    r"promotion|banner|share|social|sharing|comment|comments|related|"
    r"recommend|newsletter|subscribe|subscription|cookie|consent|popup|"
    r"modal|dialog|overlay|toast|search|signup|signin|login|register|"
    r"account|avatar|author-bio|bio|print|toolbar|widget|hidden|skip-link|"
    r"jump-link|sr-only|screen-reader|visually-hidden",
    re.IGNORECASE,
)

# curl 常见退出码的中文说明，用于给出更友好的错误提示。
_CURL_ERRORS = {
    1: "不支持的协议",
    3: "URL 格式错误",
    5: "无法解析代理",
    6: "无法解析主机名",
    7: "无法连接到服务器",
    18: "传输被中断",
    22: "服务器返回 HTTP 错误",
    26: "读取文件失败",
    28: "操作超时",
    35: "SSL/TLS 握手失败",
    47: "重定向次数过多",
    52: "服务器无响应",
    56: "接收数据失败",
}


class WebFetchError(Exception):
    """网页抓取 / 解析过程中的错误。"""


class ToolService:
    """文件操作工具服务。"""

    def __init__(self, work_root, max_text_size=MAX_TEXT_SIZE,
                 baidu_qianfan_api_key="", skills=None):
        self.work_root = os.path.abspath(work_root)
        self.max_text_size = max_text_size
        self.baidu_qianfan_api_key = (baidu_qianfan_api_key or "").strip()
        self._skills = {s.name: s for s in (skills or [])}

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
        if name == "RunCil":
            return self.run_cil(
                arguments.get("command", ""), arguments.get("args")
            )
        if name == "fetchweb":
            return self.fetch_web(arguments.get("url"))
        if name == "searchWeb":
            return self.search_web(arguments.get("query"))
        if name == "loadSkill":
            return self.load_skill(
                arguments.get("name"), arguments.get("filename")
            )
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

    def run_cil(self, command, args=None):
        """执行本地已安装的任意命令行程序。

        以参数列表方式（shell=False）调用 subprocess，不拼接 Shell 命令字符串，
        从而规避命令注入风险。命令以运行 Lagent 的当前用户权限执行，
        本教学阶段不实现命令白名单、黑名单或审批机制，仅限受控实验环境使用。
        """
        if not command or not command.strip():
            return "错误：命令不能为空"
        command = command.strip()

        argv = [command]
        if args is None:
            pass
        elif isinstance(args, (list, tuple)):
            argv.extend(str(a) for a in args)
        elif isinstance(args, str):
            argv.append(args)
        else:
            return "错误：参数 args 必须是字符串列表"

        try:
            proc = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=COMMAND_TIMEOUT,
            )
        except FileNotFoundError:
            return f"错误：未找到命令 {command}，请确认程序已安装并加入 PATH"
        except subprocess.TimeoutExpired:
            return f"错误：命令执行超时（超过 {COMMAND_TIMEOUT} 秒），已终止：{command}"
        except OSError as e:
            return f"错误：执行命令失败：{e}"

        stdout = self._truncate_output(proc.stdout or "", MAX_COMMAND_OUTPUT, "stdout")
        stderr = self._truncate_output(proc.stderr or "", MAX_COMMAND_OUTPUT, "stderr")

        parts = [f"退出码：{proc.returncode}", "[stdout]"]
        parts.append(stdout if stdout else "(无输出)")
        if stderr:
            parts.append("[stderr]")
            parts.append(stderr)
        return "\n".join(parts)

    @staticmethod
    def _truncate_output(text, limit, stream_name):
        """截断过长输出并在末尾标明截断情况。"""
        if len(text) <= limit:
            return text
        return (
            text[:limit]
            + f"\n\n……[{stream_name} 输出过长，已截断：显示 {limit} / 共 {len(text)} 字符]"
        )

    def fetch_web(self, url):
        if not url or not url.strip():
            return "错误：URL 不能为空"
        url = url.strip()
        if not url.lower().startswith(("http://", "https://")):
            return f"错误：URL 必须以 http:// 或 https:// 开头：{url}"

        try:
            html_bytes = _download_page(url)
            markdown = _html_to_main_markdown(html_bytes, url)
        except WebFetchError as e:
            return f"错误：{e}"

        return f"原始 URL：{url}\n\n{markdown}"

    def search_web(self, query):
        """调用百度千帆「百度搜索」API，返回搜索摘要与来源信息。"""
        if not query or not query.strip():
            return "错误：搜索关键词不能为空"
        query = query.strip()

        if not self.baidu_qianfan_api_key:
            return (
                "错误：未配置百度千帆 API Key，"
                "请在 config.ini 的 [search] 小节中设置 baidu_qianfan_api_key"
            )

        payload = json.dumps(
            {
                "messages": [{"role": "user", "content": query}],
                "search_source": "baidu_search_v2",
                "resource_type_filter": [{"type": "web", "top_k": _SEARCH_TOP_K}],
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            _SEARCH_API_URL,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.baidu_qianfan_api_key}",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=_SEARCH_TIMEOUT) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            return self._search_error_detail(
                f"搜索请求失败（HTTP {e.code}）", e.read()
            )
        except urllib.error.URLError as e:
            return f"错误：网络请求失败：{e.reason}"
        except OSError as e:
            return f"错误：网络请求失败：{e}"

        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            return f"错误：搜索响应解析失败：{e}"

        if not isinstance(data, dict):
            return "错误：搜索响应格式异常"

        references = data.get("references")
        if references is None:
            code = data.get("code")
            message = data.get("message") or data.get("error_msg") or "未知错误"
            return f"错误：搜索 API 返回错误（code={code}）：{message}"

        if not isinstance(references, list) or not references:
            return f"错误：未获取到任何搜索结果：{query}"

        return self._format_search_results(query, references)

    # ------------------------------------------------------------------
    # loadSkill 工具与辅助方法
    # ------------------------------------------------------------------
    def load_skill(self, name, filename=None):
        """加载指定 Skill 的 SKILL.md 全文或其附件文件。"""
        if not name or not name.strip():
            return "错误：Skill 名称不能为空"
        name = name.strip()
        skill = self._skills.get(name)
        if skill is None:
            return f"错误：未找到技能：{name}"

        if not filename or not filename.strip():
            return self._read_skill_file(skill.skills_md_path)

        return self._load_skill_attachment(skill, filename.strip())

    def _read_skill_file(self, path):
        """读取 Skill 目录内的一个纯文本文件，返回正文。"""
        if not os.path.isfile(path):
            return f"错误：文件不存在：{path}"
        size = os.path.getsize(path)
        if size > self.max_text_size:
            return (
                f"错误：文件过大（{size} 字节），超过限制 "
                f"{self.max_text_size} 字节，拒绝读取"
            )
        ok, why = is_text_file(path)
        if not ok:
            return f"错误：仅支持纯文本文件，{why}"
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            return f"错误：读取失败：{e}"

    def _load_skill_attachment(self, skill, filename):
        """按精确路径优先、文件名兜底的顺序解析并读取附件。"""
        # 1. 相对 Skill 目录的路径
        candidate = os.path.join(skill.dir_path, filename)
        if os.path.isfile(candidate) and self._is_within(skill.dir_path, candidate):
            return self._read_skill_file(candidate)

        # 2. 项目相对路径
        candidate = os.path.join(self.work_root, filename)
        if os.path.isfile(candidate) and self._is_within(skill.dir_path, candidate):
            return self._read_skill_file(candidate)

        # 3. 绝对路径
        if os.path.isabs(filename):
            if not self._is_within(skill.dir_path, filename):
                return (
                    f"错误：路径越界，禁止访问技能 {skill.name} "
                    f"目录之外的文件：{filename}"
                )
            if os.path.isfile(filename):
                return self._read_skill_file(filename)
            return f"错误：文件不存在：{filename}"

        # 4. 仅提供文件名时，递归搜索该 Skill 目录
        matches = self._find_in_skill(skill.dir_path, os.path.basename(filename))
        if len(matches) == 1:
            return self._read_skill_file(matches[0])
        if len(matches) > 1:
            rel_paths = [os.path.relpath(m, skill.dir_path) for m in matches]
            candidates = "\n".join(f"- {p}" for p in rel_paths)
            return (
                f"错误：存在多个同名文件，请指定具体路径（相对 Skill 目录）：\n"
                f"{candidates}"
            )
        return f"错误：在技能 {skill.name} 目录中未找到文件：{filename}"

    @staticmethod
    def _is_within(root, path):
        """校验 path 解析后仍位于 root 目录内。"""
        root_real = os.path.realpath(root)
        path_real = os.path.realpath(path)
        try:
            common = os.path.commonpath([root_real, path_real])
        except ValueError:
            return False
        return common == root_real

    @staticmethod
    def _find_in_skill(root, filename):
        """递归查找 root 目录下所有名为 filename 的文件。"""
        matches = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                if fn == filename:
                    matches.append(os.path.join(dirpath, fn))
        return matches

    # ------------------------------------------------------------------
    # searchWeb 辅助方法
    # ------------------------------------------------------------------
    @staticmethod
    def _search_error_detail(prefix, body):
        """尝试从错误响应体中解析 code/message，拼接出更清晰的错误信息。"""
        detail = ""
        if body:
            try:
                err = json.loads(body.decode("utf-8", errors="replace"))
                code = err.get("code")
                message = err.get("message") or err.get("error_msg")
                if code is not None or message:
                    detail = f"（code={code}）{message or ''}"
            except (ValueError, UnicodeDecodeError):
                detail = body.decode("utf-8", errors="replace").strip()[:200]
        if not detail:
            detail = body.decode("utf-8", errors="replace").strip()[:200] if body else "未知错误"
        return f"错误：{prefix}：{detail}".strip()

    @staticmethod
    def _format_search_results(query, references):
        """将搜索结果整理为可读文本：摘要 + 标题 + URL。"""
        lines = [f"搜索关键词：{query}", f"共 {len(references)} 条结果：", ""]
        for idx, ref in enumerate(references, start=1):
            if not isinstance(ref, dict):
                continue
            title = ref.get("title") or "(无标题)"
            url = ref.get("url") or ""
            snippet = (ref.get("snippet") or ref.get("content") or "").strip()
            website = ref.get("website") or ""
            lines.append(f"[{idx}] {title}")
            if website:
                lines.append(f"    来源：{website}")
            if url:
                lines.append(f"    URL：{url}")
            if snippet:
                lines.append(f"    摘要：{snippet}")
            lines.append("")
        return "\n".join(lines).rstrip()


# ----------------------------------------------------------------------
# fetchweb 辅助函数（模块级，纯函数，便于测试）
# ----------------------------------------------------------------------
def _download_page(url):
    """使用本地 curl 程序抓取网页，返回原始响应字节（未经文本解码）。

    采用参数列表方式调用 subprocess，不使用 shell=True，避免命令注入。
    """
    cmd = [
        "curl",
        "-sSL",
        "--compressed",
        "--max-time", str(_CURL_TIMEOUT),
        "-A", _USER_AGENT,
        url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=_CURL_TIMEOUT + 10,
        )
    except FileNotFoundError:
        raise WebFetchError("未找到 curl 程序，请确认已安装 curl 并加入 PATH")
    except subprocess.TimeoutExpired:
        raise WebFetchError(f"获取网页超时（超过 {_CURL_TIMEOUT} 秒）")
    except OSError as e:
        raise WebFetchError(f"调用 curl 失败：{e}")

    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        stdout = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
        detail = stderr or stdout or "未知错误"
        reason = _CURL_ERRORS.get(proc.returncode)
        if reason:
            raise WebFetchError(
                f"获取网页失败（{reason}，退出码 {proc.returncode}）：{detail}"
            )
        raise WebFetchError(f"获取网页失败（退出码 {proc.returncode}）：{detail}")

    return proc.stdout


def _html_to_main_markdown(html_bytes, url):
    """将网页 HTML 解析并提取正文，转换为 Markdown 文本。"""
    if not html_bytes or not html_bytes.strip():
        raise WebFetchError("网页返回内容为空")

    try:
        soup = BeautifulSoup(html_bytes, "html.parser")
    except Exception as e:
        raise WebFetchError(f"HTML 解析失败：{e}")

    if soup.find() is None:
        raise WebFetchError("返回内容不是有效的 HTML 文档")

    main = _find_main(soup)
    if main is None:
        raise WebFetchError("无法定位网页正文")

    _clean(main)
    _resolve_links(main, url)

    try:
        markdown = markdownify(str(main), heading_style="ATX")
    except Exception as e:
        raise WebFetchError(f"Markdown 转换失败：{e}")

    markdown = _tidy_markdown(markdown)
    if not markdown:
        raise WebFetchError("网页正文为空，无法提取有效内容")

    if len(markdown) > _MAX_WEB_MARKDOWN:
        markdown = markdown[:_MAX_WEB_MARKDOWN] + "\n\n…（内容过长，已截断）"

    return markdown


def _find_main(soup):
    """定位正文容器：优先语义标签，其次按内容量启发式挑选。"""
    body = soup.body or soup

    role_main = body.find(attrs={"role": re.compile(r"^main$", re.IGNORECASE)})
    for node in (body.find("main"), body.find("article"), role_main):
        if node is not None and _has_substantial_text(node):
            return node

    best, best_score = None, 0.0
    for node in body.find_all(["div", "section", "article", "main"]):
        score = _content_score(node)
        if score > best_score:
            best, best_score = node, score

    return best if best is not None else body


def _content_score(node):
    """为容器打分：文本越长、块级标签越多、链接密度越低，得分越高。"""
    text = node.get_text(" ", strip=True)
    length = len(text)
    if length < 80:
        return 0.0
    block_tags = node.find_all(
        ["p", "pre", "blockquote", "li", "h1", "h2", "h3", "h4", "h5", "h6",
         "td", "th", "dt", "dd"]
    )
    link_text = sum(len(a.get_text(" ", strip=True)) for a in node.find_all("a"))
    density = link_text / length if length else 1.0
    return length + len(block_tags) * 25 - density * length


def _has_substantial_text(node):
    return node is not None and len(node.get_text(" ", strip=True)) >= 50


def _clean(node):
    """移除正文容器内的脚本、媒体、表单以及导航 / 广告等无关元素。"""
    for el in list(node.find_all(True)):
        if (el.name or "").lower() in _ALWAYS_REMOVE:
            el.decompose()
            continue
        id_text = el.get("id") or ""
        class_text = " ".join(el.get("class") or [])
        if _NOISE_PATTERN.search(id_text) or _NOISE_PATTERN.search(class_text):
            el.decompose()


def _resolve_links(node, base_url):
    """将正文中的相对链接解析为绝对链接，去掉 javascript 等无效链接。"""
    for a in node.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.lower().startswith(
            ("javascript:", "data:", "mailto:", "tel:", "#")
        ):
            a.unwrap()
            continue
        try:
            a["href"] = urljoin(base_url, href)
        except ValueError:
            a.unwrap()


def _tidy_markdown(text):
    """统一换行符并折叠多余空行，压缩 Markdown 体积。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines, prev_blank = [], False
    for line in text.split("\n"):
        stripped = line.rstrip()
        if not stripped:
            if not prev_blank:
                lines.append("")
            prev_blank = True
        else:
            lines.append(stripped)
            prev_blank = False
    return "\n".join(lines).strip()
