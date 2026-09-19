# Feature Scope — P0-7 · Targeted analytics additions (navigation · League surfaces · Send-in-Sleeper)

<!--
Copied from docs/templates/feature-scope.md per CLAUDE.md §Conventions "Feature gates".
NOT express lane: root CLAUDE.md's bright line names analytics events explicitly as
"not a quick fix". The operator re-included P0-7 in this build on 2026-08-10 under full
gates. Every section below is answered or explicitly WAIVED with a reason.
-->

**Date:** 2026-08-11
**Entry point:** mobile UX audit finding **P0-7** (`docs/business/product/2026-08-09-mobile-ux-audit/04-priority-backlog.md` §P0-7, `06-resolutions.md` §P0-7); deferred by the operator on 2026-08-09, re-included 2026-08-10
**Builder:** planning agent, worktree `ftf-p0-remediation` @ `ab9368f`, branch `p0-remediation-2026-08-10`
**Plan:** [plan-p0-7.md](plan-p0-7.md)
**Operator sign-off on waivers:** **required before build** — one waiver (§3 Maestro) and three open decisions (§6)

---

## 1. Analytics scope

**This is the load-bearing section for this feature — the feature *is* analytics.**
The taxonomy is **default-deny** (`backend/analytics_taxonomy.py:9-10`,
`analytics_ingest.py:379-383`): an unregistered client event is counted and **dropped**
behind a 200 response, and an allowlisted event with no `CLIENT_EVENT_PROPS` row raises at
**import**, taking the app down at boot. The prop registries exist because of the
**NULL-`platform` incident** — every client event landed with `platform`, `app_version`
and `os_version` NULL until 2026-08-05, blinding per-platform and per-release reporting
(`analytics_taxonomy.py:262`; `mobile/src/api/events.ts:281-284`). Related live gotcha
**G-017**: paired client/server gates fail silently when only one is on — zero rows had
ever landed while `analytics.client_events` was on and `analytics.ingest` off.

