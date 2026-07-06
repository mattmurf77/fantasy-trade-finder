# 12. Send-to-Sleeper deep link + trade card sharing

> Tier 1 · #12 (+ #86 image adjunct) · NEW · Effort M · Sources: DD (Send Trade / Share), DDr (mass-send insight, minus the ToS exposure)

## Summary

FTF's suggestion loop currently ends at "like." The actionability gap is documented on both flanks: DynastyDealer *creates* offers inside Sleeper via user auth tokens (the mass-send moat FTF deliberately PASSed on, #79/#80), and Dynasty Daddy ships Send Trade + Share buttons on its calculator. FTF's safe version has two halves. **Deep link:** from any suggested trade (or analyzed offer, #11), jump the user into Sleeper's trade screen for the right league and partner — the user sends the offer themselves, in Sleeper, every time. **Share:** every suggestion gets a public link page and a rendered share image carrying both teams' impact framing and FTF branding, built for the place trades actually get negotiated: the league group chat full of non-users. The share card is the organic acquisition channel; the deep link is the conversion of "like" into a real offer.

The honest engineering note: the deep-link half is research-gated. Whether Sleeper exposes a web URL that lands on the trade-builder for a specific league/partner — or any `sleeper://` scheme, or asset pre-fill parameters — is unverified and must be treated as a spike, not a fact. The share half, by contrast, is mostly assembly: FTF already has an OG image generator (`backend/og_image.py`, 1200×630 trade PNGs), share-page plumbing (`/s/trade/<match_id>`, `/og/trade/<match_id>.png` in server.py), and a verdict object (#6). The gap is that today's share routes are keyed to *mutual matches*; suggestions live only in the in-memory deck, so sharing requires persisting a snapshot.

## PRD

### Problem & user story

> As a user who likes a suggested trade, I want to actually propose it — one tap into Sleeper's trade screen — and I want to drop FTF's case for the trade (both sides win, here's why) into my league chat so my trade partner sees it too.

### Goals / Non-goals

**Goals**
- One-tap path from a trade card to the most specific Sleeper destination the spike proves reachable (ideal: trade builder pre-targeted at the partner; floor: the league page) on web and mobile.
- Shareable artifact per suggestion: a stable link page (`/s/t/<share_id>`) with OG tags + a rendered image showing give/get, verdict line, both-team impact framing, FTF branding and CTA.
- Asset summary copied to clipboard alongside the deep link, so the user can paste the offer description even if Sleeper can't pre-fill.

**Non-goals**
- No offer creation in Sleeper, no write-token auth (policy: #79/#80 PASS; the user executes everything).
- No mass-send. Multi-league suggestion lists with per-league deep links (the principled alternative named in PASS #79) are a later extension, not this build.
- Share pages expose no personal ranking data beyond what the sharer chose to share (one trade snapshot).

### Functional requirements

- **FR1 (spike, ships first):** document Sleeper's reachable destinations — web URL structure for league/team/trade screens, existence and shape of any `sleeper://`/universal-link scheme on iOS, any query params for partner or asset pre-fill. Output: a short memo in this thread folder; FR2's target tier is chosen from it.
- **FR2** "Send in Sleeper" button on trade cards (web + mobile) and the #11 analyzer, opening the best-proven destination: (a) trade builder w/ partner, (b) trade builder, (c) partner team page, (d) league page — in that preference order.
- **FR3** Tapping it also copies a plaintext offer summary ("You send: A, B · You get: C — via Fantasy Trade Finder + link") to the clipboard and toasts confirmation.
- **FR4** "Share" button creates a persistent snapshot (`POST /api/trades/<trade_id>/share`) → returns `share_url`; native share sheet on mobile, copy-link on web.
- **FR5** `GET /s/t/<share_id>` renders an HTML page: give/get rosters, verdict banner (#6), both-team impact framing (#5 numbers when available), "Find your next trade" CTA; OG/Twitter meta points at FR6's image.
- **FR6** `GET /og/t/<share_id>.png` renders the 1200×630 share image via `og_image.py`: two columns, verdict headline, both-team gain framing, FTF wordmark (#86).
- **FR7** Share pages are public, unauthenticated, and resilient: snapshots are immutable JSON, so server restarts and deck expiry never break a shared link.
- **FR8** Events: `trade_deeplink_opened`, `trade_shared`, plus `share_visited` on page hit (with share_id) for the acquisition funnel.

### UX notes (per client)

- **Mobile:** action row on TradeCard gains "Send in Sleeper" (primary, after a like) and "Share" (sheet). If the Sleeper app is installed and a scheme exists (spike), prefer app-open with web fallback via `Linking`.
- **Web:** same two buttons; share = copy link + "open image" preview.
- Share page is mobile-first (league chats open it on phones) and renders without JS dependencies beyond the existing static `web/` patterns.
- Branding restraint: the image leads with the trade and the verdict, not the logo — it must read as analysis worth screenshotting, not an ad.

### Success metrics

- Deep-link opens per liked trade (conversion of like → action).
- Shares created per active user; share-page visits per share; visit → session-init conversion (the acquisition number).
- Existing match/disposition rates shouldn't drop (deep linking shouldn't cannibalize in-app matching — watch via engine-metrics #84).

### Acceptance criteria

- [ ] Spike memo filed with verified URL behaviors (each claim tested against a real league), and FR2's tier chosen from it.
- [ ] Deep link opens the documented destination on iOS (app + web fallback) and desktop web.
- [ ] Clipboard summary present on every deep-link tap.
- [ ] Shared link renders correct snapshot after a server restart; OG image unfurls in iMessage/Discord (manual check).
- [ ] No Sleeper writes anywhere in the flow.
- [ ] docs updated: api-reference.md (routes), data-dictionary.md (table), runbook (og_image cache behavior if any).

## HLD

### Components touched

- `backend/server.py` — share-create route + public `/s/t/` + `/og/t/` routes (alongside the existing `/s/trade/<match_id>` match-share family, which stays).
- `backend/og_image.py` — new suggestion-card composition (reuses existing trade PNG layout primitives).
- `backend/database.py` — `shared_trades` table.
- `mobile/src` TradeCard + share sheet; `web/js` trade card actions; `web/` share page template (server-rendered string like `_share_html`).

### Data flow

Card (in-memory deck or `/api/trades/liked`) → user taps Share → server snapshots the serialized card dict (give/receive player dicts, verdict, impact, league + usernames) into `shared_trades` → returns short id → share page/image render purely from the snapshot, never from live engine state. Deep link is computed client-side from `league_id` (+ partner ids) using the spike's URL templates served via a small config payload, so URL-format changes don't require app releases.

### Flags & config interplay

- Flags: `share.trade_cards` (share half), `share.sleeper_deeplink` (deep-link half) — independently rollable since they fail independently.
- `model_config` or feature payload carries `sleeper_url_templates` (from the spike) so the backend can hotfix Sleeper URL drift.
- Interplay: #6 verdict + #5 impact populate the page/image; absence degrades gracefully (image renders values-only).

## LLD

### API changes (routes + example payloads)

```
POST /api/trades/<trade_id>/share          (session auth)
  body: {}     // server resolves the card from deck/liked store
  → 201 { "share_id": "x7Kp2q", "share_url": "https://.../s/t/x7Kp2q" }

GET /s/t/<share_id>      → HTML (OG tags → /og/t/<share_id>.png)
GET /og/t/<share_id>.png → image/png, 1200×630

GET /api/share/config    → { "sleeper_url_templates": { "league": "...", ... } }   // spike output
```

`POST` also accepts an inline card payload (same FB-46-style echo fields as `/api/trades/swipe`) so a card can be shared even after a restart wiped the deck.

### Schema changes (SQLAlchemy Core, SQLite + Postgres)

```python
shared_trades_table = Table("shared_trades", metadata,
    Column("share_id",   String, primary_key=True),   # short random id
    Column("user_id",    String, nullable=False),     # sharer
    Column("league_id",  String),
    Column("card_json",  String, nullable=False),     # immutable serialized card snapshot
    Column("created_at", String, nullable=False),
    Column("visits",     Integer),                    # incremented on /s/t hit
    Index("ix_shared_trades_user", "user_id", "created_at"),
)
```

Idempotent add via `_migrate_db()`; text-JSON portable to Postgres.

### Client changes

- `mobile/src/.../TradeCard.tsx`: two new actions; `Linking` + `expo-clipboard`; share via React Native `Share` API. Types in `mobile/src/shared/types.ts`.
- `web/js` trade module: buttons + clipboard + window.open; share-page template lives server-side next to `_share_html`.
- Extension: none (the #19 overlay is already *on* Sleeper; it gets Share only, later).

### Sleeper integration notes (read-only boundary)

- The deep link is a **navigation**, not an API call — zero auth, zero writes, fully within policy. The user composes and sends the offer in Sleeper's own UI.
- **Unknowns (spike items, do not assert):** exact web path of Sleeper's trade builder; whether partner/assets can be pre-selected via URL; existence/behavior of `sleeper://` or universal links in the iOS app. The spike is small (manual probing with a real league) and belongs to this item, not #83 — #83 covers *API/auth* facts (pending offers, token ToS posture); this spike covers *navigation* facts. Cross-reference both memos.
- Worst-case finding (no deep route at all): FR2 floor (league page) + FR3 clipboard summary still ships and still beats today's dead end.

### Rollout

`share.trade_cards` default **false** → on after unfurl QA (iMessage, Discord, GroupMe). `share.sleeper_deeplink` default **false** → on per platform as the spike verifies each destination tier. Both web-first, mobile in the next EAS/TestFlight cycle.

### Open questions

1. Spike: what's actually reachable in Sleeper web/app navigation? (Blocks only FR2's tier, not the build.)
2. Share-page values: snapshot shows consensus-basis numbers to strangers — is the sharer's personal-Elo framing shown, or consensus only? (Proposal: consensus values + "both sides improve by their own rankings" line; never print the sharer's raw Elo table.)
3. Retention/abuse: cap shares per user/day? TTL on snapshots? (Proposal: no TTL — links are the acquisition surface; add caps only if abused.)
4. Should `share_id` creation auto-fire when a match goes `accepted` (merging with the existing `/s/trade/<match_id>` family long-term)? Defer; keep families separate for now.

## Dependencies & sequencing

- **Consumes #6** (verdict on page/image) and ideally **#5** (impact framing) — image degrades gracefully without #5.
- **Feeds #11** (analyzer's "Open in Sleeper" action), **#29** (sent-offer tracker keys off `trade_deeplink_opened`), and #27's public calculator (same share-page skeleton).
- **#86** (trade-card image generator) is folded in here as FR6 — do not build it separately.
- Wave 4 lead item: ship before #18 so push notifications ("new trade found") land on cards that have an action.
