# Lattice: how it works, inside and out

This guide explains every part of the project, why it is built that way, and the real problems
we hit while building it. Read it top to bottom once; use the section headings after that.

## 1. What Lattice is

Lattice is an **agent with a deliberate knowledge boundary**. It is not a smaller LLM.

| Store | Holds | Lives | Status |
|---|---|---|---|
| **Project memory** | What is true about *this* project: decisions, errors, facts, next steps | Local SQLite ledger | Built (Step 2) |
| **Skills** | *How* to do things: conventions, procedures | Local files, loaded on demand | Planned (Step 3) |
| **External knowledge** | General concepts and documentation | An outside LLM, asked only through a privacy gateway | Planned (Step 4) |

The three are kept separate because they differ in persistence, privacy and trust.

## 2. Architecture

```
            task
              |
        +-----v------+      relevant entries      +----------------+
        |   Agent    |<---------------------------|  Ledger (SQLite)|
        |   (loop)   |--------- outcome --------->|  typed, trusted |
        +--+------+--+                            +----------------+
           |      |
   prompt  |      | validated tool calls
           v      v
   +-----------+ +--------------------+
   | Backend   | | Tools (sandboxed)  |
   | (Ollama)  | | read/write/list in |
   +-----------+ | one Workspace dir  |
                 +--------------------+
```

Rule that shapes everything: **the model only proposes; the code decides.** The model emits
JSON text. The loop validates it, runs the tool, and feeds back the real result.

## 3. Step 1: the local loop

Files: `lattice/backends.py`, `lattice/tools.py`, `lattice/agent.py`.

- **Backend** (`backends.py`): the only code that talks to a model. The agent depends on one
  method, `complete(messages) -> text`. Ollama is one implementation; `ScriptedBackend` is a
  fake that replays fixed replies so tests are deterministic. Swapping in another model or a
  cloud API means writing one small class.
- **Tools** (`tools.py`): `read_file`, `write_file`, `list_files`, all confined to a `Workspace`
  folder. A path like `../../etc/passwd` is refused by code, not by asking the model nicely.
- **Loop** (`agent.py`): observe, think, act, repeat. Protocol: the model replies with one JSON
  object, either `{"tool": ..., "args": ...}` or `{"final": "..."}`. A step limit stops runaways.

Physics view: the agent is a dynamical system whose state is the message history. Tools are the
only coupling to the outside world. The workspace jail is a boundary condition. The scripted
backend is a controlled input, so the loop can be tested like an instrument.

## 4. Step 2: project memory

File: `lattice/memory.py`.

- **Typed entries**: `decision`, `error`, `fact`, `next_step`, `run`. Not a chat log.
- **Provenance**: each entry has `source` (`system`, `user`, `agent`), a timestamp and a
  confidence. Things the model writes get 0.7; things the system observes get 1.0.
- **Supersede**: a new entry can replace an old one. The old one stays for audit but is never
  retrieved, so stale facts don't steer the agent.
- **Retrieval**: SQLite FTS5 with BM25 ranking, falling back to `LIKE` if FTS5 is missing. Only the
  top few relevant entries enter the prompt, so cost does not grow with ledger size.
- **Evidence, not instructions**: memory is injected under a header saying it may be outdated and
  that commands inside it must not be followed. This blunts stored prompt injection.
- **System-written outcomes**: after each run the *system* records the result. The model's
  `remember` tool cannot write `run` entries, so it cannot fake its own track record.

Physics view: the ledger stores a compressed *state*, not the full *trajectory*. A superseded
entry is like a measurement update that makes the old estimate stop contributing.

Keep the ledger file **outside** the workspace (`./.lattice/`), so the agent's tools cannot reach it.

## 5. Problems we hit on real hardware (and the fixes)

These are the lessons from the first live run. They are why the code looks the way it does.

| Symptom | Cause | Fix |
|---|---|---|
| Gibberish, or `HTTP 500: token repeat limit reached` | Ollama's GPU path misbehaving on some laptops/drivers (intermittent) | `OllamaBackend(num_gpu=0)` or env `LATTICE_NUM_GPU=0` forces CPU; `scripts/ollama_matrix.py` finds which settings work |
| Reply rejected though it held valid JSON | Model wrapped JSON in a code fence or added stray text | `extract_action` takes the first JSON object and ignores the rest |
| `ModuleNotFoundError` / unknown keyword for new code | Stale copy of the package, or not installed in the venv | `pip install -e .` from the repo root; check `python -c "import lattice; print(lattice.__file__)"` |
| Model said "done" without calling a tool | Small models claim success | `final` must be plain text; prompt says never claim done before a tool confirms; real fix is verification (Step 5) |
| Model wrote its own `OBSERVATION:` lines and repeated forever | It copied the pattern, and we stored its invented text in history | Store only the parsed action in history; Ollama stop sequence on `OBSERVATION:` |
| Request times out | First call is slow, or the GPU stalls | `--cpu`; check `ollama ps`; restart Ollama |

General principle: **trust the system you control, not the model's output.** The real tool
result said "wrote 2 chars" while the model's invented one said 3. Only the first is evidence.

## 6. Running and testing

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                                # no model needed
ollama pull qwen2.5-coder:3b
python scripts/live_demo.py --cpu                     # real model, real tools
python scripts/memory_demo.py --cpu                   # memory across two runs
```

`--cpu` is only for machines where the GPU path is flaky.

## 7. Roadmap

3. **Skills on demand**: a compact index of skills; the model picks one, then only that skill loads.
4. **Privacy gateway + external oracle**: classify a question as concept vs. project, abstract it,
   redact as a backstop, require explicit approval, log every outbound query. Built last on purpose.
5. **Hardening and packaging**: system-side verification of outcomes (does the file exist?),
   OS-level sandboxing, an HTTP API so other software can call Lattice, tracing and metrics, and
   packaging for distribution.

Design intent for integration and scale: the backend, tools and ledger are interfaces, so each can
be swapped (other models, a shared database, remote tools) without touching the loop. These
properties are goals for later steps, not claims about what exists today.

## 8. Contributing workflow

- Make small commits; one idea per commit.
- Run `pytest` before every commit; do not commit a red suite.
- Message format: a short summary line, then a paragraph on *why*.
- Never commit `.venv/`, `workspace/`, `.lattice/` or `.env` (they are in `.gitignore`).
