# Trios → Tier Calibration — Plan (2026-07-08, rev. 2 after pressure test)

> **2026-07-10 addendum:** the **Pick Anchor wizard** (`POST /api/anchor/save` + mobile `PickAnchorScreen`) shipped as an *explicit-statement sibling* of Lever B: instead of inferring a band from a bracketing trio, the user states a player's worth directly in draft capital ("worth 2 firsts") and the Elo is pinned as an authoritative override (apply_tiers semantics, no cap). Trio-driven Lever B (ordinal anchor placement inside trios) remains design-only; if it lands, wizard-pinned players are overrides and must be treated as read-only reference points, per "Overrides win."

*Reworking the Trios ranking loop so its outcomes drive **meaningful value change** and land players into the tiers we've defined — instead of small, local Elo nudges. **This is a personal-use calibration tool** (single operator ranking their own board), which lets us favour decisive, operator-tunable mechanics over anti-noise machinery built for a public audience. Grounded in `backend/ranking_service.py`, `backend/tier_config.json`, `backend/trade_service.py`. Design only, no code.*

---

## Pressure-test findings (what changed in rev. 2)

Rev. 1 was rewritten against the actual engine. Three load-bearing claims were wrong or imprecise; two new footguns surfaced:

- **❌ "Flat Elo asymptotes inside the seed band, so trios can't cross boundaries."** Wrong mechanism. Elo asymptotes to whatever a player's *revealed win-rate against opponents faced* implies — not the seed. The real cause is **matchup selection**: `_algorithmic_trio` picks the *"tightest uncompared trio by Elo"* — 3 adjacent players with minimal spread ([ranking_service.py](../../backend/ranking_service.py), `_algorithmic_trio`). You are only ever asked to compare near-equals, so the **cross-tier comparison that would move a player across a band is never generated.** The per-trio Elo delta is also small *because* the players are near-equal (E≈0.5 → update ≈ `elo_k/2` ≈ 16), not because of any band ceiling.
- **❌ "A tier is ~120 Elo wide; each trio update is ~16 max."** Bands are ~70–90 Elo wide with ~40-Elo gaps between them ([tier_config.json](../../backend/tier_config.json)). And `elo_k=32`, so a single pairwise update is *up to* 32 (a big upset) — ~16 is the *typical* value only because the selector picks near-equals.
- **❌ "Value parity: earning a player into a tier ≈ dragging them there, within a small tolerance."** Not achievable, and not even the right target. With `elo_value_k=0.005`, an 80-Elo band spans `exp(0.005·80) ≈ 1.49×` in value — **a ~50% value range *inside a single tier***. "Same tier" is nowhere near "same value." Corollary: a within-band Elo move is already a large value move, so the premise "trios = minor value tweaks" is only true because trios move *slowly and locally*, not because within-band moves are inherently small.
- **⚠️ Naming collision (footgun).** There are **two unrelated "tier" concepts** in the code: (1) `tier_size=24` — the top-N-by-seed *matchmaking pool* (`_tiered_pool`); (2) the `tier_config.json` **value bands** elite/starter/solid/depth/bench. This plan only touches behaviour *relative to the value bands*; it must not be conflated with the top-24 pool window.
- **⚠️ Anchor overshoot (footgun).** Rev. 1's "compare against a pinned anchor to settle into its band" is mathematically broken: if you consistently beat a fixed 1520 anchor, your Elo climbs to ~anchor+350 (until E≈1) — you blow *past* the band into elite, you don't settle in it. Elo dynamics against a single anchor can't place you *in* a band. Rev. 2 fixes this (below).

**Verdict:** the strategic thesis survives — *tiers = coarse manual override; trios = the engine that earns tier-quality placement*. But the mechanics needed a real rewrite, and one honest reframing: the goal is less "cross boundaries" and more **"generate the boundary/cross-tier comparisons the selector currently refuses to, and let a decisive result place value where it belongs — within *or* across a band."**

---

## Corrected diagnosis (one sentence)

The trio selector is a **local sorter** ("tightest uncompared trio by Elo"): it refines the order of players who are *already near each other*, so it never asks "is this depth guy actually a starter?" — the only question that moves value across the coarse, ~50%-wide value bands.

---

## Design principles

