# Status — personal-market-policy

```project-status
{
  "status": "built-dark",
  "updated": "2026-09-04",
  "summary": "personal market policy",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: **built, DARK** · 2026-09-04 **built, DARK** · 2026-09-04 — Consensus becomes a **non-bypassable market guardrail** and two-sided personal opportunity becomes the ordering signal ([D-180](../../../living-memory/DECISIONS.md)), tested as an **orthogonal** `policy_variant` dimension rather than a fourth generator arm ([D-181](../../../living-memory/DECISIONS.md)). New leaf `backend/trade_policy.py` called by v2, v3 and one server-side choke point on the final deck, so sweeteners / relaxed fallback / likes-you / wildcards / replenishment stop being separate bars. Adds symmetric ranking confidence to `member_rankings`, a frozen `deck_impressions.valuation_json`, a canonical `trade_concept_id`, and the `trade_proposals` + `trade_policy_shadow` tables. **Both flags default false in code and in `config/features.json`; nothing enabled, nothing deployed, no production migration run.** [scope](scope.md) · [code-walk](code-walk.md) · [TestFlight checklist](testflight-checklist.md) (written, not yet run). Open: [Q-038](../../../living-memory/OPEN_QUESTIONS.md) — the policy and the generators judge \"both managers gain\" on two different value bases.. Prior row preserved at ../../reviews/2026/2026-09-06-project-status-migration/plans-index.md."
}
```
