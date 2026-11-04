"""Try several Ollama option sets and show which ones give sane output.

Usage:  python scripts/ollama_matrix.py [model]
"""
import json
import sys
import time
import urllib.error
import urllib.request

HOST = "http://localhost:11434"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5-coder:3b"
PROMPT = "What is the capital of France? Answer in one short sentence."

CASES = {
    "A. Ollama defaults (no options)": {},
    "B. temperature 0": {"temperature": 0},
    "C. temperature 0.2 + repeat_penalty 1.1": {"temperature": 0.2, "repeat_penalty": 1.1},
    "D. num_ctx 4096 only": {"num_ctx": 4096},
    "E. like C but CPU only (num_gpu 0)": {"temperature": 0.2, "repeat_penalty": 1.1, "num_gpu": 0},
}


def run(options):
    body = json.dumps({
        "model": MODEL, "stream": False, "options": options,
        "messages": [{"role": "user", "content": PROMPT}],
    }).encode()
    req = urllib.request.Request(HOST + "/api/chat", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return "OK   ", json.load(r)["message"]["content"]
    except urllib.error.HTTPError as e:
        return "FAIL ", f"HTTP {e.code}: {e.read().decode(errors='replace')}"
    except Exception as e:
        return "FAIL ", repr(e)


for name, opts in CASES.items():
    t = time.time()
    status, text = run(opts)
    print(f"{status}{name}  ({time.time() - t:.0f}s)")
    print("      ", repr(text[:160]))