- [x] **(a) New events specced:** name, properties, trigger moment, emitting client(s):

  **Device `platform` is NOT a prop on any event below.** It is a `user_events` **column**
  derived server-side in `analytics_ingest.py:365-368` from the batch body / `X-Device`
  headers, which `events.ts:285` always sends. Where `platform` appears as a prop it means
  the **league** platform (`sleeper`/`espn`/`mfl`/`fleaflicker`), matching the existing
  `league_selected` precedent (`analytics_taxonomy.py:185`). This distinction is recorded
  in the tracking-plan addendum so no analyst conflates them.

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `tab_selected` | `tab`, `from_tab`, `refocus`, `intercepted` | First statement of each existing `tabPress` handler in `TabNav.tsx` (6 handlers: Rank×2, Trades, Draft, Matches, League), **before** `preventDefault()`/prefetch/pop so intercepted taps still count | mobile |
  | `league_view` | `surface`, `state`, `platform` *(league)*, `team_count`, `basis`, `subset`, `starters_available`, `outlook_shown`, `is_tab_root` | Once per mount (`firedRef` guard) when the primary query first settles, or immediately when there is no `leagueId` | mobile — `LeagueScreen.tsx` (`league_home`) and `LeagueSummaryScreen.tsx` (`league_rankings`) |
  | `league_basis_changed` | `basis`, `from`, `boards_differ`, `team_focused` | New `changeBasis()` helper wired to both `BasisChip`s (`LeagueSummaryScreen.tsx:835`, `:841`); guarded so a no-op tap emits nothing | mobile |
  | `league_subset_changed` | `subset`, `from`, `source`, `filter_count`, `picks_stripped` | Inside the existing `switchSubset` (`:746`) — the single choke point for both control instances; the `:466` auto-fallback calls `setSubset` directly and stays deliberately silent | mobile |
  | `league_team_opened` | `via`, `rank`, `basis`, `subset`, `filter_count`, `is_self` *(omit if identity unprovable — never guess)* | New `openTeam()` helper at both drill-in sites (`:1048` bar, `:1294` row) | mobile |
  | `league_home_action_tapped` **(OPTIONAL-A)** | `action` | Each hub row/tile `onPress` on `LeagueHome` | mobile |
  | `sleeper_send_attempted` | `surface`, `give_n`, `receive_n`, `from_deck`, `has_target` | Top of `SendInSleeperButton.onPress` (`:231`), after the `state !== 'idle'` guard, before haptics | mobile |
  | `sleeper_send_failed` | `surface`, `error_code` *(12 server codes ∪ `network`\|`timeout`\|`unknown`)*, `status`, `kind`, `give_n`, `receive_n`, `from_deck` | First statement of the `doPropose` catch (`:143`), before the alert ladder | mobile |
  | `sleeper_send_succeeded` | `give_n`, `receive_n`, `pick_n`, `from_deck`, `transaction_id` | `/api/trades/propose` success path (`server.py:~12404`), beside `_save_deck_outcome_safe` | **server** (`record_event`, `event_id` NULL, not client-forgeable) |

  **Naming decision.** `analytics_queries.py:52-53` already reserves
  `sleeper_send_attempted/_succeeded/_failed` as the north-star **WAT** send leg, and they
  are referenced by `FUNNEL_STAGES` stage 8, `FEATURE_VERTICALS["send_in_sleeper"]` and a
  dark caveat at `:497`. Tracking plan v2 §S3 specs them by name;
  `2026-08-05-trade-impact-and-rank-integrity.md:40` calls them *"the single
  highest-value instrumentation gap."* This plan therefore uses the **reserved** names
  rather than `06-resolutions.md`'s `send_in_sleeper_*` — same cost, and it lights up
  four dark metrics for free. **Operator decision, recorded in plan §10.3 Q1.**

  → **follow-through (all three are mandatory, not optional):**
  1. `backend/analytics_taxonomy.py` — 8 names into `ALLOWED_CLIENT_EVENTS`, 1 into
     `SERVER_FIRED_EVENTS`, 8 rows into `CLIENT_EVENT_PROPS`.
  2. `backend/analytics_queries.py` — `tab_selected` + `league_view` into
     `NON_INTENT_EVENTS` (**INTENT is a deny-list; without this DAU/WAU step-changes on
     ship day and every retention/churn series breaks at that seam**); send leg moved
     `WAT_DARK` → `WAT_LIVE`; the now-false dark caveat at `:497` made conditional or
     deleted.
  3. **Tracking-plan addendum** `docs/business/analytics/2026-08-11-p0-7-addendum.md`
     (shape: `2026-08-06-draft-room-w1-addendum.md`) — the registries' own comments
     require an addendum *before* new client events. Must record the naming decision, the
     league-vs-device `platform` distinction, the DAU/WAU seam date, and a "what is
     deliberately NOT here" section.
  4. `docs/data-dictionary.md` `user_events` "Trade:" bullet — `sleeper_send_succeeded`.
  5. `docs/cross-client-invariants.md` §"Client analytics event contract".

  **Ordering is itself the deliverable:** registry + addendum ship as their own commit and
  merge **before** any `track()` call. Reversing it reproduces the repo's documented
  prior-art failure (a client event fired into a default-deny allowlist, silently dropped,
  behind a success-shaped 200).

- [x] **(b) Existing events cover it** — named so the scope stays three additions, not a
  programme. Already live and **not** re-instrumented: `screen_viewed` / `screen_left`
  with real `dwell_ms` for every route including both League screens
  (`RootNav.tsx:352,376,181,365`); `api_request_failed` for every failed `apiRequest`
  including transport failures on `/api/trades/propose` (`client.ts:371`); server-side
  `record_event` for swipes, trade generation, tier saves and trio submits
  (`server.py:9988-10007`, `:5231-5236`, `:7387-7397`, `:5971-5981`);
  `trade_card_viewed` already carrying `ms_since_open` + `cold_start`, so
  time-to-first-trade-viewed needs no new event.

- [ ] (c) WAIVED — **not waived.** Analytics is the feature.

**Deliberately NOT instrumented** (recorded so a future session sees these were weighed):
position-filter pills; drill-in close/dwell; the Send confirm-dialog cancel; the
`validateTradeSend` warning branch; the SleeperConnect round-trip (owned by backlog item
**A-19**); season-outlook interactions while `outlook.odds` is off — carried as a single
`outlook_shown` boolean instead.

## 2. Schema & flag scope

- **New/changed tables or columns: none.** `user_events` already stores every field used;
  props ride the existing JSON `props` column. **No migration.** `docs/data-dictionary.md`
  is updated for the new server-fired `event_type` only, per that file's own rule (`:264`).
