# ADR-020: Overhaul plans classify depth/backup roster blockers as advisory; the global engine rule is untouched

Date: 2026-09-07
Status: Accepted for the team-overhaul v1 build (flag `overhaul.enabled`, ships dark)

## Context

`backend/trade_roster.evaluate` is the ONE two-sided post-trade roster check. Its `_team_result` emits four blocker families for each team: `legal_deficits:<group>` (a required starting slot can no longer be filled), `cuts_required` (active count exceeds the platform capacity), `deficits:<group>` (a quality-threshold starter is lost) and `backup_depth:<group>` (the Hall condition — one usable replacement per constrained group — no longer holds). The deck's full-roster gate (2026-09-04) treats all four as blocking, and `backend/CLAUDE.md` says so: "Current safety policy also protects usable depth; do not remove it globally to produce more rebuild offers."

A team overhaul is, by the owner's definition, a substantial roster change. `Blow it up` sells productive starters for picks and youth; `Push all in` consolidates depth into stars. Both **legitimately** reduce quality depth. If the plan-level compatibility check ([BUILD-CONTRACT §5.4](../plans/team-overhaul/BUILD-CONTRACT.md)) blocked on `deficits:*` / `backup_depth:*`, no honest rebuild roadmap could ever validate — and the engineering spec is explicit that "quality/backup preferences must not silently become a new hard rule that makes an intentional rebuild impossible" while also demanding that "any plan-scoped change to existing protection policy needs a documented ADR."

## Decision

At the **plan level only** (`overhaul_service.validate_prepare`, run on the final union of every chosen offer per counterparty):

- `legal_deficits:*` and `cuts_required` → **blockers** (`lineup_illegal`). Platform legality, ownership and capacity are never relaxed.
- `backup_depth:*` and `deficits:*` → **warnings** (`depth_reduced`). They are shown on the receipt and the summary; they do not stop a send.
- Every `trade_roster` unknown is carried verbatim into `receipt.unknowns`; an unknown is never relabelled safe.

The global engine rule is **not** changed: `trade_roster.py`, `trade_roster_adapter.py`, the deck's full-roster gate and every existing caller keep treating all four families as blockers. The classification lives in the overhaul module and nowhere else. Capacity is still enforced arithmetically across the whole plan (worst case over one alternative per package, capped at 200 combinations, beyond which the per-package maximum is used — strictly more conservative).

## Alternatives considered

- **Keep depth blocking at plan level.** Rejected: it makes the feature's defining outlooks unreachable and contradicts the owner's stated intent (R3.1 — moving productive players *is* the point).
- **Relax the engine rule globally or behind a flag.** Rejected: the deck must keep protecting usable depth for ordinary single trades; a global relaxation to serve one feature is exactly what the spec forbids.
- **Drop the depth check from the overhaul entirely.** Rejected: the user should still *see* what a plan costs in depth; advisory is the honest middle.

## Consequences

- Overhaul receipts can be `ok: true` while carrying `depth_reduced` warnings; clients must render warnings, not just blockers.
- If the engine later adds new blocker families, `validate_prepare`'s classification must be extended deliberately — an unrecognised family is neither blocking nor advisory today and would be silently ignored; add a test when that happens.
- Reverting this ADR is a two-line change in `validate_prepare` (move the two prefixes into the blocking branch) and a copy change on the summary.
