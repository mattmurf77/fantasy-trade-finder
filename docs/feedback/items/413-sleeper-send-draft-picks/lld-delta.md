# LLD delta — G-413 Send in Sleeper: server-owned draft-pick encoding

> Delta against [`living-memory/LLD.md`](../../../../living-memory/LLD.md) and
> [`docs/api-reference.md`](../../../../docs/api-reference.md). Everything here is
> **binding**: a backend agent and a mobile agent working blind must produce compatible
> code from this document alone.
>
> Base: worktree `9145d22f`. Every `file:line` verified 2026-09-02. Requirements `R-n`
> are in [`prd.md`](prd.md) §3.

---

## 1. Shape of the change

Two new helpers in `server.py`, one pure formatter in `sleeper_write.py`, one conditional
block in each of two existing routes, two new 422 codes, one new 400 reason, two new
validate warning codes, two new mobile alert branches, two new structural checks.
**No table, no flag, no route, no type change on the wire.**

```
propose_trade_to_sleeper (server.py:16156)
  … existing gates … their_rid resolved (:16226)
  ├─ give_players / give_picks  = split(give)      ─┐ _is_ftf_pick_asset  (:27903)
  ├─ recv_players / recv_picks  = split(receive)   ─┘
  ├─ if give_picks or recv_picks:
  │     rows   = load_draft_picks(league_id)                  (server.py:149 import)
  │     traded = _fetch_sleeper_traded_picks(league_id)       (:13895)
  │     encoded, unmapped, not_owned = _sleeper_encode_ftf_picks(...)   NEW
  │     unmapped  → 422 sleeper_pick_unmapped   (+picks[], message)
  │     not_owned → 422 sleeper_pick_not_owned  (+picks[], message)
  ├─ req = ProposeTradeRequest(give_player_ids=give_players,
  │                            receive_player_ids=recv_players,
  │                            draft_picks=encoded or None)   (:16228-16232, edited)
  └─ … unchanged … _record_send_success(…, give_players, recv_players, encoded, …)  (:16274-16278, edited)
```

---

## 2. `backend/sleeper_write.py`

### 2.1 `encode_draft_pick` — NEW, pure

Place immediately after `_is_valid_pick_str` (`backend/sleeper_write.py:234-236`).

```python
def encode_draft_pick(orig_roster_id: int, season: int, round_: int,
                      from_roster_id: int, to_roster_id: int) -> str:
    """One Sleeper `draft_picks` element: "<orig>,<season>,<round>,<from>,<to>".

    Captured shape (runbook §C2, 2026-07-02): fields 2-5 and both live examples
    ("11,2026,1,1,2", "1,2027,4,2,1") are OBSERVED. Field 1 is captured as the
    ORIGINAL-owner roster id but has not been confirmed on a pick that has
    changed hands (living-memory Q-035) — if Sleeper wanted the current holder
    there, only acquired picks would fail, visibly (GraphQL error → 502).
    `from` is the roster giving the pick up, `to` the roster receiving it.
    Output always satisfies _is_valid_pick_str.
    """
    return f"{int(orig_roster_id)},{int(season)},{int(round_)},{int(from_roster_id)},{int(to_roster_id)}"
```

All five arguments are cast with `int()`; a non-numeric input raises `ValueError`, which the
server-side encoder (§3.2) catches and classifies as `unmapped`. The module keeps its
no-Flask/no-DB rule (`:33`).

### 2.2 Comment edits (same commit)

- Module header `:22` — after "league_id + draft_picks are inlined into the query string":
  add *"draft_picks elements are produced server-side by `server._sleeper_encode_ftf_picks`
  via `encode_draft_pick`; field 1 = original-owner roster id (captured, unconfirmed on a
  multi-owner pick — Q-035)."*
- `ProposeTradeRequest.draft_picks` comment `:230` — replace `pre-encoded` with
  *"server-encoded by encode_draft_pick — never client-supplied"*.

---

## 3. `backend/server.py` — helpers

Place both immediately after `_mfl_encode_ftf_picks` (`server.py:27937-27960`), under a banner
comment mirroring `:27877-27889` (title: `# ── Sleeper pick-asset encoding (FTF pick ids → "orig,season,round,from,to") ──`).

### 3.1 `_sleeper_pick_holder_index` — NEW

