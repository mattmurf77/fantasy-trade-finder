# Feature Scope — Composite window model (#372)

**Date:** 2026-08-20
**Entry point:** feedback #372 (operator `mattmurf77`, v1.15.0, screen TeamReview)
**Builder:** agent session on `claude/372-window-composite`
**Operator sign-off on waivers:** not needed — the one waiver (§1c) is the same
one #365 and #371 took on this beat, for the same reason.

> *"The logic is still too simple… age distribution alone is not a strong enough
> of a signal. We calculate starter dynasty value. Let's incorporate that and
> playoff likelihood. The age distribution can stay but make it a lighter driver
> for the evaluation."*

The **third** report on this surface (#365 → #371 → #372). Two of the three
things it asks for are new — starter dynasty value as a signal, and age
down-weighted. The third, playoff likelihood, was already built and dark behind
`trades.window_from_odds`. This build composes all three into **one re-weighted
score** rather than bolting a fourth independent term onto the side of a model
the operator has now told us three times is too simple.

---

## 0. The model

| Term | Legacy weight | Composite weight | Source |
|---|---|---|---|
| `vet_share` (value aged ≥ `vet_age` 27) | **+1.00** | **+0.40** | roster |
| `youth_share` (value aged ≤ `youth_age` 26) | **−1.00** | **−0.40** | roster |
| `pick_share − 1/num_teams` | −2.00 | −2.00 | `draft_picks.pool_value` |
| **`starter_index`** (NEW) | — | **+0.60**, capped ±0.50 | `power_rankings` |
| **`playoff_index`** (NEW) | — | **+0.40**, capped ±1.00 | `backend/outlook/` |
| `firsts.net_share` | −0.10 | −0.10 | own flag, unchanged |
| `contender_cut` / `rebuilder_cut` | ±0.08 | **±0.08 — UNMOVED** | — |

Age's contribution drops by **60 %**, which is the "lighter driver" instruction
made arithmetic. **Both** age terms move together on purpose: `vet_age` 27 and
`youth_age` 26 are *adjacent*, so every aged player is one or the other and the
pair is close to one rescaled quantity — halving only one would tilt the model
rather than lighten it.

`starter_index = (your starters' value / the league's) × num_teams − 1`, i.e.
0.0 is an exactly average starting lineup and +0.30 is 30 % above the league
mean. That is `share − 1/num_teams` rescaled so the number does not depend on
league size, which is why **one** weight is correct at every league shape.

`playoff_index = 2 × (playoff_pct − 0.50)`. The centre is not invented: 0.50 is
the midpoint of the `tossup` band (`outlook.trade_delta.playoff_band`: likely
≥ 0.65, unlikely < 0.35), so the neutral point of the term is the neutral point
of the band map every client already renders. At the `likely` edge the
contribution is `0.40 × 0.30 = 0.12`, which alone clears the 0.08 contender cut
— a genuinely likely playoff team should be called one.

**Nothing new is computed.** Starter value is summed off the `starters` list
and `roster[].value` that `compute_power_rankings` already returns and the Team
Review route already calls; the playoff band is the one `resolve_window_from_odds`
already resolves. `backend/team_review.py`'s module rule — *"this module computes
nothing new, and that is the point"* — survives intact.

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** #372 changes the *value* of
  a field on an existing beat, not the beat set, the step order, or any user
  action. `team_review.beat_view` / `team_review.outlook_set` already fire with
  the same properties and answer the same questions; the window's *inputs* are
  not a user action and there is no funnel step to add. Same waiver #365 and
  #371 took on this surface. The one question a new event could answer — "does
  the composite change how often users override the inferred window?" — is
  answerable today from the existing `outlook_set` payload against
  `window.inferred`, without a new emitter.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. Both signals are derived from data
  already loaded by the route (`league_members`, `draft_picks`, the outlook
  simulator's own payload). `docs/data-dictionary.md` — **n/a, no schema change**.
- **New/changed feature flags:** `trade.outlook_composite`, **default false**.
  Registered in `backend/feature_flags.py` `DEFAULT_FLAGS`, `config/features.json`,
  `docs/config-reference.md`, and mirrored into the three flag fixtures
  (`backend/tests/fixtures/flags/{release,onboarding-v2,profiles-on}.json`) the
  seed-DB guard pins.
  - **Named `trade.*`, not `trades.*`, deliberately** — same call as
    `trade.outlook_net_firsts`. This lives in the ENGINE's classifier, whose
    verdict feeds `outlook_alpha`. `trades.*` is the client surface namespace.
  - **Graduation criterion:** a TestFlight pass on FFV3 confirming the window
    beat reads `contender` with the arithmetic card itemising every term
    (checklist in `testflight-checklist.md`), plus the operator's agreement
    that the composite's *league-mate* windows on the partners beat read
    sensibly. Not graduated by this build.
- **New `model_config` keys:** eight, all namespaced `infer_composite_*` —
  `w_vet` 0.40, `w_youth` 0.40, `w_pick` 2.00, `w_starter` 0.60,
  `starter_cap` 0.50, `w_playoff` 0.40, `playoff_center` 0.50,
  `playoff_cap` 1.00. A **separate namespace** from the five legacy `infer_w_*`
  keys on purpose: the legacy vector is what every engine caller still scores
  with, and reusing its keys would mean the composite could not be tuned
  without moving the engine.
- **Ship-the-knob — the deploy-free rollback lever:** the flag itself, via
  `POST /api/feature-flags/reload` (no redeploy, no client release — the client
  renders off the payload, so flipping the flag down removes both signal blocks
  and the beat reverts to the shape build 122 already parses). Below that,
  `PUT /api/admin/config/infer_composite_w_starter` and
  `…_w_playoff` to `0` degenerate the composite to a down-weighted age model
  while leaving the payload shape and every card intact. Pinned by
  `test_the_knobs_are_a_rollback_lever_below_the_flag`.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-window-composite.js` (14
  assertions, `npm run test:window-composite`) — pins that the composite
  weights are **read** off `window.model` and no composite weight literal
  appears in the beat; that both new contribution rows are itemised off the
  same weight the backend scored with; that the composite is detected from the
  payload (`signals.starters.applied` **and** `model.composite`) and never from
  a client-held flag; that neither term is gated on `index !== 0`; that every
  degraded `provenance` produces copy; that the "that is the whole model"
  sentence stays conditional; and that all eight new type fields are optional
  and `source` admits `'composite'`.
- [x] **Unit tests:** `backend/tests/test_window_composite.py` — **38 tests**.
  Updated: `backend/tests/test_bakeoff_arm_a_golden.py` (`_PINNED_KNOBS` +
  the exclusion rationale) and three flag fixtures.
- [x] **Code-walk proof:** [code-walk.md](code-walk.md) — file:line-cited trace
  of both invariants, the per-signal degradation, the precedence rule, and the
  render path.
- [x] **Manual TestFlight checklist:** [testflight-checklist.md](testflight-checklist.md)
  — eight numbered steps across all four flag combinations. Runtime proof
  genuinely matters here: the composite changes the *verdict* on the screen the
  operator reported three times, and under D-056 this is the only runtime
  evidence mobile gets.
- **`testID`s added:** `team-review.window.starters`,
  `team-review.window.playoff`. Both pass `mobile/scripts/testid-lint.sh`.

### 3.1 Sabotage results

Every new guard was reverted, required to go RED **with the named test in the
failures**, restored via `git checkout --`, proved restored with
`git diff --quiet`, and re-run GREEN. `__pycache__` cleared between every cycle.

| Backend sabotage | RED | named test failed | restored | GREEN |
|---|---|---|---|---|
| S1 composite branch drops the `starter_signal is not None` gate | ✓ | ✓ | ✓ | ✓ |
| S2 `composite` set regardless of `applied` | ✓ | ✓ | ✓ | ✓ |
| S3 flag gate removed entirely | ✓ | ✓ | ✓ | ✓ |
| S4 `model` not re-stated at composite weights | ✓ | ✓ | ✓ | ✓ |
| S5 refused playoff term scored anyway | ✓ | ✓ | ✓ | ✓ |
| S6 starter index uncapped | ✓ | ✓ | ✓ | ✓ |
| S7 precedence rule deleted (band replaces AND scores) | ✓ | ✓ | ✓ | ✓ |
| S8 `_window` stops passing `starters` through | ✓ | ✓ | ✓ | ✓ |
| S9 `starter_value_signal` fakes `observed` on unreadable input | ✓ | ✓ | ✓ | ✓ |
| S10 age weights left at 1.00 inside the composite | ✓ | ✓ | ✓ | ✓ |
| S11 playoff index scale doubled | ✓ | ✓ | ✓ | ✓ |
| S12 starter term gated on `index != 0` instead of `applied` | ✓ | ✓ | ✓ | ✓ |
| S13 `index_raw` capped, so the card prints the model's number not the team's | ✓ | ✓ | ✓ | ✓ |

| Mobile sabotage | RED | named check failed | restored | GREEN |
|---|---|---|---|---|
| M1 starter weight hardcoded as `0.60` | ✓ | ✓ | ✓ | ✓ |
| M2 `composite` derived from `st.applied` alone | ✓ | ✓ | ✓ | ✓ |
| M3 `lineup_unknown` copy branch removed | ✓ | ✓ | ✓ | ✓ |
| M4 `signals.starters` made required in the type | ✓ | ✓ | ✓ | ✓ |
| M5 `'composite'` dropped from the `source` union | ✓ | ✓ | ✓ | ✓ |
| M6 "whole model" sentence made unconditional | ✓ | ✓ | ✓ | ✓ |
| M7 `starterScored` gated on `st.index !== 0` | ✓ | ✓ | ✓ | ✓ |
| M8 playoff contribution row deleted | ✓ | ✓ | ✓ | ✓ |
| M9 starter card switched to the capped `index` | ✓ | ✓ | ✓ | ✓ |

**Two assertions were dead on the first pass and are recorded because finding
them is the point of the exercise:**

1. **S5 did not go red.** `test_a_refused_playoff_term_is_absent_from_the_score_not_a_zero`
   built its refused signal from `playoff_odds_signal`, which *zeroes the index
   on refusal* — so removing the `applied` guard was a numeric no-op and the
   test passed against a broken function. Fixed by handing
   `infer_team_outlook` a refused block with a **loud** `index` of 0.8: only
   the `applied` check can now keep it out. Its starter-side sibling
   (`test_an_unapplied_starter_signal_with_a_LOUD_index_still_scores_nothing`,
   sabotage S12) was added at the same time for the same reason.
2. **M7 did not go red.** Mobile check 4 read
   `/starters[\s\S]{0,80}index\s*[!=]==?\s*0/` — it required the literal word
   "starters" within 80 characters of the comparison, but the real gate is
   written `st.index`, so the sabotage sailed past. Rewritten to match the
   comparison itself anywhere in the beat, plus a positive half (4b) asserting
   both `Scored` flags derive from `applied`.

**And one defect found by re-reading passing code rather than by sabotage.**
The starter card originally printed `index`, which is the **capped** value. The
cap binds on real rosters — the FFV3 caller measures **+0.82** and is scored at
**+0.50** — so the card would have told him his starters were 50 % above the
league mean when they are 82 % above. That is D-101's defect from a new angle:
a screen stating the model's number as if it were the team's. Fixed by shipping
`index_raw` (measured) alongside `index` (scored), rendering the measurement,
and naming the cap only when the two differ. Sabotages S13 and M9 were written
for it.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `GET /api/league/team-review` — `window.signals.starters` / `.playoff`, the composite `window.model` keys, the fourth `provenance` value, `window.source: "composite"` and the precedence rule |
| `living-memory/LLD.md` | n/a | No convention shifted. The *existing* conventions are what this build follows: flag-gated additive payload keys (#365), `provenance`/`applied` degradation (D-110), and "a client reads an encoding, it never restates one" (D-101) |
| `docs/architecture.md` | n/a | No module wiring changed. `team_review.py` remains a pure composer over the same five functions; two pure helpers were added beside `first_round_signal` in the module that already owns the classifier |
| `living-memory/HLD.md` | n/a | No new module, client, or flow |
| `docs/cross-client-invariants.md` | **updated** | New § *Composite window signals — `provenance`, `applied`, and the fourth refusal* |
| `docs/glossary.md` | n/a | "starter value", "playoff band" and "window" are all existing terms; no new domain vocabulary |
| `DECISIONS.md` entry | **added** | D-140 |

## 5. Ship gate declaration

- **CI green on this tree:** `python3 -m pytest backend/tests -q` → **3761
  passed, 1 skipped, 0 failed**; `tsc --noEmit` → clean; all **67**
  `mobile/tests/check-*.js` scripts pass; `mobile/scripts/testid-lint.sh` → OK.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry `2026-08-20f`.
- **TestFlight verification:** checklist written (§3); **not yet run** — this
  branch is committed and deliberately **not pushed and not merged**.
- **Express lane declared by the operator?** No. Full gates.

---

## 6. What this build deliberately did NOT do

- **Did not graduate any flag.** `trade.outlook_composite` ships false, and
  `trade.outlook_net_firsts` / `trades.window_from_odds` are left exactly where
  #365 and #371 left them.
- **Did not move `infer_contender_cut` / `infer_rebuilder_cut`.** The
  distribution below shows the re-weighting does not require it; §7 is the
  evidence, and moving them later would be a headline rather than a footnote.
- **Did not wire the composite into any generation caller.** `trade_gen_v2`,
  the mock draft and the outlook seed still pass four positional arguments and
  therefore still score the legacy vector even with the flag lit (INV-372b).
  Moving decks would need a second, deliberate change with its own evidence.
- **Did not touch `_bin_player` / `analyze_roster_strengths`, `_depth`, or the
  `Depth` / `Plan` components** — a concurrent session owns those.

---

## 7. Calibration — measured on real prod data, read-only

The #365 session drew its conclusion from `data/trade_finder.db`, **which does
not contain FFV3 at all**, and got the direction backwards. So every number
here comes from a read-only `DATABASE_URL_PROD` connection
(`set_session(readonly=True)`), with the league's **real** Sleeper lineup
template fetched from the public meta endpoint. Player metadata and consensus
seed Elo come from the local universal pool, which is a global format-scoped
artifact rather than a per-league one.

### 7.1 The league in the report — `Fantasy Football Version 3` (`1312140920132497408`)

12 teams, `status: pre_draft`, so `completed_weeks == 0` and **the playoff term
is refused** — today the composite runs on starter value, picks and
down-weighted age alone, and the card says so.

| | legacy score | legacy verdict | composite score | composite verdict |
|---|---|---|---|---|
| **`mattmurf77`** | **−0.4867** | **rebuilder** | **+0.2009** | **contender** |

That is the exact defect the report names. What the age model could not see:
his starters are worth **43,615 against a league mean of 23,963** — 82 % above
average, the best starting lineup in the league — while he holds essentially no
pick capital (`pick_share` 0.004 against an even split of 0.083) because he has
sold all three of his own firsts. Every one of those facts says "all in"; the
one signal the legacy model weighted heavily, age, says the opposite because
his roster is young.

The starter cap binds here: his raw index is +0.82, held at +0.50.

Full league, sorted by starter value:

| user | legacy | score | composite | score | moved |
|---|---|---|---|---|---|
| mattmurf77 | rebuilder | −0.4867 | **contender** | +0.2009 | ✔ |
| MangoPatti | contender | +0.2659 | contender | +0.2703 | |
| KevinLake | rebuilder | −0.2615 | not_sure | +0.0026 | ✔ |
| lofman | rebuilder | −0.3008 | not_sure | +0.0123 | ✔ |
| bsharp3 | rebuilder | −0.2508 | not_sure | +0.0313 | ✔ |
| jonbonjourvi | rebuilder | −0.9445 | rebuilder | −0.4232 | |
| gdubs10 | rebuilder | −0.1830 | not_sure | −0.0610 | ✔ |
| Shark357 | rebuilder | −0.0922 | not_sure | −0.0265 | ✔ |
| JohnStanfield | rebuilder | −1.1000 | rebuilder | −0.6015 | |
| dondags20 | contender | +0.2923 | not_sure | −0.0500 | ✔ |
| Bcork | rebuilder | −0.5968 | rebuilder | −0.6059 | |
| PaulSm3nis | **contender** | +0.2295 | **rebuilder** | −0.2464 | ✔ |

The `PaulSm3nis` row is the second sanity check and it runs the other way: the
legacy model calls him a **contender** on age alone while he has the **worst
starting lineup in the league** (3.2 % share against an even 8.3 %) and sits
12th of 12 in total value. An old roster that cannot field a lineup is not
contending, and the composite says so.

### 7.2 The distribution, across 12 prod leagues / 156 teams

Guards against tuning the vector to one league. (Approximation stated: this
sweep uses the app's standard 7-slot offensive template for every league rather
than fetching 12 separate metas — the FFV3 headline above uses the real one.)

| model | rebuilder | not_sure | contender |
|---|---|---|---|
| legacy | **101 (65 %)** | 26 | 29 |
| composite | 62 (40 %) | 40 | 54 |

**The legacy vector calls two thirds of every team in production a rebuilder,
and produces almost no `not_sure` verdicts at all.** That systematic skew is
what #365, #371 and #372 have each reported from a different angle. The
composite's spread is the finding that justifies leaving the cuts alone: a
model that needed the cuts moved would show up here as a distribution still
pinned to one label, and this one does not.

Transitions: `rebuilder→rebuilder` 50, `rebuilder→contender` 29,
`rebuilder→not_sure` 22, `contender→contender` 17, `not_sure→not_sure` 10,
`not_sure→contender` 8, `not_sure→rebuilder` 8, `contender→not_sure` 8,
`contender→rebuilder` 4. The model disagrees with itself in both directions,
which is what a re-weighting should look like and not what a thumb on the scale
would.

---

## 8. Contradictions found against the brief / existing docs

1. **`config/features.json`'s `_comment_outlook_net_firsts` says `mattmurf77`
   is "net +3" in FFV3. Prod says net −3.** He owns 3 of his own firsts,
   traded away 3, acquired 0 → `acquired − traded_away = −3`. The *direction*
   in that comment is right (a seller reads as contending, because the score
   *subtracts* `w × net_share`) and the code is correct; only the prose sign is
   wrong. Left as-is rather than edited — it is #365's artifact, not this
   build's, and a silent edit to another item's evidence comment is worse than
   a note. Worth a follow-up.
2. **`docs/api-reference.md` carries the `GET /api/league/team-review` row
   twice** (lines 481 and 482), a merge artifact: one copy has the #365/#371
   window content, the other has the #366 depth content, and neither has the
   other's. #372's addition went onto the window copy. A concurrent session
   owns the depth half, so this was not reconciled here.
