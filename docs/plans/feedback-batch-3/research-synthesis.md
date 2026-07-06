# Research synthesis — batch-3 enhancement/polish items

*Two parallel subagents, 2026-06-11: (A) mined our competitor teardowns + backlog + top20; (B) verified external UX/data-viz best practices. Condensed below with citations. Full agent reports are in the session transcript.*

## The single biggest finding (cross-cuts #53, #54, #58)

**Display player value on the 0–10,000 scale (via the existing `elo_to_value`), not raw Elo — and pair positional rank + tier with it.** This one change addresses three complaints at the display layer:
- Every competitor (KTC, FantasyCalc, Dynasty Daddy, DynastyGM `6,116 (QB2)`, DynastyDealer Josh Allen `9,927`) uses a ~0–10k value AND shows positional rank, almost always WITH a tier.
- Dynasty values are deliberately **exponential** — a value-5000 player is ~26% of a value-9999 player, so ~4 of them ≈ 1 elite. A ~1-point-per-rank linear Elo spread (the #54 complaint) destroys exactly this separation. `elo_to_value` is already exponential, so displaying it restores the cliff.
- Perceptual encoding (Cleveland–McGill): use **position-on-scale and length**, not color alone; when levels exceed what a channel resolves, **aggregate into tiers**. → tiers + bar length, color as secondary.

Sources: KTC rankings (positional rank + tier + value rows), DynastyProcess exponential curve, NN/g + UC Davis DataLab perceptual guidance, competitor-top20 `14`/`16`/`17`.

## Per-item

**#50 Trends framing.** Competitors carry "yours-ness" via possessive titles ("Your Leagues/Picks" — DynastyGM) + a personal anchor number, and HARD-separate personal vs market (DynastyDealer Portfolio tab vs Market Hub). top20 `14` has the directly-transferable **"By Market / By You" basis toggle**; `09` (community-diff) supplies per-row "You: WR12 · Market: WR24" badges. Best practice: a one-line subhead naming subject+metric+timeframe; empty state = copy + visual + CTA. Backlog `#33` = movers scoped to rostered players.

**#53 Value display.** Strong precedent: positional rank prominent, value secondary, KEEP BOTH. DynastyGM row `Name — RB5, #22 — 6,261`; `(NR)` for unranked. top20 `14` LLD already serializes `pos_rank`. Pure presentation change.

**#54 Value separation.** Three levers: (1) display on 0–10k `elo_to_value` (cheap, fixes it at display); (2) tune curve steepness via the `ktc_k` family (backlog `#40`, optionally league-size-aware per DTC); (3) tiers + color for perceptual separation. CAUTION (top20 `16`): low-matchup Elo separation is partly noise — confidence ranges may be more honest than fake-precise gaps; don't manufacture separation the data doesn't support.

**#56 Tier bulk move.** **Thin competitor coverage** — no captured app has a user-editable tier board. But the "multi-select → one-tap apply" grammar IS validated (DynastyGM bulk-delete, DynastyDealer Mass-Send "apply to all"). External: tier-list bulk best practice = multi-select + "move to tier" (TierCraft), NOT drag (drag is for single moves, fragile on touch). Our screen already has multiselect + up/down arrows; the ask = add tier-target buttons. Build tap-to-tier, product-led.

**#58 Tile density.** **No pixel spec exists** in docs. But competitors run dense one-line rows: DynastyGM `headshot · name · team chip · age(1dp) · value · pos-rank · R-tag`; DynastyDealer adds a thin trend-colored edge bar; both use **collapsible position groups**. External: 44pt min touch target (Apple HIG), ≥8px spacing, rows-not-cards for scannable lists (NN/g), most-important attribute top-left, ~3–4 fields/row. Needs operator's reference screenshots to finalize exact sizing.
