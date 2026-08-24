# Tracking-plan addendum — the Quick Set `via` gap (2026-08-24)

**Status:** built on branch `claude/elegant-feynman-c3689e`; **awaiting operator
confirmation before ship** (analytics events are a bright-line surface per root
CLAUDE.md; the 2026-08-13 addendum set the same hold-for-confirmation
precedent).

## What this is

A correction to the record on `quickset_completed`, plus the one-line client
fix that lights it up. **No taxonomy registry change** — no new name, no
reclassification, no prop change. The event stays `SERVER_FIRED` and INTENT
exactly as registered.

## The gap

`POST /api/tiers/save` has branched on `via == "quickset"` since analytics P0
(FR-20): it fires `quickset_completed`, stamps `tier_save.props.via`, and
writes `ranking_method = 'quickset'` at the point of use (P0-1). But **no
client has ever sent that value**:

- `mobile/src/api/rankings.ts` `saveTiers` only ever whitelisted the
  `rookie_*` forensic tags (added in rookie-draft M2), and
  `QuickSetTiersScreen.tsx` passed `via` only on rookie-scoped saves
  (`rookie_quickset`, which deliberately does NOT fire the event —
  `test_rookie_via_tags_are_recorded_and_do_not_fire_quickset_completed`).
- Web has no Quick Set surface at all (`git grep quickset -- web/` is empty).

So every unscoped mobile Quick Set save landed as the default `via:'tiers'`:
`quickset_completed` has had **zero production firings ever**, `tier_save`
rows never distinguished the Quick Set surface, and `_note_ranking_method`
recorded those users as `'tiers'` (unlock behavior identical — both values
share the same unlock arm — but the forensic method label is wrong, and the
`quickset-done` fixture's `ranking_method: 'quickset'` shape was never
producible by the shipped clients).

The 2026-08-13 dropped-emitter addendum then **deleted the client
`quickset_completed` emitter** on the stated ground that "the server row is
the authoritative completion" — true in intent, false in fact. Since that
build, Quick Set completion has had no live signal on either side.

## The semantics correction

Multiple docs claimed the server row fires "per completed position." It
cannot, and never could:

- Quick Set saves **rung by rung** (one `/api/tiers/save` per tier step with
  picks or clears); the route has no way to know which commit is the walk's
  last.
- A step advanced by Skip, or with nothing selected, saves nothing — and the
  walk's selection starts EMPTY (not consensus-pre-selected), so a user who
  accepts consensus by tapping Continue through every rung completes the
  position with **zero server contact**.

Corrected contract, now reflected in `backend/server.py`,
`backend/analytics_taxonomy.py`, `docs/data-dictionary.md`, and
`docs/cross-client-invariants.md`:

- **`quickset_completed` = one Quick Set tier COMMIT** (a
  `via:'quickset'`-tagged unscoped save). `players_placed` is that commit's
  count. Up to 8 rows per position walk; possibly zero.
- **The per-position completion read is client-side:**
  `quickset_step_advanced` with `tier_index == tier_count - 1` (fires on
  every advance — save, skip, or empty — and is already registered INTENT).
  `quickset_abandoned` is its complement.
- `duration_ms` / `skipped` remain registered on the server row but are
  **null from current clients** — with per-commit firing there is no honest
  whole-walk duration to attach. `quickset_step_advanced.ms` carries
  per-rung timing. (`report_time`'s quickset duration read therefore stays
  dark; that is honest, not a regression — it was dark before too.)

## The fix (one emitter change, mobile only)

`QuickSetTiersScreen` now passes `{ via: 'quickset' }` on unscoped saves
(`mobile/src/api/rankings.ts` widens the `saveTiers` opts union). Rookie-scoped
saves keep `rookie_quickset` unchanged. `TiersScreen` and every other caller
still send no `via` ⇒ `'tiers'`. Server code is untouched — the branch has
been deployed and tested (`test_quickset_completed_fires_with_props`) since
P0; it was simply unreachable.

Takes effect from the first TestFlight build containing this change.

## What lights up at the seam

| Read | Before | After |
|---|---|---|
| `FEATURE_VERTICALS["rank_quickset"]` | permanently zero | counts Quick Set commits |
| Funnel stage 4 `board_started` | Quick Set users entered via `tier_save` only | unchanged users, plus the event itself qualifies |
| Ranking-surface mix (`analytics_queries` board-source read) | Quick Set activity misattributed to `tier_save`-generic | `quickset_completed` rows appear |
| `tier_save.props.via` | always `'tiers'` from mobile | `'quickset'` on Quick Set commits |
| `users.ranking_method` | `'tiers'` written at point of use for chooser-bypassing Quick Set users (#244 launch route) | `'quickset'` (same unlock arm; label now matches the `quickset-done` fixture) |

Do not trend `rank_quickset` or `tier_save.via` splits across the seam; every
prior row is structurally `'tiers'`.

## Accepted losses (unchanged by this fix)

- A consensus-accepting walk (all rungs skipped/empty) is server-invisible —
  measurable only via `quickset_step_advanced` / the client receipt.
- The `onboarding` prop lost in the 2026-08-13 deletion stays lost; the named
  escape hatch (a NEW client name, e.g. `quickset_walk_finished`) remains
  unused. If per-position completion ever needs to be a first-class *event*
  rather than a derived read, that is the honest path.
