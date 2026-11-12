# Feature Scope — Sleeper trade universe crawler (research data collection)

**Date:** 2026-11-12
**Entry point:** direct ask (operator), research plan `docs/plans/sleeper-trade-universe/research-plan.md` (on branch of the trade-universe thread; §5, §8.1–8.2, decisions in §11), plus four operator additions relayed 2026-11-12: `--seasons` and backward reconstruction; every roster-changing event; standings as of each week with a check against Sleeper's records; schedule and as-of outlook inputs.
**Builder:** crawler-builder subagent, branch `feat/sleeper-universe-crawler`
**Operator sign-off on waivers:** needed for the waivers in §1 and §3 (both are "no app surface" waivers)

---

## 0. What this is, and the data it collects

A research program, not app code. `scripts/sleeper_universe.py` (logic `backend/sleeper_universe/`) reads Sleeper's public REST v1 API through one throttled client and writes only the git-ignored `data/sleeper-universe/`. The Flask app never imports it; no production database is read or written; nothing is uploaded.

**Collected:** league settings and format; rosters as pulled; every transaction (all types and statuses); weekly matchups (players, starters, per-player points, pairings) through the end of the season including unplayed weeks; drafts and picks; traded picks; both brackets; `/state/nfl` once per run. Derived: trades and their assets, rosters at each trade, weekly standings, outcomes, checks.

**Identity rules (operator decision 2, 2026-11-12):**
- No username, display name, team name, league or draft name, avatar, nickname, description or free-text note is written anywhere. `/league/<id>/users` is never stored raw.
- Every Sleeper user id (owner, co-owner, transaction creator, draft `picked_by`, draft-order keys, league members) is stored only as HMAC-SHA256 of the id under a secret key (env `SLEEPER_UNIVERSE_HMAC_KEY`, else `~/.config/ftf-sleeper-universe/hmac.key`, created 0700/0600, never inside the data folder). Weak, readable or conflicting keys are refused. Losing the key breaks linkage across pulls; the store refuses a different key.
- **The dataset is pseudonymous, not anonymous.** It keeps league ids and roster ids, so anyone holding it can look owners up through Sleeper's public API. The keyed hash keeps identity out of the store itself; it does not make the data shareable. The data folder is treated as personal data.
- Stripping is an allow-list per payload type (`backend/sleeper_universe/identity.py`, documented in the README).
- Seeds live only in `data/sleeper-universe/seeds.txt` (git-ignored), never in the repo, a test, a log or the store. Skipped leagues are recorded as league id, season and reason only.
- A leak scan after every run (and in `report`) reads every written file and fails on a dropped field name, a raw user id (found by hashing digit runs against the stored keys), or a name value seen during the run.

**Retention:** no limit; the data is kept for further analysis (operator decision 6, 2026-11-12). Deleting `data/sleeper-universe/` removes it entirely.

**Access:** covered by the operator's agreement with Sleeper for this app's development, as stated by the operator on 2026-11-12 (research plan §10).

## 1. Analytics scope

- [ ] (a) New events specced
- [ ] (b) Existing events cover it
- [x] **(c) WAIVED — no analytics needed because:** there is no user-facing surface and no app code path. The tool's own accounting is its `runs` table (parameters, request counts per endpoint, seconds, code version, NFL state, leak-scan result) and its report. No `user_events` row is written.

## 2. Schema & flag scope

- New/changed tables or columns in the app (`backend/database.py`): **none**. The crawler's own SQLite schema is in `backend/sleeper_universe/store.py` and described in its README; it is not an app table, so `docs/data-dictionary.md` is not the place for it.
- New/changed feature flags: **none** (not a product feature).
- New env vars: `SLEEPER_UNIVERSE_HMAC_KEY` (optional) → added to `docs/config-reference.md`. Rollback lever: none needed; the program only runs when the operator runs it.

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_sleeper_universe_client.py` (throttle, rate cap, retries, 429 hard stop, counters, one live client), `_discovery.py` (dedup, hops, cap and revival, lineage and season range, dynasty filter reasons, `--seasons` widening keeps lineage ids and checkpoints), `_pull.py` (kill mid-league and resume gives the same store, `--limit`, no name or raw id in any written byte, key linkage and key dependence, key file 0600, users never raw, leak scan), `_trades.py` (players/picks/FAAB from the committed manager-profiles fixture, three-team trade, pending excluded, pick resolution both ways, cleaning flags), `_reconstruct.py` (in-season, forward, backward with a rookie draft in between, agreement, every completed type counts, failed waiver never does, startup and rookie drafts, verifier and its cause attribution), `_standings.py` (median, tie, divisions, playoff cut-off and phases, games back, reported-record mismatch reported, outcomes, bye/unpaired, unplayed week by NFL state, standing helper, as-of inputs leak nothing after the trade), `_report.py` (numbers on a known world). Review hardening: `_safety.py` (one process per machine, hard stops, league-id check, list shapes, key rules, budget), `_no_bracket.py` (null brackets, no-playoff leagues, counted nulls, same-shape stop), `_hardening.py` (the independent reviewer's leak-scan planting and hostile-payload cases, bye weeks, score overrides, injected faults, failed-league back-off, seed rule, cap walk-back). Synthetic world: `backend/tests/support/sleeper_universe_world.py`. Each test was sabotaged red, restored green, checksum unchanged.
- [x] **Code-walk proof** for what tests cannot show: the live API's real shapes are only proven by the pilot (phase 2); the pilot report is that evidence.
- [ ] Structural guard / TestFlight checklist: **WAIVED because** backend research tooling only; no mobile or web surface. No `testID`s.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added or changed |
| `living-memory/LLD.md` | n/a (by builder) | no app schema/route convention shifted; living-memory is written by the main session |
| `docs/architecture.md` | n/a | no app module wiring or data flow changed; the package is outside the app's import graph |
| `living-memory/HLD.md` | n/a | as above |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md` | n/a | terms used (lineage, league-season, hop) are defined in the crawler README |
| ADR or `DECISIONS.md` | not by builder | non-obvious choices are stated in the README and module docstrings (lineage id stability, backward reconstruction, played-week rule, rank rule); the main session decides whether any warrants a D- entry |
| `docs/integrations/sleeper.md` | **updated** | new section "Research crawler: the Sleeper trade universe" |
| `docs/config-reference.md` | **updated** | `SLEEPER_UNIVERSE_HMAC_KEY` row |
| `scripts/README.md`, `scripts/CLAUDE.md` | **updated** | new "Research crawl" row and per-script traps |
| `docs/plans/README.md` | **updated** | `sleeper-trade-universe/` row |

## 5. Ship gate declaration

- **CI green:** `backend-tests` must pass with the new files (the full suite run is recorded in the builder's report); no mobile change.
- **Evidence recorded:** TEST_LEDGER entry to be written by the main session (the builder does not edit `living-memory/`).
- **TestFlight verification:** none (no app change).
- Express lane declared by the operator? No.
