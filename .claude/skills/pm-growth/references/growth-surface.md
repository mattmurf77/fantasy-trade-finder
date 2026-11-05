# Growth surface — inventory snapshot and how to regenerate it

> **Snapshot:** `origin/main` at `678834ab`, read 2026-10-15. Line numbers drift every
> week (the 2026-10-14 audit's `server.py` refs were already ~43 lines off a day
> later). **Never cite a line from this file in a deliverable.** Re-run the commands in
> §1 against freshly fetched `origin/main`, cite that output with its sha, and use this
> snapshot only to spot what changed. If the surface moved materially, say so in your
> deliverable's Handoffs so the skill gets refreshed.

## 1. Regenerate (run these, don't trust §2–§8)

All commands read the `origin/main` tree, so the checkout's own branch doesn't matter.
Use `git grep` only (never `grep -r`).

```bash
git fetch origin && git rev-parse --short origin/main           # the sha you cite

# Flags: key, value, line
git grep -n -E '"(growth|invite|landing)\.|"onboarding\.(landing|share_sheet)"|"ux\.deeplink_router_v2"|"profiles\.(public_pages|user_toggle)"|"experiments\.engine"|"trade\.send_in_sleeper"|"league\.power_rankings"' origin/main -- config/features.json

# Who reads each growth flag (what a flip would touch)
git grep -n -E 'growth\.[a-z_]+|invite\.k_factor_dashboard|onboarding\.share_sheet' origin/main -- backend/server.py mobile/src web/js

# Routes: share, OG, invite, profile, AASA, ?ref=
git grep -n -E '@app\.route\("/(s|og|u)/|@app\.route\("/app/league/join|@app\.route\("/api/(share|invite|league/invite-meta)|apple-app-site-association"\)|def _share_html|request\.args\.get\("ref"\)' origin/main -- backend/server.py

# What a non-user sees on /s/*: CTA text + target, OG image, brand line
git grep -n -E 'cta_url=|cta_text=|image_url=|· Fantasy Trade Finder|class="brand"' origin/main -- backend/server.py

# Events: registration + props, then classification
git grep -n -E '"(trade_card_shared|invite_[a-z_]+|calc_trade_shared|share_package_created|rating_prompt_requested|notif_empty_state_shown)"' origin/main -- backend/analytics_taxonomy.py
git grep -n -E 'invite_|share_package_created|calc_trade_shared|trade_card_shared' origin/main -- backend/analytics_queries.py

# Emitters (mobile + web). A registered event with no emitter on a surface is a GAP.
git grep -n -E "track\(['\"](invite_[a-z_]+|trade_card_shared|calc_trade_shared|share_package_created)|^ *'(trade_card_shared|calc_trade_shared|share_package_created)'," origin/main -- mobile/src web/js

# Mobile entry points (mounts and invite calls)
git grep -n -E "<(InviteLeaguematesBanner|InviteLeaguematesCard|ShareTradeImage|SendInSleeperButton)[ />]|<(InviteLeaguematesBanner|InviteLeaguematesCard|ShareTradeImage|SendInSleeperButton)$|shareInvite\(\{" origin/main -- mobile/src

# Words a non-user receives, referral attribution, web CTA
git grep -n -E 'type="referral_joined"|captureReferralFromUrl\(\)|lp-mobile-link|Join me on' origin/main -- backend/server.py web mobile/src

# Indexing intent
git show origin/main:web/robots.txt
git grep -n -i 'name="robots"' origin/main -- 'web/*.html'

# Tests that pin the surface
git ls-tree -r --name-only origin/main -- backend/tests mobile/tests | grep -E 'invite|share|universal|tier_share|growth'

# Decisions (titles + dates)
git grep -n -E '^\| D-(028|039|040|046|057|173) ' origin/main -- living-memory/DECISIONS.md

# Growth items still open in NEXT.md
git grep -n -i -E 'invite|referral|share_landing|app store|testflight url' origin/main -- living-memory/NEXT.md
```

## 2. Flags (`config/features.json` @ `678834ab`)

