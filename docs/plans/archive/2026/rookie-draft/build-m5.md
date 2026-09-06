# Build status — M5: MFL parity (production wiring)

**Wave:** M5 · **Branch:** `wave/m5` (base `origin/main` @ `f14223c`) · **Date:** 2026-08-06
**Spec:** [plan](plan.md) §M5 + D8/D10 + *Operator decisions — 2026-08-06* · [lld](lld.md) §4.6, §2.1, §5.2, §6.1, §6.2, §7 · [hld](hld.md) §2.2, §5.3, §7
**Flag:** `draft.mfl` — **default OFF, not flipped.** Nothing merged, nothing pushed.

---

## 1. What M5 actually was

`backend/draft_board_service.py` already rendered MFL completely, with passing fixture tests
(`test_m5_01..05`) against the four committed live grids. What did not exist was **production
wiring**: `draft_board_route` returned `dbs.unsupported_board(req)` for every non-Sleeper
platform, and the `BoardRequest` MFL fields (`mfl_host`, `mfl_year`, `mfl_franchise_to_user`,
`mfl_player_ids`) were never populated by anything but tests.

So this wave is a binding, not a renderer. `backend/draft_board_service.py` was **not touched**
(it is another agent's file this wave, and it needed nothing).

## 2. What was built

### 2.1 `backend/server.py` — Draft Room region only

Two new helpers, placed immediately above `draft_board_route`, plus ~20 lines inside it.

| Symbol | Purpose |
|---|---|
| `_mfl_draft_opener()` | The MFL transport, `None` in production. MFL has no `FTF_SLEEPER_FIXTURES_DIR`-style env seam, so `mfl_service` takes an injected `_opener` instead. Exposing it as a **function** rather than a module constant makes it a one-line monkeypatch seam — which is exactly what lld §4.6's RB-3 requires ("thread `_opener` down to `fetch_draft_results`, or M5 cannot be tested against the committed corpora"). |
| `_mfl_board_binding(league_id, sess)` | Resolves everything `build_board` needs, or `None`. Returns `{"request_fields": {...}, "cookie": ...}`. |
| route body | `platform == mfl and is_enabled("draft.mfl")` ⇒ resolve the binding, construct the (frozen) `BoardRequest` **once** with MFL fields already in place, call `build_board` with `PlatformFetchers(rookie_ids_fn=..., mfl_opener=..., mfl_cookie=...)`. Otherwise the pre-existing `platform != SLEEPER ⇒ unsupported_board` line is reached unchanged. |

**Resolution reuses the existing MFL scheme; no second one was invented.**

| Field | Source | Precedent |
|---|---|---|
| `mfl_host` | `leagues.platform_host` | `_draft_status_for_league` (server.py ~10073), `_refresh_mfl_future_picks` |
| `mfl_year` | `leagues.platform_season`, falling back to `_MFL_DEFAULT_YEAR` | same |
| cookie | `_mfl_cookie_for(sess, user_id)` — encrypted `mfl_credentials` row first, in-memory session fallback | the #177 authed-link flow |
| `mfl_franchise_to_user` | synthetic member ids `mfl:<league>.f<franchise>` inverted out of `league_members`, with `leagues.platform_my_team` → `leagues.user_id` overlaid | `_sync_mfl_owned_picks`'s `_fr_to_user` (server.py ~8697) |
| `mfl_player_ids` | `_shared_crosswalk().by_mfl_sleeper` — the **existing** shared DP crosswalk | `map_franchises` call sites |
| `rostered_ids` | `league_members.player_ids` (already crosswalked at import time) | — |

### 2.2 The crosswalk is load-bearing (spec item 3)

`_render_mfl` **suppresses the undrafted list entirely** when `mfl_player_ids` is missing
(service comment ~line 982), because subtracting MFL-space pick ids from our rookie ids would
silently under-count. The binding therefore injects `by_mfl_sleeper` directly (no copy — the
field is a read-only `Mapping`), and a crosswalk failure is caught and degrades to `{}`, i.e. an
honestly-suppressed list rather than a wrong one. `T-M5-08` asserts the undrafted **count**
exactly so a half-wired crosswalk fails loudly; `T-M5-08b` is the contrast case.

### 2.3 Request spacing (spec item 4)

The binding makes **exactly one** MFL export call per refresh cycle (`TYPE=draftResults`), so
`_REQUEST_SPACING_SECONDS = 1.0` has nothing to space. That is a deliberate design constraint,
not an accident: `mfl_service.resolve_host` is **not** called as a host fallback, because it is a
second network round-trip. A league with no stored `platform_host` was never imported through
the MFL path, so there is nothing to read — the binding returns `None` and the route degrades to
the same `platform_unsupported` payload the flag-off path serves. `T-M5-07` asserts the
one-call property. Both the code comment and this doc state that a future second export on this
path must space the calls the way `fetch_league_bundle` does.

### 2.4 `as_of`, auth failure, stale-as-live (spec item 5)

Already implemented in the service; this wave proves it is **reachable through the wiring**:
`T-M5-07` pins `as_of` on the happy path (frozen clock, exact match) and `T-M5-09` drives a 401
through the real route and asserts `state:"unavailable"` (never `live`/`complete`),
`stale:true`, `degraded.reason == "auth_expired"`, `notice.code == "mfl_reconnect"`, empty
`picks`/`order`, and a non-empty `as_of`.

## 3. Live mode is release-gated, not built off (spec item 6) {#the-live-probe}

**The honest position.** A genuinely drafting MFL league *does* report `state: "live"` — that is
true and suppressing it would be a lie. What is unverified is **latency**: nobody has measured
how long after a pick MFL's `draftResults` export reflects it. Plan §M5 makes that a RELEASE
gate for MFL live mode.

**How the gate is enforced without a special case.** MFL live mode = `draft.mfl` ON **and**
`draft.live_poll` ON. `draft.live_poll` is a separate flag, also default OFF, and it gates the
*only* recurring fetch in the system (the M4 client poll). Flipping `draft.mfl` on therefore
starts no poll: MFL ships **upcoming + manual refresh**, which is precisely what plan §M5 asks
for. No third flag and no platform-specific poll suppression were added — that would be dead
machinery duplicating a gate that already exists.

> Reviewer note: the one thing this does NOT gate is the *server-side* TTL. A `live` MFL entry
> caches for `_TTL_BY_STATE[LIVE] = 20 s`, so a user hammering manual Refresh can cause one
> upstream read per 20 s. That is the same budget Sleeper gets, it is bounded by the existing
> ≤3-fetches-per-rolling-60 s counter, and it is user-initiated, not recurring. If the probe
> shows MFL's export lags badly, the correct follow-up is to raise MFL's `live` TTL, not to add
> a flag.

### The live probe — what it must measure

Run against a **genuinely drafting** MFL league (an in-progress rookie draft; a mock or a
paused draft does not count). This gates flipping `draft.live_poll` on for MFL.

1. **Setup.** Note the league's `platform_host`, id and year. Have the MFL draft room open in a
   browser so pick times are observable to the second.
2. **For each of ≥5 consecutive real picks**, record:
   - `t_pick` — the wall-clock second the pick was made, read from MFL's own draft room.
   - `t_export` — the first second at which a poll of
     `https://<host>/<year>/export?TYPE=draftResults&L=<id>&JSON=1` returns that pick with a
     non-empty `player`. Poll every 5 s from `t_pick`, with the ≥1 s spacing honored.
   - `timestamp` — the `timestamp` field MFL itself puts on the pick, to confirm it agrees with
     `t_pick` (if it does not, the field is not usable for "how fresh is this board").
3. **Compute** `lag = t_export − t_pick` for each pick; report min / median / **max**.
4. **Pass criterion:** `max(lag) ≤ 30 s` across all sampled picks — the same "live enough" bar
   D6/O6 sets for Sleeper (whose CDN floor is ~20–30 s). A single sample over 30 s fails the
   gate.
5. **Also record, because they change the answer:**
   - whether the export is CDN-cached (response headers: `Age`, `Cache-Control`, `s-maxage`) —
     a cached export means the measured lag is a floor, not a constant;
   - whether a **private** league (cookie-authed) behaves differently from a public one;
   - whether a multi-`draftUnit` league (division/conference draft) lags differently.
6. **Record the result in this document** and, if it passes, in the `draft.live_poll` row of
   `docs/config-reference.md`. If it fails, MFL stays on upcoming + manual refresh for the
   season — which is the plan's own stated fallback and still most of the ask.

**Status: NOT RUN.** No drafting MFL league was available at build time, and the committed
corpora cannot answer a latency question. `draft.mfl` and `draft.live_poll` both remain OFF.

## 4. Flag — the 4-touch convention (lld §6.1)

| # | File | Change |
|---|---|---|
| 1 | `backend/feature_flags.py` | `draft.mfl` appended to `FLAG_KEYS` with a comment stating what it gates **and** the flag-off behavior. Default-`False` follows automatically. |
| 2 | `config/features.json` | `"draft.mfl": false`; the existing `_comment_rookie_draft` string was **extended**, not duplicated. |
| 3 | `backend/tests/fixtures/flags/release.json` | mirrored exactly (enforced by `test_seed_ui_test_db.py`). |
| 4 | `docs/config-reference.md` | one row in `### Rookie draft + Draft Room`. |

A parallel agent appends `picks.slot_values` to the same four files; a merge conflict there is
expected and resolves by union-dedupe.

## 5. Deviations from plan / LLD

| # | Deviation | Justification |
|---|---|---|
| D-1 | **No `resolve_host` fallback.** LLD §4.6 does not say either way; the existing public-import routes *do* call `resolve_host`. | It is a second network call, which would put this path under the `_REQUEST_SPACING_SECONDS` obligation for no gain: a league with no stored host was never MFL-imported, so there is nothing to read. Degrades to `platform_unsupported`. |
| D-2 | **No new "MFL live" flag.** Plan §M5 says "a timed probe … gates `draft.mfl` live mode". | Read literally that could mean a third flag. `draft.live_poll` already gates every recurring fetch in the system, and it is already OFF with a release gate on it. Adding a second suppressor would be dead machinery. Documented in §3 above and in the flag comment. |
| D-3 | **`mfl_opener` exposed as a function seam (`_mfl_draft_opener()`), not a constant.** | LLD §4.6 RB-3 requires the `_opener` be threadable for M5 to be testable at all; MFL has no env fixture seam. A function is monkeypatchable in one line and self-documents as a seam. Production behavior is unchanged (`None` ⇒ `urllib.request.urlopen`). |
| D-4 | **`sleeper_get` is left unbound on the MFL path.** | The MFL path never reads Sleeper. Leaving it unbound makes a stray Sleeper read raise inside `PlatformFetchers._get` rather than go live. Asserted by `test_m5_mfl_binding_is_hermetic`. |
| D-5 | Server-side `live` TTL for MFL is the service's 20 s, not plan §M5's "30 s server poll". | The service's TTL table is `draft_board_service`'s (another agent's file this wave) and is shared with Sleeper. 20 s is *tighter* than 30 s, and it is a cache TTL on user-initiated reads, not a poll. Flagged for the reviewer in §3 rather than changed unilaterally. |

## 6. LLD-vs-operator-decisions conflicts hit

The LLD (2026-08-05) predates the operator decisions block (2026-08-06). Two conflicts touch M5:

| Conflict | LLD says | Operator decision says | Resolution here |
|---|---|---|---|
| **C-1 — O8 / Render plan** | lld §4.6 + plan §M5 assume live polling may never ship ("MFL ships upcoming + refresh"); the fan-in budget (`≤3 upstream fetches / rolling 60 s / draft`) is stated as a **per-process** guarantee, and plan §6 explicitly warns "if O8 upgrades to multi-worker, ≤3 req/min/draft multiplies by worker count — restate the budget then". | **O8: UPGRADE Render** — live polling is real. | M5 changes nothing about the budget mechanism, so the warning is now **live and unresolved**: with N workers, MFL's upstream budget is `3N` req/min/draft, and MFL's own guidance is ≥1 s between requests. **Recorded in a code comment on `_mfl_board_binding` and here.** Restating the budget per worker count is an operator/orchestrator task at upgrade time, not something one wave should decide. |
| **C-2 — O10 / pick rungs under scope** | lld §8 closes with "O10 = generic pick rungs under scope is implemented as **YES**, year-labeled, after players". | **O10: NO pick rungs inside rookie scope — players only.** | Does not affect M5 (the Draft Room's `undrafted[]` is sourced from `players.rookie_year`, never from the pick pool). Flagged because it *does* affect M2, and the LLD line is now wrong. |

Neither conflict was resolved unilaterally in code beyond what M5 owns.

## 7. Tests added — `backend/tests/test_draft_board.py`

`T-M5-01..05` (service level) already existed and are untouched. Added at the bottom of the file,
in the route-shim block:

| ID | Proves |
|---|---|
| `T-M5-06` | Flag OFF ⇒ the response is **byte-identical** to the pre-M5 build (compared against a flag cache that does not contain the key at all — `is_enabled` returns False for unknown keys — with `_now_iso` frozen so the comparison is exact), and **zero** MFL reads are attempted: `get_platform_league` and `_shared_crosswalk` are replaced with functions that raise, and the opener call log must be empty. |
| `T-M5-07` | Flag ON ⇒ a real `schema:1` board from the committed `mfl-complete` grid, driven entirely through the injected `_opener` (RB-3, zero live egress). Pins state/kind/order_confidence/order+pick counts against the manifest, `as_of` present, `stale:false`, `my_picks` resolving through the synthetic-id scheme, and **exactly one** MFL export call. |
| `T-M5-08` | The crosswalk is genuinely injected ⇒ `undrafted_suppressed:false` and the undrafted list has the **exact** expected membership and count (a silent under-count fails). Also asserts the picks were moved into our id space. |
| `T-M5-08b` | Contrast case: a crosswalk failure ⇒ `undrafted:[]` + `undrafted_suppressed:true`, and the rest of the board still renders. Without this, `T-M5-08` could pass vacuously. |
| `T-M5-09` | Auth failure through the real route ⇒ stored snapshot + `notice.mfl_reconnect` + `stale:true` + `degraded.auth_expired`, `state` never `live`/`complete`, `as_of` present. |
| `T-M5-10` | **D10** — `draft.mfl` on vs off, a Sleeper league's response is byte-identical (frozen `as_of`), and a Sleeper league never binds MFL (the opener raises if touched). |
| `test_m5_mfl_binding_is_hermetic` | `sleeper_live_egress_attempts == 0` on the MFL path. |

**Verify-failing-first:** with the binding disabled (`if False:` in place of the flag check),
`T-M5-07`, `T-M5-08`, `T-M5-08b`, `T-M5-09` and the hermeticity test all fail. `T-M5-06` and
`T-M5-10` pass in both states by construction — they are invariance tests, and that is correct.

## 8. Gates

| Gate | Command | Result |
|---|---|---|
| Backend suite (baseline on base commit: 1692 passed / 1 skipped) | `python3 -m pytest backend/tests -q` | **1699 passed, 1 skipped — exit 0** (+7 new) |
| Mobile typecheck | `cd mobile && npx tsc --noEmit` | **exit 0** |

## 9. What a reviewer should scrutinize

1. **The franchise → user map.** It is derived from `league_members`' synthetic ids plus
   `platform_my_team` → `leagues.user_id`. If the *session* user is not the *linking* user
   (a shared/handed-over league row), `my_picks` will be empty rather than wrong — verify that
   is the desired failure direction.
2. **`_shared_crosswalk()` on a request path.** It is process-cached with a 24 h TTL and a
   bundled-snapshot fallback, and every other MFL surface already calls it, but this is the
   first time it sits on a *read* route that a poll could hit. Cold-process first call does a
   DP fetch; it is inside `try/except` and degrades to a suppressed undrafted list.
3. **The unbound `sleeper_get` on the MFL path (D-4).** Intentional: it converts a wiring
   mistake into a raise instead of live egress. Confirm you agree with that failure mode.
4. **C-1, the fan-in budget under multi-worker Render.** Unchanged by this wave and now
   materially different because of O8. Someone owns restating it.
5. **The live probe has not been run.** §3 is a procedure, not a result. `draft.mfl` must not
   be flipped on together with `draft.live_poll` until it has.
6. **Flag-off byte-identity.** `T-M5-06` compares against a flag cache without the key, which is
   the strongest available proxy for "the pre-M5 build". If you want a stronger proof, diff the
   flag-off response against `git stash`-free output from `origin/main` by hand.
