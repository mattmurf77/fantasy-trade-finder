# 8. Per-league strategy/outlook

> Tier 1 · #8 · ENH · Effort S · Sources: OP

## Summary

A user contending in one league is rebuilding in another — the same trade card is right in one context and insulting in the other. **Code correction to the backlog framing:** outlook storage is *already* per-league end-to-end. `league_preferences` is keyed by `(user_id, league_id)` with a unique constraint (`uq_league_pref` in `backend/database.py`), `GET/POST /api/league/preferences` takes `league_id`, the web client loads prefs per `currentLeagueId` (`web/js/app.js` ~4037), mobile queries per league and opens `OutlookSheet` when `team_outlook` is unset (`mobile/src/screens/TradesScreen.tsx`), and the trade job reads `load_league_preference(user_id, league_id)` in `_run_trade_job` (`backend/server.py`, the prefs block near line 1494). So the "move from global to per-league" half of the backlog item is already shipped; what remains is making per-league outlook *smart*.

The real gaps: (1) a new league has no row, so the engine silently runs the user at `outlook=None` → `not_sure` α 0.50 until they hand-fill a blank picker — per league, every league; (2) the first-run prompt is a cold five-option sheet that demonstrates nothing about the product's intelligence. This item closes both by defaulting unset leagues from #1's classifier run on the user's *own* roster, and converting first-run into a confirm — "We think this team is rebuilding — right?" (backlog #82) — which simultaneously fixes the default, demonstrates intelligence in the first session, and collects labeled ground truth for the classifier. Small change, outsized correctness gain for exactly the multi-league users most likely to be power users.

## PRD

### Problem & user story

*As a multi-league user*, I shouldn't have to remember to configure each league before suggestions make sense; FTF already knows my roster in each league and should open with a sensible read on my window. *As a new user*, my first trade deck shouldn't be priced on a 50/50 shrug just because I skipped a settings sheet.

Today: no `league_preferences` row → `outlook_value = None` → `outlook_alpha(None)` falls back to `outlook_alpha_not_sure` (0.50) (`outlook_alpha` in `backend/trade_service.py`). Mobile prompts on first land in the Trades tab; web exposes outlook in the find-a-trade config; both start blank with zero guidance.

### Goals / Non-goals

**Goals**

