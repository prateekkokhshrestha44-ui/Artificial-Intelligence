import json

from lattice import Agent, ScriptedBackend, Workspace, build_default_tools


def act(tool, **args):
    return json.dumps({"tool": tool, "args": args})


def final(text):
    return json.dumps({"final": text})


def make(tmp_path, replies, max_steps=8):
    ws = Workspace(tmp_path)
    return Agent(ScriptedBackend(replies), build_default_tools(ws), max_steps), ws


def test_write_then_finish(tmp_path):
    agent, ws = make(tmp_path, [act("write_file", path="a.txt", content="hi"), final("done")])
    result = agent.run("make a.txt")
    assert result.finished and result.answer == "done" and result.steps == 2
    assert (ws.root / "a.txt").read_text() == "hi"


def test_sandbox_blocks_escape(tmp_path):
    agent, _ = make(tmp_path, [act("read_file", path="../../etc/passwd"), final("ok")])
    result = agent.run("try to escape")
    observation = result.transcript[3]["content"]
    assert "escapes workspace" in observation


def test_recovers_from_bad_json(tmp_path):
    agent, _ = make(tmp_path, ["not json at all", final("recovered")])
    result = agent.run("x")
    assert result.finished and result.answer == "recovered"
    assert "invalid reply" in result.transcript[3]["content"]


def test_unknown_tool_and_bad_args_are_reported_not_crashed(tmp_path):
    agent, _ = make(tmp_path, [act("rm_rf"), act("read_file", wrong="x"), final("ok")])
    result = agent.run("x")
    assert result.finished
    assert "unknown tool" in result.transcript[3]["content"]
    assert "bad arguments" in result.transcript[5]["content"]


def test_extract_action_tolerates_fences_chatter_and_trailing_junk():
    from lattice.agent import extract_action

    assert extract_action('```json\n{"final": "x"}\n```') == {"final": "x"}
    assert extract_action('Sure! {"final": "x"} hope that helps') == {"final": "x"}
    assert extract_action('{"final": "x"}}') == {"final": "x"}  # the stray brace seen live
    for bad in ["", "no json here", "[1, 2]", '{"final": ']:
        try:
            extract_action(bad)
        except ValueError:
            continue
        raise AssertionError(f"should have rejected {bad!r}")


def test_agent_accepts_fenced_reply(tmp_path):
    agent, _ = make(tmp_path, ['```json\n{"final": "ok"}\n```'])
    assert agent.run("x").answer == "ok"


def test_step_limit_stops_runaway_loops(tmp_path):
    agent, _ = make(tmp_path, [act("list_files")] * 3, max_steps=3)
    result = agent.run("loop forever")
    assert not result.finished and result.answer is None and result.steps == 3
