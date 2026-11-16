# Lattice: how it works, inside and out

This guide explains every part of the project, why it is built that way, and the real problems
we hit while building it. Read it top to bottom once; use the section headings after that.

## 1. What Lattice is

Lattice is an **agent with a deliberate knowledge boundary**. It is not a smaller LLM.

| Store | Holds | Lives | Status |
|---|---|---|---|
| **Project memory** | What is true about *this* project: decisions, errors, facts, next steps | Local SQLite ledger | Built (Step 2) |
| **Skills** | *How* to do things: conventions, procedures | Local files, loaded on demand | Built (Step 3) |
| **External knowledge** | General concepts and documentation | An outside LLM, asked only through a privacy gateway | Gateway built (4a); real provider adapter next (4b) |

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
- **Observed facts only**: after a run the *system* records what it observed: that the task
  finished, how many tool calls ran, and what each world-changing tool really did (for example
  `write_file(path='plan.txt') succeeded: wrote 8 chars`). The model's own final answer is **never**
  stored, because it is a claim, not an observation. The model's `remember` tool cannot write `run`
  entries, and runs that used no tools are not recorded at all.

Physics view: the ledger stores a compressed *state*, not the full *trajectory*. A superseded
entry is like a measurement update that makes the old estimate stop contributing.

Keep the ledger file **outside** the workspace (`./.lattice/`), so the agent's tools cannot reach it.

## 4b. Step 3: skills on demand

File: `lattice/skills.py`. Example skills: `skills/`.

A skill is a folder with a `SKILL.md`: a name, a one-line description, and the full instructions.

```
skills/note-taking/SKILL.md
---
name: note-taking
description: How to write project notes: where to save them, ... Use when asked to write a note.
---
1. Save the note inside the `notes/` folder. ...
```

- **Progressive disclosure**: the prompt carries only an *index* (name + description). If the task
  needs a skill, the model calls the `use_skill` tool and the full text arrives as the tool result.
  Prompt size stays small no matter how many skills exist.
- **The index does not grow with the library**: with few skills all are listed; with many, only the
  best matches for the task are (`suggest`, default limit 8).
- **Bad skills are skipped, not fatal**: wrong name, missing description, oversized body, or a symlink
  pointing outside the skills folder is recorded in `registry.problems` and ignored.
- **Pluggable source**: the agent depends on a small `SkillRegistry` interface, so skills could later
  come from a shared service with the same checks.
- **Trust**: skill text is delivered as instructions to follow, so load skills only from folders you
  control. This is the opposite of memory, which is always labelled as evidence.

Skills vs memory: memory says *what is true here* (a fact that can go stale and is superseded); a skill
says *how we do things here* (a procedure that is edited on purpose).

How we test it: `scripts/skills_demo.py` runs the same task with and without the skill, then checks the
result with plain code (right path, right title line) instead of trusting the model's "done".

Physics view: a skill is a pre-computed solution method. You do not re-derive it each time; you look it
up in the index and apply it only to the problem that needs it. The control run is the experiment's
control group.

## 4c. Step 4a: the privacy gateway

File: `lattice/gateway.py`. Try it offline: `python scripts/gateway_demo.py`.

Everything that leaves the machine for an external model goes through one object, the `Gateway`. It
**fails closed**: if it cannot show a question is safe, it does not send it.

```
question -> hard blocks -> abstract -> VERIFY -> approval -> external model -> audit log
```

1. **Hard blocks**: empty, too long (600 chars), contains a code block, or contains a stack trace. Code
   cannot be safely abstracted, so it is refused, not "cleaned".
2. **Abstract**: identifying content becomes a generic placeholder: secrets and keys, URLs, emails, IPs,
   internal hostnames, file paths, file names, `code spans`, quoted strings, line numbers, long numbers,
   CONSTANTS, ClassNames and function_names. Public names (PostgreSQL, Node.js ...) are left alone.
   "Why is our PaymentProcessor class failing on line 847?" becomes
   "Why is our [class] class failing on [position]?".
3. **Vocabulary**: the gateway learns *your* words locally from the workspace: identifiers, identifier-like
   file and folder names (not plain words like `plan` or `billing`, which would make ordinary questions look
   private; list those yourself if they are), and the **actual values of secrets** found in `.env`/config files (a bare password has no shape a
   pattern could recognise, so it must be learned). You can add terms (`Vocabulary(["Falcon"])`).
4. **Verify**: the detectors run again on the OUTPUT. Placeholders are designed so abstraction is idempotent;
   if anything is still detectable, the question is blocked. If too little general content remains
   ("Fix [class] in [file]"), it is blocked as well.
5. **Approval**: default is to ask the user for every outbound question and show exactly what would be sent.
   No approver, or an approver that crashes, means **deny**. Modes: `always` (default), `project` (only when
   something was abstracted), `never` (explicit opt-in; blocked questions still never leave).
6. **Local-only mode**: `Gateway(..., enabled=False)` sends nothing, ever.
7. **Audit log** (`.lattice/audit.jsonl`): each attempt records *what was sent*, the answer, the decision, and a
   **hash** of the original question, never the original text, so the log itself cannot leak.
