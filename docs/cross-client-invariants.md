# Cross-Client Invariants

Things that **must** stay in sync across backend, web, mobile, and the extension. Drift here = clients disagree silently. Update *all* listed locations together.

---

## Tier keys, labels & color tokens

**The tier taxonomy is the 8-tier pick-value ladder (2026-07-12, feedback #117/#118; supersedes the 2026-07-11 six):** tier keys/labels read directly in draft-pick terms — a tier says what a player in it is worth in the Pick Anchor wizard's vocabulary. The 2026-07-11 keys `firsts_2plus` and `bench` are retired (`firsts_2` and `waivers` replace them; `apply_tiers` no-ops unknown keys so stale clients sending old keys degrade safely, and `users.tier_overrides` stores raw Elo so saved boards re-bucket automatically). Keys are cross-client enums (sent verbatim in `/api/tiers/save`, served by `/api/tier-config`, `/api/extension/rankings`, `/api/anchor/save`, profile tier snapshots).

Color rule unchanged (re-canonicalized 2026-07-10 to de-collide from position colors): **tier hues must not share a hue with any position color.** Tiers are the *bright* family (Tailwind 400-level), positions the *deeper* family (500-level). Lighter same-hue accents (300/200-level borders and text on tinted dark backgrounds, as in the extension badge and web tier legend) are allowed per client, but the base identity color and rgba() tint bases must be these values. (The two hues added for the #117 top tiers: red-400 is a distinct hue family from the semantic `--neg` red-500 by the same bright-vs-deep rule that separates tier gold `#fbbf24` from `--warn` amber-500; fuchsia-400 is magenta, distinct from TE purple-500 and from tier pink `#f472b6`.)

| Tier key | Label | Color | Canonical hex | rgba tint base | Elo band [min, max] |
|---|---|---|---|---|---|
| `firsts_4plus` | 4+ 1sts | red | `#f87171` | `248,113,113` | [1927, 1972] |
| `firsts_3` | 3 1sts | fuchsia | `#e879f9` | `232,121,249` | [1869, 1922] |
| `firsts_2` | 2 1sts | gold | `#fbbf24` | `251,191,36` | [1788, 1864] |
| `first_1` | 1 1st | teal | `#2dd4bf` | `45,212,191` | [1580, 1785] |
| `second` | 2nd | sky | `#38bdf8` | `56,189,248` | [1400, 1575] |
| `third` | 3rd | pink | `#f472b6` | `244,114,182` | [1280, 1395] |
| `fourth` | 4th | lime | `#a3e635` | `163,230,53` | [1220, 1275] |
| `waivers` | FA | gray | `#7a7f96` | `122,127,150` | [1150, 1215] |

The `waivers` display label was renamed **"Waivers" → "FA"** on 2026-07-17 (label-only; the key, hex, and band are unchanged).

**Locations (colors + labels):** `mobile/src/theme/colors.ts` (`colors.tier`), `mobile/src/components/TierBadge.tsx` + `chalkline/Badge.tsx` (`TierChalkBadge`) label maps, `mobile/src/utils/tierBands.ts` (`TIERS`/`TIER_LABEL`), `web/positional-tiers.html` (inline CSS: tier-row accents, tier-assign buttons, legend swatches; JS `TIERS`/`TIER_LABELS_SHORT`), `web/profile.html` (inline `:root` vars + `TIER_ORDER`/`TIER_LABELS`), `web/style-guide.html` (badge swatches), `extension/content.css` (`.ftf-badge.ftf-tier-*`) + `extension/content.js` (`TIER_LABELS`), `backend/og_image.py` (`TIER_ORDER`/`TIER_LABELS`/`TIER_TINTS`).

Note: `web/css/styles.css` has a separate 4-level *dynasty value* badge set (`.tier-elite/.tier-high/.tier-mid/.tier-depth`) — a different taxonomy, not these tokens. Likewise `trade_service.analyze_roster_strengths`' `tier_depth` profile bins (`elite/starter/bench`, KTC-value thresholds) and the `tier_mult_*` `model_config` keys are backend-internal engine taxonomies that merely reuse the old words — they are NOT the tier enum and were deliberately left untouched by the 2026-07-11/12 ladder migrations. `extension/popup.css` contains no tier colors. Rank-medal accents (web `.ranked-1/2/3`, mobile `PlayerCard` rank styles) use the gold/silver/neutral medal tokens, not tier tokens.

---

## Tier band Elo cutoffs

The Elo ranges that map a player into a tier. Single source of truth is `backend/tier_config.json`, served to clients via `GET /api/tier-config`; bucketing is a top-down walk assigning the first tier whose `min <= elo`.

**Banding rule (8-tier pick-value ladder, 2026-07-12):** each tier's floor is a rung of the anchor/pick Elo ladder (`GENERIC_PICK_SEEDS` + the multi-first anchor Elos — see "Pick anchor keys" below): `firsts_4plus` ≥ 1927 (just under `value_to_elo(4 × Mid 1st)` = 1927.3; its max 1972 sits just under the 5-firsts rung), `firsts_3` ≥ 1869 (just under `value_to_elo(3 × Mid 1st)` = 1869.7), `firsts_2` ≥ 1788 (just under `value_to_elo(2 × Mid 1st)` = 1788.6), `first_1` ≥ 1580 (Late 1st seed — "worth a pick in round 1"), `second` ≥ 1400 (Late 2nd), `third` ≥ 1280 (Late 3rd), `fourth` ≥ 1220 (Late 4th), `waivers` = below 4th-round value down to 1150 (below 1150 = unranked; keeps the `no_value` anchor at Elo 1100 below every band). Because pick value is position-uniform by design, the bands are **identical across positions AND scoring formats** — the JSON keeps its per-(format, position) shape so consumers don't change, but every cell holds the same eight bands. Occupancy differs per position/format because the seed Elos differ (`data_loader.seed_elo_for_value` — the #117 recalibration: DP values map affinely onto the trade-value scale, DP 0 → Elo 1200 and DP 10000 → the 4-firsts rung ≈ 1927.3, so the OVERALL top consensus assets read ≈ 3–4 firsts and reach the top two tiers, while e.g. 1QB QBs still rarely clear a 1st — that asymmetry is the point; empty-by-default top tiers for weak positions are expected, user anchors/rankings can populate them). Occupancy + the "every anchor rung lands in the tier that carries its name" invariant are pinned by `backend/tests/test_tier_occupancy.py` against a checked-in consensus snapshot. A related invariant: `apply_reorder` (manual ranks) is a pure permutation of existing Elo values, so reorders never change tier occupancy.

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

**Detection collapse convention (two buckets only):** Superflex **or** TE Premium → `'sf_tep'`; otherwise `'1qb_ppr'`. SF is the dominant value-driver, and a TEP-only league is still closer to the sf_tep board than to plain 1QB PPR. Implementations: Sleeper `server._detect_scoring_format_from_meta` (`SUPER_FLEX` slot / QB count ≥ 2; `bonus_rec_te > 0`) and MFL `mfl_service.detect_scoring_format` (#201: max startable QBs ≥ 2 from the `league` export's lineup config; TE per-reception points > WR's from the `rules` export). Any new platform detector must use the same collapse.

**Locations:** `backend/database.py` (defaults), `backend/data_loader.py`, `backend/server.py`, `backend/mfl_service.py` (detection), `mobile/src/api/league.ts`, `web/js/app.js`. Tables affected: `swipe_decisions`, `member_rankings`, `elo_history`, `user_player_skips`, `leagues.default_scoring`.

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
| `reengagement` | `notification_prefs.reengagement` | `winback_dormant`, `deck_replenished` (F10 weekly fresh-deck push — deliberately in this bucket so `notif.reengagement_default_off` applies), similar |

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

`fairness_score` is serialized as a float in `[0, 1]` on every trade card (consensus package-value ratio, lesser/greater). The **web** still renders it as a percent: `Math.round(fairness * 100)` driving a 0–100% meter (do **not** rescale server-side). **Mobile (1.10.0+) no longer renders `fairness_score`** on the deck — it renders the pick-denominated value bar (below) instead. `fairness_score` stays serialized (web meter + `trade_narrative` still read it).

**Locations:** `backend/server.py` (`trade_card_to_dict`), `web/js/app.js` fairness meter.

## Trade value-verdict shape (`favors` + `gap`) — the value bar

The pick-denominated **TradeValueBar** (feedback #157) is the universal trade verdict — it replaces the mobile deck's 0–1 fairness meter. It reads four fields that BOTH `POST /api/trade/evaluate` and every deck card (`/api/trades`, `/api/trades/status`, `/api/trades/liked`) now carry, built by the single shared helper `_value_verdict_payload` in `backend/server.py`:

- `favors`: enum **`give` | `receive` | `even`** — who the value leans to (`receive` = the caller/you win). `even` is set when the package point ratio ≥ 0.95. (`/api/trade/evaluate` may also return `favors: null` on a one-sided read; deck cards always have both sides.)
- `give_value` / `receive_value`: consensus package values (value space, `elo_to_value` over the seed) — the SAME numbers the calculator shows for the same players.
- `gap`: `{value, add_to: give|receive|null, firsts, pick_equivalent}` — the consensus delta in generic-pick terms; `add_to` is the LIGHTER side needing the sweetener. `null` only when one-sided; on an exactly-even trade `gap.value` is 0 and `pick_equivalent` is `null`.

Deck cards **omit** all four when rebuilt from client echo (server-restart FB-46 path); clients gate the bar on `give_value`/`receive_value` being present.

**Locations to update together:** `backend/server.py` (`_value_verdict_payload`, `trade_evaluate_route`, `trade_card_to_dict`), the card-construction sites in `backend/trade_service.py` + `backend/trade_optimizer.py` (stamp `give_value`/`receive_value`), `mobile/src/components/TradeValueBar.tsx` + `TradeCard.tsx`, `mobile/src/api/trades.ts` + `mobile/src/api/calc.ts` + `mobile/src/shared/types.ts`.

---

## Playoff outlook bands (#169, flag `outlook.odds`)

The **only** permitted rendering of `GET /api/league/outlook`'s `teams[].odds.playoff_pct`. The band is a data encoding by the same rule that governs tier colors — a client must read these keys, thresholds and colors, never re-derive them.

| Band key | Label | Threshold on `playoff_pct` (0..1) | Color token | Canonical hex |
|---|---|---|---|---|
| `likely` | Likely | `>= 0.65` | semantic `pos` | `#22C55E` |
| `tossup` | Toss-up | `>= 0.35` and `< 0.65` | semantic `warn` | `#F59E0B` |
| `unlikely` | Unlikely | `< 0.35` | semantic `neg` | `#EF4444` |

Bucketing is a top-down walk (first band whose floor the value clears), so the boundaries belong to the higher band: exactly `0.65` is `likely`, exactly `0.35` is `tossup`. Colors are the pos/warn/neg **semantic** tokens, not tier or position hexes; the label always ships next to the color (color alone fails a color-blind read).

**Why bands and not percentages** ([`docs/feedback/items/169-outlook-league-summary/calibration-combined-2026-08-10.md`](feedback/items/169-outlook-league-summary/calibration-combined-2026-08-10.md) §7): the engine is over-confident at the extremes — a 95% preseason call realizes 78% — and the preseason skill lower CI bound is +2.9%. Three bands are the finest granularity that evidence supports (≥0.65 buckets realize 0.60–0.78; ≤0.35 buckets realize 0.0–0.5). Two rules travel with the thresholds and are part of the invariant:

- **`meta.beta` is the two-state switch.** It clears at `completed_weeks >= 6`. Weeks 0–5 (beta true): bands and row order only, **no win-loss numbers** — a projected record is the same false-precision point estimate as a percentage in a different unit. Week 6+ (beta false): rows may add current + projected records.
- **`odds.title_pct` is unrenderable at any week, in any form.** Not a calibration judgement — an absence of skill (CI spans zero; 3 of 6 backtested league-seasons lose to a constant). It is served but never shown, banded or numeric.

A **playoff** percentage rounded to the nearest 5%, from week 6 only, is the one documented alternative to the band chip — an operator risk call on pooled (not week-stratified) calibration, not a validated result. It ships **off** (`OUTLOOK_WEEK6_PERCENT_ENABLED` in `LeagueSummaryScreen.tsx`); the 5% rounding is load-bearing if it is ever turned on.

Row **order** is a sibling encoding: a surface presenting the rows as projected standings sorts by `odds.projected_seed` ascending (ties → `playoff_pct` desc → `roster_id` asc). The payload's own ordering is by `playoff_pct`, which is nearly but not exactly the standings order.

**Locations to update together:** `mobile/src/screens/LeagueSummaryScreen.tsx` (`PLAYOFF_BAND_LIKELY_MIN` / `PLAYOFF_BAND_UNLIKELY_MAX` / `PLAYOFF_BAND_LABEL` / `PLAYOFF_BAND_COLOR` / `playoffBand`), `mobile/src/theme/chalkline.ts` (`semantic`), `mobile/src/api/league.ts` (the `odds` field notes), and — when web parity lands — `web/league-rankings.html`. Backend serves raw fractions and must stay band-agnostic.

---

## Deck disposition (Pass / Like) (#169)

The trade deck's disposition control pair is named **Pass / Like** — operator
decision ([`feedback/items/169-outlook-league-summary/operator-frame-decisions-2026-08-11.md`](feedback/items/169-outlook-league-summary/operator-frame-decisions-2026-08-11.md) §7 Q2).
No client introduces "Accept/Decline", "Send offer", or any third vocabulary
for this control, **in any string surface**: visible copy, testIDs, *and*
accessibility/VoiceOver labels (the pre-#169 "Accept this trade" labels were
renamed for exactly this rule).

- **testIDs:** `trades.pass-btn` / `trades.like-btn` — the cross-client names
  for the pair; Maestro flows and any future client bind to these.
- **Card ordering rule (operator, same decision record §3/§8):** the
  disposition pair sits **directly beneath the player tile section** inside
  the deck card; `TradeValueBar` sits below the pair; **any future card
  outlook/odds block mounts below `TradeValueBar`** ("value bar above the
  playoff outlook" — vacuous while no card odds block exists, binding on
  whoever designs the deferred week-6+ treatment).
- "Send in Sleeper" is a separate action (proposal transport), not a
  disposition — it keeps its own naming and placement outside this rule.

**Locations to update together:** `mobile/src/components/TradeCard.tsx`
(disposition row + a11y strings), `mobile/src/screens/TradesScreen.tsx`
(`SwipableTopCard` a11y actions), `mobile/.maestro/flows/smoke/06-trades-deck.yaml`
+ `mobile/.maestro/capture/onboarding-tour@fresh.yaml` (the flows that tap
the pair), and any future web/extension deck surface.

---

## Team outlook modes

Canonical set: `championship`, `contender`, `rebuilder`, `jets`, `not_sure`.

**Locations to update together:** `backend/trade_service.py`, `backend/database.py` (`league_preferences.team_outlook` validation), `mobile/src/screens/LeagueScreen.tsx` + `mobile/src/components/OutlookSheet.tsx`, `web/js/app.js` outlook picker, `model_config` rows storing outlook multipliers.

---

## Trade-card lane enum (phase 2, 2026-07-17)

Canonical set: `window`, `value` — the optional `lane` field on trade cards (flag `trade.lanes`; absent when the user has no declared/seeded window). `window` = the trade moves roster composition toward the user's contend/rebuild window; `value` = pure value play. Classified by `trade_service.classify_lane`; also logged in swipe `user_events` props for A/B joins.

**Display labels (#256, 2026-08-08):** `window` renders as **"Team-fit moves"** (web card chip `TEAM-FIT MOVE`), `value` as **"Value moves"** (`VALUE MOVE`). "Window" was the engine's word and read as jargon to testers; the label is presentation-only and must stay in sync across clients — the enum values and the `lane-chip--window` / `lane-chip--value` class names are unchanged. Deliberately not "Win-now moves": the `window` lane is win-now for a contender and youth+picks for a rebuilder.

**Locations to update together:** `backend/trade_service.py` (`classify_lane`, `_LANE_SIGN`), `backend/server.py` (`trade_card_to_dict` + swipe event props), `mobile/src/shared/types.ts` + `mobile/src/screens/TradesScreen.tsx` (lane filter), `web/index.html` (lane filter buttons), `web/js/app.js` `renderTrades` (`lane-chip--window` / `lane-chip--value` chips).

---

## Stud-tax mode strings (#214/#215)

Canonical set: `market` (retuned default — NULL/unknown stored values read as market), `heavy` (pre-#214 legacy adjustment math, byte-identical), `off` (no crown premium / package-depth discount; naive sums stand). Stored per user (`users.stud_tax_mode`), served by `GET/PUT /api/settings/stud-tax`, echoed by `POST /api/trade/evaluate` as `stud_tax_mode`.

**Locations to update together:** `backend/trade_service.py` (`STUD_TAX_MODES` / `STUD_TAX_DEFAULT`), `backend/database.py` (`STUD_TAX_MODES` validation + `get/set_stud_tax_mode`), `backend/server.py` (`/api/settings/stud-tax` whitelist), `mobile/src/api/calc.ts` (`StudTaxMode` union), `mobile/src/screens/SettingsScreen.tsx` (`STUD_TAX_OPTIONS` segmented control), `mobile/src/components/AdjustmentsDisclosure.tsx` (the `'off'` note).

---

## Ranking method strings

`users.ranking_method`: null, `'trio'`, `'manual'`, `'tiers'`, `'anchor'` (added 2026-07-10 with the Pick Anchor wizard + rank-home chooser), `'quickset'` (added 2026-07-12, #119 — the guided tier quick-set walk promoted to a first-class method; unlocks like `'tiers'` since it writes through `/api/tiers/save`).

**Locations:** `backend/server.py` (`/api/ranking-method` whitelist), `mobile/src/api/rankings.ts` (`setRankingMethod` union), `mobile/src/state/useSession.ts` (`RankMethodPref` — the device-local launch-routing preference), `mobile/src/navigation/TabNav.tsx` (`PREF_ROUTE` map), `mobile/src/screens/RankHomeScreen.tsx` + `mobile/src/components/SteerSlider.tsx` (the two pickers). Add a method in all of these together.

**The CONTRACT shifted on 2026-08-11 (P0-1); the string set did not.** It used to mean *"the chooser recorded the user's stated preference"*. It now means *"written at the point of USE, first-use wins"* — four save routes record it as a side effect of a successful save (`/api/tiers/save`, `/api/rank3`, `/api/rankings/reorder`, `/api/anchor/save`), and `'anchor'` is the single upgradable value (a completeness-marking tiers/quickset save may overwrite it, because `'anchor'` can never satisfy an unlock branch). Subset boards — rookie-scope tier saves, `via:'rookie_ranks'`, `via:'draft_room'` — write nothing. **This belongs here and not only in the backend docs because the value is read by two clients:** the unlock ladder in `get_rankings_progress` branches on it, and `web/js/app.js:866` reads it for truthiness. A pre-fix cohort was backfilled to `'quickset'` — see [data-dictionary § users](data-dictionary.md#users). Full rationale: [api-reference § Progress / method](api-reference.md#progress--method).

---

## `no_league` — the account-only league sentinel

`no_league` is a **shared constant**, not a league id. The backend emits it as the session's league when an authenticated account has no bound league source (`backend/server.py` `ACCOUNT_NO_LEAGUE_ID = "no_league"`, plus the two `"reason": "no_league"` responses); mobile consumes it as `NO_LEAGUE_ID` in `mobile/src/state/useSession.ts` and as the routing predicate in `mobile/src/navigation/RootNav.tsx`. It has been on the wire since account-only sign-in shipped and was documented nowhere until P0-5.

**Rules:**

- **Routing keys off the SENTINEL, never off a user flag.** Post-auth destination is decided by "is the pinned league the sentinel", not by `user.account_only` — a user who has since linked ESPN/MFL/Fleaflicker is no longer stranded and must not be re-routed. Keying off the flag would send them back to the picker forever.
- It is **never** passed to a platform API. A `GET /api/sleeper/leagues/acct_<id>`-style fetch on an account-only session proxies a synthetic id upstream: 503 `sleeper_unavailable` under the hermetic harness, `null` live (rendering as "No 2026 NFL leagues found"). See `GOTCHAS.md` G-032.
- A screen that receives it must render a **companion state**, not an empty list.

**Locations to change together:** `backend/server.py` (`ACCOUNT_NO_LEAGUE_ID`), `mobile/src/state/useSession.ts` (`NO_LEAGUE_ID`), `mobile/src/navigation/RootNav.tsx` (the relaunch predicate), `mobile/src/screens/LeaguePickerScreen.tsx` (the companion state).

---

## Invite URL format — a two-client contract

The invite URL is emitted by mobile (`mobile/src/utils/deepLinks.ts` `buildInviteUrl`) and parsed by **both** web (`web/js/app.js` `captureReferralFromUrl()`) and mobile (`deepLinks.ts`). Two forms are accepted:

| Form | Emitted when | Parsed |
|---|---|---|
| `/?league=<league_id>&ref=<username>` | `growth.invite_join_link` **off** (today's default) | **Forever, by both clients** |
| `/app/league/join/<league_id>?ref=<username>` | `growth.invite_join_link` **on** | Web → server 302 back into form 1; mobile → Universal Link, AASA `/app/league/join/*` |

**The legacy form is parsed forever and is not deprecated.** Links already shared live in group chats, screenshots and pinned messages indefinitely; a parser removal would silently break every one of them. `ref` is optional in both forms (mobile omits it when the username is unknown — FB #239), which is why the AASA `components` matcher must match on `league` alone.

**Ordering rule:** the reader, the mobile route, the server 302 and the AASA claim are all **unflagged and ship first**; only the emitter is flagged. Apple's AASA CDN cache (~24 h) makes the reverse order actively worse than shipping nothing. See [config-reference § `growth.invite_join_link`](config-reference.md#flags-p0-remediation-2026-08-11-mobile-ux-audit-plans).

---

## Position color tokens (segmented progress bar)

| Position | Color | Canonical hex |
|---|---|---|
| QB | orange | `#f97316` |
| RB | green | `#22c55e` |
| WR | blue | `#3b82f6` |
| TE | purple | `#a855f7` |

**Locations:** `mobile/src/theme/colors.ts` (`colors.position`), `mobile/src/components/PositionChip.tsx` (rgba tint bases), `web/profile.html` (`--qb`…`--te`), plus any progress-bar component. Tier colors must not reuse these hues (see Tier color tokens above).

**Draft capital is NOT a position, and never takes a position hex (#14 FR1, reaffirmed #293/#294 2026-08-10).** Wherever a chart or bar decomposes a roster's value, the owned-pick group renders in a **neutral ink/chalk tone** — never orange/green/blue/purple — because a position hex would assert that picks are a fifth position. Mobile uses `chalk.faint` for the live segment and `ink.ink3` for its grayed-out (drill-in defocus) state (`mobile/src/screens/LeagueSummaryScreen.tsx`: `PICKS_COLOR`, `GRAY_SEGMENT.PICKS`); web's `league-rankings.html` picks segment follows the same rule. The group's label is **"Picks"** in legends and filter pills and **"Draft capital"** as a section header. Pick value is **subset- and filter-independent**: a client that offers starters/bench or position views must include the team's full `picks.value` in every one of them, so the two subsets deliberately do **not** partition the total.

**Dashed-ice tick = other-board marker (#248, 2026-08-05):** in any chart that draws bars from one value basis, a *dashed ice hairline* (ice `#56D9EC`, dashed, with an end-cap dot) overlaid on a bar marks where the **other** basis (consensus vs. the caller's board) places that entity on the *same* scale as the bars. It is a data encoding, not a decoration — do not reuse a dashed ice line over bars for anything else, and don't render the other-board marker in any other style. (The league-average line stays a dashed *chalk-dim* hairline — a different encoding, deliberately a different color.) First consumer: `mobile/src/screens/LeagueSummaryScreen.tsx` (`consTick`).

**Same-view rule for the other-board marker (#208, 2026-08-08):** the marker and
any rank-delta indicator derived from it must be computed under **exactly the
filters the bars are drawn under** (subset, position selection, basis) — a
filtered bar may never be shown beside an unfiltered tick — and the marker must
**not render at all in a view where the two bases hold identical values**. Both
halves matter: the first keeps the comparison honest, the second keeps the chart
from asserting a comparison the current view doesn't contain (a tick drawn
exactly on its own bar top, with a "rank 3/12 · rank 3/12" caption beside it).
"Identical in this view", not "identical overall" — a caller who has re-ranked
only RBs has two genuinely different boards, and the marker must still disappear
when they filter to QB. Any rank printed for the other basis is denominated by
**that basis' own entity count**, never the bars'.

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

## Client analytics event contract (`POST /api/events`, flag `analytics.client_events`)

Tracking plan v2 ([spec](business/analytics/2026-07-17-tracking-plan-v2.md) §S2/§S3) — the envelope shape and event names are shared verbatim by every client SDK (mobile `mobile/src/api/events.ts`, web `web/js/events.js` (`window.FTFTrack`), extension `extension/background.js` `emitAnalyticsEvent`) and the backend allowlist (`backend/analytics_taxonomy.py:ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS`). Changing either side alone breaks ingestion silently (unknown types/props are dropped). All three clients emit the versioned `{v:1, events:[…]}` queue shape and gate on `analytics.client_events` (default-dark); the extension emits only the taxonomy-legal `app_opened`/`signin_succeeded` (richer extension events need a tracking-plan addendum).

**Envelope** (per event, batched ≤50):

```
{ event_id, event_type, client_ts, screen, props, session_id, seq }
```

- `event_id`: 8–64 chars `^[A-Za-z0-9_-]+$`, the idempotency/dedup key.
- `session_id`: 8–64 chars; rotated after 30 min inactivity or cold start.
- `seq`: **per-session monotonic integer from 1**, reset on session rotation — the signal that makes event loss measurable (gap analysis per `device_id`×`session_id`). Adding an event without `seq` breaks that.
- Identity: `X-Device-Id` header (body `device_id` accepted for v0 binaries). Server stamps `occurred_at`, device headers, `source`. Per-event props are filtered to that event's allowed keys, then PII-scrubbed server-side (§S4/FR-47) — clients must not send tokens/emails/etc.

**Client persistence:** the mobile SDK's offline queue lives at AsyncStorage key `ftf.events.queue.v1`, shape `{v:1, events:[…]}`. Any other shape (the pre-P1 plain array, corruption) is discarded on read, never crashed on. Web/extension SDKs (when built) must use the same envelope + a per-origin equivalent.

**Allowed client event names** (default-deny; additions require a tracking-plan addendum first, then both the allowlist and the emitting client):

- Lifecycle/nav: `app_opened`, `app_backgrounded`, `screen_viewed`, `client_error`
- Pre-auth funnel: `signin_attempted`, `signin_succeeded`, `signin_failed`, `league_selected`, `demo_entered`
- Ranking: `rank_method_selected`
- Trades: `find_trades_tapped`, `trade_card_viewed`, `trade_flagged`, `match_opened`
- Engagement: `push_opened`
- Onboarding plan ([plan](plans/onboarding-conversion/plan.md)): `apple_prompt_shown`, `apple_prompt_accepted`, `apple_prompt_declined`, `apple_prompt_dismissed`, `quickset_prompt_shown`, `quickset_prompt_accepted`, `quickset_prompt_snoozed`, `trade_card_shared`, `coach_mark_shown`, `coach_mark_dismissed`, `celebration_shown`, `deck_exhausted_viewed`
- **P0 remediation batch (2026-08-11 — [addendum](business/analytics/2026-08-11-p0-7-addendum.md)); mobile only:**
  - Navigation + League: `tab_selected`, `league_view`, `league_basis_changed`, `league_subset_changed`, `league_team_opened`, `league_home_action_tapped`
  - Send in Sleeper: `sleeper_send_attempted`, `sleeper_send_failed` — **client-fired.** The success leg `sleeper_send_succeeded` is **server**-fired on `POST /api/trades/propose` and is therefore NOT in this list (the two namespaces are disjoint by an import-time assertion in `analytics_taxonomy.py`)
  - Invite loop: `invite_shared`, `invite_link_opened`, `invite_league_pinned`, `invite_pin_failed`. `invite_shared` is **not new** — it had been fired by `InviteLeaguematesBanner.tsx` since it shipped and dropped every time; registering it is a bug fix
  - Experiments: `experiment_exposed` (exposure, not assignment)
  - Quick Set funnel: `quickset_step_advanced`, `quickset_abandoned`
  - Deck: `deck_regenerated`

**Canonical send names + the `surface` enum.** The reserved names are `sleeper_send_attempted` / `sleeper_send_failed` / `sleeper_send_succeeded` — **not** `send_in_sleeper_*`. `analytics_queries` reserved this exact trio in 2026-07-17 and `FUNNEL_STAGES` stage 8 + `FEATURE_VERTICALS["send_in_sleeper"]` already reference the succeeded name, so the reserved spelling lights those up without a query edit. Every one of them carries `surface` ∈ **`deck` | `match` | `awaiting` | `calculator`** — the four `SendInSleeperButton` mounts. Canonical definition: `SendSurface` / `SEND_SURFACES` in `mobile/src/utils/tradeText.ts`; mirrored in `CLIENT_EVENT_PROPS`. **`awaiting` is the Matches non-match send row — it is NOT `suggested`.** Adding a mount means adding a value in both places.

**`celebration_shown`, never `celebration_fired`.** The registered name has always been `celebration_shown`; the client emitted `celebration_fired` and every one of those events was dropped. Fixed 2026-08-11 by **renaming the client**, deliberately **without an alias** — an alias would make the taxonomy the place typos go to live.

**INTENT is a deny-list, so taxonomy growth is intent-by-default.** Impression-, navigation- and outcome-class names MUST also be added to `analytics_queries.NON_INTENT_EVENTS` in the same commit, or DAU/WAU step-change on ship day and every retention and churn series breaks at that seam — silently and permanently. `tab_selected`, `league_view`, `experiment_exposed` and `quickset_abandoned` are classified **non-intent** for exactly this reason (a tab tap and a League mount would otherwise make DAU ≈ app-open count). `quickset_step_advanced` stays **intent** — it is real ranking intent. Seam date recorded in the addendum.

**Web (`web/js/events.js`) and the extension (`extension/background.js`) fire NONE of the P0-batch names.** That omission is deliberate — these are mobile surfaces — and is stated here so a future reader reads it as a decision, not as drift.

> ⚠️ **Default-deny is silent.** A client `track()` name absent from `analytics_taxonomy.py` is counted and dropped behind a **200**: no client error, no server error, a plausible dashboard with no rows. A 2026-08-11 sweep found **33 of 73** emitted mobile names unregistered; this batch fixed three (`invite_shared`, `deck_regenerated`, and `celebration_fired` by rename), leaving **29**. Register the name *before* shipping the emitter. See `GOTCHAS.md` G-031.

Sign-in requests may carry `device_id` (body) or `X-Device-Id` (header) on `/api/extension/auth`, `/api/auth/apple`, `/api/auth/google`, `/api/session/demo` — the backend stitches device→identity in `identity_links`.

---

## Device platform / source enums

- `device_tokens.platform`: `ios`, `android`
- `user_events.device_type`: `iphone`, `ipad`, `macos`, `web`, `extension`
- `user_events.source`: `mobile`, `web`, `api`, `cron`

---

## League platform enum

`leagues.platform`: `sleeper` (NULL reads as `sleeper`) | `espn` (flag `espn.link`) | `mfl` (flag `mfl.link`) | `fleaflicker` (flag `fleaflicker.link`). Served on `/api/leagues`, `GET /api/{espn,mfl,fleaflicker}/leagues`, and `/api/sleeper/leagues/<user_id>` league objects; mobile types it as `LeagueSummary.platform` (`mobile/src/shared/types.ts`) and branches session-init roster sourcing on it (`api/auth.ts` → `api/espn.ts` / `api/platformLink.ts`). UI rule: imported platforms render as a small **text badge** (chalkline `Badge`, no logos — App-Store/trademark posture): `espn`→**"ESPN"**, `mfl`→**"MFL"**, `fleaflicker`→**"FLEA"** (map `PLATFORM_BADGE` in `LeaguePickerScreen`). A `mfl`/`fleaflicker`/`sleeper` value can also come back from `/api/league/parse-url` (parse-only, unpersisted) — the badge/enum rule is the same.

---

## Asset preference list types

`asset_preferences.list_type` vocabulary, defined in `backend/database.py:ASSET_PREF_LISTS` and sent verbatim by clients in the POST `/api/league/asset-prefs` body (`list` field — `mobile/src/api/league.ts:setAssetPref`):

- `untouchable` — never offer this player FROM the owner's roster in generated trades (feedback #95)
- `target` — bias suggestions toward acquiring this player
- `not_interested` — never offer this player TO the owner in generated trades (#163 — receive-side hard filter, all gen paths incl. v3 sweeteners and likes-you injections; the give side is untouched, so the owner can still trade the player away)
- `none` — POST-body-only sentinel meaning "remove the tag" (never stored)

A player holds at most one tag per (user, league). If you add a list type, update `ASSET_PREF_LISTS`, the mobile union type, and this list.

---

## Pick anchor keys

The pick-anchor wizard's answer vocabulary (2026-07-10), defined in `backend/server.py:VALID_ANCHORS` and sent verbatim by mobile (`mobile/src/api/rankings.ts:AnchorKey`; the rung grid lives in `mobile/src/utils/anchorRows.ts` — extracted from `PickAnchorScreen` by draft-extensions W1 when the Draft Room's `AnchorSheet` became a second host, so a rung can never diverge between the two surfaces):

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

**Anchor `via` (draft-extensions W1, 2026-08-06) — a SEPARATE whitelist from the tiers-save one.** `POST /api/anchor/save` accepts an optional `via` (alias `surface`) ∈ `{anchors, draft_room}` (`backend/server.py:_ANCHOR_VIA`; mobile `AnchorVia` in `mobile/src/api/rankings.ts`). It is **request-only** — it rides `anchor_answered`'s event props and the response is byte-unchanged — and an unrecognised value **falls back to `anchors`**, never 400s. It is deliberately not the `POST /api/tiers/save` `via` whitelist: that one gates the merged-band path, which the Draft Room's actions must never reach (pinned by `backend/tests/test_draft_extensions_w1.py`). Omitting `via` sends the pre-W1 body exactly.

Anchor values are position-uniform on purpose (uniform valuation across position groups); tier assignment falls out of the per-position/format band walk. The Elo seeds come from `GENERIC_PICK_SEEDS` (`backend/pick_values.py` since #158 — re-exported by `backend/server.py`, so `server.GENERIC_PICK_SEEDS` still resolves) — if those seeds or the anchor set change, update the backend constant, the mobile union type + button rows, and this table. The ≈-Elo values above assume the default `elo_value_*` config (base 1000, ref 1500, k 0.005).

**Owned-pick `pool_value` (#158) — clients MUST NOT recompute it differently.** An owned draft pick's calculator/suggestion value is server-authoritative: `pool_value = pick_pool_value(round, years_out)` = `elo_to_value(GENERIC_PICK_SEEDS[(round,"Mid")]) × 0.85^years_out` (the round's **Mid** seed, year-discounted 15%/yr in value space; deep rounds clamp to the (4,"Mid") seed). At `years_out=0` a league pick equals its generic "Mid <round>" pool twin exactly. This is the **only** value clients render for owned picks — they read `pool_value` off `GET /api/league/picks`, never derive it. Single source: `backend/pick_values.py::pick_pool_value` (shared by the calculator, the suggestion-pool injection, and #157). The legacy `draft_picks.pick_value` (0–100 round-tier scale, mid-1st 67.5) is a **different** number used only for pick-**share** ratios — not a client-facing value.

**`notice.code` is an OPEN set; `state` / `kind` / `order_confidence` are CLOSED (draft-extensions W3 M-B, 2026-08-08).** `GET /api/draft/board`'s three state enums are closed vocabularies a client may switch on exhaustively — `state` ∈ `upcoming|live|complete|unavailable`, `kind` ∈ `rookie|startup|unknown`, `order_confidence` ∈ `assigned|unset|unknown` — and **no wave may add a member**. `notice.code` is deliberately the opposite: an open set carrying a server-authored `message`, so a client that does not recognise a code renders `notice.message` verbatim. That is the whole reason W3's new ESPN state ships as `notice.code = "picks_not_assigned"` on an `unavailable` board rather than as a new `state`: an old binary renders the message and behaves correctly, and `schema` stays `1`. Any future state should ride `notice.code` the same way. Codes so far: `order_not_set`, `startup_draft`, `platform_unsupported`, `class_not_loaded`, `mfl_reconnect`, `picks_not_assigned`.

**Asserted pick ownership prices IDENTICALLY to platform ownership, and provenance is server-authoritative (W3 M-A, [ADR-010](adr/adr-010-user-asserted-pick-ownership.md)).** A `draft_picks` row with `source = 'user'` is priced by the SAME shipped functions as every other row — `pick_pool_value(round, years_out, format)` for `pool_value`, `compute_pick_value` for the legacy pick-share scale — because no user may ever enter a value (the assignment routes 400 `values_not_accepted` on any value field). Clients therefore never treat an asserted pick as a different KIND of asset; they read `pool_value`/`priced_pool_value` exactly as they do today. What they MUST surface is the `source` field: an asserted pick is member-entered and unverified with the platform. Contested and orphaned slots are withheld from every priced payload by a **row filter**, never by a nulled `pool_value` — `server._power_picks_by_owner` re-derives a price from NULL, so nulling would silently re-price the very row the rule withholds.

**The member-entered marker is ONE STRING, and it is inescapable on priced surfaces (W3 M-C, D17).** Every client renders exactly `Member-entered — not verified with ESPN` — em dash, sentence case, no abbreviation, no per-surface variant — beside the PRICE of any pick whose `source` is `'user'`, together with a one-action correction that deep-links the league's assignment grid at `{leagueId, season, focusPickId}`. Provenance that varies by surface teaches users the marker is decorative, which is why the string is registered here rather than authored per client. Gated by `picks.assign_tradeable`: with the flag off no client shows the marker and no priced surface changes. Mobile's single source is `mobile/src/components/MemberEnteredMarker.tsx` (`MEMBER_ENTERED_COPY`), which self-gates on the flag AND on `source === 'user'` so hosts render it unconditionally; the five priced surfaces are the trade-away picker, the swap-suggestions sheet, the evener chip, the calculator pick rows and the power-rankings draft-capital group, structurally pinned by `mobile/tests/check-member-entered-marker.js`. The label is a **separate field from** `_owned_pick_label` — the display string ("2027 1st") is shared with Sleeper/MFL leagues and must never be rewritten to carry provenance.

**Generic pick-rung labels are a SERVED STRING — clients MUST NOT parse them (#207).** The 12 rungs keep their stable, league-agnostic ids (`generic_pick_{round}_{early|mid|late}`) forever, but their **display label is resolved per league at serialization time**: `GET /api/rankings` and `GET /api/trio` serve `"2026 Early 1st"` when the session league's rookie draft hasn't happened and `"2027 Early 1st"` once it has (flag `picks.rank_year_labels`; off ⇒ the year-less `"Early 1st Round Pick"` form). Two teams' boards can therefore show different year text for the SAME rung id — which is correct: a shared board values "an early 1st", and which year that maps to depends on the league you are looking through. Consequences for clients: **key off `id`, never the name**; render `name` verbatim; do not regex a year, a round or `"Round Pick"` out of it; and do not cache a label across leagues. (`mobile/src/components/TradeValueBar.tsx`'s `/\s*Round Pick$/` strip is fine — it operates on `/api/trade/evaluate`'s `gap.pick_equivalent.label`, which is league-agnostic and deliberately NOT relabelled.) The matching `pick_value` is `years_out`-discounted the same way `pool_value` is, so a relabelled 2027 rung prices like the owned 2027 pick of that round; `elo`, `rank` and pool membership never change.

**#185 corollary (backend invariant):** the v2/v3 suggestion engine prices assets through **Elo maps** (consensus `seed_elo` + each member's board), not through `dynasty_value` — an id absent from a map silently defaults to Elo 1500 (~value 1000). Any code that puts a pick pseudo-asset in front of the engine MUST also prime those maps with the pick's bridged Elo (`server._pick_asset_elos`: `1200 + 6·pick_value` = `value_to_elo(pool_value)`; wired in `server._inject_owned_picks`). Skipping the priming reproduces feedback #185: every pick prices identically and reads "fair" against any mid-value player.

**Per-user pick-value scale does NOT change this enum** (1.5.4 #111, re-derived 2026-07-12 for the #117 8-tier ladder): `/api/anchor/scale` lets a user declare "a top-tier asset = N firsts" (N ∈ 2/3/4, default **4** = the table above, persisted in `users.anchor_scale`; the #117 seed recalibration puts the consensus top asset at the 4-firsts rung, so N = 4 is now the neutral scale — `ANCHOR_TOP_TIER_FIRSTS_DEFAULT`). A non-default N re-spaces only the three multi-first rows' target Elos for THAT user's saves (`m firsts → value(Mid 1st) × m^(log 4 / log N)`; the user's own N-firsts answer pins to the default top-tier Elo ≈ 1927). The keys, button labels, single-pick rows, `no_value`, the generic pick assets in the pool, the calculator's `gap` firsts unit (`/api/trade/evaluate` is public/sessionless), and the tier-ladder band floors all stay consensus-denominated per this table. A scaled user's own top-tier answer (m = N) pins to Elo ≈ 1927 → `firsts_4plus`; their intermediate multi-first answers re-space upward (N < 4 users believe firsts are expensive) and may land above the tier carrying their name — by design (on that user's scale those packages ARE worth more). Existing `users.anchor_scale` rows keep their semantics — the statement "top asset = N firsts" is interpreted by the same formula, only the neutral point moved from 2 to 4.

**Tier labels ARE pick terms** (2026-07-11, supersedes the 1.5.4 #103 display-sublabel approach): the tier ladder itself is denominated in this table's vocabulary — every anchor answer lands in the tier that carries its name at the default scale (`4_firsts` → `firsts_4plus`, `3_firsts` → `firsts_3`, `2_firsts` → `firsts_2`, `1_first` → `first_1`, …, `no_value` → unranked). `mobile/src/utils/pickTerms.ts` (the #103 sublabel helper) was removed. If `GENERIC_PICK_SEEDS` or the anchor multiples change, recalibrate `backend/tier_config.json` (and its mirrors) **and** the consensus seed map (`data_loader.seed_elo_for_value`, whose ceiling anchor is 4 × Mid 1st) alongside the locations above so the name↔rung invariant holds (`test_tier_occupancy.py::test_anchor_rungs_land_in_matching_tiers`).

---

## Asserted-pick provenance: the `source` enum and its ONE label (W3 M-C)

Registered here **before** any client renders it, because three clients must not paraphrase it differently. Flag `picks.assign_tradeable` ([ADR-010](adr/adr-010-user-asserted-pick-ownership.md), plan §6.4 + operator decision 4).

**The enum — CLOSED, exactly two members, never null:**

| `source` | Meaning |
|---|---|
| `"platform"` | the pick's ownership came from the platform (Sleeper / MFL sync). **A NULL `draft_picks.source` column serializes as `"platform"`** — every pre-W3 row is NULL, so clients never see one. |
| `"user"` | ownership was **asserted by a league member** through the pick-assignment grid. Never verified against a platform, because ESPN has no draft object to verify against — now or ever. |

**The label — EXACT COPY, on every priced surface, no abbreviation and no rewording:**

> **Member-entered — not verified with ESPN**

Every place it appears carries a **one-action correction** that deep-links to the assignment screen with `{leagueId, season, focusPickId}` — which is why payloads that did not already carry them ship `season` (and `pick_id`, on power-rankings items) alongside `source`.

**Where it rides** (flag on; **absent entirely** with the flag off, which is what keeps every payload byte-identical):

| Payload | Entry |
|---|---|
| `GET /api/league/picks` | every row in `my_picks` / `all_picks` |
| `POST /api/trade/evaluate` | every `per_player` entry whose id is a league pick (+ `season`). A player entry carries none — it is not a pick |
| `POST /api/trade/evaluate` → `eveners[]` | every pick item (+ `season`); a 2-piece combo containing a member-entered pick carries `source: "user"` so the badge cannot vanish inside a bundle |
| `GET /api/league/power-rankings` | every `picks.items[]` entry (+ `pick_id`, `season`) |

**Rules for clients:**

1. **Do not infer provenance from anything else** — not the league's platform, not the `pick_id` shape, not the absence of a `synced_at`. Read `source`.
2. **Do not treat an asserted pick as a different KIND of asset.** It is priced by the identical shipped functions (`pick_pool_value` / `priced_pool_value`) because no user can ever enter a value. Only the label differs.
3. **A contested or orphaned slot never appears on a priced payload at all** — it is withheld by a row filter server-side. Clients must not reconstruct it; the one place it is visible is `GET /api/league/pick-assignments`, the screen where it gets fixed.
4. **`picks_supported` is a data test, not a platform test** (`platform != "espn" or the league has assigned rows`), so an ESPN league can now report `true`. Do not re-derive it from the platform string.

## Draft-pick slot values are DISPLAY ONLY — they are not the ladder

**`order[].slot_value` on `GET /api/draft/board` is a second, independent pricing of draft picks, and nothing values an asset with it** (rookie-draft M6, flag `picks.slot_values`, default off).

It comes from DynastyProcess's *combined* `files/values.csv` — the `pos == "PICK"` rows, which price individual slots (`"2026 Pick 1.01"` … `"2026 Pick 5.12"`) plus the future-year rungs — mapped into seed-Elo space through the same `data_loader.seed_elo_for_value` the player seeds use, so the number is directly comparable to a player's Elo *on screen*. That is the whole of its contract.

**What it is NOT.** It is not `GENERIC_PICK_SEEDS`, not `pick_pool_value`, and not a tier-band floor. **Amended by M6b (2026-08-06):** it CAN now reach the trade engine, the suggestion pool and `/api/trade/evaluate` — but only through the one named seam `pick_values.priced_pool_value`, only for OWNED picks, only under the per-user mode `pick_pricing_mode == 'market_slots'`, and only while the flag `trade.slot_pricing` is on (it is off). It still never reaches an anchor, the ranking pool or a tier band. The two scales genuinely disagree: DP's current-year slot curve is far steeper than our shipped ladder — **1.01 ≈ Elo 1817 against "Early 1st" 1720, and 1.12 ≈ 1461 against "Late 1st" 1580** (1QB, 2026-08-06 snapshot). A client that renders a slot value next to a ladder value must label which is which.

**The two prices of a pick, and which is which (M6b).** After M6b there are TWO engine-visible prices for an owned pick, selected per user:

| mode | source | who sees it |
|---|---|---|
| `tier_ladder` (**default**) | `pick_values.pick_pool_value` — the shipped ladder's **Mid** rung of the round, `YEAR_DISCOUNT ** years_out` | everyone today |
| `market_slots` | `pick_values.market_pick_pool_value` — DP's published curve for the pick's **absolute** season+round | opt-in, flag-gated, currently nobody |

**The 12 generic pick rungs are byte-identical in BOTH modes, always.** They are rankable pool assets whose seed Elo anchors the tier bands in the table above, those bands are absolute Elo mirrored across five clients, and the pricing mode is per-user — so repricing a rung would repaint another user's tier colours. `GENERIC_PICK_SEEDS` is not a function of `pick_pricing_mode` and must never become one.

**The unknown-slot basis.** An owned `draft_picks` row carries `(season, round)` and no slot. Under `market_slots` a round maps to the **value-space mean of that round's middle tercile** (slots 5–8 of a 12-team round) — DP's own definition of a "Mid" rung, and the market analogue of the ladder's Mid rung. It lives in ONE place, `pick_values.UNKNOWN_SLOT_BASIS` / `_basis_slots`. Seasons past DP's ~3-year horizon extrapolate from the deepest published season with the shipped `YEAR_DISCOUNT`.

**The measured direction is DEFLATION, not inflation.** The plan's premise (a steeper DP curve inflates pick values) is wrong for owned picks: in 1QB every representative owned pick gets CHEAPER under `market_slots` — 1sts by 12–17 %, **2nds by ~40–47 %** — because the 1.01 premium only attaches to the literal 1.01 slot, which an unknown-slot pick never receives. Superflex is far closer to parity at round 1 and still ~35–42 % down at round 2. Read any future calibration for 2nd/3rd-round package deflation first (numbers: `docs/plans/rookie-draft/build-m6b.md`).

**Approximation marker.** DP publishes ONE slot curve and it is a **12-team** curve. A 12-team league is priced exactly and the payload carries **no** `slot_value_approx` key; any other league size is mapped onto the 12-team curve by within-round percentile with both ends anchored (slot 1 → `x.01`, slot T → `x.12`) and the payload carries `slot_value_approx: true`. Clients must label an approximated axis.

**Omit-when-absent.** With the flag off, the read failed, the order unresolved (`slot: null`), or the round/season unpublished by DP, the `slot_value` key is **absent entirely** — never `null`, never `0`. A null would render as "this pick is worthless".

**Locations:** `backend/data_loader.py` (`PICK_VALUES_URL`, `load_pick_slot_values`, `pick_slot_label`) · `backend/draft_board_service.py` (`_annotate_slot_values`, `_basis_slot`, `SLOT_VALUE_BASIS_TEAMS`) · flag `picks.slot_values` in `backend/feature_flags.py` · test seam `FTF_DP_PICK_VALUES_FILE` ([config-reference](config-reference.md)). M6b: `backend/pick_values.py` (`market_pick_pool_value`, `priced_pool_value`, `UNKNOWN_SLOT_BASIS`, `PICK_PRICING_MODES`) · `backend/trade_service.py` (`pick_pricing_override`, `pick_pricing_mode_for_user`) · `backend/server.py` (`_owned_pick_assets`, `_inject_owned_picks`, `/api/trade/evaluate`, `/api/settings/pick-pricing`) · `users.pick_pricing_mode` · flag `trade.slot_pricing`.

Tests: `backend/tests/test_slot_values.py` (T-M6-01/02/03, including a per-module assertion that `trade_service`, `trade_optimizer` and `ranking_service` never read the map, and that `pick_values` reads it ONLY from `market_pick_pool_value`) and `backend/tests/test_pick_pricing_m6b.py` (T-M6B-01 flag-off byte-identity, T-M6B-02 the flag is the only gate, T-M6B-03 read-time-only, T-M6B-04 the ladder is unchanged in both modes).

---

## Rookie predicate

**There is exactly ONE test for "is this player in season N's rookie class".** Anything that scopes, filters, counts or labels rookies — server, client, script or report — resolves to it:

> `rookie_year == str(season)` when Sleeper carried a plausible 4-digit class year; **otherwise** the proxy `years_exp == 0 AND team IS NOT NULL AND team != ''`.

`metadata.rookie_year` is the exact "class of YYYY" field. `years_exp` counts *accrued* seasons, so it is **not** a class field (a 2023 UDFA who spent two years on practice squads reads `years_exp == 1`); it is only the fallback for rows whose class year Sleeper never carried. The `team` requirement on the proxy is what drops the teamless pre-NFL-draft prospect tail that would otherwise read as rookies every January.

**Two consequences worth stating out loud:**

- **The proxy branch is season-independent.** A row with no class year matches *every* season by construction. Anything that must answer "has next season's class loaded yet?" needs the EXACT test only — that is `database.count_rookie_class_rows(season)` (the M0 class-load monitor), never this predicate.
- **`database.load_rookies()` / `GET /api/rookies` were a THIRD, looser rule** (`years_exp == 0 OR years_exp IS NULL`, no `team` requirement, no `rookie_year` test) that swept in the whole teamless prospect tail plus every unclassifiable camp body — 157 phantom "rookies" against the April-2026 dev cache, 2 of them with a team. They were rebased onto this predicate in rookie-draft M0 and are retired entirely in M4.

**Locations:** `backend/draft_status.py:is_rookie_row` (the decision, pure) · `backend/database.py:load_rookie_player_ids` (the indexed SQL mirror — THE callable) · `backend/server.py:_rookie_player_ids` (memoised per `(season, pool_generation())`) · `backend/database.py:load_rookies` (rebased; retired in M4) · `backend/database.py:count_rookie_class_rows` (exact-only, class-load monitor). Tests: `backend/tests/test_players_refresh.py::test_load_rookie_player_ids_mirrors_is_rookie_row` pins the two implementations against the full `rookie_year` × `years_exp` × `team` matrix.

**Freshness is part of the predicate.** It reads `players` rows written by `sync_players` from the Sleeper bulk cache, and a class only exists in that dump from ~late April. A stale cache therefore does not return "no rookies" — it returns *last* year's answer, or a teamless prospect list. `POST /api/cron/players-refresh` (M0) is what keeps it true; outside prod, `server._rookie_scope_allowed()` refuses rookie-scoped reads off a cache older than 7 days.

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
