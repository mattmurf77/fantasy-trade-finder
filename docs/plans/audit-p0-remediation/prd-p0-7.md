# PRD — P0-7 · Analytics blindness

> **What this document is:** the requirements and acceptance criteria for P0-7 of the
> 2026-08-09 mobile-UX-audit remediation batch. The code-level design is
> [`lld-p0-7.md`](lld-p0-7.md); the binding batch design is [`hld.md`](hld.md); the
> originating plan and scope block are [`plan-p0-7.md`](plan-p0-7.md) and
> [`scope-p0-7.md`](scope-p0-7.md).
>
> **One-sentence framing.** The app cannot currently answer *which tabs people use*,
> *whether the League surfaces do anything*, *whether Send in Sleeper converts*, or
> *where the Quick Set ladder loses people* — and the first two of those are questions
> launch day will ask on day one.

## Contents

- [1. Problem](#1-problem)
- [2. Requirements](#2-requirements)
- [3. Acceptance criteria](#3-acceptance-criteria)
- [4. Event dictionary](#4-event-dictionary)
- [5. Non-goals](#5-non-goals)
- [6. Docs impact](#6-docs-impact)
- [7. Rollback](#7-rollback)
- [8. Risks carried from the HLD](#8-risks-carried-from-the-hld)

---

## 1. Problem

The client analytics spine is healthy — an SDK with a persistent queue and backoff
(`mobile/src/api/events.ts`), a default-deny ingest pipeline
(`backend/analytics_ingest.py`), and a report layer (`backend/analytics_queries.py`).
Both gates (`analytics.client_events`, `analytics.ingest`) are on. What is missing is
**coverage of four surfaces**, plus one structural defect that makes the gap worse than
it looks:

1. **Navigation.** `screen_viewed` fires for every route (`RootNav.tsx:352`, `:376`) —
   this is *already true* and the audit's "zero client instrumentation on navigation"
   claim is wrong (HLD §10.1). What is genuinely missing is the tab **selection** itself:
   which tab a user chose, from where, and whether the tap was a re-tap or was
   intercepted by the Rank action sheet.
2. **The two League screens.** `LeagueScreen.tsx` (1 195 lines) and
   `LeagueSummaryScreen.tsx` (2 347 lines) contain **zero** `track()` calls. Neither
   mounts nor interactions are measurable.
3. **Send in Sleeper.** `SendInSleeperButton.tsx` contains zero `track()` calls and
   `POST /api/trades/propose` contains **no** `record_event` on any path — so the
   product's highest-intent action is entirely invisible, including all twelve of its
   distinct failure codes. Meanwhile `analytics_queries.py:52` has **reserved the exact
   names** `sleeper_send_attempted/_succeeded/_failed` since 2026-07-17, wiring them into
   the north-star WAT metric, funnel stage 8 and the `send_in_sleeper` feature vertical.
   All four have been dark ever since, one alias away from data.
4. **The taxonomy is default-deny behind a 200.** An unregistered client event name is
   counted, dropped, and answered with success (`analytics_ingest.py:379-383`). The
   result is a plausible dashboard with no rows. **Three live instances already exist in
   this tree:** the NULL-`platform` incident (fixed 2026-08-05); `invite_shared`, which
   `InviteLeaguematesBanner.tsx:47` has fired into a wall since it shipped — meaning "the
   invite loop converts zero" has never actually been measurable; and
   `experiment_exposed`, which sits in `FUNNEL_CRITICAL` and in the SDK's mirror but not
   in the allowlist, so **every A/B read today is exposure-diluted** and
   `backend/experiments.py:620,723` falls back to assignment-as-exposure and reports the
   dilution itself.

The consequence for the batch: P0-9's first-session test — *"is the Quick Set ladder a
grind, and does trades-first beat it?"* — is not readable without F1 (exposure) and F3/F4
(the per-rung drop-off curve). A test that cannot be read is not a test.

---

## 2. Requirements

### R1 — Register every name before any emitter ships (must)

All **15 client event names + 1 server-fired name** land in
`backend/analytics_taxonomy.py` with a `CLIENT_EVENT_PROPS` row each, in **their own
commit, as the first code commit on the branch**, before a single `track()` call is
wired. Names are enumerated in §4. This includes `invite_shared` (already firing, already
dropped) and `experiment_exposed` (in `FUNNEL_CRITICAL` and the SDK mirror, absent from
the allowlist) — registering both is a bug fix, not an addition.

### R2 — DAU, WAU and every retention series must be unbroken across the seam (must)

`INTENT_EVENTS` is a **deny-list**, so taxonomy growth is intent-by-default. The four
impression/outcome-class names — `tab_selected`, `league_view`, `experiment_exposed`,
`quickset_abandoned` — are added to `NON_INTENT_EVENTS` in the same commit. Without this,
DAU/WAU step-changes to roughly app-open count on ship day and every retention and churn
series breaks at that seam, silently and permanently.

The **eleven** remaining new names stay INTENT deliberately (a basis toggle, a drill-in,
a send attempt, an invite share, a Quick Set rung advance are all a user acting on the
product). That produces a genuine, expected step in WAU. The seam date and the split are
recorded in the tracking-plan addendum so the step reads as designed, not as drift.

### R3 — Tab usage must be readable (must)

`tab_selected` fires as the **first statement** of each of the six existing `tabPress`
handlers in `TabNav.tsx` — before any early return, `preventDefault()`, prefetch or pop —
carrying `tab`, `from_tab`, `refocus` and `intercepted`. No new handlers, no navigation
behaviour change, including the Rank variant's `preventDefault()`.

### R4 — League engagement must be readable on both screens (must)

Each League screen emits exactly **one** `league_view` per mount, when its primary query
first settles (or immediately when there is no league), carrying surface, state, **league**
platform, team count, basis, subset, starters availability, `outlook_shown` and
`is_tab_root`. `LeagueSummaryScreen` additionally emits `league_basis_changed`,
`league_subset_changed` and `league_team_opened`; `LeagueScreen` emits
`league_home_action_tapped` across its twelve hub exit paths, because League Home's exit
paths are the only question that screen answers.

### R5 — The send funnel must be readable end to end, including why it fails (must)

`sleeper_send_attempted` and `sleeper_send_failed` are **client**-fired (the only place
that sees network errors, timeouts, the pre-identity refusals the server cannot attribute
to a user, and the `surface` the send came from). `sleeper_send_succeeded` is
**server**-fired from `/api/trades/propose`'s success path (the only place the send is
*known* to have landed in Sleeper; a client-forgeable success would sit in WAT and funnel
stage 8 next to server-authoritative `trade_ratified`).

`error_code` is a closed 15-value enum: the route's twelve codes ∪ `network` | `timeout`
| `unknown`. The reserved names are adopted verbatim, so WAT, funnel stage 8 and the
`send_in_sleeper` vertical light up with no further work.

### R6 — P0-9's test must be readable (must)

- **F1 `experiment_exposed`** — emitted on **first consumption of an experiment-overlaid
  flag key**, once per key per session, **deferred** so it never runs during render.
  Provenance (which key came from which experiment/variant) is recorded in `api/flags.ts`
  during the existing `configs[*].flags` merge, which today discards it.
- **F3 `quickset_step_advanced`** — per forward rung, carrying `seeded_accepted` (the
  user saved exactly the consensus-seeded set, i.e. the rung cleared in one tap — the
  operator's fairness point about "32 taps"), plus `picked_n` and `via`.
- **F4 `quickset_abandoned`** — on blur/unmount/background with progress and no
  completion, carrying the rung they stopped on.
- **F2 `first_session_started` is excluded** — arm attribution is already derivable from
  `experiments.stamp_for_event`.

### R7 — Zero events silently dropped (must)

Backend acceptance asserts `dropped == 0` **and** an exact `set(by_type)` over all
fifteen — the two assertions a default-deny allowlist can otherwise fail silently. The
negative guard (a plausible misspelling is counted-and-dropped) stays armed. During the
sim run, `GET /api/admin/analytics/health`'s `dropped_unknown_type` and
`dropped_unknown_prop` counters stay flat.

### R8 — Zero product-behaviour change (must)

No UI, copy, layout, colour, timing, navigation behaviour, route, schema, migration,
feature flag, env var or `model_config` key changes. Every mobile insertion is either a
`track()` call — synchronous, `void`-returning, error-swallowing by contract
(`events.ts:188-215`), and a no-op while `analytics.client_events` is off — or a
pass-through prop. The one server change is a `record_event` **side effect** on an
existing route, not a contract change.

### R9 — No device-`platform` prop on any event (must)

Device platform is a `user_events` **column**, derived server-side from the batch body
and `X-Device` headers (`analytics_ingest.py:365-368`). Where `platform` appears as a
prop it means the **league** platform (`sleeper|espn|mfl|fleaflicker|unknown`), matching
the `league_selected` precedent. The distinction is pinned by a prop-stripping test and
recorded in the addendum. This is the direct guard against a repeat of the NULL-`platform`
incident.

### R10 — Never guess a prop (must)

`is_self` on `league_team_opened` is **omitted** entirely: session-user ↔
`PowerRankedTeam.user_id` identity was not proven. `unit` on `experiment_exposed` is
registered but not emitted: the flag endpoint returns merged experiment maps without the
`unit_type` the server knew. A missing prop is honest; a guessed one poisons a metric
permanently.

### R11 — No side effects on notification gating (must)

`sleeper_send_succeeded` must **not** be added to `database._EVENT_TO_USER_COL`. Bumping
`last_trade_proposed_at` would change notification-gating behaviour, which is out of
scope for an instrumentation item. Verified absent today; a test pins it.

### R12 — The Maestro waiver's conditions hold (must)

`mobile/.maestro/04-tabs-navigation.yaml` (drives every `tabPress` handler this change
edits) and `mobile/.maestro/flows/smoke/09-league.yaml` (mounts both League screens) must
pass **unmodified**. They are the regression proof that stands in for the waived flow;
**any diff to either invalidates the waiver** and is a review stop.

### R13 — File ownership is respected (must)

The instrumentation agent does not open `TradesScreen.tsx`, does not change
`SendInSleeperButton`'s signature or render path before the close-out commit, does not
touch either Maestro file above, and does not add an alias for `celebration_fired`. The
three one-line `surface` props live in files owned by other agents and are supplied as
handoff specs.

---

## 3. Acceptance criteria

Each row is a question launch day will ask, and the query that answers it.

| # | Criterion | How it is proven |
|---|---|---|
| **A1** | **"Which tabs do people actually use?"** is answerable, with re-taps and Rank-sheet interceptions separable from real switches. | `SELECT props->>'tab', COUNT(*) FROM user_events WHERE event_type='tab_selected'` returns all five tabs after a sim session touching each; `refocus` and `intercepted` both appear as `true` and `false`. |
| **A2** | **"Does anyone engage with the League surfaces?"** is answerable for mounts *and* interactions on **both** screens. | One `league_view` per screen visit (exactly one — R11 double-fire guard), plus rows for `league_basis_changed`, `league_subset_changed` (with `source` distinguishing the chart control from the drill-in control), `league_team_opened`, and `league_home_action_tapped` across the hub. |
| **A3** | **"Does Send in Sleeper convert, and when it fails, why?"** is answerable. | `sleeper_send_attempted` → `sleeper_send_succeeded` is a computable rate; failures group by a closed 15-value `error_code`; `surface` is present on attempt and failure so deck / match / suggested / calculator are separable. WAT's `caveat` flips from `"dark"` to a real value on the first send. |
| **A4** | **P0-9's test is readable.** | `experiment_exposed` rows exist with `experiment`/`variant` matching `GET /api/feature-flags` for an assigned device; `quickset_step_advanced` gives a per-rung completion curve with `seeded_accepted` and `picked_n`; `quickset_abandoned` names the rung people stop on. |
| **A5** | **Zero events silently dropped.** | `test_p0_remediation_events_accepted` asserts `dropped == 0` **and** exact `set(by_type)` over all 15; `dropped_unknown_type` / `dropped_unknown_prop` flat across the sim session; the misspelling negative test still drops. |
| **A6** | **DAU / WAU / retention series unbroken.** | `test_p0_impression_events_are_non_intent` (the four names are in `NON_INTENT_EVENTS` and out of `INTENT_EVENTS`); post-ship, DAU/WAU shows **no** step-change on the ship date. |
| **A7** | **`platform` is never NULL on the new rows.** | Sim-run query groups by `platform` and returns `'ios'`, not NULL — the direct regression check for the incident that motivates the whole prop-spec regime. Plus the prop-stripping test for the league-vs-device distinction. |
| **A8** | **`screen_viewed` is verified, not rebuilt.** | Rows exist for `LeagueHome`, `LeagueRankings`, `Trades`, `Rank`, `Matches` with non-NULL `platform` and plausible `screen_left.dwell_ms`. This confirms time-to-first-value and the LeaguePicker→Trades drop-off are **already** readable and removes the dependency P0-9's test was said to hang on. **No code is written for this criterion.** |
| **A9** | **Nothing user-visible changed.** | `04-tabs-navigation.yaml` and `smoke/09-league.yaml` pass **unmodified**; the batch tier-1 smoke suite is green; `screen-freshness.sh` flags nothing (anything it flags means the "no visual change" claim is wrong). |
| **A10** | **The build is green at every commit.** | `python3 -m pytest backend/tests/ -q` and `cd mobile && npx tsc --noEmit` pass independently at commits 1, 5, 9, 10 and 13. At commit 13 the required `surface` prop makes a missed mount a compile error. |
| **A11** | **The registry's own precondition is met.** | `docs/business/analytics/2026-08-11-p0-7-addendum.md` exists and records the naming decision, the league-vs-device `platform` distinction, the DAU/WAU seam date, the `invite_shared` history, the D2 rename, the deliberately-NOT-here list, and the `find_trades_tapped` defect. |

---

## 4. Event dictionary

Sixteen names. **Agent** is the wave/agent that ships the emitter; **every** name is
registered by `W0-TAX` in commit 1 regardless of who emits it. `I` = INTENT,
`NI` = NON_INTENT (excluded from DAU/WAU/retention/churn).

| # | Event | Props | Trigger | Emitter agent | I/NI |
|---|---|---|---|---|---|
| 1 | `tab_selected` | `tab` (`rank\|trades\|draft\|matches\|league`), `from_tab` (str\|null), `refocus` (bool), `intercepted` (bool) | First statement of each of the six existing `tabPress` handlers, before `preventDefault()` / prefetch / pop | W2-P07 (`TabNav.tsx`) | **NI** |
| 2 | `league_view` | `surface` (`league_home\|league_rankings`), `state` (`ready\|empty\|error\|no_league`), `platform` (**league**), `team_count` (int\|null), `basis`, `subset`, `starters_available`, `outlook_shown`, `is_tab_root` | Once per mount (`firedRef`), when the primary query first settles — or immediately when there is no league | W2-P07 (both League screens) | **NI** |
| 3 | `league_basis_changed` | `basis`, `from`, `boards_differ` (bool), `team_focused` (bool) | New `changeBasis()` helper on both `BasisChip`s; guarded, so a no-op re-tap emits nothing | W2-P07 (`LeagueSummaryScreen.tsx`) | I |
| 4 | `league_subset_changed` | `subset` (`all\|starters\|bench`), `from`, `source` (`chart\|roster`), `filter_count` (int), `picks_stripped` (bool) | Inside the existing `switchSubset` choke point, guarded on a real change. The server-driven auto-fallback stays deliberately silent | W2-P07 (`LeagueSummaryScreen.tsx`) | I |
| 5 | `league_team_opened` | `via` (`bar\|row`), `rank` (1-based **on-screen** rank under the active filters), `basis`, `subset`, `filter_count`. **`is_self` omitted** (R10) | New `openTeam()` helper at both drill-in entry points | W2-P07 (`LeagueSummaryScreen.tsx`) | I |
| 6 | `league_home_action_tapped` | `action` — closed 12-value enum: `rank`, `find_trades`, `matches_mutual`, `matches_awaiting`, `rankings`, `free_agents`, `draft_room`, `rookie_board`, `draft_picks`, `whats_new`, `members`, `espn_resync` | Each hub row/tile `onPress` on League Home | W2-P07 (`LeagueScreen.tsx`) | I |
| 7 | `sleeper_send_attempted` | `surface` (`deck\|match\|suggested\|calculator`), `give_n`, `receive_n`, `from_deck` (bool), `has_target` (bool — false ⇒ the openInSleeper handoff, not a real send) | Top of `onPress`, after the `state !== 'idle'` guard, before haptics. **Handler only — never the render path** | W2-P07 (`SendInSleeperButton.tsx`, handlers only) | I |
| 8 | `sleeper_send_failed` | `surface`, `error_code` (closed 15-value enum), `status` (int\|null), `kind` (str\|null), `give_n`, `receive_n`, `from_deck` | First statement of `doPropose`'s catch, before the alert ladder | W2-P07 (`SendInSleeperButton.tsx`, handlers only) | I |
| 9 | `sleeper_send_succeeded` | `give_n`, `receive_n`, `pick_n`, `from_deck`, `transaction_id` (str\|null) | `/api/trades/propose` success path, via the extracted `_record_send_success` helper, after `_save_deck_outcome_safe` | **W1-BE** (`server.py`, **server-fired**, `event_id` NULL) | I |
| 10 | `invite_shared` | `league_id` | Share sheet returns a non-dismissed action from the invite CTA. **Already firing since it shipped and dropped every time** — registration is a bug fix | W2-P03 (existing call site) | I |
| 11 | `invite_link_opened` | `league_id`, `has_ref` (bool), `format` (`legacy\|path`), `auth_state` (`signed_out\|authed_member\|authed_non_member`) | An invite URL is parsed — the new path route or a legacy `?league=` URL | W2-P03 | I |
| 12 | `invite_league_pinned` | `league_id`, `source` (`join_screen\|picker_autopin`), `ms_since_open` | The invited league becomes the active league | W2-P03 | I |
| 13 | `invite_pin_failed` | `league_id`, `reason` (`not_member\|session_init_failed\|expired`) | The invite intent could not be honoured | W2-P03 | I |
| 14 | `experiment_exposed` | `experiment`, `variant`, `key` (the flag key consumed). **`unit` registered, not emitted** (R10) | First consumption of an experiment-overlaid flag key, once per key per session, **deferred** — never during render | W2-P07 (`api/flags.ts` + `state/useFeatureFlags.ts`) | **NI** |
| 15 | `quickset_step_advanced` | `position`, `tier_index`, `tier_count`, `seeded_accepted` (bool), `picked_n` (int), `via` (`save\|skip\|empty`), `ms` | Each **forward** rung advance (save success / empty-save / skip). A backward step is not an advance and is not counted | W2-P07 (`QuickSetTiersScreen.tsx`) | I |
| 16 | `quickset_abandoned` | `position`, `tier_index`, `tiers_done`, `ms`, `reason` (`nav\|background`) | Blur / unmount / background with progress > 0 and the walk not completed; deduped | W2-P07 (`QuickSetTiersScreen.tsx`) | **NI** |

**Registration owner for all sixteen: `W0-TAX`, commit 1, exclusively.** No other commit
in this batch may open `analytics_taxonomy.py` or `analytics_queries.py`.

---

## 5. Non-goals

**Explicitly out of scope. Each was considered; none is an oversight.**

- **No schema change, no migration.** `user_events` already stores every field; props
  ride the existing JSON column.
- **No route added, renamed, removed or contract-changed.** `POST /api/events` accepts
  the new names purely by registry membership — its request/response shape is untouched.
  `/api/trades/propose` gains a side effect, not a contract change.
- **No feature flag added or defaulted differently.** Behaviour rides the existing pair
  `analytics.client_events` + `analytics.ingest`, both already on.
- **No UI change, no copy change, no new `testID`, no capture delta.**
- **No new Maestro flow** (waived — see R12). Maestro asserts on rendered UI and cannot
  observe an analytics queue.
- **No navigation instrumentation built from zero.** `screen_viewed` / `screen_left` are
  already live for every route including tab switches; S-38 resolves to a **verification**
  task (A8).
- **No `celebration_fired` alias.** The client renames to the already-registered
  `celebration_shown` at its three call sites (executed by the TradesScreen agent);
  an alias would enshrine a typo in a shipped surface.
- **Not a full instrumentation programme — three additions plus F1/F3/F4.** Deliberately
  not instrumented: the position-filter pills; drill-in close/dwell; the Send
  confirm-dialog cancel; the `validateTradeSend` warning branch; the SleeperConnect
  round-trip (owned by backlog item **A-19**); season-outlook interactions while
  `outlook.odds` is dark (carried as the single `outlook_shown` boolean); P0-6's proposed
  `send_unavailable_shown` / `trade_copied` (they would need a render-path event, which
  §1.4/S-23 forbids — these go to `NEXT.md`).
- **F2 `first_session_started` is out** — arm attribution is already derivable from
  `experiments.stamp_for_event`.
- **The `find_trades_tapped` empty-prop-allowlist defect is documented, not fixed.**
  `CLIENT_EVENT_PROPS` registers it as an empty frozenset, so the `source` prop the
  existing call site sends is stripped at ingest: the event lands, its only dimension does
  not. Widening a shipped event's prop surface inside a registration commit is the
  opposite of that commit's discipline. It is recorded in the addendum's
  deliberately-NOT-here section and queued on `NEXT.md`.
- **No `is_self`, no `unit` emission, no `last_trade_proposed_at` bump** (R10, R11).
- **No flag flip, no rollout.** This build changes no flag default anywhere.

---

## 6. Docs impact

All rows are owned by **`W3-DOCS`** except the addendum, which is owned by `W0-TAX`
because the registry's own comments make it a **precondition** for new client event names
(`analytics_taxonomy.py:9-10`), not a follow-up.

| Doc | Updated? | Content |
|---|---|---|
| **`docs/business/analytics/2026-08-11-p0-7-addendum.md`** (new) | **NEW — mandatory, owned by `W0-TAX`** | Parent: tracking plan v2 §S3. Shape follows `2026-08-06-draft-room-w1-addendum.md`. Records: the `sleeper_send_*` naming decision; the league-vs-device `platform` distinction; the DAU/WAU seam date and the NON_INTENT/INTENT split; that `invite_shared` was firing into a wall since it shipped; the D2 `celebration_fired` → `celebration_shown` rename (documented here, executed by the client, **no alias**); the full deliberately-NOT-here list; and the `find_trades_tapped` empty-prop-allowlist defect. |
| `docs/cross-client-invariants.md` §"Client analytics event contract" (`:268`) | **Updated** | That section already states event names are shared verbatim by every client SDK **and** the backend allowlist, and that changing one side alone breaks ingestion silently. Add the fifteen new client names + the server-fired name + the addendum link, and state explicitly that **web (`web/js/events.js`) and the extension (`extension/background.js`) fire none of them**, so the omission reads as deliberate rather than as drift. |
| `docs/data-dictionary.md` `user_events` "Trade:" bullet | **Updated** | `sleeper_send_succeeded` and its props, per that file's own rule that a new stored `event_type` joins the list. Client events land in the same table but are documented via the taxonomy + addendum, matching how `guide_*` and `draft_room_*` were handled. |
| `living-memory/DECISIONS.md` | **Updated — `D-031`** (id allocated by HLD §7; the "next id `D-011`" in five plans and in root `CLAUDE.md` is stale, per HLD §10.4) | P0-7's two non-obvious choices: (1) adopting the reserved `sleeper_send_*` names over `send_in_sleeper_*`, lighting up WAT / funnel stage 8 / the `send_in_sleeper` vertical; (2) the client/server split — success server-authoritative, attempt and failure client-side. |
| `living-memory/GOTCHAS.md` — **`G-031`** | **Updated** | A client `track()` name absent from `analytics_taxonomy.py` is counted and dropped **in silence** behind a 200 — third occurrence in this repo. |
| `living-memory/NEXT.md` | **Updated** | `source` prop on `find_trades_tapped`'s allowlist; `FUNNEL_CRITICAL` ↔ SDK-mirror drift (`app_opened_first` is in one and not the other, and in neither allowlist); P0-6's `send_unavailable_shown` / `trade_copied`; `unit` on `experiment_exposed` (needs the flag endpoint to return `unit_type`). |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | **On ship** | TEST_LEDGER carries the batch tier-1 sim run **and** P0-7's destination row-landed verification (§5.3 of the LLD) verbatim. |
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed or contract-changed. |
| `living-memory/LLD.md` · `living-memory/HLD.md` · `docs/architecture.md` | **n/a** | No convention shift, no architectural shift, no module wiring or data-flow change — every call uses an existing path (`track` → SDK queue → `POST /api/events` → ingest; `record_event` → `user_events`). |
| `docs/config-reference.md` · `docs/glossary.md` · `living-memory/DEPENDENCIES.md` | **n/a** | No flag / env var / `model_config` key; no new domain term (`basis`, `subset`, `WAT`, `intent event` are all defined); no dependency added, bumped or removed. |

---

## 7. Rollback

**Every event in this PRD is additive, and removal is a client no-op.**

- **`track()` is fire-and-forget.** It is synchronous, returns `void`, and swallows every
  error by contract (`events.ts:188-215`). Deleting any `track()` call — or all of them —
  removes a queue push and nothing else. No control flow, no render output, no state
  depends on the return value, because there is no return value.
- **Two pre-existing kill switches, deploy-free.** Flipping `analytics.client_events` off
  stops client emission (queued events are retained, nothing is lost); flipping
  `analytics.ingest` off stops the write. Both are documented in `docs/runbook.md`
  §"Analytics platform P0". Neither requires a build.
- **The taxonomy commit is separately revertible by design** (it is deliberately not
  squashed with anything else). Reverting it is a **metric-definition rollback** and
  nothing more: the fifteen names return to counted-and-dropped, the four names leave
  `NON_INTENT_EVENTS`, and the send leg returns to `WAT_DARK`. No user-visible behaviour
  changes in either direction.
- **The server-fired event is inside a `try/except` inside a helper.** A failure logs a
  warning; a completed Sleeper trade is never undone by an analytics write. Removing the
  single call site removes the event.
- **The `surface` prop is the one thing with a compile-time edge.** It ships optional and
  is tightened to required only in the close-out commit, once all four mounts are plumbed.
  Rolling back that one-line type change restores the optional form and every mount still
  compiles.
- **No schema, no migration, no route contract, no flag default, no UI.** There is
  nothing to un-migrate and nothing for a user to notice in either direction.

---

## 8. Risks carried from the HLD

| # | Risk | Sev | Mitigation |
|---|---|---|---|
| **R3** (HLD) | Client wired before the taxonomy is registered → every new event counted-and-dropped behind 200s, and a plausible dashboard with no rows. Three live instances already in the tree. | **High** | The taxonomy commit is **first** and owns both registry files exclusively. `dropped == 0` + exact `set(by_type)` are the automated guard; flat health counters are the manual one. |
| **R4** (HLD) | DAU/WAU step-change on ship day if the impression events land as INTENT. Every retention and churn series breaks at that seam. | **High** | `NON_INTENT_EVENTS` additions are mandatory and in the same commit; a dedicated test pins them; post-ship seam check. |
| **R11** (HLD) | `league_view` double-fires — `LeagueSummaryScreen` runs two parallel queries with `placeholderData`. | Med | `firedRef` guard + `query.isFetched` trigger; verified on sim by counting rows for one visit (A2). |
| **R12** (HLD) | The Maestro waiver is invalidated by an accidental edit to `04-tabs-navigation.yaml` or `smoke/09-league.yaml`. | Med | Neither file is in any agent's ownership list; both are listed must-pass-unmodified; a diff to either is a review stop (R12/A9). |
| — | `outlook.odds` is OFF, so `outlook_shown` is `false` on every row until the flag flips. | Low | Correct and honest; recorded in the addendum so nobody reads the constant `false` as a bug. |
| — | `tab_selected` is high-frequency (queue cap 500, batch 50, flush 10 s). | Low | Small props, well inside `MAX_PROPS_BYTES`; `trimQueue` drops non-critical oldest-first and none of these is `FUNNEL_CRITICAL`, so pressure degrades gracefully. |
| — | `transaction_id` is an external identifier in an analytics prop. | Low | Server-fired props bypass `_scrub_pii` (client-only). It is a Sleeper transaction id, not a person; the runbook's reconciliation path wants it. **No user id is included** — `their_user_id` is deliberately excluded. |
| — | `experiment_exposed` misses direct `useFeatureFlags.getState().flags[k]` reads. | Low | The only live experiment overlays `onboarding.*` keys, which are consumed exclusively through the three instrumented helpers (that is the kill-switch contract). Limitation recorded in the addendum rather than fixed by widening the blast radius into files this agent does not own. |
