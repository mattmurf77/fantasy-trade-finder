# PRD — P1-9 · Quality-gated `trade_found` push (audit A-18)

> **Status:** REQUIREMENTS ONLY — no source file is changed by this document.
> **Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`,
> branch `p1-remediation-2026-08-11` @ `ab9368f`.
> **Companion:** [`LLD-p1-9.md`](LLD-p1-9.md) — diff sites, predicates, parameters, corrections.
> **Inputs:** [`plan-p1-9.md`](plan-p1-9.md), [`scope-p1-9.md`](scope-p1-9.md),
> [`HLD-p1.md`](HLD-p1.md) (wave B, owner **B2**), [`DECISIONS-p1.md`](DECISIONS-p1.md).
> **Gate posture:** **FULL GATES.** New feature-flag surface, two new cross-client enum
> values, and a notification that reaches a user outside the app. Per root `CLAUDE.md`, an
> agent never self-selects express.

## Contents

- [1. Problem statement (corrected)](#1-problem-statement-corrected)
- [2. What this ships, and what it deliberately does not](#2-what-this-ships-and-what-it-deliberately-does-not)
- [3. User-visible behaviour](#3-user-visible-behaviour)
- [4. Acceptance criteria](#4-acceptance-criteria)
- [5. Maestro flow specs](#5-maestro-flow-specs)
- [6. Docs impact](#6-docs-impact)
- [7. Operator parameter gates](#7-operator-parameter-gates)
- [8. Staged rollout and graduation](#8-staged-rollout-and-graduation)
- [9. Rollback](#9-rollback)
- [10. Blockers and dependencies](#10-blockers-and-dependencies)

---

## 1. Problem statement (corrected)

**The audit's finding is stale as written and must not be carried into the build.**

`04-priority-backlog.md` §P1-9 / `06-resolutions.md` row A-18 assert *"no new-trade
notification."* Verified false at `ab9368f`: F10's `deck_replenished` push exists
(`backend/server.py:15797-15803`), `deck.replenishment` is **`true`**
(`config/features.json:148`), and `_run_weekly_replenishment` (`backend/server.py:15751-15808`)
fires weekly for every active user-league.

**The true finding:**

> **The only new-trade push that exists is calendar-driven, quality-blind, and opted out by
> default.**
>
> - **Calendar-driven.** It fires on a weekday gate (`replenish_weekday`,
>   `backend/trade_service.py:373`), not on anything happening in the league.
> - **Quality-blind.** Its only condition is `deck_size > 0` (`backend/server.py:15790`).
>   Whether the deck contains one great trade or ten mediocre ones, the push is identical.
> - **Opted out by default.** The kind is deliberately mapped to the `reengagement` bucket
>   (`backend/database.py:9847-9850`), and `notif.reengagement_default_off`
>   (`config/features.json:123` = `true`) forces that bucket to `0` for any user with no
>   stored pref row (`backend/database.py:9853-9871`). A user who never opened Settings
>   **never receives it.**

Meanwhile the one honest, non-model quality signal the product already collects is invisible
outside the deck: `_inject_likes_you_cards_impl` (`backend/server.py:2813-2936`, flag
`trade.likes_you` = `true`) mirrors leaguemates' `like` decisions into the user's deck, but
`load_recent_league_likes` (`backend/database.py:4154-4200`) has **exactly one caller**
(`backend/server.py:4894`). A real person has said *yes* to a trade for your players, and the
product's only way of telling you is to hope you come back and tap Find a Trade.

**What P1-9 does about it.** One push kind, `trade_found`, whose trigger is **another human's
revealed intent** — a leaguemate's `like` whose mirror is still actionable on your roster —
delivered on the existing dispatcher, caps and quiet-hours machinery, behind a default-OFF
flag and a default-ON dry run.

**The quality gate is the feature.** The delivery path is nearly free (`_send_typed_push`
already does prefs, caps, quiet hours and device fan-out). The work is the gate, the dry run,
and the measurement. Nine conjunctive clauses, specified as evaluable predicates in
[`LLD-p1-9.md` §3](LLD-p1-9.md#3-the-nine-gate-clauses-as-evaluable-predicates).

---

## 2. What this ships, and what it deliberately does not

### Ships

| | |
|---|---|
| A new push kind `trade_found` and a new `notifications.type` value `trade_found` | two cross-client enum values, both with **silent** failure modes |
| `_run_trade_found_pass` inside the existing `POST /api/cron/daily-tick` | no new route, no new cron, no new schedule, no new `CRON_SECRET` consumer |
| One new feature flag `notif.trade_found`, default **OFF** | the round's **only** real kill switch (`HLD-p1.md` §F R-1) |
| Eight `model_config` knobs, `PUT /api/admin/config`-changeable without a deploy | including `trade_found_dry_run`, default **ON** |
| An extracted, shared actionability predicate | so the deck and the push can never disagree about what "actionable" means |
| `dedup_key` in every push's Expo payload, and `push_opened` fired for the first time ever | lights `push_open_rate`, permanently `"dark"` today (`backend/analytics_queries.py:479`, `:501`) |
| An inbox row written **before** the push and independent of it | the only artifact a simulator can assert, and the only thing a push-declining user ever sees |

### Does not ship

- **No model score anywhere in the trigger.** No `composite_score`, no `fairness_score`, no
  mutual-gain threshold. Those order the deck; they are not evidence that a trade is worth
  interrupting someone for, and a threshold on them is a product judgement dressed as a
  number.
- **No new analytics event name.** `push_sent` gains a new *value* of `kind`; `push_opened` is
  registered-and-dark (`backend/analytics_taxonomy.py:68`, props `:213`) and merely gets lit.
  P1-9 therefore never touches `analytics_taxonomy.py` — the round's most contended file.
- **No schema change**, no migration, no index.
- **No second quality-blind weekly push next to F10's.** The cross-kind quiet period exists
  precisely to prevent that.
- **No web edit.** The web inbox degrades safely (generic glyph, inert tap, no error —
  verified, [`LLD-p1-9.md` §1 C8](LLD-p1-9.md#c8--hld-f-r-6-dead-notification-tap-on-web-is-answered-it-degrades-safely)).

---

## 3. User-visible behaviour

| Actor | What they experience |
|---|---|
| **Recipient (push allowed, all gates pass)** | One push. Copy names the concrete trade — **[P-5](#7-operator-parameter-gates)** decides how much it reveals about the leaguemate. Tapping it opens the **Trades** tab. A matching row appears in the bell. |
| **Recipient during quiet hours (22:00–08:00 local)** | No banner at night. The push is queued (`notification_queue`) and drains into the single 08:00 `bundle_summary` — existing behaviour, inherited, unchanged. The bell row is already there in the morning. |
| **Recipient with the bucket toggled off** | **No push. The bell row still appears.** They can still find out; they just chose not to be interrupted. |
| **User who declined the push primer entirely** | Never receives a push. Still gets the bell row — the only channel independent of push permission, prefs, quiet hours and the OS. |
| **User whose leaguemate liked something stale, or that they already saw or swiped** | Nothing. Silently. This is the gate working. |
| **A user P0-1 just backfilled into `unlocked`** | **Nothing, structurally.** The trigger is someone *else's* like; no change in a user's own progression state can fire this push. Belt and braces: a device token must be ≥ `trade_found_grace_hours` old **and** the user must have returned since minting it, and only likes inside `trade_found_max_age_days` count. **A user's first-ever push from this product is never a `trade_found`.** |
| **Counterparty (the leaguemate who liked)** | Nothing changes for them. They are not notified, not named to anyone but the recipient, and their like is not re-surfaced. |
| **Everyone, while dry-run is on** | **Nothing at all.** No push, no bell row, no DB write. The feature's entire first release is counters in a cron response. |
| **Everyone, while the flag is off** | Byte-identical to today, including the `daily-tick` response body. |

---

## 4. Acceptance criteria

**33 criteria, each independently testable.** Backend cases run in
`backend/tests/test_trade_found.py` (new) on the isolated in-memory SQLite harness that
`backend/tests/test_notif_teardown.py` establishes for cron tests, seeding likes with the
helper shape from `backend/tests/test_deck_replenishment.py`. Mobile cases run under
`mobile/.maestro/flows/p1-9-trade-found-inbox.yaml` (§5) or the named manual check.

**The construction rule that makes the negative criteria non-vacuous:** every blocking case
(**AC-8 … AC-21**) starts from **AC-3's happy-path fixture** and breaks **exactly one**
clause. A suite that only tested the happy path would pass identically against a gate
accidentally short-circuited to "always send"; a suite of zero-assertions built from
independent fixtures would pass against a gate that never fires for an unrelated reason.
One-clause-delta from a fixture proven to send is what makes "0 pushes" mean something.

### A. Flag, dry run, and the happy path

| # | Criterion | Proof |
|---|---|---|
| **AC-1** | **Flag OFF is byte-identical.** With `notif.trade_found` false and a perfectly qualifying candidate seeded: the `daily-tick` response contains **no** `trade_found` key; zero `notification_events_log` rows; zero `notifications` rows; `_send_expo_push` never called. | pytest |
| **AC-2** | **Dry run writes nothing.** Flag ON, `trade_found_dry_run = 1`, one qualifying candidate: `dry_run_would_push == 1`, `pushed == 0`, **zero** `notification_events_log` rows, **zero** `notifications` rows, `_send_expo_push` never called. | pytest |
| **AC-3** | **Happy path.** Flag ON, dry run off, one qualifying candidate: exactly **1** Expo send; **1** `notification_events_log` row with `kind='trade_found'` and `dedup_key` matching `lk:{league_id}:{sig}`; **1** `notifications` row with `type='trade_found'`; **1** `push_sent` `user_events` row with `props.kind == 'trade_found'`; response `pushed == 1`. | pytest |
| **AC-4** | **One push per user per run, newest like wins.** Two qualifying candidates for one user in two leagues: exactly **1** Expo send, describing the candidate whose `like.created_at` is newest; the other is counted (not silently lost). | pytest |
| **AC-5** | **Idempotence.** Running `daily-tick` twice in a row: the second run pushes **0** and creates **no** duplicate inbox row. | pytest |
| **AC-6** | **The inbox row survives every push suppression path.** With (a) the pref bucket off, (b) no device tokens registered: **1 inbox row, 0 pushes** in each case. The inbox write happens **before** the push attempt. | pytest |
| **AC-7** | **Blast cap binds.** 60 qualifying users with `trade_found_max_per_tick = 50`: exactly **50** pushed, the remaining 10 counted in `blocked_max_per_tick`. | pytest |

### B. Negative criteria — each gate clause proved to BLOCK, one at a time

*How you prove a gate that should mostly NOT fire is working: assert the blocks, by reason,
each isolated from a fixture that is otherwise proven to send.*

| # | Clause | One-clause delta from AC-3 | Assert |
|---|---|---|---|
| **AC-8** | **G2** activity | the pair's last deck activity is older than `trade_found_active_days` | pair **not enumerated**; `eligible_pairs` excludes it; 0 pushes |
| **AC-9** | **G3** intent | no leaguemate `like` exists | `candidates == 0`, 0 pushes |
| **AC-10** | **G3** age | the like is `trade_found_max_age_days + 1` old | `blocked_stale == 1`, 0 pushes |
| **AC-11** | **G3** settling | the like landed `trade_found_min_like_age_minutes − 1` ago | `blocked_stale == 1`, 0 pushes |
| **AC-12** | **G4** roster | the counterparty's give player is no longer on their roster | `blocked_unactionable == 1`, 0 pushes |
| **AC-13** | **G4** untouchables | the mirrored give side intersects the user's untouchables | `blocked_unactionable == 1`, 0 pushes |
| **AC-14** | **G4** not-interested | the mirrored receive side intersects the user's not-interested list | `blocked_unactionable == 1`, 0 pushes |
| **AC-15** | **G5a** already shown | a `trade_impressions` batch exists with `shown_at` **after** the like | `blocked_seen == 1`, 0 pushes |
| **AC-16** | **G5b** already swiped | the user already has a `trade_decisions` row for the mirrored (give, receive) key | `blocked_swiped == 1`, 0 pushes |
| **AC-17** | **G6a** cooldown | a `trade_found` was sent 2 days ago, `trade_found_cooldown_days = 7` | `blocked_cooldown == 1`, 0 pushes |
| **AC-18** | **G6b** cross-kind | a **`deck_replenished`** was sent 2 days ago, `trade_found_global_quiet_days = 5` | `blocked_quiet == 1`, 0 pushes — **this is the "one great push a week" assertion, and the direct answer to R2 (double-notification with F10)** |
| **AC-19** | **G6** lifetime dedup | a `notification_events_log` row already exists for the same `lk:{league}:{sig}` (any age, e.g. 200 days) | 0 pushes, **forever** |

### C. The backfill guard — proving a P0-1-backfilled user never receives this push

| # | Criterion | Proof |
|---|---|---|
| **AC-20** | **G7 grace.** Device token `created_at` is 2 hours old, `trade_found_grace_hours = 48`, everything else qualifies: `blocked_grace == 1`, 0 pushes. | pytest |
| **AC-21** | **G7 must-have-returned.** Token is 5 days old but `users.last_active_at` **predates** the token (granted permission, never came back): `blocked_grace == 1`, 0 pushes. | pytest |
| **AC-22** | **Structural proof — a progression-state change produces nothing.** Simulate the P0-1 backfill on a fixture with **no leaguemate like**: flip `unlocked_formats`, mint a fresh device token, and drive `/api/rankings/progress` through its first-unlock branch. Assert `candidates == 0` and **0** `trade_found` sends. Then add a 90-day-old like and re-run: still **0** (`blocked_stale`). *This is the criterion that proves the design cannot re-create the surprise-push problem P0-1 deliberately avoided by suppressing its own backfill's fan-out.* | pytest |

### D. Regression — the parts that touch shared code

| # | Criterion | Proof |
|---|---|---|
| **AC-23** | **Extraction parity.** A table-driven differential test feeds identical fixture rows to `_likes_you_actionable` and to a verbatim copy of the pre-extraction predicate, asserting identical accept/reject on every row (empty sides, roster moved on either side, untouchable hit, not-interested hit, clean pass). Plus: every existing likes-you test stays green. **If parity cannot be made clean, the extraction is not taken** — the fallback (duplicate + binding comment) is recorded in the scope block. | pytest |
| **AC-24** | **Cap-regime regression.** The `_freq_cap_blocks` change (dedup gate and window cap both evaluated instead of the dedup branch short-circuiting) is **inert for every existing kind**: `deck_replenished` is still blocked by a prior dedup row and unaffected by any window; `winback_matches` is still capped 1-per-7-days; `first_match` still fires at most once per lifetime. Additionally: changing `trade_found_cooldown_days` in `model_config` mid-run changes the effective cap **without a restart** (the knob is not deploy-only). | pytest |
| **AC-25** | **Payload regression.** For an existing kind (`new_match`): `title` and `body` are byte-identical to before, and `data` differs **only** by the added `dedup_key`. | pytest |
| **AC-26** | **New payload shape.** A `trade_found` Expo message's `data` contains `type == 'trade_found'`, `league_id`, and a non-null `dedup_key`. | pytest |
| **AC-27** | **Quiet-hours deferral.** With the user's local time at 23:00: **0 Expo sends**, exactly **1** `notification_queue` row whose `deliver_after` is the next local 08:00, `queued_quiet == 1`. The morning drain then produces one `bundle_summary` and back-logs `trade_found` + its `dedup_key` so the caps stay accurate. | pytest |
| **AC-28** | **Copy constraints.** The rendered title and body contain **no emoji** (regex assert), no countdown, and no "come back"/"we miss you" language, and they name concrete inventory. *The specific wording is [P-5](#7-operator-parameter-gates); these constraints hold for every option.* | pytest |

### E. Measurement and cross-client

| # | Criterion | Proof |
|---|---|---|
| **AC-29** | **`push_opened` fires exactly once per tap**, carrying `kind` and a non-null `dedup_key`, from **both** the cold-start replay and the live listener, deduped by notification identifier so a warm tap surfacing through both paths counts once. | manual device check (see AC-33 note) + a unit check on the dedupe guard |
| **AC-30** | **`platform` is not NULL** on the resulting `user_events` row (device platform is a server-derived column, not a prop — the direct regression check for the incident that motivates the prop-spec regime), and `GET /api/analytics/health` shows `dropped_unknown_type` flat. | manual: background the app ≥10 s to flush, then query |
| **AC-31** | **Counters are attributable.** For a seeded population containing one of each blocking condition, the response distinguishes `candidates == 0` (density) from `candidates == N, blocked_X == N` (gate) — every blocked user lands in exactly **one** `blocked_*` bucket, and the buckets sum with `candidates` to `users_considered`. *This is the single most valuable output of the item and it is asserted, not assumed.* | pytest |
| **AC-32** | **Cross-client degradation is documented and true.** A client that does not know the kind performs **no navigation** and logs nothing (`resolveNotificationTarget` → `null`); the web inbox renders the generic bell glyph and the tap is inert (`web/js/app.js:4676-4681`, `:4830`). Both recorded in `docs/cross-client-invariants.md`. | code assertion + doc row |
| **AC-33** | **The push leg is verified on a real device or not at all.** Before graduating past dry run, the operator sends themselves one via the allowlist and confirms: banner copy, tap → Trades, quiet-hours deferral after 22:00 local, and a `push_opened` row landing. **Simulators never register a token** (`mobile/src/hooks/usePushNotifications.ts:89`) and the iOS permission alert is a SpringBoard surface — the same waiver `plan-p0-1.md` §6.1 takes for the primer. | operator, logged in `TEST_LEDGER.md` |

**Existing suites that must stay green:** `backend/tests/test_notif_teardown.py`,
`backend/tests/test_deck_replenishment.py`, any suite asserting the `daily-tick` response
shape, and the likes-you deck tests. Command: `python3 -m pytest backend/tests/ -q`.
Mobile: `cd mobile && npx tsc --noEmit` (do **not** run `npm install`; `node_modules` is a
symlink) and `mobile/scripts/testid-lint.sh` exit 0.

---

## 5. Maestro flow specs

### What a simulator structurally cannot cover, stated first

`usePushNotifications` returns early on `!Device.isDevice`
(`mobile/src/hooks/usePushNotifications.ts:89`), so **a simulator never registers a token and
never receives an Expo push**, and the iOS permission alert lives outside the app hierarchy.
**No flow can cover the push leg.** Compensating coverage, three ways: (i) the inbox row is
written unconditionally by design, and *is* assertable — that design choice exists partly to
make this waiver defensible rather than convenient; (ii) the pytest matrix drives the full
gate and dispatcher server-side including the exact Expo payload; (iii) **AC-33**, one real
device send before graduation. **Any diff to the existing smoke flows invalidates this
waiver** — they are the regression proof.

Second honest bound: while `trade_found_dry_run = 1`, the pass writes nothing, so **the flow
never exercises the pass**. It exercises the rendering and routing of a `trade_found` inbox
row — which is exactly the part the push tap shares.

### New flow — `mobile/.maestro/flows/p1-9-trade-found-inbox.yaml`

Header per `mobile/.maestro/README.md`: `appId`, `# tc:`, `# profile: likes-you-waiting`,
`# flags: likes-you-waiting` (a **resolved fixture filename** under
`backend/tests/fixtures/flags/`, law 16 — prose values silently split cells and fall back to
defaults), `# source: docs/plans/audit-p1-remediation/PRD-p1-9.md`,
`tags: [p1-9, notifications]`.

