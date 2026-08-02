# FB-232 (+ #233) — Rank-method chooser consolidation — status

**Implemented 2026-08-02** (branch `teardown-remediation`, isolated worktree),
per the operator-approved mocks
`mockups/polish-lab-2026-08/rank-method-consolidation-v2.html` + `-v3.html`
(verdicts: chooser consolidation approved with **Tiers board as MOST
CONTROL**; import entry = **Variant A** text link; paste-first scope stands —
the import build itself is tracked in
[`../2026-08-02-rankings-import/status.md`](../2026-08-02-rankings-import/status.md)).

## A · Chooser consolidation (#232)

- **Shared content model** — `mobile/src/navigation/rankChooserModel.ts` is
  the single source of truth consumed by BOTH chooser surfaces
  (`RankHomeScreen` + the Rank-tab `RankMenu` sheet in `TabNav.tsx`), so the
  two can't diverge. Decision (per the task's either/or): the sheet stays a
  sheet — collapsing it to open RankHome would cost the one-tap mode switch
  from every rank surface's header — but it renders the model verbatim.
- **Three primary cards/rows, labeled by outcome:**
  - **FASTEST = Quick set** (recommended, flare tag) + the Quick-rank
    follow-on subrow ("Then, if you want: …").
  - **MOST PRECISE = Head-to-heads** (route `Trios`; chooser vocabulary
    unified to "Head-to-heads" per the mock — route/testID segments keep
    the historical `trio(s)` names).
  - **MOST CONTROL = Tiers board** (route `Tiers`, drag-into-tiers; the v2
    operator correction — v1 had the overall 1-to-N list here).
- **"More ways to rank" disclosure** (collapsed by default, both surfaces):
  Pick Anchors · Overall ranks (ManualRanks, "order every player 1-to-N") ·
  Trends. Trends navigates without saving a method pref.
- **Quick rank removed as a peer** from both surfaces (mock rationale: it's
  Quick set's follow-on pass, offered by the finish prompt; the route stays
  registered for the prompt + deep links).
- RankHome drops the v1 hands-on meter / WE-STEER axis / time hints in favor
  of the mock's role tags; callout copy tightened to the mock's two
  sentences. Method selection behavior unchanged (#162/#165 navigate-not-
  replace, pref persistence, fire-and-forget `POST /api/ranking-method`).
- **Import entry (flag `ranks.import`, v3 Variant A):** quiet text link
  right of the "Build your board" heading — chalk-dim question "Have
  rankings already?", ice underline, corrected UPLOAD glyph (arrow up out of
  the tray; new `upload` icon in `components/chalkline/Icon.tsx`). Shares
  the heading's line; wraps intact + right-aligned when it can't
  (flex-wrap + `marginLeft:'auto'`). testID `rank-home.import`.

New testIDs: `rank-home.card.trends` · `rank-home.more-toggle` ·
`rankmenu.more-toggle` (existing `rank-home.card.<pref>` +
`rankmenu.<method>` ids unchanged; `rankmenu.quickrank` retired with the
row).

## B · Quick set empty-tier CTA (#233)

`QuickSetTiersScreen` footer at **0 selected** (testID `quick-set.save-btn`):

- Primary becomes the position-aware, action-first
  **"Continue — no QBs this high"** (position from the active walk); last
  tier uses the short-fit fallback **"Continue & finish"** ("this high"
  reads wrong at FA and the full string + suffix would overflow).
- **Skip is hidden at 0 selected** — it duplicated the primary (an empty
  save composes as a skip). It reappears with ≥1 selection, where the
  footer renders its exact previous content (Back / Skip / "Save <tier>
  (N)").
- Tap behavior unchanged: same `onSave` press; the empty branch remains a
  pure skip and can never trigger #161 demotion.
- **Supersedes the #159 labels** ("No players for this tier" / "No players
  here & finish") — `159-empty-tier-cta/status.md` updated.

## Verification

- Backend: `python3 -m pytest backend/tests` → **1405 passed, 1 skipped**
  (includes the 25 new import tests; `flags/release.json` fixture mirrored
  for the new flag).
- Mobile: `cd mobile && npx tsc --noEmit` → clean (exit 0).

Docs touched: `docs/api-reference.md`, `docs/config-reference.md`,
`docs/design/components.md`, `mobile/src/screens/CLAUDE.md`,
`mobile/src/navigation/CLAUDE.md`, `mobile/src/components/CLAUDE.md`
(testID registry), `docs/feedback/items/159-empty-tier-cta/status.md`.
