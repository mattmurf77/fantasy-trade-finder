# Trades-landing ruling — 2026-08-28 (late)

> Operator, after withdrawing a trios-page resume ask mid-question:
> **"I changed my mind.. App opens, land on trades page."** For all users.

- The launch tab becomes **Trades** for everyone. Today `TabNav.tsx`'s
  `initialTab` (~:606) resolves `'Rank'` unless
  `onboarding.trades_first && !firstSwipeDone` → `'Trades'`.
- Implementation: new flag **`nav.trades_landing`**, shipped **true**
  (four-place registration, house comment). ON ⇒ `initialTab` is `'Trades'`
  unconditionally (the onboarding.trades_first special case is subsumed —
  note that in its comment, don't delete its code). OFF ⇒ today's logic
  byte-identical. Same decide-once-at-mount contract the surrounding code
  documents (initialRouteName honored on first mount only; no mid-session
  reroute).
- Rank remains one tap away; #244's completion-aware Rank-stack routing is
  untouched (it governs where the Rank stack opens when the user goes
  there, not which tab the app opens on).
- Suite pin + config-reference row + checklist line ride the same commit.
- Rides the `feat/canvas-results` branch / v1.16.11 train. Applied by the
  orchestrator after the canvas-results agent's commit (shared
  features.json).
