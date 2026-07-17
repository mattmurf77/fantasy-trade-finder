# Affiliate Layer — LLD

Owner: eng-backend / eng-web / eng-mobile / eng-integrations. Date: 2026-07-17.
Status: DRAFT. Design: [hld.md](hld.md). Requirements: [prd.md](prd.md).
Foundation primitives: [../00-platform-foundation.md](../00-platform-foundation.md).

## 0. File-level change map

| File | Change |
|---|---|
| `config/affiliates.json` | NEW — partner registry (§1) |
| `backend/affiliates.py` | NEW — registry load/validate/cache + geo + placement filtering (§3) |
| `backend/feature_flags.py` | Add `"monetize.affiliate"` to `FLAG_KEYS` (§4) |
| `backend/database.py` | `affiliate_clicks` table per foundation §2.1 **+ reconciliation delta columns** (§2) |
| `backend/server.py` | Routes `GET /api/affiliates/placements`, `GET /api/affiliates/go/<partner>` (§5) |
| `build.sh` | Download GeoLite2-State mmdb (`MAXMIND_LICENSE_KEY` env) (§3) |
| `web/js/affiliate.js` | NEW — slot renderer + impression events (§6) |
| `web/positional-tiers.html`, `web/player.html` (+ trade results view) | Add `data-ftf-affiliate-slot` divs (§6) |
| `extension/background.js`, `extension/popup.js`/`content.js` | Placement fetch + one overlay slot (§6) |
| `mobile/src/components/BestBallCard.tsx` (NEW) + host screen | iOS outbound info card (§6) |
| `web/offers.html` | NEW — offers hub page (all slots, one page; PRD FR-2b) (§6) |
| `mobile/src/components/OffersLinkRow.tsx` (NEW) + `SettingsScreen.tsx` | iOS neutral site link-out to the hub (§6) |
| `scripts/affiliate_reconcile.py` | NEW — monthly reconciliation + link check (§7) |
| `backend/tests/test_affiliates.py` | NEW (§8) |
| `mobile/.maestro/07-affiliate-card-outbound.yaml` | NEW (§8) |
| `mobile/.maestro/08-offers-link-outbound.yaml` | NEW (§8) |

## 1. `config/affiliates.json` — schema + full example

Schema (informal): `{version, updated, site_link, partners: [Partner]}`.
Partner: `{id, enabled, category, phase, surfaces[], display_name, offer_copy:
{headline, subline, cta_label}, offer_expires, cta_url, states[], compliance:
{min_age, problem_gambling_line}}`.
`site_link` (PRD FR-2b; neutrality-validated per HLD §2): example —

```json
"site_link": {
  "enabled": false,
  "hub_path": "/offers",
  "ios_copy": {
    "row_label": "Offers & bonuses",
    "card_title": "Partner offers on the FTF site",
    "card_body": "Current fantasy and sportsbook offers for FTF users — on the web."
  }
}
```

States lists below are placeholders (`_comment` flags them) — the operator fills
real lists from each signed deal's terms. `enabled: false` everywhere until a
deal signs. Headlines are the USER's signup incentive, verbatim from the Jul
2026 research; they WILL go stale — that is why they are config.

