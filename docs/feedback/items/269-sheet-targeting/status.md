# #269 — Move team targeting + a league picker into the edit sheet; drop the Team/Player tabs

**Status: BUILT — flag `trades.sheet_targeting`, ships ON.** — 2026-08-09

Also covers **#276** — auto-scroll to the generated trade + a card vertical-cost
audit (multi-ID fix, lowest ID per `docs/feedback/items/README.md`).

Operator report (verbatim, on the #257 full-height `TradeDnaSheet`, referred to
as "the prefs tab"):

> "Only missing option on the prefs tab is selecting a specific team. Probably
> worth having a league picker right above it. Then we can remove player and
> team tabs (you can bundle removing those tabs when shipping this live)."

> "Focus the users screen to the generated trade when they hit find a trade.
> The entire trade offer and draft pick valuation should fit on screen."

## #269 — what changed

Built in `mobile/src/screens/TradesScreen.tsx`, `mobile/src/components/TradeDnaSheet.tsx`,
`mobile/src/components/TradeFinderModeBar.tsx`, gated end-to-end by a new flag
`trades.sheet_targeting`.

1. **League row**, directly above the team-targeting block. Reuses the global
   `LeagueSwitcherSheet` component (the same one `TopBar` mounts) wholesale —
   no second switcher implementation. Since `TradeDnaSheet` is itself a
   `<Modal>` and iOS won't stack sibling Modals, the row closes the DNA sheet,
   opens `LeagueSwitcherSheet`, and reopens the DNA sheet when it closes
   (`openLeaguePickerFromSheet` / `closeLeaguePicker`) — the exact
   close-sheet/open-picker/reopen-sheet pattern the sheet's "Specific players"
   Add buttons already use for `PlayerPickerModal`.
2. **"Trade with" block**, single-select, tap the active manager again to
   clear. **Reuses the pre-existing Team-mode machinery verbatim**, not a new
   filter:
   - The picker itself is the SAME "Pick a manager" `Modal` (`teamPickerOpen`,
     `teamPickerOpponents`, `leagueUsersQuery`) legacy Team mode already used
     — the sheet's row opens it via the same close/reopen pattern
     (`openTeamPickerFromSheet`).
   - `scopedOpponent`/`scopedOpponentName` — the values that already fed
     `generateMutation`'s `opponent_user_id`, the FB-47 target-picker pool
     (`targetPickerPool`), and the asset-ideas query — are now computed as
     `sheetTargetingOn ? sheetOpponent?.userId : (finderMode === 'team' ? route.params… : undefined)`.
     Only the SOURCE of the id changes (sheet-local state vs. route params);
     every downstream consumer is untouched.
   - Selecting/clearing autosaves like the sheet's other prefs: it does
     **not** reset the deck outright (unlike legacy Team mode's `setParams`,
     which does via the `finderMode`/`scopedOpponent` reset effect) — it
     marks `prefsChangedSinceGenerateRef.current = true`, surfacing the
     #257 "Preferences changed — tap to refresh" strip on dismiss, same as
     the #172 trade-intent chips.
3. **Team and Player chips removed** from `TradeFinderModeBar` via a new
   `hideTeamAndPlayer` prop (default `false` ⇒ today's five/six chips
   exactly). `TradesScreen` passes `hideTeamAndPlayer={sheetTargetingOn &&
   consolidateOn}` — gated on the full sheet actually existing so there's
   always a way to reach team targeting. Guided/Calc/Free agents (+ Draft
   under `draft.room`) are unaffected.
4. **Nothing deleted.** Player mode's on-screen TRADE AWAY/TRADE FOR pin
   board (`finderMode === 'player'` branches throughout `TradesScreen.tsx`)
   and Team mode's route-param scoping (`pickScopedTeam`, the
   `finderMode`/`scopedOpponent` reset effect) both stay in the tree —
   the chips that reached them are just gone. A stale deep link or the
   flag-off path can still land on `mode:'team'`/`mode:'player'` and render
   correctly.

### Flag-off behavior

