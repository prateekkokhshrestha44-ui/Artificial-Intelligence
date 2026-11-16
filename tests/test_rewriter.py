import pytest

from lattice import FakeOracle, Gateway, LocalRewriter, ScriptedBackend, Vocabulary
from lattice.gateway import _clean_rewrite
from test_gateway import SENSITIVE, make_project

Q = "Why is our PaymentProcessor class failing on line 847?"       # abstracts to: ... our [class] class ... [position]?
ABSTRACTED = "Why is our [class] class failing on [position]?"


class StubRewriter:
    """A rewriter whose output we control, to test the gateway's checks."""

    def __init__(self, output):
        self.output, self.seen = output, []

    def rewrite(self, text):
        self.seen.append(text)
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def gw(rewriter, oracle=None, **kw):
    return Gateway(oracle or FakeOracle(), rewriter=rewriter, approver=lambda o: True, **kw)


# ---- cleaning what a chatty local model says --------------------------------------------------
@pytest.mark.parametrize("reply, expected", [
    ("Why might a class fail under load?", "Why might a class fail under load?"),
    ('"Why might a class fail under load?"', "Why might a class fail under load?"),
    ("Question: Why might a class fail?", "Why might a class fail?"),
    ("Rewritten question: Why might a class fail?\nHope that helps!", "Why might a class fail?"),
    ("\n\n  Why might a class fail?  \n", "Why might a class fail?"),
    ("", ""),
    ("   \n  ", ""),
])
def test_clean_rewrite(reply, expected):
    assert _clean_rewrite(reply) == expected


def test_local_rewriter_sends_instructions_and_only_the_abstracted_text():
    backend = ScriptedBackend(["Why might a class fail intermittently?"])
    out = LocalRewriter(backend).rewrite(ABSTRACTED)
    system, user = backend.calls[0]
    assert system["role"] == "system" and "outside expert" in system["content"] and "placeholders" in system["content"]
    assert user["content"] == ABSTRACTED and out == "Why might a class fail intermittently?"


# ---- the gateway accepts good rewrites and rejects bad ones ----------------------------------------
def test_good_rewrite_is_used_and_flagged():
    oracle = FakeOracle()
    g = gw(StubRewriter("Why might a class fail intermittently when handling retries?"), oracle)
    o = g.prepare(Q)
    assert o.decision == "abstracted" and o.rewritten is True
    assert o.text == "Why might a class fail intermittently when handling retries?"
    assert "reworded by the local model" in " ".join(o.reasons)
    g.ask(Q)
    assert oracle.received == [o.text]


def test_rewriter_never_sees_the_original_question():
    stub = StubRewriter("Why might a class fail?")
    gw(stub).prepare(Q)
    assert stub.seen == [ABSTRACTED]
    assert "PaymentProcessor" not in " ".join(stub.seen) and "847" not in " ".join(stub.seen)


@pytest.mark.parametrize("bad", [
    "Why does charge_card fail?",                    # identifier shape
    "Why does PaymentProcessor fail?",              # class shape
    "Why does billing.py fail on retries?",         # file name
    "Why does /srv/app/main fail on retries?",      # path
    "Why does it fail with sk-live-abcdef1234567890abcd?",  # secret
    "Why does it fail at line 12?",                 # position
    "Why does the cfo@acmecorp.com mailer fail?",   # email
    "Why?",                                         # too short
    "",                                             # empty
    "x " * 300,                                     # ballooned
    "Why?\n```python\nprint(1)\n```",               # code block
    ["not", "a", "string"],                         # wrong type
])
def test_bad_rewrites_are_rejected_and_we_fall_back_to_plain_abstraction(bad):
    oracle = FakeOracle()
    g = gw(StubRewriter(bad), oracle)
    o = g.prepare(Q)
    assert o.rewritten is False and o.text == ABSTRACTED and o.decision == "abstracted"
    g.ask(Q)
    assert oracle.received == [ABSTRACTED]


