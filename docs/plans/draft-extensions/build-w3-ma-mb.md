# Build status — W3 M-A (backend half) + M-B · ESPN pick assignment

**Date:** 2026-08-08 · **Status:** landed dark behind `picks.assign` · **Scope:** backend only
**Sources (binding):** [plan.md §6 REVISED](plan.md) + the operator-decision block · [lld.md §W3](lld.md) · [hld.md](hld.md) · [ADR-010](../../adr/adr-010-user-asserted-pick-ownership.md)

> **This file is the delivered contract.** Where it and the LLD disagree, **this file is what shipped** — §7 lists every deviation and why.

---

## 1. What landed

| Milestone | What | Where |
|---|---|---|
| **M-A** | The assignment store: three additive `draft_picks` provenance columns, the `leagues.pick_assignment_settings` numbering blob, an explicit `league_id, source` index, `make_pick_id`, `seed_pick_grid`, `assign_draft_pick` (CAS), contested/orphaned derivation | `backend/database.py` |
| **M-A** | Three routes + the payload helpers | `backend/server.py` |
| **M-B** | `assigned_board` + `AssignmentGrid` + `NOTICE_PICKS_NOT_ASSIGNED` | `backend/draft_board_service.py` |
| **M-B** | The one-branch route wiring in `draft_board_route` | `backend/server.py` |
| — | Flag `picks.assign` (4-touch, lands **OFF**) | `backend/feature_flags.py`, `config/features.json`, `backend/tests/fixtures/flags/release.json`, `docs/config-reference.md` |
| — | `pick_assignment_changed` in `SERVER_FIRED_EVENTS` (**not** in `ALLOWED_CLIENT_EVENTS`) | `backend/analytics_taxonomy.py` |

**Not in scope and NOT built:** M-C (`picks.assign_tradeable` — the seven read sites opting in) and M-D (`draft.manual_picks` / `recorded_picks`). All seven read sites still take `load_draft_picks`' platform-only default, so asserted picks reach **no** trade math, **no** power rankings and **no** suggestions today. `picks.assign_tradeable` does not exist as a flag yet — do not reference it from a client.

---

## 2. Routes — the exact delivered contract

All three: 404 `feature_disabled` **before any session work** while `picks.assign` is off · `_gate_unverified_read` / `_gate_unverified_write` · `_require_initialized_session` (401 / 409) · actor = the session user, **a body `user_id` is ignored** · league membership asserted against `league_members` (403 `not_in_league`).

**Any body carrying `value`, `pool_value`, `pick_value`, `elo`, `price` or `values` → `400 {"error":"values_not_accepted"}`.** Checked before the session is even resolved. There is no path from a request to a price.

### 2.1 `GET /api/league/pick-assignments?league_id=&season=`

`league_id` defaults to the session league. `season` is accepted and currently unused — the payload always carries **all four seasons**; the client picks.

```jsonc
{
  "league_id": "1099887766554433221",
  "settings": { "rounds": 4, "order_type": "linear", "order": ["u1","u2","u3","u4"] },
  "seasons": [
    { "season": 2026,
      "slots": [
        { "pick_id": "1099887766554433221_2026_1_3",
          "season": 2026,
          "round": 1,
          "slot": 3,                     // position in settings.order; null if the
                                         // original owner is no longer a member
          "original_roster_id": "3",     // OPAQUE league-local label. Never a platform id.
          "original_user_id": "u3",
          "original_username": "Team u3",
          "owner_user_id": "u7",
          "owner_username": "Team u7",
          "is_traded": true,
          "source": "user",
          "assigned_by": "u7",
          "assigned_at": "2026-08-08T18:03:11.204+00:00",   // ALSO THE CAS TOKEN
          "contested": false,
          "orphaned": false }
      ] }
    // …2027, 2028, 2029
  ],
  "progress": { "assigned": 192, "total": 192, "traded": 3,
                "contested": 0, "orphaned": 0 },
  "seeded": true
}
```

- `seasons[]` is **always current + 3**, ascending. ~192 slots ≈ 40 KB — one round-trip beats four, so it never paginates. **The client defaults to the current season and collapses the other three**, and the confirm-the-board review step is **per season**, never one 192-row scroll.
- `assigned_at` is `null` on a never-assigned row.
- **`contested` and `orphaned` slots ARE present here.** This is the one screen where they get fixed. They are withheld from every priced payload elsewhere.
- A never-seeded league returns `seasons: []`, `seeded: false`, `progress.assigned: 0` and the **default** settings (rounds 4, linear, members sorted by `user_id`) — render "Not assigned yet".

**Errors:** 404 `feature_disabled` · 400 `league_id is required` · 404 `league_not_found` · 403 `not_in_league`.

