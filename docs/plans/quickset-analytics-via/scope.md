# Feature Scope — Quick Set `via` gap fix (unscoped walks tag `via:'quickset'`)

**Date:** 2026-08-24
**Entry point:** direct ask — analytics gap found while planning Group F (quickset tier-drop fix)
**Builder:** Claude session (branch `claude/elegant-feynman-c3689e`)
**Operator sign-off on waivers:** not needed (no waivers). The change was held
for operator confirmation before merge (bright-line analytics surface, per the
2026-08-13 dropped-emitter addendum's precedent) — **confirmed and merged
2026-08-25 (PR #196)**.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — this change ships **no new event and no
  registry change**; it makes an already-registered, already-deployed server
  branch reachable and corrects the record on its semantics:
  - `quickset_completed` (SERVER_FIRED, INTENT — unchanged classification):
    fires per `via:'quickset'`-tagged tier commit. Zero production firings
    before this fix because no client ever sent the tag. Answers "did anyone
    use Quick Set?" (`FEATURE_VERTICALS["rank_quickset"]`, funnel stage 4,
    ranking-surface mix).
  - `tier_save.props.via` now honestly distinguishes `'quickset'` commits from
    full-board `'tiers'` saves (the tracking-plan-v2 §S3 dichotomy, dark until
    now).
  - `users.ranking_method` gets `'quickset'` written at the point of use
    (P0-1's design, previously unreachable for the tag).
  - Per-position completion stays a derived read: `quickset_step_advanced`
    with `tier_index == tier_count - 1` (client, INTENT, already registered).

  → follow-through: `docs/data-dictionary.md` updated;
  `docs/cross-client-invariants.md` §events updated; tracking-plan addendum
  [docs/business/analytics/2026-08-24-quickset-via-gap.md](../../business/analytics/2026-08-24-quickset-via-gap.md)
  records the correction, the seam, and the accepted losses.
  `NON_INTENT_EVENTS` untouched **deliberately**: no name is added or
  reclassified in this change.

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags: **none**
- New env vars / `model_config` keys: **none**
- API surface: **none** — `via:'quickset'` has been in the
  `POST /api/tiers/save` whitelist since analytics P0; the client starts
  sending an already-accepted value. Old servers were never deployed without
  it; unknown values fall back to `'tiers'` regardless.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-quickset-via.js`
  (`npm run test:quickset-via`) — pins: `saveTiers` opts.via union carries
  `'quickset'` + the three rookie tags; the walk's save ternary tags
  `{via:'quickset'}` on the non-rookie arm and `rookie_quickset` on the rookie
  arm; `TiersScreen` never sends `'quickset'`; no client
  `quickset_completed` emitter exists; the server whitelist, the FR-20
  branch, and the `_note_ranking_method` gate all still exist. **Sabotage
  proof:** reverting the non-rookie arm to `undefined` (the original bug)
  turns the guard RED (`FAIL unscoped Quick Set saves pass { via: 'quickset' }`);
  green on restore.
- [x] **Unit tests:** none added — the server branch is unchanged and already
  pinned: `backend/tests/test_analytics_p0.py::test_quickset_completed_fires_with_props`
  (tagged save fires with props), `::test_quickset_event_absent_for_plain_tier_save`,
  and `test_rookie_scope.py::test_rookie_via_tags_are_recorded_and_do_not_fire_quickset_completed`.
- [x] **Code-walk proof** (the one behavior change, request-body only):
  1. `mobile/src/screens/QuickSetTiersScreen.tsx` `saveMutation.mutationFn`
     → `saveTiers(position, …, rookieScope.isRookie ? {scope:'rookie', via:'rookie_quickset'} : {via:'quickset'})`.
  2. `mobile/src/api/rankings.ts` `saveTiers` spreads `{via: opts.via}` into
     the `POST /api/tiers/save` body (union widened to accept `'quickset'`).
  3. `backend/server.py` `save_tiers_route`: `via` whitelist admits
     `"quickset"` → `_note_ranking_method(sess, "quickset", allow_over=("anchor",))`
     (unscoped only), `tier_save` props carry `via:"quickset"`, and the
     `if via == "quickset"` branch fires `quickset_completed`
     (`duration_ms`/`skipped` absent from the body → null, as documented).
  4. Every other `saveTiers` caller (`TiersScreen`, rookie surfaces) passes
     the same opts as before → responses and writes byte-identical for them.
- [x] **Manual TestFlight checklist** (runtime proof — the tag rides a real
  request):
  1. On a build containing this fix, open Rank → Quick set (any position),
     select ≥1 player on the first rung, tap Save, finish or abandon the walk.
  2. Operator runs `python3 -m backend.tools.prod_analytics` (or queries
     `user_events`) for that account: expect ≥1 `quickset_completed` row
     (`position` matching, `players_placed` ≥ 1, `duration_ms`/`skipped`
     null) and the same save's `tier_save` row with `props.via = "quickset"`.
  3. Regression: make an ordinary Tiers-board save (Rank → Tiers → move a
     player → Save): its `tier_save` row must still carry `via:"tiers"` and
     fire **no** `quickset_completed`.
- `testID`s added/renamed: **none** (testid-lint unaffected; still run in CI)

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed/removed; no contract change — the body value was already accepted |
| `living-memory/LLD.md` | n/a | no convention shift; the tiers-save `via` convention predates this change and is unchanged |
| `docs/architecture.md` | n/a | no module wiring or data-flow change |
| `living-memory/HLD.md` | n/a | no architecture change |
| `docs/cross-client-invariants.md` | updated | §events — `quickset_completed` semantics correction + seam |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` entry | updated | DECISIONS.md — per-commit semantics chosen over a per-position signal the save route cannot honestly produce |
| `docs/data-dictionary.md` | updated | `user_events` event_type taxonomy — `quickset_completed` row |
| tracking plan | updated | new addendum `docs/business/analytics/2026-08-24-quickset-via-gap.md` |

## 5. Ship gate declaration

- **CI green:** required on the pushed sha before merge (`backend-tests` +
  `mobile-typecheck` incl. `check-*.js` + `maestro-testid-lint`). Local:
  `node tests/check-quickset-via.js` green, `tsc --noEmit` green, pytest run
  logged in TEST_LEDGER.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-08-24 entry.
- **TestFlight verification:** checklist in §3, to be run by the operator
  after the next mobile release containing this change.
- Express lane declared by the operator? **No** — full gates.
