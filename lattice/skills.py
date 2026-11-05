"""Skills: written procedures the agent loads ONLY when a task needs them.

A skill answers "HOW do we do this here?" (conventions, procedures). Project memory answers
"WHAT is true here?". They are kept apart because they differ in trust and lifetime.

Progressive disclosure -- the key idea:
  1. The prompt carries only a compact INDEX (name + one-line description) of relevant skills.
  2. If the task needs one, the model calls the `use_skill` tool and gets the FULL text.
So prompt size stays small (vital for a 3B model) however many skills exist.

A skill is a folder:  <skills_dir>/<name>/SKILL.md
    ---
    name: <same as folder name>
    description: <one line: what it is and when to use it>
    ---
    <the full instructions>

Trust: skill text is delivered to the model as instructions to follow, so only load skills
from directories you control. Memory, by contrast, is never treated as instructions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .tools import Tool, ToolError

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_DESCRIPTION = 200
MAX_BODY = 3500  # keeps a loaded skill inside the agent's per-observation size limit
_STOP = {"the", "and", "for", "with", "that", "this", "then", "into", "from", "how", "use", "when", "are"}


class SkillError(ValueError):
    """A SKILL.md file is malformed."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: Path


class SkillRegistry(Protocol):
    """Anything that can supply skills (a folder today; a shared registry or service later)."""

    def names(self) -> list[str]: ...
    def get(self, name: str) -> Skill: ...  # raises KeyError if unknown
    def suggest(self, task: str, limit: int = 8) -> list[Skill]: ...


def parse_skill_text(text: str, folder_name: str) -> tuple[str, str, str]:
    """Return (name, description, body) or raise SkillError. Dependency-free frontmatter parser."""
    text = text.lstrip("﻿").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise SkillError("missing '---' frontmatter at the top")
    end = text.find("\n---", 3)
    if end == -1:
        raise SkillError("frontmatter is not closed with '---'")
    meta: dict[str, str] = {}
    for line in text[4:end].split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip().strip("'\"")
    body = text[end + 4:].strip()

    name, description = meta.get("name", ""), meta.get("description", "")
    if not NAME_RE.match(name):
        raise SkillError(f"name {name!r} must be lowercase letters, digits and hyphens")
    if name != folder_name:
        raise SkillError(f"name {name!r} must match its folder name {folder_name!r}")
    if not description:
        raise SkillError("description is required")
    if len(description) > MAX_DESCRIPTION:
        raise SkillError(f"description is {len(description)} chars; the limit is {MAX_DESCRIPTION}")
    if not body:
        raise SkillError("skill has no body")
    if len(body) > MAX_BODY:
        raise SkillError(f"body is {len(body)} chars; the limit is {MAX_BODY}")
    return name, description, body


def _words(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if len(w) >= 3 and w not in _STOP:
            out.add(w[:-1] if w.endswith("s") and len(w) > 3 else w)  # crude plural handling
    return out


class DirectorySkillRegistry:
    """Skills stored as folders on disk. A bad skill is skipped and reported, never fatal."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.problems: list[str] = []
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        """Re-scan the directory (call after adding or editing skills)."""
        self._skills, self.problems = {}, []
        if not self.root.is_dir():
            return
        for folder in sorted(p for p in self.root.iterdir() if p.is_dir()):
            md = folder / "SKILL.md"
            if not md.is_file():
                continue  # not a skill folder
            try:
                if not md.resolve().is_relative_to(self.root):
                    raise SkillError("resolves outside the skills directory (symlink?)")
                name, description, body = parse_skill_text(md.read_text(encoding="utf-8"), folder.name)
            except (SkillError, OSError, UnicodeDecodeError) as e:
                self.problems.append(f"{folder.name}: {e}")
                continue
            self._skills[name] = Skill(name, description, body, md)

    def names(self) -> list[str]:
        return sorted(self._skills)

    def get(self, name: str) -> Skill:
        return self._skills[name]

    def suggest(self, task: str, limit: int = 8) -> list[Skill]:
        """The skills worth listing in the prompt for this task.

        Few skills: list them all. Many skills: list only the best matches, so the index
        never grows with the size of the library.
        """
        task_words = _words(task)
        scored = sorted(
            ((len(task_words & _words(s.name.replace("-", " ") + " " + s.description)), s) for s in self._skills.values()),
            key=lambda t: (-t[0], t[1].name),
        )
        if len(scored) <= limit:
            return [s for _, s in scored]
        return [s for score, s in scored if score > 0][:limit]


def format_skill_index(skills: list[Skill]) -> str:
    """The compact index shown in the prompt. Descriptions only -- never the bodies."""
    if not skills:
        return ""
    lines = [
        "",
        "",
        "SKILLS -- written procedures for this project. If the task matches one, load it FIRST with "
        "the use_skill tool, then follow it. Do not load skills the task does not need. Index:",
    ]
    lines += [f"- {s.name}: {s.description}" for s in skills]
    return "\n".join(lines)


def build_skill_tool(registry: SkillRegistry) -> Tool:
    def use_skill(name: str) -> str:
        try:
            skill = registry.get(name)
        except KeyError:
            raise ToolError(f"unknown skill {name!r}. Available: {', '.join(registry.names()) or '(none)'}") from None
        return f"SKILL {skill.name} -- follow these steps:\n{skill.body}"

    return Tool("use_skill", "Load the full text of a skill listed in the SKILLS index. args: {name}", use_skill)
