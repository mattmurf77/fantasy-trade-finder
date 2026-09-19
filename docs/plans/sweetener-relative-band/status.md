# Status — sweetener-relative-band

```project-status
{
  "status": "built-unmerged",
  "updated": "2026-09-02",
  "summary": "sweetener relative band",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: **built, unmerged** · 2026-09-02 **built, unmerged** · 2026-09-02 — The #414 gap-sweetener fix behind two `model_config` knobs, both default 0 = byte-identical (goldens vs `origin/main` @ `e16bb487`): `sweetener_gap_frac` makes `close_value_gap`'s trigger `max(absolute threshold, frac × the richer side)` — the flat 1,539 left the sweetenable window `(1539, 0.25·H)` empty below H ≈ 6,156, so the served London-for-CeeDee 1x1 (gap 1,396 = 19%) passed R1 and was never sweetened; `sweetener_best_effort` replaces the all-or-nothing closer with \"attach the gate-passing piece that leaves the tightest gap\" (strictly narrower, richer side unchanged, stamped `gap_sweetener.partial`), because a threshold cut alone is a measured regression. Live triple recommended (750 / 0.12 / 1) with the threshold lowered by PUT. [scope](scope.md) · [code-walk](code-walk.md) · [results](results.md) · harness `measure_sweetener.py`. Arm A pins both identities. Built on `claude/sweetener-relative-band`; the lead ships.. Prior row preserved at ../../reviews/2026/2026-09-06-project-status-migration/plans-index.md."
}
```
