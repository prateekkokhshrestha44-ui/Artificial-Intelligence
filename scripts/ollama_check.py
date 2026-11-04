"""Diagnose Ollama WITHOUT the agent: is the model itself producing sane text?

Usage:  python scripts/ollama_check.py [model]

Interpretation:
  - Step 3 gibberish  -> problem is Ollama / model / GPU, not Lattice.
  - Step 3 fine, 4 bad -> JSON mode is the problem; keep json_mode=False.
  - Everything fine    -> the agent should work; rerun your smoke test.
"""
import json
import sys
import urllib.request

HOST = "http://localhost:11434"
model = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5-coder:3b"


def post(path, payload):
    req = urllib.request.Request(
        HOST + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"\n   HTTP {e.code}: {e.read().decode(errors='replace')}")


print("1) server reachable?")
try:
    tags = json.load(urllib.request.urlopen(HOST + "/api/tags", timeout=5))
    names = [m["name"] for m in tags["models"]]
    print("   yes. installed models:", names)
    if model not in names:
        print(f"   WARNING: {model!r} not installed. Run: ollama pull {model}")
except Exception as e:
    sys.exit(f"   NO: {e}. Start the server with: ollama serve")

print("\n2) version:", json.load(urllib.request.urlopen(HOST + "/api/version")).get("version"))


def chat(content, **extra):
    r = post("/api/chat", {"model": model, "stream": False,
                           "options": {"temperature": 0}, "messages": [{"role": "user", "content": content}], **extra})
    return r["message"]["content"]


print("\n3) plain question (expect: a sensible sentence containing 'Paris'):")
print("  ", repr(chat("What is the capital of France? Answer in one short sentence.")[:200]))

print("\n4) JSON-mode question (expect: a JSON object):")
print("  ", repr(chat('Reply with JSON {"answer": "<capital of France>"}', format="json")[:200]))
