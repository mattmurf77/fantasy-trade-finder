# Feature Scope — P0-3 · Invite loop (deep-link join route + referred sign-in)

<!--
Copied from docs/templates/feature-scope.md. Every section answered or explicitly waived.
Full gates apply: this change adds a deep-link route, a server route, and an API route.
Operator confirmed full gates for this build (no express lane).
Design detail: docs/plans/audit-p0-remediation/plan-p0-3.md
-->

**Date:** 2026-08-10
**Entry point:** mobile UX audit finding **P0-3** — `docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md` §P0-3
**Builder:** planning agent (P0-3), worktree `ftf-p0-remediation`, branch `p0-remediation-2026-08-10`
**Operator sign-off on waivers:** **required** — two waivers below (§3 Maestro block 3 conditional on harness change M12; §1 no server-fired events)

---

## 1. Analytics scope

**(a) New events specced.** The taxonomy is default-deny
(`backend/analytics_ingest.py:376`), and `invite_shared` — already fired at
`mobile/src/components/InviteLeaguematesBanner.tsx:47` — is **not** registered in
`ALLOWED_CLIENT_EVENTS` (`backend/analytics_taxonomy.py:34-99`), so it is being dropped
today. Registration lands and deploys **before** any client call ships.

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `invite_shared` *(backfill — existing call, currently dropped)* | `league_id` | Share sheet returns a non-dismissed action from the invite CTA | mobile |
| `invite_link_opened` | `league_id`, `has_ref` (bool), `format` (`legacy` \| `path`), `auth_state` (`signed_out` \| `authed_member` \| `authed_non_member`) | An invite URL is parsed — either the `/app/league/join/:id` route or a legacy `?league=` URL | mobile |
| `invite_league_pinned` | `league_id`, `source` (`join_screen` \| `picker_autopin`), `ms_since_open` | The invited league becomes the active league | mobile |
| `invite_pin_failed` | `league_id`, `reason` (`not_member` \| `session_init_failed` \| `expired`) | The intent could not be honoured | mobile |

No PII: no usernames in properties (`ref` is reduced to `has_ref`), no league names.
`invited_by` continues to travel on `/api/session/init` as it does today
(`mobile/src/api/auth.ts:406, 490`), not as an analytics property.

Follow-through: `docs/data-dictionary.md` **not** required (no new stored columns — these
land in the existing `user_events` / analytics ingest path); tracking-plan addendum under
`docs/business/analytics/` **is** required, including the note that `invite_shared` has
been silently dropped since it shipped.

**Waiver:** no server-fired events. The whole loop is client-observable and the server
already records `invited_by` on user insert; adding a server-fired duplicate would
double-count. *Reason recorded; operator sign-off requested.*

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** The invite intent
  (`{leagueId, invitedBy, ts}`) is client-side `AsyncStorage` under `ftf_invite_intent`,
  mirroring web's `localStorage` keys `ftf_invited_by` / `ftf_invited_league`
  (`web/js/app.js:5832-5833`). No migration. `docs/data-dictionary.md`: n/a.
- **New/changed feature flags:** `growth.invite_join_link` — **default OFF**.
  Registered in `backend/feature_flags.py` `FLAG_KEYS`, `config/features.json`, and
  `backend/tests/fixtures/flags/release.json`; documented in `docs/config-reference.md`.
  - *Gates:* only the **emitter** (`buildInviteUrl`). OFF ⇒ byte-identical legacy URL.
  - *Does not gate:* the mobile `?league=` reader, the `LeagueJoin` route, the AASA claim,
    or the server 302 — all additive, and all must be live before a new-format link exists.
  - *Graduation criterion:* AASA deployed and verified by an external validator, ≥24h of
    CDN propagation elapsed (`docs/runbook.md:410-412`), and a TestFlight build installed
    **after** that deploy demonstrably opens the app on a tapped `/app/league/join/...`
    link. Then flip ON in `config/features.json`.
  - *Deploy-free rollback lever:* flip the flag OFF — invites immediately revert to the
    legacy URL, which both clients still parse. The route, the redirect and the AASA claim
    stay live and harmless.
- **New env vars / `model_config` keys:** **none.**

## 3. Test scope (mobile test platform)

