# Recovery ledger — device-auth design programme + S0 sweep, 2026-08-13

> Capture-then-delete, per [`CLAUDE.md`](CLAUDE.md). Tip shas recorded **before**
> removal; every branch verified **by content** against `origin/main` (this repo
> squash-merges, so ahead/behind counts are not evidence).

---

## Branches swept

| Branch | Tip sha | Landed as | Verified |
|---|---|---|---|
| `design/device-auth-lld` | `da42f81` | pushed direct → `da42f81` | content on main |
| `handoff-s0` | `9bf5a7d` | pushed direct → `9bf5a7d` | content on main |
| `feat/s0-faab` | `79123a0` | pushed direct → `79123a0` | content on main |
| `feat/s0-vault-sentry` | `e240aae` | cherry-picked into `feat/s0-bundle` → `f79b4c3` | content on main |
| `feat/s0-bundle` | `f79b4c3` | pushed direct → `f79b4c3` | content on main |
| `feat/s0-spikes` | `da42f81` | **never used** — no commits | nothing to land |

`feat/s0-bundle` is the branch that actually merged the mobile half: it was cut
from `origin/main`, took `feat/s0-faab` and `feat/s0-vault-sentry` by
cherry-pick, and was rebased twice as `main` moved under it (once for the
notification-inbox ship, once for the v1.13.3 mock-draft ship). The FAAB commit
dropped out of the second rebase because it had already landed on its own —
which is the expected behaviour, not a loss.

`feat/s0-spikes` was created for the OI-9 / OI-12 Gate-C spikes; the agent hit a
session limit before writing anything, so the branch sat at its base sha. **The
spikes are still owed** — see `NEXT.md`.

## Verification method

Not `git branch -d` refusals and not ahead-counts. Each item was checked by
reading content out of `origin/main`:

- `backend/sleeper_write.py` contains `_graphql_object_literal` (4 occurrences)
- `mobile/src/transport/credentialVault.ts` contains
  `WHEN_UNLOCKED_THIS_DEVICE_ONLY` (2 occurrences)
- `mobile/src/observability/sentry.ts` contains the three scrub hooks
  (`beforeSend` / `beforeBreadcrumb` / `tracePropagationTargets`)
- all four programme docs (PRD, HLD decisions, LLD, Plan) plus the analytics
  spec resolve on `origin/main`

## Worktrees removed

- `scratchpad/lld-wt` (held `design/device-auth-lld`)
- `scratchpad/s0-faab-wt`
- `scratchpad/s0-vault-sentry-wt`
- `scratchpad/s0-bundle-wt`
- `scratchpad/s0-spikes-wt`

All were session-scoped worktrees under the agent scratchpad, not user clones.
