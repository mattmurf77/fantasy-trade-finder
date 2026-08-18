# githooks/ — Notes for Claude

One hook. Not active until installed per clone:

```bash
git config core.hooksPath githooks
```

## `pre-push`

Fires only on pushes to `refs/heads/main`. Two behaviors:

1. **Blocks** a push whose range touches `mobile/src/` unless `qa/sim-runs/last-sim-run.json` records a passing Maestro run on an ancestor of the pushed commit.
2. **Warns, never blocks**, when the push changes `mobile/src/screens/` without a matching capture under `screens/`.

Escape hatch: `FTF_SKIP_SIM_GATE=1 git push …`.

## ⚠ The hook is stale — the escape hatch is now the normal path

Operator decision **D-056** (2026-08-15, Active — `living-memory/DECISIONS.md`) retired
Maestro and the simulator entirely, screen captures included. The artifact this hook demands
is no longer produced, and `screens/` is frozen at 2026-08-11.

**Standing posture: `FTF_SKIP_SIM_GATE=1`, with a one-line note in
[`living-memory/TEST_LEDGER.md`](../living-memory/TEST_LEDGER.md).** D-056 says so
explicitly. Do not satisfy the gate by generating a `last-sim-run.json`.

The hook's own comments, and the `docs/runbook.md § Pre-ship simulator gate` they point at,
still read as live. They have not been updated. Current QA regime:
[`qa/README.md`](../qa/README.md).
