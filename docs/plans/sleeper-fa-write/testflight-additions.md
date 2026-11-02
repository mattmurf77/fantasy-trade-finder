# Free-agent moves (D1): TestFlight checklist additions

> Changes to the manual TestFlight checklist in the scope block (`docs/plans/sleeper-fa-write/scope.md` §3 on `plan/fa-moves-launch`, rows T1–T15, FA1–FA6, AX1), from release-lead's independent QA of #579 @ `c3449e15` (2026-11-01). The checklist stays the only runtime evidence mobile gets (D-056). Every real move is a production platform write: it needs the operator's approval when it runs, uses the dummy Sleeper league only, and is reversed straight afterwards (scope §3).

## Contents

- [Changed rows](#changed-rows)
- [New rows](#new-rows)

## Changed rows

| # | Setup | Steps | Expected |
|---|---|---|---|
| T9 | Connected, consent valid; Network Link Conditioner on a slow profile, so the send outlasts 8 s | Tap the named CTA. **Wait until "Still sending…" appears**, then turn on airplane mode | "Check before resending"; **no retry** (no CTA for that player); Open in Sleeper offered. Airplane off → Sleeper shows whether it landed, and the list after Done agrees. Reverse if it landed. (Turning airplane mode on before the line shows can be offline at the tap instead, which is state 11, not 12.) |
| T10 | **Post-launch:** day 8 after T3's grant | Tap the named CTA | The consent step (lapsed); no write until ticked. It can't run before launch, since the window is 7 × 24 h from a real grant. The boundary itself is pinned by the backend test |

## New rows

| # | Setup | Steps | Expected |
|---|---|---|---|
| UT1 | Flag on; connected; consent valid; a Sleeper free agent in the focused league | Usage Trends → open the player's availability (the card's pill, or expand the row in Version B). **Wait a second** (the capability is prefetched in the background), then tap Add for that league | The claim sheet opens on the in-app move (the named CTA, "In {League}"), not "Open in Sleeper to claim". Tap → the result names the player and the league. Reverse. Control: tap Add **straight away** on a row whose availability was never opened: it opens at once in the hand-off, as #509 did |
| DT1 | Connected, consent valid; Network Link Conditioner on a slow profile | Tap the named CTA **twice as fast as possible** (two fingers, or a double tap) | Exactly **one** move in Sleeper, and the server's move log shows one `POST /api/league/free-agents/move` for that tap. Reverse. Repeat with consent **not** valid: exactly one consent step appears, and one consent GET |
| AX2 | VoiceOver on | (a) Connected, consent valid, a slow profile: tap the named CTA and wait. (b) Settings › Leagues with a grant active and the network off: tap **Stop roster moves** | (a) VoiceOver says "Still sending…" when the line appears (about 8 s). (b) VoiceOver says "Couldn't turn off roster moves. Try again."; the row stays. Also check that "Turn off" in the window line is its own button (one swipe lands on it) |