def test_rewriter_that_crashes_falls_back_instead_of_failing_the_question():
    g = gw(StubRewriter(ConnectionError("ollama is down")))
    o = g.prepare(Q)
    assert o.text == ABSTRACTED and o.rewritten is False


def test_unchanged_rewrite_is_not_reported_as_rewritten():
    o = gw(StubRewriter(ABSTRACTED)).prepare(Q)
    assert o.text == ABSTRACTED and o.rewritten is False


def test_rewriter_is_not_called_when_nothing_was_abstracted_or_when_blocked():
    stub = StubRewriter("Why might a class fail?")
    g = gw(stub)
    assert g.prepare("What is a mutex in operating systems?").decision == "allow"
    assert g.prepare("Why?\n```code```").decision == "blocked"
    assert g.prepare("Fix PaymentProcessor in billing.py").decision == "blocked"
    assert stub.seen == []


def test_audit_log_records_that_a_rewrite_happened(tmp_path):
    from lattice import AuditLog

    audit = AuditLog(tmp_path / "a.jsonl")
    gw(StubRewriter("Why might a class fail intermittently?"), audit=audit).ask(Q)
    event = audit.events[0]
    assert event["rewritten"] is True and event["outbound"] == "Why might a class fail intermittently?"
    assert "PaymentProcessor" not in (tmp_path / "a.jsonl").read_text()


def test_gateway_without_a_rewriter_behaves_exactly_as_before():
    o = Gateway(FakeOracle()).prepare(Q)
    assert o.text == ABSTRACTED and o.rewritten is False


# ---- THE KEY TEST: a rewriter built to leak cannot make anything leak -----------------------------
@pytest.mark.parametrize("secret", SENSITIVE)
def test_hostile_rewriter_cannot_smuggle_any_sensitive_string_out(tmp_path, secret):
    vocab = Vocabulary.from_workspace(make_project(tmp_path / "proj"), extra=["Falcon", "Acme"])
    oracle = FakeOracle()
    plain = Gateway(FakeOracle(), vocab).prepare(Q).text     # what plain abstraction alone produces
    hostile = StubRewriter(f"Why does {secret} keep failing under heavy load?")
    g = Gateway(oracle, vocab, approver=lambda o: True, rewriter=hostile)
    g.ask(Q)
    assert hostile.seen, "the rewriter should have been consulted"
    for sent in oracle.received:
        assert secret.lower() not in sent.lower(), f"{secret!r} smuggled out via the rewriter: {sent!r}"
    assert oracle.received == [plain]            # the hostile text was rejected; plain abstraction went out


# ---- the gateway says WHY a rewrite was not used, without ever repeating the rejected text -----------
@pytest.mark.parametrize("output, expected", [
    (ConnectionError("down"), "model call failed (ConnectionError)"),
    ("", "empty or too short"),
    ("x " * 300, "far longer"),
    ("Why does a class fail on retries?\n```c x```", "code or a stack trace"),
    ("Why does charge_card fail on retries?", "identifying content (identifier)"),
    (["not text"], "not text"),
])
def test_rejection_notes_explain_the_kind_of_problem(output, expected):
    o = gw(StubRewriter(output)).prepare(Q)
    notes = [r for r in o.reasons if r.startswith("local rewrite not used")]
    assert len(notes) == 1 and expected in notes[0]


def test_rejection_notes_never_contain_the_rejected_text():
    leaky = "Why does PaymentProcessor in billing.py fail with sk-live-abcdef1234567890abcd?"
    o = gw(StubRewriter(leaky)).prepare(Q)
    joined = " ".join(o.reasons)
    for piece in ("PaymentProcessor", "billing.py", "sk-live"):
        assert piece not in joined


def test_no_note_when_the_model_simply_returns_the_text_unchanged_or_when_accepted():
    assert not [r for r in gw(StubRewriter(ABSTRACTED)).prepare(Q).reasons if "not used" in r]
    assert not [r for r in gw(StubRewriter("Why might a class fail on retries?")).prepare(Q).reasons if "not used" in r]
