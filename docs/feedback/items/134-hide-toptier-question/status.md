# #134 — Remove the top-tier asset question (Anchors) — status

**State:** built (2026-07-12, branch `trade-engine-v2`). Awaiting QA/ship.

The #111 pick-value-scale control ("A top-tier asset is worth 2/3/4 1sts"
pill row at the foot of the Pick Anchor wizard) is **hidden**, not deleted:

- `mobile/src/screens/PickAnchorScreen.tsx` — pill row + its scale
  query/mutation and styles removed, with a comment pointing at the intact
  plumbing. Wizard flow otherwise unchanged.
- **Kept:** `GET/POST /api/anchor/scale` (backend), `getAnchorScale` /
  `setAnchorScale` / `TopTierFirsts` in `mobile/src/api/rankings.ts`, and any
  previously stored per-user scales (they keep applying server-side). New
  users stay on the default (4 firsts — the #117 consensus rung).

Docs: `mobile/src/screens/CLAUDE.md` row updated. `docs/glossary.md`'s
"Pick-value scale" entry still describes the backend semantics (accurate);
the UI entry point is gone until the control returns.
