# Cross-Client Invariants

Things that **must** stay in sync across backend, web, mobile, and the extension. Drift here = clients disagree silently. Update *all* listed locations together.

---

## Tier keys, labels & color tokens

**The tier taxonomy is the pick-value tier ladder (2026-07-11):** tier keys/labels read directly in draft-pick terms — a tier says what a player in it is worth in the Pick Anchor wizard's vocabulary. The former abstract five (elite/starter/solid/depth/bench) are retired; `bench` survives as the "below 4th-round value" floor. Keys are cross-client enums (sent verbatim in `/api/tiers/save`, served by `/api/tier-config`, `/api/extension/rankings`, `/api/anchor/save`, profile tier snapshots).

Color rule unchanged (re-canonicalized 2026-07-10 to de-collide from position colors): **tier hues must not share a hue with any position color.** Tiers are the *bright* family (Tailwind 400-level), positions the *deeper* family (500-level). Lighter same-hue accents (300/200-level borders and text on tinted dark backgrounds, as in the extension badge and web tier legend) are allowed per client, but the base identity color and rgba() tint bases must be these values.

| Tier key | Label | Color | Canonical hex | rgba tint base | Elo band [min, max] |
|---|---|---|---|---|---|
| `firsts_2plus` | 2+ 1sts | gold | `#fbbf24` | `251,191,36` | [1788, 1870] |
| `first_1` | 1st | teal | `#2dd4bf` | `45,212,191` | [1580, 1785] |
| `second` | 2nd | sky | `#38bdf8` | `56,189,248` | [1400, 1575] |
| `third` | 3rd | pink | `#f472b6` | `244,114,182` | [1280, 1395] |
| `fourth` | 4th | lime | `#a3e635` | `163,230,53` | [1220, 1275] |
| `bench` | Bench | gray | `#7a7f96` | `122,127,150` | [1150, 1215] |

**Locations (colors + labels):** `mobile/src/theme/colors.ts` (`colors.tier`), `mobile/src/components/TierBadge.tsx` + `chalkline/Badge.tsx` (`TierChalkBadge`) label maps, `mobile/src/utils/tierBands.ts` (`TIERS`/`TIER_LABEL`), `web/positional-tiers.html` (inline CSS: tier-row accents, tier-assign buttons, legend swatches; JS `TIERS`/`TIER_LABELS_SHORT`), `web/profile.html` (inline `:root` vars + `TIER_ORDER`/`TIER_LABELS`), `web/style-guide.html` (badge swatches), `extension/content.css` (`.ftf-badge.ftf-tier-*`) + `extension/content.js` (`TIER_LABELS`), `backend/og_image.py` (`TIER_ORDER`/`TIER_LABELS`/`TIER_TINTS`).

Note: `web/css/styles.css` has a separate 4-level *dynasty value* badge set (`.tier-elite/.tier-high/.tier-mid/.tier-depth`) — a different taxonomy, not these tokens. Likewise `trade_service.analyze_roster_strengths`' `tier_depth` profile bins (`elite/starter/bench`, KTC-value thresholds) and the `tier_mult_*` `model_config` keys are backend-internal engine taxonomies that merely reuse the old words — they are NOT the tier enum and were deliberately left untouched by the 2026-07-11 ladder migration. `extension/popup.css` contains no tier colors. Rank-medal accents (web `.ranked-1/2/3`, mobile `PlayerCard` rank styles) use the gold/silver/neutral medal tokens, not tier tokens.

---

## Tier band Elo cutoffs

The Elo ranges that map a player into a tier. Single source of truth is `backend/tier_config.json`, served to clients via `GET /api/tier-config`; bucketing is a top-down walk assigning the first tier whose `min <= elo`.

