# #184 — Feedback badge counts closed items

**Status:** fixed (client-side), 2026-07-25
**Report:** "When feedback for a user is 'closed' it should be hidden from the number icon on the feedback button. I still see 150+ feedback items but most are closed."

## Root cause

The number pill on the feedback FAB (`mobile/src/components/FeedbackFAB.tsx`)
rendered `items.length` — every locally stored note in `useFeedback`,
regardless of lifecycle status. The badge predates operator statuses (its
original meaning was "notes pending export"), so nothing ever aged out of it.

Two compounding gaps:

1. **No status filter.** Closed notes (`closed: true` — shipped/declined or
   no longer served by `/api/feedback/mine`) and resolved-but-visible notes
   (`fixed`) all counted.
2. **Stale statuses.** The FAB only called `hydrate()`; `closed`/`status`
   are derived in `refreshStatuses()`, which only the inbox screen ran. A
   user who never opened the inbox never saw the badge drop.

The backend was already correct: `GET /api/feedback/mine`
(`list_feedback_for_user` in `backend/database.py`) excludes
`FEEDBACK_CLOSED_STATUSES` (`shipped`, `declined`) and returns `fixed`
(so the list can show "Fixed — in next update"). Covered by existing
`backend/tests/test_feedback_status.py`. No server change.

## What the badge counts — before vs after

| Note state | Before | After |
|---|---|---|
| no status yet (unsynced / never fetched) | counted | counted |
| `new` / `planned` / `in_progress` | counted | counted |
| `fixed` | counted | **excluded** (still shown in the inbox list) |
| `shipped` / `declined` | counted | **excluded** |
| `closed` (hidden from list, incl. absent-from-`/mine`) | counted | **excluded** |

Definition: badge = notes still awaiting action = `!closed` AND status not in
`RESOLVED_FEEDBACK_STATUSES` (`fixed`, `shipped`, `declined`). The inbox
LIST is unchanged — it keeps hiding `closed` notes and keeps showing `fixed`
with the "Fixed — in next update" chip.

## Change (all mobile)

- `mobile/src/utils/feedbackBadge.ts` — **new** pure module:
  `RESOLVED_FEEDBACK_STATUSES` + `openFeedbackCount()`. Kept free of runtime
  imports so the regression test can run it under plain node.
- `mobile/src/components/FeedbackFAB.tsx` — badge + accessibility label use
  `openFeedbackCount(items)`; mount effect now chains
  `hydrate().then(() => refreshStatuses())` so operator statuses reach the
  badge without an inbox visit (one best-effort GET per launch; silent-fail).
- `mobile/src/api/feedback.ts` — cross-reference comment only
  (`CLOSED_FEEDBACK_STATUSES` ↔ `RESOLVED_FEEDBACK_STATUSES`).
- `mobile/tests/check-feedback-badge.js` — **new** regression test (7 checks)
  run via `npm run test:feedback-badge` (`mobile/scripts/` is gitignored, so
  the test lives in tracked `mobile/tests/`; pattern mirrors
  `test:contrast`). Pins the resolved-status vocabulary and every counting
  rule above, and fails loudly if the pure module gains a runtime import.
- `mobile/package.json` — `test:feedback-badge` script.

No route contract changed → no `docs/api-reference.md` update.

## Verification

- `node mobile/tests/check-feedback-badge.js` — 7/7 checks pass.
- `npx tsc --noEmit` (mobile) — clean.
- `python3 -m pytest backend/tests -q` — baseline green (backend untouched);
  see final report for the exact line.
