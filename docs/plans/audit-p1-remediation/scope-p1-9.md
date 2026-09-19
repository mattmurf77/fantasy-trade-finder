# Feature Scope — P1-9 · Quality-gated `trade_found` push (audit A-18)

<!--
Copied from docs/templates/feature-scope.md per CLAUDE.md §Conventions "Feature gates".
Every section is answered or explicitly WAIVED with a reason. Silence is not a waiver.
Plan: docs/plans/audit-p1-remediation/plan-p1-9.md
-->

**Date:** 2026-08-11
**Entry point:** 2026-08-09 mobile UX audit → `04-priority-backlog.md` §P1-9 / `06-resolutions.md` row **A-18**
**Builder:** planning agent, worktree `ftf-p1-remediation`, branch `p1-remediation-2026-08-11` off `origin/main @ ab9368f`
**Operator sign-off on waivers:** **PENDING** — waivers in §3 (the push leg is not Maestro-assertable) and §4 (six `n/a` rows), plus the seven operator checkpoints **OC-1…OC-7** in the plan. Surface all of them before build starts.
**Gate posture:** **FULL GATES.** Not a quick fix — a new feature-flag surface, two new cross-client enum values, and a notification that reaches a user outside the app. Per root `CLAUDE.md`, an agent never self-selects express.
**Sequencing constraint:** **P0-1 must merge to `main` first.** It is the prerequisite that makes push permission reachable for the default path, and the dry-run baseline is meaningless before it lands.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — plus one registered-but-never-fired event finally emitted. **No new event name is introduced**, so `plan-p0-7.md` §3's "register before you `track()`" ordering constraint does not bind here. Verified against the registries, not assumed:

  | Event | Status at `ab9368f` | What it answers here |
  |---|---|---|
  | `push_sent` (server-fired) | Live. `analytics_taxonomy.py:117`; fired from `_send_typed_push` (`backend/server.py:15403-15407`) with `props={"kind","dedup_key"}`. | Denominator. This feature contributes a **new value** `kind = "trade_found"`, not a new name. |
  | `push_opened` (client) | **Registered and dark.** `ALLOWED_CLIENT_EVENTS` `analytics_taxonomy.py:68`; `CLIENT_EVENT_PROPS` `:213` = `frozenset({"kind","dedup_key"})`. **Zero clients fire it** — `mobile/src/hooks/usePushNotifications.ts` has no `track()` call. `analytics_queries.py:478-501` renders `push_open_rate` permanently `"dark"`. | **Numerator — the only way to tell a rare push from a good one.** Wiring it needs **no** taxonomy commit: the name is already in the allowlist *and* has a props row, which is the exact pair `analytics_ingest.py` checks. |
  | `notif_pref_changed` (server-fired) | Live, `analytics_taxonomy.py:117`, fired at `backend/server.py:15528-15532`. | Opt-out rate — the cost side of the ledger. |

  **Blocking sub-change:** `_send_typed_push` builds the Expo payload as `{**(data or {}), "type": kind}` (`backend/server.py:15393-15399`) — `dedup_key` is capped and logged but **never sent to the device**, so `push_opened.dedup_key` would be permanently null. One-line additive fix (plan change #12), cross-cutting over all 13 live kinds, inert for clients (`data` is opaque except `type`/`match_id`/`league_id`).

  **`platform` discipline (plan-p0-7 rule):** neither event carries a `platform` prop. Device platform is a server-derived `user_events` **column** (`analytics_ingest.py:365-368`); `platform` as a *prop* means LEAGUE platform. Nothing here needs either.

  **INTENT / NON_INTENT (the deny-list hazard):** `push_opened` is **absent** from `NON_INTENT_EVENTS` (`analytics_queries.py:60-63`), so by the deny-list default it is **INTENT** and enters DAU/WAU/retention on first emission. **Deliberate, recommended: leave it INTENT** — a push open is a genuine return, and the incremental effect is ~nil because the resulting session fires intent events anyway. This is **OC-6**; if the operator prefers NON_INTENT it is a one-line edit to a **P0-7-owned** file and should be routed there, not made here. The emission date is a metric seam and goes in `CHANGELOG.md`.

  **Gate telemetry is operator-facing, not analytics.** `_run_trade_found_pass` returns per-reason counters (`candidates`, `blocked_cooldown`, `blocked_grace`, `blocked_seen`, `blocked_stale`, `pushed`, `dry_run_would_push`, `errors`) in the `POST /api/cron/daily-tick` response when the flag is on — the F10 `replenish` precedent (`backend/server.py:16159-16165`). No new event, no new table.

  → follow-through: `docs/data-dictionary.md` (new `notifications.type` and push-`kind` values — no schema change), `docs/cross-client-invariants.md` (the push-`kind` ↔ tap-routing map). **No tracking-plan addendum required** (`analytics_taxonomy.py:9-10` conditions that on *new client event types*), **but** `docs/business/analytics/2026-07-17-tracking-plan-v2.md:14` lists `push_opened` under *"documented but dark"* and that line becomes false — one-line correction.

- [ ] (a) New events specced — **n/a, none.**
- [ ] (c) WAIVED — **n/a, analytics are in scope and answered above.**

## 2. Schema & flag scope

**New/changed tables or columns: NONE.** No migration, no index. Every write lands in a table that exists:

| Table | Where | Used for |
|---|---|---|
| `notifications` (`backend/database.py:817-826`) | `create_notification` `:8439-8474` | The bell row — written **even when the push is suppressed** (OC-7). New **value** `type = 'trade_found'`. The column comment at `:820` currently enumerates `trade_match \| trade_accepted \| trade_declined` and is **already stale**; correct it in the same pass (A-33 rule). |
| `notification_events_log` (`:1249-1256`) | `log_notification_send` | Frequency + dedup caps. New **value** `kind = 'trade_found'`. |
| `notification_queue` (`:1259-1270`) | quiet-hours deferral | Unchanged mechanism. |
| `device_tokens` (`:1212-1218`) | `created_at` | The P0-1 grace guard (gate clause **G7**). |
| `trade_decisions` / `trade_impressions` | `load_recent_league_likes` `:4154`, `load_active_deck_user_leagues` `:4253`, `load_latest_trade_impression_batch` `:4284` | The gate's inputs. All existing loaders; **one new loader is not needed.** |

**New/changed feature flags: exactly ONE.**

| Flag | Default | Registration | What ON does | Graduation |
|---|---|---|---|---|
| `notif.trade_found` | **false** | `backend/feature_flags.py` `FLAG_KEYS` (notif block `:267-271`) + `config/features.json` (`~:123`, with a `_comment_notif_trade_found` block in house style) + `docs/config-reference.md` | Enables `_run_trade_found_pass` inside the existing `POST /api/cron/daily-tick`. OFF ⇒ **byte-identical** tick response, zero pushes, zero inbox rows, zero DB writes. | 14-day dry-run window with legible per-reason counters → operator device-unit allowlist → general. Full criterion in plan **OC-5**. |

**Why a flag at all** (the plan proposes no others): the change crosses a bright line — a notification leaves the building and reaches a user outside the app — so `CLAUDE.md`'s ship-the-knob rule wants a deploy-free kill switch. No existing flag's default changes.

**New env vars: none.** No new `CRON_SECRET` consumer, no new cron schedule, no `.github/workflows/render-cron.yml` change.

**New `model_config` keys: eight** — all Float-typed per the convention (`backend/database.py:1814`), declared in `backend/trade_service.py` `_DEFAULT_CFG` after the F10 block (`:369-373`), read through `_deck_cfg` (`backend/server.py:3074-3082`). **These are the deploy-free rollback levers**, and the reason thresholds are *not* flags:

`trade_found_max_age_days 7.0` · `trade_found_active_days 21.0` · `trade_found_cooldown_days 7.0` · `trade_found_global_quiet_days 5.0` · `trade_found_grace_hours 48.0` · `trade_found_min_like_age_minutes 30.0` · `trade_found_max_per_tick 50.0` · `trade_found_dry_run 1.0`

**Ship-the-knob, named:** two independent levers, neither needing a deploy — `notif.trade_found → off` (kill the pass entirely) or `trade_found_dry_run → 1` via `PUT /api/admin/config` (keep computing, stop sending). Both go in the runbook.

**Caveat carried into the build (plan change #5):** `_NOTIF_FREQ_CAPS` (`backend/server.py:15212-15217`) is a module-level literal read at import. The `trade_found` cap must be resolved **at call time** or the cadence knob silently becomes deploy-only. Do not let this pass silently.

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/p1-9-trade-found-inbox.yaml` — cold start → sign in → open the notification bell → assert a seeded `trade_found` inbox row renders (bounded regex on the title, not full copy — laws 1 + 12) → screenshot and eyeball the glyph (law 23) → tap the row → assert it lands on the Trades tab (this exercises `resolveNotificationTarget`, **the same routing table the push tap uses**, via `TopBar.onRowTap` at `:341-352`) → Settings leg asserting the opt-out row is reachable.
- [ ] **Extended flow:** none. Verified by `grep -rl` over `mobile/.maestro/`: no existing flow asserts a notification kind, a bell row, or the Settings notification block. The hits are `capture/*.yaml` screenshot flows plus `flows/espn-connect-capture.yaml`, none of which assert on this surface.
- [x] **WAIVED — the push leg itself is not assertable, with reasons:**
  - `usePushNotifications` returns early on `!Device.isDevice` (`mobile/src/hooks/usePushNotifications.ts:89`), so **a simulator never registers a token and never receives an Expo push**.
  - The iOS permission alert is a SpringBoard surface outside the app hierarchy — the identical waiver `plan-p0-1.md` §6.1 takes for the primer.
  - **Compensating coverage, three ways:** (i) the inbox row is written unconditionally by design (plan §Design, OC-7) and *is* assertable — that design choice exists partly to make this waiver defensible rather than convenient; (ii) 26 pytest cases drive the full gate + dispatcher server-side, including quiet-hours deferral and the exact Expo payload; (iii) one **real-device** send by the operator before graduating past dry-run (plan §Test plan → Mobile).
  - Any diff to the existing smoke flows invalidates this waiver — they are the regression proof.
- **`testID`s added:** `topbar.notif-bell` (the bell `Pressable` at `mobile/src/components/TopBar.tsx:~215-237` has **none** today) · `settings.notif.trade-matches`, `settings.notif.weekly-digest`, `settings.notif.reengagement`, `settings.notif.quiet-hours` (the `Row` helper accepts a `testID` at `SettingsScreen.tsx:1450-1459`; no caller passes one). Reused: `topbar.notif-row.<id>` (dynamic — `testid-lint.sh` matches on the static prefix). All registered in `mobile/src/components/CLAUDE.md`; `mobile/scripts/testid-lint.sh` must pass.
- **Capture delta:** the new `p1-9__trade-found-inbox-row` screenshot. **Plus `settings` and `settings@two-leagues` if and only if OC-1 lands the Settings copy edit** (the `trade_matches` row `sub` reads *"New matches, counter-offers, league activity"* and would otherwise be false). Run `mobile/scripts/screen-freshness.sh` and re-capture only what it flags.
- **Smoke-suite impact:** none of the 11 smoke flows crosses this surface (no notification, bell, or Settings-notification assertions anywhere). Expectation: all green and **unmodified**. Verify rather than assume.
- **Backend pytest:** new `backend/tests/test_trade_found.py` — 26 cases. **Eighteen of them assert ZERO pushes**, each isolating one gate clause by starting from the happy-path fixture and breaking exactly one thing (that construction is what makes a zero-push assertion non-vacuous). Highlights: **T-11** cross-kind quiet period vs `deck_replenished`; **T-13/T-14** the P0-1 grace + must-have-returned guard; **T-16** quiet-hours deferral into `notification_queue`; **T-17** dry-run writes nothing at all; **T-22** inbox row survives push suppression; **T-24** differential parity test for the `_likes_you_actionable` extraction; **T-26** regression that `new_match`'s payload is byte-identical apart from the added `dedup_key`. Must stay green: `test_notif_teardown.py`, `test_deck_replenishment.py`. Fixture work: `seed_ui_test_db.py` gains `matches_seed.likes_you` + a generic `notifications_seed`; new profile `fixtures/profiles/likes-you-waiting.json`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **Updated** | `POST /api/cron/daily-tick` — the optional `trade_found` counters object, present only when the flag is on. **No route added, renamed, removed, or contract-changed**; this mirrors how F10's `replenish` key is documented. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **Updated** | One convention shifts: *a push kind's cadence cap is a `model_config` key read at call time, not a literal in `_NOTIF_FREQ_CAPS`* — the first time that map is made live-tunable. |
| `docs/architecture.md` (module wiring / data flow changed) | **n/a** | No module added, removed or re-wired; no data-flow change. A new function inside an existing cron endpoint, using existing loaders and the existing dispatcher. |
| `living-memory/HLD.md` (architecture genuinely shifted) | **n/a** | No new module, client, or major flow. Deliberately rides `_send_typed_push` and `daily-tick` rather than building a parallel system. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **Updated** | **The load-bearing doc row.** Two new cross-client values — push `kind` `trade_found` (read by `deepLinks.ts` `V2_TRADE_KINDS`, the legacy set in `usePushNotifications.ts:200`, `TopBar.tsx` `ROW_GLYPHS`, and `web/js/app.js`'s notification renderer) and `notifications.type` `trade_found`. Record the **silent** failure mode: a client that misses the kind returns `null` from `resolveNotificationTarget` and the tap does nothing — no error, no log. |
| `docs/glossary.md` (new domain term) | **Updated** | *likes-you* / *counterparty intent* is used across the deck engine (`backend/server.py:2813+`) and now the notification layer, and is not defined. One entry. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **`DECISIONS.md`** (next live id — take it after P0-1/P0-7 land) | Three: (1) **the gate is counterparty intent only** — no model score may trigger a push without an explicit operator decision, and gate strength is coupled to the pref bucket (OC-1/OC-2); (2) the **inbox row is written even when the push is suppressed**, which is also what makes the feature simulator-testable; (3) **`trade_found` sits in `trade_matches`** (if OC-1 = A), with the coupling rule written down. No ADR — no architectural choice of ADR weight. |
| `docs/data-dictionary.md` | **Updated** | New values only (no schema change): `notifications.type` gains `trade_found` **and** its stale column comment at `backend/database.py:820` is corrected; the push-kind list gains `trade_found`. |
| `docs/config-reference.md` | **Updated** | Flag `notif.trade_found` (default, ON/OFF semantics, kill switch, graduation criterion) + the eight `model_config` keys with defaults and units. |
| `docs/runbook.md` | **Updated** | New subsection modelled on *"Weekly deck replenishment (F10…)"*: what the pass does, that it lives inside `daily-tick`, how to read the per-reason counters, how to run dry, both kill switches, and how to answer *"why did nobody get one this week?"* from `candidates` vs `blocked_*`. |
| `docs/design/design-system.md` + `components.md` | **n/a** | No new component and no new token. The NotificationRow glyph map already has a spec (#225); this adds one entry. Re-read both before touching `TopBar.tsx`, per `CLAUDE.md`. |
| `docs/business/analytics/2026-07-17-tracking-plan-v2.md` | **Updated (one line)** | `:14` lists `push_opened` as *"documented but dark"*; first emission makes that false. No addendum required (no new event name). |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | **On ship** | TEST_LEDGER carries the pytest run, the sim run, **and the dry-run observation-window result**. |
| `living-memory/DEPENDENCIES.md` | **n/a** | No dependency added, bumped, or removed. |
| `screens/CLAUDE.md` (screen library index) | **Conditional** | Only if OC-1's Settings copy edit lands and `settings` is re-captured. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a** | Dated artifact — record the outcome in CHANGELOG, don't rewrite the audit. |

## 5. Ship gate declaration

- **Simulator-gate tier:** **Tier 2** — *"Mobile logic touched, no UI change"*: the feature's own flow (`p1-9-trade-found-inbox.yaml`) + the affected smoke subset, plus `mobile/scripts/screen-freshness.sh` with re-capture of whatever it flags.
  **Escalates to Tier 1 if OC-1 = A**, because the Settings row copy change (plan change #18a) is a visible screen change and requires `mobile/scripts/screen-capture.sh --screen settings` (and `settings@two-leagues`). **The tier is therefore not final until OC-1 is answered** — declare it here before the build starts.
- **Evidence:** `living-memory/TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json` written after the run. `githooks/pre-push` enforces locally (`git config core.hooksPath githooks`).
- **Operator deviation from the matrix:** none proposed.
- **Open items that must be closed before build starts:** **OC-1** (bucket — also decides the sim tier, the Settings copy, and whether `PushPrimingModal`'s consent bullets need a fourth line per risk R3) · **OC-2** (gate strength) · **OC-3** (the eight defaults) · **OC-4** (copy and how much it reveals about a leaguemate — privacy, risk R4) · **OC-5** (rollout + graduation) · **OC-6** (`push_opened` INTENT vs NON_INTENT) · **OC-7** (inbox row when the push is suppressed). Full text in `plan-p1-9.md` §Operator checkpoints.
- **Merge-order constraint:** **after P0-1**, and the dry-run window starts no earlier than `trade_found_grace_hours` past P0-1's deploy. Also rebase after **P0-3** (`mobile/src/utils/deepLinks.ts`) and **P0-1** (`backend/tests/fixtures/seed_ui_test_db.py`).