```python
def _sleeper_pick_holder_index(traded_picks: list) -> dict:
    """{(season:int, round:int, orig_roster_id:str): holder_roster_id:int} from the
    public traded_picks list ({round, season(str), roster_id(orig), owner_id(current)},
    _fetch_sleeper_traded_picks). Same parsing sync_draft_picks does at
    database.py:10037-10042. Malformed entries are skipped; an absent key means
    "the original roster still holds it"."""
```

Parsing contract (binding): `season = int(tp["season"])`, `rnd = int(tp["round"])`,
`orig = str(tp["roster_id"])`, `holder = int(tp["owner_id"])`; any `TypeError`/`ValueError`/`KeyError`
skips the entry. Live rows carry ints for `roster_id`/`owner_id` and a string `season`
(`backend/tests/fixtures/outlook-hypotheses/ffv3-2024.json:6-12`) — the casts above normalize
both directions.

**Rule (binding):** every roster-id *comparison* is `int` vs `int` — `my_rid`/`their_rid` are
`int` (`_roster_id_for_owner`, `server.py:15981`; body `their_roster_id` cast at `:16220`), the
holder is `int`, the default holder is `int(row["original_roster_id"])`. `str` appears **only**
inside the holder-index key, because the grid column is `String` (`database.py:1100`, written as
`str` at `:10027`/`:10041`/`:10073`). `encode_draft_pick` re-`int()`s all five fields (T-1's
string-input case pins that).

### 3.2 `_sleeper_encode_ftf_picks` — NEW

```python
def _sleeper_encode_ftf_picks(league_id: str, give_picks: list, recv_picks: list,
                              my_rid: int, their_rid: int,
                              grid_rows: list, traded_picks: list
                              ) -> tuple[list, list, list]:
    """FTF pick ids → Sleeper draft_picks strings, ground-truthed twice.
    Returns (encoded, unmapped, not_owned). A pick lands in exactly one of the
    three; `encoded` preserves give-then-receive order. The propose route
    hard-blocks on either failure list (an offer must never silently lose an
    asset); the validate route reports them as blocking advisories."""
```

Per-pick algorithm (binding, in this order):

