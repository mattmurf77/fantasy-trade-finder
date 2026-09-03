# HLD delta — G-413 Send in Sleeper: server-owned draft-pick encoding

> Delta against [`docs/architecture.md`](../../../../docs/architecture.md) (§ Data flow `:5`,
> § Components → Backend `:122`) and [`living-memory/HLD.md`](../../../../living-memory/HLD.md).
> **A delta, not a rewrite** — only what changes is here. Mechanics are in
> [`lld-delta.md`](lld-delta.md); requirements in [`prd.md`](prd.md); gates in [`scope.md`](scope.md).
>
> Base: worktree `9145d22f` (= `origin/main` `ce3f443c` + Phase 0/1 docs). Every `file:line`
> verified 2026-09-02 against that tree. Plan: [`plan-g413.md`](plan-g413.md).

---

## 1. Why this is an HLD delta and not just a bug fix

`architecture.md` has **no row for `backend/sleeper_write.py`** and no data-flow edge for the
Sleeper write path — the only mention is a parenthetical inside the `trade_block_service.py`
row (`docs/architecture.md:152`). The MFL and ESPN propose routes (`backend/server.py:28186-28208`,
`:28639-28644`) already treat pick assets as a first-class step with their own ground truth; the
Sleeper route (`:16155-16282`) is the one propose path with **no pick step at all**. This change
adds that step, and in doing so gives the Sleeper write path two ground-truth reads it did not
have. That is a data-flow addition, so it is recorded here.

What does **not** change: no new module, no new table, no new flag, no new client, no new
route. The request contract of `POST /api/trades/propose` is unchanged.

---

## 2. Delta to `docs/architecture.md` § Data flow (`:5`)

Today the Sleeper send is one hop: mobile → `POST /api/trades/propose` → `sleeper_write.propose_trade`
→ `POST https://sleeper.com/graphql`, with one public read (`/v1/league/{id}/rosters`) to resolve
the two roster ids. Pick ids ride the same arrays as player ids and reach Sleeper as player keys.

After this change the route gains **one conditional branch with two reads**, taken only when the
trade carries at least one pick asset:

```
SendInSleeperButton (4 mounts, mixed arrays unchanged)
    │ POST /api/trades/validate            (advisory; same split, same two reads)
    │ POST /api/trades/propose
    ▼
server.propose_trade_to_sleeper           server.py:16156
    ├─ _fetch_league_rosters              (existing — roster ids, :13886)
    ├─ split give/receive by _is_ftf_pick_asset          (existing helper, :27903)
    ├─ [picks present only]
    │    ├─ load_draft_picks(league_id)   ── existence ── draft_picks table (platform rows)
    │    └─ _fetch_sleeper_traded_picks   ── holder ───── GET /v1/league/{id}/traded_picks  (:13895)
    │    └─ _sleeper_encode_ftf_picks     NEW  → encoded[] | 422 sleeper_pick_unmapped | 422 sleeper_pick_not_owned
    ├─ ProposeTradeRequest(players-only arrays, draft_picks=encoded)
    └─ sleeper_write.propose_trade        → propose_trade(... draft_picks: ["orig,season,round,from,to", …])
```

Mermaid, `flowchart LR`: add the label `traded_picks (pick sends)` to the existing `SRV → SL`
edge — two routes (propose, validate) now hit `/v1/league/{id}/traded_picks` on pick sends — and
add the new **`DB → SRV` edge for `draft_picks` on the propose path** (the write route now reads a
table the sync daemon populates).

---

## 3. The two ground-truth sources (why two, and why these)

| Question | Source | Why this source and not another |
|---|---|---|
| **Does this pick exist in this league?** | `draft_picks` grid, `load_draft_picks(league_id)` with its default platform-only source (`backend/database.py:10142-10183`). For Sleeper rows `original_roster_id` **is** the Sleeper roster_id (`:1100`; written at `:10027`/`:10073`), and the row's `pick_id` is exactly the asset id the client sent (`make_pick_id`, `:9756-9765`). | It is what the client displayed — already horizon-corrected (#355) and completed-draft-excluded (#228). A pick absent from it is a pick the user could not have seen. Generic rungs (`generic_pick_…`, `backend/pick_values.py:213`) never appear in it by construction. |
| **Who holds it right now?** | Live public `traded_picks` (`_fetch_sleeper_traded_picks`, `server.py:13895-13908`), overlaid on "original roster holds by default". | The grid's `owner_user_id` is as fresh as the last `session_init` sync (`docs/architecture.md:152`); a pick traded since then would encode with a stale `from` and Sleeper would reject it as a 502. The live list is roster-id keyed end to end, so co-owned rosters resolve the same way `_roster_id_for_owner` already does (`:15965-15983`). Same trust level and same fail-soft as the rosters fetch the route already makes. |

Both reads are **skipped entirely** for a player-only send. A player-only send is byte-identical
to today's request and makes zero additional upstream calls (PRD R-4, R-12).

---

## 4. Components touched

