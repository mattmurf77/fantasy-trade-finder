# Manual TestFlight checklist — package-benchmark fix + gap auto-sweetener

**Date written:** 2026-08-21 · branch `fix/package-benchmark-sweetener`
**Why this file exists:** D-056 retired Maestro and the simulator entirely, so
a manual TestFlight pass is the ONLY runtime evidence mobile gets. Everything
in this change is backend-only (zero mobile files touched), but it moves what
the deck contains and what the value bars read, so "the tests pass" is not
runtime evidence that the cards render sanely.

**Run this AFTER the Monday merge, on a build that contains it.** Nothing here
is a substitute for the pre-ship gates (CI green + the TEST_LEDGER entry).

---

## 0. Before you start

- Confirm the build is on this change: backend deploy sha ≥ the merge commit.
- Use a real league with a real board — the whole point is production values.
- Have the readout SQL below open in a second window; steps 4–6 need it.

## 1. The deck still fills

1. Pull a fresh deck (Trade Finder → refresh) on your main league.
2. **PASS:** the deck is not obviously short. Expect a modest shrink versus
   what you remember — the fixture measurement put it at **−4 % across the
   served arm roster**, worst single case −20 % on one arm/path/league cell
   (TEST_LEDGER 2026-08-21a). A deck that drops by half is NOT the expected
   cost — stop and report it.
3. **FAIL condition:** empty deck, or "no trades found" on a league that
   produced a deck yesterday.

## 2. The card that started this

4. Look for any card where you send **three or more mid-tier players for one
   stud**. Under the old math these priced ~0.94 fairness and served as fair.
5. **PASS:** those cards are now rare, and any that DO serve show a value bar
   that reads honestly — the give side visibly lower than the naive sum of the
   pieces. The reference case is Rice + Etienne + Swift + Corum → Nacua, which
   should no longer appear at all.

## 3. Sweetened cards render sanely — the main event

6. Find a card with an extra piece attached to close a gap (the payload key is
   `gap_sweetener`; in the UI it just looks like one more asset on a side).
7. **PASS, all four:**
   - the equalizer player appears in that side's player list, not floating
     outside it;
   - the **value bar totals include the equalizer** — give and receive totals
     move, and the bar is visibly closer to even than an unsweetened card;
   - the remaining gap reads **≤ one late 1st (1539)** in whatever units the
     bar shows;
   - the card's fairness/verdict copy does not contradict the bar.
8. **PASS:** tapping into the card detail shows the same asset list and the
   same totals as the deck card — no drift between list and detail.
9. **FAIL conditions to watch for specifically:**
   - a value bar whose two halves sum to more/less than the listed assets;
   - an equalizer that is a player you marked **untouchable** (give side) or
     one you marked **not interested** (receive side) — either is a bug;
   - on a **pinned** job ("trade away exactly X") a card that ships an asset
     you did not pin — this was a real defect, fixed in `49c1d76`, and this
     step is its runtime confirmation;
   - on an **acquire-position** job ("get me a RB") a card that hands back an
     off-need position — same defect, same fix.

## 4. Send one

10. Propose one sweetened card to a real counterparty through the app.
11. **PASS:** the proposal that lands in Sleeper contains exactly the assets
    the card showed, equalizer included.

## 5. Readout SQL — how many cards were sweetened

Run against prod (read-only). `gap_sweetener` is stamped on **every**
`deck_impressions` row inside `features_json` — null when the card was not
sweetened — so the split is unambiguous and needs no absent-key handling.

```sql
-- sweetened share of served cards, last 3 days
SELECT
  (features_json::jsonb ->> 'gap_sweetener') IS NOT NULL AS sweetened,
  COUNT(*) AS impressions
FROM deck_impressions
WHERE served_at > NOW() - INTERVAL '3 days'
  AND COALESCE(is_ghost, 0) = 0
GROUP BY 1;

-- the gap distribution that motivated the change, per arm
SELECT
  model_arm,
  COUNT(*) AS cards,
  AVG(ABS((features_json::jsonb ->> 'give_value')::numeric
        - (features_json::jsonb ->> 'receive_value')::numeric)) AS mean_gap,
  SUM(CASE WHEN ABS((features_json::jsonb ->> 'give_value')::numeric
                  - (features_json::jsonb ->> 'receive_value')::numeric) > 1539
           THEN 1 ELSE 0 END) AS over_one_late_first
FROM deck_impressions
WHERE served_at > NOW() - INTERVAL '3 days'
  AND COALESCE(is_ghost, 0) = 0
GROUP BY 1 ORDER BY 1;

-- what the sweetener actually closed, card by card
SELECT
  features_json::jsonb -> 'gap_sweetener' ->> 'side'       AS side,
  (features_json::jsonb -> 'gap_sweetener' ->> 'gap_before')::numeric AS before,
  (features_json::jsonb -> 'gap_sweetener' ->> 'gap_after')::numeric  AS after
FROM deck_impressions
WHERE served_at > NOW() - INTERVAL '3 days'
  AND features_json::jsonb -> 'gap_sweetener' IS NOT NULL
ORDER BY 2 DESC LIMIT 50;
```

**PASS:** `gap_after` ≤ 1539 on every row of the third query. Any row above it
means a sweetened card shipped without actually closing its gap.

**Expected from the fixture measurement, so you know what "normal" looks
like:** the sweetener is a *narrow* pass — roughly one card per deck on the
fixture leagues, not a third of the deck. A sweetened share above ~20 % or
below 0 % on a live deck both deserve a second look.

## 6. The arm-C caveat the operator should see in the data

Arm C (`gen_v2`) inherits the benchmark fix in its DISPLAYED values but does
**not** run the sweetener (a named v1 follow-up, scope.md). The fixture
measurement predicts its over-1539 share goes UP, not down (0 → 3 of 22 on
one league). The per-arm query above is where that shows.

**PASS:** arm C's over-1539 count is elevated relative to arm `current` —
that is the predicted, accepted state, not a regression.
**ESCALATE:** arm `current`'s over-1539 share is also elevated — that would
mean the sweetener is not reaching the served arm.

---

## Rollback, without a deploy

Every part of this is knob-gated in `model_config` (all DB-seeded, no deploy):

| Symptom | Set |
|---|---|
| Deck too short / packages priced too harshly | `package_bench_trade_wide` = 0 (restores the pre-fix own-max math byte-identically) |
| Sweetened cards look wrong | `sweetener_gap_threshold` = 0 (skips the pass entirely) |
| Cross-side discount too aggressive but the benchmark is right | raise `package_floor_cross` from 0.40 toward 0.70 |

Hot-reload path: update the `model_config` row, then the next generated deck
picks it up — no redeploy, no TestFlight build.
