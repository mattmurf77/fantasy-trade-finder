# Hybrid Ads (Free Tier) — LLD

Companion to [prd.md](prd.md) / [hld.md](hld.md); foundation primitives per
[00-platform-foundation.md](../00-platform-foundation.md). All paths repo-relative.
Assumptions are labeled inline.

## 1. Flags + config

- `backend/feature_flags.py`: append to `FLAG_KEYS`:
  `"monetize.ads_web"`, `"monetize.ads_mobile"` (comment-block: "Monetization —
  hybrid ads (docs/plans/monetization/ads/)"). Defaults False automatically.
  *(If another monetization plan lands first and registers the full `monetize.*`
  block, skip — do not double-register.)*
- `config/features.json`: no change until rollout (flags flip here per gates,
  PRD §6).
- `config/house_ads.json` (new): `[{id, headline, body, cta_label, url, weight,
  active}]`. Seed with 3 cards: newsletter, extension, Pro.
- Secrets/env (→ `secrets.local.env` locally, Render env in prod; document in
  config-reference): `ADMOB_APP_ID_IOS`, `ADMOB_BANNER_UNIT_ID`,
  `ADMOB_REWARDED_UNIT_ID`. Client gets unit IDs via `app.config.js` `extra`
  (EAS env), not from the backend.

## 2. Backend

### 2.1 Entitlements (extends foundation §2 — assumes that code exists first)
- `get_entitlements()` return gains `ad_free: bool` and
  `ads_suppressed: bool = pro or ad_free`. Resolution logic unchanged (the
  existing query already matches any `entitlement` value; add the `ad_free`
  rollup alongside `pro`).
- `GET /api/me/entitlements` response gains the two fields (additive — no client
  break).
- Admin grant routes: no code change (accept `entitlement: "ad_free"` —
  validate against the enum {`pro`, `ad_free`}).
- Referral granting (foundation §5): reward writer takes an
  `entitlement` param; ad-free arm writes
  `entitlement='ad_free', source='promo_referral', expires_at=+30d`. Arm
  selection per PRD D4 (Pro-month primary; `ad_free` beyond the 4/season cap /
  A-B arm — pm-growth config).

### 2.2 Deep-scan credits + rewarded claim
New table (`backend/database.py`; → data-dictionary):

```
deep_scan_credits
  id           INTEGER PK
  user_id      TEXT NOT NULL, indexed
  scan_date    TEXT NOT NULL              -- UTC date "YYYY-MM-DD" the credit is valid for
  source       TEXT NOT NULL              -- 'rewarded' (only value now)
  consumed_at  TEXT NULL
  created_at   TEXT NOT NULL
  UNIQUE(user_id, scan_date, id)          -- count rows per (user, day) for the cap
```

Routes (`backend/server.py`; session-authed like other user routes; → api-reference):

| Route | Behavior |
|---|---|
| `GET /api/rewards/deep-scan/status` | `{remaining_today: 0-3, pro: bool}`. `remaining = 3 - count(rows for user, today)`. Pro → `{remaining_today: null, pro: true}` (uncapped, no ads). 404-equivalent `{enabled:false}` when `monetize.ads_mobile` OFF. |
| `POST /api/rewards/deep-scan/claim` | Cap check (3/day per `user_id` — cross-device by construction) → insert credit → `record_event('rewarded_completed', {surface, remaining_today})` → `{granted: true, remaining_today}`. 429 `{error:'daily_cap'}` at cap. **Assumption:** client-trusted claim at launch; upgrade path = AdMob SSV callback route verifying `ad_network` signature before insert — build only if `rewarded_completed` volume looks farmed. |
| `POST /api/trades/deep-scan` | Runs the deep scan. Guard: `pro` entitlement OR unconsumed today-credit (consume it transactionally). **Assumption (PRD D3):** scan semantics = trade-finder pass with v3 exact package construction + widened candidate depth across all counterparties, fresh (cache-bypassing) compute; final definition owned by trade-engine owner. Must be strictly additive to today's free behavior. |
| `GET /api/house-ads` | Active cards from `config/house_ads.json`, weight field included (client picks). Empty list when `monetize.ads_web` OFF. Public, cacheable (60s). |

Events (all via existing `record_event`): `ad_impression`, `rewarded_completed`,
`att_response` (client-posted through the existing client-event pathway —
an-data-architect spec is the blocking prerequisite, foundation §6). Nightly
`arpdau` rollup joins AdMob/AdSense reported revenue (operator-pasted or API
later — **assumption: manual CSV/paste at launch**) with DAU into the metrics
rows pattern of foundation §4.

## 3. Mobile (`mobile/`)

### 3.1 Build plumbing
- `mobile/app.config.js`: add plugin
  `["react-native-google-mobile-ads", {iosAppId: ADMOB_APP_ID_IOS, userTrackingUsageDescription: "..." , skAdNetworkItems: [...]}]`.
  Pin `react-native-google-mobile-ads` to a version with the Expo SDK-54 plugin
  fix (GitHub issue #820) in `package.json` (exact pin, no `^`). EAS dev build
  required — Expo Go no longer runs ads code paths (see §7 edge cases).
- `App.tsx`: deferred `mobileAds().initialize()` — called only once
  `ads_eligible` resolves true (HLD §3); never on Pro/ad-free sessions.

### 3.2 New files
| File | Contents |
|---|---|
| `mobile/src/hooks/useAdsEligibility.ts` | Derives `ads_eligible` from `useFeatureFlags` (`monetize.ads_mobile`) + entitlements state (`ads_suppressed`) + consent/ATT resolution. Single source for every ad surface. |
| `mobile/src/state/useEntitlements.ts` | (Foundation deliverable — consumed here.) Caches `/api/me/entitlements`; refetch on foreground + after purchase/restore. Fail-closed-for-suppression per HLD §3. |
| `mobile/src/components/ads/AdBanner.tsx` | Wrapper around `BannerAd` (anchored adaptive, `BannerAdSize.ANCHORED_ADAPTIVE_BANNER`). Renders `null` unless `ads_eligible`. `onAdFailedToLoad` → collapse (render null; no retry loop — next mount retries). Chalkline: container uses `--ink-1` background + `--line` top hairline + 4px padding; testID `ad-banner`. Fires `ad_impression {surface, format:'banner', filled}`. |
| `mobile/src/hooks/useRewardedGate.ts` | Exposes `{available, remainingToday, show()}`. Loads `RewardedAd` lazily when CTA visible; `onEarnedReward` → `POST /api/rewards/deep-scan/claim` → invalidate status query. Handles: load failure (CTA disabled, "try again later"), cap reached (CTA hidden), flag off (hidden). |
| `mobile/src/components/ads/AttPrePromptSheet.tsx` | Chalkline sheet (ink-2 surface, `--shadow-sheet`, Barlow Condensed header) per HLD §5 copy. Then `requestTrackingPermissionsAsync()` (expo-tracking-transparency); posts `att_response`. Shown at most twice ever (persisted flag in async storage). |
| `mobile/src/components/ads/DeepScanCard.tsx` | Trades-screen CTA card: "Extra deep scan · watch a short ad" + remaining-today ticks. Hidden for Pro (their scan entry is the plain button) and when `!ads_eligible`. |

### 3.3 Placements (surgical edits)
- `mobile/src/screens/TrendsScreen.tsx`: `<AdBanner surface="trends" />` as the
  last child inside the SafeAreaView, below the ScrollView (anchored above tab
  bar). No other changes.
- `mobile/src/screens/TiersScreen.tsx`: `<AdBanner surface="tiers" />` anchored
  bottom; **suppressed while a drag is active** (screen already tracks drag
  state for DraggableFlatList — hide banner during drag to protect the
  interaction and avoid accidental clicks).
- `mobile/src/screens/TradesScreen.tsx`: `<DeepScanCard />` in the header region
  above the card queue.
- Explicit non-placements (enforced by review + Maestro): TradeCalculatorScreen,
  RankScreen, QuickSetTiers, QuickRank, PickAnchor, ManualRanks, Matches.

## 4. Web (`web/`)

| File | Change |
|---|---|
| `web/js/ads.js` (new) | Sole owner of network code. On DOMContentLoaded: read `window.FTF_FLAGS['monetize.ads_web']`; fetch `/api/me/entitlements` (anonymous visitors = free tier); if eligible, inject the AdSense loader `<script>` ONCE and fill every `.ad-slot`; else remove slots. Unfilled slot after timeout (3s) or blocked script → fetch `/api/house-ads`, weighted-pick, render house card. Fires `ad_impression` per slot. **Snippet policy: no inline AdSense snippets in any HTML page — `ads.js` is the only place network code exists** (keeps the HLD §8 ladder a one-file migration). |
| `web/css/styles.css` | `.ad-slot` container spec: `--ink-1` surface, `--line` border, 4px radius, "SPONSOR" TickLabel in `--chalk-faint`, fixed min-height (prevent CLS), `max-width` matching page content column. House-card styles reuse existing card classes. |
| `web/positional-tiers.html`, `web/player.html`, `web/ranking-method.html`, `web/faq.html` | One `<div class="ad-slot" data-slot="<page>-1"></div>` each, below primary content / between sections. + `<script src="js/ads.js">`. No slot on `index.html` (core loop), privacy, terms. |
| `web/app-ads.txt` (new) | `google.com, pub-XXXXXXXXXXXXXXXX, DIRECT, f08c47fec0942fa0` (AdMob publisher ID once account exists). Root-served automatically (Flask `static_url_path=""`). |
| `web/ads.txt` (new) | Same line for AdSense; networks append lines at ladder stages 2/3. |

## 5. Growth-loop reward (ad-free 30d)

No new pipeline: foundation §5 referral flow, reward writer parameterized with
`entitlement='ad_free'` (§2.1 above). Client copy on the invite surface gains the
alternate-currency line only when `monetize.ads_mobile` or `monetize.ads_web` is
ON for that user's platform (an ad-free reward is meaningless before ads exist —
gate the *copy*, not the grant capability).

## 6. Flag registration + kill behavior (client)

- Mobile: `useFeatureFlags` already refetches on foreground — `useAdsEligibility`
  recomputes and unmounts ad components (HLD §2). No new plumbing.
- Web: `ads.js` reads flags at page load; kill takes effect on next navigation
  (static pages — acceptable; no long-lived web sessions in practice).

## 7. Edge cases

| Case | Behavior |
|---|---|
| Offline / no network | No ad request (SDK fails fast) → banner collapses; DeepScanCard disabled (status query failed); no cached-credit spending offline (deep scan needs the server anyway). |
| Ad-load failure | Collapse silently (mobile, PRD §4.1); house-ad fallback (web). Never a spinner, never an error toast. |
| Cap tracking across devices | Server-side per `user_id` (§2.2); device-local state is display-only. |
| Expo Go / dev without native module | `require('react-native-google-mobile-ads')` wrapped in a guarded loader (`mobile/src/components/ads/admob.ts` — try/catch require, export null stubs). All ad components render null when the module is absent. Dev on Expo Go keeps working; ads testable only in EAS dev builds with Google test unit IDs (`TestIds.*` in `__DEV__`). |
| Entitlements fetch fails | Fail-closed for suppression with cache; no cache → free tier (HLD §3). |
| Mid-session Pro purchase | Entitlements refetch post-purchase → unmount instantly. |
| Rewarded ad interrupted/abandoned | No `onEarnedReward` → no claim → no credit; CTA re-enabled. |
| Clock skew on `scan_date` | Server computes today (UTC) on both claim and consume; client never sends dates. |
| ATT denied | Continue with non-personalized ads (still monetizes); never re-prompt (OS forbids); `att_response {status:'denied'}`. |

## 8. Test plan

**pytest (`backend/tests/test_ads_entitlements.py`, new):**
- `ad_free` grant → `ads_suppressed: true`, `pro: false`; every `@require_pro`
  route still 402s (ad_free must NOT unlock Pro).
- `pro` grant → `ads_suppressed: true`.
- Expired `ad_free` row → suppression off at read time.
- Claim cap: 3 claims succeed, 4th → 429; cap resets across `scan_date`.
- Deep-scan route: consumes exactly one credit transactionally; Pro bypasses
  credits; no credit + no pro → 402/blocked.
- Referral ad-free arm writes correct row (`source='promo_referral'`, +30d).
- Flags OFF → status route reports disabled; house-ads route returns `[]`.

**Maestro (`mobile/.maestro/`, new flows; register in its README):**
- `07-ads-free-user.yaml`: flags ON + free session → `ad-banner` testID visible
  on Trends and Tiers; NOT visible on Calculator/Rank screens (assert absent).
- `08-ads-pro-suppressed.yaml`: grant Pro (admin bulk-grant in test setup) →
  walk Trends/Tiers/Trades → assert `ad-banner` and `deep-scan-card` never
  appear ("ads never appear for Pro" — the release-blocking flow).
- `09-att-preprompt.yaml`: fresh install path → explainer sheet appears before
  system prompt; "Not now" defers without the system prompt firing.
- Note: AdMob test creatives are nondeterministic — flows assert on FTF
  containers/testIDs, not creative content.

**Web smoke:** with flag ON + adblock simulated (script blocked), every slot
shows a house card, zero layout shift beyond reserved min-height.

## 9. Docs-to-update checklist (at build time)

- [ ] `docs/data-dictionary.md` — `deep_scan_credits`; `entitlements.entitlement`
      enum gains `ad_free`
- [ ] `docs/api-reference.md` — rewards status/claim, deep-scan, house-ads routes;
      `/api/me/entitlements` new fields
- [ ] `docs/config-reference.md` — 2 flags, `ADMOB_*` secrets, `house_ads.json`
- [ ] `docs/cross-client-invariants.md` — `ad_free`/`ads_suppressed` contract,
      event names, banner-surface allowlist
- [ ] `docs/glossary.md` — deep scan, house ad, ATT, rewarded ad
- [ ] `docs/design/components.md` — ad-slot container + house-ad card spec
- [ ] `docs/runbook.md` — kill-switch procedure + retention-guard check
- [ ] ADR — "ads suppression = separate `ad_free` entitlement, no-request
      client contract" (HLD §3–4 rationale)
- [ ] `mobile/.maestro/README.md` — new flows
