# Affiliate Layer — HLD

Owner: eng-backend / eng-web / eng-integrations. Date: 2026-07-17. Status: DRAFT.
Requirements: [prd.md](prd.md). Shared primitives (flags, `affiliate_clicks`,
`record_event`): [../00-platform-foundation.md](../00-platform-foundation.md).
File-level detail: [lld.md](lld.md).

## 1. Shape of the system

```
config/affiliates.json ──▶ backend registry loader (validate + cache + reload)
                              │
        GET /api/affiliates/placements?surface=…   ← web / extension / iOS
                              │  filter: flag → partner.enabled → surface →
                              │          category-surface invariant → geo(state)
                              │          → offer_expires
                              ▼
                     placement payloads (copy + compliance block + go-URL)
                              │ user clicks
                              ▼
        GET /api/affiliates/go/<partner>?placement=…
                              │ mint subid → INSERT affiliate_clicks
                              │ → record_event(affiliate_click) → 302
                              ▼
                     partner site (subid in URL)  …weeks later…
                              ▼
        partner payout report (CSV) ─▶ scripts/affiliate_reconcile.py
                                        join on subid ─▶ payout summary
```

Everything server-side. Clients render what the API returns and never embed
partner URLs, copy, or state lists — one source of truth, no client redeploys
when offers change.

## 2. Partner registry architecture

`config/affiliates.json`, mirroring the `config/features.json` pattern: JSON in
`config/`, loaded by a small backend module (`backend/affiliates.py`) with the
same cache + `reload()` shape as `feature_flags.py`. Not merged into
features.json — the registry holds structured objects, not booleans, and has its
own validation.

Per-partner fields (full schema + example in [lld.md](lld.md) §1):

- `id` — stable key; matches `affiliate_clicks.partner` values.
- `enabled` — per-partner switch under the global `monetize.affiliate` flag.
- `category` — `dfs | sportsbook | commerce`. Drives compliance defaults and
  the iOS exclusion invariant.
- `surfaces[]` — subset of `web | extension | ios`.
- `offer_copy` — headline (the USER value prop), sub-line, CTA label.
- `offer_expires` — ISO date; past date = auto-hidden.
- `cta_url` — template with a required `{subid}` slot.
- `states[]` — uppercase state codes where the placement may show.
- `compliance` — `min_age` (21 sportsbook / 18 DFS typical),
  `problem_gambling_line` (bool; forced true for sportsbook by validation).

Top-level `site_link` object (beside the partner list): `{enabled, ios_copy
{row_label, card_title, card_body}, hub_path}` — drives the in-app link-out to
the offers hub (PRD FR-2b). Validation enforces the neutral-copy invariant
mechanically: `ios_copy` strings may not contain any partner `display_name`,
any `$` amount, or the substrings "bet"/"odds"/"bonus bets" (case-insensitive;
"sportsbook" as a category word is allowed once in `card_body`).

Validation at load (fail loud at boot, skip-partner + log in prod): unknown
category, missing `{subid}`, "risk-free" substring anywhere in copy, sportsbook
partner with `ios` in surfaces, sportsbook without problem-gambling line,
expired-date format errors, `site_link.ios_copy` neutrality violations.

Served to clients **only** via the placements API — the raw registry file is
never exposed (it may later hold deal notes/private fields).

## 3. Placement component architecture (per surface)

- **Web:** one renderer (`web/js/affiliate.js`) that fetches placements for
  `surface=web` and renders Chalkline-token cards into named slots
  (`data-ftf-affiliate-slot="web_bestball_card"` etc.) present in
  `positional-tiers.html`, `player.html`, and the trade results view. The
  compliance block is part of the card component, not per-page markup — pages
  cannot render a partner CTA without it. Fires `affiliate_impression` on first
  visibility (IntersectionObserver).
- **Extension:** the existing content-script popup gains one optional slot fed
  by the same API (background service worker fetches `surface=extension`,
  caches ≤ 1h). Same payload → same compliance rendering. No new host
  permissions needed (backend host already whitelisted).
- **iOS:** a single info-card component (DFS only, by server guarantee) that
  opens the go-URL via `Linking.openURL` → Safari. No in-app webview, no
  sportsbook payloads possible (server invariant, §4). Behind the same flag via
  the existing flags hook.
- **iOS site link-out (indirect path):** a neutral Settings row (+ optional
  contextual card, PRD decision 6) whose payload comes from the placements API
  (`surface=ios` response includes `site_link: {show, row_label, card_title,
  card_body, url}`). `url` = `<hub_path>?src=ios&t=<opaque token>`; opens via
  `Linking.openURL` → Safari. The server computes `show:false` when the flag is
  off, `site_link.enabled` is false, or the caller's geo has zero eligible
  partners — the app renders nothing rather than a dead link. All partner
  branding, offer amounts, and compliance blocks render only on the hub page.
