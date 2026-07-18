# Render Paid Tier — Keep-Warm Cost Memo

**Role:** fin-budget · **Date:** 2026-07-17 · **Status:** Decision memo (decision owner: operator)
**Context:** onboarding redesign item 3 (keep-warm); growth review of the <60s time-to-first-trade-card north star.

## Problem

Prod runs on Render's free web-service tier, which idles the container after ~15 min without traffic. The next request pays a **30–60s cold start** — by itself enough to blow the onboarding north star of **<60s from install to first trade card**. Any new user who arrives at an idle server starts their first session staring at a spinner.

## Options

**A. Keep-warm cron (this change) — $0/mo, best-effort.**
`.github/workflows/keep-warm.yml` pings `GET /api/feature-flags` every 10 minutes so the dyno ~never idles out. Free, shipped, reversible (disable the workflow in the GitHub Actions UI). Limits: GitHub cron drifts/skips under load and auto-disables after 60 days of repo inactivity, so occasional cold starts will still leak through — this is warming that usually works, not an SLA. Also spends free-tier instance hours continuously (fine at current scale; monitor if Render meters harder).

**B. Render paid tier — ~$7/mo (Starter; assumed, verify at render.com), always-on.**
No instance sleep, so cold starts disappear entirely and the north star stops depending on a third-party scheduler. Also buys headroom (more RAM/CPU) ahead of launch traffic. Cost is trivial in absolute terms but is the project's first recurring infra spend.

## Recommendation (from the growth review)

Paid tier is a **recommended conversion expense** — a reliably warm first session protects the exact moment we convert a curious installer into an activated user, and $7/mo is cheap against that. But it is **non-blocking**: keep-warm (option A) plus onboarding UX masking of any residual cold start must stand on their own regardless, both because best-effort warming leaks and because the paid tier can lapse. Ship A now; adopt B when the operator is ready to take on recurring spend (suggested trigger: TestFlight → public beta, or first observed cold-start complaint from a real onboarding session).

## Decisions needed

1. Adopt Render Starter (~$7/mo, verify current price at render.com) now, at public beta, or defer — **operator**.

## Handoffs

- If B adopted: plan change is a Render dashboard toggle (`render.yaml` `plan: free` → paid) → eng-integrations; then optionally disable the keep-warm workflow.
- Recurring-spend line item once adopted → fin-pnl.
