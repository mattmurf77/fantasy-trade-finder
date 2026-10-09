# Competitor feature-gap matrix (standing doc)

> Owner role: pm-competitor. One row per capability, one column per competitor, cells = has / partial / lacks / queued (Fleeced planned) with a citation. Compare Fleeced *as flagged on today*. Update the changelog line every run.

**Changelog:** 2026-10-09 — created with Dynasty Trade Lab + Fleeced columns from the [DTL teardown](2026-10-09-dynastytradelab-teardown/teardown.md). Earlier teardowns (DynastyGM 2026-07-26, DynastyDealer/DTF 2026-07-26, RosterAudit/Angle Ranks 2026-07-20, web-tools sweep 2026-06-10) are not yet entered as columns — next run.

| Capability | Fleeced (2026-10-09) | Dynasty Trade Lab (2026-10-09) |
|---|---|---|
| Value source | has — personal Elo board + blended consensus seed; premium rank-set import | has — FantasyCalc chart (1QB + SF), daily refresh ([rankings](2026-10-09-dynastytradelab-teardown/evidence/rankings-page.md)) |
| Personalised values | has | lacks |
| Fairness test | has — band + stud tax + positional caps; value core queued (`trade.value_core` off) | partial — straight sum, filler allowed ([report](2026-10-09-dynastytradelab-teardown/evidence/trade-report-generated.md)) |
| Counterparty acceptance model | has — mutual-gain + bilateral preference-led construction | lacks — "🟢 Likely" label only |
| Manager-level needs list | partial — need fit per card | has — slot-level needs for every manager + WHO TO CALL ([account](2026-10-09-dynastytradelab-teardown/evidence/account-and-credits.md)) |
| Weekly value movers (league-scoped) | lacks | has — Player Stock Movement + Rising FA Stock ([dashboard](2026-10-09-dynastytradelab-teardown/evidence/dashboard-page.md)) |
| Draft picks | has — slot values, owned-pick sync, provenance | partial — round-level values; provenance shown in rosters |
| Three-team trades | queued (`trade.three_team` off) | has (toggle; unverified output) |
| AI chat over league data | lacks | has — Lab Analyst, credit-gated, snapshot-only ([chat](2026-10-09-dynastytradelab-teardown/evidence/lab-analyst-chat.md)) |
| Free-text trade constraints | lacks | has — TRADE PROMPT ([generator](2026-10-09-dynastytradelab-teardown/evidence/trade-generator-page.md)) |
| Platforms | has — Sleeper, ESPN, MFL (Fleaflicker dark) | partial — Sleeper, Fantrax |
| Send trade into the platform | has — Sleeper/ESPN/MFL | lacks |
| Mobile app | has — iOS (TestFlight) + web | lacks — responsive web only |
| Pricing | free today (`monetize.paywall` off) | credits: 10/$4.99 · 40/$17.99 · 75/$29.99, 5 free ([landing](2026-10-09-dynastytradelab-teardown/evidence/landing-and-stack.md)) |
| Engine self-evaluation | has — Calibration blind grading (`grading.blind` on) | lacks (none visible) |
