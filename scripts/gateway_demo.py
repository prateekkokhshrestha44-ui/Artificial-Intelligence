"""See exactly what the privacy gateway would let leave your machine. Offline: no model, no account.

Usage (from the repo root):
    python scripts/gateway_demo.py                          # built-in sample questions
    python scripts/gateway_demo.py "your question" "another"  # your own questions
    python scripts/gateway_demo.py --workspace ./workspace   # also learn identifiers/secrets from a folder
    python scripts/gateway_demo.py --term Falcon --term "Acme Corp" ...   # words you want treated as private
    python scripts/gateway_demo.py --interactive             # full flow: you approve each send (fake external model)
"""
import sys

from lattice.gateway import AuditLog, FakeOracle, Gateway, Vocabulary, console_approver

argv = sys.argv[1:]
workspace, terms, questions, interactive = None, [], [], False
i = 0
while i < len(argv):
    if argv[i] == "--workspace":
        workspace, i = argv[i + 1], i + 2
    elif argv[i] == "--term":
        terms.append(argv[i + 1]); i += 2
    elif argv[i] == "--interactive":
        interactive, i = True, i + 1
    elif argv[i].startswith("--"):
        sys.exit(f"unknown option {argv[i]!r}. Options: --workspace PATH, --term WORD, --interactive "
                 "(this demo never uses a model, so there is no --cpu)")
    else:
        questions.append(argv[i]); i += 1

SAMPLES = [
    "What is the syntax for async context managers in Python 3.12?",
    "Why is our PaymentProcessor class failing on line 847?",
    "Why does charge_customer_card in billing/payments.py return None?",
    "My config has password = hunter2 and key sk-live-abcdef1234567890abcd, host 10.1.2.3",
    "Why does PostgreSQL ignore my index when Node.js sends a prepared statement?",
    "Fix PaymentProcessor in billing.py",
    "Here is my code:\n```python\nprint(secret)\n```",
]

vocab = Vocabulary.from_workspace(workspace, extra=terms) if workspace else Vocabulary(terms)
print(f"vocabulary: {len(vocab)} project-specific terms learned" + (f" from {workspace}" if workspace else ""))
oracle = FakeOracle(lambda q: "(fake external answer)")
gateway = Gateway(oracle, vocab, approver=console_approver if interactive else None, audit=AuditLog("./.lattice/audit.jsonl"))

for q in questions or SAMPLES:
    shown = q.replace("\n", "\\n")
    if interactive:
        print(f"\nYOU ASKED : {shown}")
        r = gateway.ask(q)
        print(f"RESULT    : {r.status}" + (f" ({r.detail})" if r.detail else ""))
    else:
        o = gateway.prepare(q)
        print(f"\nORIGINAL  : {shown}")
        print(f"DECISION  : {o.decision}")
        print(f"WOULD SEND: {o.text if o.decision != 'blocked' else '(nothing)'}")
        if o.reasons:
            print(f"WHY       : {'; '.join(o.reasons)}")

if interactive:
    print("\nWhat the external model actually received:")
    for sent in oracle.received:
        print("  -", sent)
    print("Audit log written to ./.lattice/audit.jsonl")
