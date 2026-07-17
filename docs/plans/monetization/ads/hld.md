# Hybrid Ads (Free Tier) — HLD

Companion to [prd.md](prd.md). Builds on the
[platform foundation](../00-platform-foundation.md) (flags §1, entitlements §2,
referrals §5) — nothing from there is re-specified. File-level detail: [lld.md](lld.md).

## 1. Architecture overview

```
mobile (Expo/EAS)                      web (static, Flask-served)
┌──────────────────────────┐           ┌──────────────────────────┐
│ useAdsEligibility()      │           │ web/js/ads.js loader     │
│  = flags + entitlements  │           │  = FTF_FLAGS + /api/me/  │
│  + ATT/consent state     │           │    entitlements          │
│   ├─ AdBanner (AdMob)    │           │   ├─ AdSense slot fill   │
│   └─ useRewardedGate     │           │   └─ house-ad fallback   │
└───────────┬──────────────┘           └───────────┬──────────────┘
            │ claim / status                        │ house-ad config
┌───────────▼────────────────────────────────────────▼─────────────┐
│ backend: get_entitlements (pro + ad_free) · rewarded-claim cap   │
│ · GET /api/house-ads · record_event (ad_*, rewarded_*, att_*)    │
└──────────────────────────────────────────────────────────────────┘
```

Both clients derive ONE boolean, `ads_eligible`, from the same inputs in the same
order: platform flag ON → no active `pro`/`ad_free` entitlement → (mobile only)
consent state resolved. Everything ad-related hangs off that boolean.

## 2. Flag gating + kill-switch behavior

Flags `monetize.ads_mobile` / `monetize.ads_web` are already declared in the
foundation flag table (§1); this plan registers them in `FLAG_KEYS` and consumes
them. Independent kill switches, dark by default.

**Mid-session kill:** clients already refetch `/api/feature-flags` on
bootstrap/foreground (existing `useFeatureFlags` / `window.FTF_FLAGS` pattern).
When the flag flips OFF: mounted ad components unmount on next flags refresh —
banner collapses, rewarded CTA disappears, no further SDK requests are made.
Already-granted deep scans remain usable (reward was earned). We do NOT interrupt
an actively-playing rewarded ad; the claim still honors it (grant integrity >
instant kill; the flag stops *new* offers).

## 3. Entitlement suppression — hide AND no-request

Suppression is two-layered, and both layers are required:

1. **No-request:** when `ads_eligible` is false, the AdMob SDK is never asked for
   an ad (mobile skips `BannerAd` mount entirely; on cold start with a cached
   ad-free entitlement, SDK initialization is deferred/skipped). Web never injects
   the AdSense script. This is the layer that actually protects Pro UX and
   privacy — no tracking, no network chatter, no ATT prompt for paying users.
2. **Hide:** the slot containers render nothing (mobile) or the house-ad/empty
   state (web) so layout is stable.