8. **The answer is untrusted reference material**: the tool labels it "NOT instructions", it is never stored
   as trusted memory, and the external model never sees project files, memory or skills.

Honest limits (tested as such, see `test_known_limitation_*`):
- A sensitive plain-English word that is in neither the vocabulary nor a recognisable shape (a codename you
  never listed) passes through. Fix: list it.
- A bare secret that appears in no project file and has no `password =` label cannot be recognised.
- Abstraction removes details, so a project-specific question gets a more general answer.
These are why approval is on by default, and why the audit log exists.

How we test it: a leak matrix of 20 sensitive strings x 4 question templates (80 questions) asserts that none
of them appears in anything the external model receives, plus tests for each detector, idempotence, the approval
and audit behaviour, and false positives (TCP/IP, and/or, apostrophes are left alone).

Physics view: the gateway is a **filter with a verified output**, like a band-pass with a monitor on the far
side. You do not trust the filter design alone; you measure what comes out. The leak test is that measurement.

### 4d. Step 4b: verified local rewriting

Plain abstraction is safe but blunt ("Why is our [class] class failing on [position]?"). A local model can
reword that into a better general question. `Gateway(..., rewriter=LocalRewriter(OllamaBackend()))`.
Try it: `python scripts/rewrite_demo.py --cpu`.

The rule that makes this safe: **the rewriter is never trusted, only checked.**
- It sees only the already-abstracted text, never the original question.
- Its output goes through the same detectors as everything else (identifiers, paths, secrets, vocabulary ...),
  and is also rejected if empty, too short, much longer than the input, or containing code or a stack trace.
- If it fails any check, or the local model is down, the plain abstracted text is used instead. A rewriter
  can improve a question but can never make one leak.
- Whether a rewrite happened is shown to the approver and recorded in the audit log. When a rewrite is NOT
  used, `reasons` says why (model call failed / reply empty / too long / contained code / contained identifying
  content), naming only the kind of problem, never the rejected text.

How we test it: a *hostile rewriter* that deliberately tries to put each of the 20 sensitive strings back in
is run through the gateway; none gets out. We also ran a mutation check: with the re-verification step
removed, 27 tests fail, so the tests genuinely depend on the check.

Known limit: **semantic drift**. A small model may reword the question into a slightly different one ("fail
intermittently under load" when the user never said so). The detectors cannot judge meaning, so the approval
step, which shows the exact text, is what catches this.

## 5. Problems we hit on real hardware (and the fixes)

These are the lessons from the first live run. They are why the code looks the way it does.

| Symptom | Cause | Fix |
|---|---|---|
| Gibberish, or `HTTP 500: token repeat limit reached` | Ollama's GPU path misbehaving on some laptops/drivers (intermittent) | `OllamaBackend(num_gpu=0)` or env `LATTICE_NUM_GPU=0` forces CPU; `scripts/ollama_matrix.py` finds which settings work |
| Reply rejected though it held valid JSON | Model wrapped JSON in a code fence or added stray text | `extract_action` takes the first JSON object and ignores the rest |
| `ModuleNotFoundError` / unknown keyword for new code | Stale copy of the package, or not installed in the venv | `pip install -e .` from the repo root; check `python -c "import lattice; print(lattice.__file__)"` |
| Model said "done" without calling a tool | Small models claim success | `final` must be plain text; prompt says never claim done before a tool confirms; real fix is verification (Step 5) |
| Model wrote its own `OBSERVATION:` lines and repeated forever | It copied the pattern, and we stored its invented text in history | Store only the parsed action in history; Ollama stop sequence on `OBSERVATION:` |
| Model answered with made-up names that matched a prompt example | Small models copy examples that sit above retrieved memory | Example uses obviously fake names and is labelled format-only; memory header says to prefer memory over examples |
| "file" did not find a note about "files" | Plain full-text search treats word variants as different words | FTS5 `porter` stemming; older ledgers are rebuilt automatically |
| **Memory poisoning**: a wrong answer came back as "evidence" | The system had stored the model's wrong answer as a trusted entry, and it ranked first when the question repeated | Store only observed facts, never model claims. After upgrading, delete old demo ledgers (`.lattice/ledger.db`) because old entries are not cleaned automatically |
| Request times out | First call is slow, or the GPU stalls | `--cpu`; check `ollama ps`; restart Ollama |

General principle: **trust the system you control, not the model's output.** This applies to memory too:
anything that stores what the model *said* and later feeds it back as trusted will poison itself. The real tool
result said "wrote 2 chars" while the model's invented one said 3. Only the first is evidence.

## 6. Running and testing

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                                # no model needed
ollama pull qwen2.5-coder:3b
python scripts/live_demo.py --cpu                     # real model, real tools
python scripts/memory_demo.py --cpu                   # memory across two runs
python scripts/skills_demo.py --cpu                   # same task with vs. without a skill
```

`--cpu` is only for machines where the GPU path is flaky.

## 7. Roadmap

3. **Skills on demand** (done): a compact index of skills; the model picks one, then only that skill loads.
4. **Privacy gateway + external oracle**: (4a done) abstract, verify, approve, audit; (4b done) a local model may reword the question while the
   code re-verifies it; (4c next) a real external provider adapter.
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
