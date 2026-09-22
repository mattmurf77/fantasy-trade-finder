# Prepared inventory: counterparty freshness regression

September 22, 2026. Agent B, parent-authorized bounded diagnostic. This
**reproduces** the board/outlook counterexample in
[prepared-inventory-audit.md](prepared-inventory-audit.md) through real job
admission, generation, persistence, save routes and public views. It is not a
production observation, a freshness fix or a full dependency-receipt design.

## Result

All four counterparty freshness guards are **RED**. Both completed and genuinely
running A jobs continue exposing their identical 19-card snapshots after B saves
either rankings or outlook. Thirteen of those cards are explicitly B-targeted,
undecided offers excluding the one fixture-seeded liked offer. All thirteen
remain visible. A's ordinary, non-forced generate request reuses the same old
job ID; no replacement worker is admitted.

All four matching **own-input controls are GREEN**. A's own board/outlook save
changes public status to `error` / `inputs_changed`, clears cards and causes the
next ordinary request to admit exactly one distinct replacement job.

| Changed input | A job before change | B changes input | A changes own input |
|---|---|---|---|
| Board | Complete | 19 cards retained; same completed job | 0 cards; replacement admitted |
| Board | Running, durable cards published | 19 cards retained; same running job | 0 cards; replacement admitted |
| Outlook | Complete | 19 cards retained; same completed job | 0 cards; replacement admitted |
| Outlook | Running, durable cards published | 19 cards retained; same running job | 0 cards; replacement admitted |

Before each mutation, unchanged-input adoption successfully reuses the original
job. This rules out a harness that simply never reaches the cache-admission path.
The own-input controls exercise genuine route invalidation rather than a direct
test call to `_invalidate_trade_jobs` or an assertion over synthetic job keys.

## Exact proof scope

- Reuses the existing isolated owner-route league/session fixture, with actual
  SQLite member rankings and league preferences. A and B have separate verified
  sessions and ranking/trade services. Their synthetic canonical account IDs
  equal their league-member IDs, in one active Sleeper-format league.
- Runs actual `_kickoff_trade_job(..., synchronous=True)` and the actual dark
  bilateral revision constructor. A transparent observer records the constructor
  arguments while delegating unchanged. It verifies B's DB-backed board and
  declared `not_sure` outlook were consumed. No generated cards, evaluations or
  publication results are mocked.
- B's actual `/api/tiers/save` request changes the persisted B board; actual
  `/api/league/preferences` changes B's persisted outlook to `jets`. Both return
  200, and direct reads from the isolated database confirm the changed values.
  The viewer controls invoke those same routes with A's session.
- Reads actual `/api/trades/status` and `/api/trades/generate`. Running checks
  execute immediately before the real worker's successful finish transition,
  after its real cards/impressions are durable and public. No test assigns a
  fabricated running/complete state. Replacement thread launch alone is stubbed
  to record admission and avoid a second generation; current-job execution is
  real. This proves a deterministic running-publication boundary, not arbitrary
  thread interleavings or mutation during constructor execution.
- Preserves all original impression rows, including exact private valuation
  strings, and the exact linked like audit row. The like is seeded with the real
  `save_trade_decision` writer against one actual impression, not by pretending
  to exercise a human swipe. The before/after impressions, decisions and outcomes
  tables are equal in all eight cases. No view/engagement outcome is created.
- B's session receives 404 for A's job-status ID. This establishes the exercised
  ownership check, **not** universal account/league authority coverage. No
  provider-account aliasing, ESPN/MFL identity resolution, cross-league switch,
  membership transfer or concurrent session-init mutation is tested.
- Socket connections are denied and counted; zero network attempts occur.
  Existing local DynastyProcess test data supplies market values. Nonessential
  deck exploration/presentation and ranking analytics hooks are disabled or
  stubbed consistently; the job registry, epochs, invalidation, real ranking and
  preference writes, generator and public freshness checks remain actual code.

The proven defect is failure to revoke dependent undecided inventory after a
known consumed counterparty input changes. The diagnostic does not claim that
all retained offers become economically ineligible, measure a production stale
offer rate, test every source in the audit, or establish a latency improvement.
It does not implicate the round7 JSON optimization as the cause. No runtime or
shared test file was changed for this diagnostic.

## Reproduction and binding

Private test:
`/private/tmp/prepared-inventory-regression-20260922.F5Rkdv/test_prepared_inventory.py`

Final private-test SHA256:
`9b38fd717a6fc110c9b20c22f3a1e3a423c0d4c4c5676d97b3defb98b1d98f0d`.

Final run: **4 failed / 4 passed in 1.74s**, exit 1 deliberately retained. Only
the four `[board|outlook]-partner-[complete|running]` cases fail, at the named
`stale dependent undecided inventory remains public` guard. They first assert
the exact old snapshot and job are retained and audit evidence is unchanged.
The preliminary board harness call omitted a required loader argument; that
harness-only error was corrected before the stated final result.

Run from `/private/tmp/fleeced-bilateral-revision-20260922`:

```sh
env DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/private/tmp/fleeced-bilateral-revision-20260922 \
  FTF_DP_VALUES_FILE=/private/tmp/fleeced-bilateral-revision-20260922/backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv \
  /private/tmp/ktc-benchmark-venv/bin/python -m pytest \
  /private/tmp/prepared-inventory-regression-20260922.F5Rkdv/test_prepared_inventory.py \
  -q -s -p no:cacheprovider --tb=short
```

Actual shared source hashes at the diagnostic:

| File | SHA256 |
|---|---|
| `backend/server.py` | `3fa92ee850dfc8eb01a69ab7d052a85f8cda5facc158ac84d730ad27d2ed19c6` |
| `backend/database.py` | `7e5a0f2f22ac7379b4ed5946c361832c636ff746eee290990016de5eb887272c` |
| `backend/trade_gen_owner.py` | `cf76e4e79da318165812d94ff16a047ec3be7c2980b02b25fd5b5662ee4f39ad` |
| `backend/trade_gen_bilateral.py` | `978b09445652bf2f65c2bdb3e8f2f507788b08ea50fc5808cf95ad7d96ccde32` |
| `backend/trade_gen_bilateral_candidate.py` | `18d524ce1aab2d50118e976604e4c6ad123acc8da2bfbb44f231b49d17ab7b69` |

The private RED regression is outside shared pytest collection. Parent's passing
full suite therefore remains a correct account of that suite, but does not
establish this newly exercised freshness property. Any repair requires its own
parent-written implementation scope and subsequent RED/GREEN validation.
