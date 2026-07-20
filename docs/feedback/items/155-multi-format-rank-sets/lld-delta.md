# LLD delta — Multi-format rank sets (feedback #155)

> Low-level design delta. **Plan only, no code.** File/line references are to the
> tree at planning time (branch `teardown-remediation`). Read with the PRD, HLD
> delta, and `format-mapping-matrix.md`.

---

## 1. Data-loader changes (`backend/data_loader.py`)

### 1.1 Format registry (replace the 2-tuple)

Today:
```
SCORING_FORMATS   = ("1qb_ppr", "sf_tep")
DP_SCORING_PARAM  = {"1qb_ppr": "1qb", "sf_tep": "2qb"}
_KTC_FORMAT_PATH  = {"1qb_ppr": ("oneQBValues", None),
                     "sf_tep":  ("superflexValues", "tep")}
```

Replace with a single table-driven registry (one row per format), so a format is
fully described by *(DP column, KTC block, KTC TE-variant, position uplift)*:

| Format | DP suffix | KTC block | KTC variant | uplift (pos, knob) |
|---|---|---|---|---|
| `1qb_ppr` | `1qb` | `oneQBValues` | — | — |
| `1qb_tep` | `1qb` | `oneQBValues` | `tep` | (TE, `tep_te_uplift`) |
| `sf` | `2qb` | `superflexValues` | — | — |
| `sf_tep` | `2qb` | `superflexValues` | `tep` | (TE, `tep_te_uplift`) |
| `2qb` *(Opt A)* | `2qb` | `superflexValues` | — | (QB, `qb_2qb_uplift`) |
| `sf_tepp` *(Opt B)* | `2qb` | `superflexValues` | `tepp` | (TE, `tepp_te_uplift`) |

