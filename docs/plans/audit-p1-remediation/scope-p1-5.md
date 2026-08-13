# Feature Scope — P1-5 · Promote and measure the league invite (audit A-14)

<!-- Copied from docs/templates/feature-scope.md. Every section is answered or
     explicitly WAIVED with a reason. Silence is not a waiver. -->

**Date:** 2026-08-11
**Entry point:** mobile UX audit finding **P1-5 / A-14** (`docs/business/product/2026-08-09-mobile-ux-audit/04-priority-backlog.md` §P1 row 5; `06-resolutions.md` row A-14) — routed through the P1 audit-remediation round, not the feedback pipeline.
**Builder:** planning agent (plan only, no code) — build agent TBD, wave-assigned by the orchestrator.
**Plan:** [`plan-p1-5.md`](plan-p1-5.md)
**Worktree/branch:** `ftf-p1-remediation` @ `ab9368f`, branch `p1-remediation-2026-08-11`
**Gate posture:** **FULL GATES.** `CLAUDE.md` §Conventions bright line — *"a change touching schema, API contracts, feature-flag surfaces, or **analytics events** is not a quick fix."* This item registers analytics events. Express is not available and was not offered; agents never self-select it.
**Hard prerequisite:** **P0-3 must be merged to `main` before this build starts.** See plan §P0-3 dependencies. Do not begin until `origin/main` contains it.
**Operator sign-off on waivers:** **REQUIRED — pending.** Waivers are listed in §6 below; operator checkpoints OC-1 … OC-11 are in the plan and must be answered before build.

---

## 1. Analytics scope

**(a) New events specced.** ✅ — this is the bright line the item crosses.

Naming convention per tracking plan v2 §S3: `object_action`, snake_case, past tense.

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `invite_cta_shown` **(new)** | `surface` str ∈ `league_home\|matches_empty\|trades_banner\|members_overlay`; `not_joined` int\|null; `total_mates` int\|null; `platform` str ∈ `sleeper\|espn\|mfl\|fleaflicker\|unknown` (**LEAGUE** platform) | Once per surface mount, `firedRef`-guarded, only after the league summary settles **and** the CTA actually rendered | mobile |
| `invite_cta_tapped` **(new)** | same four | First statement of `shareInvite()`, **before** the OS share sheet opens — so an abandoned sheet is still counted | mobile |
| `invite_shared` **(existing name, currently dropped)** | `league_id` (existing) + the four above | Share sheet resolves with `res.action !== Share.dismissedAction` — unchanged semantics from `InviteLeaguematesBanner.tsx:46` | mobile |

**Critical registration facts, verified in this worktree on 2026-08-11:**

- `invite_shared` is **not** in `ALLOWED_CLIENT_EVENTS` (`backend/analytics_taxonomy.py:38-99`, read in full; `grep -n "invite" backend/analytics_taxonomy.py backend/analytics_queries.py` → **zero matches in either file**). Ingest is **default-deny** and returns **200** on a drop, so the only invite event in the product has been silently discarded since it shipped. **There is no invite baseline.**
- **P0-3 B4 registers `invite_shared`.** P1-5 must therefore **extend that event's `CLIENT_EVENT_PROPS` row**, not re-add the name. Unknown props are **stripped silently** — a name that lands with no props is the failure mode this item must not repeat.
- **Ordering:** the taxonomy commit merges **and deploys** before any client `track()` ships. Verified between phases by a hand-rolled `POST /api/events` + `GET /api/analytics/health` (`dropped_unknown_type` flat).
- **`invite_cta_shown` MUST be added to `analytics_queries.NON_INTENT_EVENTS` (`:60-63`).** `INTENT` is a **deny-list** (`:64`), so taxonomy growth is intent-by-default; an impression event left in INTENT would step-change DAU/WAU on ship day and break every retention/churn series at that seam. `invite_cta_tapped` and `invite_shared` stay INTENT.
- **`platform` here is the LEAGUE platform**, matching the `league_selected` precedent (`analytics_taxonomy.py:185`). Device platform is a server-derived **column** on `user_events` — the NULL-`platform` incident. No event in this item carries a device-platform prop; a test pins that.
- **No reserved canonical name exists in code** for invites: `WAT_LIVE`/`WAT_DARK` (`analytics_queries.py:51-54`), `FUNNEL_STAGES` (`:66-80`), `FEATURE_VERTICALS` (`:83-95`) contain nothing invite-shaped. Tracking plan v2 §S3 (`:78`) reserves `invite_sent` **in prose only** — a fork resolved at **OC-3** (recommendation: keep `invite_shared`, amend the plan doc).

