# Rankings Marketplace — publisher ranks in-app + contributor rank-set sales

Owner: pm-monetization (+ pm-partnerships for publisher deals). Date: 2026-07-17.
Status: PLAN (research + assessment; PRD/HLD/LLD follow on green-light).
Research: condensed briefs in [the research appendix](2026-07-17-monetization-research-appendix.md)
(publisher landscape; accuracy + marketplace economics sections).

## Question & context

Can FTF monetize by letting (a) dynasty platforms — Dynasty Nerds, DLF,
PlayerProfiler — offer their rankings in-app via IAP or subscriber account-linking,
and (b) users sell their own rank sets to other users, with credibility from a
FantasyPros-style accuracy contest? What profile types, dashboards, and rev shares
make it work?

**Strategic fit — why this is FTF-shaped:** every FTF user already maintains a
personal Elo board, and the engine already accepts `seed_ratings` (rank → initial
Elo). So "adopting" a rank set isn't reading an article — it **re-seeds your board
and re-weights your trade suggestions**. That's the FantasyPros My Playbook insight
(custom consensus re-weights every tool) fused with FTF's core mechanic (your board
then *diverges* as you swipe). No competitor can offer "buy these ranks and your
trade finder thinks like this ranker." Two pieces of white space confirmed by
research: **no in-app rankings marketplace exists in fantasy**, and **nobody scores
dynasty rankings retrospectively** — FTF can be first at both.

**Platform thesis (operator direction, 2026-07-17):** the durable asset may be the
*combination* of the Elo-matchup method (honest, effortful rankings, not
copy-paste lists) and the accuracy engine that scores them — "TipRanks for fantasy
rankings." Under that thesis, ranking **formats** are the expansion surfaces, all
riding one pipeline (publish → snapshot → score → badge → adopt/sell). Dynasty
trade-finding remains the wedge and the brand; the engine is built
format-agnostic so the thesis can be tested without sprawl (see §Rank-set types
and Phase 6).

## Research summary (details + citations in appendix)

**Publishers.** DLF is the best first partner: deepest rank catalog (overall/SF/
IDP/devy/rookie), and they already trade Premium away through partner channels
(Chalkboard $10/yr, Novig free-with-deposit, $5 flash sales) — an effective floor
of $5–10/yr means subscriber-linking costs them ~nothing and fits their existing
promo machinery. PlayerProfiler ($45/season modules, media-forward CEO) fits an
IAP-first "cheap taster" deal scoped to rankings (their Dynasty Deluxe includes a
competing trade tool). Dynasty Nerds is a direct competitor (DynastyGM = league
sync + calculator) — linking-only pitch or pass. FantasyPros' commercial API (real
redistribution licenses) is the turnkey no-negotiation option for a consensus rank
set; FantasyCalc's open market values are a free default-library option. None of
the big 3 has OAuth or an API — linking = promo/entitlement codes or an
email-verification endpoint; feeds = CSV drops or scrape-with-permission.

