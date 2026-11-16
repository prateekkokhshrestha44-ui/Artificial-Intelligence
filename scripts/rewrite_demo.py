"""Compare plain abstraction with local-model rewriting, side by side. Uses your LOCAL Ollama model only.

Usage (from the repo root):
    python scripts/rewrite_demo.py [--model qwen2.5-coder:3b] [--cpu] [--workspace PATH] [--term WORD ...] ["question" ...]

Nothing is sent anywhere. The rewriter sees only the already-abstracted text, and its answer is re-verified
by the same detectors; if it fails the check you will see 'rewrite rejected' and the plain version is used.
"""
import sys

from lattice import FakeOracle, Gateway, LocalRewriter, OllamaBackend, Vocabulary

argv = sys.argv[1:]
model, cpu, workspace, terms, questions = "qwen2.5-coder:3b", False, None, [], []
i = 0
while i < len(argv):
    if argv[i] == "--model":
        model, i = argv[i + 1], i + 2
    elif argv[i] == "--workspace":
        workspace, i = argv[i + 1], i + 2
    elif argv[i] == "--term":
        terms.append(argv[i + 1]); i += 2
    elif argv[i] == "--cpu":
        cpu, i = True, i + 1
    elif argv[i].startswith("--"):
        sys.exit(f"unknown option {argv[i]!r}. Options: --model NAME, --cpu, --workspace PATH, --term WORD")
    else:
        questions.append(argv[i]); i += 1

SAMPLES = [
    "Why is our PaymentProcessor class failing on line 847?",
    "Why does charge_customer_card in billing/payments.py return None?",
    "How do I make retry_failed_orders idempotent when the queue redelivers messages?",
]

vocab = Vocabulary.from_workspace(workspace, extra=terms) if workspace else Vocabulary(terms)
backend = OllamaBackend(model=model, num_gpu=0 if cpu else None)
plain = Gateway(FakeOracle(), vocab)
reworded = Gateway(FakeOracle(), vocab, rewriter=LocalRewriter(backend))

for q in questions or SAMPLES:
    a, b = plain.prepare(q), reworded.prepare(q)
    print(f"\nORIGINAL  : {q}")
    print(f"ABSTRACTED: {a.text or '(blocked: ' + '; '.join(a.reasons) + ')'}")
    if b.decision == "abstracted":
        print(f"REWRITTEN : {b.text}" if b.rewritten else "REWRITTEN : (rewrite rejected, unchanged, or model unavailable; the abstracted text above would be used)")
