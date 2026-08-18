# Recovery ledger — dismiss cooldown sweep (2026-08-18)

> Capture-then-delete. Verified **by commit ancestry** against `origin/main`
> (`git log origin/main..<branch>` = 0), not by ahead-counts or `branch -d`.

| Worktree | Branch | Tip | Landed as |
|---|---|---|---|
| `.claude/worktrees/pass-cooldown` | `fix/pass-cooldown` | `f68f860` | merge `505ca2c` → `main` |
| `.claude/worktrees/ship-cooldown` | (detached on `main`) | `791da23` | pushed directly (merge + ship record) |

## Where the work landed

- `505ca2c` — dismiss cooldown (D-067): `pass_cooldown_days` 14.0,
  immediate in-memory bind across all scoring formats,
  `pass_cooldown_start_epoch` legacy amnesty.
- `791da23` — CHANGELOG + TEST_LEDGER ship record.
- Deploy **verified by content**: both knobs present in prod
  `/api/admin/config` with correct values (`14.0`, `1787005800.0`).
- **No TestFlight build cut** — backend-only change; `git diff 67b54f6..main --
  mobile/` is empty, so main's mobile tree is byte-identical to what
  **v1.14.0 build 116** already carried (finished 2026-08-17 18:46 EDT).

## Note for the next sweep

A deploy-verification monitor reported a **false negative** here: its inline
`CRON_SECRET` extraction (`tr -d`) differed from the working one (`sed`),
so the probe 401'd and printed "knob absent" — indistinguishable from a failed
deploy. A direct re-check showed both knobs live. Probe failures and deploy
failures must be distinguishable; check the HTTP status, not just the grep.
