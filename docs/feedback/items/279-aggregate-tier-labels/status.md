# #279 — Aggregate pick-equivalent labels (LeagueSummaryScreen)

**Status:** built-dark · 2026-08-09 · branch `worktree-agent-a1e9ac18717f11781`, experiment `aggregate_tier_labels`

## What this is

Builds the **E1 frame** from `mockups/polish-lab-2026-08/trades-home-inline.html`
(#270/#272/#279 polish lab; see the frame's caption and
`docs/feedback/items/270-inline-trades-home/status.md` § "#279 frame (E1)").
On `LeagueSummaryScreen` (the League tab's power-rankings root), TEAM totals
and POSITIONAL subtotals render as pick-equivalent labels ("≈14 firsts")
instead of raw numbers — for the operator's device only, via a new
experiment. Everyone else's numbers are unchanged; per-player values are
untouched (#277/#278 tier badges already ship there — this item is
aggregates only).

## §Rule change (#285, 2026-08-09)

The operator filed a bug against this exact experiment: "Draft picks should
be summed into the league/team values. Keep it simple. 1sts equal firsts,
3-4 2nds equal a 1st. No other picks included." The team TOTAL label
(`total_value_label`) changed as a result — full detail, rationale, and the
numeric-`total_value`-stays-unchanged decision live in
`docs/feedback/items/285-pick-sums/status.md`. Short version: the label's
base switched from `total_value` (positions + DOLLAR-priced picks) to
`positions_value` (players only) PLUS a new literal pick-count term
(`_pick_firsts_equivalent`: 1st = 1.0 firsts, 2nd = 1/3.5 firsts, 3rd+ = 0),
so picks stop being double-priced through two different formulas at once.
The `_aggregate_pick_label(value)` snippet below is now
`_aggregate_pick_label(value, pick_firsts=0.0)` — the positional labels
(this doc's whole subject otherwise) call it exactly as shown, unaffected.

## Formula reused (not invented)

The label reuses `backend/server.py`'s `_pick_gap_equivalent` — the SAME
value→pick-equivalent conversion already live on every trade card as
`gap.pick_equivalent`/`gap.firsts` (surfaced today as "a Late 2nd" in the
Dynasty Value Swing bar). A new thin wrapper, `_aggregate_pick_label(value)`,
applies it to a raw AGGREGATE (a team total or positional subtotal — a SUM
across many assets) instead of a value delta:

```python
def _aggregate_pick_label(value: float) -> str:
    firsts = _pick_gap_equivalent(max(value, 0.0))["firsts"]
    half = round(firsts * 2) / 2      # nearest half-first
    return f"≈{half:g} firsts"
```

Deliberately does **not** reuse or extend the 8-bucket `TIER_LABEL` ladder
(`mobile/src/utils/tierBands.ts` / `RankingService.tier_for_elo`) — per the
mockup's own caveat, that table is a per-asset classification whose top
bucket (`4+ 1sts`) is an open-ended catch-all, not a countable multiple, and
a roster-scale aggregate blows past it immediately. `firsts` (the gap in
units of a generic Mid 1st) is the one number in the existing formula that
already generalizes to "how many firsts is this whole pile worth" — no new
calibration was invented for this item.

**Rounding rule (a real design decision, not free):** the mockup flagged
sub-segment (bar-stack) labels as an open question with no rounding rule
picked. For the two surfaces actually wired (team total, positional
drill-in subtotal — see Scope below), I picked "round to the nearest
half-first" so a small positional subtotal (e.g. a thin TE room) doesn't
collapse to a bare "0 firsts" while staying close to the mock's whole-number
examples ("≈14 firsts") for team-scale totals. This is a judgment call, not
mandated by #279 — flag if the operator wants integer-only.

## Scope: which raw numbers actually got swapped

The mock's rank-bars frame *illustrates* labels sitting directly above each
bar column; today's shipped chart has no visible per-bar numeric label at
all (only a screen-reader `accessibilityLabel` and the rank numeral render
on-chart) — the mock is an idealization of where the number WOULD go, not a
literal 1:1 diff. Rather than inventing new on-chart UI beyond what #279
asked for, this wires the label into the raw-number displays that already
exist and are unambiguously "team total" / "positional aggregate":

1. **`TeamRow`** (the ranked list under the chart) — the team total shown at
   the right of each row. Labeled only when `subset === 'all'` and no
   position filter is active (the one condition where the displayed number
   is guaranteed to equal the server's authoritative `total_value`).
2. **Drill-in summary line** (`"#1 of 12 · 14,820 value"`) — same
   `subset==='all'`, no-filter condition.
3. **Drill-in per-position group header** (`"QB · 3 · 4.2k"`) — labeled
   whenever `subset === 'all'`, regardless of position filter (the
   per-position subtotal doesn't change with the filter, only which
   sections are shown).

**Explicitly not touched**, matching the mock's own caveats:
- The roster drill-in's per-player values — already solved by #277/#278
  (`TierBadge`/`tier` field), untouched by this item.
- The bar chart's stacked position segments — no numeric label exists there
  today (color-proportion only); the mock itself flagged extending labels
  down to sub-segments as an open false-precision question, not attempted.
- The league-average line (`"Avg 9.4k"`) — an average across teams, not a
  single team's total or a position's subtotal; not what #279 asked for.
- Accessibility labels (`accessibilityLabel` on the bar columns / list rows)
  stay numeric always — precision serves screen-reader users better than a
  rounded label, and this is a one-user rollout so there's no coverage gap.
- Starters/bench subset and position-filtered views keep the numeric
  fallback — the backend only prices `positions[pos].value` and
  `total_value` for the FULL roster, so a filtered/subset number isn't the
  same quantity the label would represent; showing "≈14 firsts" for a
  starters-only sum would be lying about which formula produced it.

## Rollout mechanism (operator-decided, binding)

**New experiment `aggregate_tier_labels`**, mirroring the
`onboarding_v2_rollout` precedent
(`docs/business/analytics/2026-07-18-onboarding-v2-rollout-experiment.md`)
as closely as this surface allows:

| Field | Value | Why |
|---|---|---|
| key / version | `aggregate_tier_labels` v1 | |
| layer | `ranking` | Semantically correct home — this is a `LeagueSummaryScreen`/rankings surface, not `trades_ui` |
| unit_type | `account` | The screen requires sign-in + a selected league; there's no pre-auth device moment to target here (unlike onboarding), so `is_tester_allowlist` resolves against the caller's `sleeper_user_id` — already unioned into `config/tester_allowlist.json` |
| buckets | `[0, 10000)` | Full layer — targeting, not bucketing, narrows to the operator |
| targeting | `{"is_tester_allowlist": true}` | Same mechanism as onboarding — resolved from `FTF_TESTER_ALLOWLIST` env ∪ `config/tester_allowlist.json` |
| variants | `control` 0bp / `treatment` 10000bp | 0-weight control makes treatment certain for the captured unit |
| primary_metric | `wat` | Placeholder catalog metric — no readout is intended for v1 (n=1, exactly like onboarding v1) |
| exposure_surface | `league_summary` | |
| scope | none | No funnel-event stamping need for a display-only label swap |

**Why the experiments engine (not a plain feature flag + allowlist check):**
the engine already has everything this needs — `is_tester_allowlist`
targeting, deterministic assignment, and (per `docs/config-reference.md`)
`config/tester_allowlist.json` as the git-deployable allowlist source
(Render ignores `render.yaml` envVars on a dashboard-created service, which
is why that file exists at all). Building a second, parallel flag+allowlist
mechanism next to one that already does this exact job would be the
"invent a second scale" mistake this item explicitly warns against, just at
the gating layer instead of the value-formula layer.

**One deliberate divergence from the onboarding precedent's client
mechanics:** onboarding surfaces its assignment to the client as a boolean
`client_config.flags` overlay (`onboarding.v2: true`) merged into the global
flag map, and the client checks the flag. This item instead gates by
**field presence** on the `/api/league/power-rankings` payload itself —
`total_value_label` / `positions.*.value_label` are simply absent unless the
RESOLVING caller (the session's `user_id`) is `treatment`. This is the
SAME idiom the very same endpoint already uses for #277/#278's per-player
`tier` field ("absent on old servers / unpriceable rows"), so the client
needs no separate flag plumbing at all — presence of the field IS the gate,
one signal instead of two. Both mechanisms use the identical underlying
`experiments.variant_for(...)` targeting/allowlist call; this is strictly
simpler for a payload-shaped feature (as opposed to onboarding's UI-flow
toggle, where a boolean flag is the more natural fit).

### Backend

- `backend/server.py`: `_aggregate_pick_label(value)` (new helper, next to
  `_pick_gap_equivalent`). In `league_power_rankings_route()`, after
  `compute_power_rankings` builds `teams`, `experiments.variant_for(g_user_id,
  "aggregate_tier_labels")` is checked; on `"treatment"`, every team in the
  response gets `total_value_label` + a `value_label` per core position.
  Non-`"treatment"` (including "no experiment running", the default state
  today) → no new keys, verified byte-identical by test.

### Mobile

- `mobile/src/api/league.ts`: `PowerRankedTeam.total_value_label?: string`
  and `positions.{QB|RB|WR|TE}.value_label?: string` — both optional,
  additive.
- `mobile/src/screens/LeagueSummaryScreen.tsx`: `TeamRow` takes a new
  optional `totalLabel` prop (falls back to the existing
  `Math.round(active).toLocaleString()` when absent); the drill-in summary
  line and per-position group header do the same inline. No new component,
  no new state — a label-vs-number branch at three existing render sites.

## Prod launch runbook (once this branch ships)

Not run yet — this build stays on its worktree branch per the task brief
(no merge/push). When an operator ships it:

1. Merge → `main` (Render auto-deploys); EAS build → TestFlight.
2. Confirm the operator's unit is already in `config/tester_allowlist.json`
   (it is: `313560442465169408`, the same account id the
   `onboarding_v2_rollout` allowlist already carries — no new allowlist
   entry needed for this experiment, since it's account-unit and targets
   the same operator identity).
3. Create + launch the experiment against prod:

   ```bash
   curl -s -X POST https://fantasy-trade-finder.onrender.com/api/admin/experiments \
     -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
     -d '{
       "key": "aggregate_tier_labels", "layer": "ranking", "unit_type": "account",
       "bucket_start": 0, "bucket_end": 10000,
       "targeting": {"is_tester_allowlist": true},
       "variants": [
         {"name": "control", "weight_bp": 0},
         {"name": "treatment", "weight_bp": 10000}
       ],
       "primary_metric": "wat", "exposure_surface": "league_summary"
     }'
   # → {"key": "aggregate_tier_labels", "version": 1, "status": "draft"}

   curl -s -X POST https://fantasy-trade-finder.onrender.com/api/admin/experiments/aggregate_tier_labels/transition \
     -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
     -d '{"to": "running", "version": 1, "override_underpowered": true,
          "reason": "n=1 operator-only rollout, not a powered test"}'
   ```

4. Reopen the app on the operator's device (League tab) — team + positional
   totals render as pick-equivalent labels; every other league member sees
   the numbers exactly as before.

## Widening the cohort later

`POST /api/admin/experiments/aggregate_tier_labels/revise` with the
allowlist targeting dropped (e.g. replaced with an `app_version_gte` floor
or removed entirely) and weights rebalanced (e.g. 50/50) — same pattern as
`onboarding_v2_rollout`'s documented graduation path. No code change is
needed on either client or server to widen the cohort; it's purely an
admin-API call once the operator decides to ship it broadly. If/when that
happens, the rounding rule (nearest half-first) and the "subset==='all' only"
scoping above should get a fresh look — they were sized for a one-user
rollout, not necessarily for general use.

## Gates run

- `python3 -m pytest backend/tests -q` → 2064 passed, 1 skipped (baseline
  2060 passed / 1 skipped + 4 new tests in `test_power_rankings.py`:
  assignment operator-only, route labels present + conversion-correct for
  the allowlisted caller, byte-identical response for a non-allowlisted
  caller under a running experiment, and formula-reuse correctness).
- `cd mobile && npx tsc --noEmit` → clean (symlinked
  `.claude/worktrees/agent-a16b8c9e20f110454/mobile/node_modules` for the
  run, removed after per the task brief).

## Docs updated

- `docs/api-reference.md` — `/api/league/power-rankings` entry documents the
  new additive `total_value_label` / `positions.*.value_label` fields and
  the gating mechanism.
- This status doc.
- `docs/feedback/items/INDEX.md` — new row for #279.

Not touched (n/a): `docs/data-dictionary.md` (no schema change — experiments
already have a table, no new column), `docs/config-reference.md` (no new
feature-flag key; `experiments.engine` and `config/tester_allowlist.json`
are pre-existing, documented under the `onboarding_v2_rollout` precedent
already).

## Feature-scope gate note

This was scoped as an **express-adjacent** build per the task brief's own
binding requirement (operator-decided rollout mechanism specified up front,
formula direction pre-documented in the #270/#279 mockup lab and this
item's own prior research) — not a from-scratch feature-scope block. It
does touch an API payload shape and a new experiment (a bright-line item per
root `CLAUDE.md`'s express-lane rule), so: full gates were run (tests +
typecheck), docs were updated, and this status doc records the formula
reuse, gating mechanism, and widen-later path in place of a separate
`docs/templates/feature-scope.md` copy — the task brief itself supplied the
equivalent of that scope block's answers.
