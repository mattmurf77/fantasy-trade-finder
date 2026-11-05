# Mode: launch readiness

**Use when:** sequencing the first public App Store release (TestFlight → App Store), a
per-season relaunch push, or any time someone asks "can we launch?".
**Output:** one checklist (gates × owner × evidence × status) plus a go/no-go
recommendation. Run it again at each state change; the latest dated run is the one that
counts.

`growth-pm` **holds the gate list** (decides which gates exist and sequences them). Each
gate's owner holds its evidence. Go/no-go goes up the chain (`head-product` → the
operator); you recommend, never decide. `release-lead` runs submission and freezes the
list at submission.

**File home is pending.** `head-product` decision P19 leaves the checklist's home to
`head-bizops`, because NEXT.md's "First public App Store release" item points into
`docs/business/ops/` (a `head-bizops` folder) at a checklist that doesn't exist. Until
`head-bizops` decides, put the checklist in your dated deliverable
(`docs/business/product/YYYY-MM-DD-launch-readiness.md`), list the home as a Decision
needed, and don't create files in `docs/business/ops/`.

## Gates

| # | Gate | Owner (org box) | Evidence that passes it |
|---|---|---|---|
| G1 | **Core loop passes a `/pm-pfo` audit** (sign-in → board usable → first trade suggestion) | `head-product` → `onboarding-pm` + `trades-pm` (both chartered by `/pm-pfo`) | Dated audit with a pass verdict and no open P0s. Launching into a broken first run wastes the window |
| G2 | **Pre-launch security audit** | `head-eng` → `eng-security` | Audit doc; no open critical or high findings |
| G3 | **Privacy policy, App Store privacy labels, account deletion** | Legal owner under `head-bizops`. **`legal-privacy` is retired: name this gap, don't route to it.** Restoring it is the operator's call through `head-bizops` | `web/privacy.html` matches what is collected (`analytics-lead`'s data-collected inventory); label answers drafted; deletion path documented |
| G4 | **Store listing** (name per D-057, subtitle, keywords, screenshots from a current build, description) | `marketing-lead` (`mkt-aso` drafts); proposed home `docs/business/marketing/app-store-listing.md`, frozen by `release-lead` at submission | Listing doc complete; App Store Connect entry only on the operator's go |
| G5 | **Public URL and CTAs**: an App Store or public TestFlight URL exists, and the web landing CTA and every `/s/*` CTA point to it | Decides `growth-pm` (target is an operator call until a listing exists); builds `onboarding-eng` (`web/`) and `engagement-eng` (`/s/*`) | The `cta_url=` grep in `growth-surface.md` §1 shows no dead-end `/`; landing waiver W6 closed |
| G6 | **AASA / universal-link validation** (and `growth.invite_join_link` graduation) | Builds `engagement-eng`; flag flip `release-lead` on the operator's go | External AASA validator output plus an operator device check (`docs/runbook.md` § AASA; D-028) |
| G7 | **Install-source / UTM convention** | `analytics-lead` (tracking-plan addendum, P18) | The addendum exists; landing, share and invite links carry it; a test install shows up attributed |
| G8 | **Measurement ready** | `analytics-lead` | Funnel stage 0 → activation renders real counts (`docs/business/context.md` § Funnel), so launch-week numbers can be measured |
| G9 | **Support macros** | `head-bizops` (`ops-support` worker; every outbound reply needs the operator) | Macro file exists and is current (ESPN and MFL are live) |
| G10 | **Custom domain** | Operator, through `head-bizops` / `marketing-lead` (D-057 lists it outstanding) | Registered; canonicals, sitemap and AASA served on it. A domain change touches G5 and G6, so sequence it before them |
| G11 | **Prod `CRON_SECRET`** | `release-lead` (Render config) through `head-eng` | Key is set in Render and isn't a dev value. Check the key name only; never print the value |
| G12 | **Seasonality window** | `growth-pm` | Target date sits ahead of a ramp (July–Aug; rookie draft late Apr–May), with App Review and listing lead time counted back from it |

Add a gate only with an owner and an evidence bar. A gate nobody owns gets named in
Decisions needed, not silently dropped.

## Procedure

1. Pin the sha. Re-run `growth-surface.md` §1; G5/G6 evidence comes straight from it.
2. For each gate, find the newest evidence (file + date) or mark it `open`. Don't
   accept a skill's existence as evidence; the evidence is the dated output.
3. Status per gate: `pass` (evidence linked), `open`, `fail` (evidence shows a blocker),
   `waived` (only by the operator, with the date and the reason).
4. Draw the critical path: which open gates block which (G10 → G5/G6; G4 → submission;
   G1 before any acquisition spend).
5. Recommend go / no-go / go-with-conditions, with the riskiest open gate and the date
   the window closes.
6. Route each open gate to its owner through `head-product` (the marketing and legal
   ones reach `head-bizops` through `head-product`).

## Output format

```markdown
# Launch readiness — YYYY-MM-DD (origin/main <sha>)

**Target window:** … · **Recommendation:** go / no-go / go with conditions

| # | Gate | Owner | Evidence (link + date) | Status | Blocks |
|---|---|---|---|---|---|
| G1 | … | … | … | open / pass / fail / waived (operator, date) | … |

## Critical path
## Riskiest open gate
## Decisions needed
(always includes the checklist's file home until head-bizops decides it)
## Handoffs
```
