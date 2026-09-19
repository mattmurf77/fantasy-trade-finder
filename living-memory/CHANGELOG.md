# CHANGELOG

Ten recent outcomes; current release routing is in [HANDOFF](HANDOFF.md). Older entries are preserved in the [September 19 tail archive](archive/CHANGELOG-tail-preserved-2026-09-19.md) and [September 6 archive](archive/CHANGELOG-through-2026-09-06.md).

## 2026-09-19 — Organization publication refreshed against current main

Reconciled organization `801e00ea` with main `b33b4da9`, retained later implementation/evidence, restored compact memory and refreshed product/engineering routing. Publication and exact-head CI remain pending at this snapshot; no runtime or production changes are claimed. Private interviews and excluded worktrees remain outside this change.

## 2026-09-17 — Shared trade-significance implementation; activation separate

Raw-tier significance filtering, trusted exceptions and cache safety are present in the integrated source. The dated [validation](../docs/plans/trade-significance/validation.md) records 6,058 backend passes / one skip plus client checks; its pre-publication statements describe that earlier checkpoint. Mode defaults off. Calibration, hosted release evidence and activation remain separate gates; no live setting was verified by this organization task.

## 2026-09-16 — Diagnostic storage release and prevention recheck

[Release evidence](../docs/plans/db-storage-reduction/release.md) records PRs #293/#294, bounded shared diagnostic writes, 14-day debug retention, preserved core/outcome data, complete historical compaction and physical reclamation on September 15. The September 16 recheck found the expected writer live, retention active and health checks passing; no new records were available for a post-cleanup write sample. Capacity estimates are dated storage estimates, not concurrent-load limits.

## 2026-09-08c — Feedback batch (#422–#428) SHIPPED; backend live, iOS 1.17.3 building