1. **Ask boundary questions.** The high-value comparison is cross-tier, not intra-tier. The loop should spend interactions there.
2. **A trio result should be legible as a value/tier consequence** ("↑ Bijan → Starter", or "↑ Bijan +18%"), not an invisible drift.
3. **Manual tier placements are authoritative.** Trios never silently overwrite an override; they can *use* tiered players as fixed reference points and, at most, *suggest* a change.
4. **Single-user → decisive over cautious.** No public audience to protect from noise, so favour larger, operator-tunable moves and explicit snapping; skip growth metrics, reconcile-queue UI ceremony, and defensive anti-abuse logic.

---

## Mechanics (rewritten)

### Lever A — Flip the selector from "tightest" to "boundary-probing" *(primary fix, low risk)*
Invert the core heuristic. Instead of the tightest-Elo trio, **prefer trios whose members straddle a value-band edge**: one player just below a band's `lo`, one just above, plus a tie-breaker — chosen using `tier_for_elo` on current Elo ([ranking_service.py](../../backend/ranking_service.py), `tier_for_elo`). Each such trio is a direct vote on a boundary crossing. Keep an "uncompared/fresh" penalty so we don't re-ask settled boundaries.
- This is the single change that fixes the root cause. It's a swap of the selection objective, not new value math — **safe and reversible via config** (`trio_boundary_weight`, default new-behaviour for this personal build; 0 = legacy).
- Blend, don't replace: a fraction of trios can remain intra-tier ordering (the current behaviour is genuinely useful for fine ordering within a band, which — per the 50%-value finding — matters). Tune the split with one scalar.

### Lever B — Anchor probes done right: **ordinal placement, not Elo convergence** *(the trios→band bridge)*
Rev. 1's Elo-convergence-against-an-anchor is dropped (it overshoots). Replace with a **direct ordinal read**:
- Occasionally inject a trio of **[candidate, low-anchor, high-anchor]** where the anchors are the seed-median players of two *adjacent value bands* (e.g. a canonical Solid and a canonical Starter). Anchors are chosen from seed Elo, **read-only**, and are *never written into `_elo_overrides`* (that dict is the user's tier board — polluting it would make phantom players appear in Tiers).
- The user's ranking is a **bracketing statement**: candidate above the Starter-anchor and below the Elite-anchor ⇒ "high Starter." Convert that *ordinally* into a target: place the candidate's Elo at the implied position **between the two anchors' Elos** (interpolated by where they slotted them), i.e. a **soft, trio-earned tier assignment**. This lands them *in* the band by construction — no dynamics, no overshoot.
- If the user ranks the candidate above *both* anchors, that's itself signal → next trio brackets them one tier higher (dynamic re-selection). This is how a genuinely underrated player climbs tiers in a few decisive trios instead of dozens of local nudges.
- **This is effectively the "soft-snap" that rev. 1 called optional — the pressure test shows it's the *core* of any "land into a defined band" mechanism.** Elo dynamics alone cannot place into a band; a direct assignment must.

### Lever C — Bigger, consistency-scaled K for the *non-anchored* boundary trios *(optional)*
For Lever-A boundary trios that aren't anchored, `elo_k=32` still moves value slowly. Since this is single-user, simply **raise the effective K on boundary-straddling trios** (e.g. 1.5–2×) and/or add mild momentum (consistent same-direction outcomes scale K up, bounded). Cheaper than Lever B, less precise. Gate behind `trio_boundary_k_mult`. Only add if A+B alone feel sluggish in practice.

---

## Reconciling with tier overrides & value parity

- **Overrides win.** Tiered players keep pinning their own Elo and are skipped by swipe updates ([ranking_service.py](../../backend/ranking_service.py), `_compute_elo`); trios only ever *read* them (a tiered Elite is a perfect high-anchor). A pool player, having no override, can be freely (soft-)placed by Lever B; an already-tiered player is at most flagged "your rankings suggest a different tier" — apply-on-tap, never automatic. For a personal tool this can be a one-line note on the Tiers screen, not a queue system.
- **Value parity, corrected target.** Don't chase "trio-earned Elo == tier-dragged Elo" (bands are ~50% value-wide; that's a false precision). The real acceptance criterion: **(1) trio-earned placement lands in the *correct band* (tier match), and (2) within-band position is monotonic in the user's expressed margin** (ranked comfortably above the low-anchor ⇒ upper half of the band). Validate with a seed-data simulation, not a tight numeric tolerance.

