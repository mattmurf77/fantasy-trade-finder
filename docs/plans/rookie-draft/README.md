# rookie-draft — rookie rankings + live draft support

**Status: shipped, 2026-08-05 → 2026-08-06.** `ranks.rookie_subset`, `draft.room`,
`draft.live_poll`, `draft.mfl`, `picks.slot_values`, `trade.slot_pricing` are all `true`.
Decisions: [ADR-009](../../adr/adr-009-rookie-scope-view-filter.md) (rookie scope as a post-Elo
view filter) and [ADR-010](../../adr/adr-010-user-asserted-pick-ownership.md) (user-asserted
pick ownership).

The follow-on workstreams — draft-room actions, the FTF-native mock draft, ESPN pick
assignment — live in [`../draft-extensions/`](../draft-extensions/).

## Read order

1. [`plan.md`](plan.md) — **§0 "Ground truth corrections" first.** Four verified findings that
   reshaped the build, including that the player-data pipeline had no refresh path at all
   (the real M0) and that per-slot pick values already existed upstream in DynastyProcess.
2. [`hld.md`](hld.md) → [`lld.md`](lld.md) — 1,218 lines from the converged dual-agent plan.
3. The `build-*.md` for the milestone you care about.

## Milestones

| M | Scope | Files |
|---|---|---|
| M0 | Valued-rookie measurement for the 2026 class | [measurement.md](measurement.md) |
| M2 | Rookie scope on the ranking surfaces (mobile) | [build-m2-mobile.md](build-m2-mobile.md) |
| M3–M4 | The Draft Room + its route | [build-m4.md](build-m4.md) |
| M5 | MFL parity, production wiring | [build-m5.md](build-m5.md) · [handoff](m5-m6-handoff.md) |
| M6 | Slot values, display-only | [build-m6.md](build-m6.md) |
| M6b | Market slot values **in the trade engine** — a repricing, not a plumb | [build-m6b.md](build-m6b.md) |
| — | Draft-surface placement (option B + seasonal A′) | [build-placement.md](build-placement.md) |

## QA

[`qa-results.md`](qa-results.md) covers V1 (M0–M4); [`qa-testflight-handoff.md`](qa-testflight-handoff.md)
is the operator TestFlight pass. Both pre-date [D-056] — ignore any Maestro/simulator steps
they contain and use a manual TestFlight checklist instead.

## One file that is not this initiative

[`mock-draft-plan.md`](mock-draft-plan.md) — the mock-draft + CPU-drafter design. It was a
local-only draft during this build and was **superseded** by W2 of
[`../draft-extensions/`](../draft-extensions/), which is what shipped. Read the
`draft-extensions` HLD/LLD and its calibration reports for the built model.

[D-056]: ../../../living-memory/DECISIONS.md
