# P1-9 — Quality-gated `trade_found` push (audit A-18)

> **Status:** PLAN ONLY — no code written. Worktree `ftf-p1-remediation`, branch
> `p1-remediation-2026-08-11`, off `origin/main @ ab9368f`.
> **Source:** audit `04-priority-backlog.md` §P1-9, `06-resolutions.md` row **A-18**,
> evidence in `02-tier-a-briefs.md` §7 (Acquire Deck → Retention item 1).
> **Depends on:** P0-1 (push permission unblock) merged to `main` first. See §"Design" → *Composition with P0-1*.
> **Scope block:** [`scope-p1-9.md`](scope-p1-9.md).
> **Gate posture:** **full gates.** The change adds a feature flag and a new push kind,
> and its blast radius is outside the app. Bright lines enumerated in §"Surface changes".

## Contents

- [Verified current state](#verified-current-state)
- [Design](#design)
- [Exact change list](#exact-change-list)
- [Surface changes](#surface-changes)
- [Maestro delta](#maestro-delta)
- [Docs impact table](#docs-impact-table)
- [Test plan](#test-plan)
- [Risks and cross-item collisions](#risks-and-cross-item-collisions)
- [Operator checkpoints](#operator-checkpoints)

---

## Verified current state

Every claim below was read from **this** worktree at `ab9368f`. Nothing is taken on the
audit's word, and nothing is taken on a comment's word (A-33 rule) — where a comment and
the code disagree, the code is cited.

### The push machinery, mapped end to end

The audit's "the push system is well built" is correct and, if anything, understated.
There are **two layers**, and the high-level one already implements every gate this
feature needs.

| Concern | Where | What it actually does |
|---|---|---|
| Raw transport | `backend/server.py:15240-15277` `_send_expo_push(messages)` | POSTs to `https://exp.host/--/api/v2/push/send`, chunks at 100, wrapped in `_api_obs.observe_call("expo_push","send")`, swallows everything. Knows nothing about prefs, caps or quiet hours. |
| **The entry point** | `backend/server.py:15344-15412` `_send_typed_push(user_id, kind, *, title, body, data, dedup_key)` | 5 steps in order: (1) `get_notification_prefs`, (2) **bucket gate**, (3) **frequency cap**, (4) **quiet-hours deferral**, (5) fan out to every device + `log_notification_send` + `record_event("push_sent", props={kind, dedup_key})`. Non-throwing throughout. |
| Bucket map | `backend/database.py:9830-9851` `NOTIF_KIND_TO_BUCKET` | 14 kinds → 3 buckets (`trade_matches` · `weekly_digest` · `reengagement`). A kind **absent** from this map is treated as transactional and is never bucket-gated. |
| Pref defaults | `backend/database.py:9819-9825` `NOTIF_PREF_DEFAULTS` + `:9853-9871` `_notif_pref_effective_defaults()` | All three buckets default ON **except** that flag `notif.reengagement_default_off` (**`config/features.json:123` = `true`**, same in `backend/tests/fixtures/flags/release.json:124`) forces `reengagement = 0` when no row is stored. Stored values always win. |
| Window frequency caps | `backend/server.py:15212-15217` `_NOTIF_FREQ_CAPS` | `winback_matches (7d,1)` · `winback_dormant (30d,1)` · `finish_ranking (30d,1)` · `season_start (365d,1)`. Kinds absent from the map are **uncapped**. |
| Per-event dedup caps | `backend/server.py:15230-15237` `_NOTIF_DEDUP_CAPS` + `:15312-15327` `_freq_cap_blocks` | For a kind in this set, `notification_dedup_sent(user, kind, dedup_key)` is a **lifetime** gate: any prior row with that key blocks forever. |
| Quiet hours | `backend/server.py:15280-15288` `_local_hour_in_quiet_window` (22:00–08:00) + `:15291-15309` `_next_8am_utc` | Deferred pushes go to `notification_queue` with `deliver_after = next local 08:00`. tz falls back to `America/New_York` on any resolution failure. |
| Quiet-hours drain + bundling | `backend/server.py:15966-15994` (inside `cron_hourly_tick`) + `:15862-15889` `_summary_push` | Collapses every queued row for a user into **one** `bundle_summary` push and back-logs each original kind + `dedup_key` so caps stay accurate. |
| tz acquisition | `backend/server.py:15427-15458` `_sync_tz_from_header` (flag `notif.tz_sync` = **on**) | Adopts `X-User-TZ` into `notification_prefs.tz` at session-init and register-device, but only while the stored value is still the default. |
| Device token storage | `backend/database.py:1212-1218` `device_tokens` (`user_id`, `device_token` PK, `platform`, **`created_at`**, `last_seen_at`) written by `POST /api/notifications/register-device` (`backend/server.py:15461-15493`); read by `load_device_tokens_for_users` (`backend/database.py:9282-9305`) | `created_at` is load-bearing for this plan (§Design G7). |
| Send log | `backend/database.py:1249-1256` `notification_events_log` (indexed `user_id, kind, sent_at`) | The substrate every cap reads. Appended by `log_notification_send`. |
| In-app inbox (separate!) | `backend/database.py:817-826` `notifications` + `create_notification` (`backend/database.py:8439-8474`) | The bell feed. **Only match events write to it** (`backend/server.py:10068`, `:10077`, `:13009`, `:13018`). `_send_typed_push` does **not** write an inbox row. |
| Cron surface | `backend/server.py:15811-15824` header; `_require_cron_auth` `:15840-15859` | Three endpoints — `realtime-tick` (15 min), `hourly-tick`, `daily-tick`. `X-Cron-Secret`; fails **closed** in prod when unset. `.github/workflows/render-cron.yml` drives them. |
| Client permission path | `mobile/src/hooks/usePushNotifications.ts:85-139` | Gated on `enabled`. On `undetermined` it hands off to `usePushPriming` → `PushPrimingModal`; on `granted` it silently re-registers; on `denied` it **never re-prompts**. `Device.isDevice` guard at `:89` — **simulators never register and never receive a push.** |
| Permission gate value | `mobile/src/navigation/RootNav.tsx:266-267` `pushEnabled = everUnlockedRef.current \|\| progressQuery.data?.unlocked === true`, passed at `:279-283` | This is the P0-1 dependency. |
| Consent copy | `mobile/src/components/PushPrimingModal.tsx:56-69` | Promises exactly three things: *"A new trade match is generated for you · A leaguemate accepts your match · A match is about to expire"*, plus the quiet-hours explanation. |
| Tap routing | `mobile/src/utils/deepLinks.ts:247-262` (V2 kind sets, flag `notif.tap_routing_v2` = **on**) + `:273-286` `resolveNotificationTarget` + `:303-325` `routeNotificationTap`; legacy sets inline at `mobile/src/hooks/usePushNotifications.ts:186-209` | Unknown kind ⇒ `null` ⇒ **no navigation at all**. Both the cold-start replay (`:64-82`) and the live listener (`:166-213`) resolve through the same map and dedupe on notification identifier. |
| Opt-out surface | `mobile/src/screens/SettingsScreen.tsx:986-1006` (three bucket rows) + `:1010-1026` (quiet hours + tz) + `:964-984` (iOS-denied recovery banner, flag `notif.denial_recovery`) | Row copy for the `trade_matches` bucket today: *"New matches, counter-offers, league activity."* **None of these rows carries a `testID`** — the `Row` helper accepts one (`:1450-1459`) but no caller passes it. |

### Every push kind that actually ships today

Enumerated by reading each `_send_typed_push` call site, not the bucket map:

| Kind | Bucket | Fired from | Cadence gate |
|---|---|---|---|
| `first_match` / `new_match` | `trade_matches` | `backend/server.py:10116` / `:10125`, chosen by `_match_push_kind` (`:15330-15341`) | dedup: `"lifetime"` / `match_id` |
| `match_accepted` | `trade_matches` | `backend/server.py:12891` | dedup `accept:{match}:{actor}` |
| `match_expiring` | `trade_matches` | `backend/server.py:15909` (`cron_realtime_tick`, >48h undecided) | dedup `match_id` |
| `league_member_joined` | `trade_matches` | `backend/server.py:14788` | dedup `joined:{joiner}:{peer}` |
| `league_member_unlocked_trades` | `trade_matches` | `backend/server.py:6254` (first-unlock transition) | dedup `unlock:{user}:{peer}` |
| `weekly_digest` / `pending_review` | `weekly_digest` | `backend/server.py:16026` / `:16040` (Tue/Wed 09:00 local) | 1/6d via `count_notification_sends_since` |
| `season_start` | `reengagement` | `backend/server.py:16088` (Aug 25 only) | window (365d, 1) |
| `finish_ranking` | `reengagement` | `backend/server.py:16099` | window (30d, 1) |
| `winback_dormant` | `reengagement` | `backend/server.py:16126` / `:16134` (flag `notif.honest_winbacks`) | window (30d, 1) + lifetime stop after 3 unanswered |
| `winback_matches` | `reengagement` | `backend/server.py:16147` | window (7d, 1) |
| `deck_replenished` | `reengagement` | `backend/server.py:15797` (F10, flag `deck.replenishment`) | dedup `{league}:{iso_week}` |
| `bundle_summary` | — (raw send) | `backend/server.py:15979-15994` | n/a |
| `counter_offer` | `trade_matches` | **no call site — dead kind** | — |

**Thirteen live kinds, not twelve.** The primer's own comment
(`mobile/src/components/PushPrimingModal.tsx:57-59`) already records that `counter_offer`
was promised and never fires.

### The thing that most changes the shape of this item

**F10 already ships a "your new deck is ready" push, and it is effectively muted.**
`_run_weekly_replenishment` (`backend/server.py:15751-15808`) generates a deck per active
user-league once a week and sends `deck_replenished` whenever `deck_size > 0` —
**unconditional on quality**. `deck.replenishment` is **`true`** in `config/features.json:148`
and `release.json:148`. But the kind is deliberately mapped to the `reengagement` bucket
(`backend/database.py:9847-9850`, comment: *"Deliberately in the re-engagement bucket so
`notif.reengagement_default_off` applies"*) — and that flag is on. So a user with no stored
pref row **never receives it**. Verified as intended behaviour by
`backend/tests/test_deck_replenishment.py:249` `test_reengagement_default_off_policy_gates_push`.

Two consequences:

1. P1-9 is not "there is no new-trade push." It is **"the only new-trade push is
   calendar-driven, quality-blind, and opted out by default."** The gap the audit names —
   *notify on genuinely **new** trades* — is real, but the fix must not be a second
   quality-blind weekly push next to the first one.
2. Whatever `trade_found` becomes, it must be **cadence-aware of `deck_replenished`**, or a
   user who opts back into re-engagement gets two "we found you trades" pushes in one week.
   §Design G6 handles this.

### The one honest, non-model quality signal that already exists

`_inject_likes_you_cards_impl` (`backend/server.py:2813-2936`, flag `trade.likes_you` =
**`true`**, `config/features.json:30`) mirrors leaguemates' **`like` decisions** into the
user's deck: their give ⊆ their current roster, their receive ⊆ the user's current roster,
respecting untouchables (`:2880`) and not-interested (`:2884`), skipping anything the user
already swiped (`:2893`), capped at `_LIKES_YOU_CAP = 3` (`:2798`). Its data source is
`load_recent_league_likes(league_id, exclude_user_id, days=90)`
(`backend/database.py:4154-4200`) — a plain read of `trade_decisions` where
`decision = 'like'`.

**A one-sided like is invisible until the user generates a deck.** There is no push, no
inbox row, and no cron sweep for it anywhere in the repo (`load_recent_league_likes` has
exactly one caller: `backend/server.py:4894`). A real leaguemate has said *yes* to a trade
for the user's players, and the product's only way of telling them is to hope they come
back and tap Find a Trade.

### Drift from audit

| Audit claim | Verified state at `ab9368f` | Verdict |
|---|---|---|
| "No new-trade notification" (`04-priority-backlog.md` P1-9) | Partly stale. `deck_replenished` exists, is flag-**on**, and is a new-deck push — but is quality-blind and bucket-muted by `notif.reengagement_default_off`. | **Amended.** The finding stands on *quality* and *default reachability*, not on absence. |
| "The push plumbing is excellent" (`02-tier-a-briefs.md:332`) | Confirmed. Prefs, three buckets, two cap regimes, quiet-hours queue + morning bundling, tz sync, cold-start tap replay, denial-recovery banner. | **Holds.** |
| "the 12 push kinds with their caps and dedup" (`05-appendix.md:13`) | 14 kinds in the bucket map, **13 with live call sites**, plus `bundle_summary` sent raw. `counter_offer` is mapped but dead. | **Drift (+1/+2).** |
| "'Fresh trades arrive after waivers' is the only temporal hook" (`02-tier-a-briefs.md` §7 Retention) | Understated: the F10 cron behind that copy is live, generating decks weekly. The *push* is what is muted. | **Amended.** |
| Audit's Retention item is scored **M** effort | Confirmed M, but for a different reason than assumed: the delivery path is ~free (existing dispatcher); the *gate*, the *dry-run*, and the *measurement* are the work. | **Holds.** |
| `06-resolutions.md:103` "riding the EXISTING cap and quiet-hours machinery" | Both exist and are directly reusable via `_send_typed_push`. | **Holds.** |
| Audit line refs for the push layer | Not cited in the audit at all (A-18 carries no `file:line`). All references in this plan are first-hand. | n/a |

### Measurement is currently blind — and the fix is free

`push_opened` is **already registered**: `backend/analytics_taxonomy.py:68`
(`ALLOWED_CLIENT_EVENTS`) with props `frozenset({"kind","dedup_key"})` at `:213`. **No
client fires it** — `mobile/src/hooks/usePushNotifications.ts` contains zero `track()`
calls. `backend/analytics_queries.py:478-501` renders the push funnel with
`push_open_rate` permanently `"dark"` and an unconditional caveat.

Per `plan-p0-7.md` §3 the default-deny trap applies to **new names**; `push_opened` is not
new, so **no `analytics_taxonomy.py` commit is required before wiring it**. That is verified,
not assumed — the name is in the frozenset and has a `CLIENT_EVENT_PROPS` row, which is the
exact pair `analytics_ingest.py` checks.

One gap blocks the `dedup_key` prop from ever being non-null: `_send_typed_push` builds the
Expo payload as `{**(data or {}), "type": kind}` (`backend/server.py:15393-15399`) — the
`dedup_key` argument is logged and capped on, but **never put in `data`**, so the client
cannot read it back.

---

## Design

### The quality gate (this is the feature)

The gate is a **conjunction**. Every clause must hold. Any clause failing is a silent,
counted no-op — the pass never "almost" sends.

The gate's organising principle: **the trigger is another human's revealed intent, never a
model score, and never a change in the user's own account state.** That single choice does
most of the work here — it makes the push truthful by construction ("someone actually wants
this"), it makes it un-spammable at the source (a like is a scarce human act), and it makes
the P0-1 backfill structurally incapable of generating one (§Composition with P0-1).

| # | Clause | Predicate | Reads |
|---|---|---|---|
| **G1** | **Feature is on** | `notif.trade_found` enabled | `feature_flags` |
| **G2** | **Recipient is a real, recently-active deck user** | `(user_id, league_id)` appears in `load_active_deck_user_leagues(days=trade_found_active_days)`; `league_id != "league_demo"`; user id is not `demo_*`/test | `backend/database.py:4253-4281` (the same eligibility query F10 uses, `backend/server.py:15768`) |
| **G3** | **Counterparty intent exists** | ≥1 row from `load_recent_league_likes(league_id, exclude_user_id=uid, days=trade_found_max_age_days)` | `backend/database.py:4154-4200` |
| **G4** | **The trade is actionable right now** | their give ⊆ their current roster **and** their receive ⊆ the user's current roster; mirrored give ∩ `untouchables` = ∅; mirrored receive ∩ `not_interested` = ∅ | rosters from `load_league_members`; prefs from `load_asset_preferences` (`backend/server.py:4780-4784`) — **the identical predicate chain as `_inject_likes_you_cards_impl:2873-2885`, extracted so the two can never diverge** |
| **G5** | **It is genuinely NEW to this user** | the like's `created_at` is **after** the user's most recent deck generation for that league (`load_latest_trade_impression_batch(...).shown_at`, `backend/database.py:4284+`), falling back to `users.last_active_at` when there is no impression history; **and** the mirrored (give,receive) key is not in `load_trade_decisions(user_id, league_id, since_days=90)` | If a deck was generated after the like, the likes-you injector already showed them the card. Pushing about a card they scrolled past is the exact failure mode the audit warns about. |
| **G6** | **Cadence — one great push** | `_NOTIF_FREQ_CAPS["trade_found"] = (trade_found_cooldown_days, 1)` **and** no send of any kind in `{deck_replenished, trade_found, winback_matches, winback_dormant, weekly_digest}` within `trade_found_global_quiet_days` (via `count_notification_sends_since`) **and** dedup lifetime cap keyed on the trade signature | The window cap rides `_freq_cap_blocks` (`:15321-15327`) for free. The **cross-kind** quiet period is the new part and is the direct answer to "three mediocre ones a day costs the permission permanently". |
| **G7** | **No surprise for a freshly-permissioned user** | the user has ≥1 `device_tokens` row with `created_at ≤ now − trade_found_grace_hours` **and** `users.last_active_at > that token's created_at` | i.e. they granted permission **and then came back at least once**. §Composition with P0-1. |
| **G8** | **Prefs, quiet hours, devices** | inherited verbatim from `_send_typed_push` steps 1–5 | zero new code |
| **G9** | **Blast radius** | at most `trade_found_max_per_tick` sends per cron run; `trade_found_dry_run` computes and counts everything and sends nothing | Ship-the-knob. The pass runs in dry-run for its first weeks. |

**Selection when several candidates pass.** Exactly one push per user per run, describing
**one** trade: the *most recent* qualifying like (newest `created_at`). Deliberately not
"the highest-scoring" — a model ranking would reintroduce the judgement the gate exists to
avoid, and recency is the property the user can verify ("this just happened").

**What the gate deliberately does NOT use.** No `composite_score`, no `fairness_score`, no
mutual-gain threshold, no "the model likes this a lot". Those numbers are how the deck is
*ordered*; they are not evidence that a trade is worth interrupting someone for, and a
threshold on them is a product judgement dressed as a number. If the operator later wants a
model-scored lane, it is specced but not built — see Operator checkpoint **OC-2**.

**Why the gate should mostly not fire, and why that is correct.** The audit's own
replicability finding (`02-tier-a-briefs.md` §7) says the two-board case *"has essentially
never happened in production."* G3 requires a leaguemate who has swiped a deck in the last
`trade_found_max_age_days`. At today's density this pass will very often send **zero**
pushes. That is the designed behaviour of a quality gate, and it is also why **G9's dry-run
counters ship before the sends do** — the operator gets a truthful count of how often the
gate *would* fire before a single notification leaves the building.

### The delivery path (ride the machinery; build nothing parallel)

```
/api/cron/daily-tick  (existing, X-Cron-Secret, existing Render cron)
   └── _run_trade_found_pass(now)          ← new, flag-gated, same shape as
        │                                    _run_weekly_replenishment (:15751)
        ├── load_active_deck_user_leagues(days=…)      G2
        ├── per pair: load_recent_league_likes(…)      G3
        │             load_league_members / asset prefs G4
        │             load_latest_trade_impression_batch / load_trade_decisions G5
        ├── _trade_found_blocked(uid)                  G6 cross-kind quiet + G7 grace
        ├── create_notification(uid, "trade_found", …) ← inbox row, ALWAYS written
        └── _send_typed_push(uid, "trade_found", …)    ← G8: prefs + caps + quiet hours
                dedup_key = f"lk:{league_id}:{sig}"
```

Four deliberate choices in that path:

1. **`daily-tick`, not a new cron.** `.github/workflows/render-cron.yml` and
   `_require_cron_auth` already exist; F10 set the precedent of a flag-gated pass inside
   `daily-tick` whose counters appear in the response only when the flag is on
   (`backend/server.py:16159-16165`). Flag off ⇒ byte-identical response.
2. **No deck generation.** Unlike `_replenish_deck_for` (`:15699`), which runs a full
   synchronous trade job, this pass is four indexed reads per user-league. It costs
   effectively nothing and cannot time the cron out.
3. **The inbox row is written even when the push is suppressed.** `create_notification`
   (`backend/database.py:8439`) is independent of push permission, prefs, quiet hours and
   the OS. A user who declined push still learns a leaguemate wants their player, via the
   bell. This is also the **only** artifact a simulator can observe — it is what makes the
   feature Maestro-testable at all (§Maestro delta).
4. **Copy names the concrete thing, never "come back".** F10's PRD guardrail, adopted
   verbatim. Draft, pending **OC-4**:
   - title: `@{username} wants {PlayerName}`
   - body: `They liked {give} for {receive} · {league_name}` (mirrors `_match_body`'s
     shape at `backend/server.py:10065-10070` — body carries only what the title doesn't).
   - No emoji (ADR-004). No countdown, no "act now".

### Composition with P0-1

**What P0-1 actually changes about permission acquisition** (read from
`ftf-p0-remediation/docs/plans/audit-p0-remediation/plan-p0-1.md`, cross-checked against
this worktree):

- `ranking_method` starts being written at the point of use by four save handlers, so a
  Quick Set user finally computes `unlocked: true` at `backend/server.py:6163-6175`.
- `RootNav.tsx:266-267` `pushEnabled` therefore flips true for the default-path cohort for
  the first time, and `usePushNotifications`'s `undetermined` branch
  (`mobile/src/hooks/usePushNotifications.ts:130-132`) hands off to `PushPrimingModal`.
- A **startup backfill** in `_migrate_db()` tags pre-existing all-four tier boards as
  `'quickset'`, so **existing** users flip to unlocked on their next
  `/api/rankings/progress` poll — with no action of their own.

**P0-1's deliberate push suppression** (plan-p0-1 §R2 + open question **Q5**, and
`scope-p0-1.md:237-238`): the first `/api/rankings/progress` after the backfill takes the
`was_first` branch at `backend/server.py:6218-6255`, which records
`ranking_complete_first_time` **and fans `league_member_unlocked_trades` out to every
leaguemate**. P0-1 flags this as a burst it does not want and specifies the mitigation —
have the backfill pre-populate `unlocked_formats` so `was_first` is already spent,
suppressing both the event and the push — while leaving the yes/no to the operator as Q5.

**How a backfilled user is excluded or delayed here — three independent mechanisms:**

- **Structural (primary).** The trigger is **G3: a leaguemate's like**. There is no code
  path by which a change in the *recipient's own* progression state produces a
  `trade_found` push. P0-1's backfill can flip `unlocked`, mint a push token, and light up
  the primer for thousands of users, and this pass still sends **zero** — because none of
  those events is a like. This is the mechanism that matters; the other two are belt.
- **G7, the grace window.** A `trade_found` push requires a `device_tokens` row at least
  `trade_found_grace_hours` old (default **48**) *and* `users.last_active_at` strictly after
  that token's `created_at`. The P0-1 cohort's tokens are all minted at primer-accept, so
  for the first 48 hours after the P0-1 deploy the entire backfilled cohort is ineligible by
  construction — and any of them who accept the primer and never return stay ineligible
  **forever**. A user's first-ever push from this product is therefore never a `trade_found`.
- **G5 + G3's age window, the burst brake.** Only likes newer than
  `trade_found_max_age_days` (default **7**) count, and only likes postdating the user's
  last deck generation. A backfilled account with 90 days of accumulated league likes
  produces no candidates at all. This is the clause that prevents "we turned it on and 400
  people got a push about something from May."

**Merge order is not optional.** P0-1 merges to `main` first. If P1-9 shipped first,
`notif.trade_found` would be a knob whose audience is the small pre-P0-1 population that
happened to visit the Rank Home chooser — a misleading dry-run baseline. Recorded as a
sequencing constraint, and the dry-run window (§OC-5) must start **after** P0-1's cohort has
had `trade_found_grace_hours` to settle.

### Analytics design (per `plan-p0-7.md` rules)

- **No new event name.** `push_sent` (server-fired, `analytics_taxonomy.py:117`) already
  fires from `_send_typed_push:15403-15407` with `props={"kind","dedup_key"}`. This feature
  contributes a new *value* of `kind`, not a new name. Nothing to register; the default-deny
  allowlist is not in play.
- **`push_opened` is lit, not created.** Registered at `analytics_taxonomy.py:68` +
  `:213`, never fired. Wiring it in the two existing tap handlers is the only way to
  evaluate whether the gate produced a *good* push rather than merely a *rare* one.
  Verified: it is **not** in `analytics_queries.py:60-63` `NON_INTENT_EVENTS`, so it is
  INTENT by the deny-list default. **Recommended: leave it INTENT** — a push open is a
  genuine return to the product, and the incremental DAU effect is ~nil because opening a
  push produces a session that fires intent events anyway. Recorded so it is a decision, not
  an accident (**OC-6**).
- **`dedup_key` must reach the client** or `push_opened.dedup_key` is permanently null.
  One-line addition to the Expo payload in `_send_typed_push`.
- **`platform` is not a prop here.** Device platform is a server-derived `user_events`
  column; `platform` as a prop means league platform. Neither event needs it.
- **The gate's own telemetry is operator-facing, not analytics.** Dry-run counters come back
  in the `daily-tick` JSON response (F10 precedent) and in logs. No new event, no new table.

### No new schema, and exactly one new flag

Everything persists in tables that exist: `notification_events_log` (caps),
`notifications` (inbox), `notification_queue` (quiet hours), `device_tokens` (G7),
`trade_decisions` / `trade_impressions` (G3/G5). **One** new flag, `notif.trade_found`,
default **OFF** — justified because the change crosses a bright line (a push leaves the
building and reaches a user outside the app), and `CLAUDE.md`'s ship-the-knob rule wants a
deploy-free kill switch for exactly that. Thresholds and cadence are **not** flags; they are
`model_config` keys, tunable through `PUT /api/admin/config` without a deploy.

---

## Exact change list

Ordered. Steps 1–4 are backend-only and inert while the flag is off; step 5 is the
measurement wiring that should land in the **same** release so the dry-run has an open-rate
denominator the moment sends begin.

| # | File | Change |
|---|---|---|
| 1 | `backend/feature_flags.py` (`FLAG_KEYS`, notif block `:267-271`) | Add `"notif.trade_found"` with a one-line comment naming this plan. |
| 2 | `config/features.json` | Add `"notif.trade_found": false` next to the other `notif.*` keys (~`:123`), with a `_comment_notif_trade_found` block in the house style stating: what ON does, what the gate requires, that OFF is byte-identical, and that the cadence/threshold knobs are `model_config`, not this flag. |
| 3 | `backend/trade_service.py` `_DEFAULT_CFG` (`:40`, after the F10 block at `:369-373`) | Eight keys, Float-typed per the `model_config` convention: `trade_found_max_age_days 7.0` · `trade_found_active_days 21.0` · `trade_found_cooldown_days 7.0` · `trade_found_global_quiet_days 5.0` · `trade_found_grace_hours 48.0` · `trade_found_max_per_tick 50.0` · `trade_found_dry_run 1.0` · `trade_found_min_like_age_minutes 30.0` (a like that landed 30 s ago may still be part of an in-progress swipe session; let it settle). |
| 4 | `backend/database.py` `NOTIF_KIND_TO_BUCKET` (`:9830-9851`) | Add `"trade_found": <bucket>` — **`trade_matches` recommended, pending OC-1**; comment must state why (counterparty-intent trigger ⇒ transactional, same class as `new_match`), and must cross-reference the `deck_replenished` comment at `:9847` so the asymmetry is deliberate on the page. |
| 5 | `backend/server.py` `_NOTIF_FREQ_CAPS` (`:15212-15217`) | `"trade_found": (int(_deck_cfg("trade_found_cooldown_days", 7)), 1)` — **note:** the map is a module-level literal read at import; make the entry a config read at call time inside `_freq_cap_blocks` (or rebuild the tuple in the pass) so the knob is live without a redeploy. Do not silently make the knob a deploy-only value. |
| 6 | `backend/server.py` `_NOTIF_DEDUP_CAPS` (`:15230-15237`) | Add `"trade_found"` + a comment row in the block above: `dedup_key = "lk:{league_id}:{sig}"` where `sig` is a stable hash of the sorted mirrored give/receive id sets — the same logical trade never re-pushes, ever. |
| 7 | `backend/server.py` (near `_inject_likes_you_cards_impl`, `:2813`) | **Extract** the actionability predicate (`:2873-2885`) into `_likes_you_actionable(like, opp, user_roster_set, untouchable_ids, not_interested_ids) -> tuple[list,list] \| None` and call it from **both** the injector and the new pass. Divergence between the deck's definition of "actionable" and the push's would be a silent, unfalsifiable bug. |
| 8 | `backend/server.py` (new, next to `_deck_replenishment_enabled` `:2979`) | `_trade_found_enabled()` → `getattr(FLAGS, "notif_trade_found", False)`, same shape/docstring convention. |
| 9 | `backend/server.py` (new, above `cron_daily_tick`) | `_trade_found_candidate(uid, lid, now)` → best qualifying candidate or `None` (G2–G5), and `_trade_found_blocked(uid, now)` → G6 cross-kind quiet + G7 grace. Both pure reads, both non-throwing. |
| 10 | `backend/server.py` (new) | `_run_trade_found_pass(now) -> dict` — mirrors `_run_weekly_replenishment`'s shape (`:15751-15808`): iterate pairs, gate, write the inbox row **before** the push (marker-before-push, F10's rule at `:15785-15788`), send, count. Counters: `eligible_pairs, candidates, blocked_cooldown, blocked_grace, blocked_seen, blocked_stale, pushed, dry_run_would_push, errors`. |
| 11 | `backend/server.py` `cron_daily_tick` (hook next to the F10 block at `:16159-16165`) | `if _trade_found_enabled(): trade_found_stats = _run_trade_found_pass(now)`; add the key to the response **only** when non-`None`. Wrapped in `try/except` so a failure here never touches the winback loop above it. |
| 12 | `backend/server.py` `_send_typed_push` (`:15393-15399`) | Add `dedup_key` to the Expo `data` payload: `{**(data or {}), "type": kind, "dedup_key": dedup_key}`. Cross-cutting but inert — `data` is opaque to the client except `type` / `match_id` / `league_id`. Required for `push_opened.dedup_key`. |
| 13 | `mobile/src/utils/deepLinks.ts:262` | Add `'trade_found'` to `V2_TRADE_KINDS` (→ Trades tab, where the deck lives). Comment it like the F10 entry above it. |
| 14 | `mobile/src/hooks/usePushNotifications.ts:200` | Add `'trade_found'` to the **legacy** `tradeKinds` set too. `notif.tap_routing_v2` is on today, but a flag-off path that silently performs no navigation is the A-33 class of bug. |
| 15 | `mobile/src/hooks/usePushNotifications.ts:64-82` and `:166-213` | `track('push_opened', { kind, dedup_key })` in **both** tap paths, inside the existing dedupe guard so a warm tap surfacing through both routes counts once. Import `track` from `../api/events`. |
| 16 | `mobile/src/components/TopBar.tsx` `ROW_GLYPHS` (`:66-76`) | `trade_found: { name: 'match', color: ice.base }` (or a distinct stroke glyph — **OC-4**). Without it the row renders the generic `DEFAULT_ROW_GLYPH` bell (`:73-76`). |
| 17 | `mobile/src/components/TopBar.tsx` (bell `Pressable`, `:~215-237`) | Add `testID="topbar.notif-bell"` — the affordance the Maestro flow must tap has no id today. |
| 18 | `mobile/src/screens/SettingsScreen.tsx:986-1006` | (a) Update the `trade_matches` row `sub` copy if OC-1 lands `trade_found` in that bucket — *"New matches, counter-offers, league activity"* would otherwise be false. (b) Add `testID` to all three bucket rows + the quiet-hours row (`Row` already accepts one, `:1450-1459`) so opt-out is assertable. |
| 19 | `mobile/src/components/CLAUDE.md` | Register the new testIDs so `mobile/scripts/testid-lint.sh` passes. |
| 20 | `backend/tests/fixtures/seed_ui_test_db.py` (~`:1137-1163`) | (a) `matches_seed.likes_you: N` — seed **counterparty** likes (`db.save_trade_decision(partner, lid, …, "like")` with give from the partner's roster, receive from the app user's) — the literal input to G3/G4. (b) a generic `notifications_seed: [{type,title,body,metadata}]` block so a profile can plant a `trade_found` inbox row for the Maestro flow. |
| 21 | `backend/tests/fixtures/profiles/` | New profile `likes-you-waiting.json` (from `near-unlock.json`'s shape): app user unlocked, one ranked leaguemate, `matches_seed: {mutual: 0, awaiting: 0, likes_you: 1}`, one `notifications_seed` `trade_found` row, `flags_base: release` + `flag_overrides: {"notif.trade_found": true}`. |
| 22 | `backend/tests/test_trade_found.py` | New — §Test plan. |
| 23 | `mobile/.maestro/flows/p1-9-trade-found-inbox.yaml` | New — §Maestro delta. |
| 24 | Docs | §Docs impact table. |
| 25 | `living-memory/` | `CHANGELOG.md`, `TEST_LEDGER.md`, `DECISIONS.md` (**D-0NN**: counterparty-intent-only gate; inbox-row-always; bucket choice), `GOTCHAS.md` only if the build loses time. |

---

## Surface changes

Enumerated explicitly because these are the project's bright lines.

| Surface | Changed? | Detail |
|---|---|---|
| **Routes** | **No route added, renamed, removed, or contract-changed.** | `POST /api/cron/daily-tick` gains **one optional response key**, `trade_found`, present only when the flag is on — byte-identical response when off. This is precisely the F10 precedent (`replenish`, `backend/server.py:16159-16165`). `docs/api-reference.md` still gets a row (the response shape is documented there). |
| **Schema** | **None.** No table, no column, no index, no migration. | Every write lands in an existing table: `notifications` (`backend/database.py:817`), `notification_events_log` (`:1249`), `notification_queue` (`:1259`). |
| **Enum-ish values crossing clients** | **Yes — two, and they are the reason this is not a quick fix.** | (1) new push `kind` **`trade_found`** — read by `data.type` in `mobile/src/utils/deepLinks.ts`, `mobile/src/hooks/usePushNotifications.ts`, `mobile/src/components/TopBar.tsx` `ROW_GLYPHS`, and mirrored in `web/js/app.js`'s notification list renderer. (2) new `notifications.type` value **`trade_found`**. Both belong in `docs/cross-client-invariants.md`. Degradation if a client is missed is *silent*: `resolveNotificationTarget` returns `null` and the tap does nothing. |
| **Feature flags** | **One new: `notif.trade_found`, default OFF.** | Registered in `backend/feature_flags.py` `FLAG_KEYS` + `config/features.json` + `docs/config-reference.md`. **Justified by the bright line**: the change's blast radius is outside the app, so a deploy-free kill switch is required. **Graduation criterion:** ≥14 days in dry-run with observed `dry_run_would_push` ≤ 1/user/week, then ON for the operator's device-unit allowlist, then general — see **OC-5**. No other flag's default changes. |
| **`model_config` keys** | **Eight new** (§change list #3). | All Float-typed per the `model_config` convention (`backend/database.py:1814`). Documented in `docs/config-reference.md`. These are the operator's live knobs. |
| **Analytics — new event names** | **None.** | Nothing to register against the default-deny allowlist; `plan-p0-7.md` §3's ordering constraint does not bind. |
| **Analytics — new values / first emissions** | **Yes, three.** | `push_sent.kind = "trade_found"` (new value of an existing server prop) · **`push_opened` fires for the first time ever** (already allowlisted at `analytics_taxonomy.py:68`, props at `:213`) · `push_opened` stays **INTENT** (absent from `NON_INTENT_EVENTS`, `analytics_queries.py:60-63`) — a deliberate call, see **OC-6**. |
| **Push payload shape** | **Yes — additive, cross-cutting.** | Every push's `data` gains `dedup_key` (§change list #12). No client reads unknown `data` keys; required to make `push_opened.dedup_key` meaningful. |
| **UI** | **Yes — one new notification-row glyph, and Settings copy.** | The bell can now render a `trade_found` row (`TopBar.tsx`). If OC-1 puts the kind in `trade_matches`, the Settings row `sub` must change or it lies. Both are Chalkline-token-only; no new component, no layout change. |
| **Web / extension** | **Read-only impact.** | `web/js/app.js`'s notification list will render a `trade_found` inbox row with whatever its default glyph/branch is — **verify at build time and add the mapping if it switches on `type`**; the mobile `ROW_GLYPHS` precedent says a fallback exists, but that is mobile's code, not web's. Extension: unaffected (no notification surface). |
| **Cron schedule** | **No new schedule.** | No change to `.github/workflows/render-cron.yml`, no new endpoint, no new `CRON_SECRET` consumer. |

**Bright-line verdict:** feature-flag surface + cross-client enum values + a
user-reachable push ⇒ **not a quick fix**. Full gates unless the operator explicitly
declares express, and per `CLAUDE.md` an agent never self-selects express.

---

## Maestro delta

**Not waived.** A new flow ships, plus testIDs. But the *scope* of what Maestro can prove
here is bounded by a hard platform fact, stated up front so the coverage claim is honest.

**What Maestro structurally cannot test.** `usePushNotifications` returns early on
`!Device.isDevice` (`mobile/src/hooks/usePushNotifications.ts:89`), and the iOS permission
alert is a SpringBoard surface outside the app hierarchy. **A simulator never registers a
token, never receives an Expo push, and cannot assert the permission dialog.** No flow can
cover the push leg. This is the same waiver `plan-p0-1.md` §6.1 takes for the primer, for
the same reason, and it is recorded in `scope-p1-9.md` §3.

**What makes the feature testable anyway:** the design writes the **inbox row**
unconditionally (§Design, delivery-path choice 3). That row is served by
`GET /api/notifications`, hydrated by the bell (`TopBar.tsx:109+`), and is fully assertable.

### New flow — `mobile/.maestro/flows/p1-9-trade-found-inbox.yaml`

Header per `mobile/.maestro/README.md` convention: `appId`, `# tc:`,
`# profile: likes-you-waiting`, `# flags: likes-you-waiting` (resolved fixture),
`# source: docs/plans/audit-p1-remediation/plan-p1-9.md`, `tags: [p1-9, notifications]`.

1. `launchApp: {clearState: true, clearKeychain: true, stopApp: true}` — cold start
   (law 6: the react-query cache is persisted).
2. Retry-hardened sign-in preamble, asserting the typed username before Continue (law 10);
   `leagues.row.*` → tap.
3. `extendedWaitUntil: id: tab.trades`; settle on a stable root element before any tab tap
   (law 8 — launch routing steals early taps).
4. `assertVisible: id: topbar.notif-bell` → `tapOn: id: topbar.notif-bell` (new testID,
   change #17).
5. `assertVisible: id: "topbar.notif-row..*"` (dynamic-prefix match, which
   `testid-lint.sh` supports) **and** `assertVisible: text: ".*wants.*"` — a bounded regex
   against the seeded row's title, not a full-copy match (laws 1 + 12).
6. `takeScreenshot: p1-9__trade-found-inbox-row` and **eyeball it** (law 23) — this is the
   only place the glyph from change #16 is verified as not-a-generic-bell.
7. `tapOn` the row → `assertVisible: id: tab.trades`-scoped Trades content, proving the
   `V2_TRADE_KINDS` addition (change #13) routes rather than no-ops. Note: this exercises
   `onRowTap` (`TopBar.tsx:341-352`), which shares `resolveNotificationTarget` with the push
   tap handler — so the routing table addition **is** covered, even though the push is not.
8. Settings leg: `tab` → Settings → `assertVisible: id: settings.notif.trade-matches`
   (new testID, change #18b), proving the opt-out the push depends on is reachable.

**testIDs needed:** `topbar.notif-bell` (new) · `settings.notif.trade-matches`,
`settings.notif.weekly-digest`, `settings.notif.reengagement`, `settings.notif.quiet-hours`
(new) · `topbar.notif-row.<id>` (exists, dynamic prefix). All literal strings except the
last, so `mobile/scripts/testid-lint.sh` covers them once registered in
`mobile/src/components/CLAUDE.md`.

**Smoke-suite impact.** No existing flow asserts a notification kind, a bell row, or the
Settings notification block — verified by `grep -rl "notif\|push" mobile/.maestro/`, whose
hits are all `capture/*.yaml` screenshot flows plus `flows/espn-connect-capture.yaml`,
none of which assert on this surface. Crossing captures: `capture/settings.yaml` and
`capture/settings@two-leagues.yaml` photograph the Settings screen and **will change** if
OC-1 lands the copy edit in change #18a → re-capture both. `capture/*` flows that include
the TopBar are unaffected (the bell gains a testID, not a visual).

**Capture delta:** `settings` and `settings@two-leagues` **only if** #18a lands; plus the
new `p1-9__trade-found-inbox-row` screenshot. Run `mobile/scripts/screen-freshness.sh` and
re-capture what it flags.

**Sim-gate tier: 2** (`docs/runbook.md` §Pre-ship simulator gate — mobile logic touched,
no material UI change): the feature's own flow + the affected smoke subset. Escalates to
**tier 1** if OC-1 lands the Settings copy change, because that is a visible screen change
requiring `screen-capture.sh --screen settings`. Declare the tier in the scope block once
OC-1 is answered.

---

## Docs impact table

Row per `docs/CLAUDE.md` trigger. Every row is "updated" or "n/a because".

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **Updated** | `POST /api/cron/daily-tick` — document the optional `trade_found` counters object (flag-on only), mirroring how the F10 `replenish` key is documented. No route added/renamed/removed; no request field; no other response key. |
| `docs/data-dictionary.md` | **Updated** | Two value-level rows, no schema change: `notifications.type` gains `trade_found` (the column comment at `backend/database.py:820` currently enumerates `trade_match \| trade_accepted \| trade_declined` — **that comment is already stale** and must be corrected in the same pass, A-33 rule), and the `notification_events_log.kind` / push-kind list gains `trade_found`. |
| `docs/config-reference.md` | **Updated** | New flag `notif.trade_found` (default, what ON does, kill-switch semantics, graduation criterion) **and** the eight new `model_config` keys with their defaults and units. |
| `docs/cross-client-invariants.md` | **Updated** | The push-`kind` ↔ client tap-routing map and the `notifications.type` enum are exactly this file's remit. Record `trade_found` → Trades tab, and record the **silent** failure mode of a client that misses it (`resolveNotificationTarget` → `null` → no navigation). Also note `web/js/app.js` as the third consumer. |
| `docs/runbook.md` | **Updated** | New subsection modelled on *"Weekly deck replenishment (F10…)"*: what the pass does, that it lives inside `daily-tick`, how to read the counters from the tick response, how to run it in dry-run, and the **kill switch** (`notif.trade_found` → off; or `trade_found_dry_run` → 1 via `PUT /api/admin/config`, which needs no deploy). Also: how to answer "why did nobody get one this week?" from the counters. |
| `docs/architecture.md` | **n/a** | No module added or re-wired; no data-flow change. The pass is a new function inside an existing cron endpoint using existing loaders. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow. |
| `living-memory/LLD.md` | **Updated** | One convention shifts and should be written down: *"a push kind's cadence knob is a `model_config` key read at call time, not a literal in `_NOTIF_FREQ_CAPS`"* (change #5) — the first time that map has been made live-tunable. |
| `docs/glossary.md` | **Updated** | `likes-you` / *counterparty intent* is used across the deck engine and now the notification layer but is not defined in the glossary. One entry. |
| `docs/design/design-system.md` / `components.md` | **n/a** | No new component and no new token. The notification row and its glyph set already have a spec (`components.md` NotificationRow, #225); this adds one entry to an existing map. Re-read before touching `TopBar.tsx` per `CLAUDE.md`. |
| ADR | **n/a** | No architectural decision of ADR weight — this rides an existing dispatcher and an existing cron. |
| `living-memory/DECISIONS.md` | **Updated** | Next id (**D-0NN**, take the live next after P0-1/P0-7 land): (1) the gate is counterparty intent only — no model score, ever, without an operator decision; (2) the inbox row is written even when the push is suppressed; (3) the bucket choice and its coupling to gate strength. |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | **On ship** | TEST_LEDGER carries the pytest run, the tier-2 (or 1) sim run, and the **dry-run observation window** result. |
| `living-memory/DEPENDENCIES.md` | **n/a** | No dependency added, bumped, or removed. |
| `screens/CLAUDE.md` (screen library) | **Conditional** | Only if #18a lands and `settings` is re-captured. |
| `docs/business/analytics/*` | **n/a** | No new event name ⇒ no tracking-plan addendum is required (`analytics_taxonomy.py:9-10` conditions that on new client event types). **But** the first-ever emission of `push_opened` and the resulting un-darkening of `push_open_rate` should be noted wherever the dark list lives — `2026-07-17-tracking-plan-v2.md:14` explicitly lists `push_opened` as *"documented but dark"* and that line becomes false. One-line correction. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a** | The audit is a dated artifact — record the outcome in CHANGELOG, don't rewrite the audit. |

---

## Test plan

### Backend — `backend/tests/test_trade_found.py` (new)

Harness: `backend/tests/test_notif_teardown.py`'s isolated in-memory SQLite + patched flag
helpers (the file's own docstring names it as the pattern for cron tests), plus
`test_deck_replenishment.py`'s `_insert_decision` helper shape for seeding likes.

**Flag-off invariance**

| # | Case | Assert |
|---|---|---|
| T-1 | Flag off, a perfectly qualifying candidate seeded | `daily-tick` response has **no** `trade_found` key; zero `notification_events_log` rows; zero `notifications` rows; `_send_expo_push` never called |

**The gate — each clause proved to BLOCK, individually**

| # | Clause | Setup | Assert |
|---|---|---|---|
| T-2 | G3 | no leaguemate likes | 0 pushed, `candidates == 0` |
| T-3 | G4 roster | leaguemate liked, then their give player is no longer on their roster | 0 pushed |
| T-4 | G4 prefs | mirrored give ∩ untouchables ≠ ∅ | 0 pushed |
| T-5 | G4 prefs | mirrored receive ∩ not-interested ≠ ∅ | 0 pushed |
| T-6 | G5 seen | a `trade_impressions` batch exists with `shown_at` **after** the like | 0 pushed, `blocked_seen == 1` |
| T-7 | G5 swiped | the user already has a `trade_decisions` row for the mirrored key | 0 pushed |
| T-8 | G3 stale | like is `trade_found_max_age_days + 1` old | 0 pushed, `blocked_stale == 1` |
| T-9 | G2 | the pair has no deck activity in `trade_found_active_days` | pair not even enumerated |
| T-10 | G6 window | a `trade_found` was sent 2 days ago (`cooldown = 7`) | 0 pushed, `blocked_cooldown == 1` |
| T-11 | **G6 cross-kind** | a `deck_replenished` was sent 2 days ago (`global_quiet = 5`) | 0 pushed — **this is the "one great push a week" assertion** |
| T-12 | G6 dedup | the same trade signature already has a `notification_events_log` row (any age) | 0 pushed, forever |
| T-13 | **G7 grace** | device token `created_at` is 2 h old | 0 pushed, `blocked_grace == 1` |
| T-14 | **G7 return** | token is 5 days old but `users.last_active_at` predates it (granted, never returned) | 0 pushed — **the P0-1 backfill-cohort guard** |
| T-15 | G8 prefs | user has the target bucket toggled off | 0 pushed (proves `_send_typed_push`'s bucket gate is reached, not bypassed) |
| T-16 | G8 quiet hours | user tz local time is 23:00 | **0 Expo sends**, exactly 1 `notification_queue` row with `deliver_after` = next local 08:00 |
| T-17 | G9 dry-run | `trade_found_dry_run = 1`, one qualifying candidate | `dry_run_would_push == 1`, `pushed == 0`, **zero** `notification_events_log` rows, **zero** inbox rows |
| T-18 | G9 blast cap | 60 qualifying pairs, `max_per_tick = 50` | exactly 50 pushed |

**The happy path**

| # | Case | Assert |
|---|---|---|
| T-19 | One qualifying candidate, all clauses satisfied, dry-run off | exactly **1** Expo send; `notification_events_log` has 1 row `(kind='trade_found', dedup_key='lk:…')`; `notifications` has 1 row `type='trade_found'`; a `push_sent` `user_events` row with `props.kind == 'trade_found'`; response `pushed == 1` |
| T-20 | Two qualifying candidates for the same user, different leagues | exactly **1** push (the newest like), and the second is counted as `blocked_cooldown`, not silently lost |
| T-21 | Idempotence | run `daily-tick` twice in a row | second run pushes 0; no duplicate inbox row |
| T-22 | Inbox row survives push suppression | bucket off (T-15 setup), dry-run off | **1 inbox row, 0 pushes** — the design's core resilience claim |
| T-23 | Copy honesty | qualifying candidate with known player names | title contains the counterparty's username and the headline player name; body names both sides; **no emoji** (regex assert); no "come back"/countdown language |

**Parity — the extraction must not change the deck**

| # | Case | Assert |
|---|---|---|
| T-24 | `_likes_you_actionable` extraction (change #7) | existing likes-you tests still green; a table-driven test feeds the same fixtures to the extracted helper and to a copy of the pre-extraction predicate and asserts identical accept/reject on every row |

**Cross-client contract**

| # | Case | Assert |
|---|---|---|
| T-25 | Payload shape | the Expo message `data` contains `type == 'trade_found'`, `league_id`, and **`dedup_key`** (change #12) |
| T-26 | Regression on #12 | an existing kind (`new_match`) also carries `dedup_key` in `data` and its `title`/`body` are byte-identical to before |

**Existing suites that must stay green:** `test_notif_teardown.py`,
`test_deck_replenishment.py`, and any suite asserting the `daily-tick` response shape.
Command: `python3 -m pytest backend/tests/ -q`.

### How you test a gate that should mostly NOT fire

This is the part that matters, and it is three distinct techniques:

1. **Assert the blocks, not the sends.** T-2…T-18 above are eighteen tests whose expected
   value is *zero pushes*, each isolating **one** clause with everything else satisfied. A
   suite that only tested the happy path would pass identically against a gate that had been
   accidentally short-circuited to "always send". Each blocking test therefore **starts from
   the T-19 happy-path fixture and breaks exactly one clause** — that construction is what
   makes a zero-push assertion meaningful rather than vacuous.
2. **Count the near-misses in production, not the sends.** `_run_trade_found_pass` returns
   `blocked_*` counters *by reason*. In dry-run the operator can read, every day, how many
   candidates existed and which clause rejected them. A gate that fires zero times with
   `candidates == 0` is a *density* problem (expected today); a gate that fires zero times
   with `candidates == 40, blocked_seen == 40` is a *gate* problem. Those two look identical
   from the outside and completely different in the counters. **This distinction is the
   single most valuable output of the whole item.**
3. **Ship it dry.** `trade_found_dry_run` defaults to **1** (§change list #3). The first
   release computes the full gate on real production data and sends nothing. The operator
   turns sends on only after observing the counters for a full week (**OC-5**). A gate whose
   real-world firing rate has never been observed should not be allowed to send.

### Mobile

- `cd mobile && npx tsc --noEmit` — expected clean (a set literal, a map entry, two
  `track()` calls, testIDs).
- `mobile/scripts/testid-lint.sh` after registering the new ids.
- **Manual simulator check for the client half:** seed `likes-you-waiting`, boot the
  UI-test backend, sign in, open the bell → the `trade_found` row renders with its glyph
  (not the fallback bell), tapping lands on Trades. Then background the app ≥10 s
  (`FLUSH_INTERVAL_MS`) and verify a `push_opened` row landed in `user_events` **with
  `platform` = `'ios'`, not NULL** — the direct regression check for the incident that
  motivates the prop-spec regime (`plan-p0-7.md` §9.3), and confirm
  `GET /api/analytics/health` shows `dropped_unknown_type` flat.
- **The push leg is verified on a real device or not at all.** Before flipping the flag
  past dry-run, the operator sends themselves one via the allowlist and confirms: banner
  copy, tap → Trades, quiet-hours deferral if sent after 22:00 local, and that
  `push_opened` lands.

### Simulator gate

Tier **2** (or **1** if OC-1 lands the Settings copy change) per `docs/runbook.md`. Evidence:
`TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json`.

---

## Risks and cross-item collisions

### Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **The gate never fires in production.** G3 needs a leaguemate who swiped a deck recently; the audit's own replicability finding says two-ranked-users-in-a-league *"has essentially never happened."* The feature could ship and deliver nothing. | **High (likelihood), Low (harm)** | This is *by design* — a push that cannot be justified should not be sent. The dry-run counters make the emptiness **visible and attributable** (`candidates == 0` vs `blocked_*`) instead of leaving the operator guessing. If `candidates` stays 0 for a month, the honest conclusion is that P1-9's value is gated on adoption density (P1-3/P1-5 invite work), **not** that the gate should be loosened. Do not respond to R1 by weakening the gate; that is the failure mode the whole item exists to avoid. |
| **R2** | **Double-notification with F10.** A user opted into re-engagement could get `deck_replenished` Wednesday and `trade_found` Thursday. | Medium | G6's cross-kind quiet period (`trade_found_global_quiet_days`, default 5) covers `deck_replenished`, both winbacks and the digest. Asserted by T-11. |
| **R3** | **Consent-copy mismatch.** `PushPrimingModal` promises three specific things; `trade_found` is a fourth. If it lands in the `trade_matches` bucket (OC-1), users receive a class of push they were not shown. | **Medium-High** | The primer copy is arguably already elastic enough (*"A new trade match is generated for you"*), but relying on that reading is exactly the kind of self-serving interpretation that costs the permission. **Recommend updating the primer's bullet list in the same commit** if OC-1 chooses `trade_matches`. Flagged as part of OC-1, not a separate decision. |
| **R4** | **Privacy of revealing a leaguemate's like.** A lock-screen banner naming a leaguemate and a player exposes their trade interest to anyone glancing at the phone. | Medium | In-app this is already disclosed — the `likes_you` pill reads *"They're interested"* (`TradeCard.tsx:347`) and the card names the opponent. A push is a wider surface. **OC-4** makes naming the leaguemate an explicit operator choice with a non-naming fallback (*"Someone in {league} wants {Player}"*). |
| **R5** | **The extraction (#7) changes deck behaviour.** Refactoring the actionability predicate out of a live, flag-on injector risks a silent deck regression. | Medium | T-24's differential test; the extraction is pure (no I/O, no mutation) and the injector's call site is one line. If the parity test cannot be made clean, **do not extract** — duplicate the predicate with a comment binding the two, and accept the divergence risk knowingly. |
| **R6** | **`_NOTIF_FREQ_CAPS` is a module-level literal**; a naive `_deck_cfg` call there would freeze the knob at import. | Medium | Change #5 calls this out explicitly; the cap must be resolved at call time. A test that changes `model_config` mid-run and asserts the new cap applies is the guard. |
| **R7** | **Cron cost.** Adds 3–4 indexed reads per active user-league to a daily job that already does a full-user scan plus (F10) synchronous deck generation. | Low | No generation, no external calls. At current scale this is noise next to `_replenish_deck_for`. `trade_found_max_per_tick` bounds the send loop. Wrapped so a failure cannot touch the winback loop. |
| **R8** | **`push_opened` is INTENT** ⇒ appears in DAU/WAU/retention from first emission. | Low | Incremental effect ~nil (a push open produces a session that already fires intent events). Called out as **OC-6** so the seam date is recorded rather than discovered later in a chart. |
| **R9** | **Silent client miss.** If `trade_found` reaches `V2_TRADE_KINDS` but not the legacy set (or not `web/js/app.js`), the failure is a tap that does nothing — no error, no log. | Low | Change #14 covers the legacy set; the web renderer is an explicit build-time verification item in §Surface changes. `docs/cross-client-invariants.md` records the silent-failure mode. |
| **R10** | **Timezone edge on G5's timestamp comparison.** `trade_decisions.created_at` is naive-UTC; `trade_impressions.shown_at` carries `+00:00`. | Low | Pre-existing and already handled the same way by `load_active_deck_user_leagues` (`backend/database.py:4260-4262` comment: both compare correctly against the naive prefix lexically). Reuse that idiom; **do not invent a new comparison**. A test with one of each shape. |

### Cross-item collisions

| File | This item needs | Also claimed by | Resolution |
|---|---|---|---|
| `backend/server.py` — `_send_typed_push` (`:15393`) and the two cap maps (`:15212`, `:15230`) | changes #5, #6, #12 | No other P0/P1 item found touching the push dispatcher | Clean. Re-diff before editing: the file is 20 k+ lines and multiple sessions run in this repo. |
| `backend/server.py` — `_inject_likes_you_cards_impl` (`:2813-2936`) | change #7 (extraction) | none found | Clean, but this is deck-engine code; a concurrent trade-engine session would be the collision to watch. |
| `backend/server.py` — `cron_daily_tick` (`:16060+`) | change #11 | none found | Clean. |
| `backend/server.py` — `get_rankings_progress` / `:6218-6255` | **read-only** (P0-1's suppression section) | **P0-1** owns it | No edit from here. P1-9 must **not** add anything to the first-unlock fan-out. |
| `mobile/src/hooks/usePushNotifications.ts` | changes #14, #15 | none found | Clean. P0-1 and P0-5 touch `RootNav.tsx`, not this hook. |
| `mobile/src/utils/deepLinks.ts` | change #13 (one set entry at `:262`) | **P0-3** rewrites the URL-parsing half for the invite loop (its citation `:301-302` has already moved to `:352-354`); **P1-1/2** adds a third branch to `rewriteUniversalPath` (`:189-199`) for the tiers share landing; **P1-11** explicitly does **not** touch the file | **Three-way, all disjoint regions.** P1-9 owns only the `V2_TRADE_KINDS` literal. Sequence P0-3 → P1-1/2 → P1-9 and rebase; conflicts are mechanical but the line numbers *will* have moved — re-grep for `V2_TRADE_KINDS`, do not edit by line. |
| `mobile/src/screens/SettingsScreen.tsx` | change #18 (bucket-row copy + 4 testIDs, `:986-1026` and the `Row` helper `:1450-1459`) | **P1-10** edits `navigateFromSettings` (`:220-227`), the step-up alert (`:488`) and the verify row (`:1261`) for Sleeper-Connect analytics; **P1-3** only *reads* `:354-361` / `:1331` | Same file, **disjoint regions** (notification block vs. verify/step-up block). Rebase; low risk. Note P0-1 §1.1 also only *reads* `:229-238`. |
| `mobile/src/components/TopBar.tsx` | changes #16, #17 | none found in P0 or the P1 siblings | Clean. |
| `backend/tests/fixtures/seed_ui_test_db.py` + `fixtures/profiles/` | changes #20, #21 (the `matches_seed` block `~:1137-1163` + a new profile) | **P0-1** rewrites `_validate_quickset` (`:314-366`) and `profiles/quickset-done.json`; **P1-7** adds a new seed handler; **P1-5** only *reads* `:563-593` | Three writers, all different regions of one file, plus **new** profile files that cannot collide. P0-1 merges first; rebase and re-run the seeder end to end rather than trusting a clean merge. |
| `backend/feature_flags.py` `FLAG_KEYS` | one new key in the `notif.*` block (`:267-271`) | **P1-3, P1-5, P1-11** each add flags to the same list | Textual conflicts in one Python list — mechanical, but expect them. Keep the addition inside the existing `notif.*` block so the diff is locally anchored rather than appended at the end. |
| `backend/trade_service.py` `_DEFAULT_CFG` (`:40-450`) | eight new `model_config` keys after the F10 block (`:369-373`) | **P1-7** touches `:1892` (pick-anchor logic) | Disjoint — config table vs. engine code. Clean. |
| `backend/analytics_taxonomy.py` / `analytics_queries.py` | **no edit** | **P0-7** owns both; **P1-3, P1-5, P1-10** each register new event names there | Clean by construction — P1-9 introduces no new event name, which is also why it is immune to the heaviest-contended file in the whole remediation round. If the operator answers **OC-6** with "make `push_opened` NON_INTENT", that becomes a one-line edit to a P0-7-owned file and should be handed to P0-7 rather than done here. |

---

## Operator checkpoints

Every parameter below is a **product judgement**, not an engineering one. Defaults are
recommendations; none is hard-coded as truth.

### OC-1 — Which preference bucket does `trade_found` live in? *(the consequential one)*

| Option | Effect | Consequence |
|---|---|---|
| **A. `trade_matches`** | Default **ON** for anyone who granted push. | Maximum reach. Requires the Settings row `sub` copy edit (change #18a) and, per **R3**, a `PushPrimingModal` bullet edit — the consent language must cover it. |
| **B. `reengagement`** | Default **OFF** via `notif.reengagement_default_off` — same treatment as `deck_replenished`. | Nearly nobody receives it, ever. Safest, and consistent with the F10 precedent. But it makes the feature approximately a no-op on top of R1's density problem. |
| **C. Unmapped (transactional)** | No bucket gate at all — the user cannot turn it off separately. | **Do not do this.** A push a user cannot switch off is how the permission gets revoked. |

**Recommendation: A**, *conditional on the gate staying counterparty-intent-only.* A
leaguemate liking a trade for your player is a transactional event caused by another human,
which is the same class as `new_match` and `match_accepted`, not the same class as
"you've been away 30 days". **Bucket strength and gate strength are one decision, not two:**
if the operator ever widens the gate to model-scored candidates (**OC-2**), the kind must
move to `reengagement` in the same change. Write that coupling into `DECISIONS.md`.

### OC-2 — Gate strength: counterparty intent only, or a second lane?

| Option | What it means |
|---|---|
| **A. Intent-only (this plan)** | Only a leaguemate's `like` triggers a push. Truthful by construction. Fires rarely (**R1**). |
| **B. + dual-board lane** | Also push when a leaguemate **publishes a board** (`member_rankings`) and a dual-board mutual-gain card appears where only consensus cards existed before. This is the product's actual moat (`02-tier-a-briefs.md` §7 Replicability) and is a genuinely *new* trade — but it requires deck generation, so it must ride F10's weekly pass (§Design), **upgrading** the `deck_replenished` push rather than adding one. |
| **C. + score threshold** | Push when a generated card exceeds a composite/fairness threshold. |

**Recommendation: A for v1, B specced and deferred, C never.** B is a real design with a
non-arbitrary trigger and near-zero marginal cost (F10 already generates the deck) — but it
is a second feature and should be its own decision once A's dry-run counters exist.
**C is the option the resolution doc warns about**: a numeric threshold on a model score is
a product judgement disguised as a parameter, and it is how "three mediocre pushes a day"
happens. If the operator wants C, it must move to `reengagement` (OC-1) and needs its own
dry-run window.

### OC-3 — Cadence and thresholds

All eight are `model_config` keys, changeable via `PUT /api/admin/config` **without a
deploy**.

| Key | Recommended default | Range worth considering | Why this default |
|---|---|---|---|
| `trade_found_cooldown_days` | **7** | 3–14 | "One great push a week." Matches F10's weekly rhythm and the resolution doc's own framing. |
| `trade_found_global_quiet_days` | **5** | 0–7 | Spaces `trade_found` away from `deck_replenished`/winbacks/digest. 0 disables the cross-kind rule (**not** recommended). |
| `trade_found_max_age_days` | **7** | 2–14 | Aligns with the 7-day `TradeCard` expiry. A like older than the card it refers to is not news. |
| `trade_found_active_days` | **21** | 7–30 | Narrower than F10's 30 — a `trade_found` should reach someone still in the habit, and a 30-day-absent user is a winback case, which already has its own kind. |
| `trade_found_grace_hours` | **48** | 24–168 | The P0-1 backfill guard. Longer = safer, at the cost of delaying legitimate pushes to genuinely new users. |
| `trade_found_min_like_age_minutes` | **30** | 5–120 | Lets an in-progress swipe session finish before we treat one like as a considered signal. |
| `trade_found_max_per_tick` | **50** | 10–500 | Blast-radius stop. At current scale it will never bind; it exists so it cannot bind badly later. |
| `trade_found_dry_run` | **1 (on)** | 0/1 | Ship dry. See OC-5. |

### OC-4 — Copy, and how much it reveals

| Option | Title / body |
|---|---|
| **A. Name the leaguemate and the player** | *"@dynastyDan wants Jahmyr Gibbs"* / *"They liked Gibbs for Nabers + a 2027 1st · Dynasty Warriors"* |
| **B. Name the player only** | *"Someone in Dynasty Warriors wants Jahmyr Gibbs"* / *"A leaguemate liked a trade for one of your players. Tap to see it."* |
| **C. Neutral** | *"A new trade is waiting"* / *"…"* |

**Recommendation: A.** It is the concrete-inventory rule (F10 PRD guardrail 3 / risk
section) applied honestly, it is already disclosed in-app (`TradeCard.tsx:344-347`), and it
is the only version that earns the interruption. **C fails the guardrail outright** — it is
the bare "come back" the F10 PRD explicitly forbids. Choose **B** if lock-screen privacy
(**R4**) outweighs clarity. Whichever is chosen: no emoji (ADR-004), no countdown, no
fake urgency. Also decide here whether the bell row gets the `match` glyph (recommended,
it *is* a match-adjacent event) or its own stroke icon.

### OC-5 — Rollout sequence and graduation criterion

Recommended, and the plan is written assuming it:

1. Merge **after P0-1**. Flag `notif.trade_found` **ON**, `trade_found_dry_run` **1**.
2. Wait `trade_found_grace_hours` past P0-1's deploy, then read the `daily-tick` counters
   daily for **14 days**. The question being answered is *how many candidates exist and
   which clause rejects them* — not "did it send".
3. **Graduate to sends only if** `dry_run_would_push` ≤ 1 per user per week across the whole
   window **and** the per-reason `blocked_*` mix is legible. Enable for the operator's own
   device-unit allowlist first (`config/tester_allowlist.json`, the existing mechanism), send
   yourself one, then go general.
4. `candidates == 0` for the whole window ⇒ ship it OFF and revisit after invite/density
   work (P1-3, P1-5). **Do not loosen the gate to make the counter move.**

### OC-6 — Is `push_opened` INTENT or NON_INTENT?

It is absent from `NON_INTENT_EVENTS` (`analytics_queries.py:60-63`), so it lands as
**INTENT** by the deny-list default and enters DAU/WAU/retention on its first emission.
**Recommendation: leave it INTENT** — a push open is a real return to the product, and the
incremental effect is ~nil because the resulting session fires intent events regardless.
If the operator prefers NON_INTENT, that is a one-line edit to a **P0-7-owned** file and
should be routed there. Either way the emission date is a seam and belongs in the CHANGELOG.

### OC-7 — Does the inbox row ship even when the push is suppressed?

**Recommendation: yes** (as designed). It is the only artifact independent of push
permission, prefs, quiet hours and the OS; it is the only thing a simulator can assert; and
it gives a user who declined push a way to learn a leaguemate wants their player. Cost: one
new `notifications.type` value across three clients (§Surface changes) and a bell badge that
can now increment without a push. Say no, and the feature becomes untestable on the
simulator and invisible to every user who declined the primer.
