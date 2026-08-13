# Backend build status — #295/#296/#305 (2026-08-13)

> Backend build agent's lane report. Contract: [`prd-2026-08-13.md`](prd-2026-08-13.md)
> (55433ef) · [`lld-2026-08-13.md`](lld-2026-08-13.md) §1–§2, §7 · branch
> `mock-draft-fix`, base `origin/main` @ `3b64a44`. Companion:
> [`status-mobile-2026-08-13.md`](status-mobile-2026-08-13.md) (83a1638).

## Commits (backend lane, in the LLD-mandated order)

| Commit | Content |
|---|---|
| `6f0d44e` | Analytics registration ALONE — five events + prop rows + the two `NON_INTENT_EVENTS` rows, same commit, pure addition (INV-11, drop-if-superseded-clean for Q1) |
| `5cbff26` | Engine + route repair + manual mode + harness lockstep |
| `51bd832` | §7.0 fixture rewrite, its own commit, status-diffed |
| `557fb32` / `46de759` | The 19 remaining T-295/T-305 pins; T-295-16 red-fidelity tweak |
| this commit | This status doc |

## Changes at file:line

### `backend/mock_draft_service.py` (engine)

| Site | Change |
|---|---|
| `:76-77` | `MODE_CPU` / `MODE_MANUAL` constants (M2) |
| `:98` | `REASON_USER_NOT_IN_DRAFT` (R6) |
| `:330-341` | `class UserNotInDraft(MockDraftError)`, `code = REASON_USER_NOT_IN_DRAFT` (R7) |
| `:452-480` | `start_refusal` — keyword-only `user_owner_id`, fourth rung LAST, `None` skips (legacy positional callers byte-compatible), `""` is not `None` (R6) |
| `:482-486` | `capability` — same keyword, forwarded (R6) |
| `:995` sig, `:1049-1055` | `build_settings` gains `mode`; short-order floor → labelled shuffle, `traded_slots` dropped with it (R4/§14-2) |
| `:1065-1067` | `teams = len(resolved_order)` (INV-4); `UserNotInDraft` raise before any slot table or row (INV-6) |
| `:1069-1073` | personas keyed over `dict.fromkeys([*owners, *resolved_order])` (R5/§14-1) |
| `:1091-1094` | returned settings gain `"mode"` (engine-side coercion — the `draft_type` idiom) |
| `:1123-1142` | `next_pick` — THE one mode lever (INV-7): `is_user = owner is not None and (mode == MODE_MANUAL or owner == user_owner_id)`, read-time default `MODE_CPU` |
| `:1422-1431` | `settings_echo` gains `"mode"` (always present, effective value) and `"user_owner_id"` (R8/LLD §11.1) |

Untouched by design: `advance_cpu`, `apply_user_pick`, `_append`, `owner_of`,
`pick_slots`, `loads`, `dumps`, `empty_payload`, `_pick_rng`, every import.

### `backend/server.py` (resolution layer) — the five membership sites

| Site | Change |
|---|---|
| `:11718-11736` | **`_mock_owner_ids(sess)`** — THE `owners` constructor: members + caller, str-coerced, de-duplicated, caller last, `""` never appended (R1≡R4 shared construction, INV-1/INV-3) |
| `:11739-11754` | **`_mock_rosters(sess)`** — THE `rosters` constructor: member rosters + caller's `user_roster` assigned AFTER the comprehension (session wins) (R2≡R3, INV-2) |
| `:11757…` + `:11800-11807` | **Site 5 — `_mock_usernames`** gains `session_user=(user_id, display_name)`; caller appended when absent (R3/D-16, LLD §11.3) |
| `:11826-11832`, `:11852` | **Site 1+2 — `_mock_league_context`** calls `_mock_rosters`, passes `session_user`, returns `_mock_owner_ids(sess)` |
| `:11869-11874` | **Site 3 — `_mock_context_from_row`** same two swaps (create/resume parity) |
| `:11909-11910` | **Site 4 — `_mock_capability`** → `mds.capability(ctx, _mock_owner_ids(sess), user_owner_id=str(sess.get("user_id") or ""))` (probe≡create) |
| `:12113-12117` | POST `mode` validation — `400 {"error": "bad_mode"}`, `bad_basis` parity, after rounds, before resolution (M1) |
| `:12127` | `start_refusal(ctx, owners, user_owner_id=user_id)` |
| `:12142-12158` | `build_settings(…, mode=mode)` wrapped ALONE in `try/except mds.UserNotInDraft` → `empty_payload(REASON_USER_NOT_IN_DRAFT)`, byte-identical to the rung (R7) |
| `:12046-12060` | Route docstring: `mode` body field, `bad_mode`, four-rung typed-empty list |

