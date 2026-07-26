# FB-160 — tweener spots in Quick Set (design note — NOT built)

- **Screen:** QuickSetTiersScreen (guided tier walk)
- **Type:** idea / design exploration · **Status:** PRD only, 2026-07-25 — no implementation
- **Related:** FB-161 (demotion on save — shipped; changes the cost of a wrong tier), FB-136 (Quick Rank — within-tier ordering already exists)

## Problem

The 8-tier pick-value ladder forces a binary call at every step: a player is
"worth 2 firsts" or "worth 1 first", never between. Testers hit players they
value at "1.5 firsts" — tweeners — and either over-slot them (inflating the
tier) or skip them (leaving them unplaced, and after FB-161, demoted if passed
over on an explicit save). The walk offers no way to say "high end of the
lower tier / low end of the upper tier."

Worth noting before building anything: the backend already expresses
in-between values — `apply_tiers` spreads a tier's players linearly across its
Elo band in submitted order, and Quick Rank orders within a tier. The gap is
**capture**, not representation.

## Options considered

### A — half-tier slots
Insert explicit half-steps in the walk ("between 2 1sts and 1 1st"), mapping
to the Elo midpoint between adjacent band edges.
- ✅ Most direct expression of the tester's mental model.
- ❌ Walk grows from 8 steps to up to 15 — Quick Set's whole value is speed.
- ❌ Half-tiers aren't in the cross-client tier enum: every band mirror
  (mobile/web/extension/og), badge map, and invariant doc would need a
  taxonomy change, or the halves stay label-less and confuse the Tiers board.
- ❌ Violates the "tier labels ARE pick terms" invariant (what is "1.5 1sts"
  on a badge?).

### B — drag-between placement
Make the tier grid a drag surface where a chip can be dropped on the boundary
between tiers.
- ✅ Spatially intuitive.
- ❌ Rebuilds Quick Set's core interaction (tap chips) into a drag board —
  that surface already exists (TiersScreen). Quick Set exists precisely to be
  the no-drag fast path; duplicating drag here blurs the two methods.
- ❌ Drag on a 3-column wrapping grid has poor targets for "between rows".

### C — "high / low" modifier on the current step ⭐ recommended
Keep the 8 steps. Selecting a chip cycles or long-presses into an optional
modifier: plain (default) / **high** / **low**. On save, the client orders the
tier's submission high → plain → low (apply_tiers' linear band spread does the
rest: highs land at the band top, lows at the band floor — i.e. adjacent to
the neighboring tier, which IS the tweener statement). No new tier keys, no
band changes, no API changes — the modifier compiles away into submit order.
- ✅ Zero backend/contract/taxonomy change; composes with FB-161 demotion and
  Quick Rank (which can still fine-order afterward).
- ✅ Walk stays 8 steps; modifier is opt-in and ignorable.
- ✅ Honest representation: a "low 1 1st" player genuinely sits at the
  first_1 band floor, one Elo notch above the second band's ceiling.
- ❌ A "low X" is still labeled tier X on every board (acceptable: that's
  what the ladder means; the ORDER carries the nuance).
- ❌ Within-band nuance is coarser than a true half-tier (bounded by band
  width) — judged sufficient for the reported need.

## Recommendation

**Option C.** Ship as a small Quick Set enhancement: chip long-press (or a
second tap on the selected chip) toggles plain → high → low → plain, rendered
as a tiny `▲`/`▼` glyph beside the check; `onSave` orders ids
high → plain → low within the tier before posting. Suggested flag:
`rankings.quickset_tweener`. Estimated size: S (one screen + ordering logic +
Maestro case). Revisit A only if real usage shows band-floor/ceiling
placement isn't enough.

## Explicitly out of scope

Any change to the tier enum, tier_config bands, `/api/tiers/save` contract,
or the Tiers drag board. **Do not build from this PRD without operator
green-light.**
