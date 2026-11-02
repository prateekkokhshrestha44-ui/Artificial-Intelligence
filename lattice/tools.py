"""Tools: the only ways the agent can touch the outside world.

Every file tool is jailed to a Workspace folder. This is the first piece of the
"enforce the boundary in the runtime, not the prompt" rule: even if the model
asks for ../../etc/passwd, the code refuses.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class ToolError(Exception):
    """A tool failed in a way the model should be told about (not a crash)."""


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., str]


class Workspace:
    """A directory the agent is allowed to read and write -- and nothing else."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, rel: str) -> Path:
        path = (self.root / rel).resolve()
        if not path.is_relative_to(self.root):
            raise ToolError(f"path escapes workspace: {rel}")
        return path


def build_default_tools(ws: Workspace) -> dict[str, Tool]:
    def read_file(path: str) -> str:
        p = ws.resolve(path)
        if not p.is_file():
            raise ToolError(f"no such file: {path}")
        return p.read_text()

    def write_file(path: str, content: str) -> str:
        p = ws.resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {len(content)} chars to {path}"

    def list_files(path: str = ".") -> str:
        p = ws.resolve(path)
        if not p.is_dir():
            raise ToolError(f"not a directory: {path}")
        names = sorted(
            str(c.relative_to(ws.root)) + ("/" if c.is_dir() else "") for c in p.iterdir()
        )
        return "\n".join(names) or "(empty)"

    tools = [
        Tool("read_file", "Read a text file. args: {path}", read_file),
        Tool("write_file", "Write a text file. args: {path, content}", write_file),
        Tool("list_files", "List a directory. args: {path} (default '.')", list_files),
    ]
    return {t.name: t for t in tools}