### `backend/analytics_taxonomy.py` / `backend/analytics_queries.py`

Registration-only commit `6f0d44e`, ordered FIRST on the backend lane, strictly
additive (no neighbouring reformatting): `ALLOWED_CLIENT_EVENTS` `:265-266`;
`CLIENT_EVENT_PROPS` `:733-740` (exact §6 frozensets, import-time enforced);
`NON_INTENT_EVENTS` gains `mock_completed` + `mock_create_refused`
(`analytics_queries.py:154-155`) in the same commit (the DAU-seam rule).
No `SERVER_FIRED_EVENTS` / `FUNNEL_CRITICAL` additions.

### `backend/tests/test_mock_draft.py`

- **§7.0 fixture rewrite** (`51bd832`): 4 caller-excluded QA opponents +
  QA caller `990000000000000042` (5 teams), disjoint rosters over a 30-player
  pool, `user_roster` + `display_name` set, hermetic sleeper fixture seam
  (empty dir — a board read is a caught miss, never live), per-test row
  hygiene (`_abandon_all_mocks`). **Status diff pre→post (full file, -v):
  only `test_295_02` added; 99/99 PASSED.** Lockstep updates (for
  TEST_LEDGER): `test_w2_20_g2_the_capability_probe…` (5-team session now
  `can_start: true, teams: 5`), `test_the_abort_criterion…` (an open gate now
  means a REAL created mock), `test_290_13…` (allowed lookup set = the 30-id
  class).
- **Engine-harness patch** (`5cbff26`): `make_state` builds through
  `build_settings` with a compliant user, then re-imposes the degenerate
  snapshot (tiny assigned orders, phantom users) that 15 existing
  CPU-behaviour tests exercise on purpose — the guards refuse those shapes at
  CONSTRUCTION now, and hand-built states are what `advance_cpu`'s fail-soft
  defences exist for. Documented in the helper's docstring; the guards
  themselves are pinned by T-295-06/T-295-16 driving `build_settings`
  directly. `test_w2_20_g1_traded_slots…` moved to a 4-team shape (its old
  3-team explicit order is now floored by design).
- **20 backend tests of the PRD's 21** (T-295-10 is the mobile lane's node
  check, shipped in `fffcf08`).

## Pytest counts

Baseline, this worktree, measured before the first edit (base `55433ef`):

```
2677 passed, 1 skipped in 243.58s (0:04:03)
```

Final (HEAD, full `backend/tests` suite):

```
2697 passed, 1 skipped in 234.96s (0:03:54)
```

Delta exactly +20, accounted test-by-test — all this lane's:
T-295-01/02/03/04/05/06/07/08/09/13/15/16/17 (13) + T-305-01..07 (7). The
mobile lane's new suites are Node checks under `mobile/tests/` (`fffcf08`)
and do not enter the pytest count. Zero removals; no existing test deleted
or skipped.

## Sabotage matrix — 19 sabotages / 20 tests / 0 false passes

House rule discipline: each sabotage applied ALONE (anchor asserted unique,
`git diff --quiet` proven non-quiet after apply and quiet after restore), the
named test(s) run, then restored. Driver + raw output preserved in the session
scratchpad (`sabotage_matrix.py`, `sabotage-evidence.txt`).

