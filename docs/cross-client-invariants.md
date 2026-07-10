# Cross-Client Invariants

Things that **must** stay in sync across backend, web, mobile, and the extension. Drift here = clients disagree silently. Update *all* listed locations together.

---

## Tier color tokens

Canonical hex per tier (re-canonicalized 2026-07-10 to de-collide from position colors — the 2026-07-04 set made Starter/Solid/Depth byte-identical to RB/WR/TE, source of TestFlight FB #83/#84). Rule: **tier hues must not share a hue with any position color.** Tiers are the *bright* family (Tailwind 400-level), positions the *deeper* family (500-level). Lighter same-hue accents (300/200-level borders and text on tinted dark backgrounds, as in the extension badge and web tier legend) are allowed per client, but the base identity color and rgba() tint bases must be these values.

| Tier | Color | Canonical hex | rgba tint base |
|---|---|---|---|
| Elite | gold | `#fbbf24` | `251,191,36` |
| Starter | teal | `#2dd4bf` | `45,212,191` |
| Solid | sky | `#38bdf8` | `56,189,248` |
| Depth | pink | `#f472b6` | `244,114,182` |
| Bench | gray | `#7a7f96` | `122,127,150` |

**Locations:** `mobile/src/theme/colors.ts` (`colors.tier`), `mobile/src/components/TierBadge.tsx` + `TierBin.tsx` (hardcoded rgba tint bases), `web/positional-tiers.html` (inline CSS: tier-row accents, tier-assign buttons, legend swatches), `web/profile.html` (inline `:root` vars `--elite`…`--bench`), `extension/content.css` (`.ftf-badge.ftf-tier-*`).

Note: `web/css/styles.css` has a separate 4-level *dynasty value* badge set (`.tier-elite/.tier-high/.tier-mid/.tier-depth`) — a different taxonomy, not these tokens. `extension/popup.css` contains no tier colors. Rank-medal accents (web `.ranked-1/2/3`, mobile `PlayerCard` rank styles) use the gold/silver/neutral medal tokens, not tier tokens.

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
| `👀 They're interested` | card has `likes_you: true` (likes-you pill) |
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

| Position | Color | Canonical hex |
|---|---|---|
| QB | orange | `#f97316` |
| RB | green | `#22c55e` |
| WR | blue | `#3b82f6` |
| TE | purple | `#a855f7` |

**Locations:** `mobile/src/theme/colors.ts` (`colors.position`), `mobile/src/components/PositionChip.tsx` (rgba tint bases), `web/profile.html` (`--qb`…`--te`), plus any progress-bar component. Tier colors must not reuse these hues (see Tier color tokens above).

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

## Feedback lifecycle statuses

`app_feedback.status` vocabulary, defined in `backend/database.py:FEEDBACK_STATUSES` and mirrored by the mobile inbox chips (`mobile/src/screens/FeedbackInboxScreen.tsx:STATUS_LABEL`):

| Status | User-facing label |
|---|---|
| `new` | 📬 Received |
| `planned` | 🗓 Planned |
| `in_progress` | 🔧 In progress |
| `fixed` | ✅ Fixed — in next update |
| `shipped` | 🚀 Shipped |
| `declined` | 🚫 Not planned |

NULL in the DB reads as `new` everywhere. If you add a status, update both files and this table.
