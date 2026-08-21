# Code-walk proof — composite window model (#372)

D-056 retired the simulator, so this file is the runtime evidence for behavior
that no structural check and no typecheck can see. Every claim is cited to
`file:line` on `claude/372-window-composite`.

Read alongside [scope.md](scope.md) (the model, the calibration, the sabotage
table) and [testflight-checklist.md](testflight-checklist.md).

---

## 1. INV-372 — flag OFF is byte-identical for every caller

**Claim:** with `trade.outlook_composite` off, `infer_team_outlook` returns
exactly what `origin/main` (`c00a9a6`) returned — same outlook, same score,
same `signals` keys, same `model` keys — even for a caller that passes both new
kwargs. No deck moves.

**Trace.**

1. The two kwargs are optional and default `None` —
   `backend/trade_service.py:3081-3082`.
2. Everything the composite touches sits inside one branch gated on the flag
   **and** on a signal being supplied — `backend/trade_service.py:3228`:

   ```python
   if FLAGS.trade_outlook_composite and starter_signal is not None:
   ```

   `signals["starters"]`, `signals["playoff"]` and every composite `model` key
   are assigned only inside it (`:3229`, `:3234`, `:3241-3252`). With the flag
   down the branch never runs, so a caller that passes both kwargs gets a
   `signals` dict key-for-key identical to a caller that passes neither.
3. `composite` initialises `False` at `backend/trade_service.py:3227` and is
   only reassigned inside that branch, so the score expression at `:3273`
   takes its `else` arm — the legacy weights, `_c("infer_w_vet_share")` etc.,
   at `:3290-3294`. That arm is character-for-character the expression
   `origin/main` used.
4. The route never even builds a signal while the flag is off:
   `backend/server.py:23590-23600` — `_starter_sig` returns `None` on the
   `if not composite_on` line before touching `starter_value_by_uid`, and
   `_odds_sig` (`:23602-23606`) does the same.

**Why the pin is a golden and not a re-derivation.** The expected scores in
`backend/tests/test_window_composite.py:110-134` were produced by running the
same three fixtures against a `git archive c00a9a6 backend config` tree, not by
re-evaluating the formula this module now contains — a re-derivation would
agree with any bug both copies shared. `GOLDEN_MODEL_KEYS` is pinned as tightly
as `score`, because `window.model` is *rendered*: a key appearing there that the
score is not applying is D-101's defect again.

Sabotage S3 (remove the flag gate) → RED on
`test_flag_off_ignores_supplied_composite_signals_entirely`.

## 2. INV-372b — flag ON without an applied starter signal still moves nothing

**Claim:** lighting the flag re-weights the **window beat** and not one deck.

**Trace.** The three generation callers pass four positional arguments and
cannot pass a fifth:

- trade engine — `backend/trade_gen_v2.py:986`
- mock draft — `backend/server.py:14052`
- outlook seed — `backend/server.py:5333`

