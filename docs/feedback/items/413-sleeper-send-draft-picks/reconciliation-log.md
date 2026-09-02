# Reconciliation log — G-413 (Phase 1, Author ↔ Planner)

> Round 1 critique: [review-round-1.md](review-round-1.md) (Planner, verdict "ready for build
> after fixes"). Round 2 incorporation: 2026-09-02, Author. Every code cite in the critique was
> re-verified against the worktree (`843a641c`) before the corresponding edit was written.

## Round 1 objections

| # | Objection (short) | Outcome | Where it landed |
|---|---|---|---|
| 1 | Both 422 bodies need `detail` (fielded catch-all renders `detail \|\| "Please try again"`, `SendInSleeperButton.tsx:305-310`) | **incorporated** | LLD §4.2 (code + binding bullet), §4.4 table, §9; PRD §1, R-6, R-7, guardrail 9, T-7/T-9 asserts + drop-`detail` sabotage |
| 2 | One consistent build-honesty statement | **incorporated** | PRD §1, PRD §10 header, scope §5 — same sentence in all three |
| 3 | TF-5/TF-6 not reproducible on demand; TF-3 conditional | **incorporated** | PRD §10 "Which steps are which" + row labels; HLD §7; scope §3 checklist bullet |
| 4 | Mobile copy tone; count-aware per ruling 2; curly quotes in the server validate string | **incorporated** | LLD §8.1 (rewritten strings), §5 (curly “Early 1st”, ×2), §4.2 server strings; PRD R-13, TF-5/TF-6 expected copy |
| 5 | No positive spine assertion (deleting `:16264` passes every test) | **incorporated** | PRD T-3b `assert_called_once_with("imp-1", "propose", acting_user_id=USER)`; R-8; HLD §6 |
| 6 | Ordering rule R-6 (unmapped before not_owned) untested | **incorporated** | PRD T-14 |
| 7 | `picks[]` give-then-receive across both sides unpinned | **incorporated** | PRD T-7 (both sides, both rungs) |
| 8 | T-8 sabotage was a rewrite, not a slip | **incorporated** | PRD T-8: `if False:` / rosters-derived existence |
| 9 | Int/str coercion rule scattered | **incorporated** | LLD §3.1 "Rule (binding)" paragraph |
| 10 | Restore D-063 cite in D-e; spine cite = CHANGELOG 2026-08-29d, not D-152 | **incorporated** | HLD D-e (`DECISIONS.md:675-676`), HLD §6 (`CHANGELOG.md` § 2026-08-29d, PR #241) |
| 11 | Ruling-1 paragraph (user-asserted rows) into PRD §4 + LLD §4.2 | **incorporated** | PRD §4 bullet + guardrail 8 pointer; LLD §4.2 binding bullet; PRD §12 D-172 sentence |
| 12 | `detail` on the new 400 for symmetry | **incorporated** | LLD §4.1, §4.4, §9; PRD R-2 |
| 13 | HLD §2 diagram sentence ("node covering an edge") | **incorporated** | HLD §2: label on the existing `SRV → SL` edge + new `DB → SRV` edge |
| 14 | Recount the test delta | **incorporated** | PRD §7.5, scope §3/§5 — **+20** |

**Rebutted: none.** Every objection checked out against the code at the cited lines. No item
needs orchestrator arbitration.

## Rulings on the Author's round-1 open questions

| Ruling | Decision | What changed |
|---|---|---|
| 1 — grid source | Platform-only; user-asserted rows 422 `unmapped` by design | PRD §4 bullet with the `database.py:10217-10221` / `server.py:14502-14545`, `:14591-14640`, `:10840`, `:11347` / `features.json:219` cites; LLD §4.2 bullet; D-172 text |
| 2 — mobile copy | Rewrite count-aware, keep structure (title, no `goConnect`, no `detail`, no ids, chain position) | LLD §8.1 strings + comment; server `message`/`detail` use the "Some" form verbatim; PRD R-13 |
| 3 — T-11 mock vs flag-driving | Mock; pair with T-3b | PRD §7.2 note after T-14 |
| 4 — TestFlight honesty | With `detail`, all seven steps run on any fielded build; TF-5/6 opportunistic; TF-3 "not run" legal | PRD §1/§10, scope §3/§5 |
| 5 — deviations 1–7 | All accepted except: restore D-063, cite CHANGELOG 2026-08-29d for the spine | HLD D-e, HLD §6 (objection 10) |

## Test delta, recounted

| File | Round 1 | Round 2 | Δ |
|---|---|---|---|
| `test_sleeper_write.py` | T-1, T-2 | T-1, T-2 | +2 |
| `test_sleeper_write_route.py` | T-4…T-13 new; T-3 in place | T-3b, T-4…T-13, T-14 new; T-3 in place | +12 |
| `test_trade_send_validate.py` | V-1…V-6 | V-1…V-6 | +6 |
| **Total** | **+18** | | **+20** → 4503 passed / 1 skipped on the 2026-08-31b baseline (4483) |

Named sabotages: 23 across T-/V- (T-7 and T-9 each carry three alternatives, T-14 two) plus the
three mobile structural sabotages (C-7/C-7b/C-8). Every one is run RED before its assertion is
accepted; the build agent records actuals in TEST_LEDGER.
