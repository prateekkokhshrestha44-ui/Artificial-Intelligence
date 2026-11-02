# Lattice

A local-first agent with a deliberate knowledge boundary: **skills** and **project memory** stay on your
machine; external LLMs are a read-only knowledge oracle, queried only through a privacy gateway.

## Status: Step 1 -- the local loop

```
lattice/
  backends.py   # ModelBackend interface + Ollama + scripted fake (for tests)
  tools.py      # Workspace-jailed read_file / write_file / list_files
  agent.py      # the observe -> think -> act loop
tests/
  test_agent.py
```

## Run the tests (no model needed)

```bash
pip install -e ".[dev]" && pytest
```

## Try it with a real local model

```bash
ollama pull qwen2.5-coder:3b
python -c "
from lattice import Agent, OllamaBackend, Workspace, build_default_tools
tools = build_default_tools(Workspace('./workspace'))
print(Agent(OllamaBackend(), tools).run('Create hello.txt containing the word hi, then finish.'))
"
```

## Roadmap
1. Local loop (this step)  2. Project memory ledger  3. Skills on demand
4. Privacy gateway + external oracle  5. Hardening, HTTP API, packaging