```json
{
  "version": 1,
  "updated": "2026-07-17",
  "_comment": "Offers change monthly. Edit copy/urls/states here, never in code. 'risk-free' is a banned string (validation rejects it). states[] are PLACEHOLDERS until each deal signs.",
  "partners": [
    {
      "id": "underdog",
      "enabled": false,
      "category": "dfs",
      "phase": 1,
      "surfaces": ["web", "extension", "ios"],
      "display_name": "Underdog Fantasy",
      "offer_copy": {
        "headline": "Deposit match + Best Ball Mania entry",
        "subline": "Your board beats ADP — draft it where that pays.",
        "cta_label": "Draft on Underdog"
      },
      "offer_expires": "2026-09-04",
      "cta_url": "https://play.underdogfantasy.com/p/ftf?subid={subid}",
      "states": ["_PLACEHOLDER_DFS_ELIGIBLE_LIST_"],
      "compliance": { "min_age": 18, "problem_gambling_line": false }
    },
    {
      "id": "draftkings",
      "enabled": false,
      "category": "sportsbook",
      "phase": 1,
      "surfaces": ["web", "extension"],
      "display_name": "DraftKings Sportsbook",
      "offer_copy": {
        "headline": "Bet $5, Get $200 in Bonus Bets Instantly",
        "subline": "New customers. 8 x $25 bonus bets, 7-day expiry.",
        "cta_label": "Claim on DraftKings"
      },
      "offer_expires": "2026-08-31",
      "cta_url": "https://sportsbook.draftkings.com/r/sb/ftf?subid={subid}",
      "states": ["NJ", "PA", "MI", "_PLACEHOLDER_DK_LIVE_STATES_"],
      "compliance": { "min_age": 21, "problem_gambling_line": true }
    },
    {
      "id": "draftkings_dfs",
      "enabled": false,
      "category": "dfs",
      "phase": 1,
      "surfaces": ["web", "extension", "ios"],
      "display_name": "DraftKings DFS",
      "offer_copy": {
        "headline": "DFS deposit bonus",
        "subline": "Play DFS in states without sportsbooks (TX, CA, FL).",
        "cta_label": "Play DK Fantasy"
      },
      "offer_expires": "2026-08-31",
      "cta_url": "https://www.draftkings.com/r/dfs/ftf?subid={subid}",
      "states": ["TX", "CA", "FL", "_PLACEHOLDER_DFS_ELIGIBLE_LIST_"],
      "compliance": { "min_age": 18, "problem_gambling_line": false }
    },
    {
      "id": "fanatics",
      "enabled": false,
      "category": "sportsbook",
      "phase": 2,
      "surfaces": ["web", "extension"],
      "display_name": "Fanatics Sportsbook",
      "offer_copy": {
        "headline": "$1,000 FanCash bet match",
        "subline": "10 x $100 bet match in FanCash. $10 min deposit. FanCash spends on gear.",
        "cta_label": "Get the FanCash match"
      },
      "offer_expires": "2026-09-30",
      "cta_url": "https://sportsbook.fanatics.com/promo/ftf?subid={subid}",
      "states": ["_PLACEHOLDER_FANATICS_LIVE_STATES_"],
      "compliance": { "min_age": 21, "problem_gambling_line": true }
    },
    {
      "id": "caesars",
      "enabled": false,
      "category": "sportsbook",
      "phase": 2,
      "surfaces": ["web", "extension"],
      "display_name": "Caesars Sportsbook",
      "offer_copy": {
        "headline": "10x profit boosts",
        "subline": "Bet $1, double your winnings on your next 10 bets ($25 max each).",
        "cta_label": "Boost on Caesars"
      },
      "offer_expires": "2026-09-30",
      "cta_url": "https://sportsbook.caesars.com/us/promo/ftf?subid={subid}",
      "states": ["_PLACEHOLDER_CAESARS_LIVE_STATES_"],
      "compliance": { "min_age": 21, "problem_gambling_line": true }
    },
    {
      "id": "fanduel",
      "enabled": false,
      "category": "sportsbook",
      "phase": 3,
      "surfaces": ["web", "extension"],
      "display_name": "FanDuel Sportsbook",
      "offer_copy": {
        "headline": "$1,000 in Bet Resets",
        "subline": "Bet $5, get up to $200/day back in Bet Resets for 5 days.",
        "cta_label": "Start on FanDuel"
      },
      "offer_expires": "2026-07-19",
      "cta_url": "https://sportsbook.fanduel.com/join/ftf?subid={subid}",
      "states": ["_PLACEHOLDER_FD_LIVE_STATES_"],
      "compliance": { "min_age": 21, "problem_gambling_line": true }
    },
    {
      "id": "thescore",
      "enabled": false,
      "category": "sportsbook",
      "phase": 3,
      "surfaces": ["web", "extension"],
      "display_name": "theScore Bet",
      "offer_copy": {
        "headline": "$1,000 First Bet Reset",
        "subline": "Excludes accounts created on PENN/ESPN BET before Feb 2026.",
        "cta_label": "Bet on theScore"
      },
      "offer_expires": "2026-09-30",
      "cta_url": "https://thescore.bet/promo/ftf?subid={subid}",
      "states": ["AZ","CO","IA","IL","IN","KS","KY","LA","MD","MA","MI","MO","NJ","NY","NC","OH","PA","TN","VA","WV"],
      "compliance": { "min_age": 21, "problem_gambling_line": true }
    },
    {
      "id": "bet365",
      "enabled": false,
      "category": "sportsbook",
      "phase": 3,
      "surfaces": ["web", "extension"],
      "display_name": "bet365",
      "offer_copy": {
        "headline": "Bet $5, Get $150 in Bonus Bets — win or lose",
        "subline": "New customers only.",
        "cta_label": "Join bet365"
      },
      "offer_expires": "2026-09-30",
      "cta_url": "https://www.bet365.com/olp/ftf?subid={subid}",
      "states": ["_PLACEHOLDER_BET365_LIVE_STATES_"],
      "compliance": { "min_age": 21, "problem_gambling_line": true }
    }
  ]
}
```

