# Feature Scope — notification inbox as a growth surface (phase 1)

**Date:** 2026-08-13
**Entry point:** direct ask — pm-growth build brief off
[`docs/business/product/2026-08-12-notification-inbox-growth-surface.md`](../../business/product/2026-08-12-notification-inbox-growth-surface.md)
**Builder:** eng-manager session, branch `feat/notif-inbox-growth`
**Base:** `origin/main` @ `4c67309` (the brief cited `4a4b671`; main moved 4 commits — see §6)
**Operator sign-off on waivers:** yes — D-P1-08 (no Maestro, no simulator gate) restated in the build brief

Operator decisions GD-1…GD-8 are binding and are recorded in
[`../../business/product/2026-08-12-notification-inbox-growth-surface.md`](../../business/product/2026-08-12-notification-inbox-growth-surface.md) §7
with the reasoning behind each.

---

## 1. Analytics scope

**(a) New events specced.** Full tracking plan: [`analytics.md`](analytics.md).

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `notif_inbox_opened` | `unread_count`, `row_count` | bell sheet opens | mobile |
| `notif_row_tapped` | `type`, `position`, `age_hours` | an inbox row is tapped | mobile |
| `notif_empty_state_shown` | `not_joined`, `total_mates`, `invite_offered` | empty state renders | mobile |
| `invite_cta_shown` / `invite_cta_tapped` / `invite_shared` | **`surface` enum gains `notif_empty`** | unchanged | mobile |

Classification (M10 — the registry is default-deny behind a 200, and
`INTENT_EVENTS` is derived by subtraction):

- `notif_inbox_opened` → **NON_INTENT**
- `notif_empty_state_shown` → **NON_INTENT**
- `notif_row_tapped` → **INTENT**

Both NON_INTENT names are added to `analytics_queries.NON_INTENT_EVENTS` in the
**same commit** that registers them. Registration lands in **commit 1**, before
any client emitter exists.

**Known limitation, stated so it is not over-read later:** `web/` has no client
analytics SDK at all — no `track()`, no `/api/events` caller. These three events
measure the **mobile** bell only. The web bell stays unmeasured, and the mobile
numbers are not a whole-product bell open rate.

**Second limitation, carried from D-P1-04:** the bell sheet's empty state renders
inside a `<View>`, not a scroll container. `invite_cta_shown{notif_empty}` is a
mount counter under the same caveat the `matches_empty` surface already carries.
The sheet is short enough that clipping is unlikely, but the event is not proof
of an impression.

## 2. Schema & flag scope

- **New/changed columns:** `notifications.dismissed_at VARCHAR` (NULL = live).
  Additive, idempotent `ALTER TABLE` in the existing `migration_cols` block.
  → `docs/data-dictionary.md` updated.
- **New `notifications.type` values (6):** `referral_joined` (already written,
  newly rendered), `league_member_joined`, `league_member_unlocked_trades`,
  `match_expiring`, `deck_replenished`, `counter_offer` (glyph/routing only —
  see §6). Cross-client enum → `docs/cross-client-invariants.md` updated.
- **New feature flags:** none. Per D-P1-07 a flag over server routes is not a
  usable rollback lever, and these are additive rows — `git revert` is clean and
  total. Stated as a deliberate choice, not an omission.
- **New env vars / `model_config` keys:** none → `docs/config-reference.md` n/a.

## 3. Test scope

- **Maestro: WAIVED** — D-P1-08, restated by the operator in this build brief.
  TestFlight is primary QA for this change class.
- **Simulator gate: WAIVED** — same decision. `FTF_SKIP_SIM_GATE=1` on push, with
  the TEST_LEDGER note naming the waiver and its source.
- `testID`s added: `topbar.notif-empty`, `topbar.notif-empty-invite`,
  `topbar.notif-clear-all` — all pass `mobile/scripts/testid-lint.sh`.
- **Capture delta:** none — no screen in the capture library owns the bell sheet.
- **Backend pytest:** `backend/tests/test_notif_inbox_growth.py` (new) covers the
  coalescer, the `match_expiring` inbox idempotency gate, and the dismiss route.
  `backend/tests/test_analytics_p0.py` extended for the taxonomy registration.
- **Mobile:** `mobile/tests/check-notif-glyphs.js` (new) pins glyph/routing
  coverage for all six types so a kind can never ship render-ready on one client
  and grey-bell on the other.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `POST /api/notifications/dismiss-all` added |
| `living-memory/LLD.md` | **updated** | new convention: an inbox row is written beside a push, never by the dispatcher |
| `docs/architecture.md` | n/a | no module added, removed, or re-wired |
| `living-memory/HLD.md` | n/a | no architecture shift — existing table, existing clients |
| `docs/cross-client-invariants.md` | **updated** | six `notifications.type` values are a cross-client enum; the failure mode is a silent grey bell |
| `docs/glossary.md` | **updated** | "inbox row" vs "push" as distinct objects |
| `DECISIONS.md` entry | **updated** | D-### — inbox rows are written at the call site, not in `_send_typed_push` |
| `docs/data-dictionary.md` | **updated** | `dismissed_at` column + the six type values |

## 5. Ship gate declaration

- **Simulator-gate tier:** **4 — none, CI only.** Operator deviation from the
  matrix is pre-authorised by D-P1-08 and restated in this build brief.
- Evidence: TEST_LEDGER entry naming the waiver; no `qa/sim-runs/last-sim-run.json`
  written (there is no run to record).
- CI must be green before merge. Secrets rules and the recovery ledger apply.

## 6. Premise checks — what did not hold

Verified against `origin/main` @ `4c67309`, in the spirit of D-P1-14.

1. **`counter_offer` has no emitter anywhere in the backend.** The brief asks for
   a `create_notification` "beside the existing `_send_typed_push` call" for it.
   There is no such call. The only references are a bucket mapping
   (`backend/database.py:10097`) and the two clients' kind sets — it is a kind
   that was plumbed and never fired. **Resolution:** no inbox write for
   `counter_offer` (there is nothing to sit beside, and inventing a counter-offer
   trigger is outside this batch). It **does** get a glyph and a tap route in both
   clients, so if the kind ever ships it renders correctly on day one. Four
   `create_notification` sites, not five.
2. **Routing for the new kinds mostly already exists on mobile.** `match_expiring`
   and `counter_offer` are already in `V2_MATCH_KINDS`; both league kinds are in
   `V2_LEAGUE_KINDS`; `deck_replenished` is in `V2_TRADE_KINDS`. Only
   `referral_joined` needs a routing entry. Mobile routing is one line, not six.
   Web needs all six — it has an independent router that knows three types.
3. **Main moved.** The brief pins `4a4b671`; `origin/main` is `4c67309`, four
   commits ahead, including +215 lines in `backend/server.py` (the ESPN
   device-credential work). Every line number in the brief is shifted. Nothing in
   those commits touches the notification path — verified by reading the diff —
   so the brief's substance is unaffected.
4. **GD-7's vehicle, already corrected in the brief.** There is no P1-9 taxonomy
   commit to ride; commit 1 on this branch is the registration-only commit.
