# Format mapping matrix — feedback #155

> Planning artifact. **No code.** Grounds the PRD/HLD/LLD in what our consensus
> data (DynastyProcess CSV + KeepTradeCut blend) can actually price, and how any
> one format's board maps into any other.

Related: #155 ("Add SF no TE"), #166/#167 (default to the league's format, esp.
SF-TEP). Reads on: `backend/data_loader.py`, `backend/ranking_service.py`
(`apply_value_map`), `docs/cross-client-invariants.md` → "Scoring format strings".

---

## 1. The two axes dynasty formats actually split on

Dynasty pricing moves on exactly two axes our sources carry:

- **QB axis** — **1QB** (start one QB) vs **Superflex/2QB** (a second QB can
  start). This is the single biggest value distortion in dynasty; QBs roughly
  double in relative value under SF.
- **TE axis** — **standard** vs **TE-Premium (TEP, +0.5 PPR on TE receptions)**.
  Boosts TE values ~15–25% relative to standard.

(PPR itself is near-universal in dynasty and is the anchor for every published
consensus set; half-/non-PPR dynasty is rare and we do not price it. So "PPR"
is a constant here, not a fifth axis.)

The 2×2 of those axes gives **four** clean, independently-sourceable curves. The
operator asked for **five**; the fifth is a genuine decision because our data
does **not** carry a fifth independent curve (see §4).

---

## 2. What each source carries (the ground truth)

**DynastyProcess CSV** (`files/values-players.csv`) carries exactly two value
columns:

| Column | Meaning |
|---|---|
| `value_1qb` | 1QB dynasty value, no TE premium |
| `value_2qb` | Superflex/2QB dynasty value, no TE premium |

DP has **no TE-premium column and no separate 2QB-vs-SF column.** Everything
beyond these two we must *derive*.

**KeepTradeCut** (`playersArray` literal, one page GET, already parsed in
`data_loader._ktc_consensus`) is richer — each player carries:

| KTC path | Meaning |
|---|---|
| `oneQBValues.value` | 1QB, standard TE |
| `oneQBValues.tep.value` | 1QB, TE-premium (+0.5) |
| `oneQBValues.tepp.value` | 1QB, TE-super-premium (+1) |
| `oneQBValues.teppp.value` | 1QB, TE-hyper-premium (+1.5) |
| `superflexValues.value` | Superflex, standard TE |
| `superflexValues.tep.value` | Superflex, TE-premium (+0.5) |
| `superflexValues.tepp.value` | Superflex, TE-super-premium |
| `superflexValues.teppp.value` | Superflex, TE-hyper-premium |

KTC gives us the **TE axis natively** (base / tep / tepp / teppp) but, like DP,
does **not** separate a must-start-2QB league from a Superflex league — KTC's
"superflex" IS its 2QB proxy.

**Consequence:** our sources cleanly price the **2×2 (four corners)** and,
via KTC's `tepp`/`teppp`, additional *TE-premium tiers* on either QB axis. They
**cannot** independently price "2QB (distinct from SF)".

---

## 3. Recommended 5 formats (operator picks the 5th)

The four corners are confident, data-native, and cover the vast majority of
dynasty leagues. Two existing enum keys map straight onto two corners with **no
rename** (critical for migration — see PRD §7).

| # | Proposed enum key | Human label | QB axis | TE axis | DP column | KTC path | TE uplift knob | Confidence |
|---|---|---|---|---|---|---|---|---|
| 1 | `1qb_ppr` *(existing)* | 1QB | 1QB | standard | `value_1qb` | `oneQBValues` | — (1.0) | **native** |
| 2 | `1qb_tep` *(new)* | 1QB TE-Premium | 1QB | TEP | `value_1qb` | `oneQBValues.tep` | `tep_te_uplift` (≈1.18) | **native (KTC), derived (DP-only)** |
| 3 | `sf` *(new — #155)* | Superflex | SF/2QB | standard | `value_2qb` | `superflexValues` | — (1.0) | **native** |
| 4 | `sf_tep` *(existing)* | Superflex TE-Premium | SF/2QB | TEP | `value_2qb` | `superflexValues.tep` | `tep_te_uplift` (≈1.18) | **native** |
| 5 | **operator decision** — see below | | | | | | | |

**The 5th — two honest options, operator picks:**

- **Option A (recommended): `2qb`** — must-start-two-QB. *Highest prevalence*
  of any remaining format, and it exercises the exact per-position-multiplier
  machinery we already need for the TE uplift (see §5). **But it is an
  approximation:** neither DP nor KTC price 2QB separately from SF, so `2qb` =
  the `sf` curve with a small **QB uplift multiplier** (`qb_2qb_uplift` ≈ 1.05,
  new knob) applied to QBs only. Honest framing: it's "SF with QBs nudged up,"
  not an independent consensus.
- **Option B: `sf_tepp`** — Superflex, TE-super-premium (TE+1). *Data-native*
  via KTC `superflexValues.tepp` (DP-only fallback = `value_2qb` × a larger TE
  multiplier, same machinery as `sf_tep`). Zero approximation, but **lower
  prevalence** than 2QB.

**Recommendation:** ship the **four corners with full confidence**; take
**Option A (`2qb`)** as the 5th for prevalence, clearly labeled in-app as an
approximation, since it reuses the position-multiplier lever that the editable
mapping needs anyway. If the operator prefers zero-approximation purity over
prevalence, switch the 5th to **Option B (`sf_tepp`)** — the rest of this design
is identical either way (only the derivation row for slot 5 changes).

### DP-only fallback (KTC down)

KTC is an unsanctioned surface and fails soft to DP-only (`data_loader`
docstring). Under DP-only we still serve all 5 by derivation from the two DP
columns:

| Format | DP-only seed derivation |
|---|---|
| `1qb_ppr` | `value_1qb` |
| `1qb_tep` | `value_1qb`, TE × `tep_te_uplift` |
| `sf` | `value_2qb` |
| `sf_tep` | `value_2qb`, TE × `tep_te_uplift` |
| `2qb` (Opt A) | `value_2qb`, QB × `qb_2qb_uplift` |
| `sf_tepp` (Opt B) | `value_2qb`, TE × `tepp_te_uplift` (larger) |

Both knobs neutral reproduce the pure-DP pipeline byte-for-byte, exactly like
the current `tep_te_uplift`/`ktc_blend_weight` contract.

---

## 4. Why not more / different formats

| Candidate | Verdict |
|---|---|
| **2QB as an independent consensus** | ✗ Not sourceable — DP `value_2qb` *is* "2QB/Superflex"; KTC folds them. Only approximable (Option A). |
| **Half-PPR / Standard scoring** | ✗ No consensus column; dynasty values are PPR-anchored. Out of scope. |
| **TEPP / TEPPP (TE+1 / +1.5)** | ~ Sourceable via KTC only; niche prevalence. `sf_tepp` is the Option-B 5th; `1qb_tepp` is a possible future 6th but not recommended now. |
| **Non-superflex 2-flex / other roster shapes** | ✗ Roster-construction nuance, not a value curve. Out of scope. |

---

## 5. The mapping matrix — there is no NxN table

The elegant result of the #124 design: **the "rank-set mapping values" are just
the 5 consensus seed curves.** Mapping format A → format B is not a hand-tuned
A↔B table; it is:

> Take the user's **rank order** per position from board A, then **deal out
> format B's own consensus seed Elos** to those ranks (rank 1 → B's highest
> seed, rank 2 → next, …). Order is the user's; magnitudes are B's consensus.

