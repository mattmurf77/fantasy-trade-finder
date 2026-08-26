# Code-walk — #365 net first-round capital, #371 playoff-odds window

**Date:** 2026-08-20 · **Branch:** `worktree-agent-a3ea3b1d38e084930` · **Base:** `bc43b6f`
**Scope block:** [scope.md](scope.md) · **Decisions:** D-110, D-111

Written under D-056: the simulator is retired, so this file-and-line trace plus the
[TestFlight checklist](testflight-checklist.md) *are* the evidence for the behaviour a capture
would once have shown. Every line number below is against this branch's tree.

---

## 1. The constraint, restated in code

`infer_team_outlook` has four consumers and only one of them is Team Review:

| Consumer | Call site | What a score change does |
|---|---|---|
| Trade engine | `backend/trade_gen_v2.py:986` | reprices the opponent's side of every candidate |
| Trade engine (v1 path) | `backend/trade_service.py:4381` | same |
| Mock draft | `backend/server.py:14013` | changes every CPU persona |
| Outlook seed | `backend/server.py:5320` | changes the deck for every undeclared league |
| **Team Review** | `backend/server.py:23374` (the caller), `:23363` (each member) | changes the window beat |

So the build is arranged so that the first four cannot move. Two mechanisms, in series.

**Mechanism 1 — the flag.** `backend/trade_service.py:2706`:

```python
if FLAGS.trade_outlook_net_firsts and first_round_ledger is not None:
```

With the flag down the new kwarg is read and discarded. Nothing enters `signals`, nothing enters
`model`, nothing enters `score`. `backend/tests/test_window_signals.py::
test_flag_off_ignores_a_supplied_ledger_entirely` asserts the whole tuple is equal — not
equivalent — to the no-ledger call, against goldens captured by running these exact fixtures
against `git archive bc43b6f backend`, a tree that had never heard of the kwarg. Sabotage **S1**.

**Mechanism 2 — the ledger.** The four non-Team-Review callers pass four positional arguments and
were not touched, so `first_round_ledger` is `None` for all of them even with the flag lit.
`test_flag_on_without_a_ledger_is_still_the_golden` pins it; sabotage **S2** (widening the
condition to the flag alone) turns it red. This is what makes *"lighting the flag moves the window
beat and not one deck"* a fact rather than an intention.

**Why the two `model` keys are inside the flag branch** (`trade_service.py:2711-2712`). `model` is
rendered on screen (D-101). A `w_net_firsts` present while the term is not applied would put a
weight on the card for a row that does not exist — the same class of defect D-101 was written to
stop. Sabotage **S7**.

---

## 2. #365 — where the signal comes from

### 2.1 The data was already there

`draft_picks` carries both halves of *"1sts owned vs traded away"*:
`owner_user_id` (`backend/database.py:1050`) is who holds the pick now, `original_user_id`
(`:1052`) is whose pick it was. Both have shipped since #158. No new column, no new table, no
platform call.

### 2.2 The reader — `backend/server.py:23175`

One `load_draft_picks` for the whole league (the same read `_power_picks_by_owner` already
performs), filtered to `round == 1` at `:23206`, then a two-sided walk at `:23217-23239`:

- a pick's **current** owner gets `held += 1`, and `acquired += 1` when it moved;
- a pick's **original** owner gets `own_total += 1`, and `traded_away += 1` when it moved.

`net = acquired − traded_away`, which is identically `held − own_total`: the "own firsts retained"
count appears on both sides and cancels. So the operator's phrasing and the arithmetic are the same
quantity, which is why the card can print the counts and the term without them disagreeing.

Two guards worth naming:

- **`round == 1` only** (`:23206`). Sabotage **S9** — counting every round makes a manager who
  shipped two seconds read as a seller.
- **A NULL `original_user_id` is not a trade** (`:23221`): `orig = str(...) or cur`. An
  un-attributable row (an MFL crosswalk gap) falls back to "never moved" rather than inventing a
  counterparty. Sabotage **S8**.

