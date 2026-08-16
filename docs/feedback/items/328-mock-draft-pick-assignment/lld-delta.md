# FB-328 — LLD delta: exact interfaces

> Author-round deliverable for group **G3** (2026-08-16 wave). Every file:line
> is against `origin/main` @ `d3fe3ac`. Functions marked **NEW** do not exist
> on that sha; everything else was verified to exist at the cited line.
> Companion docs: [`hld-delta.md`](hld-delta.md), [`prd.md`](prd.md).
> Two build agents must be able to produce compatible code from this file
> alone — where behavior is subtle, the rule is stated, not implied.

## 1. `backend/mock_draft_service.py`

### 1.1 Constants (NEW) — beside `ORDER_SOURCE_*` at `:67-68`

```python
OWNERSHIP_SOURCE_PLATFORM = "platform"   # overlay from platform-stated ownership (Sleeper board / MFL store), covering every slot of this mock
OWNERSHIP_SOURCE_USER = "user"           # overlay from the ESPN manual assignment grid (user-asserted), covering every slot of this mock
OWNERSHIP_SOURCE_PARTIAL = "partial"     # ownership data applied, but NOT covering every slot (rounds beyond grid/store depth, contested/orphaned exclusions, identity-dropped rows); uncovered slots use slot order
OWNERSHIP_SOURCE_NONE = "none"           # no ownership data applied; every team drafts its own slot
```

`OWNERSHIP_SOURCE_PARTIAL` exists because two real cases produce a mock that
is only partly real (review round 1, OBJ-2): contested/orphaned ESPN slots at
round ≥ 2 are grid-excluded and silently revert to slot order, and a mock
whose `rounds` exceeds grid/store depth drafts the deeper rounds at slot
order. A full-coverage label over either would be a smaller #328; degrading
the whole mock to `"none"` would throw away the real data we do hold. The
label tells the truth instead: applied, but not everywhere.

### 1.2 `build_settings` (`:995-1009`) — one new keyword parameter

Insert after `order_source` (`:1002`), before `mode`:

```python
                   order_source: str = ORDER_SOURCE_RANDOMIZED,
                   ownership_source: str = OWNERSHIP_SOURCE_NONE,   # NEW
                   mode: str = MODE_CPU,
```

Two behavior rules, both inside `build_settings`:

1. **Degrade with the overlay.** In the existing §14-2 short-order branch
   (`:1049-1056`, `order = None; traded_slots = None`) add
   `ownership_source = OWNERSHIP_SOURCE_NONE` — the label degrades **at the
   same point** the overlay is dropped. No other degrade point exists inside
   the engine; all other degrades happen in the server resolvers (§2).
2. **Closed-vocabulary coercion** in the returned dict, mirroring `mode`'s
   idiom at `:1093`. Add to the settings dict (directly under the existing
   `"order_source": resolved_source` entry):

```python
        "ownership_source": (ownership_source
                             if ownership_source in (OWNERSHIP_SOURCE_PLATFORM,
                                                     OWNERSHIP_SOURCE_USER,
                                                     OWNERSHIP_SOURCE_PARTIAL,
                                                     OWNERSHIP_SOURCE_NONE)
                             else OWNERSHIP_SOURCE_NONE),
```

The explicit `ownership` parameter (persisted/replay shape, `:1004`) does
**not** affect the label: `ownership_source` describes create-time provenance
and is snapshotted like everything else in settings.

### 1.3 `state_payload` — `settings_echo` (`:1414` block)

Cite convention (harmonized with G2's PRD §3 boundary table, which is
authoritative for the shared-file regions): the `settings_echo` dict literal
opens at `:1414`; the new echo line lands directly under `order_source`
(`:1418`).

Add one line directly under `"order_source": settings.get("order_source"),`:

```python
            "ownership_source": settings.get("ownership_source"),
```

