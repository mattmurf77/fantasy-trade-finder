# League projections: implementation scope

Date: 2026-11-06. Entry: direct user handoff to Review Fantasy Trade Finder.
Builder: projection capability agent. No waivers.

The user requested a read-only app capability for playoff likelihood and non-playoff draft order. This is an advisory sidecar; existing trade models, outlooks, Win Now and provider behavior remain unchanged.

## Analytics
Existing `screen_view` records entry; existing API observability records requests. Durable run states and reasons describe completion/coverage without collecting new interaction events. No new analytics events.

## Schema and flags
Viewer-owned `league_projection_runs` and `league_projection_targets` tables store immutable normalized inputs, configuration, version/hash, status and results. Account deletion/export includes this table. Bounded queued work takes the existing live-user row fence. New flags `league.projections` and `league.projections_provider_approved` default false everywhere. The former controls entry/routes; the latter is a technical rollout gate specific to new provider ingestion; the user has authorized using current Sleeper data. It has no effect on existing Sleeper functionality. No new environment variables/model knobs.

## Evidence
Pure engine tests cover Decimal scoring, exact assignment against exhaustive search, locks, negative points, narrowly scoped IDP bye replacements, shared-world playoff/draft invariants, deterministic seeds, missing policies and inputs. API/store tests cover authentication, queue bounds, cancellation, ownership and account deletion. A dependency-free mobile structural guard pins navigation/flag boundaries and shared API usage. Code walk and manual TestFlight checklist are in evidence.md; no simulator/Maestro.

## Documentation
API reference: new run/read/cancel/export contracts. Data dictionary: run table. Architecture/HLD/LLD: immutable asynchronous advisory sidecar. Cross-client invariants: same run results, probabilities and explicit scenarios. Glossary: Max PF, conditional expected pick. Decision: use labeled best-available source contributions while refusing malformed identities and genuinely unsupported rules; runtime flags control release. These are additive sections, preserving existing behavior.

## Ship gates
Backend tests, mobile typecheck, structural guards, test-ID lint, independent review and recorded TestFlight checks. Parent owns PR, CI, merge and deployment. No claims of provider accuracy, original prototype parity or device proof without evidence.

## Confirmed vs proposed
Confirmed: custom scoring including IDP, exact lineup eligibility, official historical Max PF, joint worlds, traded-pick ownership, expected and modal W-L-T, explicit coverage, readonly advisory behavior, 60% historical / 40% projection baseline and 40/60/80 comparison controls.
Proposed and visible scenario inputs: 250000 full simulations, 100-sample conditional-pick threshold, 5-point persistent strength SD, same-week residual correlation, IR eligibility, reserve activation, empty slots, tie handling. Unsupported divisions/median/manual seeding and live remaining-projection coverage block numeric results. IR behavior and original November 6 fixtures were not established by the handoff. Missing forecast fields now produce labeled partial estimates under the later user instruction, not automatic whole-league refusal.

The later confirmed weekly-only scheduled delivery instruction supersedes manual baseline generation: see steering-addendum.md. New targets wait until the next configured weekly slot; stored GETs never dispatch work. Explicit comparison scenarios remain separate.

The v3 mathematical correction preserves the specified expected Max PF mean while enforcing eligible dominance. It changes the joint distribution under a new policy/model version, leaves actual-score draws unchanged, and remains uncalibrated/default-off. Negative dominance gaps fail; old-model saved-input comparisons require a current weekly baseline.

The v4 continuation implements the latest best-available-source instruction and completed-game conditioning. See steering-addendum.md and implementation.md for accepted incomplete-source behavior and unchanged weekly scheduling.

## Live release and initial baseline preparation — 2026-11-07

The operator requested actual activation. The model-policy file is approved while both runtime flags remain false in repository defaults. The existing authenticated isolated cron gains a bounded operator-only initial mode for currently connected targets with no prior baseline attempt. The select and claim enforce that condition, and durable enqueue atomically schedules the next weekly refresh. No new tables, analytics or account impersonation. A first baseline can therefore be prepared during rollout without turning views or ordinary new-league registration into computation triggers. API/config references, implementation/addendum, rollout instructions and lifecycle/auth regressions are updated.
