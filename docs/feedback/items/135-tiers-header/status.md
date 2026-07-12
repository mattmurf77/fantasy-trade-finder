# #135 — Tiers screen header wraps two lines — status

**State:** built (2026-07-12, branch `trade-engine-v2`). Awaiting QA/ship.

The in-screen title "Positional Tiers" wrapped beside the header action
buttons (Select / Reset / Quick set). Renamed to **"Tiers"**
(`mobile/src/screens/TiersScreen.tsx`). The Rank-stack route header
(`TabNav.tsx`, `subScreenOptions('Tiers', …)`) already said "Tiers" — no
change needed there. Web's `positional-tiers.html` untouched (mobile-only
report).
