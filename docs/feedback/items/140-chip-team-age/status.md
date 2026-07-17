# #140 — Team + age on Quick set / Quick rank chips — status

**Status: built (2026-07-17), pending release.**
Spec source: approved mockup `mockups/quickset-cards/bottom-row.html` (option 2
"bottom-row" + the conditional-POS lever, operator-approved). Shipped together
with the tier-label rename "Waivers" → "FA" (display-only; key `waivers`, gray
`#7a7f96`, and the [1150, 1215] band unchanged).

## What shipped

### 1. Chip meta row (mobile)

- `mobile/src/screens/QuickSetTiersScreen.tsx` — chip meta row is now
  `TEAM AGE <current tier>` at the exact shipping chip dimensions
  (minHeight 48, padding 6/8, radius sm, name 12 uiSemi 1-line ellipsis,
  meta 9px, gap 6, marginTop 2). Team = 9px uiSemi chalk-dim uppercase with
  the standard `'FA'` fallback when `team` is null; age = bare numeral,
  9px Plex Mono (`fonts.data`, data-numeral rule), omitted when `age` is
  null. Separators stay the existing bare 6px gaps — no dot glyphs (the
  mockup measured dots at ~12px the row doesn't have).
- `mobile/src/screens/QuickRankScreen.tsx` — same rule: meta row was
  `POS TEAM`, now `TEAM AGE` (no tier label — the step header owns the
  tier), same styles.

### 2. Conditional POS (not deleted)

Each screen declares a module-level `const SHOW_POSITION = false` and the
chip renders the POS token (position-colored, unchanged style) only when
it is true. Default false because both walks are position-scoped — the
active position tab already names the position, so POS was redundant and
its width now funds TEAM + AGE. Any future cross-position context flips
the constant (or lifts it to a prop) to get POS back.

**Extraction choice:** the chip markup stays inline per screen (it already
was — the two chips differ in their top-right element and tier label), so
the change is duplicated consistently rather than extracted into a shared
component. Smallest surgical diff; no testID or accessibility changes.

### 3. Width budget vs the mockup

The mockup's measured worst cases (real Archivo/Plex metrics, ~98px chip
interior): `WR WAS 30 WAIVERS` ≈ 111px (over) and `WR SEA 24 4+ 1STS`
≈ 103px (over). Both fixes land here at once:

- POS dropped frees ≈19px (mockup deviation (c): worst case ≈89px, ≈9px
  slack, everything fits at gap 6 — no gap shrink, no tier ellipsis needed).
- "WAIVERS" → "FA" removes the widest label outright; the worst case is
  now `TEAM AGE 4+ 1STS` ≈ 84px — ≈14px slack.

Quick rank's row (`TEAM AGE`, no tier) is trivially inside budget.

### 4. Payload feasibility (verified)

`GET /api/rankings` builds rows via `ranked_player_to_dict` →
`player_to_dict` (`backend/server.py`), which always serializes `team` and
`age`; `RankedPlayer extends Player` already types both
(`mobile/src/shared/types.ts`). No API change needed.

### 5. "Waivers" → "FA" label sweep (display-only, key unchanged)

| Surface | File(s) |
|---|---|
| Mobile label maps | `mobile/src/utils/tierBands.ts` (`TIER_LABEL`), `mobile/src/components/TierBadge.tsx`, `mobile/src/components/chalkline/Badge.tsx` (`TierChalkBadge` map; StyleGuide renders from it) |
| Mobile copy | `mobile/src/navigation/TabNav.tsx` Rank-menu Tiers sub ("4+ 1sts down to FA") |
| Web | `web/positional-tiers.html` (legend swatch, tier-row name, assign-btn short label `Wvrs`→`FA`, `TIER_LABELS_SHORT`), `web/profile.html` (`TIER_LABELS`), `web/js/app.js` (`_eloToTierLabel`), `web/style-guide.html` (badge), `web/faq.html` (tier explainer) |
| Extension | `extension/content.js` (`TIER_LABELS`), `extension/README.md` (color table) |
| Backend | `backend/og_image.py` (`TIER_LABELS`), `backend/trade_service.py` (star-tax human-explanation `_tier_display`) |
| Docs | `docs/cross-client-invariants.md` (canonical table + rename note), `docs/glossary.md` (Tier band entry, new "FA (tier)" entry, Quick set entry), `docs/design/design-system.md`, `docs/design/components.md`, `mobile/src/{utils,theme,screens}/CLAUDE.md` |

No backend test pinned the "Waivers" display string (keys only) — zero
test updates required. Historical docs/plans (`tier-naming-proposal.md`,
feedback items #117/#124, mockups) intentionally keep the old label as
history.

## Docs

`docs/design/components.md` Quick set / Quick rank walk chip specs updated
(meta row content + conditional-POS rule). testID registry untouched — no
selector changed (`quick-set.chip.<player_id>` / `quick-rank.chip.<player_id>`
as before).

## Verification

- `cd mobile && npx tsc --noEmit` — clean.
- `python3 -m pytest backend/tests/ -q` — green (see build log).
- `node --check` on `web/js/app.js` + `extension/content.js` — clean.
- Repo grep: no user-facing "Waivers" remains outside history/plans and
  the retired-label notes.
