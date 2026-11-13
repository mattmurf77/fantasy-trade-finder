# Status — Team Review (#357 / #358 / #359)

**Status:** `shipped` — Team Review is built and live behind `trades.team_review` (on in `config/features.json`), revised by #364-#374, #423-#424 and the 2026-11-12 current-data fixes ([`2026-11-12-current-data-fixes.md`](2026-11-12-current-data-fixes.md), branch `fix/team-review-current-data`). The 2026-08-19 lines below are the original planning record and read as history: the build did start, and the standing beat no longer shows the `outlook.odds` band (it shows the saved weekly forecast's playoff chance).
**Date:** 2026-08-19 (planning); corrected 2026-11-12
**Covered feedback IDs:** #357, #358, #359 (canonical folder = lowest id, 357)
**Branch:** planning on `claude/team-review-analysis-plan-1f91e3` (worktree `jolly-leakey-d20295`), docs only; the build shipped on later branches
**Flag:** `trades.team_review` — in `config/features.json`, `true`

---

## What this is

An analyst-guided, six-beat read of the user's own team, entered from a card at
the top of `TradesHome`. Each beat states one finding from data that already
exists, explains it plainly, and offers one action — and four of the six actions
write `league_preferences`, the fields the trade engine already reads. The exit
is a deck reshaped by what the user just agreed to.

Beat `standing` carried a playoff **band chip** (replaced 2026-11-12 by the saved weekly forecast's playoff chance; see the addendum) — `outlook.odds` was lit by operator override on 2026-08-19 ([D-094](../../../../living-memory/DECISIONS.md), superseding D-093). Adds **no new modeling**. Championship odds and bare percentages stay refused on evidence.

## Doc set

| Doc | Contents |
|---|---|
| [`scope.md`](scope.md) | Feature-scope block — analytics, flag, evidence, docs table, ship gate, **three waivers** |
| [`hld-delta.md`](hld-delta.md) | Architecture delta, decisions + alternatives rejected, **the `outlook.odds` ruling and its lighting criteria** |
| [`lld-delta.md`](lld-delta.md) | Full API contract, composer spec, mobile wiring, degradation matrix |
| [`prd.md`](prd.md) | R-1…R-27, copy rules, guardrails, test plan incl. the manual TestFlight checklist |
| [`reconciliation-log.md`](reconciliation-log.md) | Adversarial review: 7 objections, 2 blocking (both fixed) |
| [`2026-11-12-current-data-fixes.md`](2026-11-12-current-data-fixes.md) | Scope addendum: eight fixes against the current engine (firsts by round, the saved forecast on the standing beat, shared outlook names, refetch after a save, no silent outlook write, the plan beat's player rules, window copy, the "Preferences changed" return) |
| Design lab | [`mockups/team-review-2026-08-19/`](../../../../mockups/team-review-2026-08-19/index.html) |

## Rulings made this session

- **`outlook.odds` is LIT** ([D-094](../../../../living-memory/DECISIONS.md), operator override reversing this session's own D-093 recommendation). Flag flipped to `true`; the built-but-dark #169 layer goes live on the next merge. Beat `standing` carries the band chip. **Still refused, on evidence rather than preference:** `title_pct` at any week (no demonstrated skill — Team Review does not serialize it) and any bare percentage (`OUTLOOK_WEEK6_PERCENT_ENABLED` stays `false`). Guard: `mobile/tests/check-outlook-bands.js`, 7 assertions, all six sabotages proven red.
- **Forward per-player PPG is CUT.** No source exists — all four candidate feeds are ToS-blocked, gray, or build-your-own. #357 is answered instead by `starter_impact.slots[].before/after` with tier + positional rank (`trade.position_impact`, already ON).
- **Championship odds cannot be honored at all** — `title_pct` is unrenderable by cross-client invariant.
- **Retrospective PPG rank is in, degraded** — Sleeper-only and empty until week 1; the card names the actual reason.
- **Form: stepped beats**, not a narrated scroll (a dashboard with prose, nowhere to put a decision) and not a Q&A (needs an LLM, breaks the deterministic-copy precedent). [D-092](../../../../living-memory/DECISIONS.md).
- **Entry: a card, not a seventh mode chip** — the chip strip already measures ≈402pt against ≈361pt usable, so an appended chip is invisible.

## Blocked on

1. **Waiver 3 only** — PPG rank is Sleeper-only and preseason-empty ([`scope.md` §6](scope.md), [Q-025](../../../../living-memory/OPEN_QUESTIONS.md)). Waiver 1 (forward PPG cut) was **ratified** 2026-08-19; waiver 2 (championship odds) is a notification and stands.
2. [Q-024](../../../../living-memory/OPEN_QUESTIONS.md) — root `CLAUDE.md` §Stack is stale about `check-*.js` CI gating; not this feature's to fix unilaterally.

## Next step

With waivers signed: two parallel build agents on the disjoint file-ownership
table in [`lld-delta.md` §1](lld-delta.md). Recommend an independent read of the
API contract first (see the reconciliation log's U-3).