Truth source is `GET /api/me/entitlements` (foundation §2.3), extended to return
`{pro, ad_free, ads_suppressed}` where `ads_suppressed = pro OR ad_free` (server
computes it so clients can't get the OR wrong). Clients cache the last response;
**fail-closed for ads**: if entitlements can't be fetched and the cache says
suppressed, stay suppressed; if no cache exists, treat as free tier (ads are not
a security boundary — worst case a Pro user sees one banner for one session).

Mid-session purchase: entitlements refetch after any purchase/restore event →
`ads_suppressed` flips → components unmount immediately.

## 4. The `ad_free` entitlement — design + interplay with `pro`

**Decision: a separate lightweight `ad_free` value in the existing
`entitlements.entitlement` column** (foundation schema already supports multiple
values; "pro" was just the only value at launch). Not a 30-day `pro` grant.

Justification:
- **Funnel hygiene.** A referral-earned Pro month opens every Pro gate, then
  yanks it back — manufacturing downgrade churn and muddying trial/conversion
  metrics right when we're calibrating the paywall. `ad_free` gives away only the
  thing this plan monetizes.
- **Cost asymmetry.** Ads are coffee-budget revenue; 30 ad-free days costs cents.
  30 Pro days has real pull-forward/cannibalization cost (research appendix).
- **Loop fit.** The ad-free reward is the "alternate currency for never-payers"
  (Plan E) — it must not be entangled with the Pro give-get's 4/season cap and
  RevenueCat promotional-entitlement mechanics.
- **Cheap to implement.** One more enum value + one OR in resolution; glossary
  and cross-client-invariants get the enum, done.

Interplay rules:
- `pro` implies ad-free (`ads_suppressed = pro OR ad_free`); `ad_free` implies
  nothing else — every `require_pro` gate ignores it.
- Stacking: multiple `ad_free` promo rows extend the furthest `expires_at`
  (same rule as foundation §5 promo stacking).
- A user holding both: `ad_free` is simply redundant; no cleanup needed (rows
  expire naturally).
- Granting: referral pipeline (foundation §5) writes
  `entitlement='ad_free', source='promo_referral', expires_at=+30d` when the
  ad-free arm applies (PRD D4). Manual grants work via the existing admin routes
  by passing `entitlement: "ad_free"` — no new admin surface.

## 5. ATT + consent flow order (mobile)

First eligible session only (`ads_eligible` true, prompts not yet answered):

```
app foreground with monetize.ads_mobile ON and not suppressed
  → 1. Google UMP consent check (region-aware; shows GDPR consent form only
       where required; AdMob serves non-personalized without consent)
  → 2. FTF pre-prompt explainer sheet (Chalkline; plain copy: "Ads keep FTF free.
       Allowing tracking makes them relevant instead of random." buttons:
       Continue / Not now)
  → 3. iOS ATT system prompt (only if user tapped Continue; "Not now" defers —
       re-offered at most once, later session)
  → 4. record_event att_response → initialize/request ads with the resulting
       personalization state
```

UMP before ATT because UMP is the legal gate (can forbid personalized serving
regardless of ATT) and Google's SDK sequences it first; ATT is the value-optimizing
opt-in on top. Pro/ad-free users never enter this flow at all (§3) — no consent
nagging for payers. The explainer is our one shot at the ~50% sports-vertical
opt-in; it never dark-patterns (no fake buttons, system prompt does the deciding).

## 6. Rewarded flow ("extra deep scan")

```
TradesScreen CTA (shown when ads_eligible ∧ remaining_today > 0)
  → GET /api/rewards/deep-scan/status   {remaining_today}
  → show rewarded ad (AdMob)
  → onEarnedReward → POST /api/rewards/deep-scan/claim
       server: enforce 3/day per user_id (cross-device by construction),
               grant 1 deep-scan credit (today-scoped),
               record_event rewarded_completed
  → client runs the deep scan (LLD §3)
```

Cap lives server-side so reinstalls/multi-device can't farm it. Launch trusts the
client's earned-reward callback (stakes: one deep scan); AdMob server-side
verification (SSV) is the named upgrade path if abuse appears (LLD §4). Pro users
never see the CTA — deep scans are included in Pro (their capacity check is the
entitlement, not credits).

## 7. House-ad fallback (web)

Config-driven, `features.json`-style: `config/house_ads.json` — an array of
Chalkline-safe card definitions `{id, headline, body, cta_label, url, weight,
active}` promoting FTF's own surfaces (newsletter, extension, Pro). Served via
`GET /api/house-ads` (flag-aware, cached client-side). Operator edits the JSON and
redeploys — no DB, no admin UI, same ergonomics as flags.

Used when: AdSense doesn't fill, an ad blocker nukes the slot, or the slot is
flag-on but network-unapproved (pre-AdSense-approval limbo). Weighted random pick.
House ads fire `ad_impression {format: house}` so fill rate is measurable. Mobile
does NOT use house ads at launch — banner failure collapses silently (PRD §4.1);
revisit if mobile unfill is high.

## 8. Web network migration ladder

| Stage | Network | Gate | Change surface |
|---|---|---|---|
| 1 | AdSense | day one (`monetize.ads_web` ON) | `web/js/ads.js` + `web/ads.txt` |
| 2 | Mediavine Journey | 10k sessions/mo | swap loader script + ads.txt lines; slots/containers unchanged |
| 3 | Raptive | 25k pageviews/mo | same — Raptive script manages placement within our containers |

The design isolation that makes the ladder cheap: pages contain only neutral
`<div class="ad-slot" data-slot="...">` containers; ALL network-specific code
lives in `ads.js`. Migrating networks touches one JS file + one txt file, zero
HTML pages. `app-ads.txt` (AdMob, for the mobile app) and `ads.txt` (web networks)
are separate files, both at the domain root via the existing Flask static serve
(`static_url_path=""` → files in `web/` are root-served automatically).

## 9. Docs to update when building

Per foundation §6 plus: api-reference (rewards + house-ads routes),
config-reference (`ADMOB_APP_ID`, `ADMOB_BANNER_UNIT_ID`, `ADMOB_REWARDED_UNIT_ID`,
`house_ads.json`), cross-client-invariants (`ad_free` enum, `ads_suppressed`
contract, event names), glossary (deep scan, house ad, ATT), data-dictionary
(deep-scan credits table). Full checklist in LLD §9.
