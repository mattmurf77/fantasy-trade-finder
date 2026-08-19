# draft-extensions — draft-room actions · FTF-native mock draft · ESPN pick assignment

**Status: shipped, 2026-08-06 → 2026-08-08.** All three workstreams are live:
`draft.room`, `draft.live_poll`, `draft.mock`, `draft.tab`, `draft.rank_inline`,
`draft.manual_picks`, `picks.assign`, `picks.assign_tradeable` are all `true` in
`config/features.json`.

**[`plan.md`](plan.md)'s own header still says "candidate v1 — under cross-review".** That was
true on 2026-08-06 and is not true now; the `build-*.md` files are the record of what actually
landed. Trust the flags and the build notes over the plan header.

Builds on [`../rookie-draft/`](../rookie-draft/), which shipped the rookie-ranking and
live-draft foundation this extends. ADR-010 covers user-asserted pick ownership (W3).

## Read order

1. [`plan.md`](plan.md) — §0 "Ground truth" is the durable part: three verified corrections that
   reshaped the scope, including the tab-predicate guard that was inert as first written.
2. [`hld.md`](hld.md) → [`lld.md`](lld.md) — architecture and implementation detail across all
   three workstreams (W1/W2/W3).
3. The `build-*.md` file for the increment you care about — each is a build-status record with
   what shipped, what was descoped, and why.

## Workstreams

| WS | Scope | Build notes |
|---|---|---|
| **W1** | Draft-room per-player actions + instrumentation | [build-w1.md](build-w1.md) |
| **W2** | FTF-native mock draft — backend engine, CPU drafter model, mobile UI | [build-w2.md](build-w2.md) (engine) · [w2b](build-w2b.md) · [w2c](build-w2c.md) · [w2d](build-w2d.md) · [w2e](build-w2e.md) · [build-mock-ui.md](build-mock-ui.md) (mobile) |
| **W3** | ESPN pick assignment + asserted-pick pricing + live offline pick recording | [M-A/M-B](build-w3-ma-mb.md) · [M-A mobile](build-w3-mobile.md) · [M-C](build-w3-mc.md) · [M-C mobile](build-w3-mc-mobile.md) · [M-D](build-w3-md.md) |
| — | Editable rookie ranks + the seasonal Draft tab | [build-tab-and-rookie-edit.md](build-tab-and-rookie-edit.md) |
| — | ESPN auto-derived draft order | [feasibility](espn-auto-draft-order-feasibility.md) · [build](build-espn-auto-order.md) |

## The mock-draft calibration sequence

Four reports, each superseding the last. **Read [`mock-calibration-2026-08d.md`](mock-calibration-2026-08d.md)
for the current model**; a–c are the reasoning trail:

| Report | What changed |
|---|---|
| [2026-08](mock-calibration-2026-08.md) | First fit of the CPU noise model (interface I-10) |
| [2026-08b](mock-calibration-2026-08b.md) | Re-spec to a two-parameter mixture, re-fit |
| [2026-08c](mock-calibration-2026-08c.md) | Corrected snapshot, re-fit — model and gate **frozen** here |
| [2026-08d](mock-calibration-2026-08d.md) | Re-balanced calibration split + create-contract gaps — **current** |

The round-tiered reach policy in [`build-w2e.md`](build-w2e.md) was installed **without**
re-running the gate; that is stated in the file. Later mock-draft tuning (the `cpu_pick`
value-gap fix, D-024) is recorded in `living-memory/CHANGELOG.md`, not here.
