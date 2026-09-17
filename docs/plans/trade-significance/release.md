# Production release — 2026-09-17

- Owner authorized push, activation, and a fresh 100-trade HTML review (50 per league).
- [PR #297](https://github.com/mattmurf77/fantasy-trade-finder/pull/297), tested head `c280369a50fe88ba433cd6d8e0028ced367346d3`, squash merge `b33b4da951066e8139e05adb9fda3bbc3d981ebc`.
- [CI run 35186853625](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/35186853625): all four jobs green. Backend **6058 passed, 1 skipped**, 550.03 seconds. Mobile typecheck/checks, test-ID lint, web structure passed.
- Render service `fantasy-trade-finder`, deployment `dep-dalo0uh5efls73blktcg`, exact merge SHA above **live at 05:55:05.684513 UTC**.
- Live `/api/admin/config` read → scoped PUT → readback at **05:55:58.502972 UTC**: `significance_mode: 0 → 2` (enforce). Threshold `significance_player_min_tier=2` (second-tier player or better) and `significance_allow_first_round_pick=1` unchanged.
- Compared all numeric configuration keys before/after: **only significance_mode changed**. Owner-only include/serve/exclusive settings remain 1; baseline/challenger/gen_v2/fit includes remain 0. Deck limit and group size remain 0 (no offer quota).
- Backend-only release: no TestFlight binary required.

## Review regeneration

Scoped Render one-off job `job-dalo1sijnfac73a89ku0` submitted at 05:56:02 UTC using the deployed artifact and production environment. Calls the existing replenishment helper for only the owner's FFv3 and Newton leagues. Does not call the daily cron, notify managers, or log research feedback as production likes/passes. Completion and batch evidence follow below.

Round-one files and decisions remain untouched. Round two uses its own directory, batch ID and feedback log.

The Render job **succeeded at 05:57:09 UTC**. Read-only Postgres verification found 821 FFv3 and 1,352 Newton non-ghost impressions; every row is owner_v1, significance-v1/enforce, eligible=true, discovery context.

Frozen run diagnostics confirm the gate removed **159 of 980 FFv3 candidates** and **254 of 1,606 Newton candidates**, all for `no_meaningful_centerpiece`. The run's legacy `deck_size` is pre-significance; `config_json.significance.final_served` is the verified post-gate denominator (821 / 1,352).

- FFv3 deck job: `239787e47b734307b71b4a50623e3561`.
- Newton deck job: `9effccc8ef824db2a3ebacc4405f687a`.
- First 50 ownership-valid, distinct packages per league selected in recorded order, excluding exact packages already decided in round one. FFv3 scan excluded 16 previously decided packages and 8 ownership-invalid packages against current public Sleeper rosters. Newton uses latest imported ESPN rosters and stored pick ownership; not a fresh ESPN sync.
- Final 100: two 1×1, fifty-two 1×2, forty-six 2×1. No review-only quality re-ranking.
- Local review: `http://127.0.0.1:8880/`; directory `/Users/teresadickens/.codex/visualizations/2026/09/04/01a06db6-8795-7631-94c0-eaefbe0a5175/trade-review-r2`.
- 11 local HTTP/data/feedback-isolation tests passed. Browser QA verified Yes auto-advance, Undo, all decline choices, and low-impact reason auto-advance; QA mode did not save synthetic feedback. Normal view handed over at 0/100.
- Original round-one log still has 32 records. Research feedback remains local and does not update production rankings or send offers.

Operational caveat: the one-off job exercises production code/data and records generated impressions, but its process-local cache is not the web process's cache. Normal app requests use the same live significance rule. Generation still uses imported roster state; the separate fresh FFv3 ownership check above removed stale packages from this review.
