# HLD delta — Multi-format rank sets (feedback #155)

> Delta vs `docs/architecture.md`. **Plan only, no code.** Read with the PRD,
> `format-mapping-matrix.md`, and `lld-delta.md` in this folder.

---

## 1. What changes at the architecture level

Three things, all *extensions* of existing mechanisms — no new subsystem:

1. **The scoring-format enum widens from 2 → 5** (`format-mapping-matrix.md`
   §6). This is a data/contract change threaded through `data_loader`,
   `database`, `server`, and all clients. `1qb_ppr`/`sf_tep` are unchanged.
2. **Cross-format propagation is promoted from a manual button to an automatic,
   preference-driven behavior.** The engine (`RankingService.apply_value_map`,
   #124) is unchanged in spirit; what's new is *when* it fires (first entry into
   a format, or a Settings toggle) and a small preference/override store.
3. **Per-format service construction becomes lazy.** Today `session_init` builds
   one RankingService + TradeService per format eagerly; with 5 formats that's
   the dominant new cost, so we defer construction to first use.

## 2. Data-flow delta

### 2a. Seeding (process-global, at boot / TTL refresh)

`data_loader` today produces a `(elo_map, value_map, pos_map)` per format from
the DP CSV blended with KTC. It expands to produce **5** format maps from the
**same** cached DP CSV + KTC page (one fetch each; the KTC page already carries
every TE-premium variant). Each format's derivation (which DP column, which KTC
variant, which position-uplift multiplier) is table-driven per
`format-mapping-matrix.md` §3. Both uplift knobs neutral ⇒ pure-DP, byte-for-
byte, exactly like today's `tep_te_uplift`/`ktc_blend_weight` contract.

```
DP CSV (cached) ─┐
                 ├─▶ per-format derive ×5 ─▶ g_universal_by_format[fmt]  (pool + seeds)
KTC page (cached)┘        (col + variant + uplift, table-driven)
```

### 2b. Per-session (lazy)

```
session_init
  └─ build service for: league-default format  (+ any format with a saved board)
       other formats' services  ──lazy──▶ built on first switch/entry, cached in sess["services"]
```

### 2c. First entry into a new format (the new control flow)

```
client switches selector to format B (no saved board for B)
  └─ backend resolves "first entry?" via user_format_prefs(user, B).first_entered_at IS NULL
       ├─ align_all_formats ON  → auto-run apply_value_map(source→B); persist; no prompt
       └─ align_all_formats OFF → return a "prompt_align" signal to the client
             client shows align sheet
               ├─ Align  → POST copy/align (source→B) + set align_all_formats=1
               └─ Fresh  → mark first_entered_at, build independently
```

The align/reseed itself is the **existing** `/api/tiers/copy-from-format`
generalized to any source→target pair among the 5 (LLD §3). "Primary/source
board" = the format the user has most invested (heuristic in LLD §3.2).

## 3. Storage delta (summary; columns in LLD §2)

- **Reuse, expand:** `users.tier_overrides`, `users.tiers_saved`,
  `users.unlocked_formats`, `users.anchor_scale` are already **format-keyed JSON
  dicts** — they simply carry up to 5 keys instead of 2. No shape change, no
  migration; `save_tier_overrides(..., scoring_format=fmt)` already writes
  arbitrary format keys.
- **New — one column:** `users.align_all_formats INTEGER` (the global
  preference; default NULL/0 = off).
- **New — one table:** `user_format_prefs (user_id, scoring_format, …)` for
  per-(user, format) first-entry tracking, align provenance, and per-user
  multiplier overrides. Keyed on the working `user_id` (acct_/sleeper).

Rationale for keeping tier STATE in the existing blobs (not the new table): the
raw-Elo override model is a load-bearing invariant (`cross-client-invariants.md`
→ "Tier band Elo cutoffs" — overrides re-bucket on read when bands change).
Moving it would be a large, risky refactor with no benefit. The new table holds
only the genuinely-new *preference/mapping* concepts.

## 4. Interaction with existing mechanisms

- **`tier_overrides` (raw Elo):** unchanged as the authoritative per-format tier
  state. Auto-align writes into `tier_overrides[B]` via `apply_value_map`, same
  as the manual #124 copy does today.
- **`useLeagueFormatDefault` / `useScoringFormat`:** the league-default applier
  and explicit-toggle hook keep their contract; they just operate over 5 keys.
  The selector on Tiers/Trios becomes a 5-way choice (LLD §4).
- **Progress gating / `unlocked_formats`:** unchanged mechanism; a format
  unlocks when its per-position rank thresholds are met, now across 5 keys.
- **Trade generation / `member_rankings`:** unchanged; publishes the active
  format's board. Auto-align republishes to `member_rankings` for the new
  format, exactly as the #124 copy route already does.

## 5. Phasing

- **Phase 1:** 5 formats seeded + enum widened + lazy services + auto-align on
  first entry + alignment toggle in Settings + league detection over 5. Editable
  mappings read/write with the **operator-global** multipliers.
- **Phase 2:** per-user editable multiplier **apply** path in `apply_value_map`
  (value-space reshape; LLD §3.3) + the mapping-editor UI wired to it.

## 6. Docs to update when this is built

`cross-client-invariants.md` (Scoring format strings → 5 keys; note the enum
touchpoints), `data-dictionary.md` (new table + `users.align_all_formats`),
`api-reference.md` (align/prefs routes), `config-reference.md` (new
`qb_2qb_uplift`/`tepp_te_uplift` model_config keys), `glossary.md` (new format
terms). Consider an ADR for "rank-set mapping = order-preserving reseed onto the
target consensus curve" if not already implied by the #124 history.
