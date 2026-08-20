# Feature Scope — Measurement rail (M1–M4: knob log + readout pack)

<!-- Filled per the feature-gate rule (CLAUDE.md §Conventions) from
     docs/templates/feature-scope.md. Skeleton required by LLD §7; covers
     PR-M's code surface: M1 (schema + set_config funnel + set_knob.py),
     M2 (bakeoff_readout.sql), M4 (tripwire queries). M5 (tester protocol)
     is doc-only and carried by docs/plans/trade-engine-accuracy/
     tester-protocol.md. M3 (fit_diag stamp) ships in PR-F2 and is covered
     by scope.md + the LLD, not here. -->

**Date:** 2026-08-20
**Entry point:** planned initiative — docs/plans/fit-challenger/PLAN-v2.md §2 (M1, M2, M4, M5), PR-M per PRD-build.md
**Builder:** PR-M coding agent (worktree trade-suggestions-review-69c9eb)
**Operator sign-off on waivers:** not needed (waivers below are the plan's own rulings, pre-approved via PLAN-v2/LLD sign-off 2026-08-20)

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** no new user-facing behavior and no
  user events. `model_config_changes` is **operator telemetry** (who flipped which knob,
  when, from where), not a user-behavior event — it deliberately lives outside the
  `user_events` taxonomy (LLD §7). The readout SQL only *reads* existing telemetry
  (`deck_impressions`, `deck_outcomes`, `trade_pass_reasons`, `bakeoff_runs`).

## 2. Schema & flag scope

- New/changed tables or columns:
  - **`model_config_changes`** (new table): `id`, `key`, `old_value` (NULL on first
    logged write), `new_value`, `changed_at` (ISO UTC), `source`; index
    `ix_model_config_changes_key (key, changed_at)`. Created by `metadata.create_all`
    in `init_db` (the repo's new-table idiom — no migration entry needed).
  - **`model_config.updated_at`** (new column, VARCHAR/ISO UTC): NULL until a key's
    first funneled write; added to the `Table` def **and** `migration_cols` (the
    additive try/except `ALTER TABLE` idiom). No backfill.
  - → `docs/data-dictionary.md` rows land in-PR (PR-M docs wave, per PRD-build §2 PR-M).
- New/changed feature flags: **none.**
- New env vars / `model_config` keys: **no new keys consumed by this package.** PR-M
  *seeds* all 17 fit/bakeoff knob rows (LLD §4 table) into `_MODEL_CONFIG_DEFAULTS` so
  `set_config`/`PUT /api/admin/config` never KeyError on them (HLD F-1) — their
  *consumers* arrive in PR-F1..F3, and the knob-inventory guard + scope-phase2
  disposition sentences land with those packages, which also own the
  `trade_service._DEFAULT_CFG` registrations. No knob **value** changes in-PR.
  Ship-the-knob / rollback lever: the whole package is additive and read-only at
  runtime; there is nothing to kill. `set_knob.py` is itself the rollback *tool* for
  every later flip.

## 3. Evidence scope

- [ ] **Structural guard:** n/a — backend + scripts only, no mobile surface.
- [x] **Unit tests:** `backend/tests/test_model_config_log.py` (new, 6 tests):
  `test_set_config_logs_change` (updated_at + change row + old_value, one txn — on an
  already-registered live knob per PRD-build's PR-M note),
  `test_set_config_unknown_key_still_raises` (KeyError, no change row),
  `test_admin_put_stamps_source` (source pass-through + `admin-api` default +
  response `old_value`), `test_admin_put_unknown_key_404s` (set_knob refusal case 2's
  contract), `test_migration_additive` (idempotent, pre-seeded tuned row untouched,
  updated_at NULL until first logged write), `test_fit_knob_defaults_seeded`
  (all 17 LLD §4 keys at their exact defaults). Sabotage-verified: deleting the
  change-row insert turns 2 tests red (verified locally 2026-08-20, then restored).
- [x] **Code-walk proof (every write path funnels through `set_config`):**
  `backend/database.py::set_config` is the only writer of `model_config` values —
  callers: `backend/server.py::admin_config_update` (PUT route, passes `source`,
  default `admin-api`) and `scripts/set_knob.py` (route mode → `source` in the body;
  `--local` mode → `set_config(..., source="operator-local")`). `git grep -n
  "update(model_config_table"` shows the single mutation site inside `set_config`;
  the seeding paths in `_migrate_db` use `INSERT OR IGNORE`/insert-if-absent only
  (never UPDATE), so they cannot clobber a tuned value and are not knob *changes*.
  Raw-SQL bypass caveat stands (PLAN-v2 M1): a bypassed write is dated-not-attributed;
  the per-run `config_json` snapshot diff catches it and R-5 defines the consequence.
- [x] **`set_knob.py` refusal cases (LLD §5.2, all implemented):** (1) non-float VALUE;
  (2) route 404 → "unknown key … needs its `_MODEL_CONFIG_DEFAULTS` row"; (3) no
  `CRON_SECRET` in `secrets.local.env` → fill it there, never chat; (4) no base URL
  resolvable in default mode; (5) `--local` while `DATABASE_URL` is non-SQLite.
  Secrets are read from `secrets.local.env` (the `prod_analytics.py` idiom) and never
  printed.
- [ ] **Manual TestFlight checklist:** n/a — no mobile/user-visible surface in PR-M.
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | owed in-PR (PR-M docs wave) | PUT `/api/admin/config/<key>`: optional body `source`, response gains `old_value`, side effect: change-log row |
| `living-memory/LLD.md` | owed in-PR (PR-M docs wave) | convention: every knob write funnels through `set_config`; flips via `set_knob.py` so they log + live-reload |
| `docs/architecture.md` | n/a | no module wiring change — one table, one column, one extended helper, two standalone scripts |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no client-facing constants/enums; clients never see the change log |
| `docs/glossary.md` | n/a | no new domain term ("knob log" is descriptive) |
| ADR or `DECISIONS.md` entry | owed at build wrap (PLAN-v2 §7) | the two planned ADRs cover the program; PR-M itself follows D-095/LLD rulings already recorded |
| `docs/config-reference.md` | owed in-PR (PR-M docs wave) | PUT `source` + change-log note; the 17 knob rows land with their consumer packages (PR-F1..F3) |
| `docs/data-dictionary.md` | owed in-PR (PR-M docs wave) | `model_config.updated_at` + `model_config_changes` (6 columns + index) |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` on the
  pushed sha (`FTF_SKIP_SIM_GATE=1` standing posture per D-056, evidence noted).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry at PR-M merge naming
  `test_model_config_log.py` (6 passed, sabotage-verified) and the neighbor sweep
  (`-k "config or database or admin"`).
- **TestFlight verification:** n/a (no checklist written — no runtime mobile surface).
- Express lane declared by the operator? **No — full gates** (PLAN-v2 §6: schema +
  config surface is bright-line; no express).
- **Rollback posture:** table + column are additive (NULL-tolerant, no backfill);
  the readout is read-only; no flag to flip. Reverting PR-M would only stop *logging*
  — it cannot affect generation or serving, which never read these surfaces.
