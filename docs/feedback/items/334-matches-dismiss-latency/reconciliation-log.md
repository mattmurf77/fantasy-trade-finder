# G9 reconciliation log — #334 + #335

> Dual-agent review rounds per the feedback pipeline. Author = G9 author
> agent; Critic = planner agent. Docs under review: `prd.md` + `scope.md`.

## Round 1 (2026-08-16, [`review-round-1.md`](review-round-1.md))

Critic's independent verifications: seventh-repopulation-path hunt (none
found — P1–P6 confirmed exhaustive), the author's four §V plan-corrections
(all confirmed), pin-range cites, mounted-tab premise, Chalkline reads, and
scope waivers W-1/W-2 — all affirmed. Objections and dispositions:

| ID | Objection (summary) | Disposition | Where |
|---|---|---|---|
| B-1 | R-2's accepted-flicker rationale cited the wrong mechanism (backend `retracted_at` filter governs only post-commit GETs); real residual window = a GET racing the POST's commit, resurrecting the row for one round-trip after a bare `onSettled` unhide | **Adopted in full.** R-2 respecced: `onError` unhides immediately; `onSuccess` unhides only after `await queryClient.invalidateQueries(...)` resolves (promise settles even on refetch failure → no-permanent-hide guarantee holds); the wrong "backend filter makes it impossible" sentence retracted. S-10c re-pinned to the ordering with the named sabotage **"unhide before await"** — exactly the pre-fix ordering, so the pin fails RED on it; RED run to be recorded in QA notes. CW-1 gains trace step (d) for the ordering | prd.md R-2, R-5, S-10c, CW-1(d), §V |
| NB-1 | R-3 mis-described the cancelled-P6 consequence: `decide(false)` → `v2ShowN61(false)` shows the N6.1 bubble **now** (router-less copy variant); nothing defers | **Adopted.** Author re-verified `TradesScreen.tsx:3252-3268` — critic correct. R-3 corrected so CW-1 doesn't inherit the wrong description; same benign conclusion | prd.md R-3 |
| NB-2 | Dismiss → app-background/kill during the undo window unspecced | **Adopted as declaration, not behavior change.** R-4 now states: backgrounded mid-window → POST fires on resume (hidden tile persists); killed before resume → POST never sent, row honestly returns next launch. Shipped #318/S3-PRD-03 semantics, unchanged, out of scope; `AppState → 'background'` flush named as the future hardening (orchestrator's call, not absorbed into G9) | prd.md R-4 |
| NB-3 | Undo racing the flush timer (no-op after flush, `:358-361`) and undo's snapshot-restore overwriting a fresher mid-window refetch — both silent in the contract | **Adopted.** Both declared in R-4 as pre-existing, frame-level / next-refetch-bounded, unchanged | prd.md R-4 |
| NB-4 | CW-1 rested on the mounted-tab premise alone | **Adopted.** CW-1 gains the unmounted-tab dual (f): unmount cleanup flushes the POST first (`:374-377`), so lost `hiddenKeys` state is harmless; proof robust to future navigation-config changes | prd.md CW-1(e)(f) |
| NB-5 | "No focus refetch" rests on `refetchOnWindowFocus: false` while the focusManager IS AppState-bridged (`App.tsx:211-216`) — pin it | **Adopted.** New structural pin S-10e: default stays `false` and neither query overrides it | prd.md S-10e |
| NB-6 | Cosmetic cite drifts: `match_dismiss_undone` at `:365` not `:363`; `fonts.data` at `chalkline.ts:92` not `:93` | **Half-accepted / half-rejected with evidence.** Accepted: scope.md fixed to `:365` (verified). Rejected: the `fonts` block spans `chalkline.ts:86-95`; `:92` is `uiBold`, `:93` is `data:` — the PRD's original `:93` cite stands (critic's own §-verifications line repeated the `:92` error) | scope.md §1; prd.md §V note |

**Round-1 outcome:** all blocking and non-blocking items resolved; one
critic cite-claim rejected with line-level evidence. No path upgrade —
client-only Polish stands. Docs updated: `prd.md` (R-2, R-3, R-4, R-5,
S-10c, S-10e, CW-1, §V), `scope.md` (§1 cite, §3 test-scope bullet).
**Ready for round 2 / critic sign-off.**
