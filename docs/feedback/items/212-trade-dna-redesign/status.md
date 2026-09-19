# #212 — Trade DNA panel redesign (covers #231 deck bias receipt, #206 hint tags)

**Status:** built 2026-08-02 (isolated worktree, branch `teardown-remediation`) — ships live, no feature flag.
**Spec:** approved mock `mockups/polish-lab-2026-08/trade-dna-outlook-v3.html` (v3 = v2 + multi-select made explicit + untouchable mini-cards), plus **two operator tweaks on top of the mock**:

1. **#206 NEED/DEPTH hint tags DROPPED entirely** (operator: "overkill… drop it"). The v3 mock still showed the passive roster-scan tags under the toggles; the build renders none, anywhere in the panel. The `splitDnaChips` util (#193) had exactly one consumer — this panel — so the util (`mobile/src/utils/dnaChips.ts`), its node test (`mobile/tests/check-dna-chips.js`), and the `test:dna-chips` package script were deleted with it. `position_needs` / `position_surplus` remain on the `GET /api/league/preferences` payload for other surfaces.
2. **Untouchable mini-cards read "A Jeanty"** — first-name initial + last name (the mock showed last name only). Single-token names pass through unchanged.

## What shipped

### Collapsed panel (default, `TradeFinderHubScreen`)
- Header: "Your Trade DNA" + outline **Edit** button (`dna.edit`; replaces the old `finder-hub.dna.edit` "Edit prefs" link — no Maestro flow referenced the old id).
- **Outlook chip** (pill, ice tick): plain-words bias for every outlook value — Rebuilding "leans young + picks" · Contending "balanced moves" · All-in "win now, spend picks" · Tanking "max youth, high picks" · Not sure "no bias applied". Inferred outlooks render with an "· inferred" suffix; nothing resolved → "Not set · tap Edit to choose".
- **One summary line** listing ALL explicit selections with position dots ("Chasing ●WR ●TE — Shopping ●QB ●RB"); a group is omitted when unset, the whole line when both are.
- **Untouchable mini-cards** (collapsed only): pill chips with a 6px position-color dot + "A Jeanty" name, cap 3 + mono "+N". Read-only — Edit is the collapsed card's single affordance; no Manage link collapsed. Name resolution reuses the `['calc-values','1qb_ppr']` pool query, now also enabled whenever the list is non-empty (previously only while the #173 sheet was open).

### Edit expands IN PLACE (no sheet)
- Four compact outlook cards (`dna.outlook.<key>`, keys `rebuilder|contender|championship|jets`, single-select, ice border + tick when selected).
- **Chasing / Shopping rows** (`dna.chase.<pos>` / `dna.shop.<pos>`, pos `qb|rb|wr|te|picks`): five multi-select toggles each — QB RB WR TE **+ Picks**. Selected = solid position-color fill + **check glyph** + bold dark label (check is the primary state cue, label weight bumped — the mock flagged WR blue at ≈4.1:1); unselected = line-strong outline + position dot. 44pt min height. **Cross-row mutual exclusion moves** the position (tap a position selected on the other row → selected here, cleared there — never an error). In-UI "· multi-select" caption on both group labels + a one-line hint.
- Untouchables line: count + **Manage** (`finder-hub.dna.untouchables`, id retained) opening the existing #173 management sheet.
- **Done** (`dna.done`, ice fill + check) persists and collapses. No-op collapse when nothing was touched — a save invalidates the backend's cached deck (`/api/league/preferences` POST → `_invalidate_trade_jobs`), so an idle expand/collapse never pays that. Save errors render inline and keep the editor open.

### Persistence
- Same API OutlookSheet used: `saveLeaguePreferences` → `POST /api/league/preferences` (`team_outlook` + `acquire_positions` + `trade_away_positions`; arrays were already the multi-select shape).
- The backend requires a valid `team_outlook` to persist positions; when the user picked no outlook card, Done saves `not_sure` (the honest no-choice value — the collapsed chip then says "no bias applied", and the engine applies no directional bias).
- **Picks is stored as `'PICK'`** in the arrays — the backend's pick pseudo-player position, which the FB-47 counterparty-fit targeting (`acquire_targets` / `sell_targets`) already matches against; the POST validates array-ness only, so old servers roundtrip it harmlessly. Cross-client note: web's outlook overlay doesn't offer a Picks toggle yet; it simply won't render the value.

### #231 — deck bias receipt (`OutlookBiasReceipt.tsx`)
- New self-contained component (`mobile/src/components/OutlookBiasReceipt.tsx`): quiet ink-2 line with a flare tick — "Leaning **young + picks** — you're **Rebuilding**." + ice **Change**. All four directional outlooks mapped; renders null unless flag `trade.outlook_direction` is on AND the resolved outlook is directional. Resolution mirrors the engine's #175 rule (declared, else inferred); an inferred bias reads "you look" instead of "you're" so the receipt never overclaims. `not_sure`/none ⇒ no receipt (the engine applies no bias).
- **Change** → `navigation.navigate('TradesHome', { editDna: true })`; the hub consumes the param and auto-expands the editor.
- TradesScreen (owned by another agent this round) got exactly one mount line + one import. The mount line, inserted directly after the `TradeFinderModeBar` block in the deck ScrollView (finder modes only):

  ```tsx
  {finderMode ? <OutlookBiasReceipt navigation={navigation} /> : null}
  ```

## OutlookSheet decision
**Kept, hub mount removed.** The panel fully replaces the sheet on the hub (import + mount + `outlookOpen` state deleted). The sheet remains the outlook editor for TradesScreen's own entry points — the no-outlook first-visit force-open, the `ux.outlook_inline_default` banner path, and the classic (flag-off) deck's Edit — none of which were in scope this round. Revisit retiring it if/when those surfaces converge on the hub panel.

## testIDs (registry updated in `mobile/src/components/CLAUDE.md`)
`dna.edit` · `dna.done` · `dna.outlook.<championship|contender|rebuilder|jets>` · `dna.chase.<qb|rb|wr|te|picks>` · `dna.shop.<qb|rb|wr|te|picks>` · `dna.untouchable.<player_id>` · `trades.outlook-receipt` · `trades.outlook-receipt.change`. Removed: `finder-hub.dna.edit`. Retained: `finder-hub.dna.untouchables` (now the expanded Manage link), `finder-hub.untouchables.row/remove.<player_id>` (sheet unchanged).

## Design-system notes
- Deliberate deviation from the mock's `--faint` key labels: collapsed "Chasing/Shopping/Untouchables" keys use chalk-**dim** (chalk-faint is placeholders/disabled only per the a11y floor — content text ≥4.5:1).
- Position color is never the only encoding: dots/fills pair with QB/RB/WR/TE/Picks text labels; selection is check-glyph + fill, not color alone. Pick teal = `tier.first_1` (`#2dd4bf`), the existing pick data color.
- Pills (`outChip`, mini-card chips) are specced pill exceptions; everything else ≤8px radius.

## Verification
- `cd mobile && npx tsc --noEmit` — clean (2026-08-02).
- Backend untouched — pytest suite not in scope (no server-side diff).
- Deleted-test note: `npm run test:dna-chips` removed from `mobile/package.json` (tested only the deleted util).