### 2.2 `PUT /api/league/pick-assignments/<pick_id>`

> ⚠️ **Per-slot path, not the LLD's body-`pick_id` PUT on the collection.** The `pick_id` rides the URL.

```jsonc
// request body
{ "league_id": "1099887766554433221",
  "owner_user_id": "u7",
  "if_assigned_at": "2026-08-08T18:03:11.204+00:00" }   // the value you READ; null/omit
                                                        // ONLY for a never-assigned row
```

| Outcome | Response |
|---|---|
| OK | `200 {"ok": true, "slot": <the updated slot object>, "progress": {…}}` |
| Unknown `pick_id` for this league | `404 {"error":"pick_not_found"}` |
| `owner_user_id` not a `league_members` row | `400 {"error":"owner_not_in_league"}` |
| Stale CAS token | `409 {"error":"stale_assignment", "current": <the WHOLE current slot object>}` |
| Row already assigned and `if_assigned_at` omitted | `409 {"error":"stale_assignment", "current": …}` — a blind overwrite is never allowed |
| Value field in the body | `400 {"error":"values_not_accepted"}` |

**The 409 carries the whole current row**, so the conflict UI ("Dana changed this 4 minutes ago — keep theirs, or use yours?") needs no second request: retry with `current.assigned_at`, or abandon. Two users editing **different** slots never collide — no locks, no roles, no approval.

Every `200` emits the server-fired `pick_assignment_changed` event. That trail is the audit log — see [runbook.md § Pick-assignment recovery](../../runbook.md).

### 2.3 `POST /api/league/pick-assignments/order`

The seeder **and** the numbering setter. All body fields optional except `league_id`.

```jsonc
{ "league_id": "…", "rounds": 4, "order_type": "linear",
  "order": ["u1","u2","u3","u4"], "reseed": false }
```

```jsonc
// 200
{ "ok": true, "seeded": 189, "reseeded_over": 0,
  "settings": { "rounds": 4, "order_type": "linear", "order": ["u1","…"] },
  "progress": { "assigned": 192, "total": 192, "traded": 3, "contested": 0, "orphaned": 0 } }
```

- **Idempotent.** Re-running **without** `reseed` preserves every edited slot verbatim. `reseed: true` resets ownership to pristine and reports `reseeded_over`.
- `rounds` default 4, **user-settable**, clamped `1..8` — outside that is `400 {"error":"rounds_out_of_range","max":8}`. The clamp also lives inside `seed_pick_grid`, so a caller that forgot it cannot widen the conservation bound.
- `order` must be a **permutation of the league's member ids** — otherwise `400 bad_order`. `order_type` ∈ `linear` (default) | `snake` — otherwise `400 bad_order_type`.
- **`order` and `order_type` change slot NUMBERING only, never ownership.** The toggle is safe to flip at any time and can never trigger a CAS conflict. A test pins this.

**The 48-tap problem, in the order the UI should lean on it:** (1) the pristine seed means a league with three trades leaves 189 of 192 slots untouched; (2) order is set **once**, a drag list of N teams plus the linear/snake toggle; (3) edit only the traded ones, which float into a "Traded picks" review summary. **Progress explicit, saves per slot, no giant dirty form.**

---

## 3. M-B — `GET /api/draft/board` for an ESPN league

No new route, no new fetch layer — a single branch inside `draft_board_route`, placed **before** the existing `platform_unsupported` return. `build_board` is untouched and unreachable for ESPN. **Zero platform egress in every state:** the fetchers carry no `sleeper_get`, so a stray platform read raises rather than going live.

| State | Condition | Payload |
|---|---|---|
| **B1** | `picks.assign` **OFF** | **Byte-identical** to today's `platform_unsupported`: `state:"unavailable"`, `notice.code:"platform_unsupported"`. Nothing changes for any existing binary. |
| **B2** | flag ON, nothing assigned | `state:"unavailable"` (**not** a new enum member), `kind:"unknown"`, `order_confidence:"unknown"`, `order:[]`, `picks:[]`, `notice.code:"picks_not_assigned"` |
| **B3** | flag ON, assignments present | `state:"upcoming"`, `kind:"rookie"`, `order_confidence:"assigned"`, `type:"linear"\|"snake"`, `order[]` from the grid, `picks: []`, the full rookie class in `undrafted[]`, `my_picks[]` sliced from `order[]`, `deep_link: null`, `stale: false` |

**Client contract:**

