# Feature Scope — League-mates' assumed outlook from the saved playoff forecast

**Date:** 2026-11-12
**Entry point:** direct ask. The operator: "Assumed team outlooks should use our projections for non app users. For example paulsmenis is shown as 'looks contending' when he has almost no chance to make the playoffs"
**Builder:** Claude Code subagent, worktree `feat/partner-outlook-from-projection` (from `origin/main` `564ff857`)
**Operator sign-off on waivers:** needed for §1 (analytics waived) and §3 (no TestFlight checklist until the client accepts the new tag source, see §6)

---

## 0. What changes

A league-mate with no saved outlook used to be assumed whatever `trade_service.infer_team_outlook` read off their roster (the **roster read**). With flag `trade.partner_outlook_projection` on, when the viewer's saved weekly forecast is usable by the same test as the viewer's outlook suggestion (`league_projections.recommendation.unusable_reason`: current, complete, current model), that league-mate is assumed from their own playoff probability in it:

| Playoff probability (unrounded) | Assumed outlook |
|---|---|
| at or below 45% (`recommendation.REBUILDING_MAX`) | `rebuilder` ("Looks rebuilding") |
| above 45% | `contender` ("Looks contending") |

Never `jets` or `championship` for a league-mate: Tanking carries hard rules (no outgoing own next-year pick, no RB without a long-term case) that must not be applied to someone on a guess.

**Precedence per league-mate:** saved outlook (`declared`) → projection read (`projection`) → roster read (`roster`, today). The viewer's own outlook is not touched (D-230).

