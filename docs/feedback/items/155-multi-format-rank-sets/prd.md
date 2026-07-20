# PRD — Multi-format rank sets (feedback #155)

> **Status: PLAN ONLY.** No code has been written. This PRD is the contract for
> a future build; it is gated on the operator decisions in §9.

Covers feedback **#155** ("Add SF no TE"); depends-with **#166/#167** (default
to the league's format, esp. SF-TEP). Companion docs in this folder:
`format-mapping-matrix.md` (data foundation), `hld-delta.md`, `lld-delta.md`.

---

## 1. Problem

Today FTF supports **two** rank sets — `1qb_ppr` and `sf_tep` — and a user's
board in one has to be manually copied into the other (`/api/tiers/copy-from-
format`, #124). Dynasty leagues actually split across at least four common
formats (1QB / Superflex × standard / TE-Premium), and #155 specifically asks
for **Superflex without the TE premium**, which we cannot currently express
(`sf_tep` bakes in the TE uplift). Users in those leagues see values that don't
match their league, and re-ranking from scratch per format is punishing.

## 2. Goal

1. Support **5** dynasty rank sets, each seeded from the correct consensus curve.
2. When a user has a board in one format and enters another for the **first
   time**, offer to **auto-align** all rank sets — carry their order across,
   re-priced to each format's consensus (order preserved, magnitudes = target
   consensus). This is the generalized #124 mapping, run automatically.
3. Let the user keep that alignment **on** (future formats auto-fill) or build
   each independently, and **toggle it from Settings**.
4. Let the user (and operator) **edit the default mappings** — the per-format
   per-position value multipliers that shape each consensus curve.

## 3. Non-goals

- No new consensus data source. We price only what DP + KTC already carry
  (`format-mapping-matrix.md` §2).
- No half-PPR / non-PPR / roster-shape formats.
- No change to the tier ladder, band cutoffs, K-factors, or the raw-Elo
  override storage model (`users.tier_overrides` stays authoritative, re-buckets
  on read).
- Phase 1 does **not** ship the *per-user* editable multiplier apply-path (schema
  is laid down; apply is phase 2 — see `format-mapping-matrix.md` §5 cost flag).

## 4. The 5 formats

Per `format-mapping-matrix.md` §3 — **operator approves the set and the 5th**:

| Enum key | Label | Source | New? |
|---|---|---|---|
| `1qb_ppr` | 1QB | `value_1qb` / KTC `oneQBValues` | existing |
| `1qb_tep` | 1QB TE-Premium | `value_1qb` +TE uplift / KTC `oneQBValues.tep` | new |
| `sf` | Superflex | `value_2qb` / KTC `superflexValues` | new (#155) |
| `sf_tep` | Superflex TE-Premium | `value_2qb` +TE uplift / KTC `superflexValues.tep` | existing |
| `2qb` **or** `sf_tepp` | 2QB **or** SF TE-Super-Premium | see matrix §3 | new — **operator picks** |

## 5. User stories & flows

**US-1 — enter a new format for the first time (align prompt).**
A user with an `sf_tep` board taps the format selector on Tiers/Trios and picks
`1qb_ppr` (which they've never built). A Chalkline bottom sheet asks whether to
align. On *Align*: their SF-TEP order is carried into 1QB, re-priced to 1QB
consensus (QBs drop, as they should), alignment preference is turned **on**, and
a secondary affordance offers *"Adjust how formats map."* On *Start fresh*: they
land on an empty/seed 1QB board and build it independently.

**US-2 — alignment stays on.**
With alignment on, the next new format the user enters auto-fills from their
primary board silently (no prompt), re-priced to that format. They can still
hand-edit any format afterward; a hand-edited format is not re-stomped by
alignment.

**US-3 — toggle alignment from Settings.**
Settings shows *"Keep rank sets aligned across formats"* (default **off** for
existing users). Turning it **on** propagates the user's primary board into
every format they have **not** hand-built. Turning it **off** freezes all boards
as-is.

**US-4 — edit default mappings.**
From the align sheet's secondary affordance or Settings → *"Edit format
mappings,"* the user adjusts per-format per-position multipliers (e.g. "TEs in
TE-Premium formats: +18%"). Defaults are the consensus values. (Phase-2 apply.)

**US-5 — league-driven default (#166/#167).**
When a league is selected, its detected format (now one of 5, resolving both
QB and TE axes from Sleeper roster/scoring) is applied as the active format,
exactly as the current 2-format `useLeagueFormatDefault` does — never stomping
an explicit in-session toggle.

## 6. Functional requirements

- **FR-1** The scoring-format enum is the 5 keys in §4. All clients and the
  backend accept the full set; `1qb_ppr`/`sf_tep` semantics are unchanged; null
  → `1qb_ppr`.
- **FR-2** Each format seeds from its curve per `format-mapping-matrix.md` §3,
  KTC-native where available, DP-derived otherwise, fail-soft to DP-only.
- **FR-3** Per-format RankingService/TradeService instances are built **lazily**
  — only when a format is first entered — not all 5 at session_init (cost, §8).
- **FR-4** First entry into a format with no saved board triggers the align
  prompt (US-1) unless alignment is already on (then auto-fill silently, US-2).
  "First entry / never resolved" is tracked per (user, format).
- **FR-5** Auto-align uses the generalized `apply_value_map` (order from the
  user's primary board, magnitudes from the target consensus). Deterministic and
  idempotent for an unchanged source board (same guarantee as #124).
- **FR-6** A global per-user preference `align_all_formats` controls US-2/US-3.
  Default **off** for existing users.
- **FR-7** Per-format per-position multiplier overrides are stored per user
  (schema in FR-9). Phase 1: read/write + operator-global apply. Phase 2:
  per-user apply in `apply_value_map`.
- **FR-8** Settings exposes the alignment toggle and the mapping editor.
- **FR-9** New table `user_format_prefs` + one `users.align_all_formats` column
  (LLD §2). Additive, idempotent migration; working key `user_id` (acct_/
  sleeper).
- **FR-10** League format detection resolves both axes → one of 5 (LLD §4).
- **FR-11** `tier_overrides` / `tiers_saved` / `unlocked_formats` / `anchor_
  scale` JSON blobs expand from 2 → up to 5 format keys with no shape change
  (they are already format-keyed dicts).

## 7. Migration

- Existing users have `1qb_ppr` + `sf_tep` boards only. They gain the other 3
  **lazily on first entry** (FR-3/FR-4) — no backfill, nothing computed/stored
  for formats a user never opens.
- `align_all_formats` defaults **off** so existing users are never surprised by
  auto-changed boards; they opt in via the first-run prompt (US-1) or Settings.
- Enum expansion 2 → 5 is a cross-client contract change: update every location
  under `docs/cross-client-invariants.md` → "Scoring format strings" and every
  hardcoded 2-format check (LLD §5 enumerates them).
- No data migration for saved boards: overrides are raw Elo and re-bucket on
  read (existing invariant).

## 8. Cost & risk (be honest)

- **Session-init CPU** is the main risk: `session_init` currently builds one
  RankingService **per format** eagerly in a thread pool, each replaying swipes.
  Naively going 2 → 5 is ~2.5× session-init cost. **Mitigation (FR-3): lazy
  per-format construction** — build the league default (+ any format with a
  saved board) at init, defer the rest to first entry. Net init cost stays ~1–2
  services.
- **Process-global pool build** goes 2 → 5 format pools per boot, but all derive
  from the same cached DP CSV + KTC page (one fetch each), so it's extra CPU at
  boot only, not extra egress.
- **Per-user editable multipliers** are the costliest feature (per-user seed
  reshaping at map time). Recommended **phase 2**; phase 1 lays the schema and
  ships the operator-global lever.
- **KTC fragility** unchanged — fail-soft to DP-only already covers all 5.
- **UX risk:** an unsolicited board rewrite is alarming. Mitigated by (a) prompt
  on first entry, (b) default-off alignment, (c) never re-stomping a hand-edited
  format.

## 9. Open decisions for the operator

1. **Approve the 5 formats**, and **pick the 5th**: `2qb` (higher prevalence,
   approximated via a QB-uplift knob) **vs** `sf_tepp` (data-native via KTC, but
   niche). Everything else is identical either way. *(Recommendation: `2qb`.)*
2. **Enum key naming** — confirm `1qb_tep`, `sf`, and the 5th key
   (`2qb`/`sf_tepp`). `1qb_ppr`/`sf_tep` are fixed.
3. **Editable-mapping knob** — confirm **per-format per-position multipliers**
   as the single editable lever (recommended), vs a coarser per-format scalar.
4. **Alignment default** — confirm **off** for existing users (recommended);
   on-by-default would auto-rewrite boards without consent.
5. **Per-user multiplier apply — phase 1 or phase 2?** Recommended phase 2
   (ship 5 formats + auto-align first).

## 10. Maestro test plan (build-phase acceptance)

1. **New-format align (US-1):** with a saved `sf_tep` board, switch selector to
   `sf`; assert the align sheet appears; tap *Align*; assert `sf` board renders
   in the same player order with format-appropriate tiers; assert the "adjust
   mappings" affordance is present.
2. **Start fresh:** repeat, tap *Start fresh*; assert an unaligned seed board.
3. **Alignment on → silent auto-fill (US-2):** with alignment on, enter a third
   format; assert no sheet, board auto-fills in order.
4. **Settings toggle (US-3):** toggle alignment on in Settings; assert
   not-yet-built formats fill; toggle off; assert boards freeze.
5. **League default (US-5/#166/#167):** select an SF-TEP league; assert active
   format resolves to `sf_tep`; select a 1QB-standard league; assert `1qb_ppr`;
   assert an explicit toggle choice is not stomped.
6. **Legacy compatibility:** an existing user's `1qb_ppr`/`sf_tep` boards render
   unchanged after upgrade.