**Accuracy.** FantasyPros scores rank-slot-implied points vs actual ("Accuracy
Gap"), with snapshot locks, relevance weighting (1.0 top slots → 0.5 deep),
worst-week forgiveness, and unranked-player imputation at deepest-rank+1; experts
join for exposure (badges/promotion), not cash. Dynasty-specific scoring exists
nowhere — proxy approaches: multi-year future-value realization, trade-value
trajectory vs market 6–12 months later, rookie-class hit-rate tiers, ADP drift.
TipRanks adds the minimum-sample gate (no rating below ~10–15 scored calls);
Metaculus adds peer-relative scoring (difficulty-immune) and a public
methodology/track-record page as the credibility move.

**Economics.** Creator-platform take rates cluster at ~10–13% all-in (Patreon/
Substack/Gumroad) but rise with how much audience + trust the platform owns
(YouTube 30%, Twitch 50%, tipster marketplaces 50–70%). FTF owns both the audience
and the *computed* trust layer → **30% platform take** reads generous vs tipster
norms while beating Patreon economics. Apple 3.1.1 forces IAP for in-app digital
content and kills dynamic per-listing pricing (Patreon's forced migration is the
case study); the sanctioned workaround is **consumable credit packs** (dynamic
pricing lives in FTF's ledger). Stripe Connect Express handles KYC/W-9/1099 for
cash-outs at $2/mo per active account; 2026 thresholds (1099-K $20k/200txn,
1099-NEC $2k) mean almost no forms. Credits-only payouts avoid money-transmission
questions entirely (FinCEN closed-loop exemption). Dabble's Copy Cash (~$0.10
credit per copy) is the micro-reward precedent.

## How it works — product design

### Three lanes, one pipeline

| Lane | Who | Money | Trust source |
|---|---|---|---|
| **1. Publisher IAP** | DLF, PlayerProfiler, FantasyPros-consensus | User buys a publisher rank set ($4.99–9.99/season IAP or credits); rev-shared with publisher | Brand + accuracy scoring (same pipeline) |
| **2. Publisher linking** | DLF (first), later others | Free unlock for the publisher's existing subscribers (code/email verification); FTF gets content + co-marketing, publisher gets churn-reducing benefit + warm leads; optional bounty per linked account | Brand |
| **3. Contributor marketplace** | Any FTF user who earns it | User prices their rank set in credits; FTF takes 30% of net | **Measured accuracy only** — listing is gated on badge tier, not application |

All three produce the same artifact: a **published rank set** (versioned, timestamped,
per scoring format) that any user can browse, preview (top-25 free), and **adopt**.

### Adoption mechanics (the product hook)

Three adoption modes, surfaced at onboarding ("start from an expert board") and in
Settings:
- **Seed** (default): rank set → `seed_ratings` → initial Elo board; the user's
  swipes personalize from there. New users skip the cold start; the set author is
  credited on the board ("seeded from DLF, March '27").
- **Replace**: overwrite current board Elo values (rank → Elo via the existing
  reorder/`valueForElo` mapping). Destructive → confirm + one-tap restore of the
  prior board (snapshot before replace).
- **Track** (later): keep your board, show the adopted set as a comparison column
  in Overall Ranks / tiers ("you vs. your expert").

Because `member_rankings` is per-league and per-format (`1qb_ppr` / `sf_tep`),
rank sets declare a format and adoption is per-league — a superflex set can't
silently seed a 1QB league.

### Rank-set types (format-agnostic engine — schema requirement, day one)

Every rank set declares a `set_type`; each type plugs its own benchmark and
scoring windows into the same pipeline. **This is a schema decision now, not a
product commitment** — cheap insurance that keeps the platform thesis testable.

| `set_type` | Scored against | Cadence | Status |
|---|---|---|---|
| `dynasty` | Dual benchmark: production truth (13wk/1yr/2yr implied-points) + market truth (value trajectory vs consensus 6–12mo) | Quarterly snapshots, slow-accruing | Core — launch type |
| `rookie` | Outcome-tier hit rates (Elite/Starter/Flex/Bust at 1–3 yrs) + market truth | Annual class, scored yearly | Core — launch type (already in plan) |
| `redraft` | Single-season implied-points (the FantasyPros method, unmodified) | Weekly/preseason snapshots, scored same season | Type-2: fast annual contest cadence; keeps early leaderboards alive ("top 5% redraft, provisional dynasty"). A marketplace rank-set type, **not** a second first-class board — the trade engine consumes only the dynasty board (now/future blend already handles win-now internally via `trade.outlook_blend`) |
| `bestball` | Preseason board vs realized best-ball scoring + ADP-drift; scoreable in one season | Apr–Aug snapshots | Type-3: the standout expansion — rankings ARE the product in best ball, the calendar fills the dynasty trough, and it monetizes through the existing Underdog affiliate lane ("your scored board vs ADP" is both the accuracy product and the CPA placement) |
| DFS | — | — | **Explicitly out.** DFS skill is projections + salary optimization + ownership leverage; ordinal Elo boards don't map onto it. Different product; off the roadmap |

Sprawl guard (solo operator): each type needs its own outcome data, calibration,
and audience. Dynasty + rookie launch; redraft and bestball ship only as
marketplace types behind their own flag (`ranks.set_types_extended`), each gated
on its outcome-data source existing.

### Contributor profile type

Extend `accounts` with a `contributor` role (nullable `contributor_type`:
`user | publisher`), gated by application for publishers and by **accuracy
qualification for users** (below). Contributor profiles get:
- Public page (web + in-app): bio, badge tier, accuracy track record (auditable
  chart, methodology-linked), listed rank sets, adoption/purchase counts.
- **Publishing flow:** their existing FTF Elo board (or CSV upload for
  publishers) → snapshot → published set with version history. Updates re-publish;
  buyers get updates for the purchased season (matches draft-kit norms).
- **Dashboard** (`GET /api/contributor/dashboard`): adoptions (seed/replace
  counts), previews→purchase conversion, gross credits, FTF take, net earnings,
  linked-signup counts (for publishers on lane 2), accuracy standing + next
  scoring window, payout status.

### Accuracy engine (the trust layer — ships first)

Benchmarks and windows are **per `set_type`** (table above); what follows
describes the launch types (`dynasty`, `rookie`).

- **What's scored:** every published set's quarterly snapshots (auto-locked), on
  rolling horizons, against a **dual benchmark**: (a) *production truth* —
  realized fantasy points over 13-week / 1-year / 2-year windows via
  rank-slot-implied values (FantasyPros method stretched to multi-year); (b)
  *market truth* — value-trajectory vs consensus market values 6–12 months later
  (fast feedback; benchmark = FantasyCalc open values + FTF's own aggregate, not
  KTC scraping). Rookie sets additionally scored on outcome-tier hit rates.
- **Fairness mechanics (all borrowed from proven systems):** peer-relative
  z-scores per window; relevance weighting top-150 → 0.5 deep; unranked imputation
  at deepest+1; worst-window forgiveness after N windows.
- **Badges:** provisional until ≥2 scored windows (TipRanks minimum-sample gate);
  then rolling-24-month percentile tiers (e.g., top 10% "Sharp"), recomputed
  quarterly with decay. **Selling is gated on holding a badge tier** — the
  differentiation vs Whop/Tipstrr is that FTF *computes* credibility rather than
  hosting self-reported records.
- **Public methodology + track-record page** from day one (Metaculus move) — the
  accuracy claim is the product; it must be auditable.
- Solo-op feasible: a quarterly scoring cron over data FTF already stores; no
  human judging. **Every FTF user is scored passively** (their board is a rank
  set) — the leaderboard doubles as an engagement/contest surface ("where do you
  rank in your league?") a season before any money moves, and is itself the
  contributor-recruiting funnel (FantasyPros recruited 200 experts on exposure).

### Commerce design

- **iOS:** consumable **credit packs** at 3–5 fixed IAP SKUs (solves Apple's
  pre-registered-SKU rigidity; explicitly sanctioned for in-app currency).
  Contributors price sets in credits. Publisher sets can also be plain
  non-consumable IAPs (fixed price, few SKUs — same projector as Season Pass).
- **Web:** Stripe checkout for credits at a ~10% discount (US iOS may link out
  post-Epic; the entitlement service is already payment-agnostic per the
  [monetization foundation](../../plans/monetization/00-platform-foundation.md)).
- **Split:** contributor 70% / FTF 30% **of net** (after Apple/Stripe), disclosed
  on the contributor dashboard. Publisher deals negotiated per-partner (target
  60–70% to the publisher on their branded sets — they bring the brand; we bring
  distribution + the surface).
- **Payout ladder:** earnings accrue as **credits** (default; usable against FTF
  Pro/passes; keeps hobbyists paperwork-free and FTF outside money transmission).
  Contributors crossing **$100 accrued + verified badge tier** may opt into
  **Stripe Connect Express** cash-out (hosted KYC/W-9; quarterly payouts, $25
  minimum). Publishers are invoiced/remitted directly, outside the ladder.
- **Anti-abuse:** rank-set content is versioned and watermark-attributed;
  adoption grants are per-account entitlements (`entitlements` row, source
  `rankset_purchase`, season-scoped) via the existing foundation projector.

### Feature flags (foundation pattern, all dark)

`ranks.accuracy_scoring` (passive scoring + leaderboard) → `ranks.rank_sets`
(publish/adopt, free only) → `marketplace.publisher_sets` (lanes 1–2) →
`marketplace.contributor_sales` (lane 3) → `marketplace.cash_payouts` (Stripe
Connect rung). Manual grants (foundation §3) can comp any rank set.

## Build assessment (what exists vs net-new)

| Piece | Status |
|---|---|
| Per-user Elo boards, format-aware | EXISTS (`member_rankings`) |
| Seeding from external values | EXISTS (`seed_ratings` in ranking engine) |
| Rank→Elo mapping | EXISTS (reorder save path, `valueForElo`) |
| Board editing UI | EXISTS (Overall Ranks drag/jump) |
| Entitlements/IAP/credits plumbing | FOUNDATION DOC (monetization build) |
| `rank_sets`, `rank_set_entries`, `rank_set_adoptions`, `accuracy_scores`, `credit_ledger` tables | NET-NEW |
| Snapshot + quarterly scoring cron | NET-NEW (batch; outcome data source needed — weekly player points ingestion is the one real new data dependency) |
| Contributor role + profile + dashboard | NET-NEW |
| Marketplace browse/preview/adopt UI | NET-NEW |
| Publisher CSV ingestion + linking codes | NET-NEW (small) |
| Stripe Connect payouts | NET-NEW (deferred rung) |

Sizing (assumption-labeled): accuracy engine + leaderboard ≈ M; rank-set
publish/adopt ≈ M; marketplace commerce on top of the monetization foundation ≈ M;
payouts ≈ S–M. Nothing here blocks the five launch plans; this is the Phase-2
differentiator that gets *stronger* the longer scoring runs.

## Phasing (season-aligned)

1. **2026 season (passive):** ship `ranks.accuracy_scoring` dark→on. Snapshot all
   user boards quarterly; ingest weekly points; publish methodology page. Zero
   commerce. Output: by March 2027, every user and any recruited publisher has 2+
   scored windows — the minimum-sample gate is satisfiable.
2. **Rookie-draft window 2027:** `ranks.rank_sets` — free publish/adopt +
   leaderboard launch ("Dynasty's first accuracy contest") as the acquisition
   event; recruit publishers on exposure (FantasyPros playbook) + open DLF deal
   talks (linking first).
3. **Summer 2027:** `marketplace.publisher_sets` — DLF linking + first IAP sets
   (PlayerProfiler or FantasyPros-consensus).
4. **2027 season:** `marketplace.contributor_sales` — credits commerce for badged
   users; Dabble-style micro-reward experiment (small credit grant per adoption)
   as the A/B against pure sales.
5. **2028:** `marketplace.cash_payouts` once >~10 contributors cross the ladder
   threshold.
6. **Platform-thesis test — best ball, spring 2027 (parallel to phase 2–3):**
   accept `bestball` rank sets and score them across the Apr–Aug window against
   realized best-ball outcomes + ADP drift. Cheap validation of "accuracy engine
   as the real value prop": if best-ball boards + the Underdog affiliate placement
   convert, formats become the roadmap axis; if not, dynasty depth stays the
   focus. `redraft` sets follow only after the accuracy brand exists (FantasyPros'
   home turf — enter from strength, not first).

## Revenue math (all assumed; labeled)

At 5k users in the 2027 season: publisher sets — 5% attach at $7.99 avg ≈ $2k
gross/season (FTF ~30–40% net of Apple+share ≈ $600–800); contributor sets — 3%
of users buy ≥1 set at ~$5 avg ≈ $750 gross, FTF 30% ≈ $225/season; linking bounty
value + churn-benefit is non-cash but drives the DLF co-marketing channel. Direct
revenue is modest at this scale — **the primary returns are acquisition (the
accuracy contest is a marketing event), retention (adopted boards + contest
standing), and moat (scored-history data nobody can replicate quickly)**. The
marketplace becomes real money only at 20k+ users; build it for the moat, price it
to not be embarrassing.

## Risks

- **Outcome-data dependency:** weekly player points ingestion is new
  infrastructure and must be reliable for scoring credibility (mitigate: single
  stats source, backfillable, scoring is quarterly not real-time).
- **Thin early leaderboards** could embarrass ("top 10%" of 40 users): hold
  badges until population thresholds, show percentile only above N=200 scored.
- **Publisher channel conflict:** Nerds/PlayerProfiler sell competing trade
  tools; scope deals to rankings, expect Nerds to decline.
- **Apple UGC review risk:** credits + UGC moderation duties (guideline 1.2) —
  rank sets are low-toxicity UGC but need report/remove plumbing.
- **Gaming the contest:** burner boards, copy-the-consensus strategies (peer-
  relative scoring largely neutralizes copying — you can't beat peers by matching
  them; min-sample + one-scored-board-per-account for the rest).
- **Cold-start chicken/egg:** solved by sequencing — scoring is valuable to every
  user before any seller exists.

## Decisions needed (operator calls, each with a recommendation)

1. **Green-light Phase 1 (passive scoring) for this season?** Recommend yes —
   it's the long-lead item, cheap, and pure upside for engagement even if the
   marketplace never ships. Needs the weekly-points ingestion decision (source).
2. **Credits vs fixed-price SKUs for contributor sets?** Recommend credits
   (Apple-proof dynamic pricing + micro-rewards + payout ladder).
3. **Take rate 30%?** Recommend yes (rationale above); publishers negotiated
   separately at 60–70% to them.
4. **First publisher call:** DLF linking-first. Recommend opening after FTF has
   its public launch + the leaderboard date ("we're building dynasty's accuracy
   contest" is the pitch that makes FTF look like a channel, not a supplicant).
5. **Score all users passively by default** (opt-out) vs opt-in? Recommend
   passive-by-default with leaderboard display opt-in — scoring everyone is what
   makes the contest instantly deep; displaying is the consent moment.
6. **Commit to the format-agnostic schema (`set_type` + pluggable benchmarks)
   now?** Recommend yes — it's a schema shape, near-zero incremental cost, and
   the platform thesis is untestable without it. The *product* commitments
   (redraft, best ball) stay separately flagged and separately decided.
7. **Best-ball thesis test in spring 2027?** Recommend yes, scoped to scoring +
   the existing Underdog placement (no new draft tooling) — it reuses the
   pipeline and the affiliate lane, and its result decides whether formats or
   dynasty depth is the 2028 roadmap axis.

## Handoffs

- **an-data-architect:** weekly player-points ingestion spec + `accuracy_scores`
  / snapshot schema; leaderboard metrics events.
- **eng-backend:** rank-set tables + snapshot cron + scoring job (after PRD).
- **pm-partnerships / mkt-partners:** DLF + PlayerProfiler outreach sequencing
  (hold until launch + leaderboard date exist).
- **legal-privacy:** contributor terms (content license, earnings terms, W-9/tax
  language), credits terms (non-cashable disclosure), UGC moderation policy.
- **fin-forecast:** credits liability accounting (unredeemed credits are a
  liability line).
- **dual-agent-doc-review / PRD pipeline:** full PRD/HLD/LLD bundle in
  `docs/plans/monetization/rankings-marketplace/` on green-light, referencing the
  [platform foundation](../../plans/monetization/00-platform-foundation.md).