The read is reached only from `:23352-23353`, inside `if is_enabled("trade.outlook_net_firsts")`,
so a flag-off request costs exactly the queries it costs today.

### 2.3 The honesty gate — `trade_service.first_round_signal`, `backend/trade_service.py:2558`

This is the part the operator ruled on directly. A league synced before pick provenance was
captured has `original_user_id == owner_user_id` on **every** row, and from inside the function
that is indistinguishable from a league where nobody has traded a first. So the reader computes one
league-wide fact — `league_any_traded` (`server.py:23225`, `:23241`) — and the signal refuses to
score a zero it cannot vouch for (`trade_service.py:2601-2603`):

| `provenance` | Reached when | Term | Card copy (`TeamReviewScreen.tsx:465-482`) |
|---|---|---|---|
| `absent` | no round-1 rows at all | not applied | "We have no draft-pick records for this league…" |
| `none_traded` | rows exist, nothing recorded as moved | not applied | "…either none has, or the trade history predates what we can see — so we are not counting this signal." |
| `observed` | at least one first is under a different owner | applied | the ledger, plus the net read in words |

Sabotage **S5** (delete the `none_traded` branch) and **S17** (collapse the client branch).

### 2.4 The term — `backend/trade_service.py:2730-2734`

```python
if firsts is not None and firsts["applied"]:
    score -= _c("infer_w_net_firsts") * firsts["net_share"]
```

Sign convention matches the existing pick-capital term directly above it: **accumulating** pick
capital reads as rebuilding, so a positive net subtracts and a manager who has sold his firsts
gains. Sabotage **S3**.

`net_share = clamp(net / max(own_total, 1), ±infer_net_firsts_cap)` at `:2607-2609`. Sabotage
**S4**. And the `total <= 0` early return forces `applied = False` (`:2718-2719`) so a team with no
readable roster never reports a term it did not score — half a model is not an opinion. Sabotage
**S6**.

**Bound.** `infer_w_net_firsts = 0.10` against a `not_sure` band of ±0.08. On the only real corpus
available (`scope.md` §7.1) `|net_share| ≤ 0.75`, so the observed contribution range is ±0.075: the
term can move an extreme team one bucket and can never move any team two.
`test_the_term_can_move_one_bucket_and_never_two` pins that a −0.89 roster stays a rebuilder no
matter what its picks say.

---

## 3. #371 — where the odds come in

### 3.1 The band read moved, and only moved

`backend/server.py:23466-23496` is the #357 band block, unchanged in substance: same guards
(`outlook.odds` on, platform Sleeper, bundle present, row found), same try/except, same six keys.
It now assigns to a local `outlook_band` and the payload assignment happens at `:23557-23558`:

```python
if outlook_band is not None:
    payload["standing"]["outlook"] = outlook_band
```

Identical result — `standing.outlook` is present exactly when it was before and absent (never
null-filled) otherwise. It moved above `build_team_review` because the band may now feed the window,
and the window is built inside the composer. The one behavioural difference is ordering: on a
league that does not resolve (the `404 league_not_found` path) the odds work now happens before the
404 instead of being skipped. That costs a cached simulator read on a request that was already
failing, and buys the hoist.

### 3.2 The ruling is a function, not an `if` in a route — `backend/team_review.py:71`

`resolve_window_from_odds(outlook_band, completed_weeks) -> (source, odds, reason)` was extracted
deliberately: it is the whole of the operator's decision, and a rule that lives only inside a Flask
handler is a rule nothing can test. Route call: `server.py:23508-23511`.

| Input | Returns | Why |
|---|---|---|
| no band | `("roster", None, "odds_unavailable")` | ESPN/MFL/Fleaflicker are `NotImplemented` stubs in `backend/outlook/league_state.py`, `outlook.odds` may be off, the sim may fail. None of those may cost the user a window. Sabotage **S11** |
| band, `completed_weeks == 0` | `("roster", odds, "preseason")` | D-094: preseason skill lower CI bound +2.9 %. The band is still **returned**, so the card shows what was available and says why it was refused. Sabotage **S10** |
| band, unknown label | `("roster", odds, "odds_unavailable")` with `implied: None` | an unmapped band surfaces as None, never as a silent `not_sure` |
| band, weeks played | `("odds", odds, None)` | the band drives |

