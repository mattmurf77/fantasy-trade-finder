# Fairness window — spec

Date: 2026-11-14. Owner: operator. Status: approved to build behind a flag.

## Problem

The trade deck's "fair" setting admits a card only when the smaller side's package value is at
least 0.75 of the larger side's (`FAIRNESS_ON_THRESHOLD` in `mobile/src/api/tradePregen.ts`;
defaults of 0.75 in `backend/trade_service.py` and `backend/server.py`). The Sleeper trade-universe
research (137,002 real dynasty trades; aggregates only) measured how real trades score on the
app's own fairness scale:

| Real trades that would pass | Share |
|---|---|
| 0.75 (today's default), with the app's package math | 41% |
| 0.75, values only (no package math) | 48% |
| 0.50 (the "fairness off" setting) | 77% |
| 1-for-1 player trades at 0.75 | 46% |

Correction (2026-11-14, after the value-blend follow-up): the 41% and 48% rows were measured on a
DynastyProcess-only copy of the app's scale. The app already blends 50% KeepTradeCut; on that basis
42–44% of real trades pass 0.75. The conclusion is unchanged.

So the default window excludes most trades that managers actually agree to. A second result from
the same research: when the generator was replayed offline for real in-season trades at 0.50, a
trade close to the real one was somewhere in the deck for 46–49% of them but in the first 30
cards for only 7–8%.

A caution that shapes the design: the two market sources agree on which side of a trade gave more
only 55% of the time, so "unfair by the board" is often noise in the board, not a bad trade. But
a trade that happened is also not proof it was good for both sides. The aim is to stop hiding
trades people really make, not to fill the first page with lopsided cards.

## Goal

More of the trades managers really make become eligible to appear as cards under the default
setting, **without** making the first page of the deck worse. Whether a wider window achieves
that is an empirical question, and this spec makes the build answer it before anything changes
for users.

## What to build

1. **One source of truth for the default window.** Today the number lives in the app, in two
   backend defaults and in comments. Make the default "fair" threshold a single server-side
   configuration value that the app reads, so it can be changed without a new build. Callers that
   pass an explicit threshold keep working unchanged. Out of scope: `gen_v2`'s own admission
   bars, the pinned-player default (0.50), the "fairness off" setting (0.50), the relaxed
   fallback (0.55) and the divergence floor (0.55), except where the new default must not end up
   tighter or looser than them in a way that breaks their existing ordering.
2. **A flag.** `trade.fairness_window_v2` (match the repo's naming if a convention differs).
   Off: every surface behaves exactly as today (0.75). On: the default is the configured value.
   Default False in `backend/feature_flags.py`, false in `config/features.json` and in the three
   flag fixtures. Do not add it to `FTF_FLAGS`. The operator turns it on.
3. **The replay measurement, in the repo's eval tooling.** An offline command that, for a set of
   real trades with the two rosters as they were, builds the deck at a given default threshold
   and reports: close match to the real trade in the first 30 cards, close match anywhere in the
   deck, exact match in the first 30, share of first-30 cards whose ratio is under 0.75, and deck
   build time. "Close" = same partner and at least half of the combined value is the same assets
   on the same sides. The research already has a working prototype
   (`data/sleeper-universe/analysis/models/scripts/m3_replay.py`, local only, never committed);
   reuse its approach. The committed tool must run on a synthetic fixture in tests and take the
   real dataset only as a path argument.
4. **Choose the number by a rule fixed in advance.** Candidates: 0.75 (today), 0.70, 0.65, 0.60,
   0.55. On the same random sample of at least 500 real in-season trades from the research
   dataset's development folds (never the held-back file):
   - Primary measure: close match in the first 30 cards.
   - Adopt the candidate with the highest primary measure **only if** its gain over 0.75 has a
     95% interval (bootstrap by league lineage) that excludes zero, deck build time is no more
     than 10% slower, and the share of first-30 cards under 0.75 is reported alongside. Ties go
     to the higher (tighter) threshold.
   - If no candidate passes, the configured value stays 0.75, the flag ships off with no
     behaviour change available, and the PR says so plainly. Do not add candidates or change the
     measure after seeing results; anything extra is reported as exploratory.
5. **Copy.** No user-facing copy changes. If any in-app text states "75%" or equivalent, list it
   in the PR rather than changing it.

## Acceptance

- Flag off: byte-for-byte the same decks as `main` for the existing deck fixtures (a test proves
  it), on every surface that takes a default threshold: first deck, prepared/pre-generated
  decks and their cache keys, paged decks, the swap sheet's balanced gate, the consensus note.
- Flag on: the default threshold everywhere is the configured value; explicit thresholds are
  untouched; prepared-deck cache keys cannot serve a deck built at the other threshold.
- The replay table for all five candidates is in the PR and in `docs/plans/fairness-window/`
  (aggregates only: no league, roster, transaction or owner ids).
- New tests are sabotage-checked. Repo feature gates and living-memory write-back are complete.

## Data rules (binding)

`data/sleeper-universe/` is local, git-ignored research data. Read
`data/sleeper-universe/analysis/RULES.md` "Hard limits" and follow them for anything that touches
it: no network, never open `holdout.sqlite`, aggregates only in anything committed, scripts that
read the data stay under `data/sleeper-universe/analysis/fairness-window/`.

## Not in this change

- Changing how values are blended or scaled (a separate research task is testing that now).
- Re-ordering the deck, new card shapes, or per-league windows.
- Turning the flag on.

## Technical design (builder, 2026-11-14, written before coding)

### Where the default is read today

| Surface | Where the 0.75 comes from | Notes |
|---|---|---|
| Mobile deck "Balanced trades" toggle (first deck, Find a Trade, paged decks, presentation deck, page prewarm) | `mobile/src/api/tradePregen.ts` `fairnessThresholdFor(true)` → `FAIRNESS_ON_THRESHOLD` | The app always sends an explicit number (0.75 on, 0.50 off). Unset preference = off (0.50). |
| Prepared / pre-generated decks | `/api/session/init` body `trade_fairness_threshold` (the same helper), stored on the session; `prepared_trade_runtime._fairness` reads it back | Absent ⇒ 0.50 (old clients). |
| `/api/trades/generate` with no `fairness_threshold` | `server.py` `default_fairness = 0.50 if pinned else 0.75` | Web and extension send their own slider value; old/headless callers may omit it. |
| Python signature defaults | `server._kickoff_trade_job(fairness_threshold=0.75)`, `TradeService.generate_trades` / `_generate_for_pair` (0.75) | Every production caller passes an explicit value; these serve scripts. |
| Consensus note ("balanced by consensus value") | `mobile/src/utils/tradePresentation.NORMAL_LOW` (re-exported as `CONSENSUS_BALANCED_MIN`), web `FAIRNESS_BALANCED_MIN` | A truth claim pinned to the definition of "balanced" (cross-client invariant, `check-consensus-balance-claim.js`). |
| Swap sheet "balanced gate" | `SwapPlayerSheet.tsx` comment only; the code is a ±15% value band | No threshold is read at runtime. |
| Calculator / evaluate verdicts | `server.py` evaluate `fairness_threshold` default 0.75, `_consensus_verdict(fairness_threshold=0.75)` | Verdicts about a hand-built trade, not the deck window. |

Below all of these, the engine clamps every request: `trade_gen_owner` uses `floor = max(threshold, market_floor_absolute)` and `trade_policy` refuses any card under `market_floor_absolute`, which is **0.65** (`database.py`, "the one non-negotiable floor"). So on today's configuration the candidates 0.60 and 0.55 build the same deck as 0.65. The measurement still runs all five, as pre-registered. Changing that floor is not part of this change.

### One source of truth

- New module `backend/fairness_window.py`: `FAIR_DEFAULT = 0.75` (today's number, the only literal), `configured_fair_threshold(cfg)` (model_config knob `fairness_window_default`, default 0.75; a missing, non-finite or out-of-range value, meaning anything outside [0.55, 0.75], serves 0.75), and `default_fair_threshold()` (flag off ⇒ `FAIR_DEFAULT`, without reading config; flag on ⇒ the configured value).
- `/api/trades/generate` uses `default_fair_threshold()` for an absent value on an unpinned request. Pinned requests keep 0.50. Explicit values are never rewritten. The Python signature defaults point at `FAIR_DEFAULT`, so they stay byte-identical.
- The range keeps the existing order: on (≥ 0.55) > off (0.50), and `min(requested, relaxed 0.55)` / `min(requested, divergence 0.55)` still give 0.55 for every allowed value.

### How the app receives the configured value

- `GET /api/feature-flags` gets one extra top-level key, `fairness_on_threshold` (a float), **present only while the flag is on**, following the `pass_reason_cadence` pattern. Flag off ⇒ the payload is byte-identical to today.
- Mobile `api/flags.ts` records it on the success path only and never persists it (like `app_min_version`). `fairnessThresholdFor(true)` returns the validated served value, or `FAIRNESS_ON_THRESHOLD` (0.75) when absent or invalid. `FAIRNESS_ON_THRESHOLD` stays 0.75 and stays pinned to `NORMAL_LOW`.
- The consensus note and `NORMAL_LOW` do **not** follow the window: they say "balanced", and a card admitted at 0.68 is not balanced by the app's definition. They stay at 0.75 with the flag in either state (D-266). Web and extension are unchanged: they send the user's slider value (web shows "75%" as the slider's starting value, listed under Copy).

### Prepared-deck cache keys

Every deck cache keys on the numeric threshold that was resolved before the key was built: `_trade_job_is_fresh` / `_trade_running_matches` compare `job["fairness_threshold"]`, `_trade_page_scope` encodes `organic:f=0.NN`, and `prepared_trade_runtime.scope_for` hashes `{"fairness": …}` from the session's stored value. The server-side default is resolved once per request, before keying, and the client sends the number itself. So a deck built at 0.75 can never answer a request for 0.70, and the other way round. Flipping the flag or the knob makes old slots miss, so they are not served. A test pins this.

A mobile cold start that has not fetched flags yet sends 0.75. That only costs a cache miss, never a wrong deck.

### Replay measurement (fixed before any result was seen)

- Committed tool `backend/eval/fairness_window_replay.py`. It takes a JSONL file of cases (each case is one real trade: every team's assets with ids, positions, ages, values and outlooks; the viewer, the partner and the real given/received assets) as a **path argument**. For each case it drives `trade_gen_bilateral_r4.generate_bilateral_trades` offline at every candidate threshold, with sockets blocked and an empty scratch database. A synthetic fixture runs it in tests. The extractor that turns the research dataset into cases stays local (`data/sleeper-universe/analysis/fairness-window/`).
- Sample: research `analysis.sqlite`, split `train`, folds 0–2 (the in-season development route), `season_phase = in_season`, unflagged (`any_flag = 0`), M2 population rule (`rosterlib.eligible`). 600 trades drawn with seed 20261114; every replayed trade counts.
- Deck = the generator's emitted order. First 30 = its first 30 cards. Close = same partner and matched value ÷ union value ≥ 0.5 (the prototype's rule). Exact = same assets both ways.
- Primary: share with a close match in the first 30. Gain over 0.75 is paired per trade; the 95% interval is a percentile bootstrap over whole lineages, 2,000 draws, seed 20261114.
- Build time: median over trades of (candidate seconds ÷ 0.75 seconds) for the same trade, in the same process. Passes if ≤ 1.10.
- Rule: among 0.70, 0.65, 0.60, 0.55, keep those whose gain interval excludes zero on the positive side and that pass the time check. Adopt the one with the highest primary estimate. Equal estimates go to the higher threshold. If none passes, the knob stays 0.75.
- Known limits, carried over from the prototype: approximate pick inventories (generic picks from counts), only 1-for-1 / 1-for-2 / 2-for-1 organic shapes, the r4 generator's order rather than the production-served deck (no ranker, presentment, deck-quality filters or first-page store), consensus boards only (no personal boards).
