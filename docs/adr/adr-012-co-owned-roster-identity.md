# ADR-012 — A co-owned Sleeper roster has one league identity: its primary `owner_id`

**Date:** 2026-08-15
**Status:** Accepted
**Author:** worktree session `claude/epic-hellman-6af20f`
(scope block: [`../plans/sleeper-co-owner-rosters/scope.md`](../plans/sleeper-co-owner-rosters/scope.md);
operator sign-off on all waivers + the additive API field, 2026-08-15)

## Context

Sleeper rosters carry an optional `co_owners` array beside `owner_id`. FTF never
read it: every roster→user match in the product — backend, mobile and web — was
`owner_id == user_id`.

Confirmed live on 2026-08-15 against the operator's own account (`mattmurf77`,
`313560442465169408`): in league `1338231586314780672` he **co-owns**
`roster_id 3`, whose `owner_id` is `460238423161040896`. Sleeper's
`GET /user/{id}/leagues` counts that league as his, so it appeared in the
picker — and then resolution found nothing. Two failures, not one:

1. No team: `user_player_ids` came back empty, so the session had no roster and
   nothing league-scoped worked.
2. Worse, the opponent filter was `owner_id != user_id`, so his own roster was
   posted as a **leaguemate** — the engine would generate trades between him and
   himself.

The obvious one-line fix — widen the client predicate, keep posting the caller's
own id as the league-member key — is wrong, and that is the decision this ADR
records. `league_members` is a league-**shared** table written by every member's
`session_init`. Roster 3 would get two rows: `(league, 313560…)` from the
co-owner's sync and `(league, 460238…)` from any other leaguemate's. A 12-team
league then carries 13 member rows with one roster duplicated — power rankings
render 13 teams, and `session_init`'s DB-member merge injects the second row as
a league member, handing the trade engine a **phantom copy of the caller's own
team** to trade against. That is worse than the original failure, which at least
failed visibly.

A single key every observer agrees on is required. `roster_id` would work but is
a schema change; `owner_id` is already that key in every roster-shaped consumer
we have — roster history's `team_key`, owned-pick sync, trade block, outlook.

## Decision

**A roster belongs to a user iff `user_id == owner_id` OR `user_id ∈ co_owners`.
A co-owner is an ALIAS of that roster's primary `owner_id` within the league,
never a separate team.**

The predicate lives in exactly one place per client —
`backend/sleeper_roster.py`, `mobile/src/api/sleeper.ts`, `web/js/app.js` — and
is listed in [`../cross-client-invariants.md`](../cross-client-invariants.md) so
the three cannot drift.

Every session now carries two identities, deliberately distinct:

| | Value | Governs |
|---|---|---|
| **Account identity** — `sess["user_id"]` | the real Sleeper user | rankings, swipes, tier overrides, entitlements, analytics, notifications, feedback |
| **League identity** — `sess["league_user_id"]`, read via `server._league_user_id()` | the resolved roster's `owner_id` | `league_members` key, power-rankings `is_you` + rank chip, free-agent "my roster", mock-draft owner set, Send-in-Sleeper roster resolution |

**They are the same string for a sole owner** — and for every session minted
before the key existed, since `_league_user_id` falls back to `user_id`. That is
what makes swapping a league-scoped comparison from one to the other safe, and
why the sole-owner path is byte-identical to its pre-2026-08-15 behavior.

The clients resolve the league identity (they already hold the rosters payload)
and send it as two optional, additive `POST /api/session/init` body fields,
`league_user_id` and `league_display_name`.

## Consequences

- **Both co-owners see the same team.** It is one team. Their boards stay
  personal, so their trade suggestions still differ in ordering.
- **Exactly one `league_members` row per roster**, whichever co-manager syncs.
  No 13th team, no phantom trade partner.
- **The team is labeled with the primary owner's Sleeper name**, not the
  co-owner's, because that row is what every *other* member sees. The caller's
  own team is marked by `is_you`, which is what the "You" badge already reads.
- **Known limitation, accepted:** two tables stay **account**-keyed —
  `member_rankings` (the team's board) and `league_preferences` (its declared
  outlook, read by leaguemates under `trade_outlook_infer`). `member_rankings`
  also feeds cross-league Trends aggregation, so re-keying it would attribute one
  person's board to another person's Sleeper id in community data. A co-owned
  team therefore reads to its leaguemates as having no board and no declared
  outlook unless the *primary owner* uses FTF — pure-consensus suggestions and
  roster-shape outlook inference. That is honest degradation, not corruption.
  Follow-up in `NEXT.md`; the open question is whether a *team* board/outlook and
  an *account* board/outlook are the same object.
- **Trust model unchanged.** `league_user_id` is client-asserted, exactly like
  the `user_id`, `user_player_ids` and `opponent_rosters` it arrives beside — a
  client that wanted to write another member's `league_members` row can already
  do so today via `opponent_rosters`. Resolving server-side instead was rejected
  on latency: `_sleeper_get` is uncached, so it would add a live Sleeper
  round-trip to `session_init`'s critical path on every launch.
- **No feature flag.** This is a correctness fix to a path that is already dead
  for the affected users; a default-off gate would leave those leagues dead.
  Rollback is a revert.

## Alternatives rejected

| | Why not |
|---|---|
| Client-side predicate only, caller-keyed `league_members` | Duplicates the roster into a 13th team and a phantom trade partner (see Context). |
| Re-key `league_members` on `roster_id` | Correct, but a schema change plus a migration for every existing league, to fix an identity bug. `owner_id` already carries the same guarantee. |
| Resolve the canonical owner server-side in `session_init` | Fully server-authoritative, but adds an uncached live Sleeper call to the launch critical path. The trust level is unchanged either way (see Consequences). |
| Re-key `member_rankings` too | Would make co-owned teams first-class in trade generation, at the cost of attributing a co-owner's board to the primary owner's id in cross-league Trends. |

## Verification

`backend/tests/test_co_owner_rosters.py` (33 tests) against
`backend/tests/fixtures/sleeper/co-owned-league/` — the real Bush League owner
ids and co-ownership with synthetic player lists. Seven of them fail if the
predicate is narrowed back to `owner_id` alone. Every co-owner assertion has a
sole-owner twin proving the common path is unchanged, including one that posts
an old-client body with neither new field.
