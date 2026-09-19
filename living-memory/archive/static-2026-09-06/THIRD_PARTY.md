# Third-Party Details — Fantasy Trade Finder

> **Purpose:** the business-flavored catalog of external entities this project depends on or references. Pricing, tiers, contacts, and operational implications. Where [`DEPENDENCIES.md`](DEPENDENCIES.md) catalogs technical quirks, THIRD_PARTY asks "what's it costing us and who do we call when it dies?"
>
> **Read at:** before adopting a new vendor or integration, before subscribing to a paid tier, before contract renewals.
> **Write at:** when vendor terms change, when a new vendor is adopted, when costs or limits shift.
>
> Companion files: [`DEPENDENCIES.md`](DEPENDENCIES.md), [`SOURCES.md`](SOURCES.md).

---

## Table of Contents
- [2026-05-21 — Vendor Inventory](#2026-05-21--vendor-inventory)
- [Cost Posture](#cost-posture)
- [Renewal / Review Cadence](#renewal--review-cadence)
- [Outstanding / Known Gaps](#outstanding--known-gaps)

---

## 2026-05-21 — Vendor Inventory

### Data providers

| Vendor | Role | Tier | Cost | Notes |
|---|---|---|---|---|
| **Sleeper** | Identity provider + league/roster/player data | Free public API; no key required | $0 | Sole identity provider for the app. If they paywall or rate-limit, the app breaks. |
| **DynastyProcess** | Initial Elo seeding from consensus dynasty values | Free CSV on GitHub | $0 | Community-maintained. Updates weekly during season. No SLA. |
| **Anthropic Claude API** | Smart matchup selection (optional) | Per-token pricing | ~$0.001 per matchup decision (Haiku); aggregate negligible at single-user scale | Optional — algorithmic fallback exists. `ANTHROPIC_API_KEY` env var required to enable. |

### Infrastructure

| Vendor | Role | Tier | Cost | Notes |
|---|---|---|---|---|
| **Local macOS + Python** | Dev execution | N/A | $0 | All dev runs locally. |
| **Render** *(planned)* | Production hosting | Free tier likely sufficient for personal use | $0 (free tier) or ~$7/mo (starter) | Config in `render.yaml`. Not yet deployed. |
| **PostgreSQL** *(planned)* | Production DB | Render-managed Postgres or external | TBD | SQLite is current; Postgres-swappable via `DATABASE_URL`. |

### Client distribution

| Vendor | Role | Tier | Cost | Notes |
|---|---|---|---|---|
| **Expo (EAS)** *(planned)* | Mobile app build/distribution | Free for dev; paid for production builds | $0 dev / $29/mo or per-build pricing for production | Not yet exercised. Dev currently uses Expo Go (free). |
| **Chrome Web Store** *(planned)* | Browser extension distribution | One-time $5 developer registration | $5 | Required for public extension distribution. Not yet submitted. |
| **Apple App Store** *(planned)* | iOS app distribution | $99/yr Apple Developer Program | $99/yr | Required for App Store distribution. Not committed. |
| **Google Play Store** *(planned)* | Android app distribution | $25 one-time | $25 | Required for Play Store distribution. Not committed. |

### Tools & libraries (zero-cost OSS — listed for completeness)

| Library | Role |
|---|---|
| Flask | Backend HTTP framework |
| SQLAlchemy Core | DB abstraction |
| pandas, numpy | Data manipulation (CSV ingest, Elo math) |
| anthropic (Python SDK) | Claude API client |
| Expo, React Native | Mobile client |
| Standard browser APIs | Web client (no framework) |

### Custom skills (in-repo, not third-party but worth listing)

| Skill | Source |
|---|---|
| `feature-evaluator.skill` | Built in-house; evaluates code across 7 dimensions |
| `project-reorganizer.skill` | Built in-house; reorganizes flat project structures |

---

## Cost Posture
- **Current monthly cost: ~$0.** All current dependencies free at personal-use scale.
- **If Anthropic Claude usage scales:** even at 1,000 matchup decisions/month, cost stays under $5.
- **If production launched:** estimated $7/mo (Render starter) + $99/yr (Apple) + $25 one-time (Play) + $5 one-time (Chrome) ≈ $150 first-year, ~$185/yr ongoing.
- **No vendor lock-in.** Sleeper is the one provider whose absence would break the app — but that's by design (Sleeper-first dynasty product).

## Renewal / Review Cadence
- **Pre-season:** verify DynastyProcess CSV is current; refresh Sleeper player cache.
- **Quarterly:** revisit this file for stale entries.
- **Before any production deployment:** confirm all "planned" vendors transition to "active."

---

## Outstanding / Known Gaps

- No formal vendor SLAs anywhere — relying on community/free-tier reliability.
- If/when productized for paying users, Sleeper API dependency becomes a risk — formal Sleeper partnership not pursued.
- DynastyProcess CSV has no maintenance commitment; if the project goes dark, we'd need an alternative initial-seed source.