| Sabotage (revert exactly this) | Named test(s) | Verdict |
|---|---|---|
| R1: `_mock_owner_ids` returns member ids only | T-295-01, T-295-04 | RED (2 failed) |
| re-add the caller to the fixture's members | T-295-02 | RED |
| `teams = len(owners)` | T-295-03 | RED |
| remove the fourth rung | T-295-05 | RED |
| remove the `build_settings` raise | T-295-06 | RED |
| resume half only: `_mock_context_from_row` member-only comprehension | T-295-07 | RED |
| probe half only: `_mock_capability` counts members only | T-295-08 | RED |
| `_mock_owner_ids` appends the caller unconditionally (`""` phantom) | T-295-09 | RED |
| remove the route `try/except` (as `except CalibrationGateClosed` — `UserNotInDraft` propagates to the generic 500) | T-295-13 | RED (the 500) |
| personas keyed on `owners` only | T-295-15 | RED |
| remove the short-order floor | T-295-16 | RED (`teams == 2`) |
| drop `mock_completed` from `NON_INTENT_EVENTS` | T-295-17 | RED |
| revert the `next_pick` lever | T-305-01 | RED |
| `my_picks` filter → `by == "user"` | T-305-02 | RED |
| remove the route `mode` validation | T-305-03 | RED (bogus → 200) |
| raise conditional on `mode != MODE_MANUAL` | T-305-04 | RED |
| `next_pick` default → `MODE_MANUAL` | T-305-05 | RED |
| remove the `user_owner_id` echo key | T-305-06 | RED |
| append one CPU pick inside the manual path | T-305-07 | RED |

Standing-trap checks: every sabotage is a code-shape change, none of the named
tests is a raw-source scan (no comment-string false-green risk); anchors were
uniqueness-asserted before replace; apply/restore proven by `git diff`.

## Zero-egress proof

`git diff 3b64a44..HEAD` over the four backend code files: **zero** added
lines matching `urllib|requests|http|_sleeper_get|mfl_opener|fetch|urlopen|socket`,
and **zero** added imports in `mock_draft_service.py`. Every new read is
`sess` (in-memory) or the snapshotted row. The engine's structural guards
(import surface, `MockContext.fetchers()` raise) are untouched and still
pinned by T-W2-13.

## Fixture flag files

Unchanged by this lane (no new flags). Verified anyway:
`flags/release.json` ≡ `config/features.json` modulo the documented
`_comment_*` mechanism (non-comment delta: NONE); `profiles-on.json` /
`onboarding-v2.json` are release ± exactly their named deltas
(`profiles.public_pages`; the five onboarding-v2 keys). The pinning suite
`test_seed_ui_test_db.py` passes 76/76. `profiles/draft-pre.json`'s two-line
delta is the mobile lane's §8.3 pin (`712ad2e`), not this lane's.

## Wire-contract conformance (real captured responses, trimmed)

CPU create (`POST {league_id, rounds: 1, rng_seed: 6}`, mode absent) → `200`:
`status: "active"`, CPU picks 1–4 all `"by": "cpu"`,
`on_the_clock: {pick_no: 5, slot: 5, roster_id: "990000000000000042", is_user: true}`
(the caller, at their real slot), caller's rostered p29/p30 absent from
`undrafted`, and:

```jsonc
"settings_echo": {"rounds": 1, "type": "linear", "teams": 5,
                  "order_source": "randomized", "personas": {/* 5, incl. caller */},
                  "noise": {"bpa_prob": 0.1, "reach_decay": 0.7, "max_reach": 3.0},
                  "consensus_pool_size": 20,
                  "mode": "cpu", "user_owner_id": "990000000000000042"}
```