**Selectors are `id:` only** (`testid-lint.sh` fails a text-selector tap). Text appears only
in bounded-regex `assertVisible`s, never as a tap target.

| Step | Action | Why |
|---|---|---|
| 1 | `launchApp: {clearState: true, clearKeychain: true, stopApp: true}` | Law 6 — the react-query cache is persisted; only a cold start proves fresh hydration |
| 2 | `extendedWaitUntil: visible: id: "signin.username-input"` → `tapOn` → `inputText: "qa_standard"` → **`assertVisible` the typed username** → `tapOn: id: "signin.continue-btn"` | Law 10 — a raced `inputText` submits a partial name; retries erase first so they stay idempotent |
| 3 | `extendedWaitUntil: visible: id: "leagues.row.<league_id>"` → `tapOn` same id | Standard preamble (`flows/smoke/03-trios.yaml`) |
| 4 | `extendedWaitUntil: visible: id: "tab.trades"` (timeout 30000) | Law 8 — the tab bar paints seconds before #244 launch routing settles; settle before any tap |
| 5 | `assertVisible: id: "topbar.bell"` → `tapOn: id: "topbar.bell"` | **New testID** (LLD D22; the reserved registry name, `docs/plans/mobile-testing/lld.md:313`). Opening the sheet triggers the server hydrate (`TopBar.tsx:118-141`) |
| 6 | **`assertVisible: id: "topbar.notif-row..*"`** | **The bell-row assertion — the only thing a simulator can assert when the push is suppressed.** Dynamic-prefix match; the row id is `topbar.notif-row.<db id>` (`TopBar.tsx:342`), which the lint resolves by static prefix (no allow-list entry needed) |
| 7 | `assertVisible: text: ".*wants.*"` (bounded regex against the seeded title) | Law 1 — text matchers are FULL-MATCH regex; assert a bounded fragment, never full copy. **The exact fragment follows [P-5](#7-operator-parameter-gates)** and must be re-derived from the shipped copy, not copied from this table |
| 8 | `takeScreenshot: p1-9__trade-found-inbox-row` **and eyeball it** | Law 23 — the only place the `trade_found` glyph (LLD D21) is verified as *not* the generic `DEFAULT_ROW_GLYPH` bell. A glyph regression is invisible to every assertion |
| 9 | `tapOn: id: "topbar.notif-row..*"` → `extendedWaitUntil: visible: id: "tab.trades"` + a Trades-tab content id | Proves the `V2_TRADE_KINDS` addition routes rather than no-ops. `onRowTap` (`TopBar.tsx:148-155`) shares `resolveNotificationTarget` with the push tap handler, **so the routing-table addition is covered even though the push is not** |
| 10 | Settings leg: navigate to Settings → `assertVisible: id: "settings.notif.trade-matches"` | Proves the opt-out the push depends on is reachable and labelled. Extend to all four ids when they land |

**Preconditions the flow depends on** — assert or fail loudly, do not discover at runtime:
`notif.tap_routing_v2` must be **true** in the resolved flags fixture (without it the bell
shows only the in-session feed and the rows are inert `View`s, `TopBar.tsx:115`, `:339-352`).
The profile does **not** need `notif.trade_found` — the flag gates the backend pass, and the
flow seeds the inbox row directly.

**testIDs added:** `topbar.bell` (new) · `settings.notif.trade-matches`,
`settings.notif.weekly-digest`, `settings.notif.reengagement`, `settings.notif.quiet-hours`
(new; the `Row` helper already accepts and forwards `testID`, `SettingsScreen.tsx:1449-1470`).
Reused: `topbar.notif-row.<id>` (dynamic prefix, already exists), `tab.trades`,
`signin.*`, `leagues.row.*`.

**Fixture:** `backend/tests/fixtures/profiles/likes-you-waiting.json` (new) with
`matches_seed: {mutual: 0, awaiting: 0, likes_you: 1}` and one `notifications_seed`
`trade_found` row — both seeder capabilities are new (LLD D25).

**Smoke-suite impact:** none of the 11 smoke flows asserts a notification kind, a bell row, or
the Settings notification block. Expectation: all green and **unmodified** — verify, do not
assume.

**Capture delta:** the new `p1-9__trade-found-inbox-row` screenshot; **plus `settings` and
`settings@two-leagues` if and only if [P-1](#7-operator-parameter-gates) lands the Settings
copy edit.** Run `mobile/scripts/screen-freshness.sh` and re-capture what it flags. Per
`HLD-p1.md` §A.5 these fold into the single consolidated **R1** pass at the end of the round,
not a separate run.

**Sim-gate tier: 2** (mobile logic touched, no material UI change) — the feature's own flow
plus the affected smoke subset. **Escalates to tier 1 if [P-1](#7-operator-parameter-gates)
lands the Settings copy change**, which is a visible screen change requiring
`mobile/scripts/screen-capture.sh --screen settings`. **The tier is not final until P-1 is
answered; declare it in `scope-p1-9.md` before the build starts.** Evidence:
`living-memory/TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json`; `githooks/pre-push`
enforces locally.

---

## 6. Docs impact

Row per `docs/CLAUDE.md` trigger. Every row is "updated" or "n/a because".

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **Updated** | `POST /api/cron/daily-tick` — the optional `trade_found` counters object, present only when the flag is on, mirroring how F10's `replenish` key is documented. **No route added, renamed, removed or contract-changed.** |
| `docs/data-dictionary.md` | **Updated** | Value-level only, no schema change: `notifications.type` gains `trade_found`, `notification_events_log.kind` gains `trade_found`. **And the stale enumeration is corrected in all three places** — `backend/database.py:812`, `:820`, `:8446` (A-33 rule; the plan cites only one). |
| `docs/config-reference.md` | **Updated** | Flag `notif.trade_found` (default, what ON does, kill-switch semantics, graduation criterion) **and** the eight `model_config` keys with defaults, units and direction-of-travel consequences. |
| `docs/cross-client-invariants.md` | **Updated** | **The load-bearing row.** Two new cross-client values — push `kind` `trade_found` (read by `deepLinks.ts` `V2_TRADE_KINDS`, the legacy set in `usePushNotifications.ts:200`, `TopBar.tsx` `ROW_GLYPHS`, and `web/js/app.js`'s renderer) and `notifications.type` `trade_found`. **Record the silent failure mode**: a client that misses the kind returns `null` from `resolveNotificationTarget` and the tap does nothing — no error, no log; the web inbox renders the generic bell and the tap is inert. |
| `docs/runbook.md` | **Updated** | New subsection modelled on *"Weekly deck replenishment (F10…)"* (`:296`): what the pass does, that it lives inside `daily-tick`, how to read the per-reason counters, how to run dry, **both** kill switches, and how to answer *"why did nobody get one this week?"* from `candidates` vs `blocked_*`. |
| `docs/glossary.md` | **Updated** | *likes-you* / *counterparty intent* is used across the deck engine and now the notification layer and is undefined. One entry. |
| `docs/plans/mobile-testing/lld.md` (Appendix A, testID registry) | **Updated** | Confirm `topbar.bell` (`:313`) and add the four `settings.notif.*` ids under `:329`. **Note in the ship notes that Appendix A `:311` and `mobile/src/components/CLAUDE.md:3` disagree about where the registry lives** — flagged, not arbitrated here. |
| `living-memory/LLD.md` | **Updated** | Two conventions shift: (1) *a push kind's cadence cap is a `model_config` key read at call time, not a literal in `_NOTIF_FREQ_CAPS`* — first time that map is live-tunable; (2) *`_send_typed_push` returns a delivery-status string* — first time the dispatcher reports outcome to its caller. |
| `docs/architecture.md` · `living-memory/HLD.md` | **n/a** | No module added, removed or re-wired; no data-flow change. A new function inside an existing cron endpoint, using existing loaders and the existing dispatcher. |
| `docs/design/design-system.md` + `components.md` | **n/a** | No new component, no new token. The NotificationRow glyph map already has a spec (#225); this adds one entry. **Re-read both before touching `TopBar.tsx`**, per `CLAUDE.md`. |
| ADR | **n/a** | Nothing of ADR weight — this rides an existing dispatcher and an existing cron. |
| `living-memory/DECISIONS.md` | **Updated** | Three entries, **ID allocated at write time in merge order** (nine claimants exist for `D-011`; `HLD-p1.md` §A.6): (1) the gate is counterparty intent only — no model score may trigger a push without an explicit operator decision, **and gate strength is coupled to the pref bucket**; (2) the inbox row is written even when the push is suppressed, which is also what makes the feature simulator-testable; (3) the bucket choice and its coupling rule. |
| `docs/business/analytics/2026-07-17-tracking-plan-v2.md` | **Updated (one line)** | `:14` lists `push_opened` as *"documented but dark"*; first emission makes that false. **No addendum required** — `analytics_taxonomy.py:9-10` conditions that on new client event **types**, and P1-9 adds none. |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | **On ship** | CHANGELOG records the `push_opened` first-emission **metric seam** with its date. TEST_LEDGER carries the pytest run, the sim run, **and the dry-run observation-window result**. |
| `living-memory/DEPENDENCIES.md` | **n/a** | No dependency added, bumped or removed. |
| `living-memory/GOTCHAS.md` | **Conditional** | Only if the build loses >30 min to something. The `_freq_cap_blocks` short-circuit (LLD C1) is a strong candidate — it is the kind of thing the next reader will re-derive painfully. |
| `screens/CLAUDE.md` | **Conditional** | Only if [P-1](#7-operator-parameter-gates)'s Settings copy edit lands and `settings` is re-captured. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a** | Dated artifact — record the outcome in CHANGELOG, do not rewrite the audit. **But** the corrected finding (§1) is worth one line in the round's ship notes: A-18 as filed was wrong, and the record should say so. |

---

## 7. Operator parameter gates

**Every row is a product judgement, not an engineering one.** Recommendations below are the
plan's, carried forward unchanged and explicitly **not settled**. Full consequence-of-moving
detail for the eight numeric knobs is in
[`LLD-p1-9.md` §8](LLD-p1-9.md#8-parameter-table--operator-decisions).

| Gate | Decision | Recommendation (not settled) | Blocking? | What it changes |
|---|---|---|---|---|
| **P-1** | **Which pref bucket does `trade_found` live in?** (a) `trade_matches` — default ON, maximum reach · (b) `reengagement` — default OFF, the `deck_replenished` treatment, ~nobody ever receives it · (c) unmapped — the user cannot turn it off | plan recommends **(a) conditional on the gate staying counterparty-intent-only**; records **(c) as "do not do this"** | **BUILD — and it is the round's loudest dependency** | **(a) adds `SettingsScreen.tsx` copy AND a fourth `PushPrimingModal` consent bullet to the diff, and escalates the sim gate from tier 2 to tier 1.** (b) adds neither. It also changes the R1 capture list. **Bucket strength and gate strength are one decision** — if the gate ever widens (P-2), the kind moves to `reengagement` in the same change. **Do not start the build until this is answered.** |
| **P-2** | **Gate strength:** intent-only, + a dual-board lane, or + a model-score threshold | plan recommends **A for v1, B specced and deferred, C never** | **BUILD** | The entire gate design |
| **P-3** | **The eight `model_config` defaults** (cooldown 7d · cross-kind quiet 5d · like age 7d · active 21d · grace 48h · min like age 30m · max per tick 50 · dry run ON) | plan recommends the values as listed | **BUILD** | All eight are `PUT /api/admin/config`-changeable without a deploy, so this is the cheapest gate to revisit — but they must have *a* value at build time |
| **P-4** | **Cross-kind quiet list** — the set `{deck_replenished, trade_found, winback_matches, winback_dormant, weekly_digest}` | plan's list as written | **BUILD** | Which other pushes crowd `trade_found` out (AC-18) |
| **P-5** | **Copy, and how much it reveals about a leaguemate** — name both, name the player only, or neutral. **Privacy dimension:** a lock-screen banner naming a leaguemate exposes their trade interest to anyone glancing at the phone | plan recommends **A**, notes **C fails the concrete-inventory guardrail outright**, and names **B** as the choice if lock-screen privacy outweighs clarity | **BUILD** | The push copy, the inbox row, and the Maestro text assertion (§5 step 7) |
| **P-6** | **Bell-row glyph** — the `match` glyph in ice, or its own stroke icon | plan recommends the `match` glyph | BUILD (one map entry) | `TopBar.tsx` `ROW_GLYPHS` |
| **P-7** | **`push_opened` INTENT or NON_INTENT** | plan recommends **leave INTENT** | release — **but routes into commit T1 if changed** | `analytics_queries.py` is P0-7-owned and frozen after T1; P1-9 must not edit it |
| **P-8** | **Rollout and graduation** (§8) | plan's sequence | release | The post-merge window |

---

## 8. Staged rollout and graduation

1. **Merge after P0-1**, with `notif.trade_found` **ON** and `trade_found_dry_run = 1`. The
   flag is on so the pass runs and counts; the dry run means nothing leaves the building.
2. **Wait `trade_found_grace_hours` past P0-1's deploy** before the observation window starts,
   so the backfilled cohort has settled and the baseline is not measured against a population
   that was ineligible by construction.
3. **Read the `daily-tick` counters daily for 14 days.** The question being answered is *how
   many candidates exist and which clause rejects them* — **not** "did it send".
4. **Graduate to real sends only if** `dry_run_would_push` ≤ 1 per user per week across the
   whole window **and** the per-reason `blocked_*` mix is legible (AC-31). Then: enable for the
   operator's own device-unit allowlist (`config/tester_allowlist.json`, the existing
   mechanism), **send yourself one and confirm AC-33**, then go general.
5. **If `candidates == 0` for the whole window:** ship it **OFF** and revisit after invite and
   density work (P1-3, P1-5). **Do not loosen the gate to make the counter move.** A gate that
   fires rarely because the trigger is scarce is working; the honest conclusion is that this
   feature's value is gated on adoption density, not that the gate is wrong.

**The failure mode to name in advance:** `dry_run_would_push` staying at 0 is
*indistinguishable from a broken gate* unless the `blocked_*` counters are read alongside it
(`HLD-p1.md` §F R-5). `candidates == 0` is density. `candidates == 40, blocked_seen == 40` is
a bug. That distinction is the reason the counters exist.

---

## 9. Rollback

Four levers, in escalating cost. **P1-9 is the only P1 item in the round with a real kill
switch** — for four of the seven, rollback is `git revert` (`HLD-p1.md` §F R-1).

| Lever | Effect | Deploy needed? |
|---|---|---|
| `trade_found_dry_run` → `1` via `PUT /api/admin/config` | The pass keeps computing and counting; **nothing is sent and nothing is written** | **No** |
| `notif.trade_found` → `false` | The pass never runs; `daily-tick` response byte-identical; zero reads | **No** (flag store), or one `config/features.json` commit |
| Any of the eight `model_config` knobs → a tighter value | Narrows the gate without stopping it (e.g. `trade_found_global_quiet_days` → 14) | **No** |
| `git revert` the P1-9 commit | Removes the kind, the pass, the flag, the extraction and the payload key | Yes |

**What rollback does *not* undo:** pushes already delivered, `notification_events_log` rows
already written (so lifetime dedup keys already spent stay spent), and the `push_opened`
metric seam — its first-emission date remains a discontinuity in DAU/WAU/retention and belongs
in the CHANGELOG regardless.

---

## 10. Blockers and dependencies

| # | Blocker | Status |
|---|---|---|
| **B1** | **P0 merges to `main` and the P1 branch rebases**; then every row of [`LLD-p1-9.md` §10](LLD-p1-9.md#10-re-verify-after-p0-merge) is answered **in writing in `scope-p1-9.md`**. A row that comes back "the premise no longer holds" stops the build. | Open — gate, not assumption |
| **B2** | **Wave A merges and releases `server.py`, `deepLinks.ts`, `SettingsScreen.tsx`, `seed_ui_test_db.py`.** P1-7 and P1-9 must never both hold `server.py`. | Open — `HLD-p1.md` §D |
| **B3** | **P0-1 is on `main`**, and the dry-run window starts no earlier than `trade_found_grace_hours` past its deploy. | Open |
| **B4** | **[P-1](#7-operator-parameter-gates) (pref bucket) answered.** It changes the file list (`PushPrimingModal.tsx` in or out — and B2 must claim that file explicitly, since it is not in its HLD ownership list), the sim tier (2 vs 1), the Settings copy, and the R1 capture list. **Build-blocking.** | Open |
| **B5** | **[P-2](#7-operator-parameter-gates), [P-3](#7-operator-parameter-gates), [P-4](#7-operator-parameter-gates), [P-5](#7-operator-parameter-gates), [P-6](#7-operator-parameter-gates) answered.** All build-blocking. | Open |
| **B6** | **Extraction parity (AC-23) proven clean**, or the documented fallback taken and recorded. | Open — build-time judgement |
| **B7** | **Two shared-code changes need reviewer assent**, both P1-9-owned but cross-cutting: `_freq_cap_blocks` non-exclusivity (LLD C1) and `_send_typed_push`'s return status (LLD C4). Both are inert for existing kinds and both are asserted (AC-24, AC-25). | Open — engineering, not operator |
