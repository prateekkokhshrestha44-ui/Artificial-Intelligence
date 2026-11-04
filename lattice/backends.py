"""Model backends: the *only* place that knows how to talk to a language model.

The agent depends on the tiny `ModelBackend` interface, not on any vendor.
Swap Ollama for llama.cpp, vLLM, or a cloud API by writing one new class.
"""
from __future__ import annotations

import json
import os
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
        json_mode: bool = False,
        temperature: float = 0.2,
        repeat_penalty: float = 1.1,
        num_ctx: int = 4096,
        num_gpu: int | None = None,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.json_mode = json_mode  # grammar-constrained JSON; try it once the plain path works
        self.temperature = temperature  # low: tool-calling wants little randomness, but 0 can loop
        self.repeat_penalty = repeat_penalty
        self.num_ctx = num_ctx
        # num_gpu=0 forces CPU. Needed on machines where Ollama's GPU path is broken
        # (symptom: gibberish or "token repeat limit reached"). Env var sets a default.
        if num_gpu is None and os.environ.get("LATTICE_NUM_GPU"):
            num_gpu = int(os.environ["LATTICE_NUM_GPU"])
        self.num_gpu = num_gpu

    def build_payload(self, messages: list[Message]) -> dict:
        options = {
            "temperature": self.temperature,
            "repeat_penalty": self.repeat_penalty,
            "num_ctx": self.num_ctx,
        }
        if self.num_gpu is not None:
            options["num_gpu"] = self.num_gpu
        payload = {"model": self.model, "messages": messages, "stream": False, "options": options}
        if self.json_mode:
            payload["format"] = "json"
        return payload

    def complete(self, messages: list[Message]) -> str:
        body = json.dumps(self.build_payload(messages)).encode()
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)["message"]["content"]
