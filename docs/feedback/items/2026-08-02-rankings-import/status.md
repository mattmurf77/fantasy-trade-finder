# Rankings import v1 (paste-first) — status

**Implemented 2026-08-02** (branch `teardown-remediation`, isolated
worktree), the #232 follow-on from the approved mocks
`mockups/polish-lab-2026-08/rank-method-consolidation-v2.html` (§B, incl.
the paste-first scoping rationale) + `-v3.html` (Variant A entry, upload
glyph). Chooser-side changes tracked in
[`../232-rank-chooser-consolidation/status.md`](../232-rank-chooser-consolidation/status.md).

**Scope: PASTE-FIRST.** One import method for v1 — paste a table. CSV
upload (same parser behind a document picker) and XLSX (real parser
dependency + multi-sheet UX) are noted follow-ons, per the mock's
defer-if-complex recommendation; paste covers the CSV case via
open-file → copy → paste.

**Flag: `ranks.import`** — registered in `backend/feature_flags.py`,
`config/features.json` (**true** — kill switch, not dark launch),
`backend/tests/fixtures/flags/release.json` (mirror), and mobile
`LAUNCHED_FLAG_DEFAULTS` (`useFeatureFlags.ts`). Off ⇒ both routes 404 and
the chooser entry disappears.

## Backend (`backend/rankings_import.py` + 2 routes in `server.py`)

- **Parser (tolerant, per-line):** accepts "rank. name", bare names,
  TSV/CSV rows (name in ANY column — first alphabetic token run per
  line/cell), space-separated rows (trailing ALL-CAPS ≤3-char team codes +
  POS codes stripped); header rows and numbers-only lines are ignored.
- **Matcher tiers:** exact on normalized names (lowercase, punctuation
  stripped, generational suffixes Jr/Sr/II–V dropped — so "Kenneth Walker"
  auto-matches "Kenneth Walker III", audit-visible in review) → fuzzy
  (prefix either way + "K. Walker" first-initial form); one hit = matched,
  2+ = ambiguous with ≤3 candidates (consensus-seed order), none =
  unmatched.
- **`POST /api/rankings/import-match`** — session-authed, format-scoped
  (body `scoring_format` → X-Scoring-Format → session), matches against the
  format's UNIVERSAL pool, read-only, ≤500 rows.
- **`POST /api/rankings/import-apply`** — write-gated
  (`@_gate_unverified_write`), initialized session. **Apply semantics
  (documented in api-reference):** imported ids (deduped, pool-filtered,
  imported order) top a FULL-BOARD permutation; all other players follow in
  their current (consensus) order; applied via `service.apply_reorder` — a
  pure permutation of the existing Elo multiset, so the value curve/tier
  occupancy hold and skipped/unlisted players keep their relative order
  below the imported block. Mirrors reorder's persistence (tier-override
  save, `member_rankings` publish, taste prior, Trends snapshot) + a
  `rankings_import_applied` event.

## Mobile

- **Entry (v3 Variant A):** `rank-home.import` link right of "Build your
  board" (RankHomeScreen; flag-gated) with the corrected `upload` glyph
  (arrow UP out of the tray) added to `chalkline/Icon.tsx`.
- **`components/RankImportSheet.tsx`** — one bottom sheet, two steps (no
  nav route: the flow is chooser-scoped + modal, so it follows the
  sheet/modal exception — no FeedbackFAB, no deep-link entry):
  - *Paste:* heading "Bring your rankings", mono textarea, live "N rows
    detected" (display-only client mirror of the parser; the server parse
    is authoritative), honesty line ("We'll match player names to your
    league's player pool — you review anything we can't match"), primary
    "Match N players". testIDs `rank-import.paste` / `rank-import.match`.
  - *Review (mock B3):* "N of M matched · K need you" counts; rows
    `rank-import.row.<n>` (1-based paste order — a stable domain order,
    same class as the trio-slot exception): auto-matched rows show
    name + team + check (audit-visible); ambiguous rows show "Which one?"
    + ≤3 candidate chips + "Skip this row"; unmatched rows read "No match —
    skipped". Footer primary `rank-import.apply` — "Apply N ranks — M to
    resolve", disabled until every ambiguous row is resolved/skipped —
    posts the resolved order to import-apply. Hint copy states the honest
    skip semantics (skipped/unlisted fall in below imported ranks, current
    order).
  - On success: toast "Imported N ranks onto your board" + navigate to
    Overall ranks so the new order is immediately visible.
- **`api/rankings.ts`:** `importMatchRankings` / `importApplyRankings`
  (X-Scoring-Format header like reorder).

## Tests (`backend/tests/test_rankings_import.py`, 25 tests)

Parser tolerance (rank-dot, bare, TSV name-in-any-column, CSV, space rows
with codes, header/numbers-only ignored) · normalization (suffix/punct) ·
match tiers (exact, "Kenneth Walker"→III, "Marvin Harrison"→Jr.,
"K. Walker" initial, ambiguous seed-ordered ≤3, unmatched, full-paste
counts) · apply semantics on a REAL `RankingService` (imported order lands,
unlisted keep relative consensus order, Elo multiset invariant) · routes
(match happy path + raw-text body + 400s + 401 no session, apply
composition/dedup/pool-filter, member_rankings publish, no-match 400, both
routes 404 flag-off).

`pytest backend/tests` → 1405 passed, 1 skipped · `npx tsc --noEmit` clean.

## Follow-ons

- CSV upload (document picker over the same parser), then XLSX.
- Web/extension import surfaces (import-match already accepts a raw `text`
  body for them).