`trades.sheet_targeting` off ⇒ `scopedOpponent` computation collapses to the
original `finderMode === 'team' ? route.params… : undefined` expression,
`TradeDnaSheet`'s `full.teamTargeting` is `undefined` (no League/Trade-with
block renders), and `TradeFinderModeBar` renders its full chip set — the
three files are byte-identical to pre-#269.

### Flag

`trades.sheet_targeting` — 4-touch convention: `backend/feature_flags.py`
(`FLAG_KEYS`), `config/features.json` (`true`), `backend/tests/fixtures/flags/release.json`
(mirrored `true`, enforced by `test_release_flags_mirror_features_json`),
`docs/config-reference.md`. Client-only — no backend route reads it.

## #276 — what changed

Two independent pieces, per the operator's own framing ("ships with the same
flag if it touches layout, or unflagged if it's pure scroll behavior — your
call").

1. **Auto-scroll to the generated card — unflagged (pure scroll behavior,
   no layout change).** `handleFindTrades` (the single entry point every
   "Find a Trade" / "Find more trades" tap and the "Preferences changed"
   strip already share) arms `pendingScrollToDeckRef`. The existing
   deck-append effect (`useEffect` on `job?.cards.length`/`job?.status`)
   consumes it the first time the current job reports any cards at all —
   covering both a first search (empty deck → populated) and a "Find more
   trades" tap that streams fresh cards on top of an existing deck — and
   scrolls `mainScrollRef` to the deck's measured Y position
   (`deckCardY`, set via an `onLayout` on the deck's wrapping `View`, the
   same pattern `featuredWindowY` already uses for the single-pin featured
   window). This is plain scroll positioning; it changes no rendered
   output, so it ships unflagged.
2. **Card vertical-cost audit — unflagged (spacing only, no information
   removed).** `mobile/src/components/TradeCard.tsx`: outer card `padding`
   `space.lg → space.md` and the outer stack `gap` `space.md → space.sm`
   (trims ~28pt across a typical card's ~6 visible sections: header, fit
   line, Match strength, the give/receive split, Edit-in-calculator, the
   pick-valuation bar); `StrengthBar`'s existing `compact` prop is now
   passed (trims its internal header-to-meter gap by 4pt). No section was
   hidden or deleted — the pick-valuation line (`TradeValueBar`) is
   untouched; it already ships its own density pass (#243) with the
   verdict paragraph collapsed by default behind "Why?".
   `TradeCard.tsx` is shared with `MatchesScreen`'s `variant="match"` cards,
   so those tighten by the same amount — a deliberate, low-risk side effect
   (spacing-only, same component).
   **Caveat, stated plainly:** this pass is reasoned from the component
   tree and the Chalkline space-token scale, not confirmed against a
   simulator screenshot of a live 2-for-2 card — this session did not spin
   up a seeded backend + simulator session to measure pixels. If a future
   pass finds the typical case still scrolls, the next lever is collapsing
   `StrengthBar` or the Edit-in-calculator row behind a disclosure, not
   further padding cuts.

### Maestro / sim-gate note

No new Maestro flow was authored in this session — the scroll behavior and
spacing change are both exercised implicitly by the existing Trades flows
(any flow that taps Find a Trade). Flagging this explicitly rather than
silently skipping the delta: a follow-up `maestro-test` pass against the
`trades.sheet_targeting` league-picker/team-targeting sheet flow (open sheet
→ pick league → pick team → refresh strip → deck scoped) is recommended
before this flag graduates past internal use.

## Gates run

- `python3 -m pytest backend/tests -q` — 2053 passed, 1 skipped (matches the
  session's stated baseline exactly; client-only flag, no backend route, so
  no new backend tests were added). `test_release_flags_mirror_features_json`
  passing.
- `cd mobile && npx tsc --noEmit` — clean.
- `mobile/scripts/testid-lint.sh` — `testid-lint OK` (new testIDs:
  `dna.league-picker`, `dna.team-target.chip`, `dna.team-target.pick`).