- **New flow:** `mobile/.maestro/flows/league/invite-join.yaml` (`# flags: release`) —
  three blocks:
  1. authed invitee who **is** a member → `LeagueJoin` interstitial → tabs with the
     invited league active;
  2. authed invitee who is **not** a member → LeaguePicker with the honest notice;
  3. **signed-out** invitee → SignIn with the inviter named.

  Entry is by launch argument, never `openLink` — deep links are dead in this harness
  (`mobile/.maestro/README.md:140-146`, `mobile/src/utils/testRouteEntry.ts:14-18`):
  `launchApp: { clearState: false, stopApp: true, arguments: { FTFTestRoute: LeagueJoin, FTFTestRouteParams: 'leagueId=<id>&ref=qa_inviter' } }`
  (params are a **query string**, never JSON).

- **Extended flow:** none. `flows/smoke/01..11` cross `SignIn` and `LeaguePicker` but
  create no invite intent, so the new banner/notice never render in them — verified by
  running the full suite, not assumed.

- **WAIVED (conditional):** block 3 requires harness change **M12** — extending the
  launch-arg entry to a signed-out boot for the single route `LeagueJoin`
  (`RootNav.tsx:341` currently applies it only when `initialRoute === 'Main'`; still
  inside the build-time `IS_TEST_BUILD` gate, `testRouteEntry.ts:33-56`). **If the
  operator declines M12,** block 3 is waived and the signed-out banner is covered by a
  screen-library capture of `SignIn` under a seeded invite intent plus manual TestFlight
  QA — recorded as a known coverage gap. *Operator decision required.*

- **`testID`s added:** `leaguejoin.root`, `leaguejoin.title`, `leaguejoin.not-member`,
  `leaguejoin.cta`, `signin.invited-banner`, `leaguepicker.invite-notice`
  (must pass `mobile/scripts/testid-lint.sh`).

- **Capture delta:** `signin`, `leaguepicker`, and the new `leaguejoin` screen — run
  `mobile/scripts/screen-capture.sh --screen <x>` per `docs/runbook.md` § Screen library.

- **Smoke-suite impact:** all 11 flows cross the touched screens (`SignIn`,
  `LeaguePicker`, `RootNav`); all 11 run as part of the tier-1 gate below.

- **Backend pytest:** `backend/tests/test_invite_links.py` (new) — AASA payload contains
  `/app/league/join/*` and still claims the four existing patterns and never `/`
  unqualified; the 302 with and without `ref`, with encoding of hostile league ids;
  `invite-meta` name resolution for Sleeper ids, `null` for non-Sleeper, no session
  required, no `leagues`-table read; the four invite event names accepted by
  `POST /api/events`; `growth.invite_join_link` present in `FLAG_KEYS` and default false.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **yes** | Add `GET /api/league/invite-meta` (league section) and `GET /app/league/join/<league_id>` (share/static section, near `/s/trade/<match_id>` at `:545`); **amend the AASA row at `:587`**, which enumerates the claimed paths and would otherwise be wrong |
| `living-memory/LLD.md` | **yes** | Convention: deep-link destinations reachable while signed out belong on the **root** stack, never inside `Main` (a link resolving into `Main` drops a session-less user into empty tabs) |
| `docs/architecture.md` | n/a | No module wiring or data-flow change — one screen, one parser branch, two read-only routes |
| `living-memory/HLD.md` | n/a | No architectural shift; no new module or client |
| `docs/cross-client-invariants.md` | **yes** | The invite-URL format is a two-client contract: mobile emits, web + mobile parse. Record both accepted formats and the rule that `/?league=&ref=` is parsed **forever** (already-shared links) |
| `docs/glossary.md` | **yes** | "Invite intent" — the persisted `{leagueId, invitedBy}` pair awaiting a pin |
| ADR or `DECISIONS.md` entry | **yes** | `DECISIONS.md`: why the legacy query format stays parsed indefinitely; why the web fallback is a 302 into the existing landing rather than a new web page (`web/js/app.js:589-601` already completes the journey) |
| `docs/config-reference.md` | **yes** | New flag `growth.invite_join_link` — default, what it gates, graduation criterion |
| `docs/runbook.md` | **yes** | Extend the AASA section (`:410-412`) with the ship ordering: deploy AASA → validate → wait for CDN → ship build → then flip the flag |

### 4.1 Execution record — W3-DOCS, commit 14 (2026-08-11)