**Mapping:** forecast teams are keyed by Sleeper `roster_id`; league-mates by the roster's owner id. `partner_outlook.projection_reads` maps them with `sleeper_roster.owns_roster` over the rosters the session's init read (`sess["sleeper_roster_index"]`, set in `session_init`; the prepared-inventory session takes the source's rosters). A co-owner is an alias of the primary owner. A member with no roster, more than one roster, or a roster without a valid probability keeps the roster read.

**One server-side decision, every consumer:** `backend/partner_outlook.py` (`assumed`, and `public` for surfaces that never show a saved outlook).

| Consumer | Before | Now (flag on) |
|---|---|---|
| Trade engine partner input (`_owner_generation_context` → `manager_preferences[uid]["inferred_outlook"]` → `trade_gen_owner._team`, all owner revisions incl. rules-first) | roster read (revision 3: `not_sure`) | projection read for an undeclared league-mate when available; else unchanged |
| Fit block "Them" tag (`_fit_league_context` reads `inferred_outlooks`) | roster read, `source: "roster"` | the same projection read, `source: "projection"`, same text |
| Team Review partner groups (`member_windows`) | roster read (composite) | projection read for an undeclared league-mate; row gains `outlook_source` |
| Request evidence (`_owner_selected_assignment` input) | — | `manager_preferences[uid].outlook_source` per league-mate |
| Owner proof (counterparty block) | — | `outlook_read` (declared / projection / roster) |

Not changed (reported, not consumers of the owner path's assumed outlook): the legacy v2 generator (`trade_gen_v2`) and legacy TradeService path (`trade_service` `_infer_outlook`), the counterparty breaker (`trade_breaker`, flag off), the value core (`value_core/windows.py`, flag off), the mock draft's CPU drafters (`server` ~26096), the roster-evaluation context (`_build_trade_roster_context`, which never used a league-mate's inferred outlook), the eval/calibration tools.

**Reads:** one read of the saved run per trade request (`_trade_job_preferences`, which every entrance calls), carried into the worker in `prefs_preload["partner_projection"]`; a worker with no preload reads once itself; Team Review reads once per request; selected-search entrances read once inside `_owner_generation_context`. Never per league-mate, never a queued run, never a provider call. Parsed results are memoised by run id.

**Caching:** the reads are in the preload, which `_trade_request_signature` hashes, so the job cache (`_trade_job_is_fresh`), stored first pages (`config_signature`) and prepared inventories (`dependency_receipt.preferences`) built under other reads never serve as current, including when a forecast goes stale by time (the next request reads `None`). This is the mechanism the viewer's seeded outlook already uses ("the seeded outlook is in config_signature"); a league-mate's saved-outlook change instead revokes input epochs, which cannot see a forecast state change. `DECK_PIPELINE_VERSION` 22 → 23 (`_run_trade_job`, `_owner_generation_context`, `_fit_league_context` changed; new `_apply_partner_outlooks` listed); `partner_outlook.py` joins `_ENGINE_CODE_MODULES`.

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** no event answers "how often is a league-mate's outlook from the forecast"; the request evidence and proofs record it per job.
- [x] **(c) WAIVED — no analytics needed because:** the change re-sources an existing engine input; the source is recorded in the owner request evidence (`manager_preferences[uid].outlook_source`) and the proof (`outlook_read`), which already land with impressions. No client interaction is added.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: `trade.partner_outlook_projection` — `FLAG_KEYS` (code default false), `config/features.json` **true** (the operator asked for the behaviour) with `_comment_partner_outlook_projection`, mirrored in `backend/tests/fixtures/flags/{release,profiles-on,onboarding-v2}.json`, `docs/config-reference.md`. It also requires `league.projections` (as `league.projection_outlook` does): with that off there is no forecast to read. **`league.projections` is false in `config/features.json`**, so the feature is dark in repo config until projections are on wherever production turns them on. Graduation: the flag can be removed once the client accepts `source: "projection"` and a week of decks shows no regression.
- New env vars / `model_config` keys: none. Rollback lever: the flag + `POST /api/feature-flags/reload`.

## 3. Evidence scope

- [ ] **Structural guard:** none (no client change in this build; see §6).
- [x] **Unit tests:** `backend/tests/test_partner_outlook_projection.py` (41 cases, every behavioural test proven RED against a named sabotage); `test_fit_block_v3.py` tag-table pin extended; `test_deck_pipeline_digest.py` pin 23.
- [x] **Code-walk proof:** §0 table, file:function cited.
- [ ] **Manual TestFlight checklist:** deferred until the client accepts the new tag source (§6). Then: (1) a league where a non-app league-mate has under 45% in the saved forecast and a roster that reads contending — their card's "Them" tag reads "Looks rebuilding"; (2) Team Review's partners beat lists them among rebuilding teams; (3) a league-mate who saved an outlook keeps their roster read on the tag.
- [ ] **WAIVED because:** —
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `fit_block.teams[].tag.source` gains `projection`; `/api/league/team-review` `partners.opposed_window[].outlook_source` |
| `living-memory/LLD.md` | n/a here | living-memory is out of this worktree's scope; the caller writes the DECISIONS/LLD/CHANGELOG/TEST_LEDGER entries |
| `docs/architecture.md` | updated | owner context paragraph (assumed outlook of an undeclared league-mate) |
| `living-memory/HLD.md` | n/a | no new module boundary beyond a leaf helper |
| `docs/cross-client-invariants.md` | updated | § Fit block: tag `source: "projection"`, the assumed-outlook precedence and bands, the client allowlist |
| `docs/glossary.md` | updated | Outlook tag; new **Assumed outlook**, **Roster read** |
| `docs/config-reference.md` | updated | the flag row |
| ADR or `DECISIONS.md` entry | for the caller | precedence, two bands, the request-signature caching mechanism, `public` never showing a saved outlook |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` (counts in the build report); no mobile change.
- **Evidence recorded:** the caller logs the sabotage table in `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** after §6.
- Express lane declared by the operator? no.

## 6. Open: installed clients drop a `projection` tag

`mobile/src/api/trades.ts` (fit block parser, `t.tag.source === 'declared' || t.tag.source === 'roster'`) and `mobile/src/shared/types.ts` (`FitBlockTeam.tag.source: 'declared' | 'roster'`) drop any other source. With this flag on, installed builds show **no "Them" tag** for a league-mate whose read came from the forecast (the lead and ranks still render, and the engine and Team Review use the projection read). A client change accepting `'projection'` (rendering `text` verbatim, as for `roster`) fixes it; until it ships, the operator may prefer to serve the tag with `source: "roster"`. Team Review's mobile partners beat does not read `outlook_source`.

Four bands instead of two (synthetic 12-team leagues, everyone undeclared, a value-ranked forecast): 5 of 11 league-mates per league would move to Tanking or All-in, and the served deck's top 30 would share only 14–21 cards with the two-band deck — the Tanking hard rules would then govern trades with managers who never chose them.