- **`notice.code = "picks_not_assigned"` is the ONLY new vocabulary.** `state`, `kind` and `order_confidence` gain **no member** — they stay closed enums a client may switch on exhaustively. `schema` stays `1`. An older binary renders `notice.message` through the existing fallback and behaves correctly.
- **B2 is an unconfigured state with a user-performable fix, NOT an error.** The operator called it an "error"; it is not. Never "Something went wrong". The server message is *"Nobody has set this league's draft picks yet. Assign them on the League tab to see the board."* The CTA routes to the M-A assignment screen.
- `picks[]` is **always** `[]` in M-B. An off-platform draft leaves no record we can read; only a future M-D could populate it. Do not render a "picks made" affordance off this payload.
- `deep_link` is **always** `null` for ESPN — there is no ESPN draft room to link to.
- `slot_value_approx: true` appears on a non-12-team ESPN board exactly as it does for Sleeper/MFL (the DP slot curve is a 12-team curve). A 12-team board carries no marker.

---

## 4. Storage — what a client should and should not assume

```
draft_picks:  + source       'platform' | 'user'   (NULL reads as platform)
              + assigned_by  FTF user_id of the last editor
              + assigned_at  ISO-8601 UTC — and the CAS token
leagues:      + pick_assignment_settings  JSON {rounds, order_type, order[]}
```

- **No backfill ran.** Every pre-W3 row has `source IS NULL`.
- **Ownership lives in `draft_picks`; NUMBERING lives in `pick_assignment_settings`.** Nothing else.
- `original_roster_id` is an **opaque, stable, league-local slot label**. `league_members` has no `roster_id` column, so it is never resolved against a platform. A member who already holds slots keeps them; a new member takes the next free integer.
- `pick_id = {league}_{season}_{round}_{original_roster}`, round **unpadded** — **not lexicographically sortable**. One constructor: `database.make_pick_id`.

---

## 5. Flag behaviour (`picks.assign`, ships **OFF**)

| Off | On |
|---|---|
| All three assignment routes 404 `feature_disabled` before any session work | The routes answer |
| ESPN board = byte-identical `platform_unsupported` | ESPN board = B2 or B3 |
| The three provenance columns stay unwritten | Written by the seeder / CAS write |
| Every read site unchanged (the `source='platform'` default) | **Still unchanged** — asserted picks reach no engine path under this flag |

`picks.assign` gates **entry, storage and the room**. Whether asserted picks enter **trade math** is a *separate, unbuilt* flag (`picks.assign_tradeable`), deliberately — so pick math can be killed without destroying the rows a league typed in.

---

## 6. Tests

`backend/tests/test_pick_assignment.py` (30) + a new W3 M-B block in `backend/tests/test_draft_board.py` (9).

| Criterion | Test |
|---|---|
| **D12** containment | `test_w3_02_ast_only_sanctioned_call_sites_name_source` (AST, the shipped `test_m3_07` pattern — enumerates every `load_draft_picks` site and pins the seven), `_02b` (no unsanctioned `replace_draft_picks`/`sync_draft_picks` caller), `_02c` (the signature default) |
| **D10 / INV-1** golden byte-identity | `test_w3_01_golden_byte_identity_on_every_read_site` — a FULL asserted grid in the DB, every read site byte-identical |
| **INV-2** | `test_w3_03_replace_draft_picks_never_crosses_provenance` |
| **D13** no user values | `test_w3_04_value_fields_are_refused_at_the_edge` (×4 fields × 2 routes), `test_w3_05_asserted_prices_are_the_shipped_function_in_both_modes` — **names `priced_pool_value` and runs under BOTH `tier_ladder` and `market_slots`** |
| **INV-4** conservation | `test_w3_06_conservation_bound_and_the_rounds_clamp`, `_06b` |
| **D14** pristine seed / orphans | `test_w3_07_pristine_seed_is_correct_and_idempotent`, `_07b` (platform-collision skip), `test_w3_08_orphaned_owners_…` |
| **INV-5** contested by row filter | `test_w3_34_contested_is_excluded_by_row_filter_not_by_nulling` — asserts the **naive nulling implementation demonstrably fails** |
| **D16** CAS / audit | `test_w3_09` / `_09b` / `_09c` / `_09d`, `test_w3_11_every_write_emits_the_audit_event`, `_11b` (taxonomy disjointness) |
| **INV-7** O9 | `test_w3_12_o9_survives_no_path_writes_the_draft_status_columns` (behavioral) |
| **INV-8** | `test_w3_10_pick_id_has_exactly_one_construction`, `_10b` |
| **D15** ESPN room | `test_w3_21` / `_22` / `_22b` / `_22c` / `_23` (zero egress) / `_24` (key set + closed enums) / `_25` (numbering ≠ ownership) / `_27` / `_20_and_26` |
| **D10** flag off | `test_w3_flag_off_404s_every_assignment_route`, `_flag_off_writes_nothing`, `test_w3_20_and_26_…` |