Manual create (same league, `mode: "manual"`) → `200`: `"picks": []`,
`on_the_clock: {pick_no: 1, round: 1, slot: 1, roster_id: "990000000000000103",
is_user: true}` (slot 1's owner — NOT the caller), `settings_echo.mode:
"manual"`, `user_owner_id` present.

Errors: `mode: "bogus"` → `400 {"error": "bad_mode"}` · phantom-user session →
`200 {"schema": 1, "empty": true, "reason": "user_not_in_draft"}` — exactly
three keys, both enforcement points byte-identical (T-295-09 ≡ T-295-13).

## Scope-block sections satisfied (backend lane)

- **API contract (bright-line):** §5 reproduced byte-exactly — POST `mode`,
  `settings_echo.mode` + `user_owner_id`, fourth rung, `bad_mode`, three-key
  POST typed-empty, GET `capability` ride-along carrying the fourth rung.
- **Analytics (bright-line):** registration-first commit, NON_INTENT rows
  same-commit, exact prop frozensets, T-295-17 pin. No emitters (mobile lane).
- **Tests:** 21-test plan's 20 backend rows green AND red-proven; fixture
  rewrite in its own commit with a full status diff; no route test hand-passes
  both `owners` and `user_owner_id` (T-295-01 derives them via the route).
- **Docs:** NONE touched — per the orchestrator's ownership ruling, the
  PRD §8 D1–D8 text (including the api-reference rows the LLD had assigned to
  this lane) is applied by the orchestrator. See defect note 3.

## PRD defects / deviations (report, not improvise)

1. **T-305-03's "byte-equal to a pre-change capture" is unsatisfiable.** The
   repair itself changed membership, and HLD §8 states the consequence: the
   same seed produces a *different draft* pre- vs post-repair. There is no
   pre-change capture the post-change create can byte-match. Pinned instead:
   absent / `null` / `""` / explicit `"cpu"` are ONE create — byte-equal
   `picks[]` for a fixed seed (the actual backward-compat property, and it
   goes red when the route validation is removed, as named). Recorded in the
   test docstring.
2. **T-295-16's named red (`teams == 2`) is unreachable as tabled.** With a
   user outside the 2-entry order (the natural reading), the sabotaged build
   hits the INV-6 raise before any `teams` assertion. The test uses an
   in-order user (`o1`) so the sabotage red is exactly `teams == 2`, and
   separately asserts a non-order owner joins the floored shuffle.
3. **Ownership conflict, resolved in the orchestrator's favour:** LLD §10 and
   PRD §8 mark `docs/api-reference.md` + `docs/cross-client-invariants.md`
   *(build commit)* under the backend agent, but the build brief explicitly
   forbids this lane touching any shared doc. Not applied here; D1–D7 remain
   for the orchestrator, verbatim in PRD §8.
4. **Unanticipated blast radius, handled:** the INV-6 raise + short-order
   floor invalidated the construction path of 15 existing ENGINE tests (tiny
   2–3-team assigned orders; phantom users used to force full-CPU drafts) —
   the PRD's §7.0 only anticipated route-fixture fallout. Resolved with the
   documented `make_state` harness patch (hand-built snapshots; guards pinned
   independently); one direct-call test moved to a 4-team shape.
5. **Local-DB hygiene gap (environment, not PRD):** the rewritten fixture
   makes route creates actually persist rows into the shared local
   `data/trade_finder.db`. The shared fixture therefore uses a QA caller id
   (never the operator's) and abandons its rows around every test; the two
   corpus e2e tests that MUST run as `313560442465169408` (the recorded
   leagues name that id) clean up the rows they create.

## Ambient notes for the orchestrator

- The mobile lane landed concurrently on this branch (`e31309a`, `fffcf08`,
  `712ad2e`, `83a1638`, mockups `67e25d0`). File ownership held — no file was
  touched by both lanes; the pytest delta is entirely this lane's.
- Q1 (analytics ownership): registration commit `6f0d44e` is isolated and
  revert-clean if the 2026-08-11 spun-out session's version surfaces first.
- Still owed by later phases (not this lane): Maestro on-sim runs + sim-gate
  tier (Q3), Tier-3 live verification, TEST_LEDGER/living-memory entries
  (proposed text is in PRD §8 / HLD §12), `npx tsc --noEmit` +
  `testid-lint.sh` (mobile lane reports these in its status doc).