`WINDOW_FROM_BAND` (`team_review.py:65`) is `likely → contender`, `tossup → not_sure`,
`unlikely → rebuilder` — a cross-client encoding, so the client renders `odds.implied` and never
re-derives it. `test_band_map_covers_every_band_and_never_infers_an_extreme` asserts the map's key
set equals the set `playoff_band` can actually emit, so a new band cannot silently fall through.

### 3.3 The payload keeps both answers — `backend/team_review.py:180`, `:229-233`

`_window` ships `source`, `roster_inferred`, `odds` and `odds_reason` **only** when `source is not
None`, which the route sets only under the flag (`server.py:23506`). Flag off ⇒ the window block is
key-for-key what it was (`test_window_is_shape_identical_when_both_flags_are_off`, sabotage
**S12**).

`roster_inferred` is always the heuristic's own verdict, even when the odds overrode it
(`:231`, sabotage **S13**) — so the payload carries **both** definitions of "contender" instead of
one silently replacing the other. That is the difference between "informs" and "replaces", written
into the contract rather than into a comment.

One consequence, stated rather than hidden: `build_team_review` derives the `partners` comparison
from the same window (`team_review.py:508`),
so an odds-driven flip reorients that beat too. That is intended —
`test_the_odds_window_also_reorients_the_partners_beat` pins it — because two definitions of
"contender" inside one payload is precisely the failure this build is arranged to avoid. For the
same reason league-mates' windows get the ledger too (`server.py:23363`).

---

## 4. The client — `mobile/src/screens/TeamReviewScreen.tsx`

Everything renders off the **payload**, never off a flag the client holds (`:389-394`): the client
cannot know whether the backend *applied* a term, so inferring it would let the card and the score
disagree. `check-window-signals.js` claim 5a pins it.

| What | Line | Condition |
|---|---|---|
| `firstsScored` — is the term live | `:391` | `f && f.applied && typeof wFirsts === 'number'` — reads `applied`, never derives it from `net_share === 0`, which is indistinguishable from a genuine net of zero (claim 5b) |
| Ledger card `team-review.window.firsts` | `:454-484` | rendered whenever the backend computed a ledger, **including** when it refused to score it |
| Contribution row in the arithmetic card | `:499-505` | `signed(-(wFirsts) * f.net_share)` — the weight comes off `window.model`, so the card can never show a total it did not itemise. Sabotage **S15** |
| The "we do not read which picks you have traded away" sentence | `:511-527` | now **conditional**. It is true today and becomes a lie the moment the flag is lit, so the scored case gets its own copy. Sabotage **S16** |
| Kicker: "from your playoff odds" vs "inferred from roster shape" | `:407-411` | `w.source === 'odds'` |
| "Roster shape alone said …" | `:414-420` | odds path only — the heuristic's verdict stays on screen |
| Preseason refusal explained | `:421-427` | `odds_reason === 'preseason'` — names the band it saw and why it did not use it |
| "no playoff odds for this league" | `:428-432` | `odds_reason === 'odds_unavailable'` |

**Flag-off render is unchanged.** With both flags down `signals.firsts` and `window.source` are
absent, so `f` is undefined, `fromOdds` is false, every new branch renders `null`, and the beat is
the beat that shipped. The only edited existing string is the "whole model" sentence, whose
flag-off branch is the original text verbatim.

`mobile/src/api/teamReview.ts` keeps all six new fields **optional** (claim 7, sabotage **S18**) —
both flags default off, so they are absent on essentially every payload, and a required field
would make the type lie and invite an undefined read.

---

## 5. Sabotage results — every new guard proven red

Procedure per case: apply one targeted revert → clear `__pycache__` → run → require red **and**
require the *named* test to be the one that failed → `git checkout --` → verify restoration with
`git diff --quiet` (**by content, never by a test result**) → clear `__pycache__` → re-run → require
green. Harness: `scratchpad/sabotage_365_371.py`. 20 of 20 pass.

