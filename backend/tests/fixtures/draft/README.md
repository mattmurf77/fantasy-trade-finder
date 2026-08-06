# Draft fixture corpora (rookie-draft M1)

Recorded cassettes that let M3–M5 exercise every draft state offline.
Spec: `docs/plans/rookie-draft/plan.md` §M1, `docs/plans/rookie-draft/lld.md` §4.1.
Harness: `backend/tests/support/draft_replay.py`. Tests: `backend/tests/test_draft_replay.py`.

## Inventory

| Corpus | Platform | Provenance | Pins | Drives |
|---|---|---|---|---|
| `lakeview-complete/` | Sleeper | **live** 2026-08-06, league `1312076055586050048`, draft `1312076055594430464` | complete draft, 48 picks (4×12), populated `draft_order`, **non-identity** `slot_to_roster_id`, 55 league `traded_picks` | T-M3-01/02/05/06, D5 |
| `ffv3-predraft/` | Sleeper | **live** 2026-08-06, league `1312140920132497408`, draft `1312140920136699904` | `draft_order: null`, `start_time: null`, `last_picked: null`, `picks: []`, **the identity `slot_to_roster_id` trap** | T-M3-03, D5 |
| `startup-shaped/` | Sleeper | derived from `lakeview-complete` | `settings.rounds: 28`, `pre_draft`, no picks — real order retained | T-M3-10 |
| `empty-drafts/` | Sleeper | authored | `drafts == []` — the ambiguous read | T-M3-04 |
| `players-bulk/` | Sleeper | authored | a 3-player stand-in at `players/nfl.json` | T-M1-04 |
| `mfl-made0/` | MFL | **live** 2026-08-06, league `10015` @ `www44` | 1 unit, **0/60** made | T-M5-01, D8 |
| `mfl-partial/` | MFL | **live** 2026-08-06, league `10125` @ `www46` | 1 unit, **36/72** made, trade provenance in `comments` | T-M5-02, D8 |
| `mfl-complete/` | MFL | **live** 2026-08-06, league `10005` @ `www48` | 1 unit, **30/30** made | T-M5-03, D8 |
| `mfl-multi-unit/` | MFL | **live** 2026-08-06, league `60206` @ `www46` | **2** `draftUnit`s (`CONFERENCE00/01`), 192/192 made | T-M5-04, D8 |

Every corpus carries a `manifest.json` stating provenance, pins and derivation;
`test_every_corpus_declares_its_provenance` enforces that a non-live corpus says
how it was made.

## Two mechanisms, because there are two seams

**Sleeper** rides the shipped `FTF_SLEEPER_FIXTURES_DIR` seam. `_sleeper_fixture_path`
maps `…/v1/<path>` → `<dir>/<path>.json`, so the tree below is literally the URL space:

```
<corpus>/league/<league_id>.json            GET /v1/league/<id>
<corpus>/league/<league_id>/drafts.json     GET /v1/league/<id>/drafts
<corpus>/league/<league_id>/rosters.json    …/rosters
<corpus>/league/<league_id>/users.json      …/users
<corpus>/league/<league_id>/traded_picks.json
<corpus>/draft/<draft_id>.json              GET /v1/draft/<id>          (1.2 KB detail)
<corpus>/draft/<draft_id>/picks.json        GET /v1/draft/<id>/picks    (20 KB pick list)
<corpus>/draft/<draft_id>/traded_picks.json
```

**MFL** has no env seam — `mfl_service` injects `_opener` (`_fetch_one`). MFL corpora are
therefore a committed `draftResults.json` plus `draft_replay.mfl_opener(<corpus>)`, matching
the convention `backend/tests/fixtures/mfl_league_snapshot_2026-07-17.json` already uses.
`draft_board_service`'s MFL path must accept an injectable `_opener` all the way down, or M5
is untestable.

## Re-recording

**One corpus per directory.** `server.py` exits if `FTF_SLEEPER_RECORD=1` and the fixtures dir
already holds any `**/*.json` — it will never silently overwrite a cassette ([RV-6]). So record
into a fresh empty dir, then move the result here:

```bash
FTF_SLEEPER_FIXTURES_DIR=/tmp/rec-<name> FTF_SLEEPER_RECORD=1 python3 - <<'PY'
from backend import server
B = "https://api.sleeper.app/v1"
lid = "<league_id>"
for u in (f"{B}/league/{lid}", f"{B}/league/{lid}/rosters", f"{B}/league/{lid}/users",
          f"{B}/league/{lid}/traded_picks", f"{B}/league/{lid}/drafts"):
    server._sleeper_get(u)
for d in server._sleeper_get(f"{B}/league/{lid}/drafts"):
    server._sleeper_get(f"{B}/draft/{d['draft_id']}")
    server._sleeper_get(f"{B}/draft/{d['draft_id']}/picks")
    server._sleeper_get(f"{B}/draft/{d['draft_id']}/traded_picks")
PY
```

Record mode is deliberately live and refuses to run with `FTF_TEST_MODE=1`. Token-bearing
fields are scrubbed by key name on write (`_sleeper_record`).

MFL re-record: `mfl_service.fetch_draft_results(<league_id>, <year>, <host>)` with no `_opener`,
then write the returned dict to `<corpus>/draftResults.json`. Public leagues need no auth;
resolve the host from the league URL or via `mfl_service.resolve_host`.

## Two things not to "tidy"

1. **The `ffv3-predraft` identity map is the hazard, not a bug.** The pre-draft detail object
   returns `slot_to_roster_id = {"1":1 … "12":12}` while `draft_order` is `null`. Reading that
   map as an order invents a draft order. `test_ffv3_pins_the_identity_slot_to_roster_id_trap`
   fails if anyone normalises it away, so T-M3-03 can't pass vacuously.
2. **Sleeper pick objects carry no timestamp.** Verified against the live recording; `last_picked`
   lives only on the detail object. `DraftReplay.truncate_picks` therefore synthesises a
   monotonic ladder anchored so `pick_timestamp(total)` equals the recorded live value — a
   full-length replay is byte-identical to the cassette. The LLD assumed per-pick timestamps.