- **New/changed feature flags: none.** Behaviour rides the existing pair
  `analytics.client_events` (client emission gate, `events.ts:52`) and `analytics.ingest`
  (server ingest gate) — **both verified `true` in `config/features.json`**. No
  `FLAG_KEYS` change, no `docs/config-reference.md` change. **Ship-the-knob:** the rollback
  lever already exists and is deploy-free — flipping `analytics.client_events` off stops
  emission at the client (events retain in queue, nothing is lost); flipping
  `analytics.ingest` off stops the write. Both are pre-existing kill switches documented
  in `docs/runbook.md` §"Analytics platform P0".
- **New env vars / `model_config` keys: none.**

## 3. Test scope (mobile test platform)

- [ ] **New flow:** none.
- [ ] **Extended flow:** none.
- [x] **WAIVED because:** **the change is not user-visible.** No rendered element, copy,
  layout, colour, timing or navigation behaviour changes. Every mobile insertion is either
  a `track()` call — fire-and-forget, returns `void`, swallows every error by contract
  (`events.ts:209`) — or a pass-through prop. Maestro asserts on rendered UI and has no
  visibility into an analytics queue or a `POST /api/events` batch; a new flow here could
  only re-assert the absence of a regression the smoke suite already covers.

  Two conditions make this a waiver rather than a shortcut:
  1. **Existing flows must pass unchanged and unmodified** — specifically
     `mobile/.maestro/04-tabs-navigation.yaml` (drives every `tabPress` handler this
     change edits) and `mobile/.maestro/flows/smoke/09-league.yaml` (mounts both League
     screens). **Any diff to those flow files invalidates this waiver.**
  2. **Verification moves to backend tests + a manual end-to-end row check** (§9 of the
     plan) — the events are proven by rows landing in `user_events` with a non-NULL
     `platform`, per G-017's rule: *verify a row at the destination, not a 200 at the
     source*.

  **→ Operator sign-off required on this waiver.**
- **`testID`s added/renamed: none** ⇒ `mobile/scripts/testid-lint.sh` unaffected.
- **Capture delta: none** — no visual change, so no `mobile/scripts/screen-capture.sh` run.
  `mobile/scripts/screen-freshness.sh` is run as part of the tier-2 gate; it is expected to
  flag nothing, and anything it does flag is a signal the "no visual change" claim is wrong.
- **Smoke-suite impact:** five of the eleven flows cross these surfaces —
  `04-tabs-navigation` (tab handlers), `smoke/09-league` (both League screens),
  `smoke/05-trades-render` + `smoke/06-trades-deck` (the deck `SendInSleeperButton` mount),
  `smoke/07-calculator` (the calculator mount). All must be green; none should need edits.
- **Backend: pytest files added/updated:**
  - `backend/tests/test_events_api.py` — new `test_p0_7_events_accepted` in the shape of
    the existing `test_new_observability_events_accepted` (`:335`) /
    `test_guide_events_accepted` (`:366`): assert `dropped == 0` **and** an exact
    `set(by_type)`, which are the two assertions a default-deny allowlist can otherwise
    fail silently. Plus a negative (misspelled name ⇒ counted-and-dropped, mirroring
    `test_unknown_type_dropped` `:246`) and a prop-stripping case (a bogus
    `device_platform` prop is stripped, pinning the "no device-platform prop" decision).
  - `backend/tests/test_analytics_p0.py` — extend `test_live_taxonomy_is_disjoint`
    (`:453`) membership with the new names; add a `sleeper_send_succeeded` server-fired
    test. **Known blocker:** `/api/trades/propose` fail-closes with `599
    test_mode_propose_disabled` under `FTF_TEST_MODE` (`server.py:12310`), so the route
    cannot be driven end-to-end. Recommended resolution: extract a one-line
    `_record_send_success(...)` helper and unit-test it directly (plan §9.1 option a).
  - Import-time asserts are self-enforcing: a missing `CLIENT_EVENT_PROPS` row or a name
    collision makes the **entire suite fail to import**, which is the intended loud
    failure and needs no new test.
- **Mobile:** `cd mobile && npx tsc --noEmit`. The new **required** `surface` prop on
  `SendInSleeperButton` turns any missed mount site into a compile error — deliberate
  enforcement across all four mounts.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **n/a** | No route added, renamed, removed or contract-changed. `POST /api/events` accepts new names purely by registry membership — request/response shape untouched. `/api/trades/propose` gains a `record_event` side effect, not a contract change. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **n/a** | No convention shifts. "Register server-side before wiring the client" is an existing convention this plan obeys, not a new one. |