**Verify-failing-first.** Eight mutations were applied to the pre-change behaviour and each guard test confirmed **red** before being accepted: unscoped `replace_draft_picks` DELETE · `load_draft_picks` defaulting to `any` · an unsanctioned `source=` at `_roster_eveners` · value fields silently ignored · a non-shipped price in the seeder · nulling instead of row-filtering · no CAS predicate · the ESPN branch removed.

**Gate:** `python3 -m pytest backend/tests -q` → **1926 passed, 1 skipped, exit 0** (baseline 1887/1 skipped). `git status --porcelain -- mobile/` empty.

---

## 7. Deviations from the LLD (the corrections win, and here is every one)

| # | LLD said | Shipped | Why |
|---|---|---|---|
| 1 | `PUT /api/league/pick-assignments` with `pick_id` in the body | `PUT /api/league/pick-assignments/<pick_id>` | The task brief specifies the per-slot path; it also reads better as a resource. `pick_id` has no slashes, so it is a safe path segment. |
| 2 | `seed_pick_grid(member_user_ids)` — "index i ⇒ `original_roster_id` `str(i+1)`" | Slot labels are **established once and preserved**; new members take the next free integer | The literal version silently re-points every `pick_id`'s *original team* the moment membership or order changes — a silent ownership corruption, since `reseed=False` preserves edits **by `pick_id`**. |
| 3 | Nothing said where `settings` (rounds / order_type / order) is stored | New additive `leagues.pick_assignment_settings` TEXT/JSON | The payload requires them and neither is expressible in `draft_picks`. Same additive-nullable migration seam; keeps ownership and numbering in separate stores, which is what makes "the toggle never changes ownership" structural. |
| 4 | `_payload` and `_render_unavailable` "both emit the same 18 keys" | **Stale.** `_payload` carries `type` (added by W2d) and the conditional `slot_value_approx`; `_render_unavailable` carries neither | Verified at build time. RV-6 anticipated exactly this; the M-B key-set test pins the current reality. |
| 5 | Seeder collision with a platform row unaddressed | The seeder **skips** a slot the platform already owns (counted as `skipped`) | Found by this suite: `pick_id`'s unique key has **no provenance dimension**, so the LLD's seeder raised an `IntegrityError` (a 500) on any league holding platform rows. The platform wins; the slot is skipped, never overwritten. |
| 6 | Seeder writes only current members | Also **carries forward** existing asserted rows whose original team left, bounded to the grid's own `(season, round)` box | "Never silently dropped" is a stated D14 requirement, and a departed member's slot may be owned by someone still here. Bounding it to the grid keeps the conservation bound intact when `rounds` shrinks. |
| 7 | `contested_pick_ids` only | `contested_pick_ids` **and** `orphaned_pick_ids`, memoised together | Both are excluded from priced reads by the same row filter and both are surfaced on the assignment payload; one cache entry, one invalidation. |
| 8 | LLD line numbers throughout §4.3.2 | All seven read sites re-located **by symbol**; several had drifted (e.g. `_power_picks_by_owner` 17230 → 17658) | RV-3 said to. The AST test keys on symbols, so it does not rot. |
| 9 | Test baseline "1764 collected" | 1887 passed / 1 skipped | Three waves landed since; re-baselined. |

**Also note:** `_ROOKIE_MAX_ROUNDS` in `server.py` is sourced from `draft_status.ROOKIE_MAX_ROUNDS` rather than re-declared, so the clamp cannot drift from the draft-shape classifier.

---

## 8. What the mobile half needs (owned by the parallel agent — NOT built here)

1. `PickAssignmentScreen` — root-stack push, per-season tabs/accordions defaulting to the current season, the "Traded picks" review summary, per-slot saves, explicit progress, and the CAS-conflict sheet fed by the 409's `current` row.
2. A **"Draft picks" section BELOW Explore** on `LeagueScreen` — *not* a 4th Explore tile (that row is a fold-budgeted 3-across grid). Sub-line from `progress`: `"Not assigned yet"` / `"48 of 48 · 3 traded"`.
3. Extend the `NoticeCode` union with `picks_not_assigned` and add one branch to the Draft Room's notice chain — the templated notice testID gives `draft-room.notice.picks_not_assigned` for free. **Copy: unconfigured, not broken.**
4. **P-1 (blocking, live today):** `useSession.connectLeague` **replaces** the league cache with `/api/sleeper/leagues` output, which filters to non-numeric ids and therefore contains no ESPN league — so connecting any Sleeper league silently drops every ESPN row. Make it MERGE, carrying forward cached rows whose platform is not `sleeper`.
5. One deep link on the root stack; `FeedbackFAB` on the screen (the setup sheet is a modal and therefore exempt).

**Do not** reference `picks.assign_tradeable`, `recorded_picks`, or a `source` badge on a priced surface — none of those exist yet.
