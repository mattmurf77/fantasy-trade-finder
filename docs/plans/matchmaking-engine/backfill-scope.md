# Scope addendum — organic-trade backfill scripts (2026-08-16)

Operator directive 2026-08-16: backfill the organic executed-trade corpus, retro-link
historical suggestions to executions, produce the first patterns report. Addendum to
[telemetry-scope.md](telemetry-scope.md), which carries the full feature-scope block for
the suggestion.telemetry surface these scripts feed.

**Why this is an addendum, not a fresh feature-scope template:** the deliverables are two
operator-run ops scripts (`scripts/backfill_sleeper_trades.py`,
`scripts/backfill_suggestion_links.py`) plus a data report. No user-visible behavior, no
new data collection category (both tables — `sleeper_trades`,
`suggestion_trade_links` — and their capture semantics were scoped in telemetry-scope.md
and PRD #43), no schema change, no API-surface change, no analytics events. The template's
sections would all read "n/a — ops script"; per the template's own intent, an explicit
dated rationale beats a hollow copy.

Decisions the scripts embed (also in the module docstrings):

- **Flag-independent.** `market.trade_capture` gates only the background daemon;
  operator-run backfill runs regardless (it was ON at run time anyway).
- **Prior seasons via `previous_league_id`, depth 3 by default**, stored under the
  historical league id; chains from co-synced leagues converge and are swept once.
- **Retro linking is exact-hash-only** (historical impressions carry `trade_hash` but no
  `assets_json`), marked `match_type='retro_exact'`. No `match_basis` column exists and
  adding one for an ops backfill would cross the schema bright line — the distinct
  match_type string is the distinguisher.
- **Telemetry-era trades (traded at/after the first `assets_json` impression) are left to
  the live matcher**, which can do richer partial matching there; retro rows must never
  preempt it. Writes go only through `save_suggestion_trade_links` (insert-only,
  idempotent on `transaction_id`), so live-matcher rows are never overwritten.

Docs table: `docs/api-reference.md` n/a (no routes); `docs/data-dictionary.md` updated
(`retro_exact` match_type value); `docs/glossary.md` updated (same); `docs/runbook.md`
updated (§ Organic trade backfill); `docs/architecture.md` / HLD n/a (no module wiring
change); report at `docs/business/analytics/2026-08-16-organic-trade-corpus.md`.

QA: Maestro n/a (backend/ops only; Maestro retired per D-056 regardless); sim gate
Tier 4 (pytest) — `backend/tests/test_backfill_scripts.py` (20 tests) + full backend
suite, logged in `living-memory/TEST_LEDGER.md`.
