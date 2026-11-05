# Exceptions register — operator-approved departures from Chalkline

Seeded 2026-10-15 from `living-memory/DECISIONS.md`, `docs/design/components.md`,
`docs/design/brand.md`, `docs/cross-client-invariants.md` and the shipped code comments
that claim an exception. Re-grep before relying on it (section 4).

## 1. The rule

- An exception is valid only if a **recorded operator decision scopes it**: a D-ID in
  `living-memory/DECISIONS.md`, or an operator ruling written into a feedback item's or
  plan's status/scope doc. A code comment, a mockup, or "the operator liked it" is not a
  record.
- Valid exceptions apply **only inside their scope**. The same move on another screen
  is a plain violation.
- A diff that relies on an exception with no record is a **block** finding: "undocumented
  exception". The fix is either removing the departure or getting an operator decision
  recorded; the reviewer never grants one.
- A valid exception missing from `docs/design/design-system.md` is a **docs owed** item
  in the verdict (copy it into the doc; see [doc-sync.md](doc-sync.md)). It does not
  block the diff.
- The register records exceptions; it does not create them. A new one enters here only
  after its decision exists.

## 2. Valid exceptions

`components.md` / `design-system.md` columns: does that doc record the exception today?

| ID | Rule bent | Scope (nothing outside it) | Decision | Date | components.md | design-system.md |
|---|---|---|---|---|---|---|
| E1 | Ice ≤ ~3 places per screen (brand.md §Color philosophy) | **Home position tiles**: the suggested Buy/Sell side is ice-bordered on **every** banded tile, up to four; Home can show five ice elements with the active tab. Code: `emphasizedSides` in `mobile/src/utils/positionSplit.ts`, `mobile/src/components/home/PositionTile.tsx` | D-204 (2) | 2026-10-10 | yes (Position tile row, but tagged D-202) | **no — docs owed** |
| E2 | The largest sanctioned ice surface; the operator asked for red | **Hero entry tile** (`OverhaulEntryCard`, Acquire landing): one full-width ice-filled tile per screen, counting against the ice ration, every colour from the single `HERO_TONE` constant. The requested **red is not approved**: Chalkline has no red action colour, so it needs a design-system token plus an ADR-005 amendment, open as `living-memory/NEXT.md` (2026-09-08 section, item 3). A red hero, or a second hero on a screen, is a block | D-192 | 2026-09-08 | yes (Hero entry tile row, tagged G-425) | **no — docs owed** |
| E3 | No gradient, no glow (Prohibition 2, brand.md never-list) | **Mascot artwork inside its own box only**: painted raster sprites under `mobile/assets/mascot/ram/`, inset to 70% ink width. No glow bleeding onto surfaces, no gradient panel behind it, no halo on ink-1 cards. Placement: guide bubble, Team Review, empty states, celebrations, auth page; never inline with data | D-155, D-156 | 2026-08-22/23 | partly (EmptyState and Celebration allow the mascot) | **no** (recorded in `brand.md` §Logo and `mobile/assets/CLAUDE.md`) |
| E4 | Hit targets ≥ 44pt (Accessibility floors) | **Home Status rows** (`components/home/StatusRow`): 40pt `minHeight`, full card width | D-202, round-3 ruling R3 in `docs/plans/home-engagement/scope.md` | 2026-10-10 | yes (Status row) | **no — docs owed** |
| E5 | Ice ≤ ~3 places per screen | **LeagueProgressModule** full variant on the low-activity League home: both in-section buttons are solid ice, beside the ring arc and segmented bar | Operator tweak recorded in `docs/feedback/items/229-empty-states-progress/status.md` (no D-ID) | 2026-08-02 | yes (LeagueProgressModule row) | no |
| E6 | Ice = actions only (design-system.md §Ice) | **Dashed-ice other-board marker** in charts drawing bars from one value basis; first consumer `LeagueSummaryScreen` `consTick`. It is a data encoding; reuse for anything else is a violation | #248, in `docs/cross-client-invariants.md` §Position color tokens | 2026-08-05 | no | no |
| E7 | Type scale is the token table | **`title-compact`** (Archivo 600 at 13/18), composed from `type.title` + `type.bodySm` metrics, **two-column trade canvas player names only** | #411 / FB-411 | 2026-08-30 | — | yes (Typography table) |
| E8 | Pills only where specced (Prohibition 5) | **Trade DNA panel** `outChip` and untouchable mini-card chips (`TradeFinderHubScreen`), per the operator-approved mock `trade-dna-outlook-v3` | Approved mock recorded in `docs/feedback/items/212-trade-dna-redesign/status.md` (no D-ID) | 2026-08-02 | no (ModeLauncherCard row describes the panel, not pill chips) — docs owed | no |

Closed, kept for history:

| ID | Rule | What happened | design-system.md |
|---|---|---|---|
| X1 | No emoji: the verbatim eyes-emoji (U+1F440) + `They're interested` pill | Migrated to `eye` icon + text on web and mobile 2026-07-02 (ADR-004); `cross-client-invariants.md` §Trade-card copy strings records it | still reads as pending (§Iconography) — docs owed |

## 3. Claimed in code, not recorded

These comments assert an exception that no decision records. Existing debt is not
re-flagged on an unrelated diff; a diff that **adds, extends or copies** one is a block.

| Where | Claim | Status |
|---|---|---|
| `mobile/src/screens/ProfileScreen.tsx` `avatar` style | `borderRadius: 48`, "avatar image may stay round (screen-specific exception)" | no decision found (2026-10-15 grep of DECISIONS.md, docs/design/) |

## 4. Keeping it current

Search for exceptions the register may be missing before you call a departure
undocumented:

```sh
git grep -n -i -E -e 'exception|operator (ruling|tweak|decision)|by operator' --and -e '[ (]ice|ice\.|--ice|flare|chalkline|radius|shadow|gradient|emoji|glow|44 ?pt|touch floor|pill|ration' -- living-memory/DECISIONS.md docs/design docs/cross-client-invariants.md 'docs/plans/*/scope.md' 'docs/feedback/items/*/status.md' 'mobile/src/*.tsx' 'mobile/src/*.ts' 'web/*.css' 'web/*.html' 'extension/*.css'
```

Most hits are unrelated rulings that happen to mention a design word; a hit that
approves a visual departure and is not a row above is a missing row. (macOS
`git grep -E` has no `\b`; the pattern avoids it.)

When a new operator decision approves a departure, the first review that relies on it
lists two docs-owed items: the new row for this register (`design-lead` adds it) and the
copy into `design-system.md`.
