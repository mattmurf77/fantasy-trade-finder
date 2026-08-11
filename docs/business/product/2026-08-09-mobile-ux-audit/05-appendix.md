# Appendix — Everything Reviewed Beyond the UX, and What It Contributed

> You asked me to summarize all the additional material I pulled in beyond the screens themselves. This is that record, plus a reconciliation against your existing internal audit.

---

## 1. Backend code — what it changed about the grades

Reading the server was not optional. Six of the nine launch blockers are only visible from the backend, or only *bounded* by it.

| Source | What it contributed |
|---|---|
| `backend/server.py` (20,915 lines) | The unlock branch logic (`:6154-6188`) that produced **P0-1** — the single most consequential finding. Also the verification gate at `:12197` that **disproved** my own Sleeper-write launch-blocker theory; the share-landing and OG routes (`:16633-16787`) that turned out to have zero callers; `_compute_invite_impact` returning `float(joined)` as a "k_factor"; the 12 push kinds with their caps and dedup; and the server-side `record_event` calls that corrected my "analytics are blind" claim. |
| `backend/ranking_service.py` | `POSITION_THRESHOLDS` (10 per position) and `_trade_unlocked`; the Elo update rule (K=32) and trio decomposition; `apply_anchor` **not** touching `_interactions`, which is why Pick Anchors can never unlock. |
| `backend/trade_service.py` | The two-board branch at `:3017` and dual-surplus gate at `:3518-3520` — the mechanism that is the app's only real moat; the harmonic-mean ranking; the fairness/junk-filler/pick-churn gates; and the docstring admitting package math is "inspired by KeepTradeCut's reverse-engineered raw adjustment." |
| `backend/feature_flags.py` | That undeclared flags default to `False`, and that `FLAG_KEYS` and `features.json` currently match 1:1. |
| `backend/database.py` (via git) | `get_ranking_method` returning `None` when unset — the fact that confirmed P0-1 rather than leaving it a strong hypothesis. |
| `config/features.json` | The authoritative flag ledger: **154 flags, 98 on, 56 off.** Every "is this actually live?" judgment in the audit traces here. |
| `mobile/app.json` | The `associatedDomains` entitlement that reversed the July teardown's universal-links finding. |

---

## 2. Competitive material

Twelve competitors appear across your internal docs. I used them to grade the Competition criterion and to sanity-check claims of uniqueness.

**Teardowns read:** RosterAudit and Angle Ranks (2026-07-20), DynastyGM and DynastyDealer/DTF (2026-07-26), the web-tools sweep covering FantasyCalc, Dynasty Daddy, DynastyTradeCalculator, FPTrack and Dynasty Dealmaker (2026-06-10), TI-CALC (2026-07-09), plus `competitor-matrix.md` and the 92-item feature backlog.

**Visual reference:** 32 Dynasty Nerds web-app screenshots in `reference/dynasty-nerds-app/`, mapped screen-by-screen against FTF equivalents.

**What it changed.** Three things I would have graded differently without it:

- **FTF has no player detail page at all.** Every competitor has one; Dynasty Nerds' includes a value trend chart, a proprietary scouting radar, career stats and cross-league ownership. This moved from "nice-to-have" to a named P2 gap.
- **The mobile field is nearly empty.** KTC, FantasyCalc, Dynasty Daddy, RosterAudit and Angle Ranks are all **web-only**. Only DynastyGM and DynastyDealer have confirmed native iOS apps. That materially raises the Competition grade on several screens — FTF is competing in a category whose leaders have no app.
- **Pricing is a barbell.** Free crowdsourced tools versus $70–120/yr bundles, with $30–50/yr described as an empty middle band. FTF currently charges nothing and has no paywall UI, no purchases SDK in `package.json`, and all eight `monetize.*` flags off — monetization is not a flag-flip away.

**One caution.** No internal doc contains competitor scale data — no downloads, ratings volume, or traffic for any competitor except RosterAudit's 611,759 trades. Every teardown defers this to a market analysis that hasn't run. I have not treated any competitor as large or small.

---

## 3. Growth, retention and analytics strategy docs

**Read:** the 2026-08-08 growth-loop strategy, the 2026-07-17 monetization brainstorm and research appendix, the analytics program plan, the tracking plan v2, the PFO measurement spec, the onboarding-conversion plan, the email-capture spec, the ASO reference, and the audience/persona register.

**What it contributed.**

- **The production reality that anchors the whole audit:** 16 users, 7 leagues, **one non-test user with a real board, zero captured trades.** This is why I graded the moat as unproven rather than strong — the mutual-gain engine is coded and has essentially never executed.
- **A confirmed conflict between two of your own docs.** The monetization plan (2026-07-17) says instrument for k ≈ 0.2–0.5. The growth strategy (2026-08-08) cites a measured average of **k ≈ 0.0494 across 400 programs** and explicitly rejects the optimistic benchmark genre. Three weeks apart, unreconciled.
- **Three different north-star metrics** defined in three same-week documents — Weekly Active Traders, Time-to-First-Value, and time-to-first-card under 60s — none cross-referencing the others. Also three activation definitions.
- **The seasonality picture:** dynasty interest is bimodal, peaking in May and again Aug 23–Sep 3, troughing Feb–Mar. Against that, the **only calendar-aware mechanism in the entire codebase is a `season_start` push hardcoded to Aug 25.** That's 16 days from this audit and the single cheapest retention lever available.
- **The ASO naming problem**, which I've left out of the backlog as a business decision rather than a product one: your App Store name is "DTF - Dynasty Trade Finder," a search for "DTF" returns ten hookup apps and zero sports results, and an unrelated competitor is also abbreviated DTF in your own docs.
- **Persona guidance that shaped how I graded onboarding:** dynasty players skew *younger* than assumed (25–34), and the named tension — one persona wants hand-holding, another finds it insulting — is exactly why "quiet by default, deep on demand" is the right call and why the current all-off state isn't it.