(Fanatics Impact **commerce** gets a `category: "commerce"` entry when that
application clears — no gambling compliance fields, all states.)

## 2. Schema — `affiliate_clicks` + reconciliation delta

Create `affiliate_clicks` exactly per foundation §2.1, **plus** these nullable
columns (delta to the foundation, flagged for its next revision):

```
  converted_at   TEXT NULL      -- from partner report (FTD + qualifying bet date)
  payout_cents   INTEGER NULL   -- reported payout for this subid
  report_batch   TEXT NULL      -- reconcile run id, e.g. "2026-09-underdog"
  reconciled_at  TEXT NULL
```

SQLAlchemy Core, no SQLite-specific SQL (Postgres path). Update
`docs/data-dictionary.md`.

## 3. `backend/affiliates.py`

- `load_registry()` / `reload()` / cached `registry()` — same lock+cache shape
  as `feature_flags.py`; reads `config/affiliates.json`.
- Validation (boot: raise in dev, skip-partner+log in prod): required fields;
  `category` in enum; `{subid}` present in `cta_url`; banned-string scan
  (`risk-free`, case-insensitive) across all copy; `category == "sportsbook"`
  ⇒ `problem_gambling_line == true`, `min_age >= 21`, and `"ios" not in
  surfaces`; `offer_expires` parses.
- `state_for_ip(ip) -> str | None` — `geoip2.database.Reader` over
  `data/GeoLite2-State.mmdb` (path env-overridable `GEOIP_DB_PATH`); reader
  opened once at boot; `None` on any miss/error. `build.sh` downloads the mmdb
  using `MAXMIND_LICENSE_KEY` (secrets.local.env / Render env); if the file is
  absent at boot, log loudly and treat all lookups as `None` (fail closed —
  server still boots).
- `placements_for(surface, state, now) -> list[dict]` — filter chain:
  `monetize.affiliate` flag → partner `enabled` → surface in `surfaces` →
  **hard invariant: surface == "ios" excludes category "sportsbook" before any
  config is consulted** → `offer_expires >= today` → state in `states`
  (categories `dfs`/`sportsbook` require a known state; `commerce` serves on
  `None`). Returns client payloads only (no deal fields).

## 4. Flag registration

`backend/feature_flags.py` `FLAG_KEYS` — append under a new comment block:

```python
    # Monetization (docs/plans/monetization/00-platform-foundation.md)
    "monetize.affiliate",   # affiliate placements (web/extension/ios per plan)
```

