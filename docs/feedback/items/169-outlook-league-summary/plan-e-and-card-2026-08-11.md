# #169 — Build plan: League-Summary frame E + trade-card frame C

**Date:** 2026-08-11 · **Status:** planned
**Decision authority:** [`operator-frame-decisions-2026-08-11.md`](operator-frame-decisions-2026-08-11.md)
(§7 + §8 — all questions resolved, none open)
**Companions:** [`hld-e-and-card-2026-08-11.md`](hld-e-and-card-2026-08-11.md) ·
[`lld-e-and-card-2026-08-11.md`](lld-e-and-card-2026-08-11.md) ·
[`prd-e-and-card-2026-08-11.md`](prd-e-and-card-2026-08-11.md) ·
[`scope.md`](scope.md)

---

## Table of Contents

- [What ships](#what-ships)
- [What does NOT ship](#what-does-not-ship)
- [Baseline facts (verified 2026-08-11)](#baseline-facts-verified-2026-08-11)
- [Workstreams](#workstreams)
- [Sequencing](#sequencing)
- [Gates](#gates)
- [Risks](#risks)

---

## What ships

Two client-only mobile changes, one branch, one PR:

1. **League Summary frame E** — the always-open `SeasonOutlookSection` gains a
   collapsed one-line "your outlook" strip as its default state (flag-dark
   behind `outlook.odds`, exactly like the section it fronts). Tap expands the
   full section in place; state remembered per league.
2. **Trade card frame C, operator-modified** — the Pass / Like buttons move
   from below the deck (`TradesScreen` `dispositionRow`) to inside the card,
   directly beneath the player tile section. `TradeValueBar` (post-#243, as on
   `main`) stays where it is. No odds block is added at any week.

## What does NOT ship

- **No backend behavior.** Card frame D was dropped (§7); no with-trade
  re-sim, no route, no schema, no flag changes. `outlook.odds` stays `false`.
  (One backend *file* changes: the analytics allowlist gains
  `outlook_strip_toggled` — operator rejected the analytics waiver, so the
  event ships specced + wired now. This touches the CLAUDE.md bright line's
  analytics surface — irrelevant to express-eligibility since this build runs
  full gates, but named here for honesty.)
- **No #243 work.** All five #243 density builds are already on `origin/main`
  (see [`../243-scroll-audit/status.md`](../243-scroll-audit/status.md)).
  "The bar from #243" = the shipped `TradeValueBar`.
- **No odds block on the trade card, in any week.** Week 6+ is deferred, not
  designed (§8). The card change is a reorder, not a feature.
- **No change to B / C1 / D on the League Summary** — already built, already
  merged, confirmed by the operator.

## Baseline facts (verified 2026-08-11)

- The `outlook-league-summary-v2` branch content (tip `36618be`) is fully on
  `origin/main`: `SeasonOutlookSection` at `LeagueSummaryScreen.tsx:1772`
  (mounted `:858`), coverage caption, platform gate, invariants section.
- The shipped trade card (`mobile/src/components/TradeCard.tsx`) renders **no
  odds/outlook block** — frame C's "absence" is already reality on the deck.
- Pass / Like live **outside** the card: `TradesScreen.tsx:4733` (`dispositionRow`,
  56×56 icon buttons, `trades.pass-btn` / `trades.like-btn`, both calling
  `advance()`).
- `TradeValueBar` mounts inside the card at `TradeCard.tsx:533`, post-#243
  (≈192pt collapsed, `valuebar.why` disclosure, 11px scale labels).
- No jest in `mobile/`; behavioral coverage = Maestro flows + node check
  scripts in `mobile/tests/`.

## Workstreams

| # | Workstream | Files | Owner |
|---|---|---|---|
| W1 | Frame E strip + its analytics event | `mobile/src/screens/LeagueSummaryScreen.tsx`, new `mobile/src/state/outlookStrip.ts`, `backend/analytics_taxonomy.py` (+ its test), `docs/business/analytics/2026-07-17-tracking-plan-v2.md` (addendum) | build agent A |
| W2 | Card disposition move | `mobile/src/components/TradeCard.tsx`, `mobile/src/screens/TradesScreen.tsx` | build agent B |
| W3 | Tests + flows | `mobile/tests/check-card-disposition.js` (new), `mobile/package.json` (`test:card-disposition` runner), `mobile/.maestro/flows/smoke/06-trades-deck.yaml` (positional extend), `mobile/.maestro/capture/onboarding-tour@fresh.yaml` (re-derive disposition anchors) | build agent B |
| W4 | Docs + invariants | `docs/cross-client-invariants.md` (Pass/Like), `living-memory/*`, screen/component CLAUDE.md rows | primary session |

W1 and W2/W3 touch disjoint files → parallel build agents. W4 stays with the
primary session (doc edits need whole-repo context).

## Sequencing

1. Docs authored (this set) → adversarial review pass → operator waiver
   sign-off (analytics + Maestro-for-E waivers, per scope.md).
2. Branch `feedback-169-e-and-card` from fresh `origin/main`.
3. W1 ∥ W2+W3 in worktrees (`npm ci`, never symlink `node_modules`).
4. Merge agent branches → primary branch; `tsc --noEmit`, `testid-lint.sh`,
   sabotage proof for the new check script (revert the move → script must
   fail → restore).
5. Tier-1 sim gate: full smoke (11 flows) + extended deck flow; re-capture
   `trades` (+ any capture `screen-freshness.sh` flags).
6. W4 docs, TEST_LEDGER, `qa/sim-runs/last-sim-run.json`, PR → `main`.

## Gates

Full feature gates apply — **no express** (operator has not declared it, and
the agents may not self-select). Scope block: [`scope.md`](scope.md). Sim
tier: **1** (mobile screen change). Two waivers need operator sign-off before
build; they are listed in scope.md §1(c) and §3.

## Risks

| Risk | Mitigation |
|---|---|
| Pass/Like taps dead inside the card's `GestureDetector` pan surface | The extended `06-trades-deck.yaml` *taps both buttons* post-move — the Tier-1 sim run is a direct tappability proof, not an inference; the pan's ±12 horizontal activation offset makes swallowing unlikely. If taps are swallowed anyway: STOP and escalate to the operator (LLD §2.4 — no silent fallback; the previously-drafted out-of-gesture composition was reviewed and found structurally dishonest). |
| Peek/back card showing a second button row | Disposition props are passed **only** to the top card (LLD §2.3); the check script asserts single-mount. |
| Strip renders a fabricated state when the payload has no `is_you` row | LLD §1.5: no `is_you` → render the full section as today, no strip. |
| Frame E drawn against the mock, not the code | LLD specs against the real `SeasonOutlookSection` (read 2026-08-11), not the mock's HTML. |
