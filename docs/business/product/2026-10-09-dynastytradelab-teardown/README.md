# Dynasty Trade Lab (dynastytradelab.com) — competitor teardown

**Started:** 2026-10-09 · **Status:** hands-on teardown written; public-research section pending (workflow) · **Owner role:** pm-competitor

New entrant flagged by the operator 2026-10-09. Web-only (WordPress + custom plugin), Sleeper + Fantrax import, credit-priced ($4.99/10 · $17.99/40 · $29.99/75, 5 free), three headline features: Trade Generator (manual builder + "Find a Trade"), Lab Analyst (LLM chat over a per-request league snapshot), three-team trade finder.

## Contents

| File | What |
|---|---|
| [evidence/landing-and-stack.md](evidence/landing-and-stack.md) | Logged-out landing page copy, pricing, and the technical stack / REST surface |
| [evidence/trade-generator-page.md](evidence/trade-generator-page.md) | The Generator page as seen logged in (roster, pool, partners) |
| [evidence/dashboard-page.md](evidence/dashboard-page.md) | Dashboard: team status, needs engine, Lab Analyst panel, stock movers, FA risers, credit rules |
| [evidence/rankings-page.md](evidence/rankings-page.md) | Rankings table, 1QB/SF toggle, nav map |
| [evidence/account-and-credits.md](evidence/account-and-credits.md) | Buy Credits, My Trade Lab hub, all managers' needs, trade history, League Analysis, connect flow, scale signal |
| [evidence/trade-report-generated.md](evidence/trade-report-generated.md) | The operator's generated trade report — what a credit buys |
| [evidence/lab-analyst-chat.md](evidence/lab-analyst-chat.md) | Fifteen verbatim Lab Analyst replies (5 operator-driven, 10 agent-driven across 4 credits) with observations |
| [evidence/screens/](evidence/screens/) | Screenshots, numbered in walkthrough order |
| public-research.md | *(pending — workflow output: company, community, methodology claims, landscape, verified + cited)* |
| [teardown.md](teardown.md) | The deliverable: surfaces, how the engine works, pricing, quality findings, FTF gap table, recommendations by owner, open questions |

## Capture method (D-056 world: no simulator; this is a web product)

Operator logged in and ran the first flows by hand; the agent captured page text, screenshots and the front-end bundle's REST routes. Live request/response capture only works for actions the agent itself performs (the Chrome tool's network log does not record the operator's own clicks), so the credit-spending flows (generate, analyze, 3-team) are replayed by the agent in the hands-on phase and logged then.
