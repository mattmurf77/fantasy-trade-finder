# Feedback Batch 3 — Enhancement Implementation Plan

*Detailed plan for the polish/enhancement items (50, 53, 54, 56, 58), with pros/cons, trade-offs, and full-codebase impact. Grounded in a three-client surface audit (mobile + web + extension + backend), 2026-06-11.*

Companion PRDs: [prd-50](prd-50-trends-framing.md) · [prd-53](prd-53-positional-rank-display.md) · [prd-54](prd-54-value-separation.md) · [prd-56](prd-56-tiers-quick-move.md) · [prd-58](prd-58-tile-density.md). Research: [research-synthesis.md](research-synthesis.md).

---

## 0. Two findings that reshape the plan

The audit surfaced two facts that aren't obvious and drive every decision below.

### Finding 1 — There are TWO Elo↔value mappings, and only one fixes #54
- **`data_loader.py:17` — LINEAR seed mapping:** `elo = 1200 + (value/10000)·600`. This is how consensus value *seeds* starting Elo (range 1200–1800). Inverting it gives `value = (elo−1200)/600·10000`.
- **`trade_service.py:278` — EXPONENTIAL `elo_to_value`:** `value = 1000·exp(0.0050·(elo−1500))`. Elo 1790→4263, 1500→1000, 1300→368.

