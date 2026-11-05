"""Controlled experiment: the same task WITH and WITHOUT the note-taking skill.

Usage:  python scripts/skills_demo.py [model] [--cpu]   (run from the repo root)

The project convention (in skills/note-taking/SKILL.md) says notes go in notes/<title-hyphenated>.md
with a fixed layout. A model that has never seen that convention cannot guess it. We check the
result with plain code, not by trusting the model's claim that it succeeded.
"""
import shutil
import sys
from pathlib import Path

from lattice import Agent, DirectorySkillRegistry, OllamaBackend, Workspace, build_default_tools

args = [a for a in sys.argv[1:] if not a.startswith("--")]
model = args[0] if args else "qwen2.5-coder:3b"
backend = OllamaBackend(model=model, num_gpu=0 if "--cpu" in sys.argv else None)

TASK = "Write a note titled Kickoff Meeting that says we start on Monday."
registry = DirectorySkillRegistry("./skills")
print("skills found:", registry.names(), "| problems:", registry.problems or "none")


def verify(root: Path) -> tuple[bool, str]:
    """Deterministic check of the convention: right path, right title line, status line."""
    path = root / "notes" / "kickoff-meeting.md"
    if not path.is_file():
        return False, f"expected file notes/kickoff-meeting.md not found (files: {[str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()]})"
    text = path.read_text()
    if not text.startswith("# Kickoff Meeting"):
        return False, "first line is not '# Kickoff Meeting'"
    if "Status: draft" not in text:
        return False, "missing 'Status: draft' line"
    return True, "file path, title and status line all follow the convention"


def run(label: str, use_skills: bool) -> bool:
    root = Path(f"./workspace_{label}")
    shutil.rmtree(root, ignore_errors=True)
    agent = Agent(backend, build_default_tools(Workspace(root)), skills=registry if use_skills else None, max_steps=6)
    print(f"\n=== {label.upper()} ===")
    result = agent.run(TASK)
    for m in result.transcript[2:]:
        print(f"  [{m['role']}] {m['content'][:170]}")
    print(f"  model says: finished={result.finished}, steps={result.steps}")
    ok, why = verify(root)
    print(f"  CHECK: {'PASS' if ok else 'FAIL'} - {why}")
    return ok


control = run("control", use_skills=False)
treatment = run("with_skills", use_skills=True)
print(f"\nSUMMARY  without skill: {'PASS' if control else 'FAIL'}   with skill: {'PASS' if treatment else 'FAIL'}")
