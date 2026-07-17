# Affiliate Layer (DFS + Sportsbooks + Best-Ball) — PRD

Owner: pm-monetization. Date: 2026-07-17. Status: DRAFT.
Builds on [../00-platform-foundation.md](../00-platform-foundation.md) (flags,
`affiliate_clicks` table, `record_event`) — referenced, never re-specified.
Sources: [Plan D](../../../business/product/2026-07-17-monetization-brainstorm-and-plans.md)
and both affiliate briefs in the
[research appendix](../../../business/product/2026-07-17-monetization-research-appendix.md).
Scope per operator direction 2026-07-17: **DFS and sportsbooks are both in scope.**
Companion docs: [hld.md](hld.md), [lld.md](lld.md).

## 1. Opportunity

FTF sits on the exact signal endemic operators pay for: users who maintain a
personal dynasty board are the highest-intent DFS/best-ball/betting audience, and
FTF uniquely knows **where each user's board diverges from ADP** — which *is*
best-ball edge and prop context.

CPA math (from the briefs; all conversion numbers are benchmarks, not measured):

- Benchmarks: 15–25% click→registration and 2–5% click→first-time-depositor (FTD)
  for engaged niche audiences.
- **DFS-only floor:** 1,000 actives seeing a contextual placement ≈ 20–50 FTDs ≈
  **$500–5,000/season** at Underdog's negotiated $25–150/FTD.
- **Sportsbook upside:** DraftKings sportsbook CPAs run $100–300 (target
  $150–250 negotiated). Even 10–20 sportsbook FTDs from web/extension adds
  **$1.5k–5k/season** on top of the DFS lane.
- Timing forcer: **Underdog Best Ball Mania entries close before Week 1 — the
  window is now (Jul–Aug).**

Deal structure constraint (non-negotiable): **CPA-only deals.** Rev-share
requires real state affiliate licenses (~$11.2k upfront + fingerprinting in
PA/CO; NJ ACSIE ~$2k) — dead for an app this size. CPA/flat deals need at most
cheap vendor registrations (NJ free, PA/CO ~$350). DFS referrals need **zero**
state licenses anywhere and are legal in more states (TX/CA/FL monetizable via
DFS, not sportsbook).

## 2. Goals / Non-goals

**Goals**

1. Ship the Underdog best-ball placement on web inside the Jul–Aug BBM window.
2. Stand up a config-driven partner registry so monthly-changing offers never
   require a code deploy.
3. Sportsbook lane (DraftKings first) on **web + extension only**, geo-gated to
   legal states, with the full compliance block on every placement.
4. Subid attribution end-to-end: impression → click → partner payout report →
   monthly reconciliation join.
5. "My board vs ADP" share graphic that is simultaneously the placement and an
   acquisition artifact (deep link back to FTF).

**Non-goals**

- Rev-share deals or state affiliate licensing (out of scope, see §1).
- Sportsbook anything inside the iOS app (18+ auto-rating risk; §5).
- PrizePicks (Sleeper-channel-conflict optics — deferred, not dead).
- Cards/collectibles affiliates (eBay EPN, Fanatics Collect) — distant
  experiment; only the Fanatics **commerce** program rides along (Phase 2).
- Odds feeds, bet tracking, or any RMG functionality in FTF itself.
- Paid media buying for partners.

## 3. Partner roster

Publisher reward = what FTF earns. **User signup incentive = the headline of the
placement copy** — every placement leads with the user's value, never "FTF earns
money." Offers verified Jul 2026; all offer copy lives in config and is expected
to go stale monthly (§7 risk 1).

