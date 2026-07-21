# Ranking-surface spec — picks in Quick Set + Quick Rank (#158/#170/#171)

**Status:** MOCKUP for operator review. The UI is NOT built this round — this
spec + `mockups/picks-quickrank/index.html` capture the model so the operator
can sign off before the Quick Rank pick-slot UI is implemented.

Resolved with the operator 2026-07-18/20 alongside the owned-picks build.

---

## The two-level model

Ranking picks reuses the existing two-flow ladder — nothing new to learn:

| Flow | Granularity | What picks are here |
|---|---|---|
| **Quick Set** | **Coarse** — players dropped into broad, pick-denominated **tiers** (4 firsts → 3 firsts → 2 firsts → 1st → 2nd → 3rd → 4th → waivers, the `colors.ts` tier ladder). | Picks are **ANCHOR rungs**, not tiered assets. "A 1st" and "a 2nd" are the fixed reference rungs a player is dropped *next to* — they define the tier bands, they aren't sorted into them. |
| **Quick Rank** | **Fine** — within one tier, order the players **and** that round's Early/Mid/Late pick slots into an exact sequence. | Picks are **rankable rows**, interleaved among the players in that tier. |

### The load-bearing rule

**Early / Mid / Late is intra-tier ORDERING, never its own tier.**

- All three 1st slots (Early 1st, Mid 1st, Late 1st) fall inside the **single
  "1st" tier band** — they share the round-1 seeds (`GENERIC_PICK_SEEDS[(1, *)]`
  = 1720 / 1650 / 1580, all in the 1st band).
- All three 2nd slots fall inside the **"2nd" tier band** (seeds 1520 / 1460 /
  1400).
- So a user never sees "Early 1st tier" vs "Late 1st tier". They see one **1st**
  tier, and inside it they order Early/Mid/Late 1st against the players they'd
  trade a 1st for.

This matches the seeds and matches how owned picks are priced in suggestions +
the calculator: every owned 1st is valued at the `(1, "Mid")` seed at launch
(operator decision), and Early/Mid/Late is a *within-round* ordering nuance —
exactly what Quick Rank captures.

---

## Quick Set (coarse) — picks as anchors

- The tier bins are already labeled in pick terms (the #117 ladder). Picks are
  the **rungs that name the bins**, not draggable chips.
- No change to Quick Set is required for this item beyond keeping the pick rungs
  legible as anchors. (Building it out is future work, gated behind operator
  review of this spec.)

## Quick Rank (fine) — pick slots interleaved among players

The mockup (`mockups/picks-quickrank/index.html`, Chalkline dark, ~390px) shows
the **"1st" tier** with the Early/Mid/Late 1st **pick slots interleaved among
players** in a single ordered list:

```
1  WR  Malik Nabers        6,940
2  1st Early 1st (slot)    6,720   ← pick slot, ice-outlined
3  RB  Jahmyr Gibbs        6,480
4  1st Mid 1st (slot)      6,290   ← pick slot
5  TE  Brock Bowers        6,050
6  QB  Jayden Daniels      5,880
7  1st Late 1st (slot)     5,610   ← pick slot
8  WR  Garrett Wilson      5,470
```

Design notes captured for the build:

- **Pick rows are visually distinct but same-list:** ice-outlined position glyph
  ("1st") + a "Pick slot" badge, so a pick reads as an asset, not a section
  header. They drag/reorder exactly like player rows.
- **One list per tier.** The Early/Mid/Late slots for the tier's round sit in
  the list; deeper rounds' slots appear in their own tier's Quick Rank pass.
- **Values shown are consensus pool values** (the `pool_value` scale) so a
  player and a pick slot are directly comparable in the same column.
- **Save writes the within-tier order** (reuses the Quick Rank reorder path —
  clicked/dragged order + unclicked appended), with the pick slots as ordinary
  rows in the permutation.

---

## Boundary / what this spec does NOT decide

- **Owned-pick Early/Mid/Late slotting by standings** is future work (gated on
  #169 league outlook). Until then every *owned* pick is the flat `(round,
  "Mid")` value in suggestions + the calculator; the Early/Mid/Late **slots**
  here are the *generic* rankable rungs (they already exist in
  `GENERIC_PICK_SEEDS`).
- **Engine weighting** of a ranked pick is the trade-logic thread's; this
  surface only captures the user's ordering.
- The pick-value ladder itself is owned by `backend/pick_values.py`
  (`GENERIC_PICK_SEEDS` + `pick_pool_value`) — the same single source #157 uses,
  so the ranking surface and the calculator/suggestions can't drift.
