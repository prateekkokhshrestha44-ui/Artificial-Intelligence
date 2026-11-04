"""Show project memory working across two separate agent runs on a live Ollama model.

Usage:  python scripts/memory_demo.py [model] [--cpu]

Run 1 does some work. Run 2 is a NEW Agent object with a NEW conversation; the only thing
connecting them is the ledger file. Then we print what the ledger contains.
"""
import sys

from lattice import Agent, Ledger, OllamaBackend, Workspace, build_default_tools

args = [a for a in sys.argv[1:] if not a.startswith("--")]
model = args[0] if args else "qwen2.5-coder:3b"
backend = OllamaBackend(model=model, num_gpu=0 if "--cpu" in sys.argv else None)

# The ledger lives OUTSIDE the workspace jail, so the agent's file tools cannot touch it.
ledger = Ledger("./.lattice/ledger.db")
tools = build_default_tools(Workspace("./workspace"))


def run(task):
    print(f"\n=== TASK: {task}")
    result = Agent(backend, tools, ledger=ledger, max_steps=6).run(task)
    for m in result.transcript[2:]:
        print(f"  [{m['role']}] {m['content'][:160]}")
    print(f"  -> finished={result.finished} steps={result.steps} answer={result.answer!r}")


ledger.add("decision", "Project notes are written as plain text files in the workspace root", source="user")
run("Create a file named plan.txt containing the words step one.")
run("Which file did we create earlier, and what did it contain? Answer without using tools if memory tells you.")

print("\n=== LEDGER CONTENTS ===")
for e in ledger.recent(20):
    print(f"  #{e.id} [{e.kind}] ({e.source}, conf {e.confidence:.1f}) {e.text[:110]}")