`dict.get` is the whole back-compat story: rows persisted before this change
have no key and echo `null` (same read-time convention as #305 pre-mode rows).
No write-time migration, no backfill.

### 1.4 Explicitly unchanged

`owner_of` (`:970`), `pick_slots`, `next_pick`/INV-7, the traded-slot
translation (`:1074-1082`), `capability()` (`:483-513` — the probe payload
gains **nothing**; see hld-delta HD-6), `new_state`, `dumps`/`loads`, all
noise/CPU logic.

## 2. `backend/server.py`

### 2.1 `_mock_platform(sess, league_id)` (NEW) — extract the platform sniff

The 5 lines currently inside `_mock_real_draft` (`:12106-12109`), needed by
two call sites (`_mock_real_draft` and the create route's MFL step):

```python
def _mock_platform(sess: dict, league_id: str) -> str:
    g_league = sess.get("league")
    platform = str(getattr(g_league, "platform", "sleeper") or "sleeper").lower()
    ctx = get_league_draft_context(league_id)
    if ctx:
        platform = str(ctx.get("platform") or platform).lower()
    return platform
```

### 2.2 `_mock_real_draft` (`:12084-12150`) — restructured guard + ESPN branch

Signature gains the mock's clamped `rounds` (parsed by the route at
`:12281-12288`, i.e. **before** the existing call site at `:12318`):
`_mock_real_draft(sess, league_id, season, rounds)` — needed by the coverage
check below; single caller updates in place. Return contract grows one key.
New shape:

```python
{"order": list[str] | None,          # unchanged
 "order_source": str,                # unchanged ("assigned" | "randomized")
 "traded_slots": dict[tuple[int, int], str],   # unchanged
 "type": str | None,                 # unchanged ("linear" | "snake" | None)
 "ownership_source": str}            # NEW — OWNERSHIP_SOURCE_* value
```

Structure (the Sleeper board path `:12119-12134` and the row-reading loop
`:12135-12149` are reused **verbatim** — only the guard, the branch that
produces `board`, and the final labeling change):

```python
    out = {"order": None, "order_source": mds.ORDER_SOURCE_RANDOMIZED,
           "traded_slots": {}, "type": None,
           "ownership_source": mds.OWNERSHIP_SOURCE_NONE}
    platform = _mock_platform(sess, league_id)

    if platform == dbs.SLEEPER and is_enabled("draft.room"):
        # UNCHANGED: _get_universal_pool + dbs.build_board exactly as :12119-:12134
        board = dbs.build_board(…)
    elif platform == dbs.ESPN and is_enabled("picks.assign"):
        # NEW — the same board the ESPN Draft Room renders (route parity:
        # the gate matches the board route's ESPN branch at :11763).
        # fetchers/recorded defaults: no undrafted list is needed, and
        # recorded picks affect state, never order/order_confidence.
        board = dbs.assigned_board(
            dbs.BoardRequest(league_id=str(league_id), platform=dbs.ESPN,
                             season=int(season), user_id=sess.get("user_id")),
            grid=_assignment_grid(str(league_id), int(season)))
    else:
        return out          # honest empty — Fleaflicker, MFL (order half),
                            # flag-off; ownership_source stays "none".
                            # (Stale MFL comment at :12111-:12114 deleted.)

    out["type"] = board.get("type")
    # UNCHANGED row-reading loop :12135-:12149 (rows, ORDER_ASSIGNED check,
    # round-1 by_slot, is_traded → traded_slots, partial-map drop).
    if out["order"] is not None:
        source = (mds.OWNERSHIP_SOURCE_PLATFORM if platform == dbs.SLEEPER
                  else mds.OWNERSHIP_SOURCE_USER)
        # Coverage check (OBJ-2): the source label promises EVERY slot of
        # THIS mock has known ownership provenance. Board rows exist for
        # every (round, slot) the platform/grid states — contested/orphaned
        # exclusions and rounds beyond grid/board depth are the holes.
        teams = len(out["order"])
        covered = {(int(r.get("round") or 0), int(r["slot"]))
                   for r in rows if r.get("slot")}
        expected = {(rnd, s) for rnd in range(1, int(rounds) + 1)
                    for s in range(1, teams + 1)}
        out["ownership_source"] = (source if expected <= covered
                                   else mds.OWNERSHIP_SOURCE_PARTIAL)
    return out
```

Labeling rule (two-sided, pinned by T-5/T-9/T-12): with the order resolved
(`out["order"] is not None`), the label is `platform`/`user` when the board's
rows cover every `(round, slot)` of the mock, `"partial"` when any hole
exists — a round-≥2 contested/orphaned ESPN slot (grid-excluded at
`server.py:11219-11221`) or mock `rounds` deeper than the grid/board. An
order that resolved with zero *traded* rows but full coverage is still
"data consulted, applied, no trades" → source label. Every full-drop path
(non-assigned confidence, partial **round-1** slot map, unseeded grid →
`assigned_board`'s `_render_unavailable` with `order_confidence: "unknown"`
at `draft_board_service.py:1399-1401`/`:1490`) leaves `"none"` without any
new code — the `ORDER_ASSIGNED` check already rejects them. (Asymmetry,
stated on purpose: a round-**1** hole breaks `by_slot` completeness and
honestly drops the whole resolution to `"none"`; a round-≥2 hole keeps the
order and labels `"partial"`.)

Notes for the builder:
- `_assignment_grid` (`:11208-11245`) already exists and is already the board
  route's helper — call it, do not duplicate or re-extract it. It reads
  `load_draft_picks(league_id, source=PICK_SOURCE_USER)` (contested/orphaned
  rows excluded in `load_draft_picks` at `database.py:8516-8526`) and
  `_assignment_settings` (`:10988`, membership-padded order).
- Coverage-check soundness: the Sleeper assigned path emits an `order[]`
  entry for **every** `(round, slot)` of the real draft
  (`draft_board_service.py:826-829`) and the ESPN `assigned_board` one per
  grid slot, so `expected <= covered` is a true full-coverage test on both.
  `_cap_order`'s 500-entry truncation (`draft_board_service.py:172,904-909`)
  cannot bite a rookie mock (≤ 8 rounds, clamped at the route).
- `assigned_board` (`draft_board_service.py:1372-1453`) with `fetchers=None`
  skips `_undrafted` and sets `notice: class_not_loaded` — the mock reads
  only `type` / `order` / `order_confidence`, so that is irrelevant. Zero
  platform egress: no `sleeper_get` exists anywhere on this path.
- The ESPN board's `type` is the grid's linear/snake `order_type` (emitted by
  `_payload` at `draft_board_service.py:1290`), so the create's existing
  `draft_type=body.get("type") or real["type"]` (`:12325`) now prefills the
  assignment tool's numbering shape for ESPN. Intended; test T-1 asserts it.

### 2.3 `_mock_owned_pick_overlay(league_id, season, rounds, resolved_order)` (NEW)

Sibling of `_mock_real_draft`. MFL only (by construction: rows in the
normalized store with platform ownership provenance).

```python
def _mock_owned_pick_overlay(league_id: str, season: int, rounds: int,
                             resolved_order: Sequence[str],
                             ) -> tuple[dict[tuple[int, int], str], str]:
    """(traded_slots, ownership_source) from the normalized draft_picks store.

    Anchored to the ORIGINAL owner's slot in `resolved_order`, wherever the
    shuffle put them — ownership is a fact about the original owner, not a
    slot number. Identity guard per the 2026-08-13 membership audit: rows
    whose ids are unknown to `resolved_order` are dropped and counted; a
    fully-dropped overlay reports "none", a partial drop applies what matched,
    logs the count (server log only, never the payload) and labels "partial".
    """
```

Exact behavior (deterministic; no rng, no egress):

1. `rows = load_draft_picks(str(league_id))` — the **default**
   `source=PICK_SOURCE_PLATFORM` read (`database.py:8474-8478`); MFL sync
   rows carry NULL `source`, which reads as platform. Never pass
   `source="any"` — user-asserted rows are ESPN's path, not this one.
2. `season_rows = [r for r in rows if int(r.get("season") or 0) == int(season)
   and 1 <= int(r.get("round") or 0) <= int(rounds)]`.
   Row keys per `_sync_mfl_owned_picks` (`server.py:9598-9612`): `season`,
   `round`, `owner_user_id`, `original_user_id`, `original_roster_id`,
   `is_traded` (int 0/1).
3. `if not season_rows: return {}, mds.OWNERSHIP_SOURCE_NONE` — no data for
   this season/rounds is a fallback, not a fact. (#228/#207 inheritance: a
   drafted current season has no rows because `_sync_mfl_owned_picks`'s
   verdict-gated exclusion removed them ⇒ honest `"none"`.)
4. Coverage census (OBJ-2): MFL's `futureDraftPicks` export enumerates every
   pick (traded or not), one row per franchise per round, so
   `complete = all(sum(1 for r in season_rows if int(r["round"]) == rnd)
   >= len(resolved_order) for rnd in range(1, int(rounds) + 1))`. A shallow
   store (mock `rounds` deeper than the export) fails the census.
5. `traded = [r for r in season_rows if r.get("is_traded")]`. Identity
   guard on `traded`: `known = {str(u) for u in resolved_order}`;
   `slot_of = {str(u): i + 1 for i, u in enumerate(resolved_order)}`; keep a
   row iff `str(original_user_id)` and `str(owner_user_id)` are both
   non-empty and in `known`; count drops.
6. `if traded and not kept: log.warning(...); return {}, OWNERSHIP_SOURCE_NONE`
   — drop-**all** degrades the label (test T-4). Partial drops:
   `log.warning("mock overlay: dropped %d/%d traded rows for %s", …)` and
   proceed with the kept rows.
7. `overlay = {(int(r["round"]), slot_of[str(r["original_user_id"])]):
   str(r["owner_user_id"]) for r in kept}` — last-write-wins on a duplicate
   `(round, slot)` key is acceptable (the store's `pick_id` uniqueness makes
   duplicates a data error, not a normal state).
8. Label: `OWNERSHIP_SOURCE_PLATFORM` iff `complete and drops == 0`, else
   `OWNERSHIP_SOURCE_PARTIAL`. Zero traded rows with a complete census is
   still `"platform"` — "no trades" is a fact (test T-9); zero traded rows
   over a shallow census is `"partial"` (test T-12).
9. Return `(overlay, label)`.

### 2.4 Create route (`POST /api/mock-draft`, `:12309-12331`) — MFL step + plumb-through

After the `rng_seed` parse (`:12309-12313`) and the existing
`real = _mock_real_draft(sess, league_id, season)` (`:12318`), replace the
inline `rng=random.Random(rng_seed)` (`:12327`) with a named instance and add
the MFL step:

```python
    real = _mock_real_draft(sess, league_id, season, rounds)
    rng = random.Random(rng_seed)
    if real["order"] is None and _mock_platform(sess, league_id) == dbs.MFL:
        # MFL states ownership but no slot sequence (KD-6: never invent an
        # order). Resolve the same seeded shuffle build_settings would have
        # produced, THEN anchor the overlay to it — build_settings will see
        # an explicit order and not reshuffle.
        shuffled = [str(o) for o in owners]     # exactly build_settings' copy rule (:1044)
        rng.shuffle(shuffled)                   # first rng use, = the internal shuffle (:1062)
        overlay, own_src = _mock_owned_pick_overlay(league_id, season,
                                                    rounds, shuffled)
        real.update(order=shuffled, traded_slots=overlay,
                    ownership_source=own_src)
        # order_source stays ORDER_SOURCE_RANDOMIZED — the shuffle is ours.
    try:
        settings = mds.build_settings(
            ctx, owners=owners, user_owner_id=league_user_id, rounds=rounds,
            draft_type=body.get("type") or real["type"],
            order=real["order"], order_source=real["order_source"],
            traded_slots=real["traded_slots"],
            ownership_source=real["ownership_source"],       # NEW
            personas=_mock_personas(league_id, sess),
            mode=mode,
            rng=rng)
```

Determinism note (binding): the pre-shuffle consumes the rng's first draw with
the identical list-copy recipe `build_settings` uses (`[str(o) for o in
owners]` then `shuffle`), so for a given `rng_seed` an MFL mock's order is the
same permutation the internal shuffle produced on 1.13.4. `rng` is used for
nothing else on either path. Test T-3 pins seed→order determinism; the
Sleeper/ESPN paths never enter this block.

`real["order"]` non-None (Sleeper/ESPN resolved): the block is skipped and
`ownership_source` rides through from `_mock_real_draft`. All other platforms
(Fleaflicker, unlinked/flag-off): block skipped or overlay empty, label
`"none"`.

### 2.5 Where ESPN manual-assignment data is read from (summary)

`_mock_real_draft` ESPN branch → `_assignment_grid` (`server.py:11208`) →
`load_draft_picks(league_id, source=PICK_SOURCE_USER)` (`database.py:8474`,
rows written by `seed_pick_grid` `database.py:8528` / `assign_draft_pick`
`database.py:8700`) + `_assignment_settings` (`server.py:10988`, stored JSON
`leagues.pick_assignment_settings` `database.py:285` via
`load_pick_assignment_settings` `database.py:8669`) → `dbs.assigned_board`
(`draft_board_service.py:1372`). The mock never reads the stored JSON or
`draft_picks` directly for ESPN — board parity with `PickAssignmentScreen` is
the point (hld-delta HD-2).

## 3. API contract

### 3.1 `GET`/`POST /api/mock-draft` state payload (additive)

`settings_echo` gains one nullable field. Full echo after the change:

```json
"settings_echo": {
  "rounds": 4,
  "type": "linear",
  "teams": 12,
  "order_source": "assigned",
  "ownership_source": "user",
  "personas": {"…": {"outlook": "compete", "source": "declared"}},
  "noise": {"bpa_prob": 0.62, "reach_decay": 0.55, "max_reach": 24},
  "consensus_pool_size": 79,
  "mode": "cpu",
  "user_owner_id": "9725…"
}
```

- `ownership_source`: `"platform" | "user" | "partial" | "none" | null`
  (string, nullable). `"partial"` = ownership data was applied but does not
  cover every slot of this mock; uncovered slots draft at slot order. `null`
  ⇔ the mock row was persisted before this change — clients treat
  absent/`null` as *unknown*, never as `"none"`.
- Rides every state payload (`POST` create, `GET` active/recap, `/pick`
  responses) because all serialize via `state_payload`. No other field
  changes shape or order of nullability.

### 3.2 Unchanged surfaces (asserted, not implied)

- Capability probe (`GET` typed-empty `capability`): byte-identical.
- `POST /api/mock-draft` request body: unchanged (no new inputs; provenance
  is resolved, never client-asserted).
- `/pick`, `/abandon` requests: unchanged.
- Error shapes: unchanged — no new error codes; an ESPN/MFL resolution
  failure is a degrade to `"none"`, never a 4xx/5xx.
- Persisted `mock_drafts` columns: unchanged (`settings` is already JSON,
  `database.py:1851`); the JSON gains the `"ownership_source"` key on new
  rows only.

## 4. Mobile client

### 4.1 `mobile/src/api/mockDraft.ts`

Next to `MockOrderSource` (`:30`):

```ts
/** #328 — provenance of the traded-pick ownership overlay. OPEN set on the
 *  client (server may grow it); `null` = row predates the field (unknown,
 *  NOT "none"). `partial` = applied but not covering every slot. */
export type MockOwnershipSource =
  'platform' | 'user' | 'partial' | 'none' | (string & {});
```

In `MockSettingsEcho` (`:88-104`), directly under `order_source` (`:92`):

```ts
  ownership_source: MockOwnershipSource | null;
```

`MockCapability` (`:110-119`): unchanged.

### 4.2 `mobile/src/screens/MockDraftScreen.tsx` — one caption, two mounts

One module-level helper (pure, exported for the structural check):

```ts
export function ownershipCaption(src: MockOwnershipSource | null | undefined): string | null {
  if (src === 'platform') return 'Real pick ownership applied';
  if (src === 'user') return 'Real pick ownership applied · entered by your league';
  if (src === 'partial') return 'Some real pick ownership applied — other slots use draft order';
  if (src === 'none') return 'Traded picks unavailable — each team drafts its own slot';
  return null; // null / undefined / unknown future value → render nothing
}
```

(`partial` deliberately drops the platform-vs-user provenance suffix — one
caption for one fact. Documented tradeoff: a partial mock's label carries no
provenance distinction anywhere, including analytics; if the fallback-rate
query ever needs it, that is a future vocabulary growth, which is why the
client set is open.)

Mount A — active draft, inside the on-the-clock card, directly under the
`clockMeta` line (`:697-700`):

```tsx
{ownershipCaption(ownershipSource) ? (
  <Text testID="mock-draft.ownership-caption" style={styles.clockHow}>
    {ownershipCaption(ownershipSource)}
  </Text>
) : null}
```

where `ownershipSource` = `state.settings_echo?.ownership_source ?? null` is
threaded to the clock-card component as a prop (the component at `:672` takes
props, not state).

Mount B — recap card, directly under its meta line (`:824-827`), same helper,
testID `mock-draft.recap.ownership-caption`. The two mounts never co-render
(`status` active vs complete).

Styling: reuse the existing `styles.clockHow` token style (already mounted in
this card at `:704`/`:710`) — Chalkline-compliant, no new component, no
emoji, no new color. The caption is plain informational text; flare stays
reserved for the user's own turn per the approved frame at `:682-683`.

**Placement correction vs plan §4:** the plan's cited "header meta row"
(`MockDraftScreen.tsx:825-826`) is the **recap** card's meta line; the active
draft's meta line is `:697`. Disclosure matters most *during* the draft, so
this delta mounts in both cards rather than recap-only.

### 4.3 Client state

None beyond the prop thread-through: no new store, no new query key, no
persistence. The caption is a pure render of `settings_echo`.

## 5. Analytics

`mock_started` gains one property, read off the server's **resolved**
`settings_echo` like the existing five (never the request):

- Emission: `mobile/src/screens/DraftRoomScreen.tsx:315-326` — add
  `ownership_source: res.settings_echo?.ownership_source ?? null,` under
  `order_source`.
- Taxonomy: `backend/analytics_taxonomy.py:855-856` — the `mock_started`
  frozenset gains `"ownership_source"`.
- Structural pin: `mobile/tests/check-mock-draft-modes.js:617-627` currently
  pins "all five" `mock_started` props off `res.settings_echo` — extend the
  pinned list to six.

No new event; `mock_pick_made` / `mock_completed` / `mock_abandoned` /
`mock_create_refused` unchanged.

## 6. DB changes

None. No table, column, index, or migration. The only persisted delta is one
new key inside the existing `mock_drafts.settings` JSON blob
(`database.py:1851`), documented in `docs/data-dictionary.md:1179`'s key list.

## 7. Structural checks (D-056 evidence layer)

- **NEW `mobile/tests/check-mock-ownership-caption.js`:** pins (a) the
  caption text function reads only `settings_echo.ownership_source`; (b) the
  four known strings and the render-nothing default; (c) both testIDs
  mounted; (d) `MockSettingsEcho` carries `ownership_source`.
- **Extend `mobile/tests/check-mock-draft-modes.js`:** the `mock_started`
  props pin (`:617-627`) grows to include `ownership_source`.
- **NEW backend structural pin** (in the G3 pytest file): both
  `server.py` call sites of `_assignment_grid` exist — the board route's ESPN
  branch and `_mock_real_draft` — via source inspection (`inspect.getsource`
  grep), so the two surfaces cannot silently fork grid construction.
- `mobile/scripts/testid-lint.sh` must pass with the two new testIDs.
