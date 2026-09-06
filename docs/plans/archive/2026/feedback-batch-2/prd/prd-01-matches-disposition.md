# PRD FB-01 — Matches accept/decline reliability + diagnostics

**Feedback:** #35, #36 (recurrence of #8) · **Surface:** backend · **Priority:** P0

## Requirement
Accepting or declining a mutual trade match must succeed reliably. The action
currently fails with "Action failed" for at least some matches — reported in May
(#8), patched in PR #51, and still failing. Root-cause it for real (add
structured logging that captures the actual exception + traceback), and harden
the disposition route's known fragilities, especially the cross-league path.

## User story
As a manager with mutual trade matches, when I tap **Accept** or **Decline** on a
match, the decision is recorded and the UI confirms it — without an "Action
failed" error — regardless of which league the match belongs to or which league
my session is currently active in.

## Acceptance criteria
- [ ] The disposition handler (`backend/server.py` `disposition_trade_match`,
      ~`:3374`) wraps its body so any unexpected exception is logged with a full
      traceback + the `match_id`, `user_id`, `decision`, the match's `league_id`,
      and whether it was a cross-league action — then returns a typed error
      (not a bare 500) the client can show.
- [ ] Session reads (`sess["service"]`, `sess["league"]`, `sess["players"]`) are
      null-guarded; a missing key never raises a KeyError.
- [ ] **Cross-league correctness:** the route resolves the match's OWN league/
      service rather than blindly applying ELO signals to the active-session
      service when the match is in a different league. If the correct in-memory
      service isn't loaded, the decision is still persisted to `swipe_decisions`
      and the route returns success (ELO replays on next session_init) — it must
      NOT fail the user's tap.
- [ ] A backend test exercises: (a) same-league accept, (b) cross-league accept,
      (c) decline, (d) already-decided (409), (e) not-found (404) — all return
      the documented status without raising.
- [ ] `python3 -m pytest backend/tests/ -q` stays green (41+).
- [ ] The fix ships in a build with the logging enabled so a live repro (if any
      residual case remains) surfaces the real cause.

## Implementation notes
- The mobile client surfaces ANY non-2xx as "Action failed" (MatchesScreen
  disposition mutation `onError`), so the truth lives in the backend response/
  logs. Don't change the client's generic handler in this feature — fix the
  backend so 2xx is returned for the legitimate cases.
- Do NOT alter the ELO K-factors or the +8/−12 signal math — only fix WHERE/
  WHETHER signals are applied and ensure the decision always persists.
- Touch: `backend/server.py` (disposition route), `backend/database.py`
  (`record_match_disposition` if its error path is implicated), `backend/tests/`.
