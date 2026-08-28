# Spike S-2 — cross-position lateral yield (2026-08-28)

> `plan.md` §Spike S-2 / `prd.md` §O-4: when a player is pinned and
> `swap_positions` asks for OTHER positions of similar value, does the
> generator actually return non-empty `lateral` ideas once the ±10% band and
> the #108 gain gate apply — or does the W2 picker mostly show "nothing
> found"? Run against the shipped generator with the W2 `swap_positions`
> implementation in place. Spike scaffolding lives in the session scratchpad,
> not in `backend/tests/`.

## Verdict, plainly

**The picker is viable — the empty state is not the dominant case, but it is
a frequent one, and the design must keep treating it as first-class.**

- A **single-position** selection comes back empty roughly **30–60% of the
  time** (worst when TE is the target: only ~28–42% of pins find a TE
  lateral; best when WR is the target: ~72–88% non-empty). The per-mode
  counts on the chips and the honest per-mode empty copy already specced
  (`lld-delta.md` §0.3, PRD R-15) are load-bearing, not polish.
- A **multi-position** selection rescues yield: **89–97% of pins find at
  least one lateral at some other position**. If the picker nudges anything,
  it should nudge multi-select.
- Yield per pair is **shallow**: mean 0.3–2.0 ideas, max 4–7 (cap 6). The
  Same-value pager will usually hold **1–2 tiles**, not a deep deck — the
  `1 / X` counter and swipe affordance should expect X to be small.
- **Truly elite pins are empty everywhere, including their own position**
  (nothing values above them league-wide). That is today's shipped behavior,
  unchanged by `swap_positions`.
- **PICK pins:** `swap_positions` does not apply (route rejects `"PICK"` per
  R-12; a PICK pin runs pure value bands) — and pick pins **already** return
  cross-position laterals today (measured: QB/RB/TE mix for a mid-1st pin).

So for O-4: build the W2 picker. **No** design change to the mechanism is
needed; the design consequence is emphasis — empty-mode counts, the multi-
select default posture, and copy that names the selection.

## Method

- **League:** 12 teams built from the real DynastyProcess 1QB-PPR value
  snapshot already in the repo
  (`backend/tests/fixtures/dp_values_snapshot_2026-07-10.json`): top 36 QB /
  84 RB / 96 WR / 36 TE snake-drafted per position (3 QB / 7 RB / 8 WR /
  3 TE per roster — a realistic dynasty shape), values → Elo via the inverse
  of `elo_to_value`. One mid-1st pick pseudo-asset (v=3785, 2026 1.03 from
  `dp_values_picks_2026-08-06.csv`) for the pick-pin case.
- **Calls:** the real `TradeService.generate_asset_ideas`
  (`direction="give"`, market stud-tax mode = production default,
  `fairness_threshold=0.50`, defaults for everything else), with
  `swap_positions=[P]` for each P; the pin's owning team plays the user.
- **Gate check (why the analytic sweep is trustworthy):** across the full
  8-pin × 4-position grid, the generator's returned lateral count **equaled
  the analytic count of opponent-held candidates in `[v_pin, 1.1·v_pin]` in
  every cell**. Inside a ±10% band the fairness ratio is ≥ 0.909 and never
  binds; the #108 gate (`rv − gv ≥ user_gain_epsilon = 0`) kills the lower
  half of the band, so band + #108 are the only binding gates for a 1-for-1
  lateral. The league-wide sweep below is therefore computed analytically
  and spot-validated through the generator (largest window: 7 candidates →
  generator returned 6, the `asset_ideas_group_cap`).

## Numbers

Representative pins (lateral count via the real generator / in-window
opponent candidates):

| Pin | Value | baseline (own pos) | QB | RB | WR | TE |
|---|---|---|---|---|---|---|
| WR1 (elite WR) | 10232 | 0 | 0/0 | 0/0 | 0/0 | 0/0 |
| WR12 | 6044 | 2 | 0/0 | 3/3 | 2/2 | 0/0 |
| RB18 (mid RB) | 2274 | 0 | 1/1 | 0/0 | 1/1 | 0/0 |
| RB30 | 586 | 1 | 0/0 | 1/1 | 0/0 | 1/1 |
| TE5 | 3604 | 1 | 2/2 | 1/1 | 3/3 | 1/1 |
| TE9 | 1970 | 0 | 1/1 | 2/2 | 1/1 | 0/0 |
| QB8 | 3281 | 0 | 0/0 | 1/1 | 0/0 | 1/1 |
| 2026 1.03 (PICK) | 3785 | 3 | — swap ignored; laterals already QB/RB/TE — | | | |

League-wide sweep, every rostered player pin (139), single-position
selections:

| Pin tier | n | swap [QB] non-empty | [RB] | [WR] | [TE] | any OTHER pos non-empty |
|---|---|---|---|---|---|---|
| elite (≥4000) | 43 | 42% (mean 0.5) | 70% (1.2) | 88% (2.0) | 28% (0.3) | **95%** |
| mid (1500–4000) | 39 | 72% (0.8) | 69% (1.1) | 72% (1.1) | 31% (0.3) | **97%** |
| depth (400–1500) | 57 | 44% (0.5) | 60% (0.8) | 77% (2.0) | 42% (0.6) | **89%** |

## Caveats

- One simulated league (12-team, 1QB PPR, snake-balanced rosters). Real
  leagues with lopsided rosters shift which cells are empty, not the shape:
  yield is a density question — how many opponent assets of the chosen
  position sit within +0–10% of the pin's value.
- The effective window is the **upper half** of the ±10% band because
  `user_gain_epsilon = 0.0` kills any 1-for-1 where the candidate values
  below the pin (the shipped #108 posture; same for same-position laterals
  today).
- The #189 relaxed refill widens the fairness band only, which never binds
  in-band — it cannot rescue an empty lateral group, by design
  (`lld-delta.md` §3.6).
