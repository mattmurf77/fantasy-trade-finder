# #183 — Hide IDP/unknown players showing as "Other" — status

**Status: fixed (server-side), research note delivered** · 2026-07-25 · branch `teardown-remediation` worktree

Operator report: some Sleeper rosters showed players as "Other" with a nonsensical id and no position or name; suspected IDPs; hide them for now and research IDP value sources for later.

## Root cause

Confirmed: roster player ids with no entry in the FTF player pool. The pool (DynastyProcess-derived) is offense-only, so IDP ids (LB/DB/DL) and team-DST ids have no metadata. `backend/power_rankings.compute_power_rankings` serialized them anyway as `{player_id, name: <raw id>, position: "?"}` rows, which the mobile drill-in (`LeagueSummaryScreen` roster overlay) bucketed under "Other" as id-only rows. The web power-rankings drill-in consumed the same payload.

## Fix

- `backend/power_rankings.py` — the roster loop now skips ids with no `players` metadata (`p is None`) before serializing. These ids hold no seed and no board entry, so their value is 0.0 by construction: totals, position summaries, and ranks are provably unchanged. Known players with non-core positions (K, DEF **with** metadata) still serialize — only id-only rows are hidden. Server-side, so mobile + web + extension all benefit; no client change needed (the mobile "Other" group simply no longer receives id-only rows).
- Tests: `backend/tests/test_power_rankings.py` — `test_unknown_roster_ids_hidden_from_roster` (IDP-style id + team-DST id omitted; K kept) and `test_unknown_roster_ids_do_not_move_totals` (totals/positions identical with and without the unknown ids). Full suite: **1047 passed, 1 skipped**.
- Docs: `docs/api-reference.md` power-rankings row notes the roster omission.

## Research (part 2)

See [idp-sources-note.md](idp-sources-note.md) — FantasyPros IDP dynasty ECR is the credible consensus source; DynastyProcess and KTC carry no IDP values today; niche paid charts exist (IDP Center, DTC). Feasibility: moderate, gated on a value feed, with per-league gating and a rosters-first (not trades) rollout suggested.