This is exactly today's `RankingService.apply_value_map` (used by
`/api/tiers/copy-from-format`), generalized from a 2-format pair to any pair
among the 5. So the "matrix" is 5 curves + one order-preserving reseed
operator — **O(5) data, not O(5²) mappings.**

| From \ To | `1qb_ppr` | `1qb_tep` | `sf` | `sf_tep` | `2qb`/`sf_tepp` |
|---|---|---|---|---|---|
| any format | — | reseed onto target curve | reseed | reseed | reseed |

Every non-diagonal cell is the **same** operation: `apply_value_map(pos,
order_from_source)` against the target service's seed curve. QBs shift most on
any cross-QB-axis hop (1QB↔SF); TEs shift most on any cross-TE-axis hop
(±TEP) — automatically, because the magnitudes come from the target curve.

### What is editable (the "default mappings" knob)

Recommended **single coherent knob: per-format, per-position value
multipliers** (default = that format's consensus). Concretely the user (or
operator) can say *"in TE-premium formats, boost my TEs by X%"* or *"in 2QB,
boost my QBs by Y%"*. This:

- reuses the exact lever we already ship globally (`tep_te_uplift`), just
  exposed per-user and per-format;
- is intuitive to explain ("how much extra are TEs worth to you here?");
- is strictly better than the alternatives:
  - *tier-boundary offsets* — ✗ fights the cross-client invariant that tier
    bands are format/position-uniform (`docs/cross-client-invariants.md` →
    "Tier band Elo cutoffs"); would desync every client's band walk.
  - *a single per-format scalar* — ✗ too coarse; can't express "TEs matter,
    QBs don't" which is the whole point of format differences.

Default multipliers per format (all 1.0 except the built-in premiums):

| Format | QB | RB | WR | TE |
|---|---|---|---|---|
| `1qb_ppr` | 1.0 | 1.0 | 1.0 | 1.0 |
| `1qb_tep` | 1.0 | 1.0 | 1.0 | `tep_te_uplift` |
| `sf` | 1.0 | 1.0 | 1.0 | 1.0 |
| `sf_tep` | 1.0 | 1.0 | 1.0 | `tep_te_uplift` |
| `2qb` (Opt A) | `qb_2qb_uplift` | 1.0 | 1.0 | 1.0 |
| `sf_tepp` (Opt B) | 1.0 | 1.0 | 1.0 | `tepp_te_uplift` |

> **Cost flag:** applying a *per-user* multiplier means reshaping that user's
> seed curve at map time (value-space, not the current pure-Elo permutation).
> See LLD §3 — this is the single most expensive piece and is recommended for a
> **phase 2**; phase 1 ships the 5 formats + auto-align using the
> operator-global multipliers, with the schema already carrying the per-user
> override columns (cheap) but the apply path deferred.

---

## 6. The 5 enum keys (cross-client contract)

The scoring-format strings are a hard cross-client contract
(`docs/cross-client-invariants.md` → "Scoring format strings"). The full v2 set:

```
1qb_ppr   1qb_tep   sf   sf_tep   2qb      (Option A)
1qb_ppr   1qb_tep   sf   sf_tep   sf_tepp  (Option B)
```

- `1qb_ppr` and `sf_tep` are **unchanged** (existing rows/boards keep working).
- Null in legacy rows still reads as `1qb_ppr`.
- Every location listed under "Scoring format strings" plus every hardcoded
  2-format check (e.g. `useScoringFormat.ts` L105, `copy-from-format`
  `valid_formats`, `_detect_scoring_format_from_meta`) must accept the full set.
  Enumerated in the LLD.
