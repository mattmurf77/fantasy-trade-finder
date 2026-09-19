# Session memory

Read the **Session brief** injected by the hook, or run `python3 scripts/session_context.py` if absent. Do not reread the same brief. Its UTF-8 JSON output is hard-capped at 6,000 bytes, including the envelope; omitted sections become explicit references, never partial instructions.

| File | Purpose/read trigger | Update |
|---|---|---|
| [HANDOFF](HANDOFF.md) | Current session/release bridge | Replace at handoff; ≤2,000 bytes total |
| [NEXT](NEXT.md) | Seven linked actionable priorities | Replace/reorder on priority changes; ≤1,500 bytes total |
| [CHANGELOG](CHANGELOG.md) | Recent work; older entries on demand | Short dated outcomes with evidence links |
| [DECISIONS](DECISIONS.md) | Before reversing a choice | Next available D-ID; link formal ADRs |
| [OPEN_QUESTIONS](OPEN_QUESTIONS.md) | Before asking an already-recorded question | Record answer/provenance; don't silently close |
| [GOTCHAS](GOTCHAS.md), [MISTAKES](MISTAKES.md) | Relevant symptom/abandoned approach | Specific searchable lesson/evidence |
| [TEST_LEDGER](TEST_LEDGER.md) | Before claiming validation/release evidence | What ran, result, source/build, limitations |

Architecture/schema/API/config/voice and coding practices belong in their canonical [docs](../docs/README.md). Former static memory filenames are compatibility links, not separate update targets. [Engineering notes](../docs/engineering-notes.md) preserves navigation to their unique contracts.

See [FORMAT](FORMAT.md) for machine-enforced limits and archive rules. The complete [pre-cleanup snapshot](archive/static-2026-09-06/README.md), including the old queue, remains available. Historical unresolved entries are not canceled when omitted from NEXT.
