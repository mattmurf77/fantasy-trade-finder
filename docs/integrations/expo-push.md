# Expo Push — mobile notification delivery

> Straggler picked up during the DynastyProcess/Anthropic integration audit — Expo's push-notification relay was found via a broad `urllib`/`requests` grep and wasn't yet documented under `docs/integrations/`. Documented here at the same level of detail as the other two.

## Table of Contents

- [What it is](#what-it-is)
- [Endpoint](#endpoint)
- [When it triggers](#when-it-triggers)
- [Request shape](#request-shape)
- [Response handling](#response-handling)
- [Error / fallback behavior](#error--fallback-behavior)
- [Frequency and gating](#frequency-and-gating)
- [Instrumentation guidance](#instrumentation-guidance)
- [Source](#source)

## What it is

Expo's hosted push-notification service (`exp.host`) relays notifications to the FTF mobile app's iOS/Android push channels on Expo's behalf — FTF's backend never talks to APNs/FCM directly. Device tokens (`ExponentPushToken[...]`) are registered client-side (`POST /api/notifications/register-device`) and stored in the `device_tokens` table; the backend's typed-push system (`_send_typed_push` → `_send_expo_push`) fans messages out to Expo's relay whenever a user-facing notification event fires (new trade match, deck replenishment, re-engagement digests, etc.).

## Endpoint

- **URL:** `https://exp.host/--/api/v2/push/send` (`server._EXPO_PUSH_URL`)
- **Method:** `POST`, JSON body, `Content-Type: application/json`, `timeout=10`s, no auth header (Expo's push API is unauthenticated for send — the push token itself is the capability).
- **Batching:** up to 100 messages per request (Expo's documented limit), chunked in `_send_expo_push`.

## When it triggers

Any call to `_send_typed_push(user_id, kind, title=..., body=..., data=..., dedup_key=...)` that survives, in order: (1) the user's bucket-level notification preference, (2) a per-kind frequency cap (`_NOTIF_FREQ_CAPS`, e.g. `winback_matches` at most 1/7 days), (3) a per-dedup-key lifetime cap for kinds like `match_expiring`/`first_match`/`deck_replenished`, and (4) quiet hours (22:00–08:00 user-local defers to `notification_queue`, drained by an 8am bundling tick instead of pushing immediately). If all four pass and the user has at least one registered device token, `_send_expo_push` fires.

Call sites include the trade-match-creation hook, the F10 weekly deck-replenishment cron tick, and various re-engagement/digest jobs — see `docs/runbook.md` § "Push notifications not arriving" and § "Weekly deck replenishment" for the operational side.

## Request shape

Each message in the batch:
```json
{ "to": "ExponentPushToken[...]", "title": "...", "body": "...", "data": {"...": "...", "type": "<kind>"}, "sound": "default" }
```
`_send_expo_push` filters to only tokens starting with `ExponentPushToken[` before sending (`_EXPO_TOKEN_PREFIX`) — non-conforming tokens (e.g. test/demo placeholder values) are silently dropped from the batch rather than sent, which is also the reason no explicit `FTF_TEST_MODE` seam exists for this egress: test/demo device tokens simply never match the prefix.

**Privacy considerations:** the push token itself is a device-identifying credential (Expo can deliver to that exact device/app install once it has this token). Title/body text is user-facing notification copy (e.g. "You have a new trade match!") — no raw PII (email, real name, session token) is put in the `data` payload; it carries the notification `kind` and IDs like `match_id`/`league_id` needed for client-side deep-linking.

## Response handling

`urlopen` response status is checked: `>= 300` logs a warning (`Expo push non-2xx: status=%s`); otherwise logs delivery of the chunk (`Expo push delivered: %d message(s)`). Expo's response body (which reports per-token receipt IDs/errors, e.g. `DeviceNotRegistered`) is **not parsed** — a token that Expo rejects (e.g. the app was uninstalled) is not detected or pruned from `device_tokens` today. That's a real gap: stale tokens will keep being sent to indefinitely until the user re-registers (e.g. on next sign-in).

## Error / fallback behavior

`_send_expo_push` wraps the whole batch send in `try/except Exception`, logs a warning (`_send_expo_push failed (non-fatal): %s`), and returns — never raises. Callers (`_send_typed_push`) treat a push attempt as fire-and-forget: the triggering action (match creation, deck replenishment, etc.) always completes regardless of push outcome. No retry, no dead-letter queue — a failed batch is simply dropped.

## Frequency and gating

Per-kind and per-dedup-key caps live in `_NOTIF_FREQ_CAPS` / `_NOTIF_DEDUP_CAPS` (`backend/server.py`) — see the module comment above `_EXPO_PUSH_URL` for the full table. Pushes exceeding a cap are silently skipped (logged to `user_events` as `push_skipped` with a reason, not sent to Expo at all — so they don't count against Expo call volume). No cost implications either way: Expo's push-send API is free.

## Instrumentation guidance

No PII/secrets to redact beyond the device token itself (device tokens are already logged in aggregate counts only, never individually, in the existing code). Recommended fields for structured logging:
- **Status:** per-chunk HTTP status from Expo, success/failure.
- **Latency:** wall-clock time of the `urlopen` call.
- **Batch size:** message count per chunk (already partially covered: `Expo push delivered: %d message(s)`).
- **Kind:** the notification `kind` driving the send (already captured via `record_event(..., "push_sent", props={"kind": kind, ...})` at the `_send_typed_push` level, but not at the raw-transport `_send_expo_push` level).
- **Rejected-token detection (gap):** parsing Expo's per-token response body to detect `DeviceNotRegistered`/`InvalidCredentials` and pruning `device_tokens` accordingly — not implemented today; flagged here as a real follow-up rather than done in this docs pass.

## Source

- `backend/server.py` — `_EXPO_PUSH_URL`, `_send_expo_push`, `_send_typed_push`, `register_device_for_push` (`POST /api/notifications/register-device`)
- `backend/database.py` — `device_tokens_table`, `save_device_token`, `load_device_tokens_for_users`
- `docs/api-reference.md` — `/api/notifications/register-device`, `/api/notifications/prefs`
- `docs/runbook.md` — "Push notifications not arriving", "Weekly deck replenishment (F10, flag `deck.replenishment`)"
- `docs/architecture.md` — data-flow diagram (External → `EX[Expo Push]`)