- **Web offers hub (`web/offers.html`):** the same `web/js/affiliate.js`
  renderer with every slot on one page, ordered by phase/category; reads
  `src`/`t` params and passes them to the go-route so hub clicks born from the
  app are attributable (`affiliate_clicks.placement = "web_offers_hub"`,
  metadata `src=ios`). Also the landing target for lifecycle emails and the
  extension "more offers" link.

Placements are contextual: the best-ball card renders only when the user's board
actually diverges from ADP (the card's data is the hook; the affiliate CTA rides
on it). Density cap: at most one affiliate placement per page view (PRD §9.3).

## 4. Geo-gating design

**Decision: server-side IP geolocation with a local MaxMind GeoLite2-State
lookup** (`geoip2` reader; mmdb fetched in `build.sh` with a free license key,
refreshed each deploy).

Tradeoffs considered:

| Option | Verdict |
|---|---|
| Local GeoLite2 mmdb | **Chosen.** No per-request third-party call, no IP egress (privacy), ~monthly staleness is fine at state granularity. Cost: mmdb download in build, license key env var. |
| Hosted IP API (ipinfo/ipapi) | Per-request latency + rate limits + sends user IPs to a third party. No. |
| CDN geo headers | Render doesn't provide them. No. |
| Client-side geolocation API | Permission prompt for an ad — hostile UX, spoofable, no. |

Mechanics:

- Placements route resolves client IP (`X-Forwarded-For` first hop on Render) →
  state code → filters each partner by `states[]`.
- **Fail closed:** unresolvable/non-US IP → no `dfs`/`sportsbook` placements
  (commerce may still serve).
- **Extension:** same backend lookup (extension API calls originate from the
  user's browser, so the backend sees the user's IP); browser locale
  (`navigator.language`) is sent as a hint prop for diagnostics only — IP wins.
- **iOS:** geo still applied for DFS state lists; sportsbooks never reach iOS
  regardless of geo — **enforced in the route** (`surface=ios` strips
  `category=sportsbook` before any other filter), not in config.
- VPNs: our filter is best-effort marketing compliance; partners geo-fence at
  signup/deposit, which is where legal enforcement actually lives.
- The resolved state is echoed in the payload so copy can say "Available in NJ".

## 5. Click → subid → redirect flow

1. Placement CTA href = `/api/affiliates/go/<partner>?placement=<id>` (plain
   anchor, `target="_blank"`).
2. Route (flag- and enabled-checked): mint subid
   `ftf-<partner>-<placement_code>-<10 hex random>` — opaque, **no PII, no
   user_id** in the string; uniqueness by DB constraint with one retry.
3. INSERT `affiliate_clicks` (user_id when a session is present and DNT/opt-out
   absent, else NULL; partner; placement; subid; clicked_at).
4. `record_event("affiliate_click", …)`.
5. `302` to `cta_url` with `{subid}` substituted.

Server-side click logging means no client JS race, and the subid exists in FTF's
ledger before the partner ever sees it. Note: the platform brief sketched this
as POST; it is GET here because placements render as plain anchors (an `<a>`
cannot POST, and `window.open`+POST breaks new-tab UX) — labeled deviation,
recorded in the PRD-adjacent decision list.

## 6. Reconciliation data flow

Partner reports (CSV, emailed/downloaded, Net-30…Net-90) → operator drops files
into a local folder → `scripts/affiliate_reconcile.py`:

1. Parse per-partner CSV (per-partner column mapping in the script; formats
   differ).
2. Join `report.subid → affiliate_clicks.subid`.
3. Write conversion facts back onto the click row (nullable columns added to
   `affiliate_clicks` — a small delta to the foundation schema, specced in
   [lld.md](lld.md) §2).
4. Emit: FTDs + payout by partner × placement × month; orphan subids both
   directions (partner-reported-but-never-issued = fraud/mapping signal;
   clicked-but-never-converted is the funnel denominator).

No partner API integrations — reports are manual-paste by design at this scale.

## 7. Flag gating

- `monetize.affiliate` (foundation flag table) gates: placements route returns
  `[]`, go-route returns 404, all client slots render nothing, zero events.
- Per-partner `enabled` in the registry is the second level (deal-by-deal
  enablement without touching the global switch).
- No new flag keys needed beyond the foundation's — per-partner switches
  deliberately live in the registry, not `FLAG_KEYS`, because they are data
  (deal state), not code paths.