`SCORING_FORMATS` becomes the 5 keys. `DP_SCORING_PARAM`, `_KTC_FORMAT_PATH`, and
`DP_PARAM_TO_FORMAT` derive from the registry. Note two formats now share a DP
suffix (`sf`,`sf_tep`,`2qb` all read `value_2qb`; `1qb_ppr`,`1qb_tep` both read
`value_1qb`) — `DP_PARAM_TO_FORMAT` must key on the **format**, not the suffix
(it's currently `{v:k for k,v in DP_SCORING_PARAM.items()}`, which would collide).
Thread the `fmt` key through `_fetch_dynasty_process` / `_apply_consensus_blend`
explicitly rather than re-deriving it from the suffix (line 563 today).

### 1.2 `_apply_consensus_blend` generalization

Currently the TE-uplift branch is hardcoded `if fmt == "sf_tep"`. Generalize to:
"apply the registry's *(position, knob)* uplift for this format." Same rank-
normalize-then-weighted-average blend; the KTC value is read from the registry's
*(block, variant)* path. Neutral knobs ⇒ untouched maps (keep the byte-identical
guard at line 340).

### 1.3 New model_config knobs

`qb_2qb_uplift` (Opt A, default ≈1.05) and/or `tepp_te_uplift` (Opt B, default
≈1.35). Add to `database._MODEL_CONFIG_DEFAULTS` and mirror the fallback in
`data_loader` like `TEP_TE_UPLIFT_DEFAULT`. Update `config-reference.md`.

## 2. Schema (`backend/database.py`)

### 2.1 New column on `users`

```
Column("align_all_formats", Integer)   # 1 = keep rank sets aligned; NULL/0 = off
```
Add to the additive `migration_cols` list (~L1456 block) as
`("users", "align_all_formats", "INTEGER")` — same idempotent ALTER pattern as
`profile_public`.

### 2.2 New table `user_format_prefs`

```
user_format_prefs (
  user_id          TEXT NOT NULL,     -- working key: acct_ / sleeper user id
  scoring_format   TEXT NOT NULL,     -- one of the 5 enum keys
  first_entered_at TEXT,              -- ISO ts; NULL = never entered → prompt on entry
  align_source     TEXT,             -- format this board was aligned FROM (audit); NULL if hand-built
  te_uplift        REAL,              -- per-user TE multiplier override; NULL = format default
  qb_uplift        REAL,              -- per-user QB multiplier override; NULL = format default
  rb_uplift        REAL,              -- (reserved) NULL = default
  wr_uplift        REAL,              -- (reserved) NULL = default
  updated_at       TEXT,
  PRIMARY KEY (user_id, scoring_format)
)
```

- Declared as a `Table(...)` so `metadata.create_all()` builds it on fresh DBs;
  existing DBs get it via `create_all()` too (it no-ops existing tables). No
  per-column ALTER list needed for a brand-new table.
- The four `*_uplift` columns are the per-user editable-mapping overrides
  (phase-2 apply; phase-1 read/write only). NULL everywhere = pure consensus =
  today's behavior.
- **Interaction with `users.tier_overrides`:** none at the storage layer.
  `tier_overrides` stays the authoritative raw-Elo tier state per format;
  `user_format_prefs` holds only preference/mapping metadata. `first_entered_at`
  is the "have we prompted for this format yet?" bit that `tiers_saved`
  (emptiness) can't distinguish from "entered but chose fresh."

### 2.3 Data-dictionary

Add `user_format_prefs` and `users.align_all_formats` to `docs/data-dictionary.
md`.

## 3. Ranking engine (`backend/ranking_service.py`)

### 3.1 `apply_value_map` — already correct, unchanged for phase 1

`apply_value_map(position, ordered_ids)` (L1364) already does the order-
preserving reseed onto **this** service's seed curve. Auto-align is just this
called with the source format's board order against the target service. No
change needed for phase 1.

### 3.2 Source-board selection helper (new, small)

Auto-align needs a "primary/source board" to map FROM. Heuristic (new helper in
`server.py`, not the engine):
1. the format with the most saved positions in `tiers_saved`, else
2. the format with the largest `tier_overrides[fmt]` dict, else
3. the league's detected default, else
4. `1qb_ppr`.

### 3.3 Per-user multiplier apply (PHASE 2 — the expensive bit)

To honor a per-user `te_uplift`/`qb_uplift`, the reseed must run in **value
space**, not the current pure-Elo permutation: multiply the affected positions'
DP/blended *values* by the user's factor, re-derive Elo via
`seed_elo_for_value`, then deal those out in the user's order. Options:
- add an optional `seed_multipliers: dict[str,float]` param to `apply_value_map`
  that reshapes `self._seed[pid]` (value-space) for matched positions before
  sorting; or
- precompute a user-adjusted seed map once per (user, format) and pass it in.

Either way this is materially more work than the O(n log n) Elo permutation and
is why phase 1 ships with the **operator-global** multipliers only (the schema
columns sit NULL until phase 2). Flag in the build ticket.

## 4. Backend routes & session (`backend/server.py`)

### 4.1 Lazy per-format services (FR-3 — the main cost mitigation)

`session_init` (~L7874–7976) builds a RankingService per format in a thread pool
(`for fmt in DB_SCORING_FORMATS`). Change to build **only** the league-default
format (+ any format that has a saved board in `tier_overrides`/`tiers_saved`).
Add a `get_or_build_service(sess, fmt)` helper that lazily constructs and caches
into `sess["services"][fmt]` on first request; `switch_scoring_format` (L3220)
and `copy-from-format` (L3329) call it instead of assuming presence. Same for
trade services (~L7987). This keeps init at ~1–2 services regardless of the
5-format count.

### 4.2 Generalize `copy-from-format` → any source→target pair

`valid_formats = ("1qb_ppr", "sf_tep")` (L3323) → `DB_SCORING_FORMATS`. Logic is
already source→target-agnostic; only the whitelist and the target-service
lazy-build change. Keep the route for the explicit "copy now" affordance.

### 4.3 New route — resolve first-entry + maybe auto-align

`POST /api/format/enter {format}` (or fold into `scoring/switch`):
1. lazy-build the target service (4.1);
2. read `user_format_prefs(user, fmt)`;
3. if `first_entered_at` is set → normal switch, return `{prompt_align: false}`;
4. else if `users.align_all_formats` → run the align (source→fmt via §3.2 +
   `apply_value_map`), stamp `first_entered_at`/`align_source`, persist, return
   `{prompt_align: false, aligned: true}`;
5. else → stamp `first_entered_at` NOT yet (only after the user decides), return
   `{prompt_align: true, source_format}` so the client shows the sheet.

`POST /api/format/align {source_format, target_format, enable_alignment?}` —
does the reseed for one target (or all not-hand-built targets when the Settings
toggle flips on), sets `align_all_formats` when `enable_alignment`, stamps
`first_entered_at`/`align_source`. Thin wrapper over the existing copy logic.

`GET/POST /api/format/mappings` — read/write the per-user `*_uplift` overrides
(phase-1 storage; phase-2 apply).

### 4.4 League detection over 5 formats (`_detect_scoring_format_from_meta`, L631)

Today returns `sf_tep` if superflex OR TEP, else `1qb_ppr` — collapsing both
axes. Resolve them independently:
- **QB axis:** `SUPER_FLEX` in roster_positions OR ≥2 required `QB` slots →
  superflex family; exactly-2 required QB with no SUPER_FLEX → `2qb` (Opt A);
  else 1QB family.
- **TE axis:** `scoring_settings.bonus_rec_te > 0` (or the graded threshold) →
  TE-premium.
- Combine → one of the 5 keys. Covers #166/#167 ("default to the league's
  format, esp SF-TEP"). Update the `format-stats` route (L7261) shape/comments
  accordingly.

## 5. Cross-client enum touchpoints (the contract change)

Every hardcoded 2-format check must accept the 5-key set. Known sites:

- `backend/data_loader.py` `SCORING_FORMATS` (§1.1).
- `backend/database.py` `SCORING_FORMATS` + `default_scoring` comments +
  `_backfill_dual_format` (null → `1qb_ppr` still holds).
- `backend/server.py`: `copy-from-format` `valid_formats` (L3323),
  `_detect_scoring_format_from_meta` (§4.4), any `("1qb_ppr","sf_tep")` literals
  (L994, L3249 doc, L4554, etc. — grep `sf_tep`).
- `mobile/src/hooks/useScoringFormat.ts` L105:
  `if (leagueDefault !== '1qb_ppr' && leagueDefault !== 'sf_tep') return;` →
  membership test against the 5-key set. The apply-chain logic is unchanged.
- `mobile/src/shared/types.ts` `ScoringFormat` union → 5 keys.
- `mobile/src/api/league.ts` / `api/rankings.ts` format params.
- `web/js/app.js` `_eloToTierLabel` / format switches; `extension` if it sends a
  format.
- `docs/cross-client-invariants.md` → "Scoring format strings" table (the
  authoritative list + Tables-affected note) → 5 keys.

Grep seeds for the build agent: `rg "sf_tep|1qb_ppr"` across `backend/`,
`mobile/src/`, `web/`, `extension/`.

## 6. Mobile UX (`mobile/src/`)

### 6.1 Format selector → 5-way

The SF/1QB toggle on Tiers/Trios (driven by `useScoringFormat`) becomes a 5-way
selector. Chalkline: a segmented control is too wide for 5 — use a compact
**pill that opens a bottom-sheet picker** (like `LeagueSwitcherSheet` /
`FormatGate` patterns already in `mobile/src/components/`). Rows: the 5 labels
from `format-mapping-matrix.md` §3, active one checkmarked (ice), each with a
one-line descriptor ("Superflex, no TE premium").

### 6.2 Align sheet (new component, US-1)

New `mobile/src/components/FormatAlignSheet.tsx` (bottom sheet, Chalkline):
- Title: "Align your rankings?"
- Body (sentence case, no emoji): "You've ranked players in **{source label}**.
  Carry that over to **{target label}**, re-priced for this format's values?"
- Primary button (ice, radius ≤8): "Align my rankings".
- Secondary (text/ghost): "Start fresh".
- After Align resolves, an inline row: "Adjust how formats map ›" → opens the
  mapping editor (6.3).
- Fires the `format/enter` → `format/align` calls (§4.3); on success invalidate
  the same query keys `doApplyFormat` does (`rankings`/`progress`/`tiers-status`
  /…).

### 6.3 Mapping editor (new screen/sheet, US-4)

New `mobile/src/screens/FormatMappingsScreen.tsx` (or sheet): per format, a small
list of per-position steppers ("TE value +18%") defaulting to consensus. Writes
`format/mappings` (§4.3). Phase-1 label it "Applies to future alignments" until
the phase-2 apply lands. Chalkline steppers/sliders per `docs/design/
components.md`.

### 6.4 Settings entries (US-3/US-4)

In `SettingsScreen.tsx`: (a) a switch row "Keep rank sets aligned across
formats" bound to `align_all_formats` (toggling on calls `format/align` for all
not-hand-built targets); (b) a nav row "Edit format mappings" → 6.3.

## 7. Test hooks

- `backend/tests/test_tier_occupancy.py` — extend the checked-in consensus
  snapshot to 5 formats; the name↔rung invariant must hold per format.
- Add a `_fetch_dynasty_process` seam test per new format (the `FTF_DP_VALUES_
  FILE` / `FTF_KTC_VALUES_FILE` hermetic seams already exist).
- Determinism test: `format/align` twice on an unchanged source board yields
  identical target overrides (the #124 idempotence guarantee, generalized).
