"""Lattice: a local-first agent with a deliberate knowledge boundary."""
from .agent import Agent, AgentResult
from .backends import ModelBackend, OllamaBackend, ScriptedBackend
from .gateway import AuditLog, FakeOracle, Gateway, Oracle, Vocabulary, build_oracle_tool
from .memory import Entry, Ledger, build_memory_tools
from .skills import DirectorySkillRegistry, Skill, SkillError, SkillRegistry
from .tools import Tool, ToolError, Workspace, build_default_tools

__all__ = [
    "Agent", "AgentResult", "AuditLog", "DirectorySkillRegistry", "Entry", "FakeOracle", "Gateway", "Ledger",
    "ModelBackend", "OllamaBackend", "Oracle", "ScriptedBackend", "Skill", "SkillError", "SkillRegistry", "Tool",
    "ToolError", "Vocabulary", "Workspace", "build_default_tools", "build_memory_tools", "build_oracle_tool",
]
