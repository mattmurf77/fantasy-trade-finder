# Standing docs — templates

Two docs live in `docs/business/product/` and are **carried forward every run**, the way
`/pm-competitor` carries `competitor-matrix.md`. Read both before you start; update the
rows your run touched; add one dated changelog line to each doc you changed. If a doc
doesn't exist on `origin/main` yet, check open branches first (another worker may be
writing it), then create it from the template below in your own worktree.

Rules for both:
- **One row per thing**, updated in place. Never delete a row; set its status to
  `killed` or `done` with a one-line reason and the date.
- **Every number is labeled** `measured` (query, source, time; prod numbers come only via
  `analytics-lead`), `benchmarked` (cited source + check date), or `assumed`.
- **Owner seam** names an org box (`engagement-pm`, `onboarding-pm`, `marketing-lead`,
  `monetization-pm`, `analytics-lead`, `platforms-pm`), never a retired skill.
- **Status** is one of: `idea` → `specced` (PRD + scope block exist) → `in build` →
  `in test` → `read out` → `done` / `killed` / `parked`.

---

## `docs/business/product/growth-backlog.md`

```markdown
# Growth backlog

> Standing doc held by `growth-pm` (charter `/pm-growth`). One row per loop idea or
> growth bet, ranked. Updated in place every `/pm-growth` run; history in the changelog.
> Rows feed PRDs through `head-product`; experiments launch only through
> `analytics-lead` on the operator's go.

**Last updated:** YYYY-MM-DD at `origin/main` <sha>

## Ranked backlog

| Rank | ID | Loop / idea | Hypothesis | Cheapest test | Success criterion (number) | Power pre-check | Owner seam | Status | Evidence / links |
|---|---|---|---|---|---|---|---|---|---|
| 1 | GB-01 | e.g. Invite → join | If the invite link lands a non-user on <X> instead of `/`, then invites → joins rises, because <mechanism> | e.g. operator TestFlight checklist + 2-week read of `invite_link_opened` / joins | e.g. joins per `invite_shared` ≥ 0.15 over 4 weeks (assumed baseline 0.05) | pending / `analytics-lead` YYYY-MM-DD: n/arm, weeks, MDE at 2/4/8 wks; "underpowered → descriptive read only" | decides: `growth-pm`; builds: `engagement-eng`; words: `marketing-lead` | idea | memo YYYY-MM-DD; loop audit hop H3 |

### Column rules
- **Hypothesis:** "If <change>, then <metric> moves <direction>, because <mechanism>."
- **Cheapest test:** the smallest thing that could kill the idea: a fake-door, a
  descriptive read, a 5-user leaguemate check, an `/an-experiment` spec. A full build
  is never the cheapest test.
- **Success criterion:** one metric, one number, one window, plus its baseline and the
  baseline's label. No number means the row stays `idea`.
- **Power pre-check:** a request to `analytics-lead`, who runs `/an-experiment`'s
  `POST /api/admin/experiments/preview` (baseline_rate, mde, variants,
  eligible_per_week; `growth` layer). You never call it yourself. If it needs more than
  26 weeks, the row says so and names the alternative (bigger swing, coarser metric,
  descriptive read).
- **Owner seam:** who decides / builds / writes the words / owns the entry point.

## Killed and parked
| ID | Idea | Status | Date | Why |
|---|---|---|---|---|

## Changelog
- YYYY-MM-DD — <what changed and why> (`/pm-growth`, <deliverable link>)
```

---

## `docs/business/product/acquisition-portfolio.md`

```markdown
# Acquisition portfolio

> Standing doc held by `growth-pm`. Which channels, in what order, and why. Channel
> execution belongs to `marketing-lead`; this doc owns the order and the evidence bar.
> Refresh before every season ramp (July–Aug is the prize; rookie draft late Apr–May)
> and before any public-launch decision.

**Last updated:** YYYY-MM-DD at `origin/main` <sha>

## Portfolio

<!-- Seed rows reflect the surface as of 2026-10-15 (see the skill's
     references/growth-surface.md). Verify every cell before carrying it forward. -->

| Channel | Funnel stage it feeds | Cost (cash / effort) | Owner | Status | Evidence | Next step |
|---|---|---|---|---|---|---|
| In-league invite (invite card, banner, bell empty state) | non-user → install/join | $0 / built | decides `growth-pm`; entry points `engagement-pm` | live | `invite_shared` → `invite_link_opened` (measured, via `analytics-lead`, query + date) | loop audit GB-01 |
| Share landings (`/s/*`) | non-user → landing | $0 / built | decides `growth-pm`; builds `engagement-eng` | live, CTA → `/` | … | … |
| Send-to-league offers seen by leaguemates | non-user → awareness | $0 / built | `trades-pm` card, `platforms-pm` write | live | … | … |
| App Store search (ASO) | search → install | $0 / listing | `marketing-lead` (`mkt-aso`) | blocked: no listing | … | launch readiness |
| Organic web / SEO | search → landing | $0 / content | `marketing-lead` (`mkt-seo`) | … | … | … |
| Creators / partners | audience → landing | $ / deals | `marketing-lead` (`mkt-partners`); spend via `head-bizops` | … | … | … |
| Paid | … | $ | `head-bizops` approves spend first | not started | — | — |

### Column rules
- **Funnel stage** uses the adopted funnel (`docs/business/context.md` § Funnel): stage 0
  first open → sign-in → league sync → … → WAT.
- **Cost:** cash and effort, each labeled. Any cash row goes to `head-bizops` (worker
  `fin-pnl`) before it's recommended.
- **Status:** `not started` / `blocked: <by what>` / `testing` / `live` / `killed`.
- **Evidence:** measured / benchmarked / assumed, cited. Attribution needs the UTM /
  install-source convention (`analytics-lead`); until it exists, channel numbers
  can't be separated and the row says so.

## Order and why
1. <channel> — <one-line reason, tied to seasonality and evidence>

## Changelog
- YYYY-MM-DD — <what changed and why>
```
