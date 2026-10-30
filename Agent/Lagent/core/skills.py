"""Skill 发现与注册层。

职责：在项目根目录的 `.agents/skills`（或 office 项目使用的 `.agents/.skills`）
下扫描各个 Skill 子目录，初始化阶段仅解析每个 SKILL.md 头部的 YAML
Frontmatter（name、description），正文在 LLM 调用 loadSkill 时才会被读取。
"""

import os
from dataclasses import dataclass

# 同时兼容两种目录约定：Lagent 的 .agents/skills 与 office 的 .agents/.skills。
SKILLS_RELATIVE_PATHS = (
    os.path.join(".agents", "skills"),
    os.path.join(".agents", ".skills"),
)


@dataclass
class Skill:
    """一个已注册的 Skill 的元信息（不含正文）。"""

    name: str
    description: str
    dir_path: str
    skills_md_path: str


def discover_skills(project_root):
    """扫描项目根目录下的技能目录，返回已发现的 Skill 列表。

    依次尝试 `.agents/skills` 与 `.agents/.skills`（后者为 office 的约定），
    同名技能以先命中的目录为准。每个 Skill 子目录必须包含 SKILL.md，
    且其头部 Frontmatter 必须声明 name，否则跳过该目录。
    """
    skills = []
    seen_dirs = set()
    seen_names = set()

    for relative_path in SKILLS_RELATIVE_PATHS:
        skills_root = os.path.join(project_root, relative_path)
        if not os.path.isdir(skills_root):
            continue
        root_real = os.path.realpath(skills_root)
        if root_real in seen_dirs:
            continue
        seen_dirs.add(root_real)

        for entry in sorted(os.listdir(skills_root)):
            subdir = os.path.join(skills_root, entry)
            if not os.path.isdir(subdir):
                continue
            subdir_real = os.path.realpath(subdir)
            if subdir_real in seen_dirs:
                continue
            md_path = os.path.join(subdir, "SKILL.md")
            if not os.path.isfile(md_path):
                continue
            meta = _read_frontmatter(md_path)
            if not meta:
                continue
            name = (meta.get("name") or "").strip()
            description = (meta.get("description") or "").strip()
            if not name or name in seen_names:
                continue
            seen_dirs.add(subdir_real)
            seen_names.add(name)
            skills.append(
                Skill(
                    name=name,
                    description=description,
                    dir_path=os.path.abspath(subdir),
                    skills_md_path=os.path.abspath(md_path),
                )
            )

    skills.sort(key=lambda s: s.name)
    return skills


def build_system_prompt(base_prompt, skills):
    """将已发现 Skill 的名称与描述追加到系统提示词中。"""
    if not skills:
        return base_prompt

    lines = [base_prompt, "", "You have access to the following skills:", ""]
    for skill in skills:
        lines.append(f"{skill.name}: {skill.description}")
    lines.append("")
    lines.append(
        "Use the loadSkill tool to load the full instructions of a skill "
        "when needed. You can also load additional files referenced by a skill."
    )
    return "\n".join(lines)


def _read_frontmatter(path):
    """读取 SKILL.md 头部的 YAML Frontmatter，返回字段字典；无则返回 None。

    仅支持 `key: value` 形式的标量字段（name、description 等），
    不依赖第三方 YAML 库。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.readline()
            if first.strip() != "---":
                return None
            meta = {}
            for line in f:
                stripped = line.rstrip("\n")
                if stripped.strip() == "---":
                    return meta
                if ":" in stripped:
                    key, _, value = stripped.partition(":")
                    meta[key.strip()] = _unquote(value.strip())
    except OSError:
        return None
    return None


def _unquote(value):
    """去除标量值两侧可能存在的引号。"""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value