| Component | Change | Kind |
|---|---|---|
| `backend/sleeper_write.py` | `encode_draft_pick()` — pure formatter for `"orig,season,round,from,to"`; header caveat that field 1 is captured-not-confirmed on a multi-owner pick | additive; module stays Flask/DB-free (`:33`) |
| `backend/server.py` propose route `:16155-16282` | split → existence+holder → encode → 422s → players-only `ProposeTradeRequest` → honest `_record_send_success` args; `draft_picks` body key rejected if non-empty | additive contract (two new 422 codes, one new 400 reason on a key nobody sends) |
| `backend/server.py` new helpers beside the MFL block (~`:27960`) | `_sleeper_pick_holder_index()`, `_sleeper_encode_ftf_picks()` | new |
| `backend/server.py` validate route `:27715-27834` | same split; `asset_unmapped` / `pick_moved` blocking advisories; `player_moved` and `roster_limit` computed over players only | fix (#413 half 1) |
| `backend/analytics_taxonomy.py:1055-1058` | `sleeper_send_failed.error_code` enum comment: 14 server codes + 3 = 17 | comment only; `CLIENT_EVENT_PROPS` constrains keys, not values |
| `mobile/src/components/SendInSleeperButton.tsx:266-310` | two `else if` branches for the new 422s, before the catch-all | additive |
| `mobile/src/api/sendInSleeper.ts:5-6`, `:214` | comment updates (error-code list; warning-code list) | comment only, no type change |
| `mobile/tests/check-send-button-platform.js` | checks 7–8 | new assertions |

Web and the extension have no send route (`git grep -n "trades/propose" -- web extension` is
empty) — nothing there.

---

## 5. Decisions

| # | Decision | Alternatives rejected |
|---|---|---|
| D-a | **The server owns pick encoding; the client never asserts `from`/`to`.** Mirrors `_mfl_encode_ftf_picks` (`server.py:27937-27960`) and the MFL banner comment (`:27877-27889`). | *Client-side encoding* — the client has no `traded_picks` view and a client-asserted `from` is exactly the value the server must verify. *A new `give_pick_ids` key* — the four fielded mounts already send mixed arrays with no discriminator beyond id shape; builds 1.16.12–1.16.14 must start working on server deploy alone. |
| D-b | **`draft_picks` body key: reject non-empty with 400.** One way in; a pre-encoded string from a client is a client-asserted orientation. | *MFL-style pass-through* (`give_pick_assets`, `server.py:28219-28224`) — keeps a second, unverified entry point alive for a producer that does not exist (`docs/api-reference.md:421`). *Silently ignore* — violates never-drop-an-asset. |
| D-c | **Existence from the grid, holder from live `traded_picks`, holder defaulting to the original roster.** | *Grid `owner_user_id` alone* — stale between syncs; and it is a user_id, not a roster_id, so it cannot be compared to the roster ids the route resolves. *Live `traded_picks` alone* — proves holder, not existence: a generic rung or a phantom season has no traded row and would default to "original holds it". |
| D-d | **Any single unresolvable pick refuses the whole send** (422). Same rule as MFL (`:28193-28198`) and ESPN (`:28625-28644`). | *Send the mappable subset* — a partially-mapped trade is a different trade. |
| D-e | **No feature flag.** The change lives inside `trade.send_in_sleeper`; a pick-free send is byte-identical; both new responses are refusals on a path that today ends in a 502. Rollback is a code revert of an additive contract — the D-063 precedent (*"rollback is a code revert on an additive contract, operator-accepted"*, `living-memory/DECISIONS.md:675-676`). | *A `trade.sleeper_pick_send` flag* — would add a second way to keep pick sends broken, gating a fix rather than a behavior. Stated in scope §2, not waived. |
| D-f | **`traded_picks` fetch failure degrades, it does not block.** `_fetch_sleeper_traded_picks` returns `[]` on error (`:13906-13908`), indistinguishable from "nothing traded"; holder falls back to the original roster. Outcomes are bounded (LLD §6.9): an acquired pick → 422 `not_owned` (safe refusal); one's own original pick already traded away → encoded with `from = me` → Sleeper rejects → 502 (today's behavior). **Never a silently wrong send.** | *A strict variant returning `None` + 502 on flake* — a second failure path for a transient the route already tolerates on the rosters fetch. Accepted residual, recorded. |

The `DECISIONS.md` entry is **D-172** (next id; `D-171` at `living-memory/DECISIONS.md` is the
current max, verified 2026-09-02) — text in PRD §12.

---

## 6. What the propose-label spine does not see

`_save_deck_outcome_safe(impression_id, "propose")` (`server.py:16264-16265`, F1 `deck.signal_v2`;
shipped as the propose-label spine — `living-memory/CHANGELOG.md` § 2026-08-29d, PR #241)
and `_record_send_success` (`:16274-16278`) are both **after** the Sleeper write succeeds. Both new
422s return before the write, so neither an impression is labeled `propose` nor a
`sleeper_send_succeeded` row is written on a refusal — the same shape as the existing 502 path.
PRD R-8 pins both directions: T-11 (a refusal never labels) and T-3b (a success still labels —
the sabotage that deletes the `:16264` call must go red; a negative-only assertion cannot tell
"gate before the call" from "call deleted").

---

## 7. Residual open question (recorded, not hidden)

Field 1 of the pick string (`"<f1>,<season>,<round>,<from>,<to>"`) is captured as "likely the
original-owner roster id — confirm on a multi-owner pick" (`docs/plans/sleeper-write-capture-runbook.md:159`).
Fields 2–5 and both live examples (`"11,2026,1,1,2"`, `"1,2027,4,2,1"`) are observed. Sleeper's own
transaction shape corroborates `roster_id (original)` / `previous_owner_id` / `owner_id`
(`server.py:13900`). If field 1 is instead the current holder, a never-traded pick (orig == from)
still works and only acquired picks fail — visibly, as 502 `sleeper_write_failed` with `detail`.
The operator may hold no acquired pick in any league, so the device proof is **conditional**:
"not run — Q-035 stays open" is a legal, logged outcome (PRD §10). There is no dry run (no Sleeper sandbox; `FTF_TEST_MODE` fail-closes the route at `:16167-16171`),
so the proof is TestFlight step 3 (PRD §10). Logged as **Q-035** in `OPEN_QUESTIONS.md` the way
Q-016 records `waiver_budget`.
