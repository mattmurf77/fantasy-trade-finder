# FB-419 — rejected interest resurfacing

**Status:** in_progress · 2026-09-06 · `codex/feedback-419-421-20260906`

G419: prevent an exact rejected offer from resurfacing as current counterparty interest. Independent planner approved `481b1809`; root reviewed and integrated backend `e02d074e` and mobile `396d92fc`/evidence `6838fe0f`. Focused root checks passed (401 backend, 28 mobile cases), followed by all 95 combined mobile guards, TypeScript and testID lint. Full batch independent QA/CI/release remain pending; production status remains in_progress. [Batch plan](plan.md), [backend evidence](build-evidence.md), [mobile evidence](mobile-build-evidence.md), [research-only all-45 audit](open-backlog-audit.md). Physical TestFlight is unrun.

Round 1 on `aa463789` found an old same-ID pass incorrectly coalesced into a fresh reason episode after renewed partner interest. Both independent reviewers identified the code path; root reproduced it through the real route with isolated synthetic data. Returned to the backend owner for repair; release is held and a full new redundant QA round follows the fix. [Release gates](release.md).
