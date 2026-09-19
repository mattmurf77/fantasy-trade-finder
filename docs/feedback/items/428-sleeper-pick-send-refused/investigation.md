# FB-428 — Phase 1 investigation: Sleeper refuses a pick send after the #413 fix

> Planner's trace, 2026-09-08, worktree branch `claude/feedback-422-428`. File:line cites are against this worktree. Public Sleeper reads were made with `curl` (no auth); production Postgres was **not** queried.

**Report (mattmurf77, 2026-09-08T17:04Z, v1.17.2 build 154, screen `TradesHome`):** "Draft pick trading on sleeper still doesn't work."

## 1. What the logs prove

Render, 2026-09-08 17:03:49–52Z, league FFV3 `1312140920132497408`:

| Time | Event | What it tells us |
|---|---|---|
| 17:03:50 | `POST /api/trades/validate` → 200, **41 bytes** | The body is exactly `{"checked":true,"ok":true,"warnings":[]}` — so every pick in the trade **mapped to a `draft_picks` grid row and passed the live `traded_picks` holder check** (`backend/server.py:30052-30070`). Neither #413 refusal fired. |
| 17:03:50 | Sleeper GET `/league`, `/rosters`, `/traded_picks` all 200; `traded_picks` preview shows **season 2026** rows | The send path's ground truths were healthy. Sleeper still lists 2026 rows 13 days after the 2026 draft. |
| 17:03:52 | `sleeper propose write-failed [error]: [{"message": "These draft picks cannot be traded." …` → `POST /api/trades/propose` 502 | The mutation reached Sleeper with a server-encoded `draft_picks` element; **Sleeper itself refused the pick**. The request body is not logged, so the pick identity must be reconstructed. |

## 2. Live Sleeper facts (public API, 2026-09-08)

- **FFV3 `/league`:** `season "2026"`, `status in_season`, `settings.trade_deadline 12`, `disable_trades 0`, `draft_rounds 4`, `leg 1`. → hypothesis (d) (deadline / trades disabled) is **refuted**.
- **FFV3 `/drafts`:** one draft, `season "2026"`, `status "complete"`, `start_time 1787704278413` (≈ 2026-08-26), `last_picked` set. The 2026 rookie class is spent.
- **FFV3 `/traded_picks`:** 57 rows — **2026: 34**, 2027: 17, 2028: 6, 2029: 0. Sleeper keeps the spent season's rows.
- **Operator = Sleeper user `313560442465169408` = roster 1.** Per `traded_picks`, roster 1 holds exactly one acquired pick — **roster 11's 2026 4th** (spent) — and has given away all of its own 2026 and 2027 picks plus 2028 R1–R3. His Sleeper-tradable inventory today is his own **2028 4th and 2029 1st–4th**, nothing else.
- **Sleeper's tradable window is three classes anchored at the first undrafted class (D-089 confirmed again):** FFV3's own 2025-season league (`1181674778942836736`, draft `last_picked` 2025-08-22) completed four trades in weeks 8–12 carrying **2028** picks — all `created` after the draft. SFO (`1312583962966650880`, 2026 draft complete) completed a **2029** pick trade in week 1, after its draft. So in FFV3-2026 the window is **2027–2029**; a 2029 pick is tradable and a **2026 pick is not**.
- **Encoding field 1 is the ORIGINAL roster id — confirmed by Sleeper's own data.** Completed-trade transactions carry `draft_picks: [{season, round, roster_id (original), previous_owner_id (giver), owner_id (receiver)}]` — e.g. `roster_id 3, previous_owner 6, owner 4` for a pick that had already changed hands. That is the tuple `encode_draft_pick` emits (`backend/sleeper_write.py:242-255`: `orig,season,round,from,to`). Both runbook captures are acquired-pick trades too (`"11,2026,1,1,2"` = roster 11's pick held by roster 1; `"1,2027,4,2,1"` = roster 1's pick held by roster 2 — `docs/plans/sleeper-write-capture-runbook.md:159`), contrary to Q-037's premise that both had `orig == from`. → hypothesis (c) is **refuted**; Q-037 can be closed on public evidence. A wrong `orig`/`from` would in any case have failed our own holder check (`server.py:30310-30312`) before reaching Sleeper, or surfaced as an ownership error, not "cannot be traded".