| # | Behaviour reverted | Guard that caught it | Red | Restored clean | Green again |
|---|---|---|---|---|---|
| S1 | the term applies even with the flag OFF | `test_flag_off_ignores_a_supplied_ledger_entirely` | yes | yes | yes |
| S2 | the term applies with the flag on but NO ledger | `test_flag_on_without_a_ledger_is_still_the_golden` | yes | yes | yes |
| S3 | sign flipped — hoarding firsts reads as contending | `test_selling_firsts_raises_the_score_and_hoarding_lowers_it` | yes | yes | yes |
| S4 | `net_share` clamp removed | `test_net_share_is_clamped_by_the_knob` | yes | yes | yes |
| S5 | an uncaptured pick history scores as a confident zero | `test_a_league_with_no_recorded_trades_is_none_traded_not_a_confident_zero` | yes | yes | yes |
| S6 | an empty roster still reports the term as applied | `test_empty_roster_never_reports_an_applied_term` | yes | yes | yes |
| S7 | `window.model` advertises knobs the score is not using | `test_model_carries_the_new_knobs_whenever_the_term_is_live` | yes | yes | yes |
| S8 | a NULL original owner is read as a trade | `test_ledger_reader_treats_a_null_original_owner_as_never_moved` | yes | yes | yes |
| S9 | the ledger counts every round, not just firsts | `test_ledger_reader_splits_held_owned_traded_and_acquired` | yes | yes | yes |
| S20 | the ledger stops attributing acquisitions | `test_ledger_reader_splits_held_owned_traded_and_acquired` | yes | yes | yes |
| S10 | preseason odds are obeyed instead of refused | `test_preseason_refuses_the_band_but_still_reports_it` | yes | yes | yes |
| S11 | an empty band dict is treated as a real band | `test_no_band_falls_back_and_names_it` | yes | yes | yes |
| S12 | the #371 keys ship even with the flag off | `test_window_is_shape_identical_when_both_flags_are_off` | yes | yes | yes |
| S13 | the heuristic verdict is lost when odds override | `test_window_reports_which_model_drove_and_keeps_the_other_one` | yes | yes | yes |
| S19 | the ledger is computed and then not passed through | `test_window_passes_the_firsts_ledger_through_untouched` | yes | yes | yes |
| S14 | the beat hardcodes an age threshold again | `check-window-signals` 1 | yes | yes | yes |
| S15 | the ledger is shown but its contribution is not | `check-window-signals` 2 | yes | yes | yes |
| S16 | the "we ignore traded picks" line becomes fixed copy | `check-window-signals` 3 | yes | yes | yes |
| S17 | the `none_traded` case stops being distinguished | `check-window-signals` 4 | yes | yes | yes |
| S18 | a flag-gated field is made required in the type | `check-window-signals` 7 | yes | yes | yes |

### 5.1 One guard was vacuous, and the sabotage is what found it

`check-window-signals` claim 2 originally asserted `/w_net_firsts/.test(win)` — that the identifier
appeared anywhere in the `Window` component. It does, unconditionally: the weight is destructured
at `TeamReviewScreen.tsx:390` (`const wFirsts = m?.w_net_firsts`). So **S15 deleted the
contribution row and the check stayed green.** It now requires the *product* — `wFirsts × net_share`
on one line, with the alias discovered from the source rather than assumed — which is the thing that
can only exist if the row exists. This is exactly the failure the batch before this one hit
(a change made an existing test vacuous while it kept passing), and it is why the sabotage table
requires the *named* guard to fail rather than merely requiring a red run.

### 5.2 An existing test that was checked for vacuity and is fine

`test_mock_draft.py::test_w2_07_inference_never_yields_an_extreme_label` reads the **source** of
`infer_team_outlook` and `ast.parse`s it for string constants equal to `championship` / `jets`.
`first_round_signal` was inserted immediately *above* `infer_team_outlook`, so the slice
`src[src.index("def infer_team_outlook"):]` still starts in the right place, and the enlarged
docstring adds no bare `"championship"` literal. Verified green, not assumed.
