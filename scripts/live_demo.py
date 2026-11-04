"""Run the real agent against a live Ollama model and print the conversation.

Usage:  python scripts/live_demo.py [model] [--cpu]
        (or set LATTICE_NUM_GPU=0 instead of --cpu)
"""
import sys

from lattice import Agent, OllamaBackend, Workspace, build_default_tools

args = [a for a in sys.argv[1:] if not a.startswith("--")]
model = args[0] if args else "qwen2.5-coder:3b"
backend = OllamaBackend(model=model, num_gpu=0 if "--cpu" in sys.argv else None)

task = "Create a file named hello.txt containing the word hi, then finish."
result = Agent(backend, build_default_tools(Workspace("./workspace")), max_steps=8).run(task)

print("--- conversation ---")
for m in result.transcript[2:]:
    print(f"[{m['role']}] {m['content'][:200]}")
print("\nfinished:", result.finished, "| steps:", result.steps)
print("answer  :", result.answer)
