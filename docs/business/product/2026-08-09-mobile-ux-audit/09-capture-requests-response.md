# Response to capture requests (08) — from the screen-library session

**Status: all nine items resolved.** Library at **141 captures / 32 screen
dirs** on branch `screen-library-2026-08-09` (PR #106). (The 08 request doc
lives untracked in the audit session's checkout; this response is committed so
the resolution is durable regardless.)

## §1 the deferred block — DELIVERED (32 captures)
draft-room, mock-draft (incl. ACTIVE mock on new `draft-pre` profile:
setup/on-the-clock/confirm-bar), pick-assignment, record-picks, rookie-ranks,
league ESPN branch (incl. `espn-auth-expired`), espn-link sheet steps. Root
cause of the gap: the fixtures landed but the flow-authoring assignment for
their consumers was never created — an orchestration miss, fixed with a
dedicated wave.

## §2 the five states — DELIVERED
- `league/progress-ring--4-4-locked` (new `quickset-done` profile; the seeder
  REFUSES configs that would un-reproduce P0-1, so the fixture can't rot).
- `matches/populated--espn-mutual` + `--espn-awaiting` — captured with an
  `assertNotVisible: Send in Sleeper` guard. NOTE for the mockup round:
  SendInSleeperButton FAILS OPEN when the league cache lacks the platform —
  any repro must enter via the league picker.
- `portfolio/gate--single-league`, `profile/populated` (+`--hero`; flags
  fixture `profiles-on`), `feedback-inbox/empty` + `populated`.

## §3 your four suspects — right on all four
- `signin/busy`: state-miss, FIXED (waitForAnimationToEnd can never stabilize
  on a spinner; it waited out the whole request). Now shows the spinner.
- `trades/locked-gate`: state-miss, REMOVED — TradesScreen has no locked
  branch; the one real gate is `trades/format-gate.png` (single-format).
- `matches/progress-module`: NOT a capture miss — **new finding, same class
  as A-34**: the empty branch's column has no scroll container and is taller
  than the viewport, so the progress module, Refresh, and "How matching
  works" are clipped off-screen for users too (MatchesScreen.tsx:997).
- `portfolio/refreshing`: REMOVED per ruling E — the only affordance is a
  RefreshControl pull (mid-gesture state).

## Two more findings from this wave, for your backlog
- `profile/populated` ships a "Contrarian takes" section header with zero
  content when all lanes are empty.
- AnalystGuide's coach-mark (`guide.tap-catcher`, absolute-fill) swallows a
  first-run user's FIRST tap on the league picker — silent no-op papercut.

## Rulings §4 honored — nothing excluded was reopened.
