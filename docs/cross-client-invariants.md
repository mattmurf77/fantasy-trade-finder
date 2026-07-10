# Cross-Client Invariants

Things that **must** stay in sync across backend, web, mobile, and the extension. Drift here = clients disagree silently. Update *all* listed locations together.

---

## Tier color tokens

Canonical hex per tier (unified 2026-07-04; the extension's base hues are canon). Lighter same-hue accents (e.g. Tailwind 300/400-level borders and text on tinted dark backgrounds, as in the extension badge and web tier legend) are allowed per client, but the base identity color and rgba() tint bases must be these values.

| Tier | Color | Canonical hex |
|---|---|---|
| Elite | gold | `#f59e0b` |
| Starter | green | `#22c55e` |
| Solid | blue | `#3b82f6` |
| Depth | purple | `#a855f7` |
| Bench | gray | `#7a7f96` |

**Locations:** `mobile/src/theme/colors.ts` (`colors.tier`), `web/positional-tiers.html` (inline CSS: tier-row accents, tier-assign buttons, legend swatches), `web/profile.html` (inline `:root` vars `--elite`…`--bench`), `extension/content.css` (`.ftf-badge.ftf-tier-*`).

Note: `web/css/styles.css` has a separate 4-level *dynasty value* badge set (`.tier-elite/.tier-high/.tier-mid/.tier-depth`) — a different taxonomy, not these tokens. `extension/popup.css` contains no tier colors.

---

## Tier band Elo cutoffs

The Elo ranges that map a player into a tier.

**Locations:** `mobile/src/utils/tierBands.ts`, `web/js/app.js` (search "tier"), `extension/content.js` (search "tier"), any backend tier computation in `backend/`.

---

## K-factors

Authoritative defaults live in `model_config` (`elo_k`, `trade_k_like`, `trade_k_pass`, `trade_k_accept`, `trade_k_decline_correction`). Code reads them at runtime — don't hardcode.

| Decision | Default K |
|---|---|
| Rank (3-player) | 32 |
| Trade like | 8 |
| Trade pass | 4 |
| Trade accept | 20 |
| Trade decline correction | 20 |

**Locations:** `backend/ranking_service.py`, `backend/trade_service.py`. If you change the defaults in `_MODEL_CONFIG_DEFAULTS`, also update [config-reference.md](config-reference.md) and any client display.

---

## Scoring format strings

Allowed values: `'1qb_ppr'`, `'sf_tep'`. Null in legacy rows is treated as `'1qb_ppr'`.

**Locations:** `backend/database.py` (defaults), `backend/data_loader.py`, `backend/server.py`, `mobile/src/api/league.ts`, `web/js/app.js`. Tables affected: `swipe_decisions`, `member_rankings`, `elo_history`, `user_player_skips`, `leagues.default_scoring`.

---

## Decision type strings

`swipe_decisions.decision_type`: `'rank'`, `'trade'`. Hard-coded — search both before renaming.

---

## Notification type strings

`notifications.type` (in-app inbox): `trade_match`, `trade_accepted`, `trade_declined`. Used by mobile push handler (`mobile/src/hooks/usePushNotifications.ts`) and inbox renderers.

## Notification kinds vs. preference buckets

`notification_events_log.kind` is granular (e.g. `new_match`, `winback_dormant`, week-stamped digest kinds). Each kind maps to one of three user-facing **buckets** controlled by `notification_prefs`:

| Bucket | Toggle column | Includes kinds like… |
|---|---|---|
| `trade_matches` | `notification_prefs.trade_matches` | `new_match`, match dispositions |
| `weekly_digest` | `notification_prefs.weekly_digest` | weekly summary kinds |
| `reengagement` | `notification_prefs.reengagement` | `winback_dormant`, similar |

Mapping lives in `get_pref_bucket()` in `backend/server.py`. **Add a new kind in two places:** the dispatcher (so it routes correctly) and `notification_events_log` consumers that filter by kind.

---

## Trade-card copy strings (v2 engine UI)

Shared user-facing strings rendered by both mobile and web — must stay character-identical:

| String | Shown when |
|---|---|
| `They're interested` (preceded by the Chalkline `eye` icon, not an emoji — changed from `👀 They're interested` 2026-07-02, ADR-004) | card has `likes_you: true` (likes-you pill) |
| `Fair-value idea` | card has `basis: "consensus"` (consensus label/tag) |
| `This league-mate hasn't ranked players yet — this is a balanced trade by consensus value.` | consensus-card explainer (mobile body text; web `title` tooltip on the tag) |
| `+ {player name} added to balance the deal` | card has a `sweetener` (Tier 3) — name interpolated from the referenced player |

**Locations:** `mobile/src/components/TradeCard.tsx`, `web/js/app.js` (search "likes-you-pill" / "consensus-tag" / "trade-sweetener").

## Fairness meter semantics

`fairness_score` is serialized as a float in `[0, 1]` on every trade card (consensus package-value ratio, lesser/greater). Clients render it as a percent: `Math.round(fairness * 100)` driving a 0–100% meter. Do **not** rescale server-side — both clients multiply by 100.

**Locations:** `backend/server.py` (`trade_card_to_dict`), `mobile/src/api/trades.ts` + `mobile/src/components/TradeCard.tsx` (`fairPct`), `web/js/app.js` fairness meter.

---

## Team outlook modes

Canonical set: `championship`, `contender`, `rebuilder`, `jets`, `not_sure`.

**Locations to update together:** `backend/trade_service.py`, `backend/database.py` (`league_preferences.team_outlook` validation), `mobile/src/screens/LeagueScreen.tsx` + `mobile/src/components/OutlookSheet.tsx`, `web/js/app.js` outlook picker, `model_config` rows storing outlook multipliers.

---

## Ranking method strings

`users.ranking_method`: null, `'trio'`, `'manual'`, `'tiers'`.

**Locations:** `backend/server.py` (`/api/ranking-method`), each client's settings UI.

---

## Position color tokens (segmented progress bar)

| Position | Color |
|---|---|
| QB | orange |
| RB | green |
| WR | blue |
| TE | purple |

**Locations:** same files as tier colors plus any progress-bar component.

---

## Progress gating thresholds

Minimum rank decisions per position before Trade Finder unlocks. Tracked per scoring format; result lands in `users.unlocked_formats`.

| Position | Threshold |
|---|---|
| QB | 10 |
| RB | 10 |
| WR | 10 |
| TE | 10 |

**Locations:** `backend/server.py` gating logic, each client's progress bar.

---

## Wrapped event types

`wrapped_events.event_type`: `swipe`, `trade_match`, `trade_accepted`, `trade_declined`, `tier_save`, `ranking_reorder`, `league_sync`.

---

## user_events taxonomy

See [data-dictionary.md](data-dictionary.md#user_events). When adding a new event_type, add it to that list and to any client that emits it.

---

## Device platform / source enums

- `device_tokens.platform`: `ios`, `android`
- `user_events.device_type`: `iphone`, `ipad`, `macos`, `web`, `extension`
- `user_events.source`: `mobile`, `web`, `api`, `cron`

---

## Asset preference list types

`asset_preferences.list_type` vocabulary, defined in `backend/database.py:ASSET_PREF_LISTS` and sent verbatim by clients in the POST `/api/league/asset-prefs` body (`list` field — `mobile/src/api/league.ts:setAssetPref`):

- `untouchable` — never offer this player FROM the owner's roster in generated trades (feedback #95)
- `target` — bias suggestions toward acquiring this player
- `none` — POST-body-only sentinel meaning "remove the tag" (never stored)

A player holds at most one tag per (user, league). If you add a list type, update `ASSET_PREF_LISTS`, the mobile union type, and this list.

---

## Feedback lifecycle statuses

`app_feedback.status` vocabulary, defined in `backend/database.py:FEEDBACK_STATUSES` and mirrored by the mobile inbox chips (`mobile/src/screens/FeedbackInboxScreen.tsx:STATUS_LABEL`):

| Status | User-facing label | Visible in user inbox? |
|---|---|---|
| `new` | Received | yes |
| `planned` | Planned | yes |
| `in_progress` | In progress | yes |
| `fixed` | Fixed — in next update | yes (the notification that a fix is coming) |
| `shipped` | Shipped | **no — closed** |
| `declined` | Not planned | **no — closed** |

NULL in the DB reads as `new` everywhere. Labels are emoji-free as of the Chalkline re-skin (ADR-004). Closed statuses (2026-07-04) are defined in `backend/database.py:FEEDBACK_CLOSED_STATUSES` and mirrored in `mobile/src/api/feedback.ts:CLOSED_FEEDBACK_STATUSES` — `/api/feedback/mine` excludes them server-side AND the mobile inbox hides locally-persisted notes whose merged status is closed (or that no longer come back from `/mine` for the signed-in account). If you add or reclassify a status, update both constants and this table.
