# Win-now season signal — checks on real recorded requests (2026-11-15/16)

> **Status (2026-11-16): measured, nothing changed.** Bilateral revision 5 stays off
> (`owner_bilateral_revision_5_enabled` 0; revision 2 serves). No code, flag or knob moved.
> Three local, offline measurements on the operator's own recorded requests. The sample is too
> small for the launch bars ([validation §3.4](validation.md)), so this is an early read, not a verdict.

Aggregates only: no league, user, run or member ids and no manager or league names. Leagues are
"League 1" and "League 2". NFL player names appear where they explain a result.

## Sample

- Source: the operator's own owner requests recorded in production since the founder labels were
  set (2026-11-12), read-only, in two of the operator's leagues. 14 requests with usable season
  evidence: 13 in League 2 (one viewer, nearly the same roster, saved outlook All-in) and 1 in
  League 1 (saved outlook Tanking). **2 manager-league pairs.** All organic (no pins, no partner scope).
- 10 of the 14 were recorded with the 41 founder label overrides attached; the other 4 predate them.
- Production held 20 recorded requests with a season-evidence record across 5 account-league pairs
  at the time (2026-11-16), most of them the operator's. The launch bars need at least 40 requests
  and 5 pairs with usable evidence for All-in / Contending viewers.
- Every replay ran in one process per run with sockets blocked, an in-memory SQLite database,
  `PYTHONHASHSEED=0`, production's `model_config` values and the shipped `config/features.json`.
  Served decks are `season_replay`'s stand-in: generator, significance, presentment, deck-quality
  filter. Not replayed: database-backed stages (decline windows, dispositions, likes-you), the
  first-page store, anything the client does. Partner matching stayed off, as in production.

## 1. Do the 41 founder label overrides change revision 5's decks?

Arms per request: revision 2; revision 5 with the overrides removed from the evidence ("off");
revision 5 with the 41 overrides ("on"). Each request was run under all five outlooks (70 cases,
not independent). The rebuilt "on" evidence matched the recorded evidence, digest included, on
10 of 10 requests recorded with overrides. Revision 5 "on" generated twice gave identical served
decks on 15 of 15 cases; an independent re-run of two requests in a fresh process reproduced all
10 of their cases exactly.

**Reach.** All 41 overrides attach in both leagues (`with_label_overrides` counts every projected
player, free agents included). 32 change a label in League 1 and 38–41 in League 2; the rest
already matched the engine. Largest group: cornerstone → win_now (13 in League 1, 15 in League 2,
mostly WR and TE). No label changed without an override.

**Deck change, "on" against "off", first 30 served cards.**

| League / outlook | cases | first 30 differ | mean shared of 30 | top card changed | full deck: same set of cards |
|---|---|---|---|---|---|
| L2 All-in | 13 | 13 | 27.4 | 1 | 0 (3.5 in / 0.7 out on average) |
| L2 Contending | 13 | 13 | 29.2 | 6 | 0 |
| L2 Not sure | 13 | 0 | 30 | 0 | 13 |
| L2 Rebuilding | 13 | 13 | 29.5 | 6 | 13 (order only) |
| L2 Tanking | 13 | 9 | 29.4 | 0 | 13 (order only) |
| L1 All-in | 1 | 1 | 30 | 1 | 0 |
| L1 Contending | 1 | 1 | 29 | 0 | 0 |
| L1 Not sure | 1 | 0 | 30 | 0 | 1 |
| L1 Rebuilding | 1 | 1 | 22 | 0 | 1 (order only) |
| L1 Tanking | 1 | 1 | 28 | 0 | 1 (order only) |

No card present in both decks changed its terms. For scale, revision 2 against revision 5 shares
only 8–23 of the first 30.

**Direction.** L2 All-in: win_now-corrected players received per card .274 → .313 (up in 7 cases,
down in 1); points a week in the first 30 1.33 → 1.63. L1 Rebuilding and Tanking: fewer
win_now-corrected players received (.133 → .033, .067 → 0) and, for Rebuilding, more
rebuild/cornerstone-corrected (.40 → .50). Wrong way, both small: L1 Contending (.167 → .133) and
one L2 Tanking case. Lineup points held or improved in every outlook apart from changes under 0.01
a week.

**Not testable here.** Neither viewer owns a player relabelled to win_now, so "a selling team
sends away more win_now pieces" is unmeasured. An exploratory re-rooting of League 2 onto six
league-mates with recorded boards (their roster, board and preferences substituted; history, pins
and exclusions emptied) showed the same small effect and leaned slightly the wrong way on that
question (.217 → .206 and .222 → .217 per card).

**Why All-in barely moves.** An All-in or Contending viewer reads a label only through
`_season_lean`: a projected player who starts for the viewer gets .40 for win_now or cornerstone
and .25 otherwise. So the largest correction group, cornerstone → win_now, has no effect for
these viewers.

## 2. Would one rule change replace the overrides?