Add `"monetize.affiliate": false` to `config/features.json`. Dark by default.
(Other `monetize.*` keys register with their own plans' builds.)

## 5. Routes (`backend/server.py`)

### `GET /api/affiliates/placements?surface=web|extension|ios`

Flag off → `200 {"placements": []}` (empty, not error — clients need no special
case). Invalid/missing surface → 400.

```
GET /api/affiliates/placements?surface=web
200 {
  "state": "NJ",
  "placements": [
    {
      "partner": "draftkings",
      "placement": "web_player_prop",
      "display_name": "DraftKings Sportsbook",
      "headline": "Bet $5, Get $200 in Bonus Bets Instantly",
      "subline": "New customers. 8 x $25 bonus bets, 7-day expiry.",
      "cta_label": "Claim on DraftKings",
      "go_url": "/api/affiliates/go/draftkings?placement=web_player_prop",
      "compliance": {
        "min_age": 21,
        "state_note": "Available in NJ",
        "problem_gambling": "Gambling Problem? Call 1-800-GAMBLER",
        "disclosure": "FTF earns a commission if you sign up."
      }
    }
  ]
}
```

The compliance strings ship in the payload so every client renders the same
words; the placement→partner mapping (which partner fills which slot) is a
server-side table in `affiliates.py` (slot ids: `web_bestball_card`,
`web_player_prop`, `web_trade_overlay`, `ext_player_overlay`,
`ios_bestball_card`; register slot ids in `docs/cross-client-invariants.md`).

### `GET /api/affiliates/go/<partner>?placement=<slot>`

Assumption (labeled): the platform brief said POST; this is **GET** because
placements are plain `<a target="_blank">` anchors, which cannot POST. Recorded
as a deviation in hld.md §5.

1. Flag off, partner unknown/disabled, or placement unknown → 404 (no redirect
   to disabled partners, ever — dead-link safety).
2. Mint `subid = "ftf-{partner}-{slot_code}-{secrets.token_hex(5)}"`; on UNIQUE
   violation retry once with fresh hex (§ Edge cases).
3. INSERT `affiliate_clicks` — `user_id` from the session if present **and**
   request lacks `DNT: 1`/opt-out, else NULL; `partner`; `placement`; `subid`;
   `clicked_at`.
4. `record_event(user_id or "anon", "affiliate_click", source=surface,
   props={partner, placement, state, subid})` — logging failures never block
   the redirect (record_event already swallows).
5. `302 Location: cta_url.replace("{subid}", subid)`.

`Cache-Control: no-store` on both routes. Impressions are client-fired
(`affiliate_impression` via the existing events endpoint); clicks are
server-fired here — one authoritative click record.

## 6. Clients

- **Web (`web/js/affiliate.js`):** on DOMContentLoaded, if any
  `[data-ftf-affiliate-slot]` exists → fetch placements (`surface=web`) → render
  a Chalkline card (tokens per docs/design/; ice CTA, no gradients/emoji) into
  the first matching slot; max one rendered card per page. Compliance block is
  inside the card template — unhideable. IntersectionObserver fires
  `affiliate_impression` once per pageview. Slots added to
  `positional-tiers.html` (best-ball card, fed by the board-vs-ADP delta the
  page already computes), `player.html` (prop context), trade results (overlay
  moment).
- **Extension:** `background.js` fetches `surface=extension` on the existing
  alarm cadence, caches ≤ 1h in `chrome.storage`; popup/content overlay renders
  one `ext_player_overlay` card with the same payload fields. No manifest
  changes (backend hosts already permitted).
- **iOS (`mobile/src/components/BestBallCard.tsx`):** flag-gated via the flags
  hook; renders only `ios_bestball_card` payloads (server already guarantees
  DFS-only); CTA → `Linking.openURL(API_BASE + go_url)` → Safari. No webview.
  Register no navigation — it's an inline card on the League/Tiers screen.
  App Store Connect: add the **"Contests" declaration** when this ships
  (ops-release checklist item).
- **iOS (`mobile/src/components/OffersLinkRow.tsx`):** the neutral site
  link-out (PRD FR-2b). Reads `site_link` from the `surface=ios` placements
  response; renders nothing when `show:false` (flag off / disabled / zero
  geo-eligible partners). Settings row first (list-row style, chevron/↗
  affordance, ice accent per Chalkline action rules); the optional contextual
  Trades/Trends card reuses the same component behind operator decision 6.
  CTA → `Linking.openURL(url)` where `url` is the server-built
  `https://<domain>/offers?src=ios&t=<token>` — the client never constructs
  the hub URL. Copy comes exclusively from the server payload (neutrality is
  validated server-side; no hardcoded strings that could drift into partner
  language).
- **Web hub (`web/offers.html`):** static page + `web/js/affiliate.js` with
  every slot id in category/phase order; on load, forwards `src`/`t` query
  params into each go-link so `GET /api/affiliates/go/<partner>` records
  `placement="web_offers_hub"` and `src` in the click metadata. Linked from
  the site nav footer; it is also the extension's "more offers" target.

## 7. Reconciliation script — `scripts/affiliate_reconcile.py`

CLI, stdlib + SQLAlchemy only. Modes:

- `--import <partner> <csv>`: per-partner column map (dict in-script:
  subid/FTD-date/payout columns per partner format); join on
  `affiliate_clicks.subid`; write `converted_at`, `payout_cents`,
  `report_batch` (`YYYY-MM-<partner>`), `reconciled_at`. Idempotent: re-running
  the same batch updates, never duplicates.
- `--report [--month YYYY-MM]`: FTDs + payout by partner × placement × month;
  click→FTD rate; **orphans both directions** (partner subids not in our
  ledger = mapping/fraud signal; our clicks never converted = funnel
  denominator).
- `--check-links`: for each enabled, unexpired partner, HTTP HEAD/GET the
  `cta_url` (dummy subid `ftf-linkcheck`) and report non-2xx/3xx → dead-link
  alarm. Run monthly with `--report`; also flags `offer_expires` within 14 days
  (staleness nudge).

Operator flow: download partner CSVs → `python scripts/affiliate_reconcile.py
--import underdog ud_aug.csv` → `--report`. No partner APIs.

## 8. Edge cases

| Case | Behavior |
|---|---|
| VPN / wrong IP state | Best-effort filter only; partners geo-fence at deposit (legal enforcement is theirs). No client-side geolocation fallback. |
| Unknown/foreign IP | Fail closed: no dfs/sportsbook placements (commerce OK). |
| Offer expired | `offer_expires` past → auto-hidden by the placements filter; go-route still resolves for 7 days grace (late clicks from cached pages), then 404. |
| Dead partner link | `--check-links` monthly; disabled partner → go-route 404s rather than redirecting nowhere. |
| Subid collision | UNIQUE constraint; one retry with fresh hex; second failure → 500 (never redirect without a ledger row). |
| DNT / privacy | `DNT: 1` (or logged-out) → `user_id NULL` in the click row; subids are random hex, **never contain user ids, emails, or any PII** (FTC/partner-report exposure). |
| Flag flipped off mid-flight | Placements go empty next fetch; go-route 404s; already-redirected users unaffected. |
| GeoLite2 mmdb missing at boot | Loud log; all lookups `None` → fail closed; server boots fine. |
| record_event failure in go-route | Swallowed (existing behavior); redirect proceeds; `affiliate_clicks` row is the authoritative record. |

## 9. Test plan

**pytest (`backend/tests/test_affiliates.py`)** — monkeypatch `state_for_ip`
and a temp registry file:

1. Registry validation: banned "risk-free" string rejected; sportsbook+ios
   surface rejected; missing `{subid}` rejected.
2. Flag off → placements `[]`, go-route 404.
3. Geo: NJ gets DK sportsbook; UT gets no sportsbook; TX gets DFS lane only;
   `None` state gets nothing gambling-adjacent.
4. **iOS invariant: `surface=ios` never returns `category=sportsbook` even
   with a corrupted registry that lists `ios` in a sportsbook's surfaces.**
5. Expired offer hidden; go-route grace then 404.
6. Go-route: 302 with subid substituted in `Location`; `affiliate_clicks` row
   written; DNT → `user_id` NULL; unknown partner 404; disabled partner 404;
   collision retry path.
7. Reconcile: import joins subid + idempotent re-import; report totals; orphan
   detection both directions.

**Maestro (`mobile/.maestro/07-affiliate-card-outbound.yaml`)**: with flag on
and a stubbed placement — card visible with disclosure text; tap CTA →
**app backgrounds / Safari opens (assert no in-app webview screen appears and
app state is unchanged on return)**; with flag off — card absent. (Maestro
can't inspect Safari; the assertion is outbound-only behavior, per PRD FR-2.)

**Maestro (`mobile/.maestro/08-offers-link-outbound.yaml`)**: with flag on and
`site_link.enabled` — Settings shows the "Offers & bonuses" row; assert the row
text contains **no `$` and no partner display name** (neutrality invariant);
tap → app backgrounds / Safari opens; with `show:false` stub — row absent.

**Web smoke:** placements fetch on tiers page renders ≤ 1 card with all four
compliance strings present in DOM (grep the rendered card for "1-800-GAMBLER"
and "earns a commission" on a sportsbook payload). Offers hub: every enabled
geo-eligible partner renders exactly once; `?src=ios&t=x` params propagate into
every go-link on the page.

**pytest additions (site link):** `site_link` neutrality validation rejects
partner names/`$`/betting substrings in `ios_copy`; `surface=ios` response
carries `site_link.show=false` when flag off, when disabled, and when geo has
zero eligible partners; go-route records `src` metadata from hub referrals.

## 10. Docs-to-update checklist (build-time, per root CLAUDE.md table)

- [ ] `docs/config-reference.md` — `config/affiliates.json` (schema + reload
      semantics), `monetize.affiliate` flag, `MAXMIND_LICENSE_KEY`,
      `GEOIP_DB_PATH` env vars.
- [ ] `docs/api-reference.md` — `GET /api/affiliates/placements`,
      `GET /api/affiliates/go/<partner>`.
- [ ] `docs/data-dictionary.md` — `affiliate_clicks` incl. reconciliation
      columns (§2 delta; also note in the foundation doc's next revision).
- [ ] `docs/glossary.md` — **FTD** (first-time depositor), **CPA**
      (cost-per-acquisition bounty per FTD), **subid** (opaque per-click
      tracking token joining partner payout reports to FTF placements),
      **placement**, **best ball**.
- [ ] `docs/cross-client-invariants.md` — placement slot ids, compliance
      strings (exact "Gambling Problem? Call 1-800-GAMBLER" + disclosure
      sentence), the iOS-no-sportsbook invariant.
- [ ] `docs/architecture.md` — `backend/affiliates.py` module + data flow.
- [ ] ADR — config-driven partner registry + server-side geo (fail-closed)
      decision.