| Flag | Value | Line | Gates |
|---|---|---|---|
| `growth.share_landing` | **true** | 185 | `POST /api/share/package`, `/s/p/<id>`, `/og/p/<id>.png`; client reads at `TradeCalculatorScreen.tsx:177`, `TradesScreen.tsx:739`, `ShareTradeImage.tsx:114` |
| `growth.rating_prompt` | **true** | 186 | App Store review prompt (`utils/ratingPrompt.ts:45`) |
| `growth.tier_board_share` | false | 188 | `/s/tiers/…`, `/og/tiers/…` → 404. **OFF is the resting state** (D-039, operator ruling D-P1-12), not a dark launch |
| `growth.invite_join_link` | false | 190 | Client emits `/app/league/join/<id>?ref=` instead of legacy `/?league=&ref=` (`InviteLeaguematesBanner.tsx:59`). Graduation needs an external AASA validator + a device check (D-028; `docs/runbook.md` § AASA) |
| `growth.referral` | false | 149 | Registered (`feature_flags.py:268`, "give-get referral program"); **no reader in code** |
| `growth.group_unlock` | false | 150 | Registered (`feature_flags.py:269`); **no reader in code** |
| `invite.k_factor_dashboard` | false | 20 | `/api/invite/impact` returns a zeroed payload while off |
| `onboarding.share_sheet` | false | 130 | Read at `TradesScreen.tsx:472` |
| `onboarding.landing` | **true** | 125 | Username-first landing on `SignInScreen` |
| `landing.platform_options` | **true** | 28 | Sleeper · ESPN · MFL entry chips + `POST /api/entry/platform` |
| `landing.smart_start_cta` | false | 26 | League-URL input on landing (client only) |
| `landing.try_before_sync` | false | 27 | `POST /api/session/demo` (off since 2026-08-24) |
| `ux.deeplink_router_v2` | **true** | 166 | Deep-link routing |
| `profiles.public_pages` / `profiles.user_toggle` | false / false | 24 / 195 | `/u/<username>` → 404 |
| `experiments.engine` | **true** | 123 | Experiment engine (has a `growth` layer, `experiments.py:74`) |
| `trade.send_in_sleeper` | **true** | 52 | Send-to-league card (leaguemates see the offer in their platform) |
| `league.power_rankings` | false | 198 | `web/league-rankings.html` (also `Disallow` in robots) |

## 3. Routes (`backend/server.py` @ `678834ab`)

| Route | Line | Guard | Notes |
|---|---|---|---|
| `/app/league/join/<league_id>` | 12596 | none (by design, D-028) | 302 → `/?league=&ref=`; `ref` read at 12621 |
| `/.well-known/apple-app-site-association` | 12633 | none | Claims `/u/*`, `/s/*`, `/app/league/join/*`, `/?ref=*`, `/?league=*` |
| `/og/tiers/<pos>/<username>.png` | 25415 | `growth.tier_board_share` | 404 while off |
| `/og/trade/<match_id>.png` | 25446 | **none** | |
| `_share_html(...)` | 25460 | — | Renders every `/s/*` page: OG tags + one CTA |
| `/s/tiers/<pos>/<username>` | 25522 | `growth.tier_board_share` | CTA "Build your tiers" → `/` |
| `/s/trade/<match_id>` | 25552 | **none** | CTA "Find your next trade" → `/` |
| `POST /api/share/package` | 25599 | `growth.share_landing` + session | Mints `/s/p/<id>`; 20/hour/user; demo refused |
| `/s/p/<short_id>` | 25650 | `growth.share_landing` | CTA "Build your own trade" → `/` |
| `/og/p/<short_id>.png` | 25673 | `growth.share_landing` | |
| `/api/invite/impact` | 26278 | `invite.k_factor_dashboard` (zeroed when off) | Inviter's K-factor snapshot |
| `/api/league/invite-meta` | 26445 | none, public | Sleeper public league name only (privacy constraint) |
| `/u/<username>` | 26634 | `profiles.public_pages` | |
| `session_init` → `referral_joined` bell row | 22648–22673 | first session with `invited_by` | Storage: `users.invited_by` (`database.py:462`); share packages `load_shared_package` (`database.py:14780`) |

## 4. Events (`backend/analytics_taxonomy.py` @ `678834ab`)

| Event | Registered / props | Class | Emitters |
|---|---|---|---|
| `trade_card_shared` | 73 / 1037 | INTENT | `TradesScreen.tsx:5339` (`channel`, `surface` registered but never sent) |
| `calc_trade_shared` | 253 / 1281 | INTENT | `TradeCalculatorScreen.tsx:615` |
| `share_package_created` | 253 / 1291 | NON_INTENT (`analytics_queries.py:159`) | `ShareTradeImage.tsx:171`, `TradeCalculatorScreen.tsx:598`, `TradesScreen.tsx:5317` |
| `invite_cta_shown` | 258 / 1309 | NON_INTENT (`analytics_queries.py:160`); a mount counter on some surfaces | `LeagueScreen.tsx:329` (league_home), `MatchesScreen.tsx:974` (matches_empty), `TopBar.tsx:276` (notif_empty) |
| `invite_cta_tapped` | 258 / 1311 | INTENT | `InviteLeaguematesBanner.tsx:127` (inside `shareInvite`) |
| `invite_shared` | 139 / 1154 | INTENT | `InviteLeaguematesBanner.tsx:135` (inside `shareInvite`, on non-dismissed share) |
| `invite_link_opened` | 139 / 1157 | — | `LeagueJoinScreen.tsx:77`, `deepLinks.ts:426` |
| `invite_league_pinned` / `invite_pin_failed` | 139–140 / 1159–1161 | — | `LeaguePickerScreen.tsx:245` / `:273` |
| `notif_empty_state_shown` | 296 / 1380 | — | `TopBar.tsx:265` (bell sheet; `invite_offered` prop) |
| `rating_prompt_requested` | 353 / 1425 | — | `utils/ratingPrompt.ts:90` |