| `docs/architecture.md` (module wiring / data flow changed) | **n/a** | No new module, no wiring change; every call uses an existing path (`track` → SDK queue → `POST /api/events` → ingest; `record_event` → `user_events`). |
| `living-memory/HLD.md` (architecture genuinely shifted) | **n/a** | No architectural shift. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **Updated** | §"Client analytics event contract (`POST /api/events`…)" (`:268`) — that section states event names are shared verbatim across all client SDKs and the backend allowlist, and that changing one side alone breaks ingestion silently. Add the eight new client names + addendum link, and state explicitly that **web (`web/js/events.js`) and the extension (`extension/background.js`) fire none of them**, so the omission reads as deliberate rather than as drift. |
| `docs/glossary.md` (new domain term) | **n/a** | No new domain term — `basis`, `subset`, `WAT`, `intent event` are all already defined. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **`living-memory/DECISIONS.md`, next id `D-011`** | Two non-obvious choices: (1) adopting the reserved `sleeper_send_*` names over the resolutions doc's `send_in_sleeper_*`, which lights up WAT / funnel stage 8 / the `send_in_sleeper` feature vertical; (2) the client/server split — success **server**-authoritative (the only place the send is known to have landed), attempt and failure **client**-side (the only place network, timeout and pre-identity refusals are visible, and the only place `surface` is known). No full ADR: no architectural shift. |
| **`docs/business/analytics/2026-08-11-p0-7-addendum.md`** *(added row — the mandatory one)* | **NEW** | The tracking-plan addendum is the **precondition** `analytics_taxonomy.py:9-10` demands before any new client event name. Parent: tracking plan v2 §S3. |
| `docs/data-dictionary.md` *(added row)* | **Updated** | `user_events` "Trade:" bullet (~`:721`) — `sleeper_send_succeeded` and its props, per that file's own rule at `:264`. |
| `living-memory/CHANGELOG.md` / `TEST_LEDGER.md` *(added row)* | **On ship** | Per `CLAUDE.md` §Session memory. TEST_LEDGER carries the tier-2 sim run **and** the end-to-end row-landed verification. |

### 4.1 Execution record — W3-DOCS, commit 14 (2026-08-11)

> Row-by-row closure of the table above, per the feature-gate contract. **IDs are `hld.md` §7 / §10.4's**, which supersede any `D-011` / `G-013` written above — root `CLAUDE.md`'s next-ID columns were stale when these scope blocks were authored (they have since been changed to "max existing + 1 — grep first", so the trap is closed at the source).

