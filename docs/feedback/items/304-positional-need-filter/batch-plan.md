# Batch plan — 2026-08-16 feedback wave

> Orchestrator's batch-level tracker for the 2026-08-16 run of the feedback
> pipeline. Lives here per convention (lowest selected item = #304). Every
> selected item's folder links back to this file. Selection and all operator
> answers below were given in chat on 2026-08-15/16.

## Baseline

- **Base:** `origin/main` @ `d3fe3ac` (v1.13.4, TestFlight build 111).
- All group branches start from a freshly fetched `origin/main` (CLAUDE.md
  convention 2026-08-08) — never from the session checkout.
- **QA regime:** D-056 — Maestro/simulator retired. Evidence = structural
  `check-*.js` suites + unit tests + written code-walk proofs; runtime proof
  is an operator TestFlight checklist per group.

## Groups

| Group | Items | Path | Canonical folder | Platforms |
|---|---|---|---|---|
| **G1** Calculator tier labels + send placement | 303, 306, 320 | Feature | `303-calc-send-placement/` (plan on branch `wave-calc` @ `6b6c513`) | backend + mobile |
| **G2** Mock draft room UI | 322, 323, 324, 325, 326, 327 | Polish | `322-mock-draft-room-ui/` | mobile |
| **G3** Mock draft pick assignment | 328 | Feature | `328-mock-draft-pick-assignment/` | backend + mobile-caption |
| **G4** Offer prefill + auto-run | 330 | Polish | `330-offer-prefill/` | mobile (+backend param) |
| **G5** ESPN token bleed | 321 | Bug (security-scoped) | `321-espn-token-bleed/` | backend + mobile |
| **G6** Trade presentment rules | 304, 336, 339, 340, 341 | Feature (heaviest) | `304-positional-need-filter/` | backend |
| **G9** Matches polish | 334, 335 | Polish | `334-matches-dismiss-latency/` | mobile |

**Build order:** G6 backend contract lands before G4's auto-run consumes deck
output. G1 is plan-complete and can enter Phase 2 directly. All other groups
are independent — Phase 1 runs in parallel.

## Operator decisions (chat, 2026-08-15/16)

### G1 (all six from the wave-calc plan §5)
- **D-306-1 = A: graduate `aggregate_tier_labels`** — labels ship to everyone;
  code sheds the `variant_for` guard. Confirming yes given explicitly
  (bright line: experiment + API surface).
- D-306-2 = yes: emit `picks.value_label` (literal-count firsts, #285 rule).
- D-303-1 = yes: send button moves alone; Share + Clear stay at bottom.
- D-320-1 = yes: pick rows get tier badges on calculator surfaces
  (supersedes #263 "picks stay numeric").
- D-320-2 = accept: badge reflects discounted value (2028 2nd may badge 3rd).
- D-320-3 = yes: share-image pick rows stay numeric (#277/#280 stands).
- Q7 (sequencing) unanswered → default: all three ship together.

### G2
- #322 + #325 = **one section described twice**: earliest picks at top,
  fixed-height view, earliest picks scroll up and off as new picks land.
- #324 layout: orchestrator proposes from Chalkline specs (operator delegated).
- #326 team view = **sheet**, not navigation. Position filter **resets** each turn.
- #323 tier = the 8-rung ladder (standing policy). #327 search scopes to the
  active filter subset.

### G3
- Real pick ownership: **MFL provides it; ESPN uses the existing manual
  assignment tool** (`PickAssignmentScreen`). Applies to **both** auto and
  manual modes.

### G4
- #330: offered player is a **hard lock** (appears in every suggestion).
- No-trade-found → **honest empty state with a link back to the league
  summary page**. Never silently relax the constraint.
- #329 closed `fixed` 2026-08-16 — operator confirmed resolved on 1.13.4.

### G5
- #321 was **same-device** account switching → investigate device-scoped
  credential storage leaking across sessions first. **Not** queue-jumping;
  normal priority.

### G6 — the two-part trade presentment system
- **Filter, not reorder** — need-awareness becomes a hard gate, not a
  ranking nudge (supersedes the light-multiplier posture of the 2026-07-17
  interview for *presentment*; `need_fit_weight` reordering may remain
  underneath).
- **Part 1 — construction rules** (is this package sane?):
  - #340 max-overpay ceiling, enforced even with trade fairness OFF.
  - #341 net ±1 player per position per side (never give 2 of a position
    unless getting 1 back).
  - #339 no draft pick on the overpaying side when that pick ≈ the value gap.
- **Part 2 — eligibility rules** (is this worth showing this user?):
  - #304 positional-need hard filter, **scaled by the inferred/declared
    window** (rebuilders relax it) — Q22 = yes.
  - #336 hard exclusion of trades already matched or awaiting the other owner.
- Likes-you / incoming offers: **do NOT need the same filtering** (Q21).
- Q19: closed — no `need_fit_weight` knob change as the fix.

### Held / out of scope this wave
- **G7/G8 (#310, #333, #337):** held for a joint IA design pass. Q23 note:
  the core swipe loop lives on the **Trades ("Acquire") tab** (`TradesStackNav`
  → Find a Trade), NOT Matches — `MatchesScreen` is a results surface. Matches
  becoming a surface inside Find a Trade is on the table.
- **G10 (#338):** investigate-first — a Sleeper DM on send may never have been
  part of the feature. No status change until investigated.
- **#205:** design-tenets interview — awaiting operator scheduling (Q25).
- **#331/#332:** research complete
  (`331-player-cards-stats/stat-sources-research.md`). Blocked on Q26
  (Sleeper commercial-licence conversation) before build scoping.

## Phase log

| Phase | State | Notes |
|---|---|---|
| 0 — Fetch & triage | **done 2026-08-16** | 27 open items triaged (18 + 9 overnight); 17 selected across 7 groups; statuses set |
| 1 — Plan | in progress | G1 exempt (plan exists). Planner round **complete for all six groups** (2026-08-16; survived an overnight session-limit interruption — G6 planner + G2 author resumed from transcript). Author round in flight ×6. Measured highlight: G6 combined kill rate 18.4% on the D-055 corpus, all 8 insult cards covered, worst-case empty-deck 4.6% (under the 5% bar). Cross-group question open for reconciliation: do #330 pinned/scoped searches bypass the #304 need gate? (G4 default: no bypass; G6 author to recommend.) |
| 2 — Build | — | |
| 3 — QA | — | per D-056: structural suites + code-walk proofs |
| 4 — QA resolution | — | |
| 5 — Ship | — | operator go/no-go required |
