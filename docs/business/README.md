# FTF Company Roster — role skills index

Fantasy Trade Finder is run as a one-person company through role skills in
`.claude/skills/`. Each role is invoked as `/<name>`, grounds itself in
[context.md](context.md), saves deliverables to `docs/business/<dept>/`, and ends every
deliverable with **Decisions needed** + **Handoffs**. Buildable product work routes
through the `/feedback` pipeline (the E2E feature-builder loop) or an eng-* skill.

## Marketing

| Skill | Role | Call it for |
|---|---|---|
| `/mkt-brand` | Brand marketer | Positioning, messaging house, voice, naming, launch story |
| `/mkt-seo` | SEO lead | Keywords, on-page/technical SEO for `web/`, content plan, backlinks |
| `/mkt-partners` | Partner marketer | Podcasts/creators/Reddit/Discord outreach, promo codes, pipeline |
| `/mkt-aso` | ASO specialist | App Store listing, keywords, screenshots, ratings/review strategy |
| `/mkt-lifecycle` | Lifecycle/CRM marketer | Push/email touch map, onboarding sequence, win-back, offseason drip |
| `/mkt-adops` | Ad-ops specialist | Ad networks, placements, ATT, eCPM (activates if ads route chosen) |
| `/mkt-content` | Content strategist | Content calendar, briefs, formats, distribution plan |
| `/mkt-writer` | Content writer | The actual words: articles, App Store copy, push/email copy |

## Analytics

| Skill | Role | Call it for |
|---|---|---|
| `/an-user-data` | User data analyst | Real numbers from the DB, feedback mining, TestFlight stats |
| `/an-market` | Macro/competitive analyst | Market size, competitor scale, seasonality, cited benchmarks |
| `/an-funnel` | Funnel metrics owner | Metric definitions, funnel stages, KPIs, north star, dashboards |
| `/an-data-architect` | Data architect | Event taxonomy, tracking plan, analytics storage, PII rules |
| `/an-experiment` | Experimentation front door | Hypothesis→spec, power/duration calc, launch/monitor/decide via the experiment engine |

## Engineering

| Skill | Role | Call it for |
|---|---|---|
| `/eng-web` | Front-end web engineer | `web/` features/fixes, SEO implementation, web performance |
| `/eng-backend` | Back-end engineer | Flask routes, ranking/trade engine, schema, entitlements |
| `/eng-mobile` | Mobile engineer | Screens, EAS/TestFlight builds, version bumps, StoreKit/ATT |
| `/eng-integrations` | External services engineer | Sleeper/Anthropic APIs, Render, future SDKs (RevenueCat, AdMob) |
| `/eng-qa` | QA engineer | Maestro flows, regression passes, smoke tests, "safe to ship?" |
| `/eng-architect` | Software architect | Cross-cutting design, ADRs, Postgres path, tech-debt register |
| `/eng-security` | Security engineer | Auth/secrets/endpoint audits, dependency scans, pre-launch hardening |

## Product management

| Skill | Role | Call it for |
|---|---|---|
| `/pm-growth` | Growth PM | Acquisition, league viral loop, referrals, launch sequencing |
| `/pm-retention` | Retention PM | Engagement loops, churn, notifications, offseason retention |
| `/pm-technical` | Technical PM | PRDs/specs, unified backlog, prioritization, sequencing |
| `/pm-monetization` | Monetization PM | Pricing, packaging, paywalls, subs vs ads, IAP compliance |
| `/pm-partnerships` | Partnerships/BD PM | Sleeper dependency, platform hedge, data deals, build-vs-partner |
| `/pm-pfo` | PFO PM | Core-loop audits, time-to-first-value, suggestion quality |
| `/pm-competitor` | Competitor specialist | Teardowns, feature-gap matrix, pricing intel |

## Design & research

| Skill | Role | Call it for |
|---|---|---|
| `/ux-design` | UX/product designer | Flows, wireframes, interaction specs, states, design critique |
| `/ux-research` | UX researcher | Usability tests, interviews, feedback mining, personas |

## Operations & legal

| Skill | Role | Call it for |
|---|---|---|
| `/ops-support` | Support & community | Tester/user replies, support macros, review responses, community presence |
| `/ops-release` | Release manager | Ship checklist, TestFlight/App Store submission, rollout, rollback, release log |
| `/legal-privacy` | Legal & privacy officer | Privacy policy, ToS, App Store privacy labels, ATT, account deletion |

## Finance

| Skill | Role | Call it for |
|---|---|---|
| `/fin-budget` | Budget owner | Cost ledger, burn, spend approvals, cost-creep watch |
| `/fin-forecast` | Forecasting analyst | Revenue scenarios, break-even, sensitivity, what-ifs |
| `/fin-pnl` | P&L owner | Monthly P&L, platform cuts, unit economics, margins |

## How the roster works together

Typical flows:

- **Monetization decision**: `/pm-competitor` (pricing intel) → `/pm-monetization`
  (packaging recommendation) → `/fin-forecast` (scenario math) → `/pm-technical`
  (PRD) → `/feedback` pipeline (build) → `/eng-qa` (regression) → `/fin-pnl` (results).
- **Public launch**: `/pm-pfo` (core-loop audit) → `/eng-security` (pre-launch audit)
  → `/legal-privacy` (policy, privacy labels, account deletion) → `/mkt-brand` +
  `/mkt-aso` (listing, copy via `/mkt-writer`) → `/ops-release` (ship checklist +
  submission) → `/pm-growth` (sequencing) → `/mkt-partners` + `/mkt-content` (push)
  → `/an-funnel` + `/an-data-architect` (measure it).
- **New screen/feature UX**: `/ux-research` (what users struggle with) → `/ux-design`
  (flows + specs) → `/pm-technical` (PRD) → `/feedback` pipeline → `/eng-qa` →
  `/ops-release`.
- **Monthly rhythm**: `/an-user-data` (what happened) → `/an-funnel` (metrics review)
  → `/fin-budget` (burn) → `/fin-pnl` (close).

Standing docs (updated in place, not dated): `finance/cost-ledger.md`,
`finance/pnl-YYYY-MM.md`, `product/competitor-matrix.md`, `ops/support-macros.md`,
`ops/release-log.md`.
