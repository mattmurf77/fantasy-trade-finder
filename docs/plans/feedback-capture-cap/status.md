# Status — feedback-capture-cap

```project-status
{
  "status": "in-progress",
  "updated": "2026-08-22",
  "summary": "feedback capture cap",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: **active, not merged** · 2026-08-22 **active, not merged** · 2026-08-22 — Feature scope for the in-app feedback note cap raise (2000 → 8000) and the silent-loss fix that went with it: character counter, length-gated Save, and a draft that survives a failed sync. No flag — the cap is a constant in `backend/server.py`, mirrored as `FEEDBACK_TEXT_MAX` in `mobile/src/api/feedback.ts` and pinned across the two by `mobile/tests/check-feedback-capture.js`. Built on `claude/new-user-feedback-d4c47d` by three parallel agents; not yet merged to `main`. Two operator waivers in §6; the TestFlight checklist in §3 is outstanding.. Prior row preserved at ../../reviews/2026/2026-09-06-project-status-migration/plans-index.md."
}
```
