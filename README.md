# Lattice

A local-first agent with a deliberate knowledge boundary: **skills** and **project memory** stay on your
machine; external LLMs are a read-only knowledge oracle, queried only through a privacy gateway.

> **New here? Read [docs/GUIDE.md](docs/GUIDE.md)** -- it explains every part, the design rules, and the
> real problems we hit on live hardware (and their fixes).

## Status: Steps 1-4b done (local loop, project memory, skills, privacy gateway with verified local rewriting)

```
lattice/
  backends.py   # ModelBackend interface + Ollama + scripted fake (for tests)
  tools.py      # Workspace-jailed read_file / write_file / list_files
  agent.py      # the observe -> think -> act loop (+ optional ledger)
  memory.py     # SQLite project-memory ledger: typed, provenance, supersede, FTS search
  skills.py     # skills on demand: compact index + use_skill tool (progressive disclosure)
  gateway.py    # privacy gateway: abstract -> verify -> approve -> audit -> external model
skills/         # example skills (note-taking, commit-message)
tests/
  test_agent.py, test_memory.py, test_skills.py, test_gateway.py, test_rewriter.py
docs/
  GUIDE.md      # architecture, concepts, troubleshooting, roadmap
scripts/
  live_demo.py, memory_demo.py, skills_demo.py, gateway_demo.py, rewrite_demo.py, ollama_check.py, ollama_matrix.py
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
1. Local loop (done)  2. Project memory ledger (done)  3. Skills on demand (done)  4a. Privacy gateway (done)  4b. Verified local rewriting (done)
4. Privacy gateway + external oracle  5. Hardening, HTTP API, packaging

## Project memory (Step 2)

```python
from lattice import Agent, Ledger, OllamaBackend, Workspace, build_default_tools
ledger = Ledger("./.lattice/ledger.db")          # keep OUTSIDE the agent's workspace
agent = Agent(OllamaBackend(), build_default_tools(Workspace("./workspace")), ledger=ledger)
```

Live demo: `python scripts/memory_demo.py --cpu`  (add `--cpu` only if your GPU path is flaky).

## Skills (Step 3)

```python
from lattice import Agent, DirectorySkillRegistry, OllamaBackend, Workspace, build_default_tools
skills = DirectorySkillRegistry("./skills")      # each skill is skills/<name>/SKILL.md
agent = Agent(OllamaBackend(), build_default_tools(Workspace("./workspace")), skills=skills)
```

Live experiment: `python scripts/skills_demo.py --cpu` runs one task with and without a skill and verifies the result.

## Privacy gateway (Step 4a)

```python
from lattice import Gateway, Vocabulary, FakeOracle, build_oracle_tool
vocab = Vocabulary.from_workspace("./workspace", extra=["Falcon"])     # learns your identifiers and secret values
gateway = Gateway(FakeOracle(), vocab, approver=my_approve_function)    # swap FakeOracle for a real provider later
tools = {**build_default_tools(ws), **build_oracle_tool(gateway)}       # gives the agent an ask_external tool
```

See what would leave your machine, offline: `python scripts/gateway_demo.py`.
