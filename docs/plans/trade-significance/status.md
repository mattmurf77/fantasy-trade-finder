# Trade significance — implementation status

```project-status
{
  "status": "built-dark",
  "updated": "2026-09-17",
  "summary": "Shared significance gate merged as PR #297; default off, activation unverified",
  "evidence": "PR #297 merged as b33b4da9 on September 17 and is the incoming main commit; built-unmerged in the earlier local record is superseded. validation.md reports 6,058 backend passes / one skip, 195 web checks and test-ID lint; calibration.md preserves the frozen replay. significance_mode defaults to 0. No observed deployment, production activation or physical-device evidence is recorded here. The shared rule does not change which generator arm serves; outstanding calibration/activation gates remain."
}
```

See [scope](scope.md), [calibration](calibration.md), and [validation](validation.md). This initiative does not alter which arm serves recommendations. PR #297 is merged; the older local-only statements in validation.md are historical. Recorded production activation and remaining calibration evidence are still separate gates. Production remains a separately verified operational state, not a claim derived from this plan.
