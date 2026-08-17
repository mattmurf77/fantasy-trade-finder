# FB-328 — Mock draft pick assignment: plan

> Phase-1 (plan) deliverable for group **G3** of the 2026-08-16 feedback wave.
> Batch context: [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md).
> Base: `origin/main` @ `d3fe3ac` (v1.13.4). All file:line citations are
> against that sha. Path: **Feature (backend correctness)** — HLD/LLD deltas
> follow in the Author round; §5 names every contract that moves.

## 1. Report and root cause

**Report (#328, mattmurf77, v1.13.3, LeagueRankings):** "Mock drafts aren't
using the actual assigned draft picks (for example in Newton I got all four
picks to slot 8 rather than my actual assigned/traded picks."

**Newton is an ESPN league.** "Newton Dynasty League" is ESPN league 11896 —
`backend/tests/fixtures/espn_league_11896_standings_2026-08-08.json:6`.

**Root cause — `backend/server.py:12110`,** in `_mock_real_draft`
(`server.py:12084`):

```python
if platform != dbs.SLEEPER or not is_enabled("draft.room"):
    return out          # out = {order: None, order_source: "randomized",
                        #        traded_slots: {}, type: None}
```

Every non-Sleeper league short-circuits to the empty resolution. The create
route (`server.py:12319-12331`) then calls `build_settings`
(`backend/mock_draft_service.py:995`) with `order=None, traded_slots={}`, so:

- the order becomes a seeded shuffle (`mock_draft_service.py:1061-1063`) —
  the shuffle happened to put the operator at slot 8;
- `resolved_ownership` stays empty (`mock_draft_service.py:1075-1083`), so
  `owner_of` (`mock_draft_service.py:970`) falls through to pure slot order —
  **every team drafts all rounds at its own slot**, which is exactly "all
  four picks to slot 8".

The engine itself is *not* the problem: `build_settings` already accepts a
`traded_slots` overlay keyed `(round, slot)` and `owner_of` already lets
ownership win over slot order in **both** cpu and manual modes (the mode
lever is `next_pick`'s `is_user` only, INV-7 — `mock_draft_service.py` §next_pick).
The bug is that the create route never feeds the overlay for non-Sleeper
platforms — and that the resulting fallback is **silent**: `order_source`
discloses order provenance (KD-6), but nothing in the payload or UI says
"real pick ownership was not applied".

Secondary finding: the guard's justifying comment (`server.py:12111-12114`,
"MFL's grid states the CURRENT owner but never the original") is **stale** —
`_sync_mfl_owned_picks` (`server.py:9519`) reads `pk["original_owner"]` from
MFL's `futureDraftPicks` export and persists `original_user_id` +
`is_traded` per row. MFL does distinguish overlay from order; what it lacks
is only a slot *sequence*.

## 2. Per-platform data availability matrix

| Platform | Where traded-pick truth lives | Ingested today? | Slot order available? |
|---|---|---|---|
| **Sleeper** | `/v1/league/<id>/traded_picks` → `_fetch_sleeper_traded_picks` (`server.py:10712`) → `sync_draft_picks` grid+overlay (`database.py:8297`) → normalized `draft_picks` rows (source NULL/platform), synced by `_sync_sleeper_owned_picks` (`server.py:9618`). Also live on the Draft Room board rows (`draft_board_service.py:802-804`: `original_user_id`, `is_traded`, `owner_user_id`). | **Yes — and already wired into the mock** via the board read in `_mock_real_draft` (`server.py:12119-12148`), when `draft.room` is on and `order_confidence == ORDER_ASSIGNED`. | Yes (`draft_order`, round-1 original owners). |
| **MFL** | `futureDraftPicks` API export — `mfl_service.fetch_future_draft_picks` (`mfl_service.py:401`), `parse_future_picks` (`mfl_service.py:680`), cached in `leagues.platform_future_picks` (`mfl_service.py:676`), normalized into `draft_picks` incl. `original_user_id`/`is_traded` by `_sync_mfl_owned_picks` (`server.py:9519-9614`; refresh at `_refresh_mfl_future_picks` `server.py:12556`). | **Yes** (ownership incl. original owner). Not read by the mock. | **No** — future picks carry no slot sequence; the MFL board render leaves `original_user_id: None` (`draft_board_service.py:1194`) and `draft.mfl` ships OFF. Order stays randomized-and-labelled. |
| **ESPN** | No platform pick objects ever (#158, `server.py:9209`; operator ruling: ESPN has no rookie-draft concept). Truth = the **manual pick-assignment tool** (W3, ADR-010, flag `picks.assign`): `draft_picks` rows with `source='user'` (`seed_pick_grid` `database.py:8528`, `assign_draft_pick` `database.py:8700`) + stored numbering `leagues.pick_assignment_settings` `{rounds, order_type, order[]}` (`database.py:285`, loaded via `load_pick_assignment_settings` `database.py:8669` / `_assignment_settings` `server.py:10988`). The ESPN Draft Room board is built entirely from this grid: `assigned_board` (`draft_board_service.py:1373-1453`) emits rows with `slot`, `owner_user_id`, `original_user_id`, `is_traded` and `order_confidence=ORDER_ASSIGNED`; the server's grid builder is at `server.py:11209-11245`, board-route call at `server.py:11783`. | **Yes** (user-asserted; contested/orphaned rows excluded by `load_draft_picks`'s default row filter, `database.py:8474-8526`). Not read by the mock. | **Yes, when the grid is seeded + ordered** (the stored round-1 `order`). Mock entry already requires an upcoming board, which for ESPN *is* the seeded grid. |
| **Fleaflicker** | Nothing — `backend/fleaflicker_service.py` contains zero pick/draft ingestion (verified by grep). | **No.** | No. → honest fallback only. |

## 3. Approach

One principle: **resolution happens at create time, in `_mock_real_draft` and
a new sibling helper — the engine is untouched except for carrying one new
label.** Because `owner_of` already serves both cpu and manual modes, fixing
the create-time inputs fixes **both modes** with no mode-specific code.

### 3.1 Sleeper — unchanged

The board path (`server.py:12119-12148`) already resolves order + traded
slots. Surgical rule: don't migrate it to the store; only its *label* output
gains the new `ownership_source` value (`'platform'` when the overlay was
applied, see §4).

### 3.2 ESPN — reuse the assignment board

Extend the `server.py:12110` guard: when `platform == dbs.ESPN` and
`is_enabled("picks.assign")`, build the same `AssignmentGrid` the board route
builds (share/extract the grid construction at `server.py:11209-11245`) and
call `dbs.assigned_board`. Downstream row-reading code
(`server.py:12131-12148`) is reused verbatim — `assigned_board` rows carry
the identical `slot` / round-1 `original_user_id` / `is_traded` /
`owner_user_id` fields and `ORDER_ASSIGNED` confidence. The stored round-1
`order` therefore arrives as the mock's real order (`order_source:
"assigned"`), and every user-asserted traded pick lands in `traded_slots`.
Ownership label: `'user'`.

Unseeded / unordered grid ⇒ `assigned_board` answers `picks_not_assigned` /
non-assigned confidence ⇒ the existing "partial map is not an order" drop
fires ⇒ honest fallback (§4). Note `_assignment_settings` **pads** missing
members onto the stored order (`server.py:10995-11008`) — the padded order is
what the grid renders, so using the board's rows (not the raw stored JSON) is
deliberate: mock and PickAssignmentScreen can never disagree.

### 3.3 MFL — ownership overlay from the normalized store, order stays randomized

MFL states ownership but no slot sequence, so:

1. Order: unchanged — seeded shuffle, `order_source: "randomized"` (KD-6
   holds; never invent an order).
2. New helper `_mock_owned_pick_overlay(league_id, season, rounds,
   resolved_order)` (backend/server.py, next to `_mock_real_draft`):
   - `load_draft_picks(league_id, source="platform")`
     (`database.py:8474`), filtered to `season == mock season`,
     `round <= mock rounds`, `is_traded` truthy;
   - for each row: `slot = resolved_order.index(row["original_user_id"]) + 1`;
     emit `traded_slots[(round, slot)] = row["owner_user_id"]`.

   **The overlay is anchored to the original owner's slot, wherever the
   shuffle put them** — "your 2nd belongs to team X" is true relative to the
   original owner, not to a slot number, so a randomized order still yields
   correct ownership. `build_settings` already translates `(round, slot)`
   through its own slot table incl. snake numbering
   (`mock_draft_service.py:1074-1082`).
3. Because `build_settings` requires order+overlay to travel together only
   for *platform-slot* overlays, the MFL overlay must be computed **after**
   order resolution and passed alongside whatever order was resolved. (For
   Sleeper/ESPN the board path already couples them; the "drop overlay when
   order drops" rule at `mock_draft_service.py:1050-1056` stays untouched.)
4. No new flag: this is a DB read of rows the MFL link/import paths already
   maintain (`server.py:22072/22211/22318`); `draft.mfl` gates the *board*,
   not the store, and stays irrelevant here.
5. #228/#207 exclusion is inherited for free: a drafted current season has no
   rows (`_sync_mfl_owned_picks`'s verdict-gated exclusion) ⇒ honest fallback,
   which is correct since the mock only starts on an upcoming board anyway.

### 3.4 Identity-space guard (the lessons.md membership audit)

Per the 2026-08-13 lesson, all membership/ownership reads on the mock path
were enumerated: `_mock_owner_ids` (`server.py:11880` — caller-excluded
`sess["league"].members` **plus** the caller appended under `_league_user_id`),
`_mock_rosters` (`server.py:11905`), `_mock_personas` (`server.py:12151`,
reads `g_league.members`; the caller's persona comes from the
`owners ∪ resolved_order` default union — fine), `_mock_real_draft`
(`server.py:12105-12109` platform read), and the new `load_draft_picks` read.

Rules for the new overlay code:

- **Anchor to `resolved_order`, never to raw `members`** — `resolved_order`
  includes the caller; raw members do not.
- **Drop any row whose `original_user_id` or `owner_user_id` is not in
  `resolved_order`**, counting drops. MFL rows key owners as the linking
  user's real id + synthetic `mfl:<league>.f<fid>` ids (`_mfl_member_id`
  `server.py:21943`) — the same scheme session members carry, but a co-owner
  session or a stale membership could mismatch; a dropped row must degrade
  ownership honesty, not crash or misassign.
- **If every traded row dropped, report the fallback label** — silent partial
  application of a fully-dropped overlay is the bug class this item is about.
  Partial drops apply what matched and are logged (count in the server log,
  not the payload).

### 3.5 Manual mode

No manual-mode-specific work: `owner_of` reads `settings["ownership"]` before
slot order in both modes; manual mode differs only in `next_pick`'s `is_user`
(INV-7). The PRD's acceptance tests still cover both modes explicitly (§8) —
in manual mode a traded slot shows the *acquiring* team on the clock (the
"picking for" chip), which is the visible half of this fix.

## 4. Honest-fallback spec

The current silent "all picks at your slot" is what produced this report.
Fallback stays (it is the only possible behavior for Fleaflicker, unlinked
MFL, unseeded ESPN, dropped overlays) but becomes **labeled**:

- **New settings key `ownership_source`**, persisted in the mock's `settings`
  JSON and resolved in `build_settings` from a new parameter:
  - `'platform'` — overlay from platform-stated ownership (Sleeper board,
    MFL store) was applied;
  - `'user'` — overlay from the ESPN manual assignment grid was applied;
  - `'none'` — no ownership data applied; every team drafts its own slot.
  Resolution honesty mirrors the order rules: if the overlay is dropped
  (partial order, identity drop-all, empty store), the label degrades to
  `'none'` **in the same place the overlay is dropped**. A league with
  genuinely zero traded picks still labels `'platform'`/`'user'` — the data
  was consulted and applied; "no trades" is a fact, not a fallback.
- **Echoed in `settings_echo.ownership_source`**
  (`mock_draft_service.state_payload`, alongside `order_source` at
  `mock_draft_service.py:1418`). Nullable: rows persisted before this change
  echo `null` (same read-time convention as #305's pre-mode rows) — clients
  treat absent/null as "unknown", not `'none'`.
- **Server-side the vocabulary is closed** (validated like `order_source` at
  `mock_draft_service.py:509-511`); **client-side it is read as an open set**.
- **Mobile disclosure (the UI half the operator required):**
  `mobile/src/api/mockDraft.ts` adds
  `MockOwnershipSource = 'platform' | 'user' | 'none' | (string & {})` and
  `settings_echo.ownership_source: MockOwnershipSource | null`.
  `MockDraftScreen.tsx` renders one Chalkline-compliant caption line in the
  header meta row (next to the existing `rounds · teams` line,
  `MockDraftScreen.tsx:825-826`):
  - `'platform'` / `'user'` → "Real pick ownership applied" (optionally
    "· entered by your league" for `'user'`);
  - `'none'` → "Traded picks unavailable — each team drafts its own slot";
  - `null` → render nothing (old rows).
  No emoji, no new component; flare-informational styling per the design
  system. *Note:* the batch plan lists G3 as backend-only — this one caption
  is the minimal mobile delta the operator's "labeled in the payload/UI"
  decision requires; flagged for the orchestrator to amend the platforms
  column (backend + mobile-caption).

## 5. API contract changes (Feature path — for the Author-round HLD/LLD deltas)

1. `GET/POST /api/mock-draft` state payload: `settings_echo` gains
   `ownership_source` (`'platform' | 'user' | 'none'`, nullable). Additive;
   no existing field changes shape. → `docs/api-reference.md:528` block.
2. Persisted `mock_drafts.settings` JSON gains `"ownership_source"` (schema
   docs: `docs/data-dictionary.md` mock_drafts row comment — column itself
   unchanged, it's inside the settings JSON per `database.py:1851`).
3. `mock_draft_service.build_settings` signature gains
   `ownership_source: str = OWNERSHIP_SOURCE_NONE` (internal contract; LLD
   delta).
4. Capability probe payload: **unchanged** (it deliberately omits
   board-derived fields; `ownership_source` needs the board/store, same
   reasoning as `type`/`order_source` — `server.py:12040-12050` comment).
5. New enum strings shared across clients ⇒ one new row in
   `docs/cross-client-invariants.md` (`ownership_source` vocabulary).
6. No route additions/renames; no feature-flag surface changes (`picks.assign`
   and `draft.room` are consulted, not redefined). **Bright-line note:** this
   touches an API payload contract — full gates, no express.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Identity mismatch between `draft_picks` owner ids and session member ids (MFL synthetic ids, co-owner sessions) silently mis-assigns picks | §3.4 guard: drop unknown-id rows, log counts, degrade label to `'none'` on drop-all; pytest covers a synthetic-id fixture and a co-owner id miss |
| ESPN grid changed after mock creation (reassignment mid-mock) | Non-risk by design: ownership is snapshotted at create (`owner_of` docstring, `mock_draft_service.py:973-976`); a resync never shifts an in-flight mock |
| Contested/orphaned ESPN slots leak into the mock | `load_draft_picks`/grid row filter already excludes them by default (`database.py:8516-8526`); assert in tests, don't re-implement |
| Mock `rounds` exceeds grid/store rounds (e.g. mock 4 rounds, ESPN grid 3) | Overlay covers only rounds it has rows for; deeper rounds default to slot order. Acceptable and disclosed by the label; documented in the PRD |
| Sharing the board-route grid construction with `_mock_real_draft` drifts the two call sites | Extract one helper used by both (the board route's ESPN branch at `server.py:11783` and the mock); structural test pins both call through it |
| `_mock_real_draft` stale-comment removal changes Sleeper behavior accidentally | Sleeper path byte-identical except label; regression pytest re-runs the existing W2d/G1 order/overlay tests unchanged |
| Old persisted mocks break on the new settings key | Read-time nullable echo (§4); T-305-05-style byte-compat test for pre-existing rows |

## 7. File ownership (build round, one agent — no parallel split needed)

| File | Change |
|---|---|
| `backend/server.py` | `_mock_real_draft` guard + ESPN branch; new `_mock_owned_pick_overlay`; shared grid-construction helper; label plumb-through to `build_settings` |
| `backend/mock_draft_service.py` | `OWNERSHIP_SOURCE_*` constants; `build_settings` param + settings key; `state_payload` echo |
| `backend/tests/test_mock_draft.py` (+ new `backend/tests/test_mock_pick_ownership.py` if size warrants) | §8 tests |
| `mobile/src/api/mockDraft.ts` | `MockOwnershipSource` type + `settings_echo` field |
| `mobile/src/screens/MockDraftScreen.tsx` | one disclosure caption |
| `docs/api-reference.md` | mock-draft payload block (:528) |
| `docs/cross-client-invariants.md` | `ownership_source` vocabulary row |
| `docs/data-dictionary.md` | `mock_drafts.settings` JSON note |
| `docs/feedback/items/328-mock-draft-pick-assignment/` | prd.md / hld-lld deltas / status.md (Author round) |
| `living-memory/` | CHANGELOG entry; LLD.md convention note (create-time resolution owns ownership honesty) |

## 8. Test-plan sketch (D-056: Maestro retired — pytest + structural checks + operator TestFlight checklist)

**pytest** (every behavioral test proven-to-fail on a sabotaged build per the
2026-08-10 rule — sabotage = re-adding the `server.py:12110` early return):

1. ESPN create (seeded grid fixture, one traded round-2 pick): mock order ==
   stored round-1 order; the acquiring team is on the clock at the traded
   `(round, slot)`; `settings_echo.ownership_source == 'user'`;
   `order_source == 'assigned'`.
2. Same, **manual mode**: `next_pick` at the traded slot shows the acquiring
   team's id with `is_user: true` (picking-for), proving both modes.
3. MFL create (store rows with synthetic ids, randomized order): overlay
   lands relative to the original owner's shuffled slot;
   `ownership_source == 'platform'`, `order_source == 'randomized'`.
4. MFL row with an owner id not in the resolved order → row dropped; drop-all
   → `ownership_source == 'none'` (two-sided: a matching row set must NOT
   yield `'none'`).
5. ESPN unseeded / `picks.assign` off → fallback, `'none'`, no crash, no
   platform egress.
6. Fleaflicker/unknown platform → `'none'` (the labeled version of today).
7. Sleeper regression: existing W2d/G1 tests pass unchanged; label `'platform'`
   when overlay applied.
8. Pre-existing persisted row (no `ownership_source` key) → echo `null`,
   payload otherwise byte-identical (T-305-05 style).
9. League with zero traded picks (data present) → label stays
   `'platform'`/`'user'`, not `'none'` (two-sided honesty).

**Structural checks:** `tsc` for mobile; a small `mobile/tests/check-*.js`
AST pin: MockDraftScreen's caption reads only
`settings_echo.ownership_source`; backend grep-pin that the board-route ESPN
branch and `_mock_real_draft` share the one grid helper.

**Operator TestFlight checklist (the runtime net):**

1. **Newton (ESPN)** — assign picks in PickAssignment incl. at least one
   trade; start an auto mock: your on-the-clock picks match the grid, caption
   reads "Real pick ownership applied". Repeat in manual mode.
2. Newton — the exact #328 repro: confirm you do NOT get all four picks at
   one slot when your real picks differ.
3. **MFL league** — start a mock: traded picks reflected, order labeled
   randomized, caption present.
4. **Sleeper (ffv3)** — regression: mock behaves exactly as on 1.13.4.
5. Any league with no pick data — caption reads "Traded picks unavailable —
   each team drafts its own slot".