**Follow-through:** `docs/data-dictionary.md` — **not required** (nothing new is *stored*; all three are client-fired and documented via the taxonomy + addendum, as `guide_*` and `draft_room_*` were). Tracking-plan addendum — **required and new**: `docs/business/analytics/2026-08-11-p1-5-addendum.md`, which is the precondition `analytics_taxonomy.py:9-10` demands before any new client event.

**(b) Existing events cover it** — n/a; nothing invite-related currently lands a row.
**(c) WAIVED** — n/a.

## 2. Schema & flag scope

- **New/changed tables or columns: none.** No `backend/database.py` change. `user_events` already stores every event in §1; no migration. `docs/data-dictionary.md` therefore has no trigger.
- **New/changed feature flags: none added.** Justification (`CLAUDE.md` — no new flags unless a bright line demands one): the bright line crossed is *analytics events*, whose remedy is registration + ordering, not a flag. No route, no schema, no contract change. Rollback lever is a revert of a UI-only diff with no data migration.
  - **One flag *read* is removed:** `growth.share_landing` currently gates the `invite_shared` `track()` call (`InviteLeaguematesBanner.tsx:38, 46-48`). Plan step B12 drops that gate so measurement is not flag-gated. **The flag key, its default (`true` in `config/features.json:125`), its entry in `backend/feature_flags.py:272`, the release fixture, and every other read are untouched.** No `FLAG_KEYS` edit, no `config/features.json` edit, no `docs/config-reference.md` trigger. Surfaced rather than assumed because it is a flag-surface touch → **OC-9**.
  - **Flags read but not changed:** `growth.invite_join_link` (P0-3's, default OFF — P1-5 consumes it only indirectly via `buildInviteUrl`); `league.unlock_badges_per_member` (deliberately **not** depended on — see §Design note below); `ux.empty_state_ctas`, `ux.help_surface` (untouched neighbours on the Matches empty state).
- **New env vars / `model_config` keys: none.** No `docs/config-reference.md` trigger. Ship-the-knob: not applicable — the feature has no runtime risk lever beyond revert.

> **Design note recorded here because it is a scope decision, not an implementation detail.** The audit pointed at `load_league_member_unlock_states`, which is real (`backend/database.py:5656-5746`, `"joined": bool` at `:5713`) but is served by a **flag-gated** route (`/api/league/member-unlock-states`, gated on `league.unlock_badges_per_member` at `backend/server.py:13497`). Building a default-ON feature on a flagged route would have created a hidden dependency. The unflagged `/api/league/members` (`server.py:13511`, same loader) carries the same `joined`, and the **aggregate** `leaguemates_total` / `leaguemates_joined` is already on `/api/league/summary` (`database.py:5642-5643`) and **already in scope on both target screens** (`LeagueScreen.tsx:310-311`; `MatchesScreen.tsx:385-397`). Zero new requests.

## 3. Test scope (mobile test platform)

- **New flow:** `mobile/.maestro/flows/growth/invite-promotion.yaml` (`# flags: release`) — four blocks: (1) League Home card + the real `9 of your 11` string on the `standard` fixture; (2) **duplicate suppression** — `league.progress-invite` asserted **absent** while the card is up; (3) Matches empty-state invite block; (4) **ESPN gate** — card absent, legacy inline link present, on the `espn` fixture.
- **Extended flow:** none. **`grep -rn "invite" mobile/.maestro/` returns zero hits** — no existing flow asserts any invite affordance, so none is asserting the bug being fixed and none needs correcting.
- **WAIVED:** nothing waived in this section.
- **Deliberate automation boundary (not a waiver):** the OS share sheet is **not** driven. Tapping the CTA opens system UI whose dismissal is the same hazard class as README law 17 (SpringBoard confirm) and law 20 (native overlay poisoning). Flows assert up to and including the CTA; the sheet → `invite_shared` leg is verified by the end-to-end `user_events` row check and manual sim QA (plan Test 8, Test 17).
- **`testID`s added:** `league.invite-card`, `league.invite-social-proof`, `league.invite-cta`, `matches.invite-social-proof`, `matches.invite-cta`, plus `league.members-invite` **only if OPTIONAL-M (OC-7) ships**. All static string literals ⇒ `mobile/scripts/testid-lint.sh` clean, no `testid-lint-allow.txt` entry needed. **None renamed or removed** — `league.progress-invite` (`LeagueProgressModule.tsx:126, 202`) survives untouched and gains an assert-absent use.
- **Capture delta:** `league`, `league@espn`, `league@near-unlock`, `league@quickset-done`, `league@single-format`, `league@two-leagues`, `matches`, `matches@fresh`, `matches@near-unlock`, `matches@two-leagues`, `matches@espn` — both screens change visually. Run `mobile/scripts/screen-capture.sh --screen league --screen matches`; **never combine `--prune` with a profile filter** (law 21); **eyeball every screenshot** (law 23).
- **Smoke-suite impact:** `flows/smoke/09-league.yaml:34` (waits `league.hero`, which stays above the new card) and `flows/smoke/08-matches.yaml:38` (waits `matches.empty-text`, which stays above the new block). Both must stay green **unmodified** — a diff to either invalidates the claim that this is additive. All 11 run regardless (tier 1).
- **Backend pytest:** `backend/tests/test_events_api.py` — new `test_p1_5_invite_events_accepted` (full prop sets; `dropped == 0`; exact `set(by_type)`; **`invite_shared`'s four new props survive** — the prop-stripping guard), a misspelled-name negative mirror, and a bogus-`device_platform` stripping test. `backend/tests/test_analytics_p0.py` — extend `test_live_taxonomy_is_disjoint` membership; assert `invite_cta_shown ∈ NON_INTENT_EVENTS` and `invite_cta_tapped ∉`.
- **Known coverage limit (declared, not hidden):** there is no jest in `mobile/`, so `inviteSocialProof`'s four copy branches (plural / singular-n / singular-total / null) have no unit test. Covered by the Maestro `text:` assertion on the plural case plus manual QA of the singular cases (plan Tests 12–13).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. `/api/league/summary` and `/api/league/members` are consumed exactly as documented; `POST /api/events` accepts new names by registry membership alone, with no envelope change. |
| `living-memory/LLD.md` | **n/a** | No schema/route/invariant *convention* shift. "Register the name, then wire the client" is an existing convention this plan obeys rather than establishes. |
| `docs/architecture.md` | **n/a** | No backend module added, removed, or re-wired; no data-flow change. Every call rides existing paths (`track` → queue → `POST /api/events`). |
| `living-memory/HLD.md` | **n/a** | No architectural shift — no new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **Updated** | §"Client analytics event contract" (`:268-271`) — add the three invite names + the addendum link, and state explicitly that web (`web/js/events.js`) and the extension fire **none** of them so the omission reads as deliberate. That section already warns that changing one side alone breaks ingestion silently; this is exactly that class of change. |
| `docs/glossary.md` | **n/a** | No new domain term. "Invite", "leaguemate", "joined" are already in use; `surface` is an event property, not a domain concept. |
| ADR or `DECISIONS.md` entry | **`DECISIONS.md`, updated** | Two non-obvious choices: (1) the promoted card **suppresses** the existing inline link rather than coexisting with it (one affordance per screen); (2) one `shareInvite` helper owns all four emitters and both events, **layered on top of** P0-3's `buildInviteUrl` rather than merged into it — which retires the two-emitter drift risk P0-3's own risk table names, for four emitters. No ADR: nothing at architecture altitude. |

**Additional docs triggered outside the template's seven rows** (per `docs/CLAUDE.md`):

| Doc | Updated? | Reason |
|---|---|---|
| `docs/business/analytics/2026-08-11-p1-5-addendum.md` | **NEW — mandatory** | The tracking-plan addendum `analytics_taxonomy.py:9-10` requires before any new client event. Records: no invite baseline exists; the `invite_shared`/`invite_sent` fork (OC-3); league-vs-device `platform`; the DAU/WAU seam date; the closed four-value `surface` enum; what is deliberately **not** instrumented (share-sheet channel, per-recipient attribution, invite→install, which needs deferred deep linking FTF does not have). |
| `docs/design/components.md` | **Updated** | New named League Home module `InviteLeaguematesCard` + the Matches-empty invite block. No `design-system.md` change: no new token, colour, radius, or type step — the card composes existing `Card` / `Button` / `TickLabel` primitives, no emoji, no gradient, no blur (ADR-004/005). |
| `docs/config-reference.md` | **n/a** | No flag, env var, or `model_config` key added or changed. Re-check at build **only if OC-9 is declined** and the `growth.share_landing` gate is instead extended to the new events. |
| `docs/data-dictionary.md` | **n/a** | No table or column change; nothing newly stored. |
| `docs/runbook.md` | **n/a** | No new operational lever or failure mode. |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | **On ship** | Per `CLAUDE.md` §Session memory. TEST_LEDGER carries the tier-1 sim run **and** the end-to-end row-landed verification. |
| `living-memory/GOTCHAS.md` | **Conditional** | Only if the end-to-end check surprises. G-017 (paired analytics gates fail silently) already covers the known trap. |

## 5. Ship gate declaration

- **Simulator-gate tier: 1** — `docs/runbook.md:96`, "Mobile screen / navigation / state change". Two screens gain rendered elements.
  Required before merge to `main`: **full smoke suite (11 flows)** + `flows/growth/invite-promotion.yaml` + `mobile/scripts/screen-capture.sh --screen league --screen matches` covering all 11 listed variants.
- **Evidence:** `TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json` written after the run. Enforced locally by `githooks/pre-push` (`git config core.hooksPath githooks`).
- **Additional non-simulator gate, treated as blocking:** the Phase-A → Phase-B deploy gate. The taxonomy commit must be live on Render, and a hand-rolled `POST /api/events` carrying `invite_cta_shown` must return `dropped == 0`, **before** any client `track()` call is written. Failure mode is silent (200 + no row), so this is verified, never assumed.
- **Operator deviation from the matrix:** none proposed. A tier-2 argument exists (the League Home change is one mounted card), and it is rejected: the Matches empty state is a state-conditional layout change on a screen with four capture variants, and A-34's FAB-clipping finding makes bottom-area layout on data-dense screens a live hazard — the captures are the evidence, so tier 1 stands.

## 6. Waivers requiring operator sign-off

| # | Waiver | Reason |
|---|---|---|
| W1 | **`docs/data-dictionary.md` not updated** | Nothing new is stored. All three events are client-fired into the existing `user_events` table and are documented via the taxonomy + tracking-plan addendum — the same treatment `guide_*` and `draft_room_*` received. |
| W2 | **The OS share sheet is not covered by Maestro** | System UI; dismissal is the hazard class of README laws 17 and 20. Replaced by an end-to-end `user_events` row check and explicit manual QA (plan Tests 8, 17), not dropped. |
| W3 | **No unit test for `inviteSocialProof`'s singular branches** | No jest in `mobile/`. Covered by one Maestro `text:` assertion (plural) + manual QA (singular). Declared as a real limit. |
| W4 | **The copy A/B named in `06-resolutions.md` is deferred** | `experiment_exposed` is in `FUNNEL_CRITICAL` and the mobile SDK mirror but **not** in `ALLOWED_CLIENT_EVENTS`, so exposure is unmeasurable and any read is arm-correlated-diluted (P0-7 §6-F1). Ship one variant, register the events, queue the A/B behind that fix → **OC-10**. |
| W5 | **No pre/post lift can be reported** | `invite_shared` has never landed a row, so there is no baseline. Post-ship reads are absolute, not comparative. Stated in the addendum so no dashboard implies a before/after that does not exist. |
| W6 | **Cross-platform (ESPN/MFL) invites remain unsolved** | Inherited from P0-3, which records it explicitly. P1-5's response is to *withhold the promoted CTA* on those leagues (**OC-4**) rather than scale a dead end. Not fixed here; not hidden. |

## 7. Operator checkpoints (must be answered before build)

Full options + recommendations are in [`plan-p1-5.md` §Operator checkpoints](plan-p1-5.md#operator-checkpoints). Summary of recommendations:

| # | Decision | Recommendation |
|---|---|---|
| OC-1 | Social-proof copy / framing | Factual-self-interested ("9 of your 11 leaguemates haven't joined yet") |
| OC-2 | Matches empty-state hierarchy | "Find a trade" stays primary; Invite is secondary beneath it |
| OC-3 | `invite_shared` vs tracking-plan `invite_sent` | Keep `invite_shared`; amend tracking plan v2 §S3 to runtime |
| OC-4 | ESPN / non-Sleeper gate | Gate the promoted card to Sleeper; legacy inline link stays elsewhere |
| OC-5 | Suppress the inline link when the card renders | Yes — one affordance per screen |
| OC-6 | Ship `invite_cta_tapped` | Yes — it is the share-sheet abandon rate |
| OC-7 | OPTIONAL-M members-overlay invite | Yes — ~8 lines on the surface that already names the un-joined |
| OC-8 | Zero-not-joined state | Card absent; the hero chip already shows `{joined}/{total} joined` |
| OC-9 | Drop the `growth.share_landing` gate on `invite_shared` | Yes — measurement should not be flag-gated |
| OC-10 | Defer the copy A/B | Yes — ship measurable, queue the A/B behind P0-7 F1 |
| OC-11 | Wave sequencing / file ownership | P0-3 → P0-7 → P1-5; one owner for `LeagueScreen.tsx` across P0-7/P1-5 |