**Banding rule (pick-value ladder, 2026-07-11):** each tier's floor is a rung of the anchor/pick Elo ladder (`GENERIC_PICK_SEEDS` + the multi-first anchor Elos — see "Pick anchor keys" below): `firsts_2plus` ≥ 1788 (just under `value_to_elo(2 × Mid 1st)` = 1788.6, so a "2 firsts" anchor pin lands inside; 3/4-firsts pins at 1869.7/1927.2 land here too), `first_1` ≥ 1580 (Late 1st seed — "worth a pick in round 1"), `second` ≥ 1400 (Late 2nd), `third` ≥ 1280 (Late 3rd), `fourth` ≥ 1220 (Late 4th), `bench` = below 4th-round value down to 1150 (below 1150 = unranked; keeps the `no_value` anchor at Elo 1100 below every band). Because pick value is position-uniform by design, the bands are **identical across positions AND scoring formats** — the JSON keeps its per-(format, position) shape so consumers don't change, but every cell holds the same six bands. Occupancy differs per position/format because the seed Elos differ (`elo = 1200 + value/10000 × 600`; e.g. 1QB QBs are rarely worth a 1st — that asymmetry is the point). Occupancy + the "every anchor rung lands in the tier that carries its name" invariant are pinned by `backend/tests/test_tier_occupancy.py` against a checked-in consensus snapshot. A related invariant: `apply_reorder` (manual ranks) is a pure permutation of existing Elo values, so reorders never change tier occupancy.

Saved boards need no data migration when bands change: `users.tier_overrides` stores raw Elo per player, so overrides re-bucket through the new walk on read.

**Locations:** `backend/tier_config.json` (canonical), `backend/ranking_service.py` (`ORDERED_TIERS` / `tier_bands_for` / `tier_for_elo` / `apply_tiers`), `mobile/src/utils/tierBands.ts` (offline fallback mirror — keep in sync), `web/positional-tiers.html` (fallback `TIER_CONFIG` mirror), `web/js/app.js` (`_eloToTierLabel` floor mirror), `extension` badge (consumes the backend walk).

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

## Verified-via strings (account-auth P1/P2)

`users.verified_via` / session `verified_via` / `GET /api/account`: `'sleeper'`, `'apple'`, `'google'`. NULL = never verified. Identity-provider strings double as `linked_identities.provider` values (`'apple'`, `'google'`).

**Locations:** `backend/accounts.py` (`PROVIDERS`), `backend/server.py` (auth routes), `mobile/src/api/auth.ts` (`AccountInfo` / `AccountAuthResponse` types).

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

`users.ranking_method`: null, `'trio'`, `'manual'`, `'tiers'`, `'anchor'` (added 2026-07-10 with the Pick Anchor wizard + rank-home chooser).

**Locations:** `backend/server.py` (`/api/ranking-method` whitelist), `mobile/src/api/rankings.ts` (`setRankingMethod` union), `mobile/src/state/useSession.ts` (`RankMethodPref` — the device-local launch-routing preference), `mobile/src/navigation/TabNav.tsx` (`PREF_ROUTE` map), `mobile/src/screens/RankHomeScreen.tsx` + `mobile/src/components/SteerSlider.tsx` (the two pickers). Add a method in all of these together.

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

**Per-user pick-value scale does NOT change this enum** (1.5.4 #111): `/api/anchor/scale` lets a user declare "a top-tier asset = N firsts" (N ∈ 2/3/4, default 2 = the table above, persisted in `users.anchor_scale`). A non-default N re-spaces only the three multi-first rows' target Elos for THAT user's saves (`m firsts → value(Mid 1st) × m^(log 2 / log N)`; the user's own N-firsts answer pins to the default top-tier Elo ≈ 1789). The keys, button labels, single-pick rows, `no_value`, the generic pick assets in the pool, the calculator's `gap` firsts unit (`/api/trade/evaluate` is public/sessionless), and the tier-ladder band floors all stay consensus-denominated per this table. A scaled user's own top-tier answer (m = N) still pins to Elo ≈ 1789 → `firsts_2plus`; their intermediate multi-first answers re-space downward and may land in `first_1` — by design (on that user's scale those packages are worth less than a top-tier asset).

**Tier labels ARE pick terms** (2026-07-11, supersedes the 1.5.4 #103 display-sublabel approach): the tier ladder itself is denominated in this table's vocabulary — every anchor answer lands in the tier that carries its name (`2_firsts`/`3_firsts`/`4_firsts` → `firsts_2plus`, `1_first` → `first_1`, …, `no_value` → unranked). `mobile/src/utils/pickTerms.ts` (the #103 sublabel helper) was removed. If `GENERIC_PICK_SEEDS` or the anchor multiples change, recalibrate `backend/tier_config.json` (and its mirrors) alongside the locations above so the name↔rung invariant holds (`test_tier_occupancy.py::test_anchor_rungs_land_in_matching_tiers`).

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