Latest request with overrides in each league. A parameterised copy of the label rule reproduced
the engine's no-override label for every rostered QB/RB/WR/TE (271 of 271 and 281 of 281) before
any candidate was scored. 39 of the 41 overrides still differ from the engine in at least one
league ("live"). The review page lists every rostered player of the selected league and clears an
override that matches the engine, and all 41 differed from the engine in League 2 at the time of
the save, so League 2's uncorrected players are treated as left alone on purpose (inferred, not
recorded).

| Rule (best setting of each) | live corrections reproduced in every league (in any), of 39 | uncorrected players relabelled |
|---|---|---|
| Engine today | 0 | 0 |
| `FUTURE_FLOOR` 2000 | 3 (10) | 4 |
| `RATE` 600 | 3 (14) | 7 |
| **Cornerstone only up to `_YOUNG` + 1 (QB 28, RB 25, WR 26, TE 26)** | **7 (8)** | **2** |
| Cornerstone requires `young` | 10 (11) | 7 |
| Unlabelled young player worth the filler floor → rebuild | 3 (5) | 11 |
| Non-starter above a value → win_now | 0 | net loss at every value |
| Best pair (`FUTURE_FLOOR` 2000 + age gate) | 9 (14) | 5 |

**Verdict: no simple rule does most of the work; the overrides stay.** The age gate is the only
candidate with a positive balance, it works at that one cut-off only (pooled net 11 at +1, 8 at 0,
2 at +2), and WRs supply nearly all of its hits. It would relabel CeeDee Lamb (both leagues) and
DK Metcalf (League 1), whom the operator left as cornerstones. Amon-Ra St. Brown (moved to win_now)
and CeeDee Lamb (left alone) are both WR 27 with the same market value and near-identical
projections, so any rule on these inputs gets one of them wrong. Fitting on one league and scoring
on the other picks the same setting both ways, which is weak confirmation because the leagues share
the players and the reviewer.

About 31 corrections stay hand calls: young starters called rebuild (the engine says cornerstone
because they start); players with no projection, who get no engine label at all (a data gap, not a
rule setting); cheap veterans called win_now, who look like about 100 depth players left alone;
young WR/TE cornerstones moved to win_now with untouched peers of the same age and value.

Also seen: 28 of 280 League 2 engine labels changed between the review-time snapshot and the latest
request, and 2 of the 41 overrides now agree with the engine in both leagues.

## 3. The launch bars on real requests

`PYTHONHASHSEED=0 python -m backend.eval.season_replay --dir <the 14 requests>`, exit status 1.
13 bars pass, 3 fail, 4 have too little data, 2 do not apply.

| Bar ([validation](validation.md)) | Result |
|---|---|
| §3.4 Sample: ≥ 40 requests, ≥ 5 pairs | **Insufficient**: 13 All-in requests, 1 pair |
| §3.4 All-in lineup points: median +1.0 a week over revision 2, higher on ≥ 80% | Pass: median 2.31, higher on 13 of 13 |
| §3.4 All-in adds a starter: up ≥ 15 points | Pass: +0.15 |
| §3.4 All-in costs points: no higher than revision 2 on ≥ 90% | Pass: 13 of 13 |
| §3.4 Contending | Insufficient: no request |
| §3.4 Outlook flip: All-in ≥ Contending > Not sure on ≥ 80% | **Fail**: 0.29 (revision 2 also 0.29) |
| §3.4 Label table within 0.3 a week of the numbers (arm 2 against arm 4) | **Fail**: median −0.55; the plan's fallback on a miss is to read the number |
| §3.4 Rebuilding / Tanking lineup points lower than revision 2 | Pass: Tanking −1.87 (n = 1) |
| §3.4 Tanking falls more than Rebuilding | Insufficient: no Rebuilding request |
| §3.4 Need-term clipping not above half | Pass: 78 of 1,207 |
| §6 Deck size ≥ 95% of revision 2 at the median | **Fail**: 0.775 (All-in 96 → 75 served cards on average) |
| §6 Fairness floor, Not sure identical, same cards for Rebuilding / Tanking, no forecast identical, push-down removes nothing | Pass (all five) |
| §6 Speed within 10% | Pass: 1.084 |
| §6 Pinned and partner-scoped searches | n/a: none recorded |
| §7 Stage 2 buying and selling bars | Pass (n = 13 and n = 1) |
| §7 Stage 2 Not sure within 2% | Insufficient |

The label-table failure bears on the overrides: if plan fit read the continuous number, as the
plan says it should on a miss, labels (and the 41 overrides) would stop affecting All-in and
Contending decks.

## Limits

- Two rosters, one of them repeated 13 times. Only All-in (League 2) and Tanking (League 1) were
  saved outlooks; every other outlook is counterfactual.
- Offline stand-in for the served deck (see Sample). Consensus and personal boards are as recorded.
- The page the overrides were saved from is inferred from the data.

## Re-running

The scripts and outputs are local and git-ignored (`data/review/label-check/`: `label_effect.py`,
`rule-test/rule_test.py`, private results, `launch-checks.log`), and the request pull is under
`data/prod-requests/` (never committed). Re-run the launch bars once production has recorded at
least 40 requests with usable evidence across 5 or more manager-league pairs.