## 3. Hypotheses, ranked

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| **(a)** | **A spent 2026 pick was in the trade.** It was still a row in FFV3's `draft_picks` grid (so it was served/priced and mapped), `traded_picks` still lists 2026 rows (so the holder check passed), and Sleeper refused it because the 2026 draft already ran. | **Strongly indicated — root cause.** | §1: mapped + held + refused. §2: the operator's only acquired pick is a 2026 pick; every other pick he can offer (2028 R4, 2029s) or receive (any 2027–2029 pick) is inside Sleeper's proven window. The send path has **no tradability test at all**: `_sleeper_encode_ftf_picks` (`server.py:30271-30320`) trusts grid existence + `traded_picks` holder, and both still contain spent picks. |
| (b) | A 2029 pick beyond Sleeper's window. | **Refuted.** | §2: current+3 trades completed post-draft in this league's own lineage (2028 in 2025) and in SFO (2029 in 2026). |
| (c) | Wrong `orig`/`from`/`to` (Q-037). | **Refuted.** | §2: Sleeper's transaction object + both captures are acquired-pick trades with field 1 = original. |
| (d) | Deadline / `disable_trades`. | **Refuted.** | §2 settings. |

### 3.1 How a spent 2026 row can be in the grid (mechanism — indicated, not confirmed)

The sync is `_sync_sleeper_owned_picks` (`server.py:13271-13355`), run best-effort on every `session/init` daemon pass (`:21678`). Its **only** exclusion signal is the live `/drafts` read: `_drafts = _fetch_sleeper_drafts(...)` (`:13329-13337`) → `exclude = {2026}` iff a draft with `status == "complete"` and `season == league.season` comes back. `_fetch_sleeper_drafts` is fail-soft to `[]` (`:15979-15994`), and `[]` means "exclude nothing" by design (#228 / D-089 fail-safe, pinned by `test_daemon_step_no_exclusion_when_draft_pending_or_flaked`). With no exclusion, `pick_horizon` anchors at 2026 (`backend/draft_status.py:92-135`) and `sync_draft_picks` (`backend/database.py:11070-11092`) writes 2026 rows for every roster, then the overlay (`:11130-11160`) re-applies the 2026 `traded_picks` rows — including roster 11's 4th to roster 1. The grid is a replace-sync, so any member's init with one flaked `/drafts` read re-populates 2026 for the whole league until the next healthy init. The #207 cached verdict (`leagues.draft_status`, `_refresh_league_draft_status` `server.py:18015`) is deliberately **not** consulted by the Sleeper sync (`test_cached_verdict_does_not_leak_into_the_sleeper_sync`), so there is no second signal.

**Definitive checks (operator / build agent with prod access):** (1) `SELECT season, COUNT(*) FROM draft_picks WHERE league_id='1312140920132497408' GROUP BY season` — 2026 rows present ⇒ (a) confirmed; (2) the `deck_impressions` / `trade_decisions` row for the card sent at 17:03Z (if `from_deck`) names the pick; (3) Render `session/init` logs for that league around 17:0xZ: a `→ Sleeper GET …/drafts` without a `← Sleeper 200` and the `✅ owned draft picks synced (144 picks)` line (144 is the count in BOTH states — 3 classes × 4 rounds × 12 — so the count alone cannot distinguish them).

## 4. Every surface that offers Sleeper picks reads the same grid

| Surface | Read | Covered by a clean grid? |
|---|---|---|
| Deck cards / engine pick pool | `_owned_pick_assets` → `load_draft_picks(owner_user_id=…)` `server.py:1115` | yes |
| Calculator eveners | same block `server.py:1115-1130` | yes |
| `GET /api/league/picks` | `server.py:12456`, `:12488` | yes (no season filter of its own) |
| Validate / propose | `server.py:30052-30070` / `:18391-18411`, literal platform source | yes — **plus the new send-time guard** |
| Team overhaul snapshot / eligible pool | `overhaul_api.pick_rows` `backend/overhaul_api.py:130-137` → `capture_snapshot` `:173-215`, `eligible_assets` `:411-433`; sends go through `_sleeper_propose_core` (`server.py:18322`) | yes — same rows, same core |
| Win Now | `backend/win_now_service.py:310` | yes |

No surface applies a tradability rule of its own; none can, cheaply — only the sync and the send path hold `/drafts`.

## 5. Why the user saw an unhelpful message

`sleeper_write._post_graphql` sets `detail = json.dumps(errors)[:500]` (`backend/sleeper_write.py:383-389`); the route truncates to 200 (`server.py:18435-18441`). The fielded catch-all renders `detail` (`mobile/src/components/SendInSleeperButton.tsx:323-327`), so build 154 showed a raw JSON fragment: `[{"message": "These draft picks cannot be traded.", "path": ["propose_trade"], …`. The information was there; the shape was not.