| Row | Status | Where it landed |
|---|---|---|
| `docs/business/analytics/2026-08-11-p0-7-addendum.md` | **not W3-DOCS** | Owned by `W0-TAX` as the registry's stated precondition; verified present. |
| `docs/cross-client-invariants.md` § Client analytics event contract | **updated** | All 15 client names grouped by surface + the server-fired name called out as *not* in the list (namespaces disjoint by import-time assertion); the canonical `sleeper_send_*` naming and why the reserved spelling was taken; the `SendSurface` enum with `awaiting` ≠ `suggested`; `celebration_shown`-never-`celebration_fired` and the no-alias rule; the INTENT-is-a-deny-list rule and the four non-intent classifications; the explicit statement that web and the extension fire none of them; and a default-deny warning callout with the 33-of-73 sweep number. |
| `docs/data-dictionary.md` `user_events` "Trade:" bullet | **updated** | `sleeper_send_succeeded` with its props, why it is server-fired, the excluded counterparty id, and the `_EVENT_TO_USER_COL` omission. |
| `docs/api-reference.md` | **updated (revised from n/a)** | No contract change, but the `POST /api/trades/propose` row gains the server-fired-event note — a reader of that route needs to know it now writes a `user_events` row and that `last_trade_proposed_at` is deliberately unchanged. |
| `living-memory/DECISIONS.md` | **updated — D-031** | Both choices, incl. why all-client and all-server were each impossible. |
| `living-memory/GOTCHAS.md` | **updated — G-031** | Strengthened per the sweep: 33 of 73, three fixed, 29 left, and the `quickset_completed` special case. |
| `living-memory/NEXT.md` | **updated** | Items 0h (the 29 remaining names, with `quickset_completed`'s different fix) and 0i (the three prop/allowlist gaps). |
| `living-memory/CHANGELOG.md` | **updated** | Batch H2 — names the `invite_shared`-into-a-wall finding and the NON_INTENT seam. |
| `living-memory/LLD.md` · `living-memory/HLD.md` · `docs/architecture.md` · `docs/config-reference.md` · `docs/glossary.md` · `living-memory/DEPENDENCIES.md` | **n/a — confirmed** | As stated above. |

**Not executed, and why:** `screens/CLAUDE.md` + `screens/manifest.json` re-capture rows are **deferred** — the renamed/new frames require a run of `mobile/scripts/screen-capture.sh` against the simulator, which `W3-QA` holds for the sim gate. Writing index entries for PNGs that do not exist would make the manifest lie. Tracked for the capture pass. `living-memory/TEST_LEDGER.md` is owned by `W3-QA` and is deliberately untouched here.

## 5. Ship gate declaration

- **Simulator-gate tier:** **Tier 2** — *"Mobile logic touched, no UI change"*
  (`docs/runbook.md` §Pre-ship simulator gate). The feature has no flow of its own (§3
  waiver), so the requirement resolves to the **affected smoke subset** —
  `04-tabs-navigation`, `smoke/09-league`, `smoke/05-trades-render`,
  `smoke/06-trades-deck`, `smoke/07-calculator` — plus
  `mobile/scripts/screen-freshness.sh`, re-capturing **only** what it flags (expected:
  nothing).

  *Tier-1 counter-argument, stated so the operator can overrule:* `TabNav.tsx` is
  navigation, and tier 1 covers "navigation … change". The reason tier 2 is claimed is
  that **no navigation behaviour changes** — every `tabPress` handler already exists and
  keeps its exact control flow, including the Rank variant's `preventDefault()`. If the
  operator prefers tier 1 (full 11-flow smoke), that is a recorded deviation, not a
  correction.

- **Evidence:** `living-memory/TEST_LEDGER.md` entry (flows run, pass/fail, sim device,
  SHA) **plus** the end-to-end verification from plan §9.3 — rows present in
  `user_events` for each new event type, **`platform` non-NULL** (the direct regression
  check for the incident that motivates this whole regime), and
  `GET /api/analytics/health` showing `dropped_unknown_type` / `dropped_unknown_prop` flat
  across the session. Write `qa/sim-runs/last-sim-run.json` after the run.

- **Operator deviation from the matrix (if any) and why:** none proposed. Tier 2 as
  argued above; the Maestro waiver in §3 is the only exception sought and it needs
  explicit sign-off.

---

## Open items requiring an operator/orchestrator decision before build

1. **Event naming** — reserved `sleeper_send_*` *(recommended)* vs `send_in_sleeper_*` as
   literally written in `06-resolutions.md`. Same cost; the former lights up four
   currently-dark metrics.
2. **OPTIONAL-A `league_home_action_tapped`** — in or out. *Recommended: in* — one
   registry row plus ~11 one-line inserts, and without it `LeagueScreen` gets a mount
   event and no interaction coverage, which under-delivers the resolution's *"mount and
   interaction events on **both** League screens."*
3. **P0-9 first-session funnel events** (plan §6 — a separable optional section) — none,
   F1 only, or all four. *Recommended minimum: F1 `experiment_exposed`*, which is already
   in `FUNNEL_CRITICAL` and the mobile SDK mirror but **absent from
   `ALLOWED_CLIENT_EVENTS`** — a live instance of the exact silent-drop trap this finding
   exists to close, and without it any A/B read is exposure-diluted because
   `backend/experiments.py:620,723` falls back to assignment-as-exposure.
4. **Maestro waiver (§3)** — sign off or require a flow.
5. **File-ownership collision:** `mobile/src/components/SendInSleeperButton.tsx` is also
   claimed by **P0-6** (replacing the silent ESPN `null` at `:273` with an explanatory
   state + copy fallback). *Recommendation: give the file to P0-6 and hand P0-7's diff
   over as a spec* — P0-6 restructures the render path while P0-7 only inserts into
   `onPress`/`catch` and adds a prop. `mobile/src/screens/TradesScreen.tsx` is shared with
   **P0-2** and **P0-8**, but P0-7 needs exactly one line at `:4713`.
