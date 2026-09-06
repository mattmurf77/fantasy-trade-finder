# Status — web-parity

```project-status
{
  "status": "built-unmerged",
  "updated": "2026-09-02",
  "summary": "web parity",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: **Phases 0-2 + P2-3 built; in PR #263** · 2026-09-02 **Phases 0-2 + P2-3 built; in PR #263** · 2026-09-02 — Bringing the website up to par with the mobile app. Evidence base is [`../reviews/2026-08-19-web-parity-audit.md`](../../reviews/2026/2026-08-19-web-parity-audit.md). **Phase 0** (live-user breakage, incl. the analytics flag race [G-067](../../../living-memory/GOTCHAS.md)), **Phase 1** (one token source, SEO/a11y, and `qa/web/check_web_structure.py` — the first CI job that touches `web/`), **Phase 2** (session-gated calculator + market pulse) and **P2-3** (the landing below-the-fold, link-free) are all built. Posture is settled: **B, Companion** ([D-173](../../../living-memory/DECISIONS.md)) — Phase 3 stops at 3a. **Still open:** D2/D3 (D3 = bundle+minify, the biggest perf lever left), and waivers `scope.md` §6 W1/W2 (standing decisions) plus **W6/W7 — P2-3's app CTA and screenshots both need operator input that does not exist in the repo yet** (no TestFlight/App Store link anywhere; `screens/` frozen at 2026-08-11). Phase 4 (SEO content loop + site-wide app promotion) is specced, unstarted.. Prior row preserved at ../../reviews/2026/2026-09-06-project-status-migration/plans-index.md."
}
```
