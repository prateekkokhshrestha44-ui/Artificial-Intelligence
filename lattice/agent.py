"""The agent loop: observe -> think -> act -> observe ...

The model never executes anything itself. It only *proposes* a JSON action; this
loop validates it, runs the tool, and feeds the result back. That separation is
what makes the system auditable, testable, and safe to extend.

Protocol (one JSON object per model reply):
    {"tool": "<name>", "args": {...}}     -> run a tool
    {"final": "<answer>"}                 -> finish
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .backends import Message, ModelBackend
from .tools import Tool, ToolError

MAX_OBSERVATION_CHARS = 4000  # crude guard against context rot (Phase 4 improves this)


def extract_action(reply: str) -> dict:
    """Pull the first JSON object out of a model reply.

    Small models often wrap JSON in ```json fences, add chatter before it, or
    append stray characters after it. Be strict about *what* we execute (a
    dict, validated later) but tolerant about how it is wrapped.
    """
    text = reply.strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as e:
        raise ValueError(f"malformed JSON ({e.msg})") from None
    if not isinstance(obj, dict):
        raise ValueError("reply must be a JSON object")
    return obj


def build_system_prompt(tools: dict[str, Tool]) -> str:
    listing = "\n".join(f"- {t.name}: {t.description}" for t in tools.values())
    return (
        "You are a careful local agent. Reply with exactly ONE JSON object and nothing else.\n"
        'To use a tool: {"tool": "<name>", "args": {...}}\n'
        'To finish: {"final": "<a short plain-text answer>"}\n'
        "Rules: you cannot do anything except by calling a tool. Never say a task is done "
        "until a tool result confirms it. Send ONE JSON object, then stop and wait: the system "
        "replies with the OBSERVATION. Never write OBSERVATION yourself.\n"
        f"Available tools:\n{listing}\n\n"
        "Example conversation for the task 'create a.txt containing hello':\n"
        'You (turn 1): {"tool": "write_file", "args": {"path": "a.txt", "content": "hello"}}\n'
        "System: OBSERVATION: wrote 5 chars to a.txt\n"
        'You (turn 2): {"final": "Created a.txt."}'
    )


@dataclass
class AgentResult:
    answer: str | None
    steps: int
    finished: bool
    transcript: list[Message] = field(default_factory=list)


class Agent:
    def __init__(self, backend: ModelBackend, tools: dict[str, Tool], max_steps: int = 8):
        self.backend = backend
        self.tools = tools
        self.max_steps = max_steps

    def run(self, task: str) -> AgentResult:
        messages: list[Message] = [
            {"role": "system", "content": build_system_prompt(self.tools)},
            {"role": "user", "content": task},
        ]
        for step in range(1, self.max_steps + 1):
            reply = self.backend.complete(messages)
            messages.append({"role": "assistant", "content": reply})

            try:
                action = extract_action(reply)
                # Keep only what we actually act on. Small models often append an invented
                # OBSERVATION and "final" after the action; if we stored that, they would
                # copy their own hallucination on every later turn.
                messages[-1] = {"role": "assistant", "content": json.dumps(action)}
            except ValueError as e:
                messages.append(
                    {"role": "user", "content": f"OBSERVATION: invalid reply ({e}). Send one JSON object."}
                )
                continue

            if "final" in action:
                if not isinstance(action["final"], str):
                    messages.append({"role": "user", "content": (
                        'OBSERVATION: "final" must be a plain-text string. '
                        "Use a tool to do the work first, then give a short text answer."
                    )})
                    continue
                return AgentResult(action["final"], step, True, messages)

            observation = self._run_tool(action)
            messages.append({"role": "user", "content": f"OBSERVATION: {observation}"})

        return AgentResult(None, self.max_steps, False, messages)

    def _run_tool(self, action: dict) -> str:
        name = action.get("tool")
        tool = self.tools.get(name)
        if tool is None:
            return f"error: unknown tool {name!r}. Available: {', '.join(self.tools)}"
        args = action.get("args") or {}
        try:
            out = tool.fn(**args)
        except ToolError as e:
            return f"error: {e}"
        except TypeError as e:
            return f"error: bad arguments for {name}: {e}"
        return out[:MAX_OBSERVATION_CHARS]
