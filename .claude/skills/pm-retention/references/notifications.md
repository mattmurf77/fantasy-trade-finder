# Notifications reference — pm-retention

> How to regenerate FTF's push and inbox inventory from code, the per-kind spec block every
> notification PRD carries, and the health questions to send `analytics-lead`. Code is the
> authority. The snapshot table below is a convenience that goes stale.

## Contents

- [1. Regenerate the inventory](#1-regenerate-the-inventory)
- [2. Per-kind spec template](#2-per-kind-spec-template)
- [3. Per-kind health check for analytics-lead](#3-per-kind-health-check-for-analytics-lead)

---

## 1. Regenerate the inventory

Run these from the repo root on a fresh `origin/main`. They are tracked-file searches only,
so never use `grep -r`. Line numbers drift; the anchor text doesn't.

```bash
# Which pref bucket (the user's toggle) gates each kind
git grep -n -A24 "^NOTIF_KIND_TO_BUCKET" -- backend/database.py
# Window caps, and per-dedup-key caps
git grep -n -A6 "^_NOTIF_FREQ_CAPS" -- backend/server.py
git grep -n -A8 "^_NOTIF_DEDUP_CAPS" -- backend/server.py
# How a cap is decided
git grep -n -A16 "^def _freq_cap_blocks" -- backend/server.py
# Where each kind is sent from (the kind is on one of the next two lines)
git grep -n -A2 "_send_typed_push($" -- backend/server.py
# Which tick sends what (header comment), tick routes, tick schedules
git grep -n -A6 "^# Three endpoints:" -- backend/server.py
git grep -n '@app.route("/api/cron/.*-tick' -- backend/server.py
git grep -n -A6 "name: notif-" -- render.yaml
# Notification routes
git grep -n '@app.route("/api/notifications' -- backend/server.py
# Inbox (bell) writers: these are not pushes
git grep -n -A1 -E "_write_inbox_row\($|push_notification\($|create_notification\($|create_or_coalesce_league_join_notification\($" -- backend/server.py
# notif.* flags (registry + live state)
git grep -n '"notif\.' -- backend/feature_flags.py config/features.json
# Tap route per kind, and the prefs toggles the user sees
git grep -n -A3 "const V2_.*_KINDS" -- mobile/src/utils/deepLinks.ts
git grep -n -B4 "flip('" -- mobile/src/screens/settings/sections/NotificationsSection.tsx
# Notification events in the taxonomy
git grep -n -E '"push_[a-z_]+"|"notif_[a-z_]+"' -- backend/analytics_taxonomy.py
```

Sample output at `678834ab`:

```
backend/server.py:23271:_NOTIF_FREQ_CAPS: dict[str, tuple[int, int]] = {
backend/server.py-23272-    "winback_matches": (7,   1),
backend/server.py-23273-    "winback_dormant": (30,  1),
backend/server.py-23274-    "finish_ranking":  (30,  1),
backend/server.py-23275-    "season_start":    (365, 1),

backend/database.py-13945-    "winback_dormant":                 "reengagement",

render.yaml:65:    name: notif-daily-tick
render.yaml-67-    schedule: "30 13 * * *"      # 13:30 UTC ≈ 9:30am ET — re-engagement scan
```

**Watch out:** the tick header comment (`server.py:24356-24361`) does not list
`deck_replenished`. The daily tick sends that kind through `_run_weekly_replenishment`
(`server.py:23890`, push at `:23954`). Trust the `_send_typed_push(` call sites over the
comment.

### Kind snapshot — snapshot @ `678834ab`, regenerate before use

| Kind | Bucket (toggle) | Cap | Sent from | Flag | Tap → | Inbox row |
|---|---|---|---|---|---|---|
| `new_match` | trade_matches | none | `POST /api/trades/swipe` (`server.py:16267`) | — | Matches | `trade_match` (`:16210`) |
| `first_match` | trade_matches | dedup `lifetime` | same route (`:16258`) | — | Matches | `trade_match` |
| `match_accepted` | trade_matches | dedup `accept:{match}:{actor}` | `POST /api/trades/matches/<id>/disposition` (`:20580`) | — | Matches | `trade_accepted` / `trade_declined` (`:20698`) |
| `match_expiring` | trade_matches | dedup per match | realtime-tick, 15 min (`:24516`) | — | Matches | yes (`:24509`) |
| `league_member_joined` | trade_matches | dedup | `POST /api/session/init` (`:22706`) | — | League | coalesced, one row per league per UTC day (`:22699`) |
| `league_member_unlocked_trades` | trade_matches | dedup | `GET /api/rankings/progress` (`:10561`) | — | League | yes (`:10552`) |
| `counter_offer` | trade_matches | — | **no backend sender** at this sha | — | Matches | — |
| `weekly_digest` | weekly_digest | inline 1 per 6 d (`:24627`, `:24642`) | hourly-tick, Tue 09:00 local (`:24641`) | — | Matches | no |
| `pending_review` | weekly_digest | inline 1 per 6 d, only if unread > 0 | hourly-tick, Wed 09:00 local (`:24652`) | — | Matches | no |
| `bundle_summary` | none (raw transport) | — | hourly-tick quiet-hours drain at 08:00 local | — | Matches | no |
| `winback_matches` | reengagement | 1 per 7 d | daily-tick: 7 d inactive and unread > 0 (`:24769`) | default-off applies | Matches | no |
| `winback_dormant` | reengagement | 1 per 30 d + lifetime stop ≥ 3 since last active (`:24742`) | daily-tick: 30 d inactive, and unread > 0 when honest (`:24732-24762`) | `notif.honest_winbacks` | Matches | no |
| `finish_ranking` | reengagement | 1 per 30 d | daily-tick: signed up > 3 d, no format unlocked (`:24721`) | default-off applies | Rank | no |
| `season_start` | reengagement | 1 per 365 d | daily-tick on Aug 25 UTC, all signed-up users (`:24697`, `:24710`) | default-off applies | Matches (the copy says "re-rank") | no |
| `deck_replenished` | reengagement | dedup `{league}:{iso_week}` + weekly marker | daily-tick, Wed onward (`replenish_weekday`, `:23670`) | `deck.replenishment` | Trades | yes (`:23947`) |

Inbox-only types (no push): `referral_joined` (`push_notification`, `server.py:22659`;
despite its name, `database.py:12620` writes only an inbox row) and `espn_reconnect`
(`:24133`). The authoritative inbox list is `docs/cross-client-invariants.md` § Notification
type strings.

### Gate order and the facts behind it

`_send_typed_push` (`server.py:23455`) runs, in order:

1. Bucket toggle (`:23483`).
2. `_freq_cap_blocks` (`:23488`, defined at `:23371`).
3. Quiet hours → `notification_queue`, bundled at 08:00 local.
4. Devices → Expo.
5. `log_notification_send` + `push_sent`.

- **A suppressed push leaves no row and no event**, only a `log.info` line
  (`:23485`, `:23489`). The comment at `:23269` says skips are recorded as `push_skipped`.
  No emitter exists (`git grep -n push_skipped -- backend mobile/src web` finds only that
  comment).
- **Tick response counters count attempts, not deliveries.** For example, the daily tick
  increments `winback_dormant` after the call whether or not the push left
  (`server.py:24762`). The delivered count is `notification_events_log`.
- **The five `notif.*` flags** are registered at `backend/feature_flags.py:369-373` and
  all on at `config/features.json:180-184`:

| Flag | What it does |
|---|---|
| `notif.tz_sync` | Adopts the device time zone into `notification_prefs.tz` (`server.py:23557`). |
| `notif.tap_routing_v2` | Shared tap map plus cold-start replay (`deepLinks.ts:280-342`). |
| `notif.denial_recovery` | Shows a Settings banner when the OS permission is denied (`NotificationsSection.tsx:50`, `:114`). |
| `notif.reengagement_default_off` | Defaults the re-engagement bucket to 0 (`database.py:13954-13970`). |
| `notif.honest_winbacks` | Truthful `winback_dormant` copy plus the lifetime stop (`server.py:24732`). |

### Client pieces

| Piece | File | What to know |
|---|---|---|
| Registration and tap listener | `mobile/src/hooks/usePushNotifications.ts` | Asks for permission only after the rankings unlock (`:22-40`). It never re-prompts after a denial (`:126-132`). |
| Primer state | `mobile/src/state/usePushPriming.ts` | Backs off for 3 sessions after "Maybe later", unless a want-it moment fires (`:13-24`). |
| Primer UI | `mobile/src/components/PushPrimingModal.tsx` | Its consent copy promises three transactional events (`:63-67`). |
| Interrupt arbiter | `mobile/src/state/useInterruptCoordinator.ts` | One surface at a time. Root modals, the primer included, self-defer while any surface or a tour hold is up (`:27-30`). |
| Bell inbox | `mobile/src/components/TopBar.tsx` + `state/useNotifications.ts` | Glyph map `ROW_GLYPHS` (`TopBar.tsx:81`). It hydrates from `GET /api/notifications` under `tap_routing_v2`. |
| Prefs UI | `mobile/src/screens/settings/sections/NotificationsSection.tsx` | Three toggles plus quiet hours (`:150-180`). The re-engagement toggle reads "Stay in the game". |

### Cross-kind quiet list — proposed, not live

`docs/plans/audit-p1-remediation/PRD-p1-9.md` proposes a cross-kind quiet list
`{deck_replenished, trade_found, winback_matches, winback_dormant, weekly_digest}` (gate P-4,
`:320`). It also proposes a non-exclusive `_freq_cap_blocks` change and its regression
criterion, AC-24 (`:179`). That PRD is **requirements only** (`:3`). `trade_found` is absent
from `NOTIF_KIND_TO_BUCKET` at this sha, and P-1…P-6 are open operator gates (`:380`).
Every new kind must still state its quiet-list membership, as the proposal would require.
Mark it "pending P-4" until the operator rules.

---

## 2. Per-kind spec template

Copy one block per kind into the PRD. Every field is answered or marked
`n/a — <reason>`.

```markdown
### Kind: `<snake_case_kind>`

- **Trigger:** <the event or scan condition, with the data it reads (table.column)>
- **Value refresh:** <what is NEW behind the tap. If nothing is new, stop: this kind
  is not allowed>
- **Audience:** <real DB fields, e.g. users.last_active_at < now-30d AND unread matches > 0;
  give the expected size as measured / assumed>
- **Sending tick and time:** <realtime-tick | hourly-tick (local hour) | daily-tick
  (13:30 UTC) | request path (route)>. Tick health checked on <date> (NEXT.md / runbook)
- **Dedup key:** <format, e.g. "{league_id}:{iso_week}", or none and why>
- **Cap:** class <window in _NOTIF_FREQ_CAPS | dedup in _NOTIF_DEDUP_CAPS | inline> = <N per D days>
- **Quiet-list membership:** <in / out of the cross-kind quiet list (pending P-4)>.
  Quiet hours: <bundled at 08:00 | exempt and why>
- **Prefs bucket and default:** <trade_matches | weekly_digest | reengagement>.
  Effective default given notif.reengagement_default_off = <on/off>. Reach at that
  default: <measured / assumed>
- **Primer consent:** <covered by the three primer bullets? If not, the primer copy
  change + ux-lead review>
- **Tap route:** <data.type → V2_*_KINDS set → tab/screen; deep param>. Landing screen
  owner: <box>
- **Inbox row:** <yes, written BESIDE the push via _write_inbox_row with its own
  idempotency | no>. New inbox type: <cross-client-invariants + both clients' glyph/tap maps>
- **Priming interplay:** <does it fire before permission is granted? Does any new
  in-app surface claim a useInterruptCoordinator slot, and at what priority?>
- **Events (each needs analytics-lead's grant, in the same commit as the emitter):**
  delivered = <push_sent{kind}> · opened = <push_opened{kind} — dark today> ·
  acted = <the destination's intent event>
- **Kill switch:** <flag name, default, flag-off = byte-identical tick payload?>
- **Copy table (marketing-lead writes the final words):**
  | Field | Limit | Draft intent | Voice notes |
  |---|---|---|---|
  | Title | ~40 chars effective | | |
  | Body | one line | | |
  | Inbox row | | | |
- **Evidence (D-056):** guard <mobile/tests/check-*.js and what it pins> · pytest
  <backend/tests/test_*.py, including the flag-off case> · code-walk <trigger → dispatcher
  → tap → landing, with file:line> · TestFlight <numbered operator steps with expected
  results>
- **Reviews needed:** ux-lead (flow / permission) · design-lead (any new visual) ·
  marketing-lead (copy) · analytics-lead (events) · <landing screen's box: league-pm | rankings-pm | trades-pm | draft-pm | onboarding-pm>
```

---

## 3. Per-kind health check for analytics-lead

Send these through `head-product`. You never run prod queries yourself. Ask for each answer
with its window and date.

1. **Is each kind being sent?** Rows per `kind` per week in `notification_events_log`
   (`backend/database.py:2334`, written only when a push leaves or is bundled). Is any kind
   that should be firing flat at zero?
2. **What is the cap-block and bucket-block rate?** Skips leave no row (see §1), so this
   needs the `push skipped` log lines or a new event. Ask what is answerable before you
   assume a number.
3. **What is the opt-in reach per bucket?** Counts of `notification_prefs` rows
   (`database.py:2324`) with each bucket set to 1, against signed-up users with a row in
   `device_tokens` (`database.py:2297`). The re-engagement bucket matters most, because
   it defaults off.
4. **How does the primer convert, and how does denial recovery do?** `push_primer_shown` /
   `push_primer_accepted` / `push_primer_dismissed` (`analytics_taxonomy.py:332`), and
   `notif_denied_settings_shown` / `notif_denied_settings_tapped` (`:347`). Pref changes
   are `notif_pref_changed` (server-fired, `server.py:23645`).
5. **What are the open and act rates?** `push_opened` is allowlisted (`:67`) but has no
   client emitter, and the `app_opened` props `from_push` / `push_kind` (`:918`) are not
   emitted either (`mobile/App.tsx:136`, `:205`). So per-kind open rate is **dark**
   (`analytics_queries.py:815`). Ask whether the inbox proxy (`notif_inbox_opened`,
   `notif_row_tapped`, `:296`) plus the destination's intent event is an acceptable
   stand-in, or whether wiring `push_opened` should come first.
6. **Is each tick returning 200?** Check the Render cron logs for `notif-realtime-tick`,
   `notif-hourly-tick` and `notif-daily-tick` over the last 14 days. A tick that 500s
   sends nothing after the failure point.
7. **Is the quiet-hours queue draining?** `notification_queue` (`database.py:2345`) rows
   whose `deliver_after` is more than a day in the past.

**Cautionary example.** `living-memory/NEXT.md:55-57` (2026-10-15) records that
`notif-daily-tick` is killed at the 120 s worker timeout every day. Every later step has
been silently dead since at least 2026-10-01, and the Monday and Tuesday kills most likely
sit in the re-engagement scan. `docs/runbook.md:613` has the detail. It went about two
weeks before anyone noticed. Run question 6 before any plan that leans on a tick, and
re-read NEXT.md for the current status rather than assuming it is fixed or still broken.
