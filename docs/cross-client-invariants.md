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

The Elo ranges that map a player into a tier. Single source of truth is `backend/tier_config.json`, served to clients via `GET /api/tier-config`; bucketing is a top-down walk assigning the first tier whose `min <= elo`.

**Banding rule (recalibrated 2026-07-10, FB #60/#69):** bands are per **position AND scoring format**, anchored to the DynastyProcess consensus seed scale (`elo = 1200 + value/10000 × 600`) with rank-count targets from the current consensus pool — Elite ≈ top 5, Starter ≈ through rank 15, Solid ≈ through rank 30, Depth = anything with real consensus value, Bench = the near-zero tail plus post-trio Elo down to 1150 (below 1150 = unranked; keeps the `no_value` anchor at Elo 1100 below every band). Occupancy is pinned by `backend/tests/test_tier_occupancy.py` against a checked-in consensus snapshot — recalibrate bands (and refresh that fixture) if consensus drift makes Elite leave the 2–10 range. A related invariant: `apply_reorder` (manual ranks) is a pure permutation of existing Elo values, so reorders never change tier occupancy.

**Locations:** `backend/tier_config.json` (canonical), `backend/ranking_service.py` (`tier_bands_for` / `tier_for_elo` / `apply_tiers`), `mobile/src/utils/tierBands.ts` (offline fallback mirror — keep in sync), `web/positional-tiers.html` + `extension` badge (consume the served config / backend walk).

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

## Match bucket labels & semantics (feedback #91)

Every trade a user has acted on sits in exactly **one** of two buckets, everywhere they're counted or listed:

| Bucket | `/api/league/summary` key | Definition | Sub/definition copy |
|---|---|---|---|
| Mutual matches | `matches_mutual` | Non-dismissed `trade_matches` rows involving the caller, **any** disposition status | `Liked by both sides` |
| Awaiting them | `matches_awaiting` | Caller's one-sided likes not yet matured into a match (repeat likes of the same trade deduped) | `Your like, waiting on theirs` |

A trade leaves "Awaiting them" and becomes a mutual match the moment the `trade_matches` row is created; disposition status never moves a match between buckets (see `backend/tests/test_league_summary_buckets.py`). The League tab's two Matches tiles must always equal the Matches screen's two segments. Casing follows each client's local convention (mobile sentence case "Mutual matches" / "Awaiting them"; web title-cases summary-card labels), but the wording and sub copy are shared.

The legacy `matches_pending` / `matches_accepted` keys (status-split, dismissal-blind) are still emitted for pre-1.4 clients — **do not read them in new UI.**

**Locations:** `backend/server.py` (`/api/league/summary`), `mobile/src/screens/LeagueScreen.tsx` + `mobile/src/screens/MatchesScreen.tsx`, `web/js/app.js` (`renderLeagueSummary`).

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

## Pick anchor keys

The pick-anchor wizard's answer vocabulary (2026-07-10), defined in `backend/server.py:VALID_ANCHORS` and sent verbatim by mobile (`mobile/src/api/rankings.ts:AnchorKey`, buttons in `mobile/src/screens/PickAnchorScreen.tsx`):

| Key | Button label | Pins to |
|---|---|---|
| `4_firsts` | 4 1sts | value_to_elo(4 × value(Mid 1st)) ≈ Elo 1927 |
| `3_firsts` | 3 1sts | value_to_elo(3 × value(Mid 1st)) ≈ Elo 1870 |
| `2_firsts` | 2 1sts | value_to_elo(2 × value(Mid 1st)) ≈ Elo 1789 |
| `1_first` | 1 1st | Mid 1st seed (Elo 1650) |
| `1_second` | 1 2nd | Mid 2nd seed (Elo 1460) |
| `1_third` | 1 3rd | Mid 3rd seed (Elo 1320) |
| `1_fourth` | 1 4th | Mid 4th seed (Elo 1240) |
| `no_value` | No value | Elo 1100 — below every band → unranked |

Anchor values are position-uniform on purpose (uniform valuation across position groups); tier assignment falls out of the per-position/format band walk. The Elo seeds come from `GENERIC_PICK_SEEDS` (`backend/server.py`) — if those seeds or the anchor set change, update the backend constant, the mobile union type + button rows, and this table. The ≈-Elo values above assume the default `elo_value_*` config (base 1000, ref 1500, k 0.005).

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