**What:** five groups on `feat/feedback-2026-09-08`: Win Now refuses kicker/IDP lineups early with a specific sentence (#422, `unsupported_roster_slots` unchanged); the Acquire landing's outlook row reads the saved preference and Team Review completion is recorded on reaching the plan beat, shown live (#423/#424, D-191); the Team overhaul hero replaces the utility row's Draft cell (#425/#426, D-192, ice pending a red token decision); first-round picks exempt from the stud tax with knob `stud_tax_exempt_first_round` (#427, D-190); Sleeper pick sends refuse spent/out-of-window classes with Sleeper's own message and the sync excludes completed-draft seasons (#428, D-189; Q-037 closed). Mobile 1.17.3.
**Why:** operator triage 2026-09-08 ("handle all of the bugs", then "the polish items"); every item traced to a Render-log or public-Sleeper-API repro before planning.
**Evidence:** [TEST_LEDGER](TEST_LEDGER.md) 2026-09-08 batch entry; ten QA reports in the item folders; two convergent non-PRD findings caught by the redundant QA pairs and resolved (G-423 league switch, G-428 startup drafts).
**Shipped 2026-09-08 on operator go:** PR #292 squash-merged as `1371d2e5`; Render live 00:03:58Z with a clean smoke (the first-round rule confirmed on the live calculator: 4234.0 vs 4210.2 → even; seconds still taxed). iOS 1.17.3 (155) (EAS `c0fe6e0d`) uploaded to App Store Connect (submission `2742bdd6`). Items 422–428 set `fixed`. Branches/worktrees cleaned after a [recovery capture](../docs/recovery/2026-09-08-feedback-batch-422-428.md) with ancestry + complete-tree + owned-file proofs.
**Not done:** the operator's device checklist on 1.17.3; the hero stays ice pending a red design-system token.

## 2026-09-08b — Team overhaul: blank review chips and two crashes fixed (card shape)

**What:** overhaul offers now pass through the deck's `normalizeTradeCard` at the fetch boundary, so screens receive the client `TradeCard` shape; every overhaul screen guards its server-data reads. Fixes blank review chips and the crashes on "Build roadmaps" and roadmap selection reported on build 153.
**Why:** the server `card` is the raw `trade_card_to_dict` dict (`give`/`receive`); the screens read `give_players`/`receive_players`. The deck already had the adapter; the overhaul screens bypassed it.
**Evidence:** [TEST_LEDGER](TEST_LEDGER.md) 2026-09-08; guard at 26 assertions. Ships as iOS 1.17.2 (154).

## 2026-09-08 — Team overhaul flag ON in production (operator: "push the flag")

**What:** `overhaul.enabled` true on `main` (`d59a86d7`; `config/features.json` + the release fixture mirror). Production `GET /api/feature-flags` served it as true ~2 min after the push. The Acquire "Team overhaul" card and the create/generate/assemble/send routes are live for TestFlight testers on builds 151+ (all-platform sends need 152/153).
**Why:** the operator asked to see the feature on Acquire; D1 revised and D2–D9 confirmed on 2026-09-07. Rollback lever: flip the two files back to false.
**Evidence:** [TEST_LEDGER](TEST_LEDGER.md) 2026-09-08. Device checklist still unrun.

## 2026-09-07b — Team overhaul sends on MFL and ESPN (owner D1 revision) MERGED; iOS 152 and 153 uploaded

**What:** the owner confirmed D2–D9 and revised D1 to "should work for all". Overhaul sends now dispatch through per-platform propose cores (`_sleeper_propose_core`, new `_mfl_propose_core`, `_espn_propose_core`, all extracted verbatim from their routes); capabilities are per platform (`can_propose`, `can_propose_picks` false on ESPN, Sleeper tied offers `supported`); MFL/ESPN refresh reads fresh rosters and refuses to terminalize on stale data. Mobile copy is platform-aware. Owner record: [owner-decisions.md](../docs/plans/team-overhaul/owner-decisions.md).
**Evidence:** [TEST_LEDGER](TEST_LEDGER.md) same date: full suite 5863/1 skip, CI green, PR #290 squash-merged as `8cacc1f2` (Render deploys). iOS 1.17.2 (152) and (153) both uploaded to App Store Connect from the identical tree (152 via an accidental submit that completed server-side, 153 via auto-submit; see TEST_LEDGER). The `overhaul.enabled` flip was refused by the session's permission classifier and is staged for the operator. [Recovery](../docs/recovery/2026-09-07-team-overhaul-release.md).

## 2026-09-07 — Owner-only outage: paged impression insert (G-072)

The owner-only activation (PR #287 `16bb6fd1`, LIVE 05:28 UTC, knobs flipped 05:29 UTC by the release session) crashed production on its first two searches: uncapped decks of 1,037 / 1,456 cards × ~21 KB evidence rows became a single ~28 MB `INSERT`, the 256 MB Postgres backend was OOM-killed twice, and exclusive mode failed the job (`owner_impression_unavailable`) → "Search failed" on every Find a Trade. Operator chose to keep owner-only live: budgets cut to 300 / 3,000 at 13:55 UTC (≈250 cards). Fix: `save_deck_impressions` pages at 100 rows per statement in one transaction (`DECK_IMPRESSION_INSERT_ROWS`), guarded by `test_deck_impressions_paging.py`. Shipped 2026-09-08 as [PR #289](https://github.com/mattmurf77/fantasy-trade-finder/pull/289) `609cb79e`, Render LIVE 02:41 UTC; both budgets restored to 4096 / 60000 at 02:41 UTC, so decks are uncapped again on the paged insert. First real uncapped search still to be confirmed in the logs. No mobile change: build 1.17.2 (150) already carries the owner contract. [Runbook row](../docs/runbook.md#common-failure-modes), [G-072](GOTCHAS.md).

## 2026-09-07 — Team overhaul v1 MERGED dark (D-188, ADR-020); iOS 1.17.2 (151) uploaded

**What:** the full Team overhaul flow from the 2026-09-06 handoff ([docs/plans/team-overhaul](../docs/plans/team-overhaul/README.md)) built behind `overhaul.enabled=false` on `claude/team-overhaul-scoping-ea1c72` (from `origin/main` `0e3d6b70`). Backend: `overhaul_service.py` (pure domain: pool enforcement, own-first recovery identity, bounded assembly of 4–5 give/receive-disjoint packages into ≤5 distinct roadmaps, priorities/prepare validation, attempt state machine), `overhaul_store.py` (five additive tables, transactional reservations, CAS transitions), `overhaul_api.py` (14 `/api/overhauls` routes installed like Win Now), `_sleeper_propose_core` extracted from `/api/trades/propose` with byte-identical route behavior. Mobile: `OverhaulEntryCard` on the Acquire landing below Team review, eight Trades-stack screens (outlook → pool → targets → review → roadmaps → one-package priorities → send summary → saved plan), `api/overhaul.ts`, `check-team-overhaul.js`. Docs: api-reference, data-dictionary, config-reference, cross-client-invariants, architecture, glossary, ADR-020.
**Why:** owner approved the core mocks and asked for engineering scoping and build. The engineering spec's full execution platform (workers, leases, withdrawal) was narrowed to an honest v1 ([BUILD-CONTRACT](../docs/plans/team-overhaul/BUILD-CONTRACT.md)): Sleeper-only sends, copy handoff for MFL/ESPN, status from ownership refresh (live traded-picks read) plus user assertions, manual fallback.
**Evidence:** independent backend review found 1 high / 4 medium / 8 low defects; all fixed with RED→GREEN regression tests (45 overhaul tests). Mobile tsc clean; all structural guards and testid-lint pass; web checks 190/190. Full backend suite result in [TEST_LEDGER](TEST_LEDGER.md). Device checklist ([QA.md](../docs/plans/team-overhaul/QA.md)) unrun — no build exists.
**Shipped:** operator authorized merge + TestFlight. PR #288 squash-merged as `a8ef182e` (tree identical to the branch); Render deploys `main` with `overhaul.enabled=false`. iOS **1.17.2 (151)** (EAS `2e13ce3d`) uploaded to App Store Connect from the identical tree; it supersedes build 150, whose source had no mobile/config differences from main. [Recovery](../docs/recovery/2026-09-07-team-overhaul-release.md). Flag flip still gated on D1/D9 confirmation and the device checklist on build 151.

## 2026-09-06 — Clean workspace and bounded project knowledge

Created an independent current-main organization branch, consolidated product/workflow references, generated status indexes, archived closed plans and retired tooling, and preserved local-only work with integrity manifests. Startup memory is explicitly bounded. [Migration and validation](../docs/recovery/2026-09-06-project-organization.md). This is local repository work; no product rollout.
