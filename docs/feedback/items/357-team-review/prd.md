# PRD — Team Review

**Date:** 2026-08-19 · **Items:** #357 / #358 / #359 · **Flag:** `trades.team_review` (ships dark)
**Design lab:** [`mockups/team-review-2026-08-19/`](../../../../mockups/team-review-2026-08-19/index.html)
**Contracts:** [`lld-delta.md`](lld-delta.md) · **Architecture:** [`hld-delta.md`](hld-delta.md) · **Gates:** [`scope.md`](scope.md)

---

## Table of contents

- [1. Problem](#1-problem)
- [2. What we are building](#2-what-we-are-building)
- [3. Requirements](#3-requirements)
- [4. Copy rules](#4-copy-rules)
- [5. Out of scope](#5-out-of-scope)
- [6. Guardrails and budgets](#6-guardrails-and-budgets)
- [7. Test plan](#7-test-plan)
- [8. Success criteria](#8-success-criteria)

---

## 1. Problem

A tester who has linked a league, ranked some players and opened the deck still
does not know **what he is trying to do**. In his words (#359): *"basically an
idiot version of wtf do I do next with this team."* The app has every ingredient
of an answer — roster value, league rank, positional depth, an inferred
contend/rebuild window, board-vs-market divergence, every league-mate's roster —
and it surfaces none of them as a read. It jumps straight to individual trade
cards, which is the last step of a reasoning process the user was never walked
through.

The same tester (#358) described the missing thing precisely: an AI GM that says
where you stand, what strategy that implies, and which specific moves execute it.

---

## 2. What we are building

**Team Review**: a six-beat guided read of the user's own team, entered from a
card at the top of `TradesHome`. Each beat states one finding, explains it in
ordinary words, and offers one action. Four of the six actions write
`league_preferences` — the fields the trade engine already reads — so the flow's
exit is a deck reshaped by what the user just agreed to.

| # | Beat id | Finding | Action |
|---|---|---|---|
| 1 | `standing` | Roster value rank + positional split; PPG rank in-season | none (orientation) |
| 2 | `window` | Inferred contend/rebuild window + the three signals behind it | set `team_outlook` |
| 3 | `depth` | Startable bodies per position; weakest starting slot | set `acquire_positions` / `trade_away_positions` |
| 4 | `divergence` | Where your board disagrees with the market | pin an asset |
| 5 | `partners` | Who is pointed the other way; who is deep where you are thin | scope the deck to a member |
| 6 | `plan` | Recap of what was set | "Find my trades" |

It ships **odds-free** and adds **no new modeling**. Every figure is already
computed somewhere in the app under the same definition.

---

## 3. Requirements

Numbered so QA can map each to a mechanical check (§7.5).

### Entry and navigation

- **R-1** — With `trades.team_review` ON, `TradesHome` renders a Team Review
  entry card above the deck. Dismissing it **collapses it to a one-line row**
  (per league, persisted) — it never disappears entirely, per the D-025
  collapsed-strip precedent. With the flag OFF, no card renders and the route is
  not registered.
- **R-2** — The entry card is **not** added to `TradeFinderModeBar`'s chip array.
  (Rationale: the strip already measures ≈402pt against ≈361pt usable —
  `TradeFinderModeBar.tsx:50–58`. An appended chip is invisible.)
- **R-3** — A second entry exists on the deck's empty/exhausted state and is not
  dismissible.
- **R-4** — `TeamReviewScreen` is registered in `TradesStackNav` only, uses
  `subScreenOptions('Team review', 'TradesHome')` for its back control, and
  mounts **no** `FeedbackFAB` of its own.

### The read

- **R-5** — Beat `standing` shows the user's roster-value rank out of the league
  and a four-position value split with a per-position league rank. Works on every
  platform, in every week.
- **R-6** — Beat `standing` shows a PPG rank **only** when real weekly scores
  exist. Otherwise it renders a card naming the actual reason — `preseason` or
  `platform_unsupported` — never an empty state, a spinner, or a zero.
- **R-7** — Beat `window` shows the inferred window (`contender` | `rebuilder` |
  `not_sure` only) together with the three signals that produced it: veteran
  value share, youth value share, and pick capital against an even split. The
  screen labels it **inferred from roster shape**.
- **R-8** — Beat `depth` shows startable counts per position from `tier_depth`
  and, when a lineup template exists, names the weakest starting slot with its
  tier and positional rank.
- **R-9** — Beat `divergence` shows up to five players the user rates above the
  market and up to five below, with the correct reading attached: **above the
  market = your easiest sell**, below = do not buy. It uses the league-community
  comparison when ≥3 other members have ranked, otherwise the universal
  consensus seed, and states which comparison it used.
- **R-10** — Beat `partners` shows up to three league-mates whose inferred window
  opposes the user's, with their value rank and pick capital, and up to three who
  are deep where the user is thin. Members inferred `not_sure` never appear in
  the opposed list.
- **R-11** — Beat `plan` recaps only what the user actually set in this session
  and states that any of it can be changed later in Trade DNA.

### The writes

- **R-12** — Beat `window`'s confirm writes `team_outlook` via the existing
  `POST /api/league/preferences`. No new write route exists.
- **R-13** — Beat `depth`'s save writes `acquire_positions` and
  `trade_away_positions` via the same route.
- **R-14** — Beat `divergence`'s pin and beat `partners`' scope use the existing
  finder-pin and `opponent_user_id` paths unchanged.
- **R-15** — Every write is skippable. No beat blocks progress, and `not_sure` is
  a first-class option on beat `window`.
- **R-16** — Beat `plan`'s "Find my trades" returns to `TradesHome` with the deck
  regenerated against the preferences just written, using the **existing** #330
  handoff store (`useFinderTargets.setHandoff({opponent, autoRun: true})`,
  one-shot and focus-gated). No new hand-off mechanism is built.
- **R-17** — A failed write surfaces inline on its beat, does not abort the flow,
  and emits **no** `team_review_action_taken` row.

### Honesty

> **Rewritten 2026-08-19** after the operator lit `outlook.odds`
> ([D-094](../../../../living-memory/DECISIONS.md)). R-18 originally required the
> payload to carry *no* odds at all; it now requires the narrower and permanent
> half of that rule.

- **R-18** — The payload contains no `title_pct` and no `bye_pct`, at any week,
  in any form. These are not merely unshown — they are **not serialized**.
- **R-18a** — Beat `standing` shows a playoff **band chip** (`likely` /
  `tossup` / `unlikely`) when and only when `outlook.odds` is on, the league is
  Sleeper, and the outlook call succeeded. It never displays
  `playoff_pct` as a number. The raw fraction is served for the VoiceOver label
  only.
- **R-18b** — The chip carries the "Projected" ribbon, extended to
  "Projected · preseason · beta" while `meta.beta` is true. While `beta` is
  true no win-loss number or projected record appears anywhere on the beat.
- **R-18c** — With `outlook.odds` **off**, on a non-Sleeper league, or when the
  outlook call fails, `standing.outlook` is **absent** and every other part of
  the review is byte-identical. An odds failure never costs the user their value
  rank.
- **R-18d** — When `priced_slot_coverage.affects_strength` is true and
  `fraction < 1` (IDP/kicker leagues), the chip carries the coverage caption.
  Team Review is this field's **first consumer in any client**.
- **R-19** — No figure on any beat is a forward projection of **player or team
  points**. Every number is a measured value, a computed value-derived rank, a
  labelled inference, or the playoff band — which is a projection and is
  labelled as one.
- **R-20** — Every inferred figure carries the word *inferred* adjacent to it,
  and every projected figure carries *Projected*.

### Instrumentation

- **R-21** — The four new events fire per [`scope.md` §1](scope.md), with exactly
  one `team_review_exited` per `team_review_opened`.
- **R-22** — Beat `window`'s write also emits `outlook_saved` with
  `source: "review"`; beat `divergence`'s pin also emits
  `finder_target_pinned` with `source: "review"`.
- **R-23** — `team_review_beat_viewed` and `team_review_exited` are in
  `NON_INTENT_EVENTS` in the same commit that registers them.

### Degradation

- **R-24** — On a non-Sleeper league the review renders in full with one degraded
  card. It never returns 501 and never raises `NotImplementedError`.
- **R-25** — When the caller's board has not met the ranking service's own
  confidence bar (`RankSet.threshold_met` false for `position=None`, i.e. fewer
  than 16 overall interactions), beat `divergence` is server-marked skipped and
  the client does not render it; the `plan` beat offers ranking as a follow-up.
- **R-25a** — Beat `divergence` only ever lists players the user has actually
  compared (`wins + losses > 0`). An un-judged player's board Elo *is* the
  consensus seed, so his gap is structurally zero and he carries no opinion —
  see the trap in [`lld-delta.md` §3](lld-delta.md).
- **R-26** — When the league has fewer than two other members, beat `partners` is
  server-marked skipped.
- **R-27** — The client renders exactly `meta.beats` minus `meta.beats_skipped`,
  in `meta.beats` order, and never decides for itself that a beat is empty.

---

## 4. Copy rules

#359's phrasing is the acceptance test: *an idiot version of wtf do I do next*.
That is a compliment to aim at, not a joke.

1. **Plain words, no jargon in the headline.** "You're built to win now — but
   you're not built deep" is the read. "vet value share 0.61" is the evidence,
   and it goes underneath in smaller type.
2. **One idea per bubble.** Inherited from
   `docs/plans/onboarding-conversion/guided-avatar-script.md`.
3. **State the consequence, not the statistic.** "You're 11th of 12 at TE" is a
   number. "Your TE slot is a tier below every other slot you start" is a read.
4. **Never instruct where the data only supports a suggestion.** "We recommend a
   1 year tank" becomes "This reads *rebuilder*. Is that right?" — the user owns
   the call, and the app is asking so it can configure itself.
5. **Name absences honestly.** "No games played yet — 2026 hasn't started"
   beats a blank card, and beats a zero.
6. **No emoji.** Chalkline rule, and the notifications de-emoji pass already set
   the precedent.

---

## 5. Out of scope

Explicitly, so build agents do not drift:

- **Any forward points projection**, per-player or per-team. Cut with reasons in
  [`scope.md` §6](scope.md) waiver 1.
- **Championship odds, in any form.** Unrenderable by invariant; see
  [`scope.md` §6](scope.md) waiver 2.
- **A bare playoff percentage.** `OUTLOOK_WEEK6_PERCENT_ENABLED` stays `false`.
  Lighting `outlook.odds` (done, D-094) is not lighting the percentage — that is
  a separate operator risk call on pooled, non-week-stratified calibration.
- **Championship odds.** `title_pct` is unrenderable at any week on an absence of
  demonstrated skill. Not waivable.
- **Any trade-engine change.** No generation path, gate, score or knob moves.
- **A web or extension port.** Mobile only at v1.
- **Persisting the review itself** (history, "what changed since last time").
  Tempting and cheap-looking; it needs a table and a retention answer, so it is a
  follow-up, not a v1.
- **Re-capturing `screens/`.** Impossible under D-056.

---

## 6. Guardrails and budgets

| Guardrail | Bar |
|---|---|
| Latency, `GET /api/league/team-review`, p95 | ≤ 800 ms on a 12-team league. If it exceeds this, the fix is caching the power-rankings half, **not** splitting into per-beat fetches (which reintroduces six loading states). |
| Added external calls | **Zero** when `scoring_available` is false. In-season, the Sleeper weekly fan-out reuses the existing `_outlook_sleeper_fetch` cache (completed weeks cached with no TTL). |
| New DB writes | Zero beyond the existing preferences route. |
| New tunables | Zero. Every threshold displayed is owned by the module that already owns it. |
| Rollback | `trades.team_review` → `false`, hot-reloaded via `POST /api/feature-flags/reload`. No deploy, no client release. |

---

## 7. Test plan

Per D-056: structural checks + unit tests + a written code-walk proof + a manual
TestFlight checklist. No Maestro, no simulator, no captures.

### 7.1 Structural — `mobile/tests/check-team-review.js`

Dependency-free, runs under plain node, wired into `npm run test:team-review`
**and** into the `mobile-typecheck` CI job's script list. Five assertions, as
enumerated in [`scope.md` §3](scope.md).

### 7.2 Backend unit — `backend/tests/test_team_review.py`

| Test | Asserts |
|---|---|
| `test_flag_off_404` | Route 404s with `trades.team_review` false, before any session work |
| `test_payload_shape` | Every field in [`lld-delta.md` §2](lld-delta.md) present with the right type; `meta.beats` is the six ids in order |
| `test_preseason_scoring_null` | `completed_weeks == 0` → `scoring: null`, `reason: "preseason"` |
| `test_non_sleeper_degrades` | `platform="espn"` → 200, `reason: "platform_unsupported"`, and `build_league_state` is **not called** |
| `test_divergence_source_ladder` | `league_community` at ≥3 rankers → `consensus_seed` below that → beat skipped when `threshold_met` is false |
| `test_divergence_judged_only` | A player with `wins+losses == 0` never appears in either divergence list, even though he is present in `user_elo` |
| `test_partners_excludes_not_sure` | A member inferred `not_sure` never appears in `opposed_window` |
| `test_no_title_pct` | `"title_pct"` and `"bye_pct"` absent from `json.dumps(payload)` at every week |
| `test_band_present_when_lit` | Flag on + Sleeper → `standing.outlook.band` ∈ {likely,tossup,unlikely}; `playoff_pct` present as a raw fraction |
| `test_band_absent_when_dark` | `outlook.odds` off → `standing.outlook` **absent**, and the other five beats byte-identical to the lit payload minus that key |
| `test_odds_failure_never_breaks_beat` | `run_outlook` raising → 200, `standing.outlook` absent, `value_rank` still present |
| `test_band_thresholds_server_side` | 0.65 → `likely`, 0.6499 → `tossup`, 0.35 → `tossup`, 0.3499 → `unlikely` (boundaries belong to the higher band) |
| `test_personal_basis_read_gate` | Unverified session → the `_verified_read_denial` body |
| `test_redraft_501` | `basis=redraft` → 501 with the power-rankings message shape |

Plus extensions to `backend/tests/test_analytics_taxonomy.py` per
[`scope.md` §3](scope.md).

### 7.3 Sabotage proof (required before any test counts)

The 2026-08-10 lesson: a test that has never failed proves nothing. Each of these
sabotages must be shown to turn the named test red:

| Sabotage | Must fail |
|---|---|
| Serialize `title_pct` from the composer | `test_no_title_pct` |
| Drop the `is_enabled("outlook.odds")` guard so the block is always built | `test_band_absent_when_dark` |
| Let a `run_outlook` exception propagate | `test_odds_failure_never_breaks_beat` |
| Flip the server-side band comparison `>=` to `>` | `test_band_thresholds_server_side` |
| Drop the `platform != "sleeper"` short-circuit so `build_league_state` runs | `test_non_sleeper_degrades` |
| Lower `_MIN_BASELINE_USERS` handling so `consensus_seed` is never chosen | `test_divergence_source_ladder` |
| Skip on `len(user_elo) < 16` instead of `threshold_met` | `test_divergence_source_ladder` (the skip never fires — `_pool` is unfiltered) |
| Drop the `wins+losses > 0` filter | `test_divergence_judged_only` |
| Include `not_sure` members in `opposed_window` | `test_partners_excludes_not_sure` |
| Mount a `FeedbackFAB` in `TeamReviewScreen` | `check-team-review.js` #2 |
| Append a `review` chip to `TradeFinderModeBar.CHIPS` | `check-team-review.js` #5 |
| Register `TeamReview` in `RootNav` as well | `check-team-review.js` #1 |

### 7.4 Manual TestFlight checklist (operator)

The only runtime evidence mobile gets. Run on a build with
`trades.team_review` ON.

**A — Entry (Sleeper league, preseason)**
1. Open the Acquire tab. → A "Team review" card sits above the deck, with the Analyst avatar and a "Start team review" button.
2. Confirm the mode chip strip is **unchanged** — Draft, Guided, Team, Player, Calc, Free agents. No seventh chip.
3. Tap the card's dismiss control. → It collapses to a one-line row; it does **not** vanish. Background and relaunch, return to Acquire. → Still collapsed. Switch to a second league. → Expanded there.

**B — The six beats**
4. From the collapsed state, tap the one-line row. → The review opens. Then exhaust the deck (pass every card). → A Team Review entry is offered on the empty state too.
5. Start the review. → Beat 1 of 6, "Where you stand", shows your roster-value rank out of the league and a four-position split.
6. On beat 1, confirm the PPG card reads *"No games played yet — 2026 hasn't started."* — **not** a zero, a spinner, or a blank.
7. Advance to beat 2. → An inferred window (Contender / Rebuilder / Not sure) with three signal rows beneath it, labelled "inferred from roster shape".
8. Select a *different* window than the inferred one and confirm. → Advances to beat 3.
9. Advance through beats 3–5, setting a chase position, a shop position, and scoping to one league-mate.
10. On beat 6, confirm the recap lists exactly what you set in steps 8–9 and nothing you skipped.

**C — The writes actually stick**
11. Force-quit the app. Relaunch. Open Trade DNA for the same league. → The outlook and the chase/shop positions match what you set in step 8–9.
12. Return to Acquire and pull a fresh deck. → The deck reflects the new window (a rebuilder window should surface pick-acquiring cards it did not before).

**D — Degradation**
13. Switch to an **ESPN or MFL** league and run the review. → It completes all six beats; only the PPG card differs, reading *"Not available for ESPN leagues yet…"*. Nothing 501s and nothing spins forever.
14. On an account that has made fewer than 16 ranking comparisons, run the review. → Beat count is 5, not 6; "your board vs the market" does not appear; beat `plan` offers ranking.
14a. On an account just past that bar, run the review. → Every player listed on beat `divergence` is one you actually compared — no untouched player appears with a near-zero gap.

**E — Navigation and back**
15. Mid-flow (beat 3), tap the header back control. → Returns to `TradesHome`, not to a blank screen or a dead native back.
16. Re-enter the review. → It starts at beat 1 against fresh data (it does not resume mid-flow).
17. Confirm there is exactly **one** feedback button visible on the review screen.

**F — Honesty sweep**
18. Read every screen of the flow. → The only odds figure anywhere is the **band chip** (Likely / Toss-up / Unlikely) with a "Projected · preseason · beta" ribbon. **No bare percentage** of any kind. **No championship or title odds** in any form. No "+N PPG" claim anywhere.
19. Open League Summary for the same league. → The collapsed one-line "your outlook" strip is present (this is `outlook.odds` newly lit); expand it. → Bands and row order only, no win-loss numbers, ribbon attached. Confirm no championship-odds row exists.
20. Switch to an ESPN or MFL league and open League Summary. → **No outlook section at all** — not an error, not a spinner, not a 501 message.

### 7.5 Requirement → check mapping

| R | Verified by |
|---|---|
| R-1, R-4 | `check-team-review.js` #1/#2, TestFlight A1, E17 |
| R-2 | `check-team-review.js` #5, TestFlight A2 |
| R-3 | TestFlight B4 |
| R-5, R-6 | `test_payload_shape`, `test_preseason_scoring_null`, TestFlight B5/B6 |
| R-7 | `test_payload_shape`, TestFlight B7 |
| R-8 | `test_payload_shape` (`weakest_slot` nullable branch) |
| R-9 | `test_divergence_source_ladder`, TestFlight D14 |
| R-10 | `test_partners_excludes_not_sure` |
| R-11 | TestFlight B10 |
| R-12…R-14 | Code-walk proof (the preferences→generation chain), TestFlight C11/C12 |
| R-15 | TestFlight B7 (`not_sure` selectable), B10 (skipped items absent from recap) |
| R-16 | TestFlight C12 |
| R-17 | Code-walk proof |
| R-18 | `test_no_title_pct`, `check-outlook-bands.js` #4 |
| R-18a, R-18b | `test_band_present_when_lit`, `test_band_thresholds_server_side`, `check-outlook-bands.js` #1/#2/#3/#5, TestFlight F18 |
| R-18c | `test_band_absent_when_dark`, `test_odds_failure_never_breaks_beat`, TestFlight D13 |
| R-18d | `test_payload_shape` (coverage branch) |
| R-19, R-20 | TestFlight F18 |
| R-21…R-23 | `test_analytics_taxonomy.py` extensions |
| R-24 | `test_non_sleeper_degrades`, TestFlight D13 |
| R-25, R-25a | `test_divergence_source_ladder`, `test_divergence_judged_only`, TestFlight D14 |
| R-26, R-27 | `test_payload_shape` (`beats_skipped`), TestFlight D14 |

### 7.6 Web

**n/a** — mobile only at v1. No web test section.

### 7.7 Captures named as PRD inputs

Per `mockups/CLAUDE.md`, the ground truth for "current":
`screens/mobile/trades/populated.png`, `screens/mobile/trades/empty.png`,
`screens/mobile/league-summary/populated.png` — all captured 2026-08-10/11,
manifest sha `106c8e38…`. **`TradesScreen.tsx` has moved 11 times since**, and
D-056 makes re-capture impossible; the design lab labels every reconstructed
frame accordingly. **Capture delta at ship: none, and none is possible.**

---

## 8. Success criteria

| # | Criterion | Measured by |
|---|---|---|
| S-1 | The review completes without a dead end on every live platform and in preseason | TestFlight D13/D14 |
| S-2 | ≥50% of users who open the review reach beat `plan` | `team_review_exited.outcome = completed` / `team_review_opened` |
| S-3 | ≥60% of completing users take ≥1 action | `team_review_action_taken` distinct sessions / completions |
| S-4 | The review becomes a real source of declared outlooks | `outlook_saved` with `source: "review"` as a share of all `outlook_saved` |
| S-5 | No honesty regression | `test_no_odds_fields` green; TestFlight F18 clean; `outlook.odds` still `false` |
| S-6 | Jon's own read | The three items are re-shown to `jonbonjourvi` on TestFlight and he can say what his team should do next |

S-2 and S-3 are **read-only bars for the first two weeks lit** — they inform
placement, not a rollback. The rollback trigger is S-1 or S-5 failing.
