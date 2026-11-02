"""Model backends: the *only* place that knows how to talk to a language model.

The agent depends on the tiny `ModelBackend` interface, not on any vendor.
Swap Ollama for llama.cpp, vLLM, or a cloud API by writing one new class.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Protocol

Message = dict  # {"role": "system" | "user" | "assistant", "content": str}


class ModelBackend(Protocol):
    def complete(self, messages: list[Message]) -> str:
        """Take a conversation, return the model's next reply as text."""
        ...


class ScriptedBackend:
    """A fake model that replays canned replies. Used for deterministic tests."""

    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self.calls: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> str:
        self.calls.append(list(messages))
        if not self._replies:
            raise RuntimeError("ScriptedBackend ran out of replies")
        return self._replies.pop(0)


class OllamaBackend:
    """Talks to a local Ollama server (https://ollama.com). No extra dependencies."""

    def __init__(
        self,
        model: str = "qwen2.5-coder:3b",
        host: str = "http://localhost:11434",
        timeout: float = 120.0,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def complete(self, messages: list[Message]) -> str:
        body = json.dumps(
            {"model": self.model, "messages": messages, "stream": False, "format": "json"}
        ).encode()
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)["message"]["content"]
