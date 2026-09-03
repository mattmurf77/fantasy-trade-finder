# Runbook

*Jump via the TOC — read sections, not the file.*

Operational procedures. Add to this as you learn things.


## Table of Contents

- [Local dev](#local-dev)
- [Deploy (Render)](#deploy-render)
- [Pre-ship simulator gate (2026-08-08)](#pre-ship-simulator-gate-2026-08-08)
  - [Risk-tier matrix (operator-owned; deviations are decisions, recorded in the feature's scope block)](#risk-tier-matrix-operator-owned-deviations-are-decisions-recorded-in-the-features-scope-block)
  - [Evidence](#evidence)
  - [Enforcement](#enforcement)
  - [Screen library (capture freshness)](#screen-library-capture-freshness)
  - [Failure symptom / lever](#failure-symptom-lever)
- [Database](#database)
- [Feature flags](#feature-flags)
- [Trade engine flags + kill switch](#trade-engine-flags-kill-switch)
- [Runtime tuning](#runtime-tuning)
- [Presentment-rules tripwire (`trade.presentment_rules`, G6 2026-08-16)](#presentment-rules-tripwire-tradepresentment_rules-g6-2026-08-16)
- [Negative-results memory (`trade.negmem`, 2026-08-22)](#negative-results-memory-tradenegmem-2026-08-22)
- [Debug log](#debug-log)
- [Verified-session grace monitoring (account-auth P1)](#verified-session-grace-monitoring-account-auth-p1)
- [Common failure modes](#common-failure-modes)
- [Cron schedule](#cron-schedule)
- [Weekly deck replenishment (F10, flag `deck.replenishment`, 2026-07-26)](#weekly-deck-replenishment-f10-flag-deckreplenishment-2026-07-26)
- [Reset / wipe](#reset-wipe)
- [HTTP compression / encoding (OBS-API-02)](#http-compression-encoding-obs-api-02)
- [Mobile UI-test harness (RETIRED 2026-08-15 — historical)](#mobile-ui-test-harness-retired-2026-08-15--historical)
  - [Harness build gotchas (2026-07-11)](#harness-build-gotchas-2026-07-11)
  - [Draft replay corpora (rookie-draft M1, 2026-08-06)](#draft-replay-corpora-rookie-draft-m1-2026-08-06)
- [Sign in with Apple — App Store Connect / Apple Developer setup (account-auth P2, 2026-07-11)](#sign-in-with-apple-app-store-connect-apple-developer-setup-account-auth-p2-2026-07-11)
- [Pick-value tier ladder migration (2026-07-11)](#pick-value-tier-ladder-migration-2026-07-11)
- [8-tier ladder + consensus seed recalibration (2026-07-12, feedback #117/#118)](#8-tier-ladder-consensus-seed-recalibration-2026-07-12-feedback-117118)
- [ESPN league linking — API fragility monitoring (`espn.link`, 2026-07-12)](#espn-league-linking-api-fragility-monitoring-espnlink-2026-07-12)
- [MFL + Fleaflicker league linking — monitoring (`mfl.link` / `fleaflicker.link`, 2026-07-18)](#mfl-fleaflicker-league-linking-monitoring-mfllink-fleaflickerlink-2026-07-18)
- [Bare workflow: `app.json` iOS config is silently ignored (feedback #131, 2026-07-12)](#bare-workflow-appjson-ios-config-is-silently-ignored-feedback-131-2026-07-12)
- [Universal Links AASA is CDN-cached by Apple (feedback #239, 2026-08-02)](#universal-links-aasa-is-cdn-cached-by-apple-feedback-239-2026-08-02)
- [Render cold starts — keep-warm cron (onboarding item 3, 2026-07-17)](#render-cold-starts-keep-warm-cron-onboarding-item-3-2026-07-17)
- [KTC consensus blend — source fragility + kill switch (#145/#148, 2026-07-17)](#ktc-consensus-blend-source-fragility-kill-switch-145148-2026-07-17)
- [Analytics platform P0 — WAL, wrapped cutover, kill switches (2026-07-17)](#analytics-platform-p0-wal-wrapped-cutover-kill-switches-2026-07-17)
- [Reading REAL analytics (prod, not dev) — 2026-08-05](#reading-real-analytics-prod-not-dev-2026-08-05)
- [Analytics platform P1 — ingestion pipeline + kill-switch latency (2026-07-18)](#analytics-platform-p1-ingestion-pipeline-kill-switch-latency-2026-07-18)
- [Render ignores render.yaml envVars on the dashboard-created web service (2026-07-19)](#render-ignores-renderyaml-envvars-on-the-dashboard-created-web-service-2026-07-19)
- [Offline eval harness — replay/IPS on the F1 impression spine (F8, 2026-07-26)](#offline-eval-harness-replayips-on-the-f1-impression-spine-f8-2026-07-26)
- [MFL numeric league ids wiped draft picks on session init (#200, 2026-07-27)](#mfl-numeric-league-ids-wiped-draft-picks-on-session-init-200-2026-07-27)
- [Sleeper-flake still wiped draft picks after the #200 fix (#220, 2026-08-01)](#sleeper-flake-still-wiped-draft-picks-after-the-200-fix-220-2026-08-01)
- [Player-cache refresh (rookie-draft M0, 2026-08-06)](#player-cache-refresh-rookie-draft-m0-2026-08-06)
- [Rookie-scope board restore (rookie-draft M2, 2026-08-06)](#rookie-scope-board-restore-rookie-draft-m2-2026-08-06)
- [Draft Room polling budget (rookie-draft M4, 2026-08-06)](#draft-room-polling-budget-rookie-draft-m4-2026-08-06)
- [Pick-assignment recovery (draft-extensions W3 M-A, 2026-08-08)](#pick-assignment-recovery-draft-extensions-w3-m-a-2026-08-08)
- [Pick-recording queue integrity (draft-extensions W3 M-D, 2026-08-08)](#pick-recording-queue-integrity-draft-extensions-w3-m-d-2026-08-08)
- [Quick Set unlock backfill (P0-1, 2026-08-11)](#quick-set-unlock-backfill-p0-1-2026-08-11)
- [Mobile UI-test identity seam — `FTFTestAppleSub` (P0-5, 2026-08-11)](#mobile-ui-test-identity-seam-ftftestapplesub-p0-5-2026-08-11)
- [Operator-only onboarding test — `trades_first_operator_test` (P0-9, 2026-08-11)](#operator-only-onboarding-test-trades_first_operator_test-p0-9-2026-08-11)
- [Retiring the onboarding experiment overlay — open-access Phase A (2026-08-15)](#retiring-the-onboarding-experiment-overlay--open-access-phase-a-2026-08-15)
- [Organic trade backfill (2026-08-16)](#organic-trade-backfill-2026-08-16)
- [ESPN identity binding — one-time cohort re-sign-in (#321, 2026-08-16)](#espn-identity-binding--one-time-cohort-re-sign-in-321-2026-08-16)

---

## Local dev

```bash
pip install -r requirements.txt
python run.py            # Flask on :5000
```

Mobile:
```bash
cd mobile && npm install && npx expo start --tunnel
```

Extension: `chrome://extensions` → developer mode → Load unpacked → pick `extension/`.

Port conflicts: macOS AirPlay Receiver uses :5000. Free it: `lsof -ti:5000 | xargs kill -9`.

---

## Deploy (Render)

`render.yaml` drives the deploy. Push to GitHub `main` and Render auto-builds.

- **Backend:** Python service runs `run.py`.
- **DB:** Postgres via injected `DATABASE_URL`.
- **Static:** `web/` served by Flask.
- Set `ANTHROPIC_API_KEY` in Render dashboard if smart matchups should be enabled in prod.

---

## Pre-ship simulator gate (2026-08-08)

> **RETIRED (2026-08-15, D-056 — extending D-P1-08).** Maestro/simulator work is retired
> **entirely**: no flow authoring, no runs, no captures, for any change. TestFlight is
> primary QA; automated evidence is `check-*.js` suites + unit tests; `FTF_SKIP_SIM_GATE=1`
> is the standing posture for the pre-push hook. Everything below is historical.

`main` auto-deploys (Render) and feeds EAS → TestFlight, so the Maestro/simulator check
sits **before merge/push to `main`**. CI cannot run the iOS simulator (no free macOS
runner), so the run is local and the enforceable artifact is the **evidence**, not the
execution — the operator keeps the decision, the system keeps the receipts.

### Risk-tier matrix (operator-owned; deviations are decisions, recorded in the feature's scope block)

| Tier | Change class | Required before merge to `main` |
|---|---|---|
| 1 | Mobile screen / navigation / state change | Full smoke suite (11 flows) + the feature's own flow, on sim **+ `mobile/scripts/screen-capture.sh --screen <touched>` for every screen whose visuals changed** |
| 2 | Mobile logic touched, no UI change | Feature's flow + affected smoke subset **+ run `mobile/scripts/screen-freshness.sh`; re-capture only the screens it flags** |
| 3 | Backend route/schema consumed by mobile | Smoke subset that exercises the route |
| 4 | Backend-only, web-only, docs-only | No sim run; pytest / `tsc --noEmit` (CI covers these) |

### Evidence

After the run, do both:
1. Append the result to `living-memory/TEST_LEDGER.md` (flows run, pass/fail, sim device, SHA).
2. Write `qa/sim-runs/last-sim-run.json` (gitignored, per-machine):
   ```json
   {"date": "YYYY-MM-DDTHH:MM:SSZ", "sha": "<commit tested>", "tier": 1,
    "flows": ["smoke/01", "..."], "result": "pass"}
   ```

### Enforcement

`githooks/pre-push` blocks a push to `main` that includes `mobile/src` changes unless
`qa/sim-runs/last-sim-run.json` records a passing run on a commit that is an ancestor
of what's being pushed. Install once per clone:

```bash
git config core.hooksPath githooks
```

Escape hatch (operator decision, deliberately loud): `FTF_SKIP_SIM_GATE=1 git push …`
— the hook prints that the gate was skipped; record why in TEST_LEDGER. This is
the intended mechanism for **express-lane** pushes (operator-declared quick
fixes — CLAUDE.md §Conventions "Feature gates" → "Rigor is an operator
decision"); a one-line ledger note (`express: <what> — gates skipped by
operator`) is the whole ceremony.

### Screen library (capture freshness)

`screens/` is the committed capture library: every mobile screen in every state
(`screens/mobile/<screen>/<state>.png`), taken hermetically from the real app on the
canonical simulator. It exists so design work starts from what the app *actually* looks
like instead of from memory. Two scripts own it — nothing else writes there:

| Script | Cost | What it does |
|---|---|---|
| `mobile/scripts/screen-freshness.sh` | < 1 s, no sim | Rehashes each screen's declared source files against `screens/manifest.json`. Exit `0` fresh · `1` stale · `2` no manifest. `--quiet` for scripting. |
| `mobile/scripts/screen-capture.sh --screen <x>` | 4–7 min, needs sim | Re-captures screen `<x>` in every state and rewrites its manifest entry. `--interactive` leaves the sim parked in that state instead. |

**Evidence is the manifest**, not the run: `screens/manifest.json` records each capture's
flow, profile, injections, `captured_at`, and the source-file hash that freshness compares
against. A screen is "captured for this change" exactly when its manifest hash matches HEAD.

The pre-push hook **warns, never blocks**, when a push touches `mobile/src/screens/**`
without any `screens/` path in the same range — capture freshness is a design-truth
obligation, not a ship blocker. The scope block's capture-delta row (§3 of
`docs/templates/feature-scope.md`) is where the intent gets declared up front.

Details, layout conventions, and the mockup-agent contract: `screens/CLAUDE.md`.
Prereq: `brew install pngquant` (the runner falls back to `sips` downscale with a warning).

### Failure symptom / lever

- Hook blocks unexpectedly → the marker is stale (different machine, or the sim run
  predates a rebase). Re-run the required tier; don't reach for the escape hatch first.
- Hook silent when it should block → `git config core.hooksPath` unset in this clone.
- Capture warning on every push → a screen's source moved but was never re-captured. Run
  `screen-freshness.sh` to see which, then `screen-capture.sh --screen <x>`.

---

## Database

- **Local:** SQLite at `data/trade_finder.db`. Back up by copying the file.
- **Prod:** Postgres via `DATABASE_URL`. Take a Render snapshot before destructive changes.
- **Schema source of truth:** `backend/database.py`.
- **Migrations:** No migration tool. `_migrate_db()` in `database.py` applies idempotent additive ALTERs and seeds `model_config` defaults via INSERT OR IGNORE on every startup. For destructive changes, write a one-off script and run it manually.

---

## Feature flags

- Edit `config/features.json` and commit/deploy, OR
- `POST /api/feature-flags/reload` to re-read without restart, OR
- Set `FTF_FLAGS` env var for process-level overrides.

---

## Trade engine flags + kill switch

The trade engine is selected by flags in `config/features.json` (reload via `POST /api/feature-flags/reload`, or override with `FTF_FLAGS`):

- `trade_engine.v3` — Tier 3 optimizer (`backend/trade_optimizer.py`)
- `trade_engine.v2` — Tier 1/2 scorer in `backend/trade_service.py`
- Tier 2 features toggle independently within v2: `trade.marginal_value`, `trade.outlook_blend`, `trade.likes_you`, `trade.fuzzy_match`, `trade.thompson_deck`, `trade.deck_diversity`
- `trade.three_team` — 3-team cycle cards (Tier 3)

**Kill-switch order** (bad cards / latency / errors after a trade-engine change):

1. `trade_engine.v3: false` → falls back to the v2 engine.
2. Still bad: `trade_engine.v2: false` → falls back to the legacy scorer (kept byte-for-byte unchanged).

No data migration either way; users just get the other engine's decks on next generate. See [ADR-002](adr/adr-002-trade-engine-v2-v3-rebuild.md) and [config-reference.md](config-reference.md).

**Offline validation scripts** (read-only, never write to the DB — run from repo root):

```bash
python3 -m backend.scripts.replay_trade_decisions   # regenerate historical decks legacy vs v2;
                                                    # reports precision@5, like recall, match@5,
                                                    # multi-player share, gen time
python3 -m backend.scripts.calibrate_elo_value      # Spearman check of elo_to_value(seed) vs
                                                    # dynasty_value(search_rank); PASS at ≥ 0.98,
                                                    # plus a grid/level-fit for elo_value_k
```

---

## Runtime tuning

`model_config` table is editable live (requires `X-Cron-Secret: $CRON_SECRET`):
```
curl -H "X-Cron-Secret: $CRON_SECRET" .../api/admin/config              # read all
curl -H "X-Cron-Secret: $CRON_SECRET" -X PUT .../api/admin/config/<key> # update one
```
See [config-reference.md](config-reference.md) for keys. All `/api/admin/*`
endpoints, `/api/debug/log`, and `/api/feature-flags/reload` share this auth.

---

## Presentment-rules tripwire (`trade.presentment_rules`, G6 2026-08-16)

Every trade job logs an INFO line `trade-job <id>: presentment kills={'R1':…,
'R2':…, 'R3':…, 'R5':…, 'R4':…} served=<n>` (R1/R2/R3/R5 are
construction-candidate kills — enumeration-scale numbers are normal; R4 is
distinct excluded keys; `served` is the post-ghost count). A WARNING with the
grep-able prefix **`presentment-tripwire`** fires only when a deck is thin
AND the rules' own kills explain the thinness (`served < 5 AND served +
rule_kills > 15`) — decks thinned by fairness/surplus never fire it.

Response: identify the dominant rule in the logged counters, then kill that
rule live (deploy-free) via `PUT /api/admin/config/<knob>`:
R1 → `max_overpay_frac = 0` · R2 → `pos_net_cap = 0` · R3 →
`pick_gap_frac = 0` · R5 → `need_gate_min_value = 0`. R4 has no knob; the
whole group reverts by flipping `trade.presentment_rules` to `false` in
`config/features.json` (one-line commit + deploy). Expect zero hits on
healthy leagues; contender-heavy leagues thin the most by design (#304 is a
contender complaint) — log any hit with its rule attribution in
`docs/feedback/items/304-positional-need-filter/status.md`.

---

## Negative-results memory (`trade.negmem`, 2026-08-22)

Feature docs: [`plans/negative-results-memory/`](plans/negative-results-memory/) ·
[ADR-015](adr/adr-015-negmem-soft-prior-not-fourth-filter.md) · knobs in
[config-reference](config-reference.md#negative-results-memory-flag-tradenegmem--trade_service_default_cfg-db-seeded).
Operator surfaces are **scripts, not routes**: `python3 -m backend.scripts.negmem_readout
--user <id> --league <id> [--as-of ISO] [--prod]` prints the §7.1 dump (the substance of
the [TestFlight checklist](plans/negative-results-memory/testflight-checklist.md)), and
`python3 -m backend.scripts.negmem_rfps` computes the graduation metric. Two pack queries:
`scripts/negmem-stamp-rate.sql`, `scripts/negmem-gr4-joint.sql`.

1. **negmem stamp-rate < 100% on allowlisted leagues while `trade.negmem` is ON** ⇒ map
   builds are failing silently (flag ON + no `negmem` keys is the failure signature —
   failure is in the data, never inferred from absence). **Triage order:** stamp rate →
   degraded notes (`negmem_note` on job dicts / `{degraded:true}` stamps) → the knob
   triple (`negmem_strength` / `negmem_floor` / `gen2_accept_prior_strength`).
2. **negmem degraded-rate > 1% of jobs over 24h** ⇒ set `negmem_strength = 0` and
   investigate; the measurement window is censored at the flip timestamp (PRD §8.3).
3. **Any PRD §8.3 guardrail breach at any time** ⇒ `negmem_strength = 0` (deploy-free). A
   breach plausibly originating in the acceptance prior additionally takes
   `gen2_accept_prior_strength = 0` (or rung 1: flag off) — **`negmem_strength` does NOT
   govern M2.**
4. **Kill M2 via the GLOBAL knob only** (`PUT /api/admin/config/gen2_accept_prior_strength`
   = 0, i.e. `scripts/set_knob.py`), **NEVER an arm overlay pin** — arm overlays are
   bake-off instruments, not kill switches, and the feed guard fires on the job-level
   GLOBAL read, so only the global knob verifiably empties the feed. A per-arm pin with a
   nonzero global leaves the feed populated and `acceptance_prior` computing the raw
   unshrunk ratio.
5. **Flag flips and every `negmem_*` / `gen2_accept_prior_*` knob move land at bake-off
   ROUND BOUNDARIES only** (GR3 — a mid-round flip censors the window,
   [ADR-014](adr/adr-014-bakeoff-serving-rounds.md)).
6. **GR4:** p5 of (`negmem_m` × `final_score`/`base_score`) on allowlisted non-bake-off
   rows **< 0.15** ⇒ raise floors. First check the known downward pollution (the diversity
   penalty rides the same ratio) before concluding real compounding.
7. **The stamp-rate query returns ZERO ROWS (empty denominator) while the flag is ON** ⇒
   the allowlist file is missing, unparseable, or empty — check the build warning log and
   the readout's `allowlisted` field before assuming build failures. (`config/negmem_leagues.json`;
   `["*"]` is the every-league wildcard.)
8. **"A partner's cards moved for one deck and then settled"** ⇒ likely a min-evidence
   crossing, not a bug: the curve steps at the threshold. Compare the readout's
   `n_decayed` for that partner's cells against `negmem_min_evidence` — a value hovering
   just either side confirms it. To soften the step, raise `negmem_sat_k` (step size =
   `(1 − negmem_floor)/(1 + negmem_sat_k)`: 0.10 at k=3, 0.05 at k=7, 0.02 at k=19);
   deploy-free, at a round boundary, and note that a higher k also flattens mid-range
   damping.

**Reading zeros.** `dropped_unmapped_partner_ids: 0` in the readout means "no count taken"
whenever `m2` reads `killed (…)` or `degraded` — the M2 queries never ran. Always read that
counter together with the `m2` annotation. Likewise `likes_net` is pre-clamp and
readout-only: `n_decayed + likes_net` does not reconstruct the gross evidence.

## Debug log

In-memory ring buffer (last ~200 entries; requires `X-Cron-Secret` — it leaks
usernames/user_ids/tracebacks, so it's operator-only):
```
curl -H "X-Cron-Secret: $CRON_SECRET" .../api/debug/log?n=100
```

> **Test users:** the `test_user_fp_*` username login bypass (`/api/sleeper/user`)
> is disabled in any non-SQLite (prod) environment. Seed test users only work
> against the local SQLite dev DB.

---

## Verified-session grace monitoring (account-auth P1)

While `auth.enforce_verified_writes` is **false** (grace), every mutating request from an unverified session emits exactly one log line in this stable format:

```
AUTH-GRACE unverified_write user_id=<uid> method=<POST|PUT|DELETE> path=</api/...>
```

Denials (verified controller exists / enforcement / hard route) log `AUTH-DENY unverified_write … reason=<verified_controller_exists|enforcement|hard_route>`; first-time verifications log `AUTH-VERIFIED first verified controller user_id=… via=sleeper`.

**Read gate (P2.5):** board-content reads from an unverified session whose user_id has a verified controller are denied the same way and log `AUTH-DENY unverified_read … reason=verified_controller_exists`. There is no read grace and no `AUTH-GRACE` read line — reads with no controller are simply allowed, so read denials only ever mean "squatter/second-device session for a verified account." Gated-route matrix: [api-reference.md §"The read gate"](api-reference.md).

The grace funnel (plan §2d — how many real users would P3 block?): grep Render logs (or `/api/debug/log`) for `AUTH-GRACE`, count distinct `user_id`s, and compare against `AUTH-VERIFIED` conversions. Flip the flag to true only when the unverified-writer count is ~0 or squatter-shaped.

| Symptom | Likely cause | Fix |
|---|---|---|
| Client gets 403 `{error: verification_required}` on writes | The user_id has a verified controller and this session isn't it (squatter / second device), or enforcement is on, or it's a hard route (`/api/trades/propose`, `/api/account/reset-rankings`) | Legit owner: re-run Connect Sleeper (SleeperConnectScreen) to verify this session. Squatter: working as designed |
| Client gets 403 `verification_required` on **reads** (rankings/tiers/trades/trends screens show "Verify your account to view your data") | Read gate (P2.5): the user_id has a verified controller and this session isn't it. Only ever fires post-verification — never during onboarding | Mobile: the VerifyAccountBanner appears automatically → Verify routes into SleeperConnect. Web/extension: no verification flow yet — the owner must use the verified mobile session (known limitation, carried to P3) |
| Nobody ever gets `verified: true` from `POST /api/sleeper/link` | The oracle probe (`verify_token_live`) is failing — look for `sleeper_link oracle inconclusive` (network/Cloudflare 1010: check `_BROWSER_HEADERS` still clears it) vs `oracle rejected` (Sleeper changed token semantics) | Same debugging surface as Send-in-Sleeper propose failures — see the capture runbook §C2 |

---

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Smart matchup returns boring pairs | `ANTHROPIC_API_KEY` not set, or `smart_matchup_enabled=0` | Set the env var; flip the config |
| Tier colors disagree across clients | Drift in tier color tokens | See [cross-client-invariants](cross-client-invariants.md) |
| Trade Finder still locked after many ranks | Per-position threshold not met (10 each) | Rank more of the missing position |
| Empty deck only when `trade_engine.v3` is on (v2 returns cards) | v3 enforces lineup feasibility (`_STARTER_NEED` QB1/RB2/WR2/TE1) all-or-nothing: a roster that can't field a full lineup at every position makes *every* trade infeasible → zero v3 cards | Confirm the roster covers all four positions; a thin/incomplete roster (or a player-pool sync gap dropping a position) yields no v3 trades by design (TC-ENG-002) |
| Mobile can't reach backend | Not on tunnel; backend on different network | Run Expo with `--tunnel` |
| Push notifications not arriving | No `device_tokens` row, or pref bucket off, or quiet hours active | Check `notification_prefs`, `device_tokens`, and `notification_queue` for the user |
| Queued pushes never deliver | Cron ticks not firing | Verify Render cron schedule hits `/api/cron/*-tick` |
| Duplicate pushes for same event | `dedup_key` not set or differs across calls | Ensure `_send_typed_push` is given a stable `dedup_key` |
| "Action failed" on Matches Accept (feedback #8 → #35/#36 → #77) | Mobile builds ≤1.3.0 render Accept/Decline on **every** match tile — including already-decided ones (list shows all statuses, tiles never show decision state) — and surface any non-2xx as a generic "Action failed" toast. First tap 200s; every later tap on the same match hit the route's blanket `409 already_decided`. (The 2026-06-08 FB-01 fix removed the 500/KeyError class; the 409 was the residual case.) | Fixed 2026-07-09 server-side so old clients heal without an app update: re-sending the *same* decision → idempotent `200` (no second ELO signal); only a *conflicting* decision → 409. Current clients replaced Accept/Decline with Dismiss + Send in Sleeper (c079c91), so the route now mainly serves old builds + web |
| "Awaiting them" segment always empty on Matches (found via feedback #91) | `load_awaiting_trades` ordered `trade_matches` by a nonexistent `created_at` column (its timestamp is `matched_at`) → `AttributeError` for any user with ≥1 like, which the `/api/trades/awaiting` route's blanket `except` swallowed into `[]`. Silent because the route logs only a warning and the empty state looks legitimate | Fixed 2026-07-10 (`order_by matched_at`). Lesson: a bare-array endpoint that catch-alls to `[]` hides hard failures — check server logs for `get_awaiting_trades error` before trusting an empty segment |
| Suggested/default tiers absurd — dozens of "Elite" players, or stars defaulting to Depth/Bench (feedback #60/#69, "44 elite QBs") | Three stacked causes: (1) FB-76 — SF boards bucketed with 1qb_ppr thresholds (fixed 81a1934/b11a3d1, 1.3.0); (2) `apply_reorder` respread the whole board **linearly** from pool max→min, flattening the convex consensus value curve so any full Manual Ranks session pushed the top third of a position above the Elite floor; (3) `tier_config.json` bands were never calibrated to the consensus seed scale (then `elo = 1200 + value/10000×600`; since 2026-07-12 `data_loader.seed_elo_for_value`) — DP values decay steeply, so Starter/Solid sat nearly empty and e.g. the consensus TE1 defaulted to "Depth" in SF | Fixed 2026-07-10: `apply_reorder` now permutes existing Elos (occupancy-invariant), and bands recalibrated per (format, position) to rank-count targets (Elite ≈ top 5). Guardrail: `backend/tests/test_tier_occupancy.py` pins per-position occupancy against a checked-in DP snapshot — if consensus drifts far, refresh the fixture and re-tune `tier_config.json` |
| League tab Pending/Accepted tiles disagree with the Matches list (feedback #91) | Tiles counted `trade_matches` rows split by disposition status (`pending`/`accepted`) and ignored per-user dismissal, while the Matches list shows all statuses minus dismissed — so one match could read as a "trade available" under both labels (e.g. a pending match you'd already accepted your side of + a dismissed accepted match) while the inbox showed one entry | Fixed 2026-07-10: tiles renamed to "Mutual matches" / "Awaiting them" and re-backed by `matches_mutual` / `matches_awaiting` in `/api/league/summary`, which mirror the Matches screen's segments exactly (see `test_league_summary_buckets.py`). Legacy keys still emitted for pre-1.4 builds |
| Trios keep serving the same top players (feedback #97, "Bijan/Gibbs/Jeanty way too frequently" — persisted after raising `trio_repeat_avoid` live to 8) | Selectors were deterministic *within* each strategy, and the top of the board is a tiny pool (elite ≈ 5 members; ~2+4 straddlers at the elite/starter edge within the ±60 margin): within-tier always took the tier's max/min-Elo (the #1 RB headlined every elite trio); the within-tier cursor started at *elite* on every service rebuild while anti-repeat state is in-memory (every app session opened on the same elite trio — no config value can fix a cross-restart repeat); small tiers fully inside the avoid window relaxed all-or-nothing and re-served the identical trio | Fixed 2026-07-10 (`ranking_service.py`): random cursor start per rebuild, extremes/straddlers sampled from the top-2 eligibles, partial avoid-relaxation (longest-unseen first), random edge tie-break; `trio_repeat_avoid` seeded default aligned to the live prod value (8). Live-tuning note: `trio_repeat_avoid` only suppresses repeats *within* one server lifetime — cross-session repetition is a code (selector-randomisation) concern, not a knob. Guardrail: FB #97 tests in `test_trio_variety.py` |
| Consensus QB values "look like the wrong format" (bugs #113 "1QB reflects SF valuations" / #106 "Maye QB2 in 1QB but QB9 in SF") | Investigated 2026-07-11: **not a mapping bug.** The whole pipeline (`data_loader.DP_SCORING_PARAM` → `_ensure_universal_pools` → `/api/trade/values` / `_consensus_pos_ranks`) was verified per-format end-to-end; the served numbers exactly mirror the DynastyProcess source (`value_1qb` / `value_2qb`), which is internally consistent with FantasyPros' own per-format ECR (Spearman 1.0). Maye QB2-in-1QB / QB9-in-SF is genuinely what FantasyPros' two dynasty expert pools say (they diverge on youth-vs-proven QB ordering) — an upstream data characteristic, not a crossed pool | To re-verify quickly: the cross-position fingerprint is decisive — a correct 1QB pool has ~1 QB in the overall top-20, a correct SF pool ~10. Hit `GET /api/trade/values?scoring_format=…` for both formats and count QBs in the top 20; also compare against the raw CSV columns at `dynastyprocess/data files/values-players.csv`. Guardrail: `backend/tests/test_dp_format_mapping.py` pins the column mapping, per-format column reads (mocked CSV), and the top-20 QB-share fingerprint of the checked-in snapshot |
| A scoring format serves no consensus values / trade values / tier seeds after a boot that coincided with a GitHub outage | `_ensure_universal_pools` used to cache a failed DynastyProcess CSV fetch as an empty pool (`{"players": [], "seed": {}}`) — the truthy dict passed the idempotency check, so the format stayed degraded until process restart | Fixed 2026-07-11: an empty DP values map is treated as fetch failure — nothing cached, retry allowed after a 60s backoff (`_DP_FETCH_RETRY_SECONDS` in `backend/server.py`), so the pool self-heals on a later request. `_get_universal_pool` also now logs an error for unknown format keys instead of silently serving the 1qb_ppr pool. Guardrail: `backend/tests/test_universal_pool_retry.py` |

---

## Cron schedule

External scheduler (Render cron) must hit:

| Endpoint | Recommended cadence |
|---|---|
| `POST /api/cron/realtime-tick` | every 1–5 min |
| `POST /api/cron/hourly-tick` | hourly (top of hour) |
| `POST /api/cron/daily-tick` | once daily |
| `POST /api/cron/value-snapshot` | once daily |
| `POST /api/cron/players-refresh` | once daily (see **Player-cache refresh** below) |

If these stop firing, queued pushes pile up in `notification_queue` and digests/re-engagement go silent.

**Sweep scope (2026-09-03).** Both league sweeps are now bounded: the hourly draft-status queue and the weekly roster-snapshot work-list only return leagues whose `leagues.updated_at` is inside `database.ACTIVE_LEAGUE_WINDOW_DAYS` (30 — stamped by `upsert_league` on every `session_init`), so a league nobody opens any more stops costing platform reads. `POST /api/cron/roster-snapshot` passes `active_within_days=None` and still sweeps everything; per-league forcing is `_refresh_league_draft_status(league_id, force=True)`, which skips the cheap-skip entirely.

The `not_drafted` draft-status TTL is also season-gated: 3 h inside the rookie-draft window (`_ROOKIE_DRAFT_WINDOW_*`, Apr 1 – Sep 15 UTC — dynasty rookie drafts cluster May–Aug) and 24 h outside it, since an undrafted league cannot flip out of season. `drafted` (12 h) and `unknown` (1 h) are unchanged.

**`value-snapshot` monitoring (#57):** the daily job upserts ~1,369 rows (≈684 `1qb_ppr` + 685 `sf_tep`); the response is `{"ok": true, "snapshot_date": "...", "1qb_ppr": N, "sf_tep": N}`. A day with no row written is value-history permanently lost (the universal pool is rebuilt from the live DP CSV each boot, so there is no backfill). If the job misses a day, that gap stays a gap — accept it; do **not** fabricate history. Verify it's firing by checking `player_value_history` has rows for today's UTC date. Idempotent, so re-running same-day is safe. **2026-07-26 (market-data readiness):** the endpoint was never provisioned in `render.yaml`. A dedicated `value-snapshot-daily` cron was added but **broke Render blueprint sync** (new blueprint cron = new billable resource needing approval) and was removed same-day. The operative mechanism is the **`hourly-tick` idempotent fallback guard**: it writes today's snapshot whenever any format is missing (response gains a `value_snapshot` key when the fallback ran), so cadence is guaranteed by the existing hourly cron alone — a lost day requires hourly-tick down ~24h. If a dedicated cron is ever wanted, create it manually in the Render dashboard rather than via blueprint.

**`roster-snapshot` monitoring (ADR-011, 2026-08-14):** the weekly league-state sweep (Writer B) rides `daily-tick` behind the `FTF_ROSTER_SNAPSHOT_WEEKDAY` `>=` gate; on-sync capture (Writer A) needs no scheduler at all. **The `source` column is the liveness instrument** — one week after ship, run:

```sql
SELECT source, count(*) FROM league_roster_history GROUP BY 1;
```

| Reading | Meaning | Action |
|---|---|---|
| `'weekly'` rows covering ≥95% of synced leagues, two consecutive weeks | Scheduled path proven live | Question retired. The manual route stays as the operator lever |
| **Zero `'weekly'` rows after one week** | `daily-tick` is not firing | Escalate the cron migration; until it lands, run `POST /api/cron/roster-snapshot` by hand weekly (CRON_SECRET). Writer A keeps capturing throughout |
| `'weekly'` present but <95% coverage | Sweep budget too small, or the daemon is dying | Read the per-league `roster-sweep: … fetch_ms=` log lines (emitted from day one) and raise `_ROSTER_SNAPSHOT_SWEEP_BUDGET`. **The budget and the daemon thread are a pair** — anyone removing the daemon must drop the budget to ~10 in the same change |

Same gap rule as value-snapshot: **a missed week stays a gap — never fabricate history** (and never write a snapshot from `league_members`, which is client-posted and possibly stale; the sweep fetches live). ESPN-private skips surface as `espn_reconnect` bell rows to the linking user plus `skips` counters in the sweep log — an expired cookie is a visible re-auth ask, not a silent hole.

---

## Weekly deck replenishment (F10, flag `deck.replenishment`, 2026-07-26)

Runs **inside** `POST /api/cron/daily-tick` — no separate schedule. Dark by default; flag off is byte-identical (no work, no pushes, no `replenish` key in the tick response).

- **Weekly gate:** the pass unlocks when `now.weekday() >= replenish_weekday` (`model_config`, default `2` = Wednesday, chosen post-waivers). The gate is `>=` on purpose: a missed Wednesday cron run self-heals Thu–Sun. **Tune the day** by setting the `replenish_weekday` model_config key (0 = Monday … 6 = Sunday); no deploy needed.
- **Idempotency:** one `deck_replenish_log` row per (user, league, ISO week) is written *before* the push; reruns in the same week skip both regeneration and push. The `deck_replenished` dedup key (`{league_id}:{iso_week}`) is a second, independent 1/week/league backstop in `notification_events_log`.
- **Eligibility:** user-leagues with a trade disposition or deck generation in the trailing 30 days (`load_active_deck_user_leagues`). Everyone else is untouched — no zombie churn.
- **Generation:** the existing job machinery, run synchronously per pair — a live session is reused when present, otherwise a headless session is rebuilt from `league_members` + replayed swipes. Decks land in the normal 30-min pre-gen cache (`_PREGEN_TTL_SECONDS`), so a push tapped hours later triggers a normal fresh generation rather than serving the cached one — acceptable; the push copy claims inventory, not a frozen deck.
- **Push policy:** kind `deck_replenished`, **reengagement bucket** — with `notif.reengagement_default_off` on (the shipping default) users must have opted in. Empty decks write the marker but never push; the expired-card count appears in copy only when > 0.
- **Monitoring:** the tick response's `replenish` object (`eligible / generated / pushed / skipped_done / errors`). `pushed` counts dispatcher *attempts* — preference-gated skips still decrement nothing there; check `notification_events_log` kind `deck_replenished` for actual sends. Sustained `errors` usually means a league whose `league_members` rosters were never persisted.

---

## Reset / wipe

```
POST /api/reset
```
Wipes the current user's `swipe_decisions`, `trade_decisions`, `member_rankings`.

---

## HTTP compression / encoding (OBS-API-02)

React Native's `fetch` auto-negotiates `Accept-Encoding: gzip, deflate, br` on every request. Cloudflare and Render both compress at the edge, so JSON responses are gzip-compressed in transit without any Flask-side configuration. The mobile app uses `/api/warm` (a lightweight ping) instead of fetching the full player payload on startup, so the largest payload (`/api/players`) is only fetched on first-run or after a 24-hour staleness. No additional Flask middleware is needed for current load; add `flask-compress` only if a new heavy endpoint is introduced that bypasses edge caching.

## Mobile UI-test harness (RETIRED 2026-08-15 — historical)

> **RETIRED (2026-08-15, D-056).** Maestro and the simulator are retired entirely: no flow
> authoring, no flow execution, no `screens/` captures, for any change in any pipeline.
> The `/maestro-test` skill is superseded and should not be invoked. Everything in this
> section is kept as a record of how the harness worked, not as instructions.
>
> **What to do instead:** structural `mobile/tests/check-*.js` suites + unit tests for
> anything mechanically checkable, a file:line-cited code-walk proof otherwise, and a
> manual TestFlight checklist when runtime proof matters. `mobile/scripts/testid-lint.sh`
> still runs in CI. See `docs/templates/feature-scope.md` §3.
>
> **Still live from this section:** the `testID` registry in
> `docs/plans/mobile-testing/lld.md` Appendix A, which `testid-lint.sh` reads.

Spec: `docs/plans/mobile-testing/` (plan/prd/hld/lld/test-cases). Day-to-day driver was the `/maestro-test` skill (`.claude/skills/maestro-test/SKILL.md`) — feature / page / whole-app scopes, encoded the traps below. Built so far: backend seams + blueprint (`backend/test_support.py`, seams in `server.py` — all env-gated, `pytest backend/tests/test_test_support.py` pins them incl. inertness), build contract (`mobile/app.config.js`), scripts (`mobile/scripts/sim-build.sh`, `sim-run.sh`, `testid-lint.sh`), S1-spike testIDs (SignIn + tab bar).

- **Test build:** `./mobile/scripts/sim-build.sh --env test` → Release sim app pointed at `http://127.0.0.1:5000`, Sentry DSN nulled, `resolved-config.json` emitted for the rails. `--env prod-check` statically asserts the shipping config (never builds).
- **Boot a hermetic cell:** `./mobile/scripts/sim-run.sh --udid <UDID> --app <path/to/.app> --profile standard` → seeds the profile, starts Flask in test mode, handshakes `/__test__/whoami`, erases+boots the sim, installs + launches. Without `--flow` it stops there (manual/S2 verification); with `--flow` it runs Maestro (once installed: `brew install maestro`).
- **Rails that fail closed:** backend won't START in test mode without `FTF_SLEEPER_FIXTURES_DIR` + `FTF_PLAYERS_CACHE_FILE`; a Sleeper fixture miss raises 599 (never a live call); `/api/trades/propose` returns 599 under test mode; `sim-run.sh` exits 3 on a non-localhost build, 4 if any guardrail counter is nonzero at run end, 5 on an unparseable `--flags` argument (inline JSON or `@file`; a missing/malformed file is a hard failure, never a warning), and 2 if the flags the run pins do not match what `/api/feature-flags` serves — the mismatch names the divergent keys. `--flags` **merges** over the profile's seeded flag map; it does not replace it.
- **Danger to know:** `FTF_PLAYERS_CACHE_FILE` exists because the default players-cache path (`data/.sleeper_players_cache.json`) is shared with real dev — never run the seeder or a test-mode Flask without it.
- Env vars: see `docs/config-reference.md`. Test-only routes: see `docs/api-reference.md` § Test support.

### Harness build gotchas (2026-07-11)
- **`Build input files cannot be found: …expo/node_modules/expo-font/…`** — stale Pods referencing a pre-dedupe node_modules layout. Fix: `cd mobile/ios && LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 pod install`. The locale matters: CocoaPods crashes with `Unicode Normalization not appropriate for ASCII-8BIT` in non-UTF-8 (non-interactive/agent) shells.
- Release sim builds run `ONLY_ACTIVE_ARCH=YES ARCHS=arm64` (set in `sim-build.sh`) — the default Release config also builds x86_64, which is slower and unneeded for local sims.
- **`bash: /Users/…/Fantasy: No such file or directory` in the EXConstants "Generate app.config" phase** — the project path contains spaces ("Fantasy Trade Finder") and `EXConstants.podspec` builds an unquoted `bash -l -c` command. Fixed durably by the quoting hook in `mobile/ios/Podfile` `post_install`; re-runs of `pod install` keep the fix. If an expo-constants upgrade changes the phase, the hook no-ops (guarded) — re-check quoting.
- When wrapping `sim-build.sh` in a pipeline, capture its exit code directly — `… | tail` reports the pipe's status, not the build's (this bit us once: a "0" that was actually a failed build).

### Draft replay corpora (rookie-draft M1, 2026-08-06)

The same `FTF_SLEEPER_FIXTURES_DIR` seam backs the Draft Room's offline test matrix. Corpora + full inventory: `backend/tests/fixtures/draft/README.md`; replayer: `backend/tests/support/draft_replay.py`; tests: `backend/tests/test_draft_replay.py`.

- **Record mode refuses a non-empty dir.** `server.py` exits if `FTF_SLEEPER_RECORD=1` and the fixtures dir already holds any `**/*.json` — never a silent overwrite. So **record one corpus per directory**, into a fresh temp dir, then move it under `backend/tests/fixtures/draft/`. Record mode is deliberately live and cannot run with `FTF_TEST_MODE=1`.
- **Live-recorded corpora (2026-08-06):** Sleeper `lakeview-complete` (complete, 48 picks, real order) and `ffv3-predraft` (`draft_order:null` + the identity `slot_to_roster_id` trap); MFL `draftResults` grids for all four states — 0/60, 36/72, 30/30, and a 2-`draftUnit` 192/192. `startup-shaped`, `empty-drafts` and `players-bulk` are derived/authored and say so in their manifests.
- **MFL is a different seam.** No env fixture dir — `mfl_service` injects `_opener`, so MFL corpora are committed `draftResults.json` snapshots served by `draft_replay.mfl_opener()`. Any MFL path in `draft_board_service` must thread `_opener` all the way down or M5 becomes untestable.
- **`DraftReplay` mutates a temp copy**, never the committed cassettes (pinned by a test). `truncate_picks(k)` also moves `status`/`last_picked` on *both* copies of the draft object — the `/league/<id>/drafts` list and the `/draft/<id>` detail — because Sleeper serves the same draft twice and a fixture that lets them drift is a fixture that lies.
- **Sleeper picks have no timestamps** (live-verified). `last_picked` exists only on the detail object, so the replayer synthesises a monotonic ladder anchored to the recorded value; `truncate_picks(total)` reproduces the cassette byte-for-byte.
- **Known-red, on purpose:** `test_m1_04_bulk_players_fetch_is_intercepted_by_the_fixture_seam` is a `strict=True` xfail. `_ensure_sleeper_cache_populated` fetches the ~5 MB `/v1/players/nfl` dump with raw `urllib`, so the fixture seam cannot see it ([RV-3]). M0's one-line fix — route it through `_sleeper_get` — flips it to XPASS, which under `strict=True` fails the suite until the marker is deleted. That is the handoff, not a bug.

## Sign in with Apple — App Store Connect / Apple Developer setup (account-auth P2, 2026-07-11)

The `auth.accounts` surface ships dark. Before flipping the flag ON (and before any TestFlight build exercises the Apple button), the operator must complete these one-time steps — none of them are automatable from this repo:

1. **App ID capability** — [developer.apple.com](https://developer.apple.com/account) → Certificates, Identifiers & Profiles → Identifiers → `com.fantasytradefinder.app` → check **Sign In with Apple** (as primary App ID) → Save. Without this, `AppleAuthentication.signInAsync` fails with an entitlement error on device.
2. **Rebuild via EAS** — the `expo-apple-authentication` plugin + `ios.usesAppleSignIn: true` in `app.json` add the `com.apple.developer.applesignin` entitlement; EAS regenerates the provisioning profile automatically on the next `eas build` after step 1. No Services ID or Sign-in-with-Apple *key* is needed for the native-app flow (those are only for web/Android OAuth redirects).
3. **App Store Connect privacy** — App Privacy section: declare the new identifier data ("User ID" linked to the user) and update `web/privacy.html` to cover Apple/Google `sub` storage (plan §4 → #114 owner). The current privacy policy states "no email addresses" — we store only a SHA-256 `email_hash`, never the raw email; keep it that way or amend the policy.
4. **Guideline 4.8 pairing** — if Google sign-in ever ships (`GOOGLE_OAUTH_CLIENT_ID` + un-stubbing the mobile flow), Apple must be live in the same release.
5. **Account deletion review note** — Guideline 5.1.1(v): point the reviewer at Settings → Account → Delete account (works regardless of the `auth.accounts` flag).

Verification-by-hand after setup: TestFlight build → Sign in with Apple on the sign-in screen → link a Sleeper username → Settings shows "Signed in with Apple"; delete a throwaway account and confirm `DELETE /api/account` returns the per-table counts in the server log.
- **Port 5001, not 5000, for the harness** — macOS AirPlay Receiver (ControlCenter) listens on :5000; `run.py` now honors `PORT`. Test builds bake `http://127.0.0.1:5001`.
- **"no stored swipe history" against a freshly seeded DB** — a stale Flask (or one started mid-reseed) raced the seeder's atomic rename. Kill all `python3 run.py`, seed, THEN start Flask (sim-run.sh's order). Restarting cleared it in the S2 drill.
- **Sentry build phases** — test builds set `SENTRY_DISABLE_AUTO_UPLOAD=true` (sim-build.sh); the pbxproj bundling + debug-symbols phases carry space-in-path quoting fixes and a skip-branch bypass (see the `post_install` hook in mobile/ios/Podfile and the phase scripts — re-check after any `@sentry/react-native` upgrade or expo prebuild).
- **EXConstants embedded app.config** — the phase now calls `getAppConfig.js` directly (Podfile hook) because the stock script's unquoted `basename $PROJECT_DIR` silently no-ops on spaced paths, leaving the PROD apiBaseUrl in test builds. Verify after expo-constants upgrades: `find <app> -name app.config` must exist and carry the localhost URL.

## Pick-value tier ladder migration (2026-07-11)

The user-facing tier taxonomy changed from the abstract five (`elite/starter/solid/depth/bench`) to the six-tier **pick-value ladder** (`firsts_2plus / first_1 / second / third / fourth / bench` — labels "2+ 1sts" / "1st" / "2nd" / "3rd" / "4th" / "Bench"), bands uniform across positions/formats in Elo space (floors = anchor-ladder rungs; see `docs/cross-client-invariants.md`). **Superseded one day later by the 8-tier revision below** — kept for the mechanism notes, which still apply.

- **No DB migration ran and none is needed:** `users.tier_overrides` stores raw Elo per player (never tier keys), so every saved board re-buckets through the new `tier_config.json` walk on read. Zero data loss; a board saved under the old bands renders in the nearest pick-value tiers automatically.
- **Deploy ordering:** backend first is safe — old mobile builds that still POST old tier keys to `/api/tiers/save` get a silent no-op per unknown key (`apply_tiers` skips keys without a band). Ship the mobile/extension updates promptly so saves work again; web is served by the same deploy. Mobile's offline fallback bands are baked per build — pre-update apps show old labels until updated (cosmetic only; the live `/api/tier-config` fetch corrects bounds).
- **If occupancy ever looks wrong** (e.g. an empty "1st" tier for 1QB QBs): that can be correct — the ladder states real pick value and 1QB QBs are rarely worth a 1st. The guardrail is `backend/tests/test_tier_occupancy.py` against the checked-in DP snapshot.

## 8-tier ladder + consensus seed recalibration (2026-07-12, feedback #117/#118)

The ladder was revised to eight tiers (`firsts_4plus / firsts_3 / firsts_2 / first_1 / second / third / fourth / waivers` — "4+ 1sts" … "Waivers"; `firsts_2plus`→`firsts_2`, `bench`→`waivers`) **and** the DP→Elo consensus seed map was recalibrated in the same change. The old linear map (`elo = 1200 + dp/10000 × 600`) capped consensus at Elo 1800 ≈ 2.1 firsts — a calibration artifact that made the 3+/4-firsts rungs unreachable and priced a mid 1st at ~47% of the top asset (real dynasty markets: ~25–30%). The new map (`data_loader.seed_elo_for_value`) reads DP as a linear trade-value scale: DP maps affinely onto the value space (DP 0 → Elo 1200 unchanged; DP 10000, clamped, → the 4-firsts rung ≈ Elo 1927.3), then back through the exponential Elo↔value curve, which is untouched.

- **`player_value_history` WAS migrated** (`database._migrate_db`, one-time, marker-guarded via `model_config.value_history_seed_scale = 2.0`): pre-recalibration rows stored old-scale `consensus_elo`/`consensus_value`; the FB-61 30d trend baseline and the profile tier timeline would otherwise mix scales and emit garbage deltas. The old map is invertible, so rows were rescaled in place (recover DP from the linear map, re-apply the new map) inside a single transaction; the marker insert is the atomic claim, so concurrent boots can't double-apply. Chart continuity and all-time highs/lows are preserved on the new scale. If the migration ever needs a re-run (e.g. restored backup), delete the marker row first.
- **Personal `elo_history` rows were NOT rescaled** (watch item): personal Elo = seed + swipe deltas, which has no closed-form inverse. Personal risers/fallers deltas spanning the recalibration date are distorted for ~the trend window (30d) and then age out. Accepted; revisit only if users report nonsense trends past early August 2026.
- **Anchor scale default moved 2 → 4** (`ANCHOR_TOP_TIER_FIRSTS_DEFAULT`, γ = log 4 / log N): at the default the anchor Elos are byte-identical to before, so no user-facing pin moved; stored non-default `users.anchor_scale` values keep their meaning (see cross-client-invariants → Pick anchor keys).
- **Trade-engine side effects** (quantified in the #117 item folder): fairness is a consensus package-value ratio; player values are now affine (not exponential) in DP value, so mid-market 1-for-1s read fairer (e.g. dp 6000 vs 8000: 0.55 → 0.76) and low-end gaps read less fair (dp 500 vs 1500: 0.74 → 0.44) — both directions match market intuition. Fairness golden pins did not change (they are Elo-fixture-driven). Star tax now steps over 8 rungs (penalties bite sooner); `_TIER_ELITE/_TIER_STARTER` value bins in `analyze_roster_strengths` and the `_tier_mult_v2` Elo bands now bind at market-sane depths (they were nearly-empty under the old ceiling). Runtime knobs (`min_side_surplus`, `waiver_slot_cost`, `mutual_gain_cap`) were left as-is — retune via `model_config` if deck quality shifts.
- Same deploy-ordering + no-tier-overrides-migration properties as the 2026-07-11 section above.

## ESPN league linking — API fragility monitoring (`espn.link`, 2026-07-12)

Phase 1 reads ESPN's **unsanctioned** v3 API (`lm-api-reads.fantasy.espn.com`). Expect ~one breaking change per season (host moved silently in the 2023→2024 window; non-browser User-Agents get intermittently 403'd — `backend/espn_service.py` sends browser-signature headers, same lesson as the Sleeper Cloudflare-1010 fix). Full risk table: [plan §1](plans/espn-league-linking-plan-2026-07-11.md).

- **Symptoms of endpoint churn:** spike of `espn_unavailable` (502) responses or `espn fetch failed [http]` log lines on `/api/espn/link` / `/api/espn/import`. A sudden shift of everything to 403 (`espn_auth_required`) on previously-public leagues can also mean ESPN started auth-gating or UA-blocking us — probe by hand before blaming user cookies.
- **Hand probe:** `python3 -m backend.espn_service <league_id> [season]` (env `ESPN_S2`/`SWID` for private). Run this against a real public league **before every flag flip to ON** — the test suite runs on recorded fixtures and cannot see live endpoint changes. Note: 404 can be correct (ESPN purges old leagues each season, verified 2026-07-11).
- **Kill switch:** flip `espn.link` to `false` in `config/features.json` (or `FTF_FLAGS`) → all `/api/espn/*` routes 404 and the mobile affordance disappears (flag-gated client-side). Imported leagues stay inert in the DB; no cleanup needed.
- **Crosswalk staleness:** the DP `db_playerids.csv` crosswalk is cached in-memory for 24h with a bundled-snapshot fallback (`⚠️ DP crosswalk fetch failed` log line). Symptom of a stale crosswalk: fresh rookies show up in link responses' `report.unmatched`. Self-heals on the next successful fetch (hourly retry while on the snapshot).
- **Cookie expiry:** `espn_s2` lifetime is undocumented (~1yr community consensus). 401/403 on a `cookie`-mode league → client prompts a fresh paste; nothing to do server-side.
- **Stale Flask on the harness port answers the handshake convincingly** — profile/test-mode look right because the old instance was seeded the same way. `/__test__/whoami` now returns `pid`; `sim-run.sh` asserts it matches the process it spawned. Ad-hoc runs: `lsof -ti :5001 | xargs kill` BEFORE starting Flask (pkill by name missed a detached instance once, 2026-07-12).

## MFL + Fleaflicker league linking — monitoring (`mfl.link` / `fleaflicker.link`, 2026-07-18)

Both read **official/sanctioned** APIs (far lower churn risk than ESPN), zero-auth for public reads. Plan: [multi-platform-linking-plan-2026-07-17.md](plans/multi-platform-linking-plan-2026-07-17.md). Shared crosswalk staleness behaves exactly as ESPN's (same 24h cache + snapshot fallback; fresh rookies in `report.unmatched` = stale, self-heals).

- **MFL — the `wwwNN` host gotcha:** league-scoped calls must hit the league's assigned `wwwNN.myfantasyleague.com` host, **not** `api.` (which returns empty for `TYPE=league`). Resolution: parse the host from a pasted URL, else `api.myfantasyleague.com/{year}/home/{id}` 302-redirects to it (`Location` header). Symptom of a host regression: `mfl_league_not_found` (404) on a league you know is public → hand-probe `python3 -m backend.mfl_service <id> [year]` and check the "resolved host" line. **Rate limits:** MFL asks for ≥1s between requests (the service spaces its 4 live calls); registered clients get higher limits — set the registered UA in `MFL_USER_AGENT` after MFL client registration (plan §9 Q1).
- **Fleaflicker — sportradar dependency:** the crosswalk joins on `sportradar_id` (DP's `fleaflicker_id` column is a decoy). If match rate collapses, confirm the roster fetch still sends `external_id_type=SPORTRADAR` and that `externalIds` is populated. No published rate limits (poll politely). Hand-probe: `python3 -m backend.fleaflicker_service <id>` (or an email to list leagues).
- **Kill switch (either):** flip the flag to `false` → all `/api/{platform}/*` routes 404 and the mobile link option disappears. Imported leagues stay inert; no cleanup.
- **Future picks (MFL):** `futureDraftPicks` are stored raw in `leagues.platform_future_picks` (JSON), normalized into `draft_picks` by `_sync_mfl_owned_picks` (#158) and, since the #207/#228 parity fix, **re-fetched on the draft-status refresh cadence** (`_refresh_mfl_future_picks`) — one extra zero-auth export per refreshed MFL league, bounded by the same `_DRAFT_STATUS_SWEEP_BUDGET`. Symptom of an export regression: the log line `MFL futureDraftPicks unavailable for <id> — keeping the stored snapshot`. That is a *degradation*, not a fault: the stored snapshot is kept (never wiped — #220's lesson) and the verdict-gated current-season exclusion still hides a drafted season's picks on its own.
- **Franchise name color/formatting markup (#282, reopens #258):** MFL lets owners style their franchise name; the raw name string can carry inline markup like `<font color = Green>...</font color>` (sometimes malformed — a closing tag with no matching open, or `</font color>` carrying the attribute). This is entity-encoded on the wire (`&lt;font...`), which is why it only becomes literal `<font...>` after entity-decoding. `mfl_service._clean_text` strips a fixed tag allowlist (`b`, `i`, `u`, `strong`, `em`, `font`) after unescaping — if a future report shows leftover markup, it's most likely a tag outside that allowlist; extend `_MARKUP_TAG` rather than switching to a blanket `<[^>]*>` strip (that would mangle a team name with a literal `<`/`>`). `database._backfill_mfl_name_entities()` re-cleans stored rows on every boot using the same function, so a cleaner improvement alone (no separate migration) fixes both new imports and previously-stored names.

## Bare workflow: `app.json` iOS config is silently ignored (feedback #131, 2026-07-12)

This repo uses the Expo **bare workflow** — `mobile/ios/` is tracked in git and `expo prebuild` is never run — so `app.json` iOS config plugins and `ios.usesAppleSignIn` are silently ignored at build time. The native files under `mobile/ios/` (entitlements, Info.plist, project.pbxproj) are the source of truth. Incident: #131 — `app.json` declared `"usesAppleSignIn": true` + the `expo-apple-authentication` plugin, but `mobile/ios/DTFDynastyTradeFinder/DTFDynastyTradeFinder.entitlements` never got the `com.apple.developer.applesignin` key, so builds 40/41 were signed without the capability and `signInAsync()` rejected (code 1000) on device. Fix: add the key to the entitlements file directly. A config-drift sweep found the Apple entitlement to be the only such drift. When changing iOS-native config, edit `mobile/ios/` — treat `app.json` entries as declared intent for a hypothetical future prebuild only.

- **Pinned failure copy:** the Maestro regression guard (`mobile/.maestro/flows/smoke/11-apple-entitlement.yaml`) asserts on error strings pinned from `expo-apple-authentication@8.0.8` (`ios/AppleAuthenticationExceptions.swift`); `package.json` floats `~8.0.8`, so re-verify those strings whenever that package is upgraded.

## Universal Links AASA is CDN-cached by Apple (feedback #239, 2026-08-02)

Apple fetches `/.well-known/apple-app-site-association` through its own CDN, not from the device, so AASA changes take up to ~24h to reach installed apps and MUST be deployed on Render **before** the next iOS build is installed (install-time is when iOS validates the entitlement against the live file); for immediate on-device testing, set Developer mode's "Associated Domains Development" toggle or use the `?mode=developer` entitlement suffix, and sanity-check the served file with an AASA validator (e.g. Branch's) after deploy.

**Ordering for the P0-3 invite join claim (`/app/league/join/*`, 2026-08-11).** The claim, the server 302 and both clients' parsers are **unflagged and already deployed**; only mobile's emitter is behind `growth.invite_join_link` (default OFF). Flip the flag in a **separate session, after on-device verification** — never as part of the build. The sequence, each step a gate on the next:

1. **Deploy** the backend carrying the AASA claim (already in `main`). Confirm `GET /.well-known/apple-app-site-association` returns 200 `application/json`, no redirect, and lists `/app/league/join/*` in both `components` and `paths`.
2. **Wait ≥24 h** for Apple's CDN. There is no way to shorten this for installed apps.
3. **Validate externally** — run the live URL through an AASA validator (Branch's). A validator failure here means stop; do not proceed.
4. **Ship an iOS build installed AFTER step 1's deploy.** iOS validates the entitlement against the live file at install time, so a build installed before the deploy will not have the claim regardless of what the file says now.
5. **Prove it on device:** tap a `https://<host>/app/league/join/<a real league id>?ref=<username>` link from Messages. It must open the app on the join screen, not Safari.
6. **Only then** flip `growth.invite_join_link` to `true`.
7. **If steps 2–5 fail, leave the flag OFF indefinitely.** That costs nothing: the legacy `/?league=<id>&ref=<u>` URL is still emitted, is parsed forever by both clients, and the whole invite loop already works through it. Flipping early is the only way to make things worse — every invite would open Safari for up to ~24 h.

**Rollback** is flipping the flag back to `false`. Links already shared in the new format keep working, because the 302 and the parsers are unflagged.

## Quick Set unlock backfill (P0-1, 2026-08-11)

**What runs.** `database.backfill_ranking_method_from_tiers()`, called from `_migrate_db()` — so it runs **at every Flask boot**, including the seeded UI-test backend.

**What it touches.** Two columns on `users`, in one `UPDATE` per row: `ranking_method` → `'quickset'`, and `unlocked_formats` merged with every qualifying format.

**Cohort.** `ranking_method IS NULL` (or `''`) **AND** all four of QB/RB/WR/TE present in `tiers_saved` for at least one scoring format. Users with a *partial* tier board are deliberately excluded: tagging them would move them from the trio unlock rule to the tiers rule and could **re-lock** them. Strictly improving for every row it does touch. **Idempotent by predicate** — after the first successful run the cohort is empty. Chunked at 500. Never raises; a failure prints and returns what it wrote, so it can never break boot.

**Expected one-time row count.** Small — the whole cohort is pre-fix TestFlight users who finished a Quick Set board. **Dry-run the count against a prod replica before merge** (pre-merge checklist item).

**Confirming query** (should return 0 after a successful run):

```sql
SELECT count(*) FROM users
WHERE (ranking_method IS NULL OR ranking_method = '')
  AND tiers_saved IS NOT NULL;
```

**The affected ids are printed to the boot log** — `[backfill] ranking_method: tagged N/M user(s) 'quickset' — cohort: [...]`. **That log line is what makes the undo expressible**; without it there is no way to scope a reversal. Capture it from the Render log on the first boot after deploy.

**Reversal** (scoped to the logged cohort, never blanket):

```sql
UPDATE users SET ranking_method = NULL WHERE sleeper_user_id IN (<ids from the boot log>);
```

Note this does **not** un-write `unlocked_formats` — that column is a monotonic floor by design and reversing it would take an unlock away from a user who can see it.

**The `unlocked_formats` pre-seed is fan-out suppression, not cosmetics.** The unlock ladder pushes a notification when a format transitions locked → unlocked. Without the pre-seed, a whole cohort transitions at once on the first boot after deploy and every one of them gets a retroactive push. Permanent consequence, accepted: those users never receive the "Trade Finder unlocked" push for the backfilled format.

**Seed-fixture interaction — the non-obvious one.** The backfill **rewrites the seeded `quickset-done` user on every UI-test boot**. That is why `backend/tests/fixtures/profiles/quickset-done.json` ships already in the *post*-backfill shape and `seed_ui_test_db.py`'s `_validate_quickset` guard asserts the unlocked state. A fixture written in the pre-fix shape will be silently mutated at boot and the flow asserting the old behaviour will fail with no obvious cause.

## Mobile UI-test identity seam — `FTFTestAppleSub` (P0-5, 2026-08-11)

Account-only sign-in cannot be driven by a UI test through real Sign in with Apple, so the harness substitutes an identity: `mobile/src/screens/SignInScreen.tsx` reads the launch argument `FTFTestAppleSub` (`testLaunchArg`) and, when present, posts `identityToken: "ftf-test-apple:<sub>"` instead of a real Apple token; `backend/server.py`'s `_test_mode_identity` accepts that prefix.

**Two production gates, both required — neither alone is sufficient:**

1. **Client:** `testLaunchArg` reads process launch arguments, which are only reachable from a simulator/`xcrun simctl` launch. A shipped build has no way to set one.
2. **Server:** `_test_mode_identity` is gated on `FTF_TEST_MODE=1`, which is never set in normal operation and never on Render.

A `ftf-test-apple:` token hitting a production server is rejected as a malformed Apple token. Empty/whitespace subs return `None` (covered by `backend/tests/test_account_only_harness.py`). The seam substitutes for `verify_apple_token` and **nothing else** — session creation, account linking and routing all run the real code paths.

**Why this is a runbook entry and not an api-reference row:** it adds no route and is unreachable in any deployed build.

## Operator-only onboarding test — `trades_first_operator_test` (P0-9, 2026-08-11)

**The full seven-step recipe — collision check, experiment body, the eight-key overlay, the pre-flight verification call and the one-call rollback — is in [`plans/audit-p0-remediation/prd-p0-8-9.md` §5](plans/audit-p0-remediation/prd-p0-8-9.md), with per-claim code citations in `lld-p0-8-9.md` §6.** It is reproduced there rather than here because it is a one-off operator procedure with a defined end state. The load-bearing points, so they are not lost if the plan folder is archived:

- **`CRON_SECRET` lives in `secrets.local.env`.** Read it from there; never paste it into chat.
- **Step 0 is a collision check, not a formality.** `validate_spec(for_launch=True)` rejects a launch whose buckets overlap any **running *or paused*** experiment in the same layer, and `onboarding_v2_rollout` occupies the whole `onboarding` range. If it is already running with a matching overlay, **create nothing** — skip to the device-id step.
- **`stopped` is a one-way door.** There is no `stopped → running` transition. Before stopping an incumbent, `GET /api/admin/experiments/<key>` and **save the full row** — that response is the only restore spec, and restarting means a `revise` to a new version plus a `transition`, with metrics reset.
- **Two non-obvious overlay values.** `onboarding.league_autoskip` must be **false** (with it on, a single-league user skips the picker and the `s1.1` beat is unreachable), and `landing.try_before_sync` must be **true** even though it is not an `onboarding.*` key — without it `/api/session/demo` 404s and the landing's demo link is a dead end.
- **Verify before touching the phone.** `GET /api/feature-flags` with `X-Device-Id: <id, no `device:` prefix>` must show `experiments.trades_first_operator_test == "treatment"` and the eight-key `configs` overlay. This one unauthenticated call proves allowlist match, layer salt, bucket resolution, targeting and variant config — **all of which otherwise fail silently.**
- **Device ids rotate.** `config/tester_allowlist.json` carries them (entries use the `device:` prefix; the header does not). The device pseudo-id is minted client-side into SecureStore, so a reinstall that clears the keychain rotates it. The file exists because Render does not apply `render.yaml` `envVars` to a dashboard-created service (observed 2026-07-19).
- **`reseed-layers` refuses once any experiment has assigned a unit** — run it *before* launching, never after.
- **Rollback is one call:** transition the experiment to `stopped`. No flag default changes, no deploy.

## Retiring the onboarding experiment overlay — open-access Phase A (2026-08-15)

**Context.** [`business/product/2026-08-14-open-access-onboarding.md`](business/product/2026-08-14-open-access-onboarding.md) §5 Phase A (operator-ratified, O-1): the built v2 onboarding flow ships as the **default**, so `onboarding.landing`, `onboarding.trades_first`, `onboarding.league_autoskip`, `onboarding.quickset_prompt`, `onboarding.apple_save_moment` and `landing.try_before_sync` are now **true in `config/features.json`**. Item 2 of that phase: *"the flow stops being an experiment overlay and becomes the product. The flags stay as revert levers."*

**Nothing in this section is a code change.** Experiments live in the DB (`experiments` table, created via the CRON-gated admin routes), so retirement is a **runtime operator action** performed against prod *after* the Phase A deploy.

### First, the correctness question: what does a stale running experiment do once the flags are globally true?

Short answer: **for `onboarding_v2_rollout` v1 as specified it is a value-level no-op, but it is NOT inert** — it keeps polluting analytics, and the overlay mechanism is fully capable of overriding a `true` flag back to `false`. Retire it rather than leave it running. Mechanics, cited:

1. **The server never mixes experiments into the flag map.** `GET /api/feature-flags` returns `{"flags": flags_dict(), "experiments": …, "configs": …}` (`backend/server.py:18510-18514`). `flags_dict()` is the global map; the per-unit variant data rides alongside it, untouched.
2. **The client merge is an unconditional overwrite, not an OR.** `mobile/src/api/flags.ts:56-60`:
   ```ts
   let merged = base;
   for (const key of Object.keys(configs)) {
     const overlay = configs[key]?.flags;
     if (overlay && typeof overlay === 'object' && !Array.isArray(overlay)) {
       merged = { ...merged, ...overlay };
   ```
   There is no "overlay may only turn flags **on**" semantic — `{...merged, ...overlay}` lets an overlay value of `false` win over a global `true`. **A running onboarding-layer experiment can therefore un-ship Phase A for the units it captures.**
3. **…but `onboarding_v2_rollout` v1 cannot, as currently specified.** Its treatment `client_config.flags` sets the ten `onboarding.*` keys **true** and its weights are `control 0bp / treatment 10000bp`, so a captured unit is *always* treatment ([`business/analytics/2026-07-18-onboarding-v2-rollout-experiment.md`](business/analytics/2026-07-18-onboarding-v2-rollout-experiment.md) Spec table). True-over-true is a no-op. Non-allowlisted units are excluded before any overlay exists: targeting is `{"is_tester_allowlist": true}`, and `_targeting_match` treats a missing/false attribute as **exclusion, never default-into-control** (`backend/experiments.py:219-238`, resolution at `:248`). So no unit's flag values change either way.
4. **The danger is a `revise`, not the current row.** `POST /api/admin/experiments/<key>/revise` mints a new version (`backend/experiments.py:585-589`) with arbitrary variants. Any future onboarding-layer experiment that gives **control** a `client_config.flags` block — the natural shape for a "hold back the new flow" arm — silently re-locks those users, and by (2) the client will obey it over the global `true`. Leaving a live overlay pointed at the flags Phase A just shipped is the hazard; the row itself is not.
5. **It is not analytics-inert.** Even as a value no-op, while `status='running'`: `_persist_assignment` keeps writing `experiment_assignments` rows (`backend/experiments.py:274-289`); `stamp_for_event` keeps stamping every funnel event with `{onboarding_v2_rollout: treatment}` (`:387-407`, funnel set at `:380-384`); and the client keeps emitting `experiment_exposed` for every overlaid flag key on first consumption (`mobile/src/state/useFeatureFlags.ts:132-149`, provenance built in `flags.ts:65-67`). That attributes now-default product behavior to an experiment and corrupts the plan's §8 pre/post activation seam — which is the whole measurement basis for the flip.

**Conclusion:** retire the experiment. `experiments.engine` itself stays **true** (`aggregate_tier_labels` / `trades_home_inline` depend on it — see `config-reference.md`).

### Deploy-day procedure (run AFTER the Phase A deploy is live; prod, operator-only)

`CRON_SECRET` lives in `secrets.local.env` — read it from there, never paste it into chat.

```bash
export CRON_SECRET="$(grep -E '^CRON_SECRET=' secrets.local.env | cut -d= -f2-)"
export FTF_PROD=https://fantasy-trade-finder.onrender.com
```

**Step 1 — discover what is actually running.** Do not assume `onboarding_v2_rollout` is the live row: `trades_first_operator_test` (P0-9, section above) occupies the same layer, and `validate_spec(for_launch=True)` forbids overlapping buckets in one layer (`backend/experiments.py:474-484`) — so launching that one required stopping this one.

```bash
curl -s "$FTF_PROD/api/admin/experiments" -H "X-Cron-Secret: $CRON_SECRET" | python3 -m json.tool
```
Expected: a JSON array of `{key, version, layer, status, primary_metric, created_at, started_at, decision}`. **Act only on rows whose `layer` is `onboarding` and whose `status` is `running` or `paused`.** Rows already `stopped` or `decided` need nothing.

**Step 2 — snapshot the full row before touching it.** `stopped` is a one-way door (no `stopped → running` edge, `backend/experiments.py:76-81`); this response is the only restore spec.

```bash
curl -s "$FTF_PROD/api/admin/experiments/onboarding_v2_rollout" -H "X-Cron-Secret: $CRON_SECRET" \
  | tee docs/business/analytics/2026-08-15-onboarding_v2_rollout-final-row.json | python3 -m json.tool
```
(Commit that snapshot — it sits next to the experiment's own doc and is the only restore spec. `docs/recovery/` is **not** the right home: that folder is for branch/worktree tip shas.)
Expected: the full row including `variants_json`, `targeting_json`, `bucket_start`/`bucket_end`, `status`, `version`. **Note the `version`** — the transition call needs it and defaults to `1`.

**Step 3 — stop it.** (`running|paused → stopped` are the legal edges, `backend/experiments.py:76-81`.)

```bash
curl -s -X POST "$FTF_PROD/api/admin/experiments/onboarding_v2_rollout/transition" \
  -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
  -d '{"version": 1, "to": "stopped", "actor": "operator",
       "reason": "open-access Phase A: v2 onboarding shipped as the default in config/features.json; the overlay is retired, the flags are the revert lever"}'
```
Expected: `{"key":"onboarding_v2_rollout","version":1,"status":"stopped"}`. A `409` with `illegal_transition: <from> -> stopped` means it was already stopped — nothing to do.

**Step 4 — record the decision** (`stopped → decided`; `decide` refuses from any other status, `backend/experiments.py:568-571`). This is the audit trail for "we shipped it," not a no-op.

```bash
curl -s -X POST "$FTF_PROD/api/admin/experiments/onboarding_v2_rollout/decide" \
  -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
  -d '{"version": 1, "decision": "ship",
       "rationale": "Shipped as product default (open-access plan §5 Phase A / O-1). v1 was an allowlist rollout, never a powered test — no readout drawn, per its own experiment doc."}'
```
Expected: `{"key":…,"version":1,"status":"decided","decision":"ship"}`.

**Step 5 — verify the overlay is gone.** Use the operator device id from `config/tester_allowlist.json`, **without** the `device:` prefix (the file stores the prefix; the header does not).

```bash
curl -s "$FTF_PROD/api/feature-flags" -H "X-Device-Id: dev_loc-mrpy6qog-2t72t6" | python3 -m json.tool
```
Expected: `"experiments": {}` and `"configs": {}` (or entries for *other* layers only — `aggregate_tier_labels` / `trades_home_inline` are account-unit and unaffected), while `flags` shows the six Phase A keys **true**. Allow up to **60 s** for the running-experiment cache to refresh (`_CACHE_TTL_S = 60.0`, `backend/experiments.py:82`); the `transition`/`decide` calls also invalidate it in-process (`:556`, `:581`), but only on the worker that served the request.

### What deliberately does NOT change

- **`config/tester_allowlist.json` is left intact.** It is not `onboarding_v2_rollout`'s private list: `load_tester_allowlist()` is the shared source for the `is_tester_allowlist` attribute used by `aggregate_tier_labels` and `trades_home_inline`, **and** for the `POST /api/test-users` stage-user spawner gate (`backend/server.py:19006,19018`; `backend/test_users.py`). Emptying it would silently break all three.
- **`experiments.engine` stays true** — other layers are live.
- **`onboarding.share_sheet`, `rank_routing`, `demo_bridge`, `guided_layer`, `keep_warm` stay false.** Not named in the plan's §5 flip list; not Phase A.

### Rollback

Config-only, no deploy: set any of the six keys back to `false` in `config/features.json`, then `POST /api/feature-flags/reload` with `X-Cron-Secret` (`backend/server.py:18517-18527`). Revert `onboarding.landing` and `landing.try_before_sync` **together** — `/api/session/demo` 404s without the latter (`backend/server.py:18929`). Restarting the retired experiment is *not* the rollback path: it needs a `revise` to a new version with metrics reset (Step 2's snapshot is the spec).

## Render cold starts — keep-warm cron (onboarding item 3, 2026-07-17)

Prod runs on Render's **free tier**, which spins the web service down after ~15 min idle; the next request pays a **30–60s cold start**. The onboarding redesign's <60s time-to-first-trade-card budget assumes a warm server, so a scheduled GitHub Actions workflow keeps it warm.

- **Where:** `.github/workflows/keep-warm.yml` — every 10 min, GETs `https://fantasy-trade-finder.onrender.com/api/feature-flags` (in-memory flag map, no DB or external calls) with User-Agent `ftf-keepwarm`. URL is overridable via the GitHub repo variable `FTF_PROD_URL`.
- **On/off switch:** the workflow itself — GitHub → Actions → "keep-warm" → "…" → Disable workflow. The `onboarding.keep_warm` feature flag does **not** gate this ping; it's reserved for future server-side warm affordances.
- **Expected effect:** the service should ~never idle out, so first onboarding requests land warm. Pings show in Render logs as `ftf-keepwarm` GETs on `/api/feature-flags`.
- **Caveat — best-effort, not a guarantee:** GitHub cron can drift by minutes or skip runs entirely under Actions load, and scheduled workflows are auto-disabled after 60 days of repo inactivity (re-enable in the Actions UI after quiet stretches). Onboarding UX must still mask a cold start; the always-on alternative (Render paid tier) is weighed in `docs/business/finance/2026-07-17-render-paid-tier-memo.md`.
- **Manual test:** Actions → keep-warm → "Run workflow" (workflow_dispatch), then check the job log for `HTTP 200`.

---

## KTC consensus blend — source fragility + kill switch (#145/#148, 2026-07-17)

The baseline consensus seeds are a **blend of DynastyProcess and KeepTradeCut** (`backend/data_loader._apply_consensus_blend`, applied at pool build inside `_fetch_dynasty_process`). DP remains the pool's spine — universe, crosswalk, and value scale are DP's; KTC contributes an ordering opinion (weighted `ktc_blend_weight`) and, for `sf_tep` TEs, a premium (`tep_te_uplift`). See [config-reference → Consensus seed blend](config-reference.md).

- **Sourcing mechanism (fragile — unsanctioned):** KTC has no official API. The fetcher GETs `https://keeptradecut.com/dynasty-rankings` once per boot (24h in-memory TTL, browser headers to clear Cloudflare — same lesson as the Sleeper 1010 / ESPN UA fixes) and extracts the embedded `var playersArray = [...]` literal from the page HTML (`parse_ktc_players`). Each entry carries both formats plus TE-premium variants (`tep`/`tepp`/`teppp`); we read `oneQBValues.value` for `1qb_ppr` and `superflexValues.tep.value` for `sf_tep`. **Expect this to break without notice** — a page-markup change (variable renamed, array inlined differently, values moved behind XHR) or a Cloudflare block. It is a *scrape*, not a contract.
- **Fail-soft (never blocks boot):** any KTC problem (fetch error, 403, `playersArray` not found, JSON change) is caught — `_ktc_consensus` logs `⚠️ KTC fetch failed …` and returns `{}`, and the blend then leaves the maps **DP-only**, exactly mirroring the DP CSV's own last-good/flat-Elo fallback. A failure is cached for the TTL so a broken endpoint isn't re-hammered by every pool rebuild in one process. Boot always succeeds.
- **Kill switch (no code change, no redeploy needed for the value knob):** set `ktc_blend_weight = 0` via `PUT /api/admin/config/ktc_blend_weight` (with `tep_te_uplift = 1` for a full revert). Weight 0 makes the seed pipeline **byte-identical to the pre-#145 DP-only baseline** and short-circuits before KTC is ever fetched. **Takes effect on the next boot / pool rebuild** — the universal pool is built once per boot, so bounce the service (or wait for the next daily rebuild) after flipping it. This is the lever to pull if KTC starts serving bad/garbage values (as opposed to being merely down, which already fails soft).
- **Symptoms of a silent KTC break:** the boot log shows `⚠️ KTC fetch failed` (down → DP-only, benign) OR — worse, if the markup changed but still parses — occupancy drift / weird top-of-board ordering with **no** warning. Guard: `backend/tests/test_ktc_blend.py` pins parse, blend-off byte identity, occupancy sanity, and the sf_tep TE≥1qb invariant against checked-in fixtures (network-free). To refresh after an intentional KTC data shift, re-dump `backend/tests/fixtures/ktc_rankings_snapshot_*.html` (trimmed page) and `ktc_blend_pipeline_*.json` (matched DP+KTC pool) and re-run the suite.
- **Value-history versioning — NO marker/rescale needed (unlike #117):** the daily `value-snapshot` cron writes whatever the current seed map holds, so post-#145 snapshots carry blended values while pre-#145 rows carry DP-only values. This is safe *without* a `value_history_seed_scale`-style migration because (a) both are on the **same 0–10k value scale and the same affine Elo map** — only the ordering/magnitude of individual players shifts slightly, not the scale — so the FB-61 30d-trend deltas stay meaningful (a player whose blended value rose reads as a riser, which is correct); and (b) the #117 rescale existed only because that change moved the *scale itself* (linear→affine), which is invertible; a blend is not a scale change and has no closed-form inverse. The 30d window self-heals as pre-blend rows age out. Accepted; revisit only if trend glyphs look wrong through mid-August 2026.
- **Hand probe:** `python3 -c "import backend.data_loader as d; print(len(d._ktc_consensus()))"` (prints the matched-row count, or 0 if KTC is down). Matching uses the DP `db_playerids.csv` crosswalk (`ktc_id`/`mfl_id` → DP name, position-strict per #127) with a name fallback; on the 2026-07-17 data 441/464 KTC players matched the DP pool (unmatched KTC players are ignored — universe unchanged).

---

## Analytics platform P0 — WAL, wrapped cutover, kill switches (2026-07-17)

ADR-007 / docs/plans/analytics-platform/lld.md. Operational facts:

- **SQLite WAL is now ON.** The product engine's on-connect listener sets `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, `wal_autocheckpoint=1000` (~4 MB). Expect `trade_finder.db-wal` / `-shm` sidecar files next to the DB — back up all three together (or use `sqlite3 .backup`). `GET /api/admin/analytics/health` (X-Cron-Secret) surfaces `wal` (must be `true` on SQLite; `null` = Postgres, fine), `event_id_index_present`, `wal_file_bytes` (should stay ≲ a few MB — a runaway means a stuck reader pinning the WAL), and the since-deploy ingest counters (`txn_failed` growing = look at DB lock contention).
- **wrapped_events cutover rollback = revert the deploy.** The cutover is the one non-flag-gated P0 change: the five wrapped writers now write `user_events`, and the boundary instant is `model_config` key `analytics.wrapped_cutover_at` (epoch seconds, seeded once at first boot). Rolling back the deploy restores the old writers and the old narrative reader; the key is INSERT-or-ignore so it survives the rollback and stays correct on roll-forward (events written to `user_events` during the rollback window are invisible to the legacy reader — an accepted, bounded gap). **Never edit the key by hand** — moving it double-counts or hides league-activity rows.
- **Pause vs engine-flag kill:** to stop client event ingestion, flip the `analytics.client_events` feature flag off (route 404s under the v0 contract; from P1 it answers `disposition:"disabled"` and clients stop flushing). That is the pause lever. Do NOT "kill" analytics by touching the engine wiring or dropping indexes — the ingest/ro engines are import-time constructs shared with boot checks, and the unique `event_id` index is the retry-idempotency keystone (dropping it turns every client retry into duplicate rows).

## Reading REAL analytics (prod, not dev) — 2026-08-05

`data/trade_finder.db` is the **local dev** DB and contains almost nothing but
test-suite artifacts (`caller_uid`, `user_anchor_test`, `stm_user` are pytest
fixtures). Any analytics run against it is measuring the test suite. Real usage
lives in Render Postgres.

```bash
python3 -m backend.tools.prod_analytics --diagnose          # eventing health
python3 -m backend.tools.prod_analytics --report overview --days 28
python3 -m backend.tools.prod_analytics --list
```

Read-only is enforced **server-side** (`default_transaction_read_only=on` +
`statement_timeout`), so the connection cannot write even if the code tries.
Credentials come from `DATABASE_URL_PROD` in `secrets.local.env` — never pass
them on the command line (shell history). Or just open
`https://fantasy-trade-finder.onrender.com/admin/analytics.html`.

**Latency caveat (2026-08-05):** `api_request_failed.ms` is **omitted** when a
request spanned a foreground exit (`bg: true`). Filter on "`ms` present";
averaging raw `ms` includes device-sleep time and is wrong.

## Analytics platform P1 — ingestion pipeline + kill-switch latency (2026-07-18)

The `/api/events` rewrite (`backend/analytics_ingest.py`) + mobile SDK rewrite. Operational facts:

- **Two flags, two jobs.** `analytics.ingest` = **server acceptance** (off → the endpoint answers `disposition:"disabled"`; P1+ clients retain their queue and back off, so no data is lost, it just doesn't land). `analytics.client_events` = **client emission** (off → SDKs stop `track()`-ing and stop flushing). To fully stop the flow fast, flip `analytics.ingest` off — one server reload, no client dependency. `analytics.client_events` off only stops *new* emission on clients that have fetched the flag.
- **Kill-switch latency, stated honestly.** Server flags take effect at the next `POST /api/feature-flags/reload` (operator-driven, ≤ minutes — there is no TTL). Clients pick up a flag flip at cold start OR the ≥30-min foreground config refetch that ships in the P1 binary (App.tsx `maybeRevalidateFlags`). **Binaries predating P1 only refetch flags at cold start** — their bound is next cold start, which for a backgrounded app can be long. This is why `analytics.ingest` (server-side) is the real kill lever.
- **Ingest never 4xx/429s.** Rate-limit / unknown-type / oversize are "accepted-and-dropped" (200). The dedicated `ingest_engine` runs each batch in one `BEGIN IMMEDIATE` transaction with a 150 ms lock budget; under DB contention (an NFL-Sunday burst) ingest sheds the batch (`disposition:"ok"`, `accepted:0`) and clients requeue — product-route latency is protected by design. A rising `txn_failed` counter on the health route = expected shedding under load, not a bug, unless product p95 also moves.
- **`quickrank_completed` is dark until a client ships** the `via:'quickrank'` reorder flag (in the P1 mobile build); the route wiring (`server.py`) is live and waiting.

## Render ignores render.yaml envVars on the dashboard-created web service (2026-07-19)

Adding `FTF_TESTER_ALLOWLIST` to `render.yaml` envVars and deploying did NOT set the variable — the web service was created via the dashboard, not the blueprint, so blueprint envVars never apply to it. Symptom: experiment targeting on `is_tester_allowlist` matched nobody after an apparently-successful deploy. Fix shipped: `backend/experiments.py` unions the env var with git-deployable `config/tester_allowlist.json` (commit b689f28). Rule of thumb: anything that must reach this service's environment goes in the dashboard by hand; anything that must be automatable goes in a config file.

## Offline eval harness — replay/IPS on the F1 impression spine (F8, 2026-07-26)

`backend/eval/` grades candidate deck rankers on logged data before any user sees them (docs/plans/tiktok-discovery/prds/F8-offline-eval.md). Read-only against product tables; only writes are JSON-lines run records under `data/eval_runs/` (gitignored).

- **Grade candidates:** `python3 -m backend.eval.replay --scorer base_score --scorer random` (default DB; `--db path.db` for a copy/snapshot — prefer grading a `sqlite3 .backup` copy on prod). Prints a markdown table (IPS/SNIPS, 95% cluster-bootstrap CI, ESS, verdict vs the `production` baseline) plus exclusion accounting: `null_propensity` / `never_viewed` / `undo_reversed` / `bad_features` / `scorer_error` — the counts must sum to the loaded total; a printed WARNING means a harness bug, file it.
- **Sanity first, always:** `python3 -m backend.eval.replay --self-check` replays the logged policy against its own logs; the observed like/propose rate must fall inside the replayed CI (exit 1 otherwise). Run it before trusting any candidate readout — a self-check failure means the log or the estimator is broken, not the candidate.
- **`UNRELIABLE` verdict** = ESS below the gate (`EVAL_ESS_MIN`, default 100). That is the harness refusing to bless the number, not a failure — collect more log or narrow the question. The `random` scorer is a permanent canary: it must grade worse than `production`; if it ever grades level on healthy volume, stop and debug the harness.
- **Trainable scorers (F6):** the harness enforces the time-ordered protocol — `--eval-start` is mandatory for any scorer with `fit()`; fitting sees only pre-split decks, scoring only post-split. There is deliberately no shuffled-CV mode.
- **Nightly re-runs:** `python3 -m backend.eval.nightly` (or `backend.eval.nightly.run_all()`) grades every registered scorer on the trailing 30d, idempotent per (UTC day, scorer, window) via `runs.jsonl` — safe to re-invoke. Per-scorer failures are recorded as `status:"error"` records and counted, never raised. **The `/api/cron/daily-tick` hook is NOT wired yet** (W4 handoff — F7 owned server.py that wave); until the lead pastes the snippet from `feedback-workspace/tiktok-discovery/build/W4-F8.md`, nightly runs are manual.
- **The gate (process):** no ranking-affecting change (F5 η's, F6, tweaks) graduates without (a) a replay win with adequate ESS, then (b) an interleaving/experiment win. Cite run records, not vibes.

## MFL numeric league ids wiped draft picks on session init (#200, 2026-07-27)

Operator report: "Draft picks are missing from league summary" (League Rankings, MFL league 62846 "The Dependables League"). Root cause: session-init's #158 owned-pick sync daemon gated the Sleeper grid rebuild on `str(league_id).isdigit()` alone — but MFL (and Fleaflicker) NATIVE ids are numeric too (the #149/#150 misroute class). For an MFL league the Sleeper traded-picks/rosters fetches came back empty, so `sync_draft_picks(roster_ids=[], …)` REPLACE-synced the league's `draft_picks` to an EMPTY grid — silently deleting the rows `_sync_mfl_owned_picks` normalized at link time. Every app open into the league re-wiped them, so `/api/league/power-rankings` served `picks: {count: 0}` and the client (correctly) hid the Picks pill/segment/drill-in.

- **Fix (2026-07-27):** the daemon now discriminates with `is_linked_platform_league(league_id)`: platform-linked numeric ids skip the Sleeper grid sync and re-run `_sync_mfl_owned_picks` instead (no network — reads `leagues.platform_future_picks`). This also **self-heals** previously clobbered leagues on their next session init; no manual data repair needed. Tests: `backend/tests/test_owned_picks.py::test_numeric_mfl_id_detected_as_platform_league`, `::test_mfl_renormalization_restores_clobbered_picks`.
- **Diagnosis pattern for "X missing from league summary":** check `draft_picks` rows for the ACTIVE league id first (`SELECT league_id, COUNT(*) FROM draft_picks GROUP BY league_id`) — the League Summary client renders picks only when the payload carries non-zero `teams[].picks`, and it degrades silently (no pill, no bar segment, no Draft capital section) when the league has no pick rows. The client had no bug here.
- **Watch item:** other Sleeper-only session-init daemons still gate on `isdigit()` alone (scoring auto-detect meta fetch, trade capture, lineup-slot fetch). They fail soft for MFL ids (no writes to shared stores) but waste a Sleeper call; if one ever gains a replace-style write, it needs the same `is_linked_platform_league` guard.

## Sleeper-flake still wiped draft picks after the #200 fix (#220, 2026-08-01)

Operator re-report post-#200: "Picks still not present on the bar chart" (League Rankings, v1.11.0). Honest re-root-cause: the #200 guard, the MFL self-heal, the `/api/league/power-rankings` picks group and the client bar segment were all verified working (the chart/pill/legend/drill-in render paths are live in 1.11.0; the picks group reproduced correctly against the operator's real Lakeview data; prod's 08:22Z init synced 192 Lakeview picks). What remained was the #200 runbook watch item made real **on the genuine-Sleeper path**: the daemon fed `sync_draft_picks` whatever the Sleeper reads returned — a flaked rosters read (`_fetch_league_rosters` → `None or []`) produced an EMPTY grid that the REPLACE-sync wrote over the league's picks, and a flaked meta read silently shrank the grid to 3 rounds / default season. One bad read on app open ⇒ no draft capital anywhere (chart, suggestions, calculator) until the next successful init — an intermittent, self-re-arming wipe.

- **Fix (2026-08-01):** the daemon step is extracted to `server._sync_sleeper_owned_picks`, which **skips the sync (keeps the prior snapshot)** whenever the rosters or league-meta read is unavailable, and `database.sync_draft_picks` no-ops on empty `roster_ids` (defense in depth for every caller). A skip logs `owned-pick sync skipped … (keeping prior snapshot)` and the next init retries. Tests: `backend/tests/test_owned_picks.py::test_sync_empty_roster_ids_keeps_prior_snapshot`, `::test_daemon_step_skips_when_sleeper_rosters_unavailable`, `::test_daemon_step_skips_when_league_meta_unavailable`.
- **Operational rule:** any daemon whose write is replace-style must treat "fetch came back empty" as SKIP, never as "the league truly has nothing" — the #200/#220 clobber class is exactly that conflation.

## Player-cache refresh (rookie-draft M0, 2026-08-06)

Until M0 the player pipeline had **no refresh path at all**: the only bulk fetch from `/v1/players/nfl` happened on a disk-cache MISS, the "24 h sync gate" re-synced the `players` table from that same stale file, and `_ensure_universal_pools` froze the ranking pool per-process. A new rookie class could therefore only appear via a redeploy — prod was fresh only by accident, on Render cold boots, and the dev cache was five months stale (dated Apr 11, pre-NFL-draft: 157 teamless "rookies", 2 of them with a team).

- **Trigger:** `POST /api/cron/players-refresh` (X-Cron-Secret, once daily). Render "cron" is an HTTP POST into the single-worker web service, so the handler **must not** fetch inline — it starts a daemon thread and returns **202 immediately**, always, including when nothing started. `?force=1` ignores the 20 h TTL. `POST /api/cron/daily-tick` carries an idempotent fallback guard (deployed envs only) so a missed dedicated run self-heals; provision the dedicated cron **by hand in the Render dashboard**, never via `render.yaml` — a new blueprint cron breaks blueprint sync (see the `value-snapshot` note above).
- **What the daemon does, in this order** (the order is load-bearing): fetch → **atomic** cache write (temp file in the SAME directory + `os.replace`; a `/tmp` staging file would silently degrade to a copy) → `_sleeper_cache` global → `sync_players` **directly**, past the 24 h gate → clear the DP value maps → rebuild the universal pools **build-new-then-rebind, never clear-in-place** → bump the pool generation. A cleared pool would hand a concurrent `session_init` an empty board; `_player_sync_lock` serialises writers but does not guard pool readers.
- **The generation is membership-only.** A bump makes the NEXT `session_init` rebuild that user's ranking services once; every pid present both before and after **carries its prior seed Elo forward** (rule G-SEED), so re-seeding stays on the user-change cadence and nothing moves mid-session. Expect exactly one extra rebuild per active session per refresh.
- **Everything fails soft.** A dead upstream, a DynastyProcess outage, or a build that yields no players leaves the previous cache, `players` table, pools **and generation** completely intact — the next tick retries. Last-run state is in `server._last_refresh_status` (`{at, ok, error, players, generation}`).
- **Kill switch:** `FTF_PLAYERS_REFRESH=0` (env, no deploy). M0 is deliberately not flag-gated — it has no user-visible surface — so this is the only lever. Set it if a bad Sleeper payload ever reshapes the pool.
- **Verifying it fired:** the log carries `players-refresh: DONE <n> players, generation=<g>`, and `players cache: <path> is <d> days old` on the next boot read. A refresh that runs but rebuilds nothing logs `no pool rebuilt — keeping the previous pools and generation entirely`.
- **Watch the latency claim, not just the logs.** The refresh holds `_pool_build_lock` for the whole DP re-fetch. That is deliberate — it is the single-flight guard that stops the daemon and a request worker each fanning out their own DynastyProcess fetch — and request threads never touch that lock while a pool is already built. `backend/tests/test_players_refresh.py::test_request_path_is_not_blocked_while_a_refresh_runs` is the pin: if anyone puts a lock on `pool_generation()` or on the `_ensure_universal_pools` fast path, that test is what catches it.

**Rookie class-load monitor.** `daily-tick` runs one indexed `COUNT` for `rookie_year == <next season>` and logs `CLASS-LOAD <year> rookie class has appeared` once per process the first time it is non-empty. Sleeper's dump carries **no** rows for a class until ~late April, so Feb–Apr is a structurally empty window the Draft Room has to design around; this log line is the only signal that the window closed. It uses the EXACT `rookie_year` test on purpose — the `years_exp == 0 AND team` proxy in THE rookie predicate is season-independent and would fire on day one.

**Measuring the class.** `python3 -m backend.scripts.measure_rookie_pool --refresh` runs a synchronous refresh, then writes `docs/plans/rookie-draft/measurement.md` with valued-rookie counts per scoring format × position plus the plan's abort criterion (any format under 15 valued rookies ⇒ rookie scope ships for Pick Anchors + Tiers only). Re-run it before any rookie UI wave — the numbers move as DynastyProcess picks up more of the class.

## Rookie-scope board restore (rookie-draft M2, 2026-08-06)

`users.tier_overrides` is a wholesale-overwritten JSON blob with **no history** — a prior filtering bug permanently destroyed a user's board, and `server.py` still carries the comment saying so. Rookie scope (`ranks.rookie_subset`) is the first feature that writes a **partial** board, so a one-time snapshot plus this procedure is a **precondition for flipping that flag**.

- **What is stored:** a sibling key `__pre_rookie_scope__` inside the same `tier_overrides` column — `{v:1, taken_at, reason:"pre_scope_v1", formats:{"1qb_ppr":{pid:elo}, "sf_tep":{…}}}`. No new table, no migration. `database.take_tier_override_snapshot(user_id)` writes it from `POST /api/tiers/save` **before any mutation**, only when `scope == "rookie"`. It is idempotent on purpose: the FIRST scoped save captures the pre-scope state and later saves never overwrite it with an already-damaged board.
- **What keeps it alive:** `database._parse_extra_keys`. `_parse_per_format_json` narrows to `SCORING_FORMATS`, so every writer that round-trips this column must merge non-format keys back (`{**extras, **all_overrides}`) or the very next save of either format silently deletes the snapshot. That merge is pinned by `backend/tests/test_rookie_scope.py::test_m2_01_sibling_key_survives_alternating_format_saves` — **if it ever goes red the restore path is gone and the flag must go back off.**

**Procedure:**

1. Confirm the damage window from the user's `via:'rookie_*'` rows in `user_events` (`rookie_tiers` / `rookie_quickset` / `rookie_anchors` — the forensic tags scoped saves carry).
2. Verify the snapshot predates that window:
   `python3 -c "from backend.database import load_tier_override_snapshot as l; print(l('<user_id>'))"`
3. Restore (both formats; pass a format string to restore just one):
   `python3 -c "from backend.database import restore_tier_overrides_from_snapshot as r; print(r('<user_id>'))"` → per-format counts. **Repeatable** — the restore does not consume the snapshot.
4. Have the user re-init their session (`POST /api/session/init`). In-memory `_elo_overrides` are only re-read at session init, so until they do, their live session still shows the damaged board.

**Known void:** `reset_user_rankings` (the "reset my rankings" action) sets `tier_overrides = NULL`, dropping the snapshot along with the board. That is correct — the user asked for a clean slate — but the restore path does **not** survive a self-service reset. There is no recovery after that point.

**Known, accepted cosmetic effect (RB-7):** because a merged-band save positions incumbents without rewriting them, a partial save can read as slightly out of order against stale neighbours until the next full-band save of that position. That is inherent to any partial save, not a bug to chase.

## Draft Room polling budget (rookie-draft M4, 2026-08-06)

The Draft Room is the first surface in the app that fetches on a timer. `refetchInterval` had **zero** occurrences in `mobile/` before it, and the app-wide default is `refetchOnWindowFocus: false`, so there is no established pattern to lean on — the budget below is the whole contract.

**Client → our server.** `DraftRoomScreen`'s query polls `GET /api/draft/board` every **15 s**, and only when ALL of: flag `draft.live_poll` is on · the screen is focused (`useIsFocused`) · the app is foregrounded (`useAppActive`, AppState `'active'`) · the board's own `state == "live"`. Anything else evaluates `refetchInterval` to `false`, which stops the timer rather than slowing it. `refetchIntervalInBackground: false` is set explicitly even though it is already the default.

- **The pass threshold for blurred or backgrounded is literally ZERO requests** — not "fewer", not "one straggler". Verify by instrumentation (a request counter or a proxy log), never by reading the code: the failure mode here is a timer that keeps firing invisibly and bills every user's battery.
- The manual **Refresh** control is present with the flag on or off. The room is fully usable dark; polling is an upgrade, not a dependency.

**Our server → the platform.** Independent of the client. `draft_board_service` keeps one shared entry per `(platform, league, draft)` with TTLs 20 s live / 5 min upcoming / 24 h complete, per-key single-flight (N simultaneous viewers of one draft ⇒ **one** upstream read), a rolling-60 s cap of **3** upstream cycles per draft, and a 3-failure / 120 s circuit breaker. Within a cycle it reads the 1.2 KB draft-detail object and fetches the 20 KB pick list **only when `last_picked` moves** — a direct `/picks` poll reads a complete draft's ~24 h CDN cache while believing it is live.

**If the fan-in guarantee has to be restated:** the ≤3 req/min/draft ceiling is **per process**. The Render upgrade (plan O8) that makes live polling viable also allows multiple workers — at that point the real ceiling is `3 × worker_count` per draft, and the number in the plan needs restating rather than re-deriving.

**Kill order, cheapest first:** flip `draft.live_poll` off (polling stops, manual Refresh survives, the room stays up) → flip `draft.room` off (the route 404s, the League tile reverts to the rookie-board sheet, nothing else in the app changes).

## Pick-assignment recovery (draft-extensions W3 M-A, 2026-08-08)

**Flag:** `picks.assign` (ships OFF). **Store:** `draft_picks` rows with `source='user'`. **Audit trail:** the `pick_assignment_changed` rows in `user_events` — there is no separate audit table, deliberately.

**Bug fixed 2026-08-08: "draft picks can't be created" (caller's own team missing).** `PickAssignmentScreen`'s setup step has no slots to read team names from before a board is first seeded, so it fell back to `GET /api/league/members` — the "Leaguemates" roster endpoint — for its round-1 id→name mapping. That endpoint deliberately **excludes the caller** (`_league_members_cached(..., exclude_user_id=g_user_id)` in `backend/server.py`'s `league_members_route`), because it powers a list that's supposed to be about everyone else. Reused as-is for pick assignment, the drag-order list the setup screen built was always missing the requesting user's own team, so the `order` it posted to `POST /api/league/pick-assignments/order` could never match the server's full membership set (`_assignment_members`, which correctly includes every team) and the seeder's `sorted(order) != sorted(member_ids)` check 400'd `bad_order` on every attempt — no board could ever be created for the affected user. **Fix:** `/api/league/members` gained an opt-in `include_self=1` query param (default behavior unchanged for every other caller); `mobile/src/api/league.ts`'s `getLeagueMembers()` takes an `{ includeSelf }` option, and `PickAssignmentScreen`'s setup-step query now passes `includeSelf: true`. Regression tests: `backend/tests/test_pick_assignment.py::test_league_members_excludes_caller_by_default`, `::test_league_members_include_self_returns_full_roster`, `::test_order_built_from_caller_excluded_roster_is_rejected`, `::test_order_built_from_include_self_roster_succeeds`.

**Kill switch.** Flip `picks.assign` off. The three routes 404, the ESPN Draft Room reverts to the byte-identical `platform_unsupported` payload, and **no data is lost** — the rows stay, and every existing read site was already taking `load_draft_picks`' platform-only default. There is nothing to roll back in the schema: all four columns are additive and nullable and nothing was backfilled.

**A league's grid looks wrong / a slot was mis-assigned.** Every write emits `pick_assignment_changed` with `{pick_id, season, round, original_team, old_owner, new_owner, actor}`, so the full history of a slot is one query:

```sql
SELECT occurred_at, user_id, props
FROM user_events
WHERE event_type = 'pick_assignment_changed'
  AND league_id = :league_id
ORDER BY occurred_at;          -- covered by ix_user_events_type_occurred
```

To rebuild a league's grid from scratch, replay those rows in `occurred_at` order over a fresh pristine seed (`POST /api/league/pick-assignments/order` with `reseed: true`, then one `PUT` per slot). Nothing else is needed — the audit trail is complete by construction, which is why the event is server-fired and must never be added to `ALLOWED_CLIENT_EVENTS`.

**A slot shows `contested: true`.** Two different members assigned it to two different owners. It is excluded from every priced payload until someone corrects it; correcting it (one more `PUT` agreeing with one of the two) does **not** clear the flag on its own, because the derivation reads the whole history. If the disagreement was resolved and the flag should clear, delete the losing `pick_assignment_changed` rows for that `pick_id` and call `database.invalidate_pick_assignment_cache(league_id)` — the memo is per-league with a 60 s TTL backstop, invalidated on every write.

**A slot shows `orphaned: true`.** The owner id is no longer a `league_members` row — usually a SWID rotation on an ESPN re-import, occasionally a manager who left. The slot is excluded from pricing and surfaced as a re-assign row; fix it with a `PUT` naming a current member. **Never** delete the row: a dropped slot is value that vanishes with no explanation, and no platform will ever contradict the grid.

**`PUT` returns 409 `stale_assignment`.** Working as designed — somebody else edited that slot since the client read it. The 409 body carries the whole current row, so the client re-reads nothing; retry with the `assigned_at` from `current`.

**Monitoring triggers (not ship gates).** Per plan §6.8: <50% of started grids reaching 100% within 72 h ⇒ do not open M-C; >5% of slots contested within 7 days ⇒ stop widening. Both are measured off `pick_assignment_changed` and the `progress` block.

## Pick-recording queue integrity (draft-extensions W3 M-D, 2026-08-08)

**Flag:** `draft.manual_picks` (ships OFF). **Store:** the new `recorded_picks` table ([data-dictionary](data-dictionary.md#recorded_picks)) — never `draft_picks`, never `leagues.draft_status*`. **Idempotency key:** `(league_id, season, overall)`, not `event_id` — two devices recording the same physical pick will not share a uuid, so the server key has to be the slot, not the client's queue entry.

**Zero-tolerance bar (plan §6.8).** Any duplicate or lost pick after an offline session reconnects is an idempotency bug, not a UX metric, and it takes recording off the allowlist — this is the one release gate in the wave that is not a monitoring threshold. `backend/tests/test_recorded_picks.py`'s replay tests assert a full batch survives being replayed **twice** with zero duplicate rows and a byte-identical board.

**Kill switch.** Flip `draft.manual_picks` off. Both routes 404, and `GET /api/draft/board`'s ESPN branch stops reading `recorded_picks` entirely — the flag gates the read, not only the writes, so a row already recorded is never lost and never leaks into a flag-off board; it simply stops rendering until the flag flips back on. Nothing to roll back in the schema: `recorded_picks` is a brand-new additive table.

**A pick was recorded for the wrong player.** Re-record the same `overall` with the correct `player_id` — `record_draft_picks` UPDATEs the row in place (a correction), never a second row.

**A pick needs to be undone.** `POST /api/league/recorded-picks/void` sets `voided_at`; it is **never a DELETE**. Re-recording the same `(league_id, season, overall)` later reverses the undo (`voided_at` resets to `NULL`) — there is no separate "revive" endpoint.

**A recorder tapped the wrong slot (off-by-one).** Recovery is **manual-cursor-only, no auto-shift** (the plan's binding decision, not a placeholder): tap the correct slot directly and record there. There is no "insert a skipped pick and shift everything after" mode — `overall` is the offline queue's idempotency key, and a shift operation would rewrite many rows' `overall` values, which is exactly the kind of write the idempotency contract cannot tolerate mid-replay.

**The client queue dropped something (`MAX_QUEUE` overflow).** `mobile/src/api/recordedPicks.ts` mirrors `mobile/src/api/events.ts`'s `MAX_QUEUE = 500` FIFO-trim contract (extracted shared primitives live in `mobile/src/api/_queue.ts`). A 192-slot draft cannot legitimately overflow it — a trim event is a client bug, not normal operation, and blocks the release per the zero-tolerance bar above.

**A recorded pick's team looks wrong even though the grid is right.** `recorded_picks.picking_team_id` is a **snapshot** taken at recording time, not a live join against the assignment grid (RC-7, plan §5.1) — the grid is truth for *ownership*, the recording is truth for *what happened*, and the two are deliberately not reconciled. If the grid was corrected after the pick was recorded, re-record the same `overall` (any `picking_team_id`, same or different `player_id`) to refresh the snapshot.

## Guided tour v2 — kill switches and flag preconditions (2026-08-15)

- **Kill the v2 layer only:** `onboarding.guide_v2 → false` (hot-reload via `POST /api/feature-flags/reload`, cron-secret gated). Restores the v1 tour graph: v1 beats (incl. `s6.1` toast + `s2.3`), no eligibility layer, no new beats. Copy trims persist (they ship in the binary, unconditionally).
- **Kill the whole tour:** `onboarding.guided_avatar → false`. **Reality check (PRD FR-E11):** the documented "falls back to the passive layer" claim is FALSE while `onboarding.guided_layer` is `false` — turning the avatar off today falls back to NOTHING. If a passive fallback is wanted, flip `onboarding.guided_layer → true` in the same change.
- **Guide flag preconditions** (beats fail closed when their owning feature flag is off — pulling one of these mid-season silently suppresses the beat, by design): `trade.outlook_direction` + `trades.edit_full_sheet` + `trades.finder_hub` → N2 · `deck.replenishment` + `trade.finder_targeting` + `trades.finder_hub` → N4 · `ranks.import` → N8 · `league.pos_candidates` (+ `league.player_trade_handoff` for the pin clause) → N5 · `trade.send_in_sleeper` → the send-teaching beats (N6.2/N3, Phase 2).

## Organic trade backfill (2026-08-16)

Two operator-run scripts (flag-independent — `market.trade_capture` only gates the
background daemon) populate the organic executed-trade corpus and its suggestion links.
Both are idempotent by construction (insert-only through the existing
`record_sleeper_trades` / `save_suggestion_trade_links` helpers), so re-running is
always safe; both take `--dry-run` and `--league <id>`.

```bash
# against prod (reads DATABASE_URL_PROD from secrets.local.env; quotes stripped):
export DATABASE_URL="$(grep '^DATABASE_URL_PROD=' secrets.local.env | cut -d= -f2- | sed "s/^['\"]//; s/['\"]$//")"
python3 scripts/backfill_sleeper_trades.py --dry-run     # inspect counts first
python3 scripts/backfill_sleeper_trades.py               # sweep every synced league + 3 prior seasons
python3 scripts/backfill_suggestion_links.py --dry-run
python3 scripts/backfill_suggestion_links.py             # retro-link pre-telemetry trades (exact-hash only)
unset DATABASE_URL                                       # don't leave the shell pointed at prod
```

**When to re-run:** `backfill_sleeper_trades.py` after new leagues are synced, at season
rollover (new `previous_league_id` hops appear), or if the capture daemon was dark for a
while — deeper history needs `--max-prior-seasons N`. `backfill_suggestion_links.py`
rarely — only if captured trades predating the telemetry era (first `assets_json`
impression, 2026-08-16) somehow lack link rows; telemetry-era trades are deliberately left
to the live matcher. First corpus report:
`docs/business/analytics/2026-08-16-organic-trade-corpus.md`; scope addendum:
`docs/plans/matchmaking-engine/backfill-scope.md`.
## ESPN identity binding — one-time cohort re-sign-in (#321, 2026-08-16)

The identity-binding release (feedback #321) verifies WHOSE ESPN account a
captured cookie pair belongs to, not just that it works. Two support-visible
effects:

**1. Every ESPN-connected user is signed out of ESPN exactly once.** The
deploy runs a one-time migration (`_evict_prerelease_espn_verified_stamps`,
`backend/database.py`) that nulls every `espn_credentials.verified_at` stamp
minted before the release cutoff — **any vintage, including sign-ins that
were done correctly after the 2026-08-12 fixes** — because no pre-release
stamp proves *identity* (the pre-release oracles accepted any valid ESPN
session). Expected, deliberate, and resolved by one re-sign-in through
Settings / the send flow, which now verifies identity before storing. The
encrypted pair is kept (row not deleted); status simply reads *not
connected* until re-proven. The migration is idempotent (date-bounded +
NULL-fails-`<`), so re-deploys never re-sign anyone out.

**2. A new rejection users may ask about: "it says my account doesn't own
this team."** The wrong-account 403 copy is: *"That ESPN account can't open
your linked league, so nothing was saved. Sign in with the ESPN account
that owns your team."* It means the ESPN sign-in WORKED but belongs to a
different human than the linked league's bound team (the #321 bleed shape:
someone else signed in to ESPN on that device), or the user picked the
wrong team at import. Fix: sign in with the owning ESPN account — or
re-link the league and pick the right team. Wire code is still
`espn_bad_credentials`; the additive `reason: "wrong_account"` field is
what drives the dedicated mobile copy. Diagnosis from logs: grep
`identity mismatch` (store / team-binding / re-sync variants all log it).
