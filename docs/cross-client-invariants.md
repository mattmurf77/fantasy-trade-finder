# Cross-Client Invariants

Things that **must** stay in sync across backend, web, mobile, and the extension. Drift here = clients disagree silently. Update *all* listed locations together.

---

## Tier keys, labels & color tokens

**The tier taxonomy is the 8-tier pick-value ladder (2026-07-12, feedback #117/#118; supersedes the 2026-07-11 six):** tier keys/labels read directly in draft-pick terms — a tier says what a player in it is worth in the Pick Anchor wizard's vocabulary. The 2026-07-11 keys `firsts_2plus` and `bench` are retired (`firsts_2` and `waivers` replace them; `apply_tiers` no-ops unknown keys so stale clients sending old keys degrade safely, and `users.tier_overrides` stores raw Elo so saved boards re-bucket automatically). Keys are cross-client enums (sent verbatim in `/api/tiers/save`, served by `/api/tier-config`, `/api/extension/rankings`, `/api/anchor/save`, profile tier snapshots, `GET /api/league/power-rankings` `roster[].tier`, and — since #323 — the mock-draft payload's `picks[].tier`/`my_picks[].tier`: server-computed via `RankingService.tier_for_elo` over the consensus Elo always, `null` ⇒ the client shows NO tier — clients map the key through `TIER_LABEL`/`TierBadge` and never derive a tier themselves).

Color rule unchanged (re-canonicalized 2026-07-10 to de-collide from position colors): **tier hues must not share a hue with any position color.** Tiers are the *bright* family (Tailwind 400-level), positions the *deeper* family (500-level). Lighter same-hue accents (300/200-level borders and text on tinted dark backgrounds, as in the extension badge and web tier legend) are allowed per client, but the base identity color and rgba() tint bases must be these values. (The two hues added for the #117 top tiers: red-400 is a distinct hue family from the semantic `--neg` red-500 by the same bright-vs-deep rule that separates tier gold `#fbbf24` from `--warn` amber-500; fuchsia-400 is magenta, distinct from TE purple-500 and from tier pink `#f472b6`.)

| Tier key | Label | Color | Canonical hex | rgba tint base | Elo band [min, max] |
|---|---|---|---|---|---|
| `firsts_4plus` | 4+ 1sts | red | `#f87171` | `248,113,113` | [1927, 1972] |
| `firsts_3` | 3 1sts | fuchsia | `#e879f9` | `232,121,249` | [1869, 1922] |
| `firsts_2` | 2 1sts | gold | `#fbbf24` | `251,191,36` | [1788, 1864] |
| `first_1` | 1 1st | teal | `#2dd4bf` | `45,212,191` | [1580, 1785] |
| `second` | 2nd | sky | `#38bdf8` | `56,189,248` | [1370, 1575] |
| `third` | 3rd | pink | `#f472b6` | `244,114,182` | [1280, 1365] |
| `fourth` | 4th | lime | `#a3e635` | `163,230,53` | [1220, 1275] |
| `waivers` | FA | gray | `#7a7f96` | `122,127,150` | [1150, 1215] |

The `waivers` display label was renamed **"Waivers" → "FA"** on 2026-07-17 (label-only; the key, hex, and band are unchanged).

**Locations (colors + labels):** `mobile/src/theme/colors.ts` (`colors.tier`), `mobile/src/components/TierBadge.tsx` + `chalkline/Badge.tsx` (`TierChalkBadge`) label maps, `mobile/src/utils/tierBands.ts` (`TIERS`/`TIER_LABEL`), `web/positional-tiers.html` (inline CSS: tier-row accents, tier-assign buttons, legend swatches; JS `TIERS`/`TIER_LABELS_SHORT`), `web/profile.html` (inline `:root` vars + `TIER_ORDER`/`TIER_LABELS`), `web/style-guide.html` (badge swatches), `extension/content.css` (`.ftf-badge.ftf-tier-*`) + `extension/content.js` (`TIER_LABELS`), `backend/og_image.py` (`TIER_ORDER`/`TIER_LABELS`/`TIER_TINTS`).

Note: `web/css/styles.css` has a separate 4-level *dynasty value* badge set (`.tier-elite/.tier-high/.tier-mid/.tier-depth`) — a different taxonomy, not these tokens. Likewise `trade_service.analyze_roster_strengths`' `tier_depth` profile bins (`elite/starter/bench`, KTC-value thresholds) and the `tier_mult_*` `model_config` keys are backend-internal engine taxonomies that merely reuse the old words — they are NOT the tier enum and were deliberately left untouched by the 2026-07-11/12 ladder migrations. `extension/popup.css` contains no tier colors. Rank-medal accents (web `.ranked-1/2/3`, mobile `PlayerCard` rank styles) use the gold/silver/neutral medal tokens, not tier tokens.

---

## Tier band Elo cutoffs

The Elo ranges that map a player into a tier. Single source of truth is `backend/tier_config.json`, served to clients via `GET /api/tier-config`; bucketing is a top-down walk assigning the first tier whose `min <= elo`.

**Banding rule (8-tier pick-value ladder, 2026-07-12):** each tier's floor is a rung of the anchor/pick Elo ladder (`GENERIC_PICK_SEEDS` + the multi-first anchor Elos — see "Pick anchor keys" below): `firsts_4plus` ≥ 1927 (just under `value_to_elo(4 × Mid 1st)` = 1927.3; its max 1972 sits just under the 5-firsts rung), `firsts_3` ≥ 1869 (just under `value_to_elo(3 × Mid 1st)` = 1869.7), `firsts_2` ≥ 1788 (just under `value_to_elo(2 × Mid 1st)` = 1788.6), `first_1` ≥ 1580 (Late 1st seed — "worth a pick in round 1"), `second` ≥ 1370 (Late 2nd), `third` ≥ 1280 (Late 3rd, max 1365), `fourth` ≥ 1220 (Late 4th), `waivers` = below 4th-round value down to 1150 (below 1150 = unranked; keeps the `no_value` anchor at Elo 1100 below every band). Because pick value is position-uniform by design, the bands are **identical across positions AND scoring formats** — the JSON keeps its per-(format, position) shape so consumers don't change, but every cell holds the same eight bands. Occupancy differs per position/format because the seed Elos differ (`data_loader.seed_elo_for_value` — the #117 recalibration: DP values map affinely onto the trade-value scale, DP 0 → Elo 1200 and DP 10000 → the 4-firsts rung ≈ 1927.3, so the OVERALL top consensus assets read ≈ 3–4 firsts and reach the top two tiers, while e.g. 1QB QBs still rarely clear a 1st — that asymmetry is the point; empty-by-default top tiers for weak positions are expected, user anchors/rankings can populate them). Occupancy + the "every anchor rung lands in the tier that carries its name" invariant are pinned by `backend/tests/test_tier_occupancy.py` against a checked-in consensus snapshot. A related invariant: `apply_reorder` (manual ranks) is a pure permutation of existing Elo values, so reorders never change tier occupancy.

**Round-2 amendment (D-084, 2026-08-19).** The `second` floor moved **1400 → 1370** and `third`'s max **1395 → 1365**, because the round-2 rungs of `GENERIC_PICK_SEEDS` were deflated **1520/1460/1400 → 1470/1400/1370**. Rationale in [docs/reviews/2026-08-19-ktc-pick-value-comparison.md](reviews/2026-08-19-ktc-pick-value-comparison.md): measured on the only scale-free basis (what player rank a pick is worth), our Mid 1st priced exactly at market (rank 65 vs a market median of 66.5) while our Mid 2nd sat at rank 119 against a median of 140.5 — 22 ranks too generous, with KeepTradeCut, FantasyCalc and DynastyProcess all agreeing once their incomparable value scales are neutralised. **The two edits are inseparable**: the Late rung of a round *is* that round's tier floor, so a seed move without the band move (or vice versa) breaks the ladder's meaning. Rounds 1, 3 and 4 were **not** touched — round 1 prices correctly, and the 3rd/4th divergence is `seed_elo_for_value` floor compression rather than a seed error (Q-019). Effect on boards: 2–5 players per (format, position) move up from `third` into `second`; `second` peaks at 32 against its ceiling of 35, pinned by `test_tier_occupancy.py`. Ordering still holds — the new Late 2nd (1370) sits above the Early 3rd seed (1360), margin narrowed from 40 Elo to 10. **These seeds are intentionally NOT config-driven**; the revert is a revert of the D-084 commit plus a redeploy (see the module note in `backend/pick_values.py`).

Saved boards need no data migration when bands change: `users.tier_overrides` stores raw Elo per player, so overrides re-bucket through the new walk on read.

**Two value↔Elo maps exist, and picking the wrong inverse is a recurring defect class (D-088, 2026-08-19).** Nothing may be band-walked until it is on the tier-band Elo scale, and there are **two** different maps onto that scale. Feeding a number to the wrong one is the #263 bug class, and it has now shipped twice.

| The number you hold | Scale | Invert it with | Never with |
|---|---|---|---|
| `draft_picks.pool_value`, `pick_pool_value(...)`, any `/api/trade/evaluate` `value`, `total_value`, evener `value` | **engine value** (`elo_to_value` units — `1000·e^{0.005(elo−1500)}`, floor ≈ 223) | `trade_service.value_to_elo` | `seed_elo_for_value` |
| DynastyProcess `value_1qb` / `value_2qb`, `files/values.csv` `pos == "PICK"` rows, anything read off a DP CSV | **DP consensus** (raw 0–10000) | `data_loader.seed_elo_for_value` | `value_to_elo` |

The two maps agree at **exactly one point, Elo 1548.0**, and diverge in both directions — so a mistake is silent near a mid-1st and grows the cheaper the asset. Using `seed_elo_for_value` on an engine value inflates: a Mid 3rd (Elo 1320) reads 1383.5, a Mid 4th (1240) reads 1339.3, a Late 4th (1220) reads 1329.5. That is what made a current-year 3rd badge `second` on `GET /api/league/picks` after D-084 moved the `second` floor to 1370. Full derivation: [docs/reviews/2026-08-19-pick-badge-scale.md](reviews/2026-08-19-pick-badge-scale.md).

**The invariant to test against, in either direction:** a CURRENT-year pick of round R must badge exactly where `GENERIC_PICK_SEEDS[(R, "Mid")]` sits, because `tier_config.json`'s `_calibration` *defines* the band floors as those rungs. Pinned by `backend/tests/test_league_picks_tier.py::test_current_year_rungs_badge_their_own_round`.

**Clients never re-derive a tier from a value.** Every tier on the wire is server-computed through `RankingService.tier_for_elo`; the mirrors below exist only as pre-fetch fallbacks for the *bands*, never as a place to redo this conversion.

Since #313, `1qb_ppr` QB **seed values** are compressed so no quarterback seeds above the `first_1` band (`qb_1qb_cap_elo`, default 1785). The **bands themselves are unchanged and remain position- and format-uniform** — the cap is applied in value space at pool build, so every client's tier walk (`mobile/src/utils/tierBands.ts`, the extension badge, `RankingService.tier_for_elo`) stays a single shared ladder with no per-position fork.

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

**Trade like / pass are not the final K.** Since fit-congruence weighting they are scaled at the swipe site by `fit_k_explained_mult` (0.4) or `fit_k_defying_mult` (1.0) depending on whether the swipe agrees with the user's window — so a deck pass can land at 1.6 rather than 4. The *displayed* defaults above are still the baselines; any client that shows a "signal strength" must not claim the pass K is flat. The multiplier is applied identically to the in-memory update and the persisted `swipe_decisions.k_factor` (the replay source). See [config-reference.md § Fit-congruence signal weighting](config-reference.md#fit-congruence-signal-weighting-no-flag-trade_service_default_cfg-db-seeded).

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

`notifications.type` (the in-app bell inbox) — **nine values, and the failure mode is silent:**

| Value | Written by | Mobile glyph | Tap target |
|---|---|---|---|
| `trade_match` | match creation | `match` / ice | Matches |
| `trade_accepted` | match disposition | `check` / pos | Matches |
| `trade_declined` | match disposition | `x` / neg | Matches |
| `referral_joined` | session_init, first session with `invited_by` | `plus` / **flare** | League |
| `league_member_joined` | session_init peer fanout, **coalesced 1/league/day** | `plus` / ice | League |
| `league_member_unlocked_trades` | first board unlock | `rank` / ice | League |
| `match_expiring` | 15-min cron | `match` / warn | Matches |
| `deck_replenished` | weekly replenish job | `trade` / ice | Trades |
| `counter_offer` | **no emitter today** — mapped so it renders correctly if the kind ever ships | `swap` / ice | Matches |
| `espn_reconnect` | weekly roster sweep hitting an expired/missing stored ESPN cookie (ADR-011/YR-8) — once per credential-expiry episode, keyed on `verified_at` | `reload` / warn | League |

**Four independent consumers, no shared source.** Adding a value without updating all four produces no error, no warning and no log line — just an anonymous grey bell with a dead tap that nobody notices until someone reads the code:

| Client | Glyph | Tap |
|---|---|---|
| mobile | `ROW_GLYPHS` (`mobile/src/components/TopBar.tsx`) | `V2_*_KINDS` (`mobile/src/utils/deepLinks.ts`) |
| web | `notifTypeIcon` (`web/js/app.js`) | `clickNotif` (`web/js/app.js`) |

Pinned by `mobile/tests/check-notif-glyphs.js`, which reads all four from the real files. **Run it after touching any of them.**

⚠ **Inbox types are not push kinds.** The DB writes `trade_accepted` / `trade_declined`; the paired *pushes* are `match_accepted` / (none). Listing only the push kind in a client table is how two of the four original types shipped with a glyph and a dead tap (fixed 2026-08-13). `mobile/src/hooks/usePushNotifications.ts` handles push kinds; the inbox renderers handle these.

**An inbox row is not a push.** `_send_typed_push` has never written one. Rows are written beside a push at the call site, deliberately outside the dispatcher's prefs → bucket → cap → quiet-hours gates, all of which are statements about *interrupting* the user rather than about what belongs in a list they chose to open. `deck_replenished` is the proof: its push reaches zero users (reengagement bucket + `notif.reengagement_default_off`), and its row reaches everyone.

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
| `Fair-value idea` | card has `basis: "consensus"` (consensus label/tag) — names the PRICING BASIS, unconditional |
| the consensus-card explainer, **two states** — see § Consensus balance claim below | card has `basis: "consensus"` (mobile body text; web `title` tooltip on the tag) |
| `+ {player name} added to balance the deal` | card has a `sweetener` (Tier 3) — name interpolated from the referenced player |

**Locations:** `mobile/src/components/TradeCard.tsx`, `web/js/app.js` (search "likes-you-pill" / "consensus-tag" / "trade-sweetener").

## Consensus balance claim — the 0.75 bar (D-097, 2026-08-19)

**The app may not call a trade balanced below its own definition of balanced.** Until 2026-08-19 the consensus explainer asserted `…this is a balanced trade by consensus value.` gated on `basis === 'consensus'` **alone**, with no fairness check. The app's bar for balanced is **0.75**, but the mobile fairness default flipped OFF on 2026-08-17 so the live generation floor is **0.50** and cards ship down to 0.501. Measured read-only against prod `deck_impressions` on 2026-08-19: **805 of 7,293 served consensus cards (11.0%)** carried that sentence while below the bar (band `[0.501, 0.75)`; p10 0.7302, p50 0.8590, min 0.5010, and 7,293/7,293 carried a non-NULL `fairness_score`).

**The claim is REMOVED, not replaced.** Below the bar the sub-line truncates to its true half and stops. Two character-identical strings on both clients, keyed on `fairness_score`:

| `fairness_score` | String |
|---|---|
| `>= 0.75` | `This league-mate hasn't ranked players yet — this is a balanced trade by consensus value.` |
| `< 0.75`, or absent / non-finite | `This league-mate hasn't ranked players yet.` |

Three rules that are not negotiable:

- **No replacement prose below the bar** (operator, 2026-08-19). The card already renders `TradeValueBar` with `give_value` / `receive_value` / `favors` / `gap` — direction *and* magnitude are on screen from the component whose own comment calls it the universal value verdict. A sentence about value here would restate the bar. This also settles the directional-wording question ("leans your way" / "leans theirs"): it is duplication, and on web it would additionally require plumbing `give_value` / `receive_value` into `web/js/app.js`, which has neither today. **Do not re-open it.**
- **The explanation half is never dropped.** `This league-mate hasn't ranked players yet` is the one thing on the card that says *why this is a fair-value idea rather than a divergence card*. Nothing else conveys it, so the fix truncates — it does not hide the line.
- **Fail-safe direction is DOWN.** Unknown fairness renders the truncated string, never the balanced claim. Both clients compute `balanced` as a single conjunct (`typeof === 'number' && Number.isFinite(…) && … >= 0.75`), so this is structural rather than merely tested. `Number.isFinite`, **not** the coercing global `isFinite` — `isFinite('0.9')` is `true` and a stringified payload would then compare as a string.

**The 0.75 threshold is a constant, not a server knob** — matching the two constants it mirrors. It is the *definition* of balanced, deliberately **not** the generation floor (which is 0.50 today and moves with the fairness toggle). Four spellings of the same number, all pinned to each other by `mobile/tests/check-consensus-balance-claim.js` §2:

| Spelling | Location |
|---|---|
| `NORMAL_LOW` | `mobile/src/utils/tradePresentation.ts` (canonical for mobile) |
| `FAIRNESS_ON_THRESHOLD` | `mobile/src/api/tradePregen.ts` (the `fairness_threshold` sent to the generator in balanced mode) |
| `CONSENSUS_BALANCED_MIN` | `mobile/src/utils/consensusNote.ts` — **re-exports** `NORMAL_LOW`, never redeclares it |
| `FAIRNESS_BALANCED_MIN` | `web/js/app.js` — the one unavoidable literal (vanilla JS, no import from TS) |

**Locations to update together:** `mobile/src/utils/consensusNote.ts` (the only place the copy is authored), `mobile/src/components/TradeCard.tsx` (renders `note.label` / `note.body`), `web/js/app.js` (`consensus-tag` tooltip + `FAIRNESS_BALANCED_MIN`), and this table. Guard: `npm run test:consensus-balance-claim` in `mobile/` — §3 **reconstructs both web strings from web source and compares them byte for byte** against the mobile module's output, so it catches wording drift, not just a missing gate.

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

## Sleeper roster ownership — the co-owner predicate

Sleeper rosters carry an optional `co_owners` array beside `owner_id`. **One
predicate, three implementations, and they must not drift:**

```
a roster belongs to a user  iff  user_id == owner_id  OR  user_id ∈ co_owners
```

**Locations to change together:** `backend/sleeper_roster.py` (`owns_roster` —
the reference), `mobile/src/api/sleeper.ts` (`ownsRoster`), `web/js/app.js`
(`ownsRoster`). The extension does no roster resolution.

**Rules:**

- **A co-owner is an alias, not a team.** The roster's primary `owner_id` is the
  canonical **league identity** — the key `league_members` rows carry and the id
  every "is this my team?" comparison uses. See
  [glossary § League identity](glossary.md) and [ADR-012](adr/adr-012-co-owned-roster-identity.md).
- **Exclude your own roster by `roster_id`, never by comparing owner ids.**
  `owner_id !== user_id` is true for a roster you *co-own*, which is how a
  co-manager's own team ended up in `opponent_rosters` as a trade partner.
- **An empty/None user id never matches.** An ownerless roster (`owner_id: null`
  after a manager leaves) must not resolve to a caller with no id.
- **Co-owner ids are compared as strings**, like `owner_id` everywhere else.
- **Sleeper only.** ESPN / MFL / Fleaflicker have no co-owner concept; their
  session-init builders omit `league_user_id` entirely and the backend defaults
  it to the caller.

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

## Pick identity on the wire — `is_pick` is authoritative, the magic string is legacy compat

**A client must never decide what is a draft pick by looking at `position` or `team`.** It reads the server's explicit flag. This section is the single statement of that rule and the register of every place it is mirrored.

**Why the inference was ever needed.** `build_universal_pool` (`backend/server.py`) stamps the 12 generic pick rungs with a **FAKE player position** — `_PICK_POS = {1:"RB", 2:"WR", 3:"TE", 4:"QB"}` — deliberately, so draft capital distributes across the trio/rank position tabs and gets ranked against players. That fake position is **load-bearing and is not changing**: it feeds tab distribution across five clients and the tier-occupancy tests. It also means a rung is *not* `position == "PICK"`; historically it was identifiable only by `team == "PICK"`.

**The canonical predicate** is `trade_service.is_pick_asset` (`backend/trade_service.py`): `position == "PICK" OR team == "PICK"`. Both arms are required — owned-pick pseudo-players (`server._owned_pick_assets`) carry `position == "PICK"`, the generic rungs carry only `team == "PICK"`. Every backend site that needs pick-ness calls this function; nothing re-implements it.

**The wire contract (B3 follow-up, 2026-08-18).** `GET /api/trade/values` serializes `is_pick` (bool, always present) directly from that predicate. It is **additive**: `_PICK_POS`, `position` and `team` are unchanged, so a client that has not migrated sees a byte-identical row apart from the new key.

| Rule | |
|---|---|
| **Authoritative** | the server-supplied boolean (`is_pick` on the wire) |
| **Legacy compat — keep, do not delete** | `position === 'PICK' \|\| team === 'PICK'` — the fallback for servers older than 2026-08-18, for responses served from the endpoint's `stale-while-revalidate` cache from before the deploy, and for pick shapes that never come from this endpoint at all (owned league picks built client-side from `/api/league/picks`; the demo calculator's mock picks) |
| **Only an EXPLICIT boolean wins** | a mapper wired against an older server hands over `undefined`; reading that as `false` re-creates the bug. Guard with `typeof … === 'boolean'`, never bare truthiness |
| **Never** | re-derive pick-ness from a name, a label, a round number, or `position` alone |

**Two shipped bugs are why this is registered here** rather than left to each client: feedback **#222** (picks leaking into the free-agent list) and the **2026-08-18 B3 sweep** (the calculator's PICK filter matched nothing — the rungs are typed RB/WR/TE/QB — while the RB/WR/TE/QB chips wrongly listed picks). Both were a client re-deriving identity the backend already knew.

**Mirror locations — every client re-derivation of pick identity.** This list did not exist before 2026-08-18, which is why the drift went uncaught. Add a row when you add a re-derivation; the goal is for every row to become "reads the server field".

| Location | Predicate | Status |
|---|---|---|
| `backend/trade_service.py` `is_pick_asset` | `position == "PICK" or team == "PICK"` | **canonical — the single source** |
| `backend/server.py` `trade_calc_values_route` | serializes `is_pick` from the canonical predicate | serves the flag |
| `backend/trade_service.py` `_pos_for_avoid` (#360) | resolves pick-ness via the canonical `is_pick_asset` **before** reading `position`, returning `"PICK"` | **reads the canonical predicate** — registered anyway, because this register exists precisely because unregistered re-derivations drifted before (#222, the 2026-08-18 B3 sweep). Note the deliberate asymmetry it creates: `_positions_ok` (the Chasing/Shopping gate, duplicated at `trade_optimizer.py` and `trade_service.py`) reads raw `position` and so treats a generic 4th-round rung as a QB; Avoiding does not. Fixing the two neighbours is a behavior change to shipped features nobody asked for and is out of scope — record, do not repair |
| `mobile/src/components/PlayerPickerModal.tsx` `isPickAsset` | server field, falling back to `pos`/`nflTeam` | **migrated** (2026-08-18) — pinned by `mobile/tests/check-picker-server-pick-flag.js` + `check-picker-pick-filter.js` |
| `mobile/src/screens/TradesScreen.tsx` `isPickAsset` (~:249) | `position === 'PICK' \|\| pick_value != null` | not migrated — different payload (`/api/trades`), uses `pick_value` |
| `mobile/src/utils/sessionRerank.ts` (~:109) | `position === 'PICK' \|\| pick_value > 0` | not migrated — ranking payload |
| `mobile/src/components/InLeagueCalculator.tsx` (~:548, :873) | `pos === 'PICK'` | not migrated — operates on client-built owned picks |
| `mobile/src/screens/TradeCalculatorScreen.tsx` (~:405) | `pos === 'PICK'` | not migrated |
| `web/js/app.js` (~:1746) | `pick_value != null` | not migrated — `/api/rankings` payload |

**Client mapper contract for the mobile calculator.** `CalcValueRow.is_pick` (`mobile/src/api/calc.ts`) maps to `CalcPlayer.isPick?: boolean` — a **separate field from** the demo-only `CalcPlayer.pick?: true`, which is set by the mock board and asserts nothing about the server. Mappers forward the server value verbatim or omit the key; they never synthesize it.

**Backend pin:** `backend/tests/test_trade_values_is_pick.py` (the flag follows the canonical predicate, is true for all 12 rungs and for owned picks, false for players including free agents, and no pre-existing field moved).

---

## Pick horizon — which draft years exist (#355, flag `picks.league_horizon`)

**No client may assume a league carries `current_season + 3` draft classes, or hardcode a year range for picks at all.** Which pick-years exist is *league state*, derived on the backend and expressed only by the rows the server actually returns.

**The rule.** A league carries exactly **`PICK_HORIZON_CLASSES` = 3 consecutive rookie classes, anchored to the first class that has not yet been drafted** (`backend/draft_status.py` `pick_horizon`). The window **rolls**: it is not an offset from the current season.

| League state | Classes carried | 2029? |
|---|---|---|
| 2026 season, rookie draft `pre_draft` / not yet held | 2026, 2027, 2028 | **no — phantom** |
| 2026 season, rookie draft `complete` | 2027, 2028, 2029 | **yes — real** |

Verified live against every prod league on 2026-08-19 ([evidence](feedback/items/355-phantom-pick-years/evidence.md)), including a positive reading — a post-draft league that genuinely holds 2029 traded picks — so both ends of the rule are pinned rather than inferred from an absence.

| Rule | |
|---|---|
| **Authoritative** | the set of pick rows the server returns (`GET /api/league/picks`, the deck payload). A client renders the years it is given |
| **Enforced** | where the grid is **WRITTEN** (`database.sync_draft_picks`), never at presentation — a pick outside the horizon that reached the candidate pool would still consume generation work and distort every score computed over that pool |
| **Widening** | a season the platform itself reports a traded pick for is existence proof and extends the window, bounded by `PICK_HORIZON_MAX_CLASSES` |
| **Unknown horizon** | degrades to the **narrowest plausible** window (reads as pre-draft), never to "no picks" — picks appear in ~55% of served cards |
| **Never** | a client-side year list, a `season <= currentYear + 3` filter, or a UI that assumes four classes |

**Per platform.** Sleeper derives the horizon as above from data already fetched (league meta + drafts + traded picks — no new network call). **MFL** enumerates the real `futureDraftPicks` export and has no phantom exposure. **ESPN** has no platform pick source at all; its picks come only from the manual assignment grid, which is `current_season + 3` by recorded operator decision and is deliberately **not** covered by this rule — see [Q-022](../living-memory/OPEN_QUESTIONS.md).

**Backend pin:** `backend/tests/test_pick_horizon.py`.

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

## Trade disposition control names

The two deck controls are named **Pass** and **Like** (operator decision, 2026-08-11, taken on the #169 thread and reaffirmed for #298 — it is the same control). Not "Accept/Decline", not "Send offer". Every client uses this vocabulary in copy, in accessibility labels and in analytics:

| Concept | testID | a11y label | Glyph / colour |
|---|---|---|---|
| Pass | `trades.pass-btn` | "Pass on this trade" | `x`, `semantic.neg` |
| Like | `trades.like-btn` | "Accept this trade" | `check`, `semantic.pos` |
| Third option | — | "Queue this trade" | `plus` / `check` when queued |

Swipe right = Like, swipe left = Pass; the hint string is "Swipe right to like · Swipe left to pass". The VoiceOver custom actions on the top card mirror the two buttons exactly and share their `advance()` handler — a change to one is a change to all three, and any surface that shows a trade card must carry all three or none.

Since #169 the controls live in `TradeCard.tsx`, wired through a `disposition` prop that the host threads down; `TradesScreen` maps them to `advance('pass'|'like')`. A card mounted without that prop renders **no** disposition row at all, which is invisible to `tsc` — `mobile/tests/check-single-pin-actions.js` pins the whole chain, not the co-location.

**The a11y-label asymmetry is intentional and pre-existing:** the Like button's label is "Accept this trade" while its visible name is "Like". Do not "fix" one without the other — `docs/design/components.md` and the Maestro flows both depend on the current strings.

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
- Trades: `find_trades_tapped`, `trade_card_viewed`, `trade_flagged`, `match_opened`. **`find_trades_tapped` and `trade_card_viewed` both carry `mode` ∈ `single_pin` | `deck`** (#298, 2026-08-11) — the pinned-surface discriminator; a `find_trades_tapped{mode:single_pin}` with no following `trade_card_viewed{mode:single_pin}` is #298 reappearing. `find_trades_tapped` also carries `source` ∈ `prefs_changed_strip` | `deck_error_retry` | absent, which the client had been sending since #257 into an empty prop registry that popped it on every row.
- **Feedback #297/#299/#302 batch (2026-08-11 — [addendum](feedback/items/297-lineup-impact-single-pin/analytics.md)); mobile only:**
  - Calculator: `lineup_impact_unavailable` — the honest-empty "Starting lineup" row impression. `platform` is the **LEAGUE** platform (`sleeper` | `espn` | `mfl` | `fleaflicker` | `unknown`), read from the session league cache. **Never inferred from the league id's shape: ESPN and MFL league ids CAN be numeric** (MFL `990062846` is live in this project's DB), so an `isdigit()` read labels them `sleeper`. `_sleeper_lineup_slots`' docstring implies otherwise and is wrong — those leagues fail at the meta-fetch gate, not the digit gate.
  - League drill-in: `league_team_closed` — the EXIT half. The ENTER half is **`league_team_opened` (P0-7), reused unchanged**; there is deliberately **no** `league_team_focused` / `league_team_unfocused` pair, because two events for one interaction on this screen is the two-sources-of-truth bug #208/#248/#293 are a catalog of. `via` is a closed 5-value enum, one per exit control: **`header_back` | `in_card_link` | `tab_retap` | `refocus`**, plus **`hardware_back` — REGISTERED BUT RESERVED, with no emitter.** #302's Android `BackHandler` was built and then **withdrawn before ship** (operator, 2026-08-11): it could not be exercised on any Android device or emulator and the release is iOS-only, so it would have shipped unverified code down a path no tester can reach. The name stays in the taxonomy on purpose so re-enabling is one `useEffect`, not a taxonomy migration (the `sleeper_send_*` precedent, [D-031](../living-memory/DECISIONS.md)). Both halves are pinned — the value stays allowed, and nothing emits it — by `mobile/tests/check-analytics-297-302.js` and `mobile/tests/check-league-drill-in.js`. Adding an exit control means adding a value here **and** a `closeTeam('<via>')` call — the screen's single choke point, pinned by `mobile/tests/check-analytics-297-302.js`. A `league_team_opened` with no matching close is "abandoned by navigating away", measured by absence on purpose.
- Engagement: `push_opened`
- Onboarding plan ([plan](plans/onboarding-conversion/plan.md)): `apple_prompt_shown`, `apple_prompt_accepted`, `apple_prompt_declined`, `apple_prompt_dismissed`, `quickset_prompt_shown`, `quickset_prompt_accepted`, `quickset_prompt_snoozed`, `trade_card_shared`, `coach_mark_shown`, `coach_mark_dismissed`, `celebration_shown`, `deck_exhausted_viewed`
- **P0 remediation batch (2026-08-11 — [addendum](business/analytics/2026-08-11-p0-7-addendum.md)); mobile only:**
  - Navigation + League: `tab_selected`, `league_view`, `league_basis_changed`, `league_subset_changed`, `league_team_opened`, `league_home_action_tapped`
  - Send in Sleeper: `sleeper_send_attempted`, `sleeper_send_failed` — **client-fired.** The success leg `sleeper_send_succeeded` is **server**-fired on `POST /api/trades/propose` and is therefore NOT in this list (the two namespaces are disjoint by an import-time assertion in `analytics_taxonomy.py`)
  - Invite loop: `invite_shared`, `invite_link_opened`, `invite_league_pinned`, `invite_pin_failed`. `invite_shared` is **not new** — it had been fired by `InviteLeaguematesBanner.tsx` since it shipped and dropped every time; registering it is a bug fix
  - Experiments: `experiment_exposed` (exposure, not assignment)
  - Quick Set funnel: `quickset_step_advanced`, `quickset_abandoned`
  - Deck: `deck_regenerated`
- **Dropped-emitter backlog batch (2026-08-13 — [addendum](business/analytics/2026-08-13-dropped-emitter-backlog.md)); mobile only.** 27 long-shipped emitters registered as-is (props mirror what the clients send today); this zeroes the G-031 backlog below:
  - Prompt arbiter + primers (S4 PRD-04): `prompt_shown`, `apple_banner_dismissed`, `push_primer_shown`, `push_primer_accepted`, `push_primer_dismissed`
  - Help surface (S4 PRD-01): `help_opened`, `help_read_more_tapped`
  - Player context menu (S3 PRD-02): `player_menu_opened`
  - Undo family (S3 PRD-03): `calc_clear_undone`, `match_dismiss_undone`, `suppression_undo_tapped`
  - Trades card actions + pin lifecycle: `deck_summary_viewed`, `demo_bridge_tapped`, `trade_asset_removed`, `trade_edit_in_calculator_tapped`, `trade_keep_side_tapped`, `trade_pin_cleared`, `trade_swap_suggest_opened`, `untouchable_toggled`
  - Trios: `trio_entry_tapped`, `trio_session_started`
  - Settings: `notif_denied_settings_shown`, `notif_denied_settings_tapped`, `pick_pricing_mode_changed`, `stud_tax_mode_changed`, `guide_tour_reenabled`
  - Growth: `rating_prompt_requested`
  - **`quickset_completed` is NOT among them, on purpose:** the name is server-fired and the namespaces are disjoint by an import-time assert, so the colliding client emitter in `QuickSetTiersScreen.tsx` was **deleted** (its `onboarding` prop is recorded as accepted loss in the addendum), never registered and never aliased.

**Canonical send names + the `surface` enum.** The reserved names are `sleeper_send_attempted` / `sleeper_send_failed` / `sleeper_send_succeeded` — **not** `send_in_sleeper_*`. `analytics_queries` reserved this exact trio in 2026-07-17 and `FUNNEL_STAGES` stage 8 + `FEATURE_VERTICALS["send_in_sleeper"]` already reference the succeeded name, so the reserved spelling lights those up without a query edit. Every one of them carries `surface` ∈ **`deck` | `match` | `awaiting` | `calculator`** — the four `SendInSleeperButton` mounts. Canonical definition: `SendSurface` / `SEND_SURFACES` in `mobile/src/utils/tradeText.ts`; mirrored in `CLIENT_EVENT_PROPS`. **`awaiting` is the Matches non-match send row — it is NOT `suggested`.** Adding a mount means adding a value in both places.

**`celebration_shown`, never `celebration_fired`.** The registered name has always been `celebration_shown`; the client emitted `celebration_fired` and every one of those events was dropped. Fixed 2026-08-11 by **renaming the client**, deliberately **without an alias** — an alias would make the taxonomy the place typos go to live.

**INTENT is a deny-list, so taxonomy growth is intent-by-default.** Impression-, navigation- and outcome-class names MUST also be added to `analytics_queries.NON_INTENT_EVENTS` in the same commit, or DAU/WAU step-change on ship day and every retention and churn series breaks at that seam — silently and permanently. `tab_selected`, `league_view`, `experiment_exposed` and `quickset_abandoned` are classified **non-intent** for exactly this reason (a tab tap and a League mount would otherwise make DAU ≈ app-open count). `quickset_step_advanced` stays **intent** — it is real ranking intent. Seam date recorded in the addendum. `lineup_impact_unavailable` (impression) and `league_team_closed` (terminator/dismissal, like `quickset_abandoned`) are classified **non-intent** for the same reason, added in the same commit as their allowlist entries. `league_team_opened` **stays intent** — the enter half is the value moment and already counts the user once, so admitting its terminator too would only ever add user-days where the opener was lost to queue overflow. The 2026-08-13 backlog batch classifies eight of its 27 names non-intent (`prompt_shown`, `push_primer_shown`, `notif_denied_settings_shown`, `apple_banner_dismissed`, `push_primer_dismissed`, `deck_summary_viewed`, `trio_session_started` — fires on mount — and `rating_prompt_requested` — a StoreKit request the OS may never honor); the other 19 are real user decisions and stay intent, which widens INTENT coverage at that seam (recorded in the addendum).

**Web (`web/js/events.js`) and the extension (`extension/background.js`) fire NONE of the P0-batch names.** That omission is deliberate — these are mobile surfaces — and is stated here so a future reader reads it as a decision, not as drift.

> ⚠️ **Default-deny is silent.** A client `track()` name absent from `analytics_taxonomy.py` is counted and dropped behind a **200**: no client error, no server error, a plausible dashboard with no rows. A 2026-08-11 sweep found **33 of 73** emitted mobile names unregistered; the P0 batch fixed three (`invite_shared`, `deck_regenerated`, and `celebration_fired` by rename), and the **2026-08-13 dropped-emitter backlog batch cleared the rest** (27 registered, 1 colliding client emitter deleted) — the known backlog is now **0**. Register the name *before* shipping the emitter. See `GOTCHAS.md` G-031.

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

| Key | Button label | Landing tier (default scale) | Pins to |
|---|---|---|---|
| `4_firsts` | 4+ 1sts | `firsts_4plus` | value_to_elo(4 × value(Mid 1st)) ≈ Elo 1927 |
| `3_firsts` | 3 1sts | `firsts_3` | value_to_elo(3 × value(Mid 1st)) ≈ Elo 1870 |
| `2_firsts` | 2 1sts | `firsts_2` | value_to_elo(2 × value(Mid 1st)) ≈ Elo 1789 |
| `1_first` | 1 1st | `first_1` | Mid 1st seed (Elo 1650) |
| `1_second` | 2nd | `second` | Mid 2nd seed (Elo 1400) |
| `1_third` | 3rd | `third` | Mid 3rd seed (Elo 1320) |
| `1_fourth` | 4th | `fourth` | Mid 4th seed (Elo 1240) |
| `no_value` | FA | *(none — `tier: null`)* | Elo 1100 — below every band → unranked |

**Button labels are DERIVED from `TIER_LABEL`, never authored (audit A-16 / P1-7, 2026-08-11).** The "Button label" column above is the *output* of `anchorLabel()` in `mobile/src/utils/anchorRows.ts`, which maps each key to its landing tier through `ANCHOR_TIER` and reads the tier's label. It is documentation of a derivation, not a second source of truth — **editing it does not change the app**, and re-authoring the strings in code re-creates the defect it fixed. Until P1-7 the grid carried its own hand-typed strings and **five of the eight had drifted** from the tier the answer lands in (`4 1sts`/`4+ 1sts`, `1 2nd`/`2nd`, `1 3rd`/`3rd`, `1 4th`/`4th`, `No value`/`FA`), so a user tapped "1 2nd" and read back "2nd" inside a single interaction. `mobile/tests/check-anchor-labels.js` (`npm run test:anchor-labels`) fails the build on any re-authored label, on a rung mapped to a non-existent tier, and on either host re-implementing the null-tier fallback. The landing-tier column holds **at the default anchor scale only** — see the per-user scale note below.

**`no_value`: display tier vs pin Elo.** The server pins `no_value` at Elo **1100**, which is below the `waivers` floor of **1150**, so `RankingService.tier_for_elo` returns `None` and `POST /api/anchor/save` answers **`tier: null`**. Mobile's `tierForElo` (`mobile/src/utils/tierBands.ts`) has **no lower floor** — anything under `fourth` returns `'waivers'` — so the same player wears an **FA** badge on the Tiers board. The wizard's button and its confirmation line both display **FA** (one constant, `BELOW_LADDER_LABEL = TIER_LABEL.waivers`) so they agree with that badge, while `ANCHOR_TIER['no_value']` stays **`null`** so the code never asserts that `no_value` *is* `waivers`. **The mobile/backend banding gap is a known pre-existing issue**, not something P1-7 introduced: if mobile is ever made to honour the 1150 floor, `no_value` players become tier-less and this display promise must be revisited.

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

## Trade side order — give-left / get-right, everywhere (#209/#216; violation class #312)

What the user sends renders left/first; what they get renders right/second, on every
surface showing both sides: deck cards, the player board's TRADE AWAY/TRADE FOR
columns, idea rows (give → swap glyph → receive), the featured window, the DNA
sheet's target chips AND add buttons, and the clipboard text ("I send:" before
"I get:", `tradeText.ts`). Pinned by `mobile/tests/check-dna-side-order.js`.

**Send-availability copy (#309):** `NO_SEND_REASON` never claims "Sleeper-only".
Stable, test-pinned shape: platform-NAMED tail "copy this trade to propose it in
<Platform>"; Fleaflicker's reason may say "yet" (no send path built). Pinned by
`check-trade-text.js` cases 12–15 + 29.

## League unlock thresholds (#265, #308 — both were conflation incidents)

Two unlocks on the League home progress module count DIFFERENT populations at
DIFFERENT thresholds — never conflate them:

| Unlock | Threshold | Population | Source of truth |
|---|---|---|---|
| Mutual matches | `MATCH_UNLOCK_MATES = 1` ranked leaguemate | any format, caller EXCLUDED | `mobile/src/utils/leagueUnlocks.ts` (#265); backend basis `trade_service.py generate_trades` |
| Leaderboards / contrarian ranks | 3 users with ≥1 stored ranking | ACTIVE scoring format only, caller INCLUDED | `/api/league/contrarian` (`backend/server.py`; `CONTRARIAN_UNLOCK_USERS` mirrors it client-side) |

Scoring-format display labels are pinned now that two surfaces render them
(TopBar format tile; #308 fold line): `1qb_ppr` → "1QB", `sf_tep` → "SF TEP"
(`TopBar.tsx FORMAT_TILE_LABEL`, `leagueUnlocks.ts FOLD_FORMAT_LABEL`).

## Mock-draft mode + typed-empty reason (#295/#296/#305)

**`mode` is a CLOSED two-member enum:** `cpu` | `manual`. Server constants
`MODE_CPU`/`MODE_MANUAL` (`backend/mock_draft_service.py`); client type
`MockDraftMode` (`mobile/src/api/mockDraft.ts`). On the wire: optional on
`POST /api/mock-draft` (absent/`null`/`""` = `cpu`; anything else → 400
`bad_mode`), always present on `settings_echo`. `settings_echo.mode` is the
only mode truth — no client may infer mode from `by`, cadence, or
`on_the_clock`, and no client may key "my team" off `by` (use
`settings_echo.user_owner_id` vs `picked_by_user_id`).

**`user_not_in_draft`** joins the mock typed-empty reason vocabulary
(server `REASON_USER_NOT_IN_DRAFT`; client: `MockEmptyReason` union member,
`MockDraftScreen.emptyCopy` arm, `DraftRoomScreen` blocked arm
`mock-entry.blocked.user_not_in_draft`). Fourth and last ladder rung; also
produced by the `build_settings` `UserNotInDraft` raise, mapped to the
byte-identical typed-empty at the create route. The reason enum stays OPEN
on clients (`(string & {})` + `default:` arm).

## Mock-draft ownership source (#328)

**`settings_echo.ownership_source` is a CLOSED four-member vocabulary
server-side:** `platform` | `user` | `partial` | `none` — constants
`OWNERSHIP_SOURCE_*` in `backend/mock_draft_service.py`, coerced in
`build_settings` (the `mode` idiom). Client type `MockOwnershipSource`
(`mobile/src/api/mockDraft.ts`) is **OPEN + nullable** (`(string & {})`,
`| null`): the server may grow the set, and `null` ⇔ the mock row was
persisted before the label existed — clients treat absent/`null` as
*unknown*, **never** as `"none"`. `partial` = ownership data applied but not
covering every `(round, slot)` of the mock; uncovered slots draft at slot
order. The mobile caption copy is pinned in
`MockDraftScreen.ownershipCaption` (one helper, two mounts —
`mock-draft.ownership-caption`, `mock-draft.recap.ownership-caption`) and by
`mobile/tests/check-mock-ownership-caption.js`; an unknown value renders
nothing. `mock_started` carries the resolved value as its seventh prop
(`backend/analytics_taxonomy.py`).

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

## Premium rankings import (D-058, 2026-08-15)

| Invariant | Value | Where |
|---|---|---|
| `source` enum (preset imports) | `dynasty_nerds`, `dlf` | mobile `rankPresets.ts`, analytics props, backend taxonomy |
| `via` enum | `browser`, `file` | mobile emitters, backend `CLIENT_EVENT_PROPS` |
| Source flags | `ranks.source.dynasty_nerds`, `ranks.source.dlf` — default **false**, client compiled-default **false** (never fail-open) | `config/features.json`, `FLAG_KEYS`, `useFeatureFlags.ts` |
| DN scoring → FTF board map | `PPR→1qb_ppr`, `SFLEXTEP→sf_tep` (exact); `SFLEX→sf_tep`, `STD→1qb_ppr` (nearest — labeled confirmation only) | `rankPresets.ts`, import confirmation UI |
| Contender rule | `contender_` files never apply to a dynasty board without explicit user override | `ImportRankingsSheet.tsx`, `check-premium-import.js` |
| Order-only rule | premium CSV `Value`/`Trend`/`PPG` columns are never sent to or persisted by FTF | `rankPresets.ts`, `rankings_import.py`, both check suites |

## Aggregate value presentation (2026-08-16, D-064)

Aggregate asset values shown to users are expressed as pick-equivalent labels
("≈N firsts", `_aggregate_pick_label`), never raw numerics — on every client,
ungated. Per-asset value uses the 8-rung `Tier` enum (server-computed). Raw
numeric values are a debugging/share-image-only representation (#277/#280).

## Draft-pick year decay is PER ROUND — firsts are flat (D-079, 2026-08-19)

**How much a draft pick loses per season it sits in the future is a function of the pick's ROUND, and round 1 loses nothing.** A 2029 1st and a 2026 1st are the same number. Rounds 2, 3 and 4 keep decaying at 0.85/yr.

This is registered here because pick values reach users through five surfaces that must agree — the tier badge on `GET /api/league/picks`, the rung values on `/api/rankings` and `/api/trio`, the Draft Room board, the trade calculator's pick rows, and every deck card's `give_value`/`receive_value` — and because a client that re-derives "a far-out pick is worth less" locally would now contradict the server.

**The rule and its home.** `pick_values.year_decay(round)` is the single source; it reads `model_config` `pick_year_decay_r{1..4}` live through `trade_service._c` (see [config-reference](config-reference.md#draft-pick-year-decay-d-079--pick_valuespy-db-seeded)). Rounds past 4 clamp onto `_r4`, exactly as `pick_pool_value` clamps deep rounds onto the `(4, 'Mid')` seed. Every pricing scale routes through it:

| Site | Scale | What it prices |
|---|---|---|
| `pick_values.pick_pool_value` | engine value space | `draft_picks.pool_value` for owned league picks |
| `pick_values.discount_pick_value` | rung `pick_value` | the #207 year-explicit generic rungs on `/api/rankings` |
| `pick_values.market_pick_pool_value` | engine value space | ONLY the tail past DynastyProcess's published horizon — inside DP's window the market's own published year-over-year price stands and is never re-discounted |
| `database.compute_pick_value` | legacy 0–100 pick scale | the older `draft_picks.pick_value` column |

**Never** hard-code a per-year discount in a client, and never re-derive one from a pick's label year. `GENERIC_PICK_SEEDS` and the tier band cutoffs are unchanged by D-079 — the twelve rungs are current-year assets and were never year-discounted.

**Two observable consequences that are the point, not bugs:**

- A far-out 1st now badges in the **`first_1`** band, not `second`. D-320-2's rule ("the badge reflects today's value, not the pick's name") is unchanged; the value it reflects moved. Pinned by `backend/tests/test_league_picks_tier.py::test_far_out_pick_tier_is_the_discounted_band`.
- Swapping a 1st for a different-year 1st moves exactly zero value, so the optimizer sees no edge in it. That closes the year arbitrage behind the operator's "random 1st swap. Shouldn't happen" reports.

**Deploy-free revert:** set all four keys to 0.85 and `POST /api/feature-flags/reload`-equivalent for config (`PUT /api/admin/config/<key>`, which calls `trade_service.reload_config`). Pinned by `test_pick_year_decay.py::test_all_rates_at_the_old_constant_reproduce_the_old_behaviour`.

**Analysis, measured prod impact, and the external sources that DISAGREE with the round-1 call:** [docs/reviews/2026-08-19-pick-year-valuation.md](reviews/2026-08-19-pick-year-valuation.md).
