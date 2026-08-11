# #169 — PRD: frame E + card frame C

**Date:** 2026-08-11 · **Status:** planned
**Decisions:** [`operator-frame-decisions-2026-08-11.md`](operator-frame-decisions-2026-08-11.md) (§7/§8 final)
**Plan / HLD / LLD:** [`plan-e-and-card-2026-08-11.md`](plan-e-and-card-2026-08-11.md) ·
[`hld-e-and-card-2026-08-11.md`](hld-e-and-card-2026-08-11.md) ·
[`lld-e-and-card-2026-08-11.md`](lld-e-and-card-2026-08-11.md)

---

## Table of Contents

- [Problem & intent](#problem--intent)
- [Requirements](#requirements)
- [Acceptance criteria](#acceptance-criteria)
- [Test plan](#test-plan)
- [Out of scope](#out-of-scope)
- [Launch posture](#launch-posture)

---

## Problem & intent

**Frame E:** the built Season-outlook section is 12+ rows mounted above the
League Rankings chart — the screen's actual product ends up below the fold the
moment the flag lights. The operator chose the collapsed-strip variant: your
own outlook in one glanceable line, the full league table one tap away, the
chart back above the fold.

**Card frame C:** the operator reviewed the trade-card odds mockups and chose
the frame whose design is *absence* — no odds block on the card in any week
(week 6+ deferred, §8) — with two placement corrections to the card as it
ships today: disposition actions belong directly beneath the players being
traded, and the value bar keeps its place (above any future outlook block).

## Requirements

### FR1 — Collapsed outlook strip (League Summary, flag `outlook.odds`)

1. With the flag on, a Sleeper league, data present, and an `is_you` row: the
   outlook mounts **collapsed by default** as a one-line strip — warn label
   "Season outlook", the user's playoff band chip, "for the playoffs ·
   projected *Nth* of *M*", chevron.
2. Band chip + thresholds are the shipped invariants
   (`docs/cross-client-invariants.md` § Playoff outlook bands) — same
   constants, same construction, label never color-only.
3. Tapping toggles the full existing section in place beneath the strip;
   expansion state persists **per league** across app restarts; default is
   collapsed.
4. Degenerate states per LLD §1.5 — notably: no `is_you` row → full section,
   no strip; non-Sleeper and dark-flag behavior unchanged.
5. `N` (projected finish) must equal the rank the expanded section shows for
   the You row — one shared comparator, impossible to diverge.
6. The strip toggle fires `outlook_strip_toggled` (`league_id`, `expanded`)
   — specced in the taxonomy + tracking plan in the same PR (operator
   rejected the analytics waiver 2026-08-11; instrumentation exists from day
   one even though the flag is dark).

### FR2 — Disposition inside the card (trade deck, unflagged)

1. Pass / Like render inside the deck's top card, directly beneath the player
   tile section, above "Edit in calculator" / `TradeValueBar`.
2. Same testIDs (`trades.pass-btn` / `trades.like-btn`), same icons, sizes,
   colors, pressed/disabled states, same `advance()` semantics — a placement
   change with one deliberate exception: the VoiceOver strings "Accept this
   trade" are renamed to Pass/Like vocabulary (invariant compliance, LLD
   §2.2).
3. Exactly one disposition row ever exists: top card only — never the peek
   card, match variant, or read-only mounts; the old below-deck row is gone.
4. Swipe gestures still work; taps on both buttons still work (proven on
   sim, not assumed).
5. `TradeValueBar` stays mounted post-move, below the disposition row.
6. No odds/outlook block appears on the card at any week.

### FR3 — Vocabulary invariant

"Pass / Like" is the deck disposition vocabulary across clients — recorded in
`docs/cross-client-invariants.md` (operator decision §7 Q2).

## Acceptance criteria

| # | Check | Method |
|---|---|---|
| A1 | Flag dark ⇒ byte-identical League Summary render + zero outlook requests | code review of the gate chain (unchanged) + dark-state smoke flows green |
| A2 | Flag forced on (sim): strip renders collapsed with band + "projected Nth of M"; tap expands the unchanged section; collapse persists per league after app restart | manual sim pass, logged in TEST_LEDGER (no seeded outlook fixture exists — same constraint as the 2026-08-10 build) |
| A3 | Strip rank == expanded section rank for the You row | shared-comparator code review + A2 visual |
| A4 | Deck: Pass/Like visible inside card beneath tiles; like-tap advances deck | extended `06-trades-deck.yaml` on sim (Tier-1 run) |
| A5 | Pass-tap works post-move | extended `06-trades-deck.yaml` taps pass on the second card (smoke evidence); `onboarding-tour@fresh.yaml` (capture pass, re-derived anchors) corroborates |
| A6 | One disposition row; match/featured/peek unaffected | `check-card-disposition.js` (local-only — CI runs no mobile check scripts) + `matches` re-capture showing no visual diff |
| A7 | Check script fails on sabotage | sabotage run logged in TEST_LEDGER (local-only evidence) |
| A8 | `tsc --noEmit` clean; `testid-lint.sh` OK | CI + local |
| A9 | Full smoke suite (11 flows) green | Tier-1 sim run |
| A10 | `outlook_strip_toggled` in `ALLOWED_CLIENT_EVENTS`; taxonomy test asserts it and fails on sabotage; tracking-plan addendum filed | pytest (CI) + sabotage run in TEST_LEDGER |

## Test plan

Per LLD §3: new static check (sabotage-proven), extended deck smoke flow,
Tier-1 sim run, `trades` re-capture, freshness sweep. Frame E flow waived
while dark — owed at lighting time with the strip states added (waiver in
[`scope.md`](scope.md) §3, operator-signed).

## Out of scope

- Any week-6+ card odds treatment (deferred, not designed — decisions §8).
- Web/extension parity for the strip (web has no outlook surface yet; parity
  reads the invariants doc when it comes).
- Lighting `outlook.odds`, seeding a sim fixture for it, or the lighting-time
  Maestro flow.
- Removing/altering League-Summary frames B/C1/D or `OUTLOOK_WEEK6_PERCENT_ENABLED`.

## Review log

2026-08-11: adversarial review (independent agent, refute-mandate) returned
FIX-THEN-SHIP — 4 blockers, 13 fixes, 4 nits; decision fidelity and the
bright-line claim confirmed. All 21 findings applied to rev 2 of this doc
set. The load-bearing corrections: `SeasonOutlookSection`'s sort is
extracted (not "untouched"); both Maestro deltas are positional (a plain
`visible:` assert passes identically before/after the move); the pass-tap
became smoke evidence via the extended deck flow (the tour flow is capture,
not smoke); the shipped "Accept this trade" VoiceOver labels are renamed to
match the Pass/Like invariant; `SwipableTopCard`'s existing `onLike`/`onPass`
props are reused instead of a duplicate callback pair; `dispositionDisabled`
stays in `TradesScreen` (still consumed at `:4790`); the check script gets an
npm runner and is marked local-only; the capture delta is four screens, not
one; the gesture-risk "fallback" was cut — on failure, stop and escalate.

## Launch posture

Frame E ships dark inside `outlook.odds` (nothing user-visible until the flag
lights). The card reorder ships **live** on merge — it is deliberately
unflagged (pure client reorder, instantly revertible; flagging a button move
would add a dead flag surface for no rollback value beyond `git revert`).
