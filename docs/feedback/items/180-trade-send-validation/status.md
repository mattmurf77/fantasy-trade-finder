# #180 — Trade-send pre-flight validation

**Status:** Built (backend + mobile), live wherever `trade.send_in_sleeper`
is on (no new flag — the check only exists inside the flagged send flow).
2026-07-25.

Operator ask: "We should ensure that sending a trade on mfl or sleeper
considers any errors that is stopping a trade submission from getting sent
(such as roster limits or invalid rosters)."

## Reality check (what's honestly checkable)

- **Sleeper** send is a real server-side proposal (`POST /api/trades/propose`
  via the captured write API). Sleeper enforces its own rules at submission;
  FTF can only PRE-validate against Sleeper's public read API and surface
  findings before the user commits.
- **MFL** send does not exist yet (see
  [#177 feasibility](../177-mfl-auth-link/send-trade-feasibility.md)) — there
  is nothing to validate. When it's built, the same pre-flight pattern
  applies (rosters export + roster-limit math).

## What shipped

`POST /api/trades/validate` (backend/server.py; read-only, session-authed,
gated on `trade.send_in_sleeper`, **never blocks**) re-fetches the league's
live meta + rosters from Sleeper's public API and returns
`{checked, warnings:[{code, severity, message}]}`.

Mobile: `SendInSleeperButton` calls it before the send-confirm dialog. Any
findings replace the normal confirm with an honest warning list ("This trade
will likely fail" when a blocking finding exists, "Heads up before sending"
otherwise) with **Cancel / Send anyway** — the user stays in control and
Sleeper stays the authority. Validation being unreachable degrades silently
to the normal confirm (never breaks the send path).

## Checked by FTF vs delegated to Sleeper

| Condition | Who | How |
|---|---|---|
| League season closed/archived | **FTF** (`league_archived`, blocking) | league `status == "complete"` |
| Traded player no longer on the expected roster (dropped/re-traded since last sync) | **FTF** (`player_moved`, blocking) | give ⊆ my `roster.players`, receive ⊆ theirs, per a fresh rosters fetch |
| Post-trade roster size over the league limit | **FTF** (`roster_limit`, warning) | post-trade count vs `len(roster_positions) + reserve_slots + taxi_slots` — Sleeper may require a drop on accept, so this is advisory, not blocking |
| Either team unmatchable to a roster | **FTF** (`roster_not_found`, blocking) | owner_id lookup in the rosters payload |
| Player locked (game started) | Sleeper | not exposed pre-send |
| Trade deadline passed | Sleeper | deadline is in league settings but week/lock semantics are Sleeper's; deliberately not second-guessed |
| Review/veto windows, commissioner settings | Sleeper | post-proposal mechanics |
| FAAB validity / pick ownership | Sleeper | v1 send is players-only |
| Non-Sleeper league ids (MFL/ESPN imports) | — | meta fetch fails → `checked:false`, no false confidence (the send button is already platform-gated) |

**Assumption:** max roster = lineup slots (incl. BN) + IR + taxi, and
`roster.players` includes IR/taxi players — the standard Sleeper shape. If a
league mode violates it, the worst case is a spurious *warning* (never a
block).

## Tests

`backend/tests/test_trade_send_validate.py`: flag-off 404, bad-request 400,
clean trade → no warnings, unreachable league → `checked:false`, archived
league, give-side and receive-side player_moved, at-limit OK vs over-limit
warning (both sides), `their_roster_id` path, unknown counterparty.