1. `pid` not in `grid = {str(r["pick_id"]): r for r in grid_rows}` → **`unmapped`**. This one
   membership test covers every existence failure: generic rungs (`generic_pick_…` never has a
   grid row), another league's id, a malformed id, a phantom season, a completed-draft season
   (#228 exclusion), a round beyond `draft_rounds`. `_ftf_pick_parts` is **not** needed for
   classification here — the grid row already carries `season`, `round`, `original_roster_id`,
   and `pick_id == make_pick_id(league_id, season, round, orig)` (`database.py:9756-9765`).
2. `row = grid[pid]`; `key = (int(row["season"]), int(row["round"]), str(row["original_roster_id"]))`.
3. `holder = index.get(key, None)`; if `None`, `holder = int(row["original_roster_id"])`
   (original roster holds by default). An `int()` failure → **`unmapped`**.
4. Give side: `holder != my_rid` → **`not_owned`**. Receive side: `holder != their_rid` → **`not_owned`**.
5. Else encode. Give: `encode_draft_pick(orig, season, round, my_rid, their_rid)`.
   Receive: `encode_draft_pick(orig, season, round, their_rid, my_rid)`. `ValueError` → **`unmapped`**.

The split that feeds it (both routes) is the MFL one verbatim (`server.py:27988-27991`):
`give_players = [p for p in give if not _is_ftf_pick_asset(league_id, p)]`, etc. — so a generic
rung is classified as a pick by the split and as `unmapped` by the encoder; it never reaches
`k_adds`.

### 3.3 Per-case behavior table (binding)

`my_rid = 3`, `their_rid = 5`, league `L`, grid has `L_2027_2_3` (orig 3), `L_2027_1_7` (orig 7),
`L_2026_1_5` (orig 5); `traded_picks` says `(2027, 1, "7") → owner_id 3`.

| # | Pick asset | Side | Grid row? | Holder (index → default) | Result |
|---|---|---|---|---|---|
| 1 | `L_2027_2_3` (my original) | give | yes | — → 3 == my | `"3,2027,2,3,5"` |
| 2 | `L_2027_1_7` (acquired from roster 7) | give | yes | 3 (index) == my | `"7,2027,1,3,5"` |
| 3 | `L_2026_1_5` (their original) | receive | yes | — → 5 == their | `"5,2026,1,5,3"` — from/to **flipped** |
| 4 | `L_2027_1_7` | receive | yes | 3 ≠ their (5) | `not_owned` |
| 5 | `L_2027_2_3` | give, but index says `(2027,2,"3") → 9` | yes | 9 ≠ my | `not_owned` (traded away since the card was built) |
| 6 | `generic_pick_1_early` | either | no | — | `unmapped` |
| 7 | `999_2027_1_3` (other league) / `L_2031_1_3` (beyond horizon) / `L_2026_1_3` when 2026's draft is complete | either | no | — | `unmapped` |
| 8 | mixed trade: one player + one pick from row 6 | — | — | — | whole send refused: 422, `propose_trade` **not called**, players not sent |
| 9 | co-owned rosters | — | — | roster-keyed; `my_rid`/`their_rid` come from `_roster_id_for_owner` (`:15965-15983`) | unchanged |
| 10 | season 2028+ | — | bound by the grid's horizon, not a constant | — | encodes if a row exists, else `unmapped` |
| 11 | `traded_picks` fetch flakes (`[]`) | give, acquired pick (row 2) | yes | default → 7 ≠ my | `not_owned` — **safe refusal** |
| 12 | `traded_picks` fetch flakes (`[]`) | give, my original that I already traded away (row 5) | yes | default → 3 == my | encoded with `from=3` → Sleeper rejects → 502 `sleeper_write_failed` (today's behavior; never a silently wrong send) |

Rows 11–12 are the accepted residual (HLD D-f). The rows `_fetch_sleeper_traded_picks` returns on
failure are indistinguishable from "nothing traded" (`:13906-13908`), and the route makes the
same accommodation for the rosters fetch already.

---

## 4. `POST /api/trades/propose` — route edits (`server.py:16155-16282`)

### 4.1 Request — unchanged

`{league_id, their_user_id | their_roster_id, give_player_ids[], receive_player_ids[], impression_id?}`.
`give_player_ids` / `receive_player_ids` are **MIXED** arrays: Sleeper player ids **and** FTF pick
ids (owned `{league}_{season}_{round}_{orig}`, generic `generic_pick_{round}_{tier}`) — exactly
as the four mounts already send them and as the MFL route documents (`docs/api-reference.md:429`).

**`draft_picks` body key — decision: reject if non-empty.** At `:16194` keep reading it; add,
immediately after the existing `bad_request` check at `:16197-16198`:

```python
if picks:
    _msg = ("draft_picks is not accepted — put pick ids in give_player_ids / "
            "receive_player_ids; the server encodes them.")
    return jsonify({"error": "bad_request", "message": _msg, "detail": _msg}), 400
```

`detail` rides alongside `message` for symmetry with the 422s (§4.2) — no client sends this
key, so it is never rendered; it exists so the catch-all `detail ||` read stays uniform.

Absent or `[]` is fine (every fielded client). The `picks` local is then dead past this point;
delete its later uses (`:16231`, `:16275`) rather than leaving a misleading name.

### 4.2 New block — between `their_rid` resolution (`:16226`) and `ProposeTradeRequest` (`:16228`)

```python
give_players = [p for p in give if not _is_ftf_pick_asset(league_id, p)]
give_picks   = [p for p in give if _is_ftf_pick_asset(league_id, p)]
recv_players = [p for p in receive if not _is_ftf_pick_asset(league_id, p)]
recv_picks   = [p for p in receive if _is_ftf_pick_asset(league_id, p)]
encoded: list = []
if give_picks or recv_picks:
    grid_rows = load_draft_picks(league_id)            # platform rows (default source)
    traded = _fetch_sleeper_traded_picks(league_id)
    encoded, unmapped, not_owned = _sleeper_encode_ftf_picks(
        league_id, give_picks, recv_picks, my_roster_id, their_rid, grid_rows, traded)
    if unmapped:
        _msg = ("Some draft picks in this trade couldn’t be matched to a pick in this "
                "Sleeper league, so nothing was sent. Generic picks like “Early 1st” "
                "can’t be sent — use a specific pick.")
        return jsonify({"error": "sleeper_pick_unmapped", "picks": unmapped,
                        "message": _msg, "detail": _msg}), 422
    if not_owned:
        _msg = ("Some draft picks in this trade have already changed hands, so nothing "
                "was sent. Rebuild the trade and try again.")
        return jsonify({"error": "sleeper_pick_not_owned", "picks": not_owned,
                        "message": _msg, "detail": _msg}), 422
```

Binding details:
- `load_draft_picks` is already imported into `server`'s namespace (`server.py:149`); call it by
  that name (tests patch `server.load_draft_picks`). Pass `source=PICK_SOURCE_PLATFORM` **literally** (build note: the ADR-010 AST guard `test_pick_assignment.py::test_w3_02` forbids bare-default `load_draft_picks` calls and requires each caller to be sanctioned by name — `propose_trade_to_sleeper` and `trades_validate` were added to `_SANCTIONED_SOURCE_CALLERS` with a decision comment; same value as the default)
  (`PICK_SOURCE_PLATFORM`) — not `_pick_read_source()`. Only platform-written rows are existence
  proof for a Sleeper pick; a user-asserted row (ADR-010) is not.
- The two fetches happen **only** inside the `if`. A pick-free send makes no `traded_picks` call
  and no DB read (R-4; the test-harness reason is §7.1).
- `unmapped` is reported **before** `not_owned` — an unmappable pick has no holder to check.
- `picks[]` lists the offending **FTF asset ids as received**, in give-then-receive order.
- **`detail` is mandatory on both 422s and byte-equal to `message`.** Fielded builds
  1.16.12–1.16.14 render `detail || 'Something went wrong sending to Sleeper. Please try again.'`
  in the catch-all (`SendInSleeperButton.tsx:305-310`; `detail` read at `:267`). Without `detail`
  every fielded user would see "Please try again" on a deterministic refusal. The server strings
  use the "Some" form of the mobile copy (§8.1) verbatim, so a fielded build and the new build
  read the same sentence; the new build only adds the count. Curly apostrophes / quotes and the
  em dash are deliberate — the server already ships unicode copy (`server.py:27806`).
- **User-asserted rows are excluded by design (Planner ruling 1).** A `source='user'` row
  (ADR-010) has an `original_roster_id` that is *"an OPAQUE, LEAGUE-LOCAL slot label … never
  resolved against a platform"* (`database.py:10217-10221`, `seed_pick_grid`), so it cannot be
  encoded into a Sleeper roster id even in principle. Such a row can reach a Sleeper league only
  by a direct API call (the assignment routes have no platform guard, `server.py:14502-14545`,
  `:14591-14640`, and `picks.assign_tradeable` is ON, `config/features.json:219`, so
  `_pick_read_source()` unions them into `/api/league/picks`), because the only assignment UI is
  the ESPN Draft Room (`picks_not_assigned` is ESPN-only, `:10840`, `:11347`). If one is ever sent
  it 422s `sleeper_pick_unmapped`. The platform-only default is the containment, not an
  oversight.

### 4.3 Request build and success leg

`:16228-16232` becomes
`ProposeTradeRequest(league_id=…, my_roster_id=…, their_roster_id=their_rid, give_player_ids=give_players, receive_player_ids=recv_players, draft_picks=encoded or None)`.

`:16274-16278` becomes `_record_send_success(user_id, league_id, give_players, recv_players, encoded, result.get("transaction_id"), bool(body.get("impression_id")))`.
The helper's signature (`:16117-16120`) is **unchanged**; only what the route passes changes, so
`give_n`/`receive_n` count players and `pick_n` counts encoded picks. `test_analytics_p0.py:455-467`
drives the helper directly and stays green.

### 4.4 Response — new rows in the error contract

| Status | `error` | Extra fields | Meaning |
|---|---|---|---|
| 400 | `bad_request` | `message`, `detail` (equal) | (new reason) non-empty `draft_picks` in the body. Existing 400 reasons unchanged. |
| 422 | `sleeper_pick_unmapped` | `picks: string[]`, `message`, `detail` (equal) | ≥1 pick asset is not a concrete pick in this league's grid (generic rung, foreign/malformed id, out-of-horizon or completed-draft season, user-asserted row). Nothing sent. |
| 422 | `sleeper_pick_not_owned` | `picks: string[]`, `message`, `detail` (equal) | ≥1 pick's current holder (live `traded_picks`, default original roster) is not the side offering it. Nothing sent. |

Both 422s: no `sleeper_send_succeeded` row, no `deck_outcomes` row (they return before
`:16264`), no credential change. Docstring `:16157-16166` lists the two new codes and drops
"(players-only v1; picks pre-encoded)".

---

## 5. `POST /api/trades/validate` — Sleeper branch edits (`server.py:27715-27834`)

After `mine`/`theirs` resolve and the `roster_not_found` early return (`:27787-27795`), before
`my_players` (`:27797`):

```python
give_players = [p for p in give if not _is_ftf_pick_asset(league_id, p)]
give_picks   = [p for p in give if _is_ftf_pick_asset(league_id, p)]
recv_players = [p for p in receive if not _is_ftf_pick_asset(league_id, p)]
recv_picks   = [p for p in receive if _is_ftf_pick_asset(league_id, p)]
if give_picks or recv_picks:
    _, unmapped, not_owned = _sleeper_encode_ftf_picks(
        league_id, give_picks, recv_picks, my_rid, their_rid,
        load_draft_picks(league_id), _fetch_sleeper_traded_picks(league_id))
    if unmapped:
        n = len(unmapped)
        warnings.append({"code": "asset_unmapped", "severity": "blocking", "message": (
            f"{n} draft pick{'s' if n != 1 else ''} in this trade can't be sent to Sleeper "
            "(generic picks like “Early 1st” name no real pick) — the send will be blocked "
            "rather than dropping them.")})
    if not_owned:
        n = len(not_owned)
        warnings.append({"code": "pick_moved", "severity": "blocking", "message": (
            f"{n} pick{'s' if n != 1 else ''} in this trade are no longer owned by the "
            "expected team (already traded) — Sleeper will reject the offer.")})
```

Then the existing `player_moved` loop (`:27797-27808`) and `roster_limit` loop (`:27810-27832`)
run over **`give_players` / `recv_players`** instead of `give` / `receive` — three substitutions:
`moved_give`/`moved_receive` (`:27799-27800`) and the `out_ids`/`in_ids` tuples (`:27822-27823`).
Sleeper's roster limit counts players only; picks are not roster slots.

Warning contract additions (Sleeper branch):

| `code` | `severity` | Copy (N substituted; singular/plural as above) |
|---|---|---|
| `asset_unmapped` | `blocking` | `N draft pick(s) in this trade can't be sent to Sleeper (generic picks like “Early 1st” name no real pick) — the send will be blocked rather than dropping them.` |
| `pick_moved` | `blocking` | `N pick(s) in this trade are no longer owned by the expected team (already traded) — Sleeper will reject the offer.` |

The curly quotes match the mobile alert copy (§8.1); both strings can appear in the same alert
list, so they must not mix quote styles. Both codes already exist in the MFL vocabulary (`:28003`, `:28030`; `api-reference.md:406,432`), so
`TradeSendWarning.code` (`mobile/src/api/sendInSleeper.ts:214`) needs a comment update only.
`checked` semantics unchanged; a `traded_picks` flake degrades exactly as §3.3 rows 11–12.

---

## 6. Function-level touch points

| File:line | Change |
|---|---|
| `backend/sleeper_write.py:22` | header line: server-side production + field-1 caveat |
| `backend/sleeper_write.py:230` | `draft_picks` field comment |
| `backend/sleeper_write.py:236` (after) | NEW `encode_draft_pick` |
| `backend/server.py:16157-16166` | propose docstring: new codes; drop "players-only v1" |
| `backend/server.py:16194-16198` | keep `picks` read; add the non-empty → 400 |
| `backend/server.py:16226→16228` | NEW split / fetch / encode / 422 block |
| `backend/server.py:16228-16232` | players-only arrays + `draft_picks=encoded or None` |
| `backend/server.py:16274-16278` | honest args to `_record_send_success` |
| `backend/server.py:27960` (after) | NEW banner + `_sleeper_pick_holder_index` + `_sleeper_encode_ftf_picks` |
| `backend/server.py:27795→27797` | NEW validate split + pick advisories |
| `backend/server.py:27799-27800`, `:27822-27823` | players-only lists |
| `backend/analytics_taxonomy.py:1055-1058` | comment: "14 server codes … 17 values" |
| `backend/tests/test_sleeper_write_route.py:288` | fixture fix (PRD §7.2) |
| `mobile/src/components/SendInSleeperButton.tsx:252-253` | comment: 14 server codes ∪ 3 = 17 |
| `mobile/src/components/SendInSleeperButton.tsx:300-305` | two NEW `else if` branches (§8) |
| `mobile/src/api/sendInSleeper.ts:5-6` | error-code list comment |
| `mobile/src/api/sendInSleeper.ts:214` | warning-code comment: `+ asset_unmapped \| pick_moved` |
| `mobile/tests/check-send-button-platform.js` | checks 7–8 (§8.3) |
| `mobile/src/components/CLAUDE.md:33`, `mobile/src/api/CLAUDE.md:32` | one clause each |

---

## 7. Test-harness contract (backend)

### 7.1 Why new tests must not rely on `_sleeper_get` stubs for picks

Every propose-route test stubs `server._sleeper_get` with a single `return_value=rosters`
(`backend/tests/test_sleeper_write_route.py:117,135,150,170,252,283,300`). `_fetch_sleeper_traded_picks`
also goes through `_sleeper_get` (`server.py:13905`), so an unconditional traded-picks fetch would
receive the **rosters list** as traded picks. Two consequences, both binding:

1. The route fetches `traded_picks` only when picks are present (§4.2) — the existing seven tests
   are pick-free (after the `:288` fixture fix) and stay byte-identical.
2. Pick tests patch `server._fetch_sleeper_traded_picks` and `server.load_draft_picks` directly,
   and inspect the `ProposeTradeRequest` the `propose_trade` `MagicMock` received
   (`fake.call_args[0][1]`, the idiom at `:126-127`).

### 7.2 Fixture shapes for tests

```python
GRID = [  # load_draft_picks rows — only the keys the encoder reads are required
    {"pick_id": f"{LEAGUE}_2027_2_1", "season": 2027, "round": 2, "original_roster_id": "1"},
    {"pick_id": f"{LEAGUE}_2027_1_7", "season": 2027, "round": 1, "original_roster_id": "7"},
    {"pick_id": f"{LEAGUE}_2026_1_2", "season": 2026, "round": 1, "original_roster_id": "2"},
]
TRADED = [{"season": "2027", "round": 1, "roster_id": 7, "owner_id": 1, "previous_owner_id": 7}]
```

With `rosters = [{owner_id: SLEEPER_UID, roster_id: 1}, {owner_id: "opp", roster_id: 2}]`:
give `L_2027_2_1` → `"1,2027,2,1,2"`; give `L_2027_1_7` → `"7,2027,1,1,2"`; receive `L_2026_1_2`
→ `"2,2026,1,2,1"`.

For the validate suite (`test_trade_send_validate.py`), the fixture (`:38-57`) gains two
`patch.object` rows: `server.load_draft_picks` → `GRID` and `server._fetch_sleeper_traded_picks`
→ `TRADED`, keyed to league `"987654321"`. That file does not patch the DB engine, so the
`load_draft_picks` patch is mandatory, not optional.

---

## 8. Mobile

### 8.1 `SendInSleeperButton.tsx` — error ladder (`:266-310`)

Insert two branches **after** the `roster_not_found || opponent_roster_not_found` branch
(`:300-304`) and **before** the catch-all `else` (`:305`). Exact copy:

```tsx
} else if (code === 'sleeper_pick_unmapped') {
  // #413 — ≥1 pick could not be matched to a pick in this league's grid
  // (generic rungs like “Early 1st”, or a pick outside the synced grid).
  // The server refused the WHOLE send rather than dropping the pick.
  // Count-aware like the MFL twin (SendInMflButton.tsx:141-146); the ids
  // themselves are never rendered.
  const n = Array.isArray(body?.picks) ? body.picks.length : 0;
  Alert.alert(
    'Couldn’t send',
    `${n || 'Some'} draft pick${n === 1 ? '' : 's'} in this trade couldn’t be matched to a pick in this Sleeper league, so nothing was sent. Generic picks like “Early 1st” can’t be sent — use a specific pick.`,
  );
} else if (code === 'sleeper_pick_not_owned') {
  // #413 — live traded_picks says the offering team no longer holds it.
  const n = Array.isArray(body?.picks) ? body.picks.length : 0;
  Alert.alert(
    'Couldn’t send',
    `${n || 'Some'} draft pick${n === 1 ? '' : 's'} in this trade ${n === 1 ? 'has' : 'have'} already changed hands, so nothing was sent. Rebuild the trade and try again.`,
  );
}
```

Binding: neither branch calls `goConnect` (these are not auth errors) and neither reads
`detail`. `body?.picks` is **counted, never rendered** — pick ids are league-internal strings,
not user copy; the count is the same idiom `SendInMflButton.tsx:141-146` uses for `unmapped`.
Sentence case, curly apostrophes, em dash, no emoji (Chalkline body copy,
`docs/design/design-system.md:103`). With `n = 0` (an old server that omits `picks`) the
sentence degrades to the server's own "Some …" form. The `track('sleeper_send_failed', …)` at `:254-264`
runs before the ladder and already carries `error_code: body?.error`, so the two new codes
arrive with **no emitter change**.

### 8.2 Comments

- `SendInSleeperButton.tsx:252-253`: `Closed enum: 14 server codes ∪ network | timeout | unknown = 17 values, forever.`
- `sendInSleeper.ts:5-6`: extend the parenthetical with `| sleeper_pick_unmapped | sleeper_pick_not_owned`.
- `sendInSleeper.ts:214`: `// league_archived | player_moved | roster_limit | roster_not_found | asset_unmapped | pick_moved`.

No TypeScript type changes. `ProposeTradePayload` (`:24-33`) is untouched — the arrays were
always mixed; the `:27-28` comments may say so (`// players AND FTF pick ids I send`).

### 8.3 `mobile/tests/check-send-button-platform.js` — checks 7–8

Append a block after check 6 (`:427`), same `parse`/`walk` helpers, same `ok`/`fail` idiom.
Walk `SendInSleeperButton.tsx` for the `doPropose` `catch` block's if/else-if chain: locate the
`IfStatement` whose condition matches `/sleeper_not_linked/` and follow `elseStatement` links,
collecting each condition text until the final `else` (a non-`IfStatement`). Assert:

- **7.** the collected conditions include one matching `/code\s*===\s*'sleeper_pick_unmapped'/`
  whose `thenStatement` contains a call `Alert.alert(` and **no** `goConnect` reference.
- **8.** likewise for `/code\s*===\s*'sleeper_pick_not_owned'/`.
- **7b.** both appear **before** the final `else` (i.e. inside the chain; a branch appended
  after the catch-all is unreachable and must fail).
- **7c.** the final `else` still contains `Something went wrong sending to Sleeper` (the
  catch-all was not replaced).

Named sabotages, each must go RED: delete either branch; move a branch below the catch-all;
route `sleeper_pick_not_owned` into the `goConnect` reconnect branch (the tempting "refresh"
instinct — a reconnect cannot fix a pick ownership change).

The `npm run test:send-button-platform` script exists (`mobile/package.json:80`); no
`package.json` change.

---

## 9. Contract summary (wire-level, both agents)

```
POST /api/trades/propose            request unchanged (mixed arrays); draft_picks non-empty → 400 {error, message, detail}
  200 {status, transaction_id}                          picks encoded server-side
  422 {error:"sleeper_pick_unmapped",  picks:[…], message, detail}   ← checked first; detail == message
  422 {error:"sleeper_pick_not_owned", picks:[…], message, detail}   ← detail == message (fielded catch-all renders it)
POST /api/trades/validate           request unchanged
  200 {ok, checked, warnings:[…{code:"asset_unmapped"|"pick_moved", severity:"blocking", message}]}
sleeper_send_failed.error_code      += "sleeper_pick_unmapped" | "sleeper_pick_not_owned"   (17 values)
sleeper_send_succeeded.props        give_n/receive_n = players only; pick_n = encoded picks (semantic fix, dated)
```

---

## 10. LLD conventions this establishes

One line for `living-memory/LLD.md` (new topical H2, TOC row added):

> **Pick assets ride the mixed asset arrays on every propose route; the server splits and
> encodes them against its own ground truth, and any unresolvable pick refuses the whole send
> (2026-09-02, #413).** Sleeper (`_sleeper_encode_ftf_picks`: `draft_picks` grid + live
> `traded_picks`), MFL (`_mfl_encode_ftf_picks`: stored `futureDraftPicks` snapshot), ESPN
> (permanent 422). No propose route accepts a client-encoded pick string.
