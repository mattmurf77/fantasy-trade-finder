# #168 / #172 — "Looking for" intents on the Guided finder · PRD (proposal only)

**State:** NOT BUILT (2026-07-25). Stretch item in the #156 finish batch;
the clean-mapping condition was not met, so this PRD proposes the design
instead of code.

## Feedback

- **#168:** users want to tell the finder WHAT they're looking for in
  categorical terms ("looking for" categorization) rather than only
  naming players/positions.
- **#172:** specifically the consolidate / tier-up vs. spread-out /
  tier-down intents ("2-for-1 me into a stud" / "split my stud into
  depth").

## Why no code this round

The condition was "IF the existing engine params support it cleanly."
They don't: `POST /api/trades/generate` exposes only
`fairness_threshold`, `pinned_give_players` / `pinned_receive_players` /
`pinned_give_mode`, `opponent_user_id`, and `force`. The engine-side
levers that WOULD express these intents (crown-asset consolidation
premium, package-shape enumeration, `outlook_direction_mult`, lane
classification) are global `model_config` knobs or flag-gated behaviors,
not per-request parameters — and the engine internals are another agent's
territory this round. A client-only fake (e.g. filtering the returned
deck by shape) was rejected as dishonest: it would silently discard most
of the generation budget instead of steering it.

## Proposed design (next round)

**UI (hub, Guided card → deck):** one optional single-select intent chip
row on the Guided deck header (mode bar area), mirroring the existing
lane-filter pill construction:

- `Consolidate` (tier up: 2/3-for-1 me into a better player)
- `Spread out` (tier down: 1-for-2/3, add starters/depth)
- `Win now` / `Build for later` (already partially covered by outlook —
  see open question 2)

**API:** additive `intent: 'consolidate' | 'spread' | null` on
`/api/trades/generate` (omitted = today's behavior, byte-identical).
Pinned-job-style cache bypass NOT required if intent is added to the
job-freshness key.

**Engine mapping (the part that needs the engine owner):**
- `consolidate` ⇒ restrict enumerated shapes to |give| > |receive|
  (2-for-1, 3-for-2), or strongly re-weight composite toward them; apply
  the existing crown-asset premium unconditionally on the receive side.
- `spread` ⇒ mirror (|give| < |receive|), waiver-slot cost awareness
  already exists.
- Shape restriction composes with `pinned_give_mode:'all'` (#174) — a
  pinned package + `consolidate` is exactly the #172 ask.

**Acceptance criteria:**
1. `intent:'consolidate'` ⇒ every returned card has |give| > |receive|.
2. `intent:'spread'` ⇒ every returned card has |give| < |receive|.
3. Omitted intent ⇒ byte-identical decks (existing tests stay green).
4. Empty results surface the honest empty state (no silent fallback to
   unshaped cards).

**Open questions:**
1. Should intent persist per league (like outlook) or per session (like
   pins)? Recommendation: session-only, like pins — it's a query, not a
   preference.
2. Overlap with `trade.outlook_direction` (#175): win-now/build-later may
   be redundant with outlook steering — consider shipping only
   consolidate/spread and letting outlook keep owning the time axis.
3. Whether `Consolidate` should implicitly raise the crown-asset premium
   or only restrict shapes (engine owner's call — premium changes touch
   pricing).