| Partner | Category | Publisher reward (target) | User signup incentive (placement value prop) | States | Phase |
|---|---|---|---|---|---|
| **Underdog** | DFS / best-ball | CPA $25–150/FTD, negotiated direct | Deposit match + Best Ball Mania entry ("draft your board where it pays") | DFS-legal states (no affiliate licensing anywhere) | **1** |
| **DraftKings** | Sportsbook + DFS | Sportsbook **$150–250** target, DFS lane **$50–75** (DK Partners, in-house) | **"Bet $5, Get $200 in Bonus Bets Instantly"** | Sportsbook: DK-live states; DFS lane covers non-sportsbook states (TX/CA/FL) | **1** |
| **Fanatics Sportsbook** | Sportsbook (+ Impact commerce) | $50–500/FTD reported, target $150–300 (invite/contact-only); commerce ~8%/sale on Impact | **"$1,000 FanCash bet match"** (10 × $100, $10 min deposit); FanCash → merch fits collectors | Fanatics-live states; commerce = all states, zero gambling compliance | **2** (outreach now; **Impact commerce application immediately**) |
| **Caesars** | Sportsbook | $100–400/FTD (Income Access), target $100–250; **Net-60/90 pay lag** | **"10× profit boosts"** (Bet $1, double winnings on next 10 bets, $25 max each) | Caesars-live states | **2** |
| **FanDuel** | Sportsbook + DFS | Rate card only $25–35/qualified reg — **only if negotiated to $100–200/FTD** | **"$1,000 Bet Resets"** (Bet $5, up to $200/day × 5 days) | FD-live states | **3** (conditional) |
| **theScore Bet** | Sportsbook | Not public (Penn-managed, not openly joinable) | **"$1,000 First Bet Reset"** | ~20 states (AZ CO IA IL IN KS KY LA MD MA MI MO NJ NY NC OH PA TN VA WV) | **3** (one outreach email; **no build until deal**) |
| **bet365** | Sportsbook | Rev-share-led (30–35% NGR) + 15-active/mo payment gate — bad fit | **"$150 in Bonus Bets win or lose"** (Bet $5) | bet365-live states | **3** (deprioritized; revisit at scale) |

## 4. User stories

1. **Dynasty user, best-ball card.** A user browsing their tiers on web sees a
   card: "Your board says [Player] is 14 spots above ADP — that's best-ball
   edge. Draft it on Underdog: deposit match + BBM entry." One click, FTC
   disclosure adjacent, opens Underdog with FTF's subid.
2. **Sportsbook-state user on web.** A user in NJ opens a player page; a prop
   context module shows "Bet $5, Get $200 instantly" (DraftKings) with the 21+ /
   state / 1-800-GAMBLER block. Clicking logs the subid and redirects.
3. **Excluded-state user.** A user in Utah (or unknown geo) sees **no sportsbook
   placement anywhere** — not a disabled state, literally nothing rendered. A
   DFS placement may still show if their state is DFS-eligible.
4. **iOS user.** In the app, at most one "Best Ball" info card (DFS only) that
   opens Safari outbound, plus the neutral **site link-out** (FR-2b): a
   partner-free "Offers & bonuses" row that opens the FTF site's offers hub in
   Safari — the indirect path by which the app promotes every placement,
   including sportsbooks, without any gambling content in the binary.
5. **Operator reconciling payouts.** First week of the month, operator downloads
   each partner's report, drops the CSVs in a folder, runs the reconcile script;
   it joins subids to `affiliate_clicks`, prints FTDs/payout per placement per
   partner, and flags subids the partner reported that FTF never issued.

## 5. Functional requirements

### FR-1 Partner registry (config-driven)

`config/affiliates.json` (schema in [hld.md](hld.md) §2, full example in
[lld.md](lld.md) §1). Requirements:

- Per-partner: id, `enabled` (per-partner kill switch under the global flag),
  category (`dfs | sportsbook | commerce`), surfaces, offer copy, CTA URL
  template with `{subid}` slot, state eligibility list, offer expiry date,
  compliance fields (min age, problem-gambling line).
- Offers change monthly → **copy/URLs/offer text live in config, never code.**
  Editing the JSON + `reload` is the entire update path.
- Expired offers (`offer_expires` past) auto-hide server-side.

### FR-2 Surfaces and placements

| Surface | Placements | Constraints |
|---|---|---|
| **Web** | `web_bestball_card` (board-vs-ADP card on tiers/board pages), `web_player_prop` (player page prop context), `web_trade_overlay` (post-trade-found moment) | Unconstrained; all categories |
| **Extension** | `ext_player_overlay` (slot in the existing Sleeper player badge/popup) | All categories; geo via backend on API call |
| **iOS** | `ios_bestball_card` — outbound Safari-link info card only | **DFS only. Sportsbook category is excluded from iOS at the code level** (server refuses to serve sportsbook partners to `surface=ios` regardless of config — an invariant, not a config choice). DFS links → App Store "Contests" age-rating declaration; never anything triggering the 18+ gambling auto-rating. |
| **iOS → site** | `ios_site_link` — neutral link-out to the web offers hub (FR-2b) | Partner-free copy only; opens Safari; the sportsbook promotion is indirect (lives on the site, not in the binary) |

### FR-2b Offers hub + in-app site link-out (indirect promotion)

The app promotes affiliate offers **indirectly** by linking to FTF's own site:

- **`web/offers.html` ("Offers & bonuses" hub):** one page rendering every
  geo-eligible placement from `GET /api/affiliates/placements?surface=web` —
  full offer copy, compliance blocks, go-links. This page is also the
  season-agnostic landing target for lifecycle emails and the extension.
- **In-app link-out (`ios_site_link`):** a Chalkline list-row/card in Settings
  ("Offers & bonuses ↗") plus one contextual card slot (Trades/Trends, config-
  driven) that opens `https://<ftf-domain>/offers?src=ios&t=<token>` via
  `Linking.openURL` → Safari. Server-driven copy/URL via the registry so it
  changes without an app release.
- **Neutral-copy invariant (spec, not guidance):** the in-app link text and
  card body contain **no partner names, no offer amounts, no odds/betting
  language** — "See current fantasy & sportsbook offers on the FTF site" is the
  ceiling. The binary carries zero gambling content; the gambling content lives
  on the web page. Whether the neutral link still warrants the "Contests"
  declaration is an **assumption to resolve with legal-privacy before
  submission** (labeled; reviewer behavior on link-outs is inconsistent).
- **Attribution continuity:** `src=ios` + opaque token (no PII) are recorded by
  the hub page so `affiliate_clicks` rows born from app-referred visits carry
  `placement="web_offers_hub"` and an `ios`-referred marker — the reconcile
  report can split app-driven vs organic-web CPA volume.
- Flag-gated by `monetize.affiliate` + registry `site_link.enabled`; hidden
  entirely when the flag is off or no eligible partners exist for the viewer's
  geo (server returns `show: false`).

### FR-3 Compliance block (non-negotiable specs, verbatim requirements)

Every sportsbook placement MUST render, adjacent to the CTA:

1. **"21+."** (age marker; DFS placements show the partner's `min_age`, typically 18+).
2. **State eligibility in the copy** (e.g. "NJ, PA, MI + 20 more" or the full list).
3. **"Gambling Problem? Call 1-800-GAMBLER"** — exact line, every sportsbook placement.
4. **No "risk-free" language anywhere** — in config copy or code. Lint the
   registry for the string.
5. **FTC disclosure adjacent to every placement (all categories, DFS included):**
   "FTF earns a commission if you sign up." Adjacent means visually attached to
   the placement, not a footer link. "Affiliate link" alone is insufficient.
6. **Geo-targeting to legal states**: IP-based on web/extension (mechanism in
   HLD §4); unknown geo fails closed (no gambling-adjacent placement).

These are acceptance criteria for every placement component; a placement missing
any item does not ship.

### FR-4 Tracking + reconciliation

- Impressions and clicks fire `record_event` (§6). Clicks additionally write
  `affiliate_clicks` (foundation §2.1) with a unique no-PII subid passed to the
  partner URL.
- **Conversion definition:** first-time depositor + qualifying bet ($5–10 min,
  per partner terms). FTF never observes conversion directly — it arrives in
  partner reports, **Net-30 (DK/FD) to Net-60/90 (Caesars)** later.
- Monthly reconciliation: operator pastes partner reports → script joins on
  subid → per-placement/per-partner FTD + payout summary ([lld.md](lld.md) §7).

### FR-5 Flag gating

`monetize.affiliate` (already registered in the foundation flag table) gates
every surface, route response, and event. Dark by default. Per-partner `enabled`
in the registry provides the second-level switch. Both OFF → the entire layer is
invisible and the API returns empty.

### FR-6 Growth artifact

The "my board vs ADP" graphic is Chalkline-styled, shareable, embeds an FTF deep
link, and doubles as the Underdog placement surface. It ships with Phase 1 (it
serves every monetization plan per the top-5 doc sequencing).

## 6. Success metrics + events

All via existing `record_event` / `user_events` (foundation §6). Partner and
placement ride in `props` — no per-partner event-name proliferation.

| Event | Props | Fires |
|---|---|---|
| `affiliate_impression` | `{partner, placement, surface, state}` | Placement rendered visible |
| `affiliate_click` | `{partner, placement, surface, state, subid}` | CTA clicked (server-side, in the redirect route) |

Targets (season 1): click-through ≥ 2% of impressions on the best-ball card;
click→FTD ≥ 2% (benchmark floor); ≥ $500 reconciled payout in the BBM window;
zero compliance defects (audited against FR-3 checklist).

## 7. Rollout phases

**Phase 1 — now (Jul–Aug, BBM window)**
- [ ] Apply: Underdog partner program (direct; negotiate influencer-tier CPA).
- [ ] Apply: DK Partners (draftkings.com/affiliates) — ask for sportsbook
      $150–250 + DFS lane $50–75.
- [ ] NJ vendor registration (free) if DK requires it for the CPA deal.
- [ ] Ship: registry + routes + web best-ball card (Underdog) + web player-prop
      (DK, sportsbook states) + compliance block + subid tracking.
- [ ] Ship: `web/offers.html` offers hub (FR-2b) — it's the landing target for
      every later surface.
- [ ] Ship: board-vs-ADP share graphic.
- [ ] Flip `monetize.affiliate` + `underdog.enabled` when the Underdog deal signs.

**Phase 2 — Aug–Sep**
- [ ] Apply: Fanatics **Impact commerce program immediately** (no gambling
      compliance; merch/FanCash fit).
- [ ] Outreach: Fanatics Sportsbook (no public application; contact).
- [ ] Apply: Caesars via Income Access; note Net-60/90 in cash-flow expectations.
- [ ] Ship: extension overlay slot; iOS outbound DFS card + "Contests"
      declaration in App Store Connect.
- [ ] Ship: iOS `ios_site_link` link-out to the offers hub (neutral copy;
      legal-privacy sign-off on the declaration question first — FR-2b).

**Phase 3 — conditional**
- [ ] FanDuel: negotiate off the $25–35/reg rate card; **build only at
      $100–200/FTD**.
- [ ] theScore Bet: one outreach email to Penn Sports Interactive; no build
      until a deal exists.
- [ ] bet365: deprioritized (rev-share-led + payment gate); revisit at scale.

## 8. Risks

| Risk | Notes / mitigation |
|---|---|
| **Offer copy staleness** | Partner offers change monthly; stale copy is a compliance + trust defect. Mitigation: config-driven registry, `offer_expires` auto-hide, reconcile-script link/offer check, monthly operator review calendar item. |
| **Channel conflict with Sleeper** | FTF lives on the Sleeper API (unauthenticated, no ToS restriction found, no cutoff precedent — residual risk nonzero). Promoting DK/Underdog adjacent to Sleeper's own Picks product sharpens the optics. Mitigation: placements live on FTF surfaces, never inject partner promos into sleeper.com DOM beyond FTF's own extension UI; keep PrizePicks (worst optics) out. |
| **App Review** | DFS links likely require the "Contests" declaration (2025 age-rating overhaul split Contests from Gambling→18+). Any sportsbook content in-app risks 18+ auto-rating. Mitigation: sportsbook excluded from iOS at code level; iOS card is outbound-Safari only; the site link-out (FR-2b) carries neutral partner-free copy so the binary itself has zero gambling content; plain description in Notes for Review. Residual: reviewers can follow the link to the hub — the neutral-link declaration question goes to legal-privacy before submission. |
| **Trust / brand ceiling** | KTC monetizes almost nothing (donations + one affiliate link) — that's either an open lane or evidence of a **trust ceiling**: dynasty users may read betting promos as selling them out. Mitigation: contextual-only placements (board-vs-ADP is genuinely useful), value-prop-first copy, hard cap on placement density, FTC disclosure always, watch retention/feedback delta after enable. |
| **Attribution loss** | Short cookies (bet365 30d, Fanatics commerce 7d), cross-device clicks, partner-side tracking failures. Subid in the URL is the contract; reconcile script flags partner-reported subids FTF never issued and vice versa. |
| **Payment lag / counterparty** | Net-30 to Net-90; negotiated CPAs are revocable. Treat affiliate revenue as variable, never plan against it. |

## 9. Operator decisions

1. **Green-light Phase 1 applications now (Underdog + DK)?** Recommend yes —
   BBM window is closing; applications cost nothing.
2. **Sportsbook lane on web from day one, or DFS-only first?** Recommend DFS
   first flip, sportsbook one week later once the compliance block is visually
   QA'd — same build, staged enable.
3. **Placement density cap?** Recommend max one affiliate placement per page
   view, none inside the calculator flow.
4. **Fanatics Impact commerce application now?** Recommend yes — zero gambling
   compliance, immediate, small.
5. **Accept the iOS "Contests" declaration this cycle**, or keep iOS
   affiliate-free until public launch settles? Recommend defer to Phase 2 as
   specced (web/extension carry Phase 1 anyway).
6. **In-app site link-out placement(s)?** Settings row is low-risk and always
   on (when flagged); the contextual Trades/Trends card is higher-visibility
   but higher review/trust exposure. Recommend Settings row at Phase 2, add the
   contextual card only after the retention/feedback delta from Phase 2 reads
   clean.
