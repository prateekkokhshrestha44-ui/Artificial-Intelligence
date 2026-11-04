"""Lattice: a local-first agent with a deliberate knowledge boundary."""
from .agent import Agent, AgentResult
from .backends import ModelBackend, OllamaBackend, ScriptedBackend
from .memory import Entry, Ledger, build_memory_tools
from .tools import Tool, ToolError, Workspace, build_default_tools

__all__ = [
    "Agent", "AgentResult", "Entry", "Ledger", "ModelBackend", "OllamaBackend", "ScriptedBackend",
    "Tool", "ToolError", "Workspace", "build_default_tools", "build_memory_tools",
]