They *cannot* be given a starter signal without new plumbing, and that is
structural rather than incidental: starter value is a **league-relative** number
(`starter_value_signal` needs the whole league's starters — `trade_service.py:2957-2962`),
and it can only be summed off a `compute_power_rankings` call. No generation
path makes one. The only caller that does is the Team Review route
(`backend/server.py:23590-23600`, which sums it at `:23409-23417`).

Belt and braces: even a caller that *did* pass an unreadable signal falls back.
`composite` is `bool(starters_sig.get("applied"))` at
`backend/trade_service.py:3231`, and `starter_value_signal` returns
`applied: False` for both refusal cases (`trade_service.py:3005-3011`), so
`:3273` takes the legacy arm and `:3235`'s model re-statement never runs.

Pinned by `test_flag_on_without_a_starter_signal_is_still_the_golden` and
`test_flag_on_with_an_UNAPPLIED_starter_signal_is_still_the_golden`.
Sabotage S1 and S2 → RED on those exact tests.

## 3. The composite is ONE re-weighted score, not a fourth term

**Claim:** with the composite live, the whole weight vector changes at once —
age at 40 %, starters and playoff carrying the difference.

**Trace.** `backend/trade_service.py:3273-3288`:

```python
if composite:
    score = (
        _c("infer_composite_w_vet")     * signals["vet_share"]
        - _c("infer_composite_w_youth") * signals["youth_share"]
        - _c("infer_composite_w_pick")  * (pick_share - equal_share)
        + _c("infer_composite_w_starter") * float(starters_sig["index"])
    )
    if playoff_sig is not None and playoff_sig.get("applied"):
        score += _c("infer_composite_w_playoff") * float(playoff_sig["index"])
```

Defaults at `backend/trade_service.py:303-319`. Note the **sign convention
split**, which is deliberate and commented at `:3283-3286`: a better starting
lineup and better playoff odds both read as contending so both **add**, while
accumulating pick capital reads as rebuilding and **subtracts**.

`test_age_is_a_lighter_driver_by_exactly_the_ratio_claimed` pins the ratio at
exactly 0.40 against the legacy age contribution rather than "roughly lower",
and asserts `abs(score) < abs(legacy_age)` on both an old and a young fixture.
Sabotage S10 (leave the age weights at 1.00 inside the composite) → RED.

## 4. Degrade per signal, never all-or-nothing, never a silent zero

**Claim:** an unreadable starter signal or a refused playoff band leaves the
rest of the model scoring, and the payload names what is missing.

**Trace.**

- `starter_value_signal` (`backend/trade_service.py:2957-3022`) returns three
  provenances — `lineup_unknown` when the platform exposes no template
  (`:3003-3004`), `absent` when the league prices no starter value at all
  (`:3009-3011`), `observed` otherwise (`:3012`).
- `playoff_odds_signal` (`:3023-3075`) **inherits** #371's admission rule
  rather than re-deriving it: the caller hands it
  `resolve_window_from_odds`'s own refusal string (`backend/server.py:23577-23581`),
  so "Sleeper-only" and "refused in preseason" exist in exactly one place
  (`backend/team_review.py:71-113`).
- The fourth value, `odds_disabled`, is set at `backend/server.py:23577` and
  means `trades.window_from_odds` is off — *we never asked*, which is not
  *we asked and got nothing*. It deliberately does **not** enter
  `window.odds_reason`'s vocabulary; the comment at `:23570-23576` says why,
  and `test_odds_disabled_is_not_odds_unavailable` proves the two vocabularies
  stay disjoint.
- A refused term is **absent from the score**: `:3287` requires
  `playoff_sig.get("applied")`. Both blocks still ride `signals`
  (`:3229`, `:3234`) so the card can state the refusal beside the band it
  applies to.

**The subtlety that made one of these tests dead.** `playoff_odds_signal`
zeroes `index` whenever it refuses, so a test built on the helper's own output
cannot distinguish "the `applied` guard works" from "the number happened to be
0" — sabotage S5 passed against a broken function on the first run.
`test_a_refused_playoff_term_is_absent_from_the_score_not_a_zero` now hands
`infer_team_outlook` a refused block with `index=0.8`
(`test_window_composite.py`, the `loud_but_refused` local), and its starter-side
sibling does the same. Both go RED under S5/S12.

## 5. The empty-roster guard suppresses every term

**Claim:** a team whose roster cannot be priced has no window, and half a model
is not an opinion.

**Trace.** `backend/trade_service.py:3260-3270` — the `total <= 0` early return
sets `applied = False` on the firsts block *and* on both composite blocks
before returning `("not_sure", 0.0, signals)`. Without this the pick-centering
term would read "owns zero picks" as a contend signal, and the starter block
would ship `applied: True` beside a score it never entered.
Pinned by `test_flag_on_empty_roster_suppresses_every_composite_term`.

## 6. Precedence — the band drives once or not at all

**Claim:** with `trade.outlook_composite` and `trades.window_from_odds` both
on, the playoff band is **scored as a term** and no longer **overwrites** the
verdict.

**Trace.** `backend/team_review.py:114-147` — `resolve_window_precedence`:

```python
if composite_applied:
    return "composite", roster_window
if odds_source == "odds" and odds_implied:
    return "odds", odds_implied
return odds_source, roster_window
```

Called once, at `backend/server.py:23637-23640`. It lives in `team_review.py`
rather than inline in the handler for the same stated reason
`resolve_window_from_odds` does (`team_review.py:143-146`): *a precedence rule
that only exists inside a Flask handler is a rule nothing can test.* Extracting
it is what let sabotage S7 be run at all.

Three consequences the tests pin:

- composite applied ⇒ `("composite", roster_window)`, so `inferred ==
  roster_inferred` by construction — nothing replaced anything
  (`test_composite_suppresses_the_band_replacement`).
- composite not applied ⇒ #371 behaves exactly as it did, down to `source`
  staying `None` while its own flag is off
  (`test_without_the_composite_371_is_untouched`).
- composite applied with `trades.window_from_odds` **off** ⇒ `source` still
  ships as `"composite"`, because the card renders different weights and
  different copy and has to know
  (`test_composite_source_ships_even_when_the_odds_flag_is_off`).

## 7. The route computes no new value

**Claim:** starter value is summed off numbers already on the wire.

**Trace.** `backend/server.py:23409-23417`:

```python
starters_known = any(t.get("starters") is not None for t in teams)
for t in teams:
    ids = set(t.get("starters") or [])
    v = sum(float(r.get("value") or 0.0) for r in (t.get("roster") or [])
            if str(r.get("player_id")) in ids)
```

`teams` is the `compute_power_rankings` result the standing beat already ranks
with (`backend/server.py:23356`). `starters` is that function's **value-optimal
fill** (`backend/power_rankings.py:247` → `optimal_starters`, `:99`), and
`roster[].value` is the same per-player number the standing beat shows
(`power_rankings.py:218`). So there is no second definition of "starter value"
to drift from the first, which is `team_review.py`'s whole design rule.

`starters_known` is read once for the league rather than per team, and the
comment at `server.py:23400-23408` says why: `starters` is `None` for **every**
team at once (it is a function of the league's lineup template), so a
non-Sleeper league degrades the whole composite rather than half of it.

**Every league-mate gets the same model.** The member loop
(`backend/server.py:23606-23621`) passes `_starter_sig(uid)` and `_odds_sig(uid)`
for each member, and `band_by_uid` (`:23520`, filled at `:23528-23538`) carries
**every** team's playoff percentage rather than only the caller's. The
`partners` beat pits your window against your league-mates', and two different
definitions of "contender" in one payload is the failure #365 was arranged to
avoid.

## 8. The card shows every term it scored, and nothing it did not

**Claim:** D-101 holds. The beat renders the model it ran.

**Trace.** `mobile/src/screens/TeamReviewScreen.tsx`:

- `:453-459` — `st`, `po`, and `composite = !!st && st.applied && m?.composite
  === true`. **Both** payload markers, because either alone can be true on a
  payload missing the other half.
- `:557` / `:599` — the two new cards, `team-review.window.starters` and
  `team-review.window.playoff`. Each is rendered whenever the backend *computed*
  the signal, including when it refused to score it, and each branches on
  `provenance` for its copy (`:562-585`, `:604-628`).
- `:662-673` — the two contribution rows inside the arithmetic card, gated on
  `starterScored` / `playoffScored` (`:457-460`), which are themselves derived
  from `applied` and from the weight being present in `model`. A weight is
  never printed beside a term that did not score, and a term that scored is
  never missing from the itemisation.
- **No weight is hardcoded.** `wStarter = m?.w_starter_index` (`:456`) and
  `wPlayoff = m?.w_playoff_index` (`:459`). Under the composite
  `model.w_vet_share` is `0.40` rather than `1.00` and the existing rows at
  `:641-652` read it, so the arithmetic on screen adds up to the total beside
  it. `check-window-composite.js` assertion 1b fails on any composite weight
  literal appearing in the beat.
- `:686-696` — the "that is the whole model" sentence. It already claimed the
  model *"does not read your starting lineup"*, which becomes a lie the instant
  this flag is lit; it now enumerates what actually ran, in every combination
  of the three optional terms.
- `:601-603` and `:610` — the playoff card renders **the band**, never the
  percentage. `playoff_pct` appears only inside an `accessibilityLabel`, which
  is what `check-team-review.js` assertion 5b requires and what caught the
  first draft of this card.

## 9. What a user on an older build sees

`build 122` predates every one of these keys. `_window`
(`backend/team_review.py:275-278`) adds `signals.starters` / `signals.playoff`
only when the engine flag put them in `signals`, and the composite `model` keys
only ship from inside the flag branch. With the flag off the `window` block is
key-for-key what build 122 already parses; with it on, the extra keys are
additive and every new field is optional in
`mobile/src/api/teamReview.ts` (pinned by `check-window-composite.js`
assertion 7). Pinned server-side by
`test_window_omits_the_blocks_entirely_while_the_flag_is_off`.
