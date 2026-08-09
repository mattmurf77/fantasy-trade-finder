# #257 — Consolidate the Trades controls section into the edit sheet (full sheet)

**Status: BUILT — flag `trades.edit_full_sheet`, ships ON.** — 2026-08-08

Tester report (v1.11.0, screen `TradesHome`, severity polish, verbatim):

> "This entire section can be consolidated into the edit function. Just expand
> the half sheet overlay to a full sheet to get everything presented at once to
> prevent scrolling."

**Deliverable (design phase):** `mockups/polish-lab-2026-08/trades-edit-full-sheet.html` —
a "before" column plus three side-by-side full-sheet variants, each with a
rationale and its tradeoff.

**Deliverable (build phase):** Variant C ("Big three + one quiet strip"),
flag-gated `trades.edit_full_sheet` (default ON in `config/features.json`),
built in `mobile/src/screens/TradesScreen.tsx` + `mobile/src/components/TradeDnaSheet.tsx`.
Flag OFF renders both files byte-identical to pre-#257 — the legacy Controls
Card, `OutlookSheet`, and `TradeDnaSheet`'s half-sheet DNA-only body stay in
the tree, untouched, on the off path.

## Operator decisions taken (resolving the open questions below)

1. **Q1 — variant.** C, as recommended.
2. **Q2 — does dismissing the sheet re-run the search?** No. Autosave-on-tap
   (#236) is unchanged; the deck itself is never auto-regenerated. Fairness
   and target changes already reset the deck themselves (existing
   behavior, e.g. `handleToggleFairness`/`resetDeckForNewTargets` clear
   `deck`/`job`), and the lane filter is a client-side re-filter of the
   existing deck (no staleness). The only edits that can leave a deck
   looking stale are DNA edits — outlook, chasing/shopping, untouchables —
   none of which touch `deck` state. `TradeDnaSheet` reports those via a
   new `full.onAnyChange` callback; if any fired while the sheet was open
   (tracked since the last generate, not since the sheet's own open/close,
   so it survives the picker hand-off below) and a deck already exists,
   TradesHome shows a one-line "Preferences changed — tap to refresh"
   strip (`testID="trades.prefs-changed-strip"`) below the receipt that
   re-runs the same `generateMutation` the Find-a-Trade button uses.
3. **Q3 — both engine levers stay.** Yes — that is what variant C is: a
   "Fine tuning" strip (trade fairness + the #256 lane pills) below a
   hairline, dim label, same interactions as before (slider thumb; lane
   pills keep the shipped tap-active-to-clear two-pill construction and
   the shipped `Team-fit moves` / `Value moves` wording, not the mockup's
   `Win-now moves` placeholder).
4. **Q4 — player mode.** The full sheet does **not** absorb the
   TRADE AWAY/TRADE FOR pin board. `mode:'player'` keeps that board
   on-screen exactly where the Controls Card used to render it (now bare,
   no card wrapper); the full sheet, opened from the same receipt, simply
   omits the "Specific players" section in that mode
   (`full.targeting` is `null` when `finderMode === 'player'`).
5. **Q5 — first-run.** The sheet never auto-opens. `ux.outlook_inline_default`
   already suppresses the legacy `OutlookSheet` force-open in production
   (it ships `true`), and the `trades.edit_full_sheet` consolidation adds
   its own bail (`consolidateOn`) to that same effect so a future flip of
   `ux.outlook_inline_default` can't resurrect a force-opened sheet under
   this flag.
6. **Q6 — Dynamic Type.** Accepted as designed: the sheet already sizes to
   content inside a `maxHeight:'85%'` `ScrollView` body, so it scrolls at
   larger text sizes without any code change — no fixed-height sheet frame
   was introduced.

## Scope boundary: classic (non-finder-mode) home

`OutlookBiasReceipt` — the sole entry point into the consolidated sheet —
only mounts when `finderMode` is set (`{finderMode ? <OutlookBiasReceipt ...
/> : null}`). The classic flag-off Trades home (`trades.finder_hub` off, no
`finderMode`) has no receipt, so `trades.edit_full_sheet` is scoped with
`consolidateOn = fullSheetOn && !!finderMode`: that classic path keeps the
legacy Controls Card + `OutlookSheet` regardless of the new flag — cutting
them there would leave no way to reach fairness/lane/targeting at all.
`trades.finder_hub` ships `true` in `config/features.json`, so in practice
every real TradesHome landing has `finderMode` set and gets the
consolidation.

## What the two referents were, in code (pre-#257)

| Tester's words | Code |
|---|---|
| "this entire section" | The **Controls Card** in `mobile/src/screens/TradesScreen.tsx` — the `<Card>` between the mode chips and the Find-a-Trade button. Four controls: Outlook row + its own Edit (~L3259–3276), Trade-fairness slider + hint + ⓘ (~L3285–3331), lane pills "Window moves / Value moves" (~L3337–3370), Target-players block (~L3489–3586, flag `trade.finder_targeting`) |
| "the edit function" (half sheet) | `mobile/src/components/TradeDnaSheet.tsx` — opened by `OutlookBiasReceipt`'s "Change" (#246). `maxHeight:'85%'` but it **sizes to content**, so it renders ~420pt of an available 782pt while its `ScrollView` body scrolls; the untouchables + Manage line sits below the fold |

The finding under the finding: the same preference was editable in **three**
places on one screen — the receipt line, the Controls Card's Outlook row
(whose Edit opened the *older* `OutlookSheet`, which carried its own
duplicate acquire / trade-away chips), and the DNA sheet. Consolidation
collapses three editors into one.

## What changed (implementation notes)

- `TradeDnaSheet` gained an optional `full?: TradeDnaSheetFullProps` prop.
  Omitting it (flag off, or any other DNA-only caller) renders the exact
  legacy half-sheet body — that omission is what keeps flag-off
  byte-identical. When present, the sheet: drops the "tap all that apply ·
  multi-select" header suffixes and the 3-sentence hint; merges
  Chasing/Shopping into one "Positions" block (label + sublabel beside the
  same toggle row); adds a "Specific players" section (targeting chips +
  two labeled Add buttons, replacing the away/acquire direction toggle);
  upgrades the untouchables line to up to 2 name chips + overflow count
  (still the same Manage entry point); and adds the "Fine tuning" strip.
- `TradesScreen.tsx`: the Controls Card block (pin-summary alt + full
  `<Card>`) is now wrapped `{!consolidateOn ? (<>…unchanged…</>) : (<>…new…</>)}`.
  The flag-on branch renders, bare (no `<Card>`, matching the mockup's
  "after" screen): the player-mode pin board (unchanged JSX, just no
  longer card-wrapped), the Find-a-Trade button, the progress strip, and
  the liked-trades count. `OutlookSheet` is not mounted at all when
  `consolidateOn`. The inferred-outlook banner's "Change"/"Set outlook"
  buttons route to the full sheet instead of `OutlookSheet` when
  `consolidateOn`.
- **Modal-stacking constraint:** iOS won't stack a second `<Modal>` over an
  open one (documented sharp edge, `mobile/src/components/CLAUDE.md`).
  `PlayerPickerModal` (used by "Add someone to get/send") is a separate
  Modal, so tapping Add closes the DNA sheet first
  (`setDnaSheetOpen(false)`), opens the picker, and the picker's own Close
  reopens the DNA sheet (`pickerReturnsToSheet` state) — a brief hand-off
  rather than a nested layer, unlike the untouchables/roster-pick layers
  which stay nested inside the same Modal.

## Flag

`trades.edit_full_sheet` — 4-touch convention: `backend/feature_flags.py`
(`FLAG_KEYS`), `config/features.json` (`true`), `backend/tests/fixtures/flags/release.json`
(mirrored `true`, enforced by `test_release_flags_mirror_features_json`),
`docs/config-reference.md`. Client-only — no backend route reads it.

## Original design-phase notes (unchanged from the mockup lab)

### Parallel-work assumption (declared)

`docs/feedback/items/253-outlook-cleanup/prd.md` **did not exist** when the
mockup lab was authored. Per the brief, all frames assumed the redundant
"outlook plays to trade away / acquire" section is **gone** and the minimized
outlook bar (`OutlookBiasReceipt`) is the **survivor** — every variant keeps
that one-line receipt as the collapsed summary and the sole entry point.
Two soft dependencies flagged rather than guessed:

- **#256 lane rename** — mockup frames used "Win-now moves / Value moves / Both"
  as a placeholder. Built with #256's landed wording verbatim (`Team-fit moves`
  / `Value moves`), not the mockup's placeholder.
- **#259 untouchables** — the untouchables row is drawn as an *entry point*
  (count + ≤2 name chips + Manage), not a list, so #259's roster-player
  selection lands in the existing second layer, not in this sheet.

### Variants

Designed against **393 × 852pt**. A full sheet opens at y=69pt and runs over
the tab bar to the device bottom → 782pt sheet, **694pt usable body**. Numbers
below are read off the rendered DOM, not estimated.

| Variant | Thesis | Measured body | Tradeoff |
|---|---|---|---|
| **A — "Everything, regrouped"** | Conservative: move the card in, lose no capability, spend the height on grouping. Five labeled blocks | 639 / 694pt (55pt slack) | Still five questions before a trade appears — least risky, least brave |
| **B — "Three questions"** | Aggressive #205 read: cut the fairness slider and lane pills from the UI entirely; sheet footer *is* Find a Trade | 511 / 694pt (183pt slack) | Two levers vanish with no in-app path back; "re-run search" becomes sheet-only |
| **C — "Big three + one quiet strip"** *(built)* | B's hierarchy without the amputation: three questions at full weight, both engine levers demoted to one dim "Fine tuning" strip below a hairline | 567 / 694pt (127pt slack) | Six blocks; relies on visual weight to prioritize. Tightest slack once player-mode's pin board is considered |

Cut in **all** variants: the duplicate Outlook row + Edit, the whole legacy
`OutlookSheet` (its last entry point), the 3-sentence DNA hint, the
"tap all that apply · multi-select" header suffixes, and the Trade-away /
Acquire direction toggle (replaced by two explicitly labeled Add buttons).
Kept in all: autosave-on-tap (#236), the receipt line, untouchables as an
entry point, Chalkline construction throughout.

## Next step

Shipped behind `trades.edit_full_sheet` (ON). Gates run: `npx tsc --noEmit`
clean; `python3 -m pytest backend/tests -q` — 2041 passed, 1 skipped
(unchanged from baseline; this is a client-only flag with no backend route,
so no new backend tests were added), mirror test
(`test_release_flags_mirror_features_json`) passing.
