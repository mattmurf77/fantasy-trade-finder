# W1 serving re-light — operator TestFlight checklist

**Date authored:** 2026-08-20 · **Package:** PR-S (fit-challenger PLAN-v2 §3)
**When to run:** within the hour of the W1 knob flip (`bakeoff_serve_interleaved = 1`,
per PLAN-v2 §5 W1). This checklist is the D-056 runtime evidence for the re-light —
the only runtime proof mobile gets — so run every step and log the outcome in
`living-memory/TEST_LEDGER.md`.

**Source:** draft B §7's 8-step list, adopted by PLAN-v2 §6. Steps 4, 6 and 7 verify
via the **readout, not the UI** — the app deliberately shows no arm labels. Run the
SQL against production Postgres via `backend/tools/prod_analytics.py` (read-only
posture) or an equivalent read-only session; `DATABASE_URL_PROD` is in
`secrets.local.env`.

**Precondition:** PR-M and PR-S merged and deployed; the W1 flips were made via
`scripts/set_knob.py` (logged, `source='operator'`); knob values per PLAN-v2 §5 W1:
`bakeoff_serve_interleaved = 1` · `bakeoff_group_size = 0` · `bakeoff_deck_limit = 30`
· roster B + D + C (`bakeoff_include_challenger = 1`, `bakeoff_include_gen_v2 = 1`,
`bakeoff_include_baseline = 0`).

---

## The 8 steps

| # | Step | Expected result | Pass? |
|---|---|---|---|
| 1 | Open a tester league in the app (a real Sleeper league you own, not the demo league — `league_demo` is excluded from the bake-off by `bakeoff_active`). | League loads normally. | ☐ |
| 2 | Generate an **untargeted** deck: no pinned player, no opponent selected, no "what can I get for X". | Deck generates without error; progress bar completes. | ☐ |
| 3 | Count the deck. | **≥ 20 cards.** Fewer is the R-9 deck-shrink symptom — investigate same day; median < 18 on 2 consecutive days is the pre-registered revert trigger. | ☐ |
| 4 | Verify mixed arms in the first 10 cards — **via the readout, not the UI** (query A below). | First 10 impression rows of this deck span **≥ 2 distinct `model_arm` values** (expect `current` + `challenger`; `gen_v2` only where an opponent is boarded). All-one-arm means the interleave is not live or every other arm zero-carded — check `bakeoff_runs.arms_json` before concluding. | ☐ |
| 5 | Decide **5 cards** in the app — mix of likes and declines, and **always give a decline reason** (M5 tester protocol). | Decisions register normally in the UI. | ☐ |
| 6 | Verify the 5 decisions landed attributed (query B below). | **5 `deck_outcomes` rows** for this deck, each joining to a `deck_impressions` row with **non-null `model_arm`**. A null `model_arm` on a decided card means attribution broke — stop and file it. | ☐ |
| 7 | Pin a player ("what can I get for X?") and generate that deck. | The pinned deck is **NOT interleaved** — `bakeoff_active` excludes pinned/opponent-scoped decks. Verify via query C: **no new `bakeoff_runs` row** for the pinned job, and its impression rows (if the F1 spine logs them) carry null `model_arm`. The pinned deck goes through the normal presentation stack. | ☐ |
| 8 | **Touch nothing else.** No other knob, flag, or setting changes in this session — W1's one engine-affecting change is the re-light itself (R-7 control-arm discipline). | Nothing else flipped; `model_config_changes` shows only the W1 flips for today. | ☐ |

## Rollback rehearsal (2 steps — do this once, same day)

The point: prove the revert lever works while nothing is on fire, so the R-9 tripwire
revert is a rehearsed motion, not a first attempt.

| # | Step | Expected result | Pass? |
|---|---|---|---|
| R1 | `python3 scripts/set_knob.py bakeoff_serve_interleaved 0 --source operator` (logged; one `model_config_changes` row appears). | Knob reads back 0; change row recorded with `source='operator'`. | ☐ |
| R2 | Generate a fresh untargeted deck in the app. | The deck is **arm-B normal-stack**: its `bakeoff_runs` row has `served_arm = 'current'` (dark mode — all arms still generate and log), every impression row reads `model_arm = 'current'`, and the deck went through the normal re-rankers. | ☐ |

Then re-light (`set_knob.py bakeoff_serve_interleaved 1 --source operator`) and confirm
the next deck's run row has `served_arm IS NULL` again. Log both flips' change rows in
the TEST_LEDGER entry.

---

## Readout queries

**A — arms in the first 10 of the latest deck (step 4):**

```sql
SELECT model_arm, arm_rank, card_index
FROM deck_impressions
WHERE user_id = '<your user_id>' AND league_id = '<league_id>'
  AND deck_job_id = (SELECT deck_job_id FROM deck_impressions
                     WHERE user_id = '<your user_id>' AND league_id = '<league_id>'
                     ORDER BY served_at DESC LIMIT 1)
ORDER BY card_index
LIMIT 10;
```

**B — decided cards carry attribution (step 6):**

```sql
SELECT o.action, o.acted_at, i.model_arm, i.arm_rank
FROM deck_outcomes o
JOIN deck_impressions i ON i.impression_id = o.impression_id
WHERE i.user_id = '<your user_id>' AND i.league_id = '<league_id>'
ORDER BY o.acted_at DESC
LIMIT 5;
```

**C — pinned deck stayed out of the bake-off (step 7):**

```sql
-- No bakeoff_runs row should exist for the pinned job's deck_job_id.
SELECT run_id, served_arm, deck_size FROM bakeoff_runs
WHERE deck_job_id = '<pinned job id>';
```

**Serving-mode check (used in R2 and by the M4 bypass tripwire):** an interleaved run
row records `served_arm IS NULL`; a dark run records `served_arm = 'current'`. There is
no dedicated re-ranker-bypass marker on the row — `served_arm` is the only recorded
serving-mode state (finding pinned by
`test_run_row_serving_mode_is_served_arm_not_a_bypass_marker` in
`backend/tests/test_bakeoff_serving.py`).

## After the checklist

- Log the outcome (all boxes, any anomaly, the two rehearsal change-rows) in
  `living-memory/TEST_LEDGER.md`.
- SC1 (first non-`current` decision) is due within 3 days; SC2 (deck median ≥ 24) and
  the daily tripwires (M4) take over from here — this checklist is the hour-zero gate,
  not the monitoring plan.