---

## Backend touch points
- `_algorithmic_trio` / smart selector — new **boundary-probing objective** (Lever A) + optional **anchor injection** (Lever B). New helpers: `_band_edges(position, fmt)`, `_band_anchors(position, fmt)` (seed-median per band, read-only), `_ordinal_place(candidate, low_anchor, high_anchor, ranking)` → soft override for pool players only.
- `_compute_elo` — unchanged unless Lever C (boundary-K multiplier / momentum), kept in the swipe-replay path so it survives restart.
- Expose a **tier-confidence** read (how stable each player's band has been over recent trios) via `get_progress`, so the loop stops re-asking settled boundaries and the UI can show "tiers dialed in".
- **Config** (`model_config`, document in `config-reference.md`): `trio_boundary_weight`, `trio_anchor_rate`, `trio_boundary_k_mult` (Lever C), `tier_confidence_window`. All operator-tunable — the whole point of a personal build.
- **Cross-client invariant:** value bands stay single-sourced in `tier_config.json` (`/api/tier-config`); anchors derive from it. No client-visible contract change if anchors stay backend-internal.

## Mobile touch points (minimal, personal build)
- `RankScreen`: after submit, show the **tier/value consequence** ("↑ Player → Starter" or "↑ +18%"). This is the change that makes trios feel as consequential as tiers.
- Rank progress reframed from raw "0/10" to **"tiers dialed in: N/24"** per position (from tier-confidence).
- `TiersScreen`: a lightweight **"suggested move"** inline note when trios disagree with a manual placement — tap to apply. No queue, no batch UI.

---

## Scope
- **v1:** Lever A (selector flip) + Lever B (ordinal anchor placement for pool players) + tier-confidence-driven selection + the consequence toast + the seed-data validation sim. Backend-led; mobile changes are additive.
- **Defer:** Lever C (only if A+B feel slow), the Tiers suggested-move note, SF/TEP anchor tuning beyond what `tier_config.json` encodes.
- **Out:** changing the value bands, `elo_to_value`, the top-24 matchmaking window, or finder/calculator math. This changes *which comparisons we ask and how a decisive result is placed* — not what value means.

## Risks & mitigations
- **Overshoot / thrash at boundaries** (Lever C esp.): require consistency before crossing; use the ~40-Elo inter-band gaps as hysteresis buffers; cap trio-earned placement at **Starter** in v1 (a manual drag is required to reach Elite — protects the top from a single noisy trio). Single-user, so this is a preference, not a safety requirement.
- **Anchor drift on seed refresh** → recompute anchors with seeds; treat as a normal small re-seed, not a reset.
- **Selector flip feels random** (boundary trios pair "unrelated" players): keep a chunk of intra-tier ordering trios in the mix (the 50%-value-width finding says within-band ordering genuinely matters), tuned by one scalar.
- **Convergence speed vs. fatigue:** ordinal anchor placement is decisive by design; measure interactions-to-confidence on seed data and tune `trio_anchor_rate`.

## Success metrics (personal build — keep light)
- **Boundary-decision rate:** % of trios that change a player's band (should be materially > 0, without thrash).
- **Interactions-to-confidence:** median trios to mark a position "dialed in".
- **Band correctness in sim:** synthetic user with a known target board → does the loop place players in their target bands, in the right within-band order?

## Open questions (pinned, not blocking)
1. Anchor source: seed-median per band (simple, auto) vs. a curated canonical player per band (more legible, more upkeep). Lean seed-median for v1.
2. Cap trio-earned placement at Starter (protect Elite) — keep for v1, revisit.
3. Keep the intra-tier-ordering trios (yes — the 50%-value-width finding argues they carry real value; just don't let them dominate).

*Code grounding: `ranking_service.py` (`_algorithmic_trio` = "tightest uncompared trio by Elo", `_tiered_pool` = top-24 window, `_compute_elo`, `apply_tiers`, `tier_for_elo`, `_elo_overrides`), `tier_config.json` (bands ~70–90 Elo wide, ~40 gaps), `trade_service.py` (`elo_to_value`, k=0.005 → ~1.49× value per band), on trade-engine-v2 @ 2026-07-08.*