`shareInvite` (`InviteLeaguematesBanner.tsx:119`) is the one mobile invite path; callers:
the banner (`:146`), `LeagueScreen.tsx:490` and `:1008` (members overlay),
`MatchesScreen.tsx:930`, `TopBar.tsx:289`. `surface` is a closed set (`InviteSurface`, `:67-72`).

## 5. Mobile entry points

- **Invite:** `InviteLeaguematesCard` on `LeagueScreen.tsx:603`; `InviteLeaguematesBanner`
  on `TradesScreen.tsx:7052`; Matches empty state; members overlay; bell empty state
  (D-046). Social-proof gate: `utils/inviteSocialProof.ts` (pinned by
  `mobile/tests/check-invite-social-proof.js`).
- **Invite landing in app:** `LeagueJoinScreen.tsx` (join-path form);
  `utils/deepLinks.ts` (legacy `?league=` form, both end in one persisted intent).
- **Share:** `ShareTradeImage` (`TradeCalculatorScreen.tsx:1033`,
  `InLeagueCalculator.tsx:1548`); share URL ladder `utils/shareLinks.ts`
  (`resolveShareUrl`, never returns a link-free URL).
- **Send-to-league** (leaguemates see the offer): `SendInSleeperButton` (wraps ESPN/MFL
  buttons) on `TradeCard.tsx:983/1005`, `TradesScreen.tsx:8766`,
  `InLeagueCalculator.tsx:1488`.

## 6. Web

- Landing `web/index.html`: title/OG use the shipped name; the only app path is
  "Request TestFlight access" → `/contact.html` (`:266`). No App Store or public
  TestFlight link for the app exists in `web/`, `backend/` or `mobile/src` (NEXT.md "Web
  parity SHIPPED" item; waiver W6 in `docs/plans/web-parity/scope.md`).
- Referral capture: `web/js/app.js:6390` `captureReferralFromUrl()` →
  `ftf_invited_by` / `ftf_invited_league`, sent as `invited_by` on session init (`:810`).
- Web invite share: `app.js:5831` (`buildInviteMessage`), `:6075` (`buildChannelMessage`).
- `web/robots.txt`: `Disallow: /s/` and `/og/` (:25-26), `/player.html` (:20),
  `/league-rankings.html` (:17); sitemap canonical is `fantasy-trade-finder.onrender.com`
  (no custom domain). `noindex` on `player.html`, `profile.html`, `calculator.html`, `404.html`.

## 7. Tests that pin the surface

`backend/tests/test_invite_links.py`, `test_share_package.py`, `test_universal_links.py`,
`test_tier_share_routes.py`, `test_notif_inbox_growth.py`;
`mobile/tests/check-invite-social-proof.js` (CI runs every `check-*.js`, `ci.yml:47`).

## 8. Decisions

D-028 (legacy `?league=` invite parsed forever; join path 302s into the landing) ·
D-039 at `DECISIONS.md:620` (tier-board share OFF as resting state; note a second,
unrelated D-039 at `:638` on ESPN trade-write) · D-040 (share/invite event registration;
`tier_board_shared` cancelled) · D-046 (bell carries receipts; invite ask lives in the
empty state) · D-057 (ships as **Fleeced: Dynasty Trade Finder**) · D-173 (web posture
B, Companion).

## 9. Observed at this sha — verify before acting

Leads for a loop audit or non-user view, not conclusions:

1. Every `/s/*` CTA points to `/` (`server.py:25548`, `:25563`, `:25669`), whose only
   app path is a TestFlight request form. The share loop has no install step until a
   public URL exists (operator decision).
2. `_share_html` brands pages "Fantasy Trade Finder" (`:25479` title, `:25512`); mobile
   invite text says "Dynasty Trade Finder" (`InviteLeaguematesBanner.tsx:132`,
   `app.js:5834`); the `referral_joined` row says "joined Fantasy Trade Finder"
   (`server.py:22662`). D-057's shipped name is Fleeced: Dynasty Trade Finder.
3. `og:image` is a relative URL (`/og/p/<id>.png`); many unfurlers want absolute.
4. `robots.txt` disallows `/s/` and `/og/`; check each unfurler's robots behavior
   with its card validator before assuming previews render.
5. `/s/trade/<match_id>` and `/og/trade/<match_id>.png` have no flag guard (`head-eng` to
   confirm intent).
6. NEXT.md item 0g says `invite_shared` is missing from the League tab. At this sha
   `LeagueScreen.tsx:485-490` calls `shareInvite`, which fires it. Confirm with
   `analytics-lead` (rows by `surface`) before treating either claim as current.
7. Web invite paths (`app.js:5831`, `:6075`) fire no `invite_*` event.
8. No `referral_joined` analytics event; it exists only as a bell-row type.
   `invite.k_factor_dashboard` is off, so K-factor isn't readable in-product.
9. NEXT.md item 8 ("First public App Store release. Checklist in `docs/business/ops/`")
   points at a file that doesn't exist.
10. `docs/business/context.md` still says client-side analytics is dark (2026-07-12);
    the taxonomy and the emitters above say otherwise.