- Unset leagues get an inferred outlook (classifier on the user's own roster + pick capital) applied to trade generation immediately.
- First-run UX becomes a one-tap confirm of the inferred outlook, with override to the full picker.
- Confirmations/overrides are logged as classifier ground truth.
- Declared outlook remains authoritative once set (`upsert_league_preference` unchanged).

**Non-goals**

- Opponent-side inference — that's #1 (this item consumes the same function).
- Changing the outlook enum, α values, or blend math (`outlook_alpha_*`, `outlook_blend_mult` untouched).
- Migrating or backfilling existing `league_preferences` rows (declared values are never overwritten).
- Re-prompting cadence / seasonal re-confirm (noted as open question).

### Functional requirements

1. **FR1** — In `_run_trade_job`, when `load_league_preference` returns no row or a null `team_outlook` *(verify: column is `nullable=False`, so absence-of-row is the only unset state)*, compute `infer_team_outlook` (#1) on the user's own roster and use it as `outlook_value` for that job.
2. **FR2** — The inferred value participates in job-cache freshness exactly like a declared one: it flows into the job dict's `outlook_value` so `_trade_job_is_fresh` compares correctly and a later declaration invalidates via the existing `_invalidate_trade_jobs` hook on the preferences POST.
3. **FR3** — `GET /api/league/preferences` returns, when no declared row exists, `{"team_outlook": null, "inferred_outlook": "rebuilder"}` (additive, flag-gated) so clients can render the confirm prompt without a second call.
4. **FR4** — Confirm flow: tapping "Yes" writes the inferred value through the existing `POST /api/league/preferences` (becoming a normal declared pref); "No / pick another" opens the existing picker. Either way the prompt never reappears for that league.
5. **FR5** — Each confirm/override is recorded (existing `record_event` user-events path) with `{league_id, inferred, chosen}` for classifier calibration.
6. **FR6** — Flag OFF ⇒ behavior identical to today (None → `not_sure`, blank picker).

### UX notes

- **Mobile:** `TradesScreen.tsx` already opens `OutlookSheet` when `team_outlook` is falsy; change the sheet's first-run mode to lead with the inferred option pre-selected and copy "We think this team is rebuilding — right?" + [Sounds right] / [Pick something else]. `OutlookSheet.tsx` gains an `inferred` prop.
- **Web:** the find-a-trade first-run config (`web/js/app.js`, `_pendingOutlookValue` save paths ~4131/4167) pre-selects the inferred outlook with the same confirm copy.
- **Extension:** no outlook UI today; nothing to do.
- Copy must say *why* ("young roster, 3 extra firsts") when signals are available — one line, from the classifier's `signals` output, builds trust in #1 across the whole product.

### Success metrics

- % of active leagues with a non-null effective outlook in trade jobs (target ~100% with flag ON vs. today's declared-only rate).
- Classifier agreement rate: confirms / (confirms + overrides) — this is the #1 calibration metric.
- Time-to-first-generated-deck for new leagues (confirm is one tap vs. five-option decision).

### Acceptance criteria

- [ ] New league, no prefs row, flag ON: trade job runs with inferred outlook; job dict's `outlook_value` reflects it; declaring a different outlook invalidates the cached job.
- [ ] Declared row present: inference never runs; output identical to today.
- [ ] `GET /api/league/preferences` includes `inferred_outlook` only when flag ON and no declaration exists.
- [ ] Confirm writes a normal `league_preferences` row; event logged with inferred + chosen values.
- [ ] Flag OFF: API payloads and engine behavior byte-identical.
- [ ] `docs/api-reference.md` (preferences routes) and `docs/config-reference.md` (flag) updated.

## HLD

### Components touched

- `backend/server.py` — `_run_trade_job` outlook fallback; `/api/league/preferences` GET additive field; the generate route's cache-freshness pre-read (~line 3300) must apply the same fallback so cache keys agree *(both read sites must resolve identically or every cache hit misses)*.
- `backend/trade_service.py` — none beyond #1's `infer_team_outlook` (shared).
- `mobile/src/components/OutlookSheet.tsx`, `mobile/src/screens/TradesScreen.tsx`, `mobile/src/api/league.ts` (type).
- `web/js/app.js` first-run config block.

### Data flow

League open → client `GET /api/league/preferences?league_id=…` → no declared row → server runs classifier on user roster → returns `inferred_outlook` → client renders confirm → POST writes declaration (or user defers) → `POST /api/trades/generate` → `_run_trade_job` resolves declared-else-inferred → `generate_trades(outlook=…)` → `trade.outlook_blend` α applies to user values as today.

### Flags & config interplay

- **New flag:** `trade.outlook_seed`, default **false**. (Covers both the engine fallback and the API field; clients key the confirm UI off the field's presence, so no separate client flag.)
- Depends on `trade.outlook_blend` ON for the α to matter, and on #1's classifier function (can ship against the classifier even while `trade.outlook_infer` — the *opponent-side* flag — stays dark; the two flags are independent consumers of one function).
- Kill switch: flag off → unset leagues revert to `not_sure`; declared rows unaffected.

## LLD

### Engine changes

None in `trade_service.py` proper — consumes #1's `infer_team_outlook`. The α path is the existing `outlook_alpha(outlook)` → `outlook_blend_mult(pos, age, alpha)` user-value blend in `_generate_trades_v2` (flag `trade.outlook_blend`); this item only changes *which string* arrives in the `outlook` kwarg of `generate_trades`.

### API changes

- `GET /api/league/preferences?league_id=…` (route `get_league_preferences`, `backend/server.py` ~4251) — additive:

```json
{"team_outlook": null, "acquire_positions": [], "trade_away_positions": [],
 "inferred_outlook": "rebuilder",
 "inferred_signals": {"youth_value_share": 0.61, "pick_share": 0.14}}
```

- `POST /api/league/preferences` unchanged (confirm writes through it; `upsert_league_preference` validation against `_VALID_OUTLOOKS` already covers the inferred strings).
- No new routes.

### Schema changes

None. (Deliberate: an inferred outlook is never *stored* — it's recomputed per request/job, so roster changes self-correct and there is no stale-default migration debt. Storing `outlook_source` was considered and rejected for v1; the event log carries provenance.)

### Client changes

- `mobile/src/api/league.ts` — add optional `inferred_outlook` (+ signals) to the prefs type.
- `mobile/src/components/OutlookSheet.tsx` — confirm-mode variant; `TradesScreen.tsx` passes the inferred value.
- `web/js/app.js` — first-run config pre-selection + confirm copy.

### Rollout

- Flag `trade.outlook_seed`, default `false`. Order: backend fallback + API field (dark) → mobile/web confirm UI → enable. Kill switch = flag off; since nothing is persisted, rollback is instant and clean.

### Open questions

1. **Re-confirm cadence:** rosters drift (the rebuild finishes). Re-prompt when the classifier flips bucket vs a declared value older than N months? Deferred; needs #1's agreement data first.
2. **Inference latency on GET:** classifier needs roster + pick data at request time on a Render cold start — confirm the prefs GET has cheap access to the synced roster *(verify; may need to read `league_members`/`draft_picks` directly rather than session state)*.
3. **Cache-freshness symmetry:** if the roster changes between the generate route's pre-read and the worker's read, inferred values could disagree and thrash the cache — acceptable, or pin the inferred value on the job at kickoff?

## As-built (2026-06-11)

Shipped the backend behind `trade.outlook_seed` (default false). As built:
- `_infer_user_outlook(user_id, league_id, sess, league)` + `_user_pick_share` helpers in `server.py`. Runs `infer_team_outlook` (from #1) on the user's own roster + pick share when no outlook is declared.
- Resolved identically in **both** the generate-route cache pre-read and `_run_trade_job`, so the job-cache freshness key (`_trade_job_is_fresh` compares `outlook_value`) agrees on both sides — no cache thrash (open question 3 resolved by computing in both places from the same `sess`, not pinning).
- `GET /api/league/preferences` adds `inferred_outlook` + `inferred_signals` when the flag is on and no declaration exists (additive, the confirm-UI hook).
- Nothing persisted — recomputed per request, so roster drift self-corrects (no `outlook_source` column).
- Tests: `backend/tests/test_outlook_seed.py` (5 cases: flag gating, young→rebuilder, old→contender, empty-roster guard, pick-share no-picks). Full suite 203 green.

Deferred (UI slice): the mobile `OutlookSheet` confirm variant + web first-run pre-selection (FR4 client copy "We think this team is rebuilding — right?"). The seed + API field are live; the one-tap confirm just writes through the existing `POST /api/league/preferences`, so the confirm UX is purely client work.

## Dependencies & sequencing

- **Depends on:** #1 (`infer_team_outlook` — the function, not the `trade.outlook_infer` flag).
- **Feeds:** #82 first-run confirmation (this *is* #82's mechanism), #87 onboarding workstream, #1's calibration loop (ground-truth events).
- Wave 1, immediately after #1 lands its classifier.
