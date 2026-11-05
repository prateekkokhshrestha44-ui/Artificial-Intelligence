import json
import os

import pytest

from lattice import Agent, DirectorySkillRegistry, ScriptedBackend, ToolError, Workspace, build_default_tools
from lattice.skills import MAX_BODY, MAX_DESCRIPTION, SkillError, build_skill_tool, format_skill_index, parse_skill_text


def act(tool, **args):
    return json.dumps({"tool": tool, "args": args})


def final(text):
    return json.dumps({"final": text})


def write_skill(root, name, description="Does a thing. Use when asked.", body="Step 1: do the thing.", folder=None, raw=None):
    d = root / (folder or name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(raw if raw is not None else f"---\nname: {name}\ndescription: {description}\n---\n{body}\n", encoding="utf-8")


# ---- parsing and validation ----------------------------------------------------------
def test_parse_valid_skill():
    name, desc, body = parse_skill_text("---\nname: my-skill\ndescription: 'Does X. Use for Y.'\n---\nLine one\nLine two\n", "my-skill")
    assert (name, desc, body) == ("my-skill", "Does X. Use for Y.", "Line one\nLine two")


def test_parse_handles_windows_line_endings_and_bom():
    text = "﻿---\r\nname: win\r\ndescription: ok\r\n---\r\nbody here\r\n"
    assert parse_skill_text(text, "win") == ("win", "ok", "body here")


@pytest.mark.parametrize("raw, why", [
    ("no frontmatter at all", "frontmatter"),
    ("---\nname: a\ndescription: d\nbody never closed", "not closed"),
    ("---\nname: Bad Name\ndescription: d\n---\nbody", "lowercase"),
    ("---\nname: other\ndescription: d\n---\nbody", "match its folder"),
    ("---\nname: a\n---\nbody", "description is required"),
    ("---\nname: a\ndescription: d\n---\n", "no body"),
    (f"---\nname: a\ndescription: {'x' * (MAX_DESCRIPTION + 1)}\n---\nbody", "limit"),
    (f"---\nname: a\ndescription: d\n---\n{'x' * (MAX_BODY + 1)}", "limit"),
])
def test_parse_rejects_bad_skills(raw, why):
    with pytest.raises(SkillError, match=why):
        parse_skill_text(raw, "a")


# ---- the registry --------------------------------------------------------------------
def test_registry_loads_good_skills_and_reports_bad_ones_without_crashing(tmp_path):
    write_skill(tmp_path, "good-one")
    write_skill(tmp_path, "mismatch", folder="wrong-folder")
    write_skill(tmp_path, "x", raw="garbage")
    (tmp_path / "not-a-skill").mkdir()          # folder without SKILL.md is ignored silently
    (tmp_path / "stray-file.txt").write_text("hi")
    reg = DirectorySkillRegistry(tmp_path)
    assert reg.names() == ["good-one"]
    assert len(reg.problems) == 2 and any("wrong-folder" in p for p in reg.problems)


def test_missing_directory_gives_empty_registry(tmp_path):
    reg = DirectorySkillRegistry(tmp_path / "nope")
    assert reg.names() == [] and reg.suggest("anything") == []


def test_reload_picks_up_new_skills(tmp_path):
    reg = DirectorySkillRegistry(tmp_path)
    assert reg.names() == []
    write_skill(tmp_path, "late-arrival")
    reg.reload()
    assert reg.names() == ["late-arrival"]


def test_skill_that_resolves_outside_the_directory_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    write_skill(outside, "sneaky")
    root = tmp_path / "skills"
    root.mkdir()
    try:
        os.symlink(outside / "sneaky", root / "sneaky", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this system")
    reg = DirectorySkillRegistry(root)
    assert reg.names() == [] and any("outside" in p for p in reg.problems)


# ---- suggesting: the index must not grow with the library ------------------------------
def test_suggest_lists_everything_when_the_library_is_small(tmp_path):
    for n in ("alpha", "beta"):
        write_skill(tmp_path, n)
    assert [s.name for s in DirectorySkillRegistry(tmp_path).suggest("unrelated words", limit=8)] == ["alpha", "beta"]


def test_suggest_ranks_relevant_first_and_caps_large_libraries(tmp_path):
    write_skill(tmp_path, "note-taking", description="How to write project notes and name note files")
    write_skill(tmp_path, "commit-message", description="Conventions for git commit messages")
    for i in range(30):
        write_skill(tmp_path, f"filler-{i}", description="Unrelated zebra topic")
    reg = DirectorySkillRegistry(tmp_path)
    top = reg.suggest("write a note about the budget", limit=5)
    assert top[0].name == "note-taking" and len(top) <= 5
    assert all(s.name.startswith(("note", "commit")) or s.name.startswith("filler") for s in top)
    assert reg.suggest("qqqq xxxx", limit=5) == []     # big library + no match -> nothing listed


# ---- progressive disclosure ----------------------------------------------------------
def test_index_shows_descriptions_never_bodies(tmp_path):
    write_skill(tmp_path, "secret-sauce", description="Makes sauce. Use for sauce.", body="SECRET-BODY-TEXT")
    text = format_skill_index(DirectorySkillRegistry(tmp_path).suggest("sauce"))
    assert "secret-sauce: Makes sauce" in text and "SECRET-BODY-TEXT" not in text
    assert format_skill_index([]) == ""


def test_use_skill_returns_full_body_and_rejects_unknown_names(tmp_path):
    write_skill(tmp_path, "real", body="FULL-BODY-TEXT")
    tool = build_skill_tool(DirectorySkillRegistry(tmp_path))
    assert "FULL-BODY-TEXT" in tool.fn(name="real")
    for bad in ("../real", "nope", ""):
        with pytest.raises(ToolError, match="unknown skill"):
            tool.fn(name=bad)


# ---- agent integration ---------------------------------------------------------------
def make(tmp_path, replies, reg, **kw):
    backend = ScriptedBackend(replies)
    tools = build_default_tools(Workspace(tmp_path / "ws"))
    return Agent(backend, tools, skills=reg, **kw), backend, tools


def test_agent_prompt_has_index_but_not_the_body_until_the_skill_is_used(tmp_path):
    write_skill(tmp_path / "sk", "note-taking", description="How to write notes", body="BODY: save in notes/")
    reg = DirectorySkillRegistry(tmp_path / "sk")
    agent, backend, _ = make(tmp_path, [act("use_skill", name="note-taking"), final("done")], reg)
    result = agent.run("write a note")

    first_prompt = backend.calls[0][0]["content"]
    assert "note-taking: How to write notes" in first_prompt and "use_skill" in first_prompt
    assert "BODY: save in notes/" not in first_prompt                         # not loaded yet
    assert "BODY: save in notes/" in result.transcript[3]["content"]          # arrives as an observation
    # and the model's SECOND call is the first one that can see the body (as the last message)
    assert "BODY: save in notes/" not in backend.calls[0][-1]["content"]
    assert "BODY: save in notes/" in backend.calls[1][-1]["content"]


def test_agent_does_not_mutate_callers_tool_dict_and_skills_are_optional(tmp_path):
    write_skill(tmp_path / "sk", "s1")
    agent, _, tools = make(tmp_path, [final("ok")], DirectorySkillRegistry(tmp_path / "sk"))
    assert "use_skill" in agent.tools and "use_skill" not in tools
    plain = Agent(ScriptedBackend([final("ok")]), build_default_tools(Workspace(tmp_path / "w2")))
    assert "use_skill" not in plain.tools and "SKILLS --" not in plain.run("x").transcript[0]["content"]


def test_skill_workflow_end_to_end_with_scripted_model(tmp_path):
    write_skill(tmp_path / "sk", "note-taking", description="How to write notes", body="Save as notes/<title>.md")
    agent, _, _ = make(tmp_path, [
        act("use_skill", name="note-taking"),
        act("write_file", path="notes/kickoff.md", content="# Kickoff\nStatus: draft\n\nWe start Monday.\n"),
        final("Wrote the note."),
    ], DirectorySkillRegistry(tmp_path / "sk"))
    result = agent.run("Write a note titled Kickoff")
    assert result.finished and result.tool_calls == 2
    assert (tmp_path / "ws" / "notes" / "kickoff.md").read_text().startswith("# Kickoff")


def test_skills_and_memory_work_together(tmp_path):
    from lattice import Ledger

    write_skill(tmp_path / "sk", "note-taking", description="How to write notes")
    led = Ledger()
    led.add("fact", "The team standup is on Mondays", source="user")
    agent, backend, _ = make(tmp_path, [final("ok")], DirectorySkillRegistry(tmp_path / "sk"), ledger=led)
    agent.run("write a note about the Monday standup")
    prompt = backend.calls[0][0]["content"]
    assert "SKILLS --" in prompt and "PROJECT MEMORY" in prompt
    assert prompt.index("SKILLS --") < prompt.index("PROJECT MEMORY")   # memory sits closest to the task