**Trap:** the linear inverse is the "obvious" one (it's right there in data_loader), but inverting a *linear* map of a tight Elo spread stays tight — it does **not** fix the "~1 point per rank" complaint. Only the **exponential** transform amplifies the top end into the hundreds-of-points separation competitors show. **The plan must use `elo_to_value` (exponential), not the data_loader inverse.** A subagent already mis-suggested the linear one — this is the single easiest way to build the wrong thing.

### Finding 2 — Ranking Elo is the trade engine's INPUT, not a display value
`apply_reorder` / `apply_tiers` write `_elo_overrides` → `_compute_elo` → **both** the rankings screens **and** `user_elo → elo_to_value → trade surplus math**. So:
- **Display-only changes** (show `elo_to_value` instead of raw Elo) are **safe** — they don't touch stored Elo, only its presentation. This is #53 and #54-Phase-1.
- **Changing how Elo is spread** (#54-Phase-2: wider tier bands, different `apply_reorder` interpolation, tuned `elo_value_k`) **changes trade generation too** and must be validated against the trade-engine replay harness before shipping. This coupling is the main reason Phase 2 is a separate, gated initiative.

---

## 1. The central architectural decision: who computes value + positional rank?

#53/#54-Ph1/#58 all need the same two new display inputs on the ranking screens: a **0–10k value** and a **positional rank (QB1/RB4)**. Today the core `/api/rankings` payload (`ranked_player_to_dict`, server.py:1808) returns **only `elo`, `wins`, `losses`, overall `rank`** — no value, no pos_rank, no tier.

Two ways to close that gap:

### Strategy A — Backend serves it (RECOMMENDED)
Add `value` (= `elo_to_value`), `pos_rank`, and `tier` to `ranked_player_to_dict`. Clients read the fields.

**Pros**
- **Single source of truth.** The tunable curve config (`elo_value_k/ref/base`, live in `model_config`) stays server-side; clients can't drift when it's retuned.
- **Consistency by construction** across mobile, web, extension — and it matches what the codebase **already does**: `/api/extension/rankings` already serves `tier`+`pos_rank`, and the trends endpoints already serve `pos_rank` via `trends_service._pos_rank_map`. This is the established pattern, not a new one.
- Positional-rank logic already exists (`trends_service._pos_rank_map`, trends_service.py:71) — reuse it.
- Future server-side ranking features (confidence ranges, market value) slot in without re-touching every client.

**Cons / trade-offs**
- Backend change + redeploy (can't ship client-only).
- `/api/rankings` can return ~700 players; adding 2–3 fields/row is a modest payload bump — verify p95 latency/size (likely negligible; it's already serializing a dict/row).
- All clients still need their own display updates regardless.

### Strategy B — Each client computes it
Port the exponential formula + compute pos_rank locally in mobile (TS) and web (JS).

**Pros:** ship client-only, no backend deploy.
**Cons:** formula duplicated in two languages; **silent drift** when `elo_value_*` is tuned in `model_config` (clients hardcode it); violates the cross-client-invariants discipline; re-implements logic the backend already has. **Not recommended.**

> **Decision: Strategy A.** It's the lower-long-term-cost path, matches existing architecture, and keeps the tunable curve authoritative. The one-time backend change is small (one serializer + reuse of an existing pos_rank helper).

---

## 2. Per-item plan, scope, pros/cons

### #53 — Positional rank prominent (+ value secondary)
*Effort: small–medium · Risk: low (display-only) · Depends on: §1 Strategy A*

**Blast radius**
| Layer | Files | Change |
|---|---|---|
| Backend | `server.py:1808` (`ranked_player_to_dict`); reuse `trends_service.py:71` (`_pos_rank_map`) | add `value`, `pos_rank`, `tier` to the rankings payload |
| Mobile | `screens/ManualRanksScreen.tsx` (row render), `shared/types.ts` (RankedPlayer +fields), optionally `components/PlayerCard.tsx`/`TierBadge.tsx` (TierBadge already accepts `posRank`) | show QB1/RB4 prominent, value secondary |
| Web | `js/app.js:1960` (rankings popup), `:2038` (rankings table) | same |
| Extension | none — already shows `tier · pos_rank` | (optionally align value scale) |
| Docs | `data-dictionary.md` (payload), `api-reference.md` (`/api/rankings`), `cross-client-invariants.md` (value-scale convention) | keep in sync |

**Pros:** matches universal competitor convention; pure presentation; positional rank already computed server-side and already rendered on mobile Trends (`TrendsScreen.tsx:272`) + the extension, so we're extending a proven pattern, not inventing one.
**Cons / trade-offs:** introduces a **new user-facing number** (0–10k value) that must read identically everywhere → reinforces Strategy A. Mild risk of confusion with `player.html`'s existing "consensus value" (that's *market* value; this is the user's *personal* value) — label them distinctly ("Your value" vs "Market value").

### #54 — Value separation
*Phase 1: small, low-risk (same change as #53's value field). Phase 2: medium–large, HIGH-risk (trade-engine-coupled).*

**Phase 1 (display on exponential 0–10k + tiers):** identical blast radius to #53 (it's the same `value` field + tier banding). Likely resolves the surface complaint. **Ship with #53.**

**Phase 2 (actually widen the underlying separation) — only if Phase 1 isn't enough:**
| Lever | File | Risk |
|---|---|---|
| Linear reorder spread (~1 Elo/rank) | `ranking_service.py:912-920` (`apply_reorder`) | **Feeds trade engine** — replay-validate |
| Linear in-tier spread | `ranking_service.py:888-889` (`apply_tiers`) | same |
| Tier band widths (elite [1720,1790]=70 wide → stuffed tier compresses) | `tier_config.json` | **Cross-client** (served via `/api/tier-config`; mobile reads it, web duplicates it) |
| Curve steepness | `model_config` `elo_value_k` / `ktc_k` family (backlog #40) | changes every value + every trade |
| Confidence ranges for under-sampled players (top20 #16) | `ranking_service` + all value displays | larger feature |

**Phase 2 pros:** addresses the *real* compression (the user's own "stuffed elite tier" hypothesis is correct — `apply_tiers` linearly spreads N elite players across a 70-Elo band, so 20 elites sit ~3.7 Elo apart).
**Phase 2 cons / trade-offs:** every lever here also moves **trade generation** (Finding 2). Requires offline replay (precision@5 vs recorded likes) before ship; has A/B implications; risks regressing the trade engine you just stabilized. Recommend the **least-coupled lever first** — a UX nudge ("your elite tier has 20 players; tighten it") or **wider/auto-sized tier bands** — before touching `apply_reorder` or the curve.

> **Operator decision needed:** ship Phase 1 only and measure, or commit to Phase 2's model work? My recommendation: **Phase 1 now; Phase 2 only if the complaint persists, and even then lead with tier-band/UX levers, not the trade-coupled Elo math.**

### #50 — Trends framing
*Effort: small · Risk: very low (presentational; data already exists)*

**Blast radius:** Mobile `screens/TrendsScreen.tsx` (title→"Your Trends", ≤2-sentence subhead, self-describing section headers, instructive empty state). Web parity optional (`js/app.js:5534-5795`, `index.html:449-516`). **Backend: none** — the audit confirms `user_elo/community_elo/gap/user_rank/comparison_rank/user_pos_rank/comparison_pos_rank` are already in the trends payloads.
**Pros:** cheapest high-impact clarity win; zero data risk. **Cons:** none material. Web parity is the only optional scope creep.

### #56 — Tiers quick-move (tap-a-tier bulk)
*Effort: medium · Risk: medium (adjacent to the just-fixed drag gesture)*

**Blast radius:** **Mobile only** — `screens/TiersScreen.tsx` (select-mode action bar → tier-target buttons + bulk-move handler + scroll-into-view/flash feedback), maybe `components/TierBin.tsx`. **Backend: none** — reuses `apply_tiers`/`/api/tiers/save`/`clearedPids`; a bulk move is just a bucket reassignment persisted on Save.
**Pros:** validated mobile pattern (multi-select→move-to-target), builds the user's exact ask, no API change. **Cons / trade-offs:** sits next to the drag gesture (ids 16/27/29/32/43) and the #57 scroll tuning — keep the new path **additive** (new buttons + handler), don't refactor existing select/drag code. The "follow-the-move" feedback is the part that fixes the actual complaint (#56 is half "add buttons," half "I can't see where they went").

### #58 — Tile density
*Effort: small–medium · Risk: low · **BLOCKED on operator screenshots***

**Blast radius:** Mobile `components/TierBin.tsx`, `components/PlayerCard.tsx`, `screens/TiersScreen.tsx`. Web parity optional (`positional-tiers.html`).
**Pros:** compact rows = more players/screen, matches competitor density. **Cons / trade-offs:** 44pt touch-target floor (can't shrink below it; use `hitSlop` if visual < 44pt); must sequence **after** #53/#54 so the row is reflowed around its final contents (value + pos_rank), not the current raw-Elo row. **Blocked** until the operator shares the reference-app screenshots.

---

## 3. Cross-client-invariant impact (the part that bites)

Introducing a user-facing **0–10k value** creates a new invariant: it must read identically on mobile, web, and extension. Current state of shared values:
- **Tier bands:** source of truth `tier_config.json`, served via `/api/tier-config`. **Mobile** reads it (`utils/tierBands.ts`). **Web duplicates** the thresholds in `js/app.js:_eloToTierLabel` (2011-2013) and `positional-tiers.html` CSS — *not* fetched. **Extension** gets tier pre-computed from the backend.
- **Tier colors:** mobile centralizes in `theme/colors.ts`; web hardcodes in `positional-tiers.html`; extension hardcodes class names. Three copies.

**Implication:** Strategy A (server-computed value/tier/pos_rank) sidesteps adding a *fourth* place to duplicate the value formula. But the existing tier-threshold duplication in web is pre-existing debt this work will brush against — worth a small follow-up to make web fetch `/api/tier-config` like mobile does. `docs/cross-client-invariants.md` must gain a "player value display (0–10k, server-computed)" row.

---

## 4. Recommended sequencing

1. **§1 backend change** — add `value`+`pos_rank`+`tier` to `/api/rankings` (one serializer; reuse `_pos_rank_map`). Unblocks #53 + #54-Ph1. Update data-dictionary/api-reference.
2. **#53 + #54-Phase-1 together** (one "player value display" change) — mobile ManualRanks first (the filed screen), then web rankings table, then the shared row helper. Ship behind a small flag if you want a clean A/B against raw-Elo.
3. **#50** in parallel (independent, mobile-only, no backend) — cheap clarity win.
4. **#56** — additive tap-a-tier + follow-the-move feedback.
5. **#58** — once screenshots arrive; reflow the now-final row to compact density.
6. **#54-Phase-2** — only on operator go; offline-replay-gated; lead with tier-band/UX levers.

Items 2–5 are independent enough to be separate subagent code tasks (disjoint files mostly; #53/#54-Ph1 share the value field so do them as one). #54-Ph2 is its own initiative.

## 5. Effort / risk at a glance

| Item | Effort | Risk | Backend? | Cross-client? | Blocked? |
|---|---|---|---|---|---|
| §1 API value+pos_rank | S | Low | **Yes** | Yes (new invariant) | No |
| #53 pos rank display | S–M | Low | via §1 | Yes | No |
| #54 Ph1 (0–10k display) | S | Low | via §1 | Yes | No |
| #54 Ph2 (separation math) | M–L | **High (trade-coupled)** | Yes | Yes | Operator decision |
| #50 trends framing | S | Very low | No | Optional | No |
| #56 tier quick-move | M | Medium | No | No | No |
| #58 tile density | S–M | Low | No | Optional | **Screenshots** |

## 6. Coordination with in-flight work
A launch-QA pass and a `staged-work/` convention are active in parallel, and `CRON_SECRET` is now a launch-gate (guards the whole admin surface; must be set in Render). These enhancements are **post-launch polish** — none should block launch. The one cross-stream touchpoint: the §1 `/api/rankings` payload change should be folded into the launch-QA review of API shape rather than landed blind. Keep all batch-3 code on the same `trade-engine-v2` branch + PR-gated as before.

## 7. Open decisions for the operator
1. **§1 Strategy A (server-computed value/rank)** — approve the small backend change? (Strongly recommended over client-side ports.)
2. **#54 Phase 2** — ship Phase 1 (display) only and measure, or commit to the separation-math work (offline-replay-gated)?
3. **#58 screenshots** — share the reference-app examples so density can be specced.
4. **Web parity** — do #50/#53/#58 web updates ship with mobile, or mobile-first then fast-follow web?