> Row-by-row closure of the table above, per the feature-gate contract. **IDs are `hld.md` §7 / §10.4's**, which supersede any `D-011` / `G-013` written above — root `CLAUDE.md`'s next-ID columns were stale when these scope blocks were authored (they have since been changed to "max existing + 1 — grep first", so the trap is closed at the source).

| Row | Status | Where it landed |
|---|---|---|
| `docs/api-reference.md` | **updated ×3** | New § League row `GET /api/league/invite-meta` (with the privacy contract verbatim from the landed docstring); new § Profiles + Sharing row `GET /app/league/join/<league_id>` (302, relative Location, closed param contract, 302-not-301); AASA row amended to list `/app/league/join/*`, the matcher-ordering rule, and the deliberate non-claim of `/app/*`. |
| `docs/config-reference.md` | **updated** | New § *Flags — P0 remediation (2026-08-11)* with `growth.invite_join_link`: default false, emitter-only, what it explicitly does **not** gate, the AASA-ordering rationale, the three graduation criteria, and rollback. TOC updated. |
| `docs/cross-client-invariants.md` | **updated ×2** | New § *Invite URL format — a two-client contract* (both accepted forms, "legacy parsed forever", the optional `ref` and why the AASA matcher must match on `league` alone, the ordering rule); the four invite event names added to § Client analytics event contract with the web/extension non-emission stated. |
| `docs/runbook.md` | **updated** | § Universal Links AASA extended with the seven-step ordering, including "if steps 2-5 fail, leave the flag OFF indefinitely" and why that costs nothing. |
| `docs/glossary.md` | **updated** | **invite intent** — blob shape verified against `useSession.ts` (`{leagueId, invitedBy, leagueName, ts}`, `ftf_invite_intent`, 14-day TTL evaluated on read). |
| `living-memory/LLD.md` | **updated** | Root-stack rule for signed-out deep-link destinations; imperative flag reads in shared emitters. |
| `living-memory/DECISIONS.md` | **updated — D-028** | As specified. |
| `living-memory/GOTCHAS.md` | **updated — G-033** (additive) | The `vcr_misses` rail and the single-call-site rule that keeps `invite-meta` off it. |
| `living-memory/NEXT.md` | **updated** | Item 0g — `invite_shared` not fired from `LeagueScreen.tsx`'s invite module. |
| `living-memory/CHANGELOG.md` | **updated** | Batch H2, P0-3 bullet — names the web-already-parsed finding. |
| `docs/architecture.md` · `living-memory/HLD.md` · `docs/data-dictionary.md` · `living-memory/DEPENDENCIES.md` | **n/a — confirmed** | As stated above. |
| `docs/business/analytics/2026-08-11-p0-7-addendum.md` | **not W3-DOCS** | Owned by `W0-TAX`; verified present. |

**Not executed, and why:** `screens/CLAUDE.md` + `screens/manifest.json` re-capture rows are **deferred** — the renamed/new frames require a run of `mobile/scripts/screen-capture.sh` against the simulator, which `W3-QA` holds for the sim gate. Writing index entries for PNGs that do not exist would make the manifest lie. Tracked for the capture pass. `living-memory/TEST_LEDGER.md` is owned by `W3-QA` and is deliberately untouched here.

## 5. Ship gate declaration

- **Simulator-gate tier:** **Tier 1** — mobile screen + navigation + state change
  (new root-stack screen, new route table entry, `RootNav` registration, `SignInScreen`
  and `LeaguePickerScreen` changes). Required: full smoke suite (11 flows) + the new
  `flows/league/invite-join.yaml`, plus `mobile/scripts/screen-capture.sh --screen` for
  `signin`, `leaguepicker`, `leaguejoin`.
- **Evidence:** `living-memory/TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json`
  written after the run. Backend leg: `python3 -m pytest backend/tests/ -q`; mobile leg:
  `cd mobile && npx tsc --noEmit` (no jest in `mobile/`).
- **Operator deviation from the matrix:** none requested.
- **Ship ordering (non-negotiable, and outside the sim gate):** backend (AASA + 302 +
  `invite-meta` + taxonomy + flag OFF) deploys **first**; the mobile build ships only
  after the AASA file validates live; `growth.invite_join_link` flips ON only after a
  post-deploy install proves a tapped `/app/league/join/...` link opens the app.