---

## 4. Architecture and decision records

**Read:** ADR-002 through ADR-008, the trade-engine deep dive and external research, the account-auth plan, the multi-platform linking plan, the Sleeper write capture runbook, `config-reference.md`, `api-reference.md`, and `data-dictionary.md`.

**What it contributed.** The dependency finding, which is the most uncomfortable item in the audit and doesn't fit neatly in any screen brief:

> **Every rankable player in FTF is gated on having a DynastyProcess value** (`server.py:1332-1335`). Seed Elo derives from DynastyProcess consensus (ADR-002). The player-ID crosswalk is DynastyProcess's `db_playerids.csv`. The package and fairness math shapes are explicitly adapted from KeepTradeCut and FantasyCalc.

Your values are not independently derived — they are seeded, calibrated and cross-walked from a third-party aggregator, with math shaped by two direct competitors. What FTF adds on top (personal Elo divergence, two-board matching) is real and is the product. But RosterAudit's marketing attack on poll-derived values lands on your seed too, and your own competitor matrix already names this as "FTF's credibility gap."

Also from this set: the Sleeper write path is documented as ToS-adverse and default-off across four separate documents, while `config/features.json` has it **on**.

---

## 5. QA, test and process material

**Read:** all 26 Maestro flows, `qa/teardown-remediation-qa.md`, the mobile test-case plan, and the branch triage.

**What it contributed.** The coverage gaps that inform launch risk:

- **No Maestro flow exists for** Settings, Profile, Feedback Inbox, Test Stages, Pick Assignment, Mock Draft, or Record Picks. Three of those ship flag-on.
- **No flow exercises the League Rankings chart's interactive surface at all** — no basis toggle, subset control, position filter, or drill-in.
- The trades smoke flows assert against `trades.subnav.calculator` and the classic empty state, which `trades.finder_hub: true` suppresses. They may be testing a layout users don't see. I could not resolve this — the referenced `release.json` flag fixture wasn't in the pinned snapshot.
- `qa/teardown-remediation-qa.md` shows **device-QA pending on essentially all 32 rows** of the July remediation wave. Those fixes are built and flag-on but largely unverified on hardware.

---

## 6. Reconciliation with your July internal teardown

Your existing audit (`app-teardown-review/`, 2026-07-19, gitignored, overall **B−**) graded against an iPhone platform-UX methodology. Mine graded against adoption, retention, moat and growth. Different rubrics, so the grades aren't directly comparable — but the overlap is informative.

**Where we agree.**
- *Navigation breaks platform contracts* (they graded IA a C). I found the same class of problem from a different angle: the Rank tab's destination, the League/League-Rankings collision, "Acquire" as invented vocabulary.
- *Dark-flag debt.* They named it as a cross-cutting pattern and warned that 30 new dark flags would become a graveyard without quarterly review. That review was due 2026-10. My audit found 56 dark flags including every growth and monetization surface — the prediction held.
- *Disclosure drift* — "the app's behavior is consistently better than its documents." I found the inverse case too: `trade.send_in_sleeper` is documented off and shipped on.

**Where I diverge.**
- **Universal links.** They found these couldn't fire and that the share loop terminated in Safari. That's now fixed — entitlement and AASA are both in place. But the loop still terminates, for a different reason: the links have no path to resolve.
- **Monetization graded B+.** They graded it as *readiness* (nothing shipped, readiness high). Against an adoption lens I graded it lower, because "no paywall, no SDK, no UI" is further from revenue than "readiness" suggests.

**What their rubric structurally couldn't see** — and why this audit was worth running separately:
- The **unlock coherence break**. It's a progression-logic defect, not a platform-UX one, and it silently disables push permission.
- The **growth loops built and unconnected**. A platform-UX rubric has no category for "the server route exists and nothing calls it."
- The **replicability picture** — that one mechanism is defensible and it has never run.
- The **competitive position**, which requires outside comparison their methodology didn't include.

**One process note.** That audit is gitignored and exists on one machine. It's the most valuable product artifact in the repository and it is one disk failure from gone. This audit is committed; that one should be too, or at least its report card and PRD index.

---

## 7. What I could not determine

Recorded so nothing here reads as more certain than it is.

1. Whether `web/` parses the `?league=` invite parameter and completes that journey server-side. Out of scope, and it partially bounds P0-3.
2. Whether the launch flag configuration matches `config/features.json`. Experiment overlays can differ per device, which affects P0-8 and every "this is dark" claim.
3. Whether the AASA Team ID matches `eas.json` — that file wasn't in the pinned snapshot.
4. The exact mirror-matching algorithm in `check_for_match` — `database.py` was outside most agents' snapshot, so the Matches mechanic is traced through call contracts.
5. Production error rates for `/api/trades/generate`, which bound the severity of P0-2.
6. Whether the Maestro smoke flows run against a different flag fixture than the shipped default.

---

## 8. Source count

**Code:** 30 screens, 68 components, 4 backend modules, the flag config, the app manifest, and 26 Maestro flows, all at pinned `origin/main @ 72a0770`.
**Documents:** 38 internal docs across competitive intelligence, growth and monetization strategy, analytics and measurement specs, ADRs and architecture references, QA ledgers, and living-memory state.
**Visual reference:** 32 competitor screenshots.
**Agents:** 9 Sonnet evidence-gatherers, ~1.9M subagent tokens, 373 tool calls. All grading by one reviewer.
