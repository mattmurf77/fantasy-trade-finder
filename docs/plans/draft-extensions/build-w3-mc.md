# Build status — W3 M-C · asserted picks priced across all seven read sites

**Date:** 2026-08-08 · **Status:** landed dark behind `picks.assign_tradeable` · **Scope:** backend only
**Sources (binding):** [plan.md §6.4](plan.md) + the operator-decision block (**decision 4 — full engine parity**) · [lld.md §4.5](lld.md) · [build-w3-ma-mb.md](build-w3-ma-mb.md) (the delivered M-A contract) · [ADR-010](../../adr/adr-010-user-asserted-pick-ownership.md)

> **This file is the delivered contract.** Where it and the LLD disagree, this is what shipped — §6 lists every deviation and why.

---

## 1. What landed

| What | Where |
|---|---|
| Seven read sites opted into the platform ∪ asserted union, all through ONE helper `_pick_read_source()` | `backend/server.py` |
| The two duplicated three-clause engine literals collapsed into `_owned_picks_available()` | `backend/server.py` |
| `picks_supported` as a DATA test | `backend/server.py` (`get_league_picks`) |
| Provenance helpers `_pick_provenance` / `_pick_wire_source` + the four priced payloads | `backend/server.py` |
| `has_assigned_picks(league_id)` — the memoised data half of the guard, invalidated with the contested cache | `backend/database.py` |
| Flag `picks.assign_tradeable` (4-touch, lands **OFF**) | `backend/feature_flags.py`, `config/features.json`, `backend/tests/fixtures/flags/release.json`, `docs/config-reference.md` |
| 37 tests, 10 verify-failing-first mutations | `backend/tests/test_pick_assignment_tradeable.py` (+ the M-A AST test re-decided) |

**Not built, deliberately:** M-D (`draft.manual_picks` / `recorded_picks`). No schema change — M-C adds no column and no route.

---

## 2. The seven read sites, AS FOUND (by symbol — several had drifted again)

The LLD's line numbers were stale for a second time; every site was re-located by symbol, and the AST test keys on symbols so it cannot rot.

| Stage | Symbol | LLD line | Found at | What it feeds |
|---|---|---|---|---|
| **S1** | `get_league_picks` | 8558 | **8625** | `/api/league/picks` — the calculator's pick list |
| **S1** | `_trade_evaluate_impl` | 8104 | **8157** | `/api/trade/evaluate` — per-asset pricing |
| **S2** | `_power_picks_by_owner` | 17230 → (M-A: 17658) | **18288** | power rankings' draft-capital group |
| **S2** | `_user_pick_share` | 4387 | **4427** | the caller's own contend/rebuild outlook seed |
| **S3** | `_owned_pick_assets` | 8629 | **8802** | the suggestion candidate pool (via `_inject_owned_picks`) |
| **S3** | `_run_trade_job` (opponent shares) | 4526 | **4569** | inferred opponent outlooks |
| **S4** | `_roster_eveners` | 953 | **971** | one-tap "add their 2027 1st" sweeteners |

Two engine guards, likewise by symbol: the trade job's injection guard (`_run_trade_job`) and asset-ideas' (`asset_ideas_route`). Both were the **three-clause** literal the design pass flagged, not a bare platform test.

**Build sequence, not release gates.** S1→S4 were implemented and golden-diffed in order, each site verified independently; all four land together behind the one flag, per operator decision 4. The §6.8 adoption / contested-rate / offline thresholds remain **monitoring and rollback triggers**.

---

## 3. THE PROVENANCE CONTRACT — what the mobile agent must render

Registered in [cross-client-invariants.md](../../cross-client-invariants.md) (§ *Asserted-pick provenance*) so three clients cannot paraphrase it differently. Everything below appears **only** while `picks.assign_tradeable` is on; with the flag off the fields are **absent entirely**.

### 3.1 The enum — closed, two members, never null

```
source: "platform" | "user"
```

`"platform"` = platform-synced ownership (Sleeper/MFL). **A NULL `draft_picks.source` serializes as `"platform"`**, so a client never sees a null and may switch exhaustively.
`"user"` = asserted by a league member in the assignment grid. Never verified against a platform — ESPN has no draft object to verify against, now or ever.

### 3.2 The label — EXACT COPY, all five priced surfaces, no abbreviation

> **Member-entered — not verified with ESPN**

### 3.3 The correction path

Every surface that shows the label carries a **one-action correction** deep-linking to the assignment screen with `{leagueId, season, focusPickId}` (`focusPickId` = the row's `pick_id`). That is why payloads that did not already carry them now ship `season` (and `pick_id`, on power-rankings items) next to `source` — a badge with no season is a dead end.

### 3.4 Exactly where it rides

| Payload | Entry | Extra fields |
|---|---|---|
| `GET /api/league/picks` | every `my_picks` / `all_picks` row | — (`pick_id`/`season` already present) |
| `POST /api/trade/evaluate` | every `per_player` entry whose id is a league pick | `season` |
| `POST /api/trade/evaluate` → `eveners[]` | every pick item | `season` |
| `POST /api/trade/evaluate` → `eveners[]` | a 2-piece combo containing a member-entered pick | carries `source: "user"` (no season — it is a bundle) |
| `GET /api/league/power-rankings` | every `teams[].picks.items[]` entry | `pick_id`, `season` |

A **player** entry on `/api/trade/evaluate` carries no `source` at all — it is not a pick. Do not treat its absence as `"platform"`.

### 3.5 Four rules the client must not break

1. **Read `source`.** Never infer provenance from the league platform, the `pick_id` shape, or a missing `synced_at`.
2. **An asserted pick is not a different KIND of asset.** It is priced by the identical shipped functions, because no user can ever enter a value. Only the label differs.
3. **A contested or orphaned slot never reaches a priced payload** — it is withheld server-side by a row filter. Do not reconstruct it. The one place it is visible is `GET /api/league/pick-assignments`, the screen where it gets fixed.
4. **`picks_supported` is now a data test** (`platform != "espn" or the league has assigned rows`), so an ESPN league can report `true`. Do not re-derive it from the platform string.

---

## 4. The one guard — all three clauses preserved

```python
def _owned_picks_available(league_id: str, league) -> bool:
    if not FLAGS.trade_picks_in_pool:            # clause 1
        return False
    if league_id == "league_demo":               # clause 2
        return False
    if getattr(league, "platform", None) != "espn":   # clause 3
        return True
    return _asserted_picks_tradeable() and has_assigned_picks(league_id)
```

The design pass's finding was correct and load-bearing: the literals were **three-clause**, so factoring out only the platform test would have silently re-enabled picks for the demo league and with `trade.picks_in_pool` off. With `picks.assign_tradeable` off this returns **exactly** the old expression for every league — pinned by a 16-case parametrized test that compares the helper against the literal.

Only the ESPN clause changed, and it changed from a **platform** test to a **data** test: an ESPN league with assignments qualifies; one without them does not.

---

## 5. Tests & gates

`backend/tests/test_pick_assignment_tradeable.py` — **37 tests**, plus the M-A AST test re-decided in `test_pick_assignment.py`.

| Criterion | Test |
|---|---|
| **D10** golden byte-identity, flag OFF, all seven sites | `test_mc_01_flag_off_is_byte_identical_on_every_read_site` (a full asserted grid changes nothing), `_01b` (evaluate), `_01c` (the ESPN room is untouched by this flag) |
| **D10** no new keys with the flag off | `test_mc_09c_provenance_disappears_entirely_with_the_flag_off` — all four payloads' key sets, and the assertion the golden diff structurally cannot make (it compares one build against itself) |
| **S1→S4** each site lights up | `_02` / `_02b` / `_03` / `_04` / `_05` / `_06` / `_07` |
| **D13** no user values, **both** pricing modes | `test_mc_08_…` parametrized over `tier_ladder` and `market_slots`, asserting every price is reproducible from the pick's coordinates alone |
| **D17** provenance on all four priced payloads | `test_mc_09_…`, `_09b` (a combo inherits `"user"`) |
| **INV-5** contested by ROW FILTER | `test_mc_10_…` (excluded from power rankings, `/api/league/picks` and the suggestion pool; stored price untouched), `_10b` (pins the NULL-re-derivation branch that makes nulling unsafe) |
| **The three-clause guard** | `test_mc_11_…` (16 cases vs. the literal), `_11b`, `_11c` (data test), `_11d` (AST — only `_owned_picks_available` and `get_league_picks` may hold an ESPN platform literal) |
| **AST containment** | `test_w3_02` re-decided (`source=` opt-ins are **exactly** the seven sites + the four assignment-surface callers, and no site is left on the bare default), `test_w3_02d` (every one of the seven passes `_pick_read_source()`, never a literal `PICK_SOURCE_ANY` — a literal would ignore the kill switch) |
| **Flag** | `test_mc_12_…` — registered, defaults OFF, both JSON mirrors agree |

**Verify-failing-first — 10 mutations, each confirmed RED before the guard was accepted:**

1. read source ignores the kill switch (always union) → D10 golden + evaluate golden
2. read source never opts in (M-C a no-op) → all six site tests
3. guard factored to the platform clause only (the design-pass trap) → 10 guard cases
4. ESPN clause left as a platform test (no data half) → the data-test test
5. `picks_supported` left as a platform test → S1a
6. provenance dropped from power-rankings items → D17
7. provenance emitted unconditionally → the flag-off key-set test
8. contested excluded by **nulling `pool_value`** instead of row-filtering → INV-5
9. combo evener loses its inherited provenance → `_09b`
10. a read site hard-codes `source=PICK_SOURCE_ANY` → the AST helper test

**Gate:** `python3 -m pytest backend/tests -q` → **1965 passed, 1 skipped, exit 0** (baseline 1927 passed / 1 skipped). `git status --porcelain -- mobile/` empty.

---

## 6. Deviations from the LLD (and one from the M-A doc)

| # | LLD said | Shipped | Why |
|---|---|---|---|
| 1 | `picks_supported = is_enabled("picks.assign") and _has_assigned_picks(...)` (§4.5.2) | gated on **`picks.assign_tradeable`**, the same condition that decides whether the rows are returned at all | Under `picks.assign` alone the payload's `all_picks` is still platform-only, so the LLD's version would advertise support for a payload carrying **zero** picks. The label now cannot contradict its own body. |
| 2 | `_has_assigned_picks` as a private `server.py` helper | `database.has_assigned_picks`, memoised in the store beside the contested cache | The probe is a `SELECT 1` on `draft_picks`; putting it in the store lets one invalidation hook clear both memos, which is what makes an assignment light a league up at the next read rather than after a TTL. It fails **closed**. |
| 3 | D17 as "`source` + the label + the correction path on all five priced surfaces" | `source` on the four priced **payloads**; the fifth surface (generated suggestions) carries pick ids the client resolves against `/api/league/picks` | A suggestion serializes picks as `Player` pseudo-assets; a provenance field there means widening the `ranking_service.Player` dataclass, which is a bigger, non-surgical change reaching the whole engine. **Residual, named:** until that lands, the suggestion card's badge is a client-side join on `pick_id`. |
| 4 | LLD line numbers throughout §4.5 | every site re-located **by symbol** (§2) | They had drifted again since M-A. |
| 5 | M-A doc §8: "do not reference `picks.assign_tradeable`" | it exists now | M-C is built; the mobile half may reference it and render the badge. |

**Also note:** payloads that did not already carry `season`/`pick_id` gained them alongside `source` (§3.4). The LLD did not call this out, but the correction deep link it mandates (`{leagueId, season, focusPickId}`) is unbuildable without them.

---

## 7. Residual risks (unchanged, all accepted knowingly by the operator)

1. **A leaguemate can change what FTF recommends to you** — including an active "ask for their 2027 1st" sweetener, now that S3/S4 are lit. Bounded by the conservation bound, contested ⇒ unpriced, the provenance label on every priced surface, the one-action correction, and this flag as a single kill switch that **never destroys entered data**.
2. **There is usually no corrector.** Most ESPN leagues will have exactly one FTF user, so the realistic failure is one honest mistake persisting unnoticed.
3. **No self-healing.** ESPN will never contradict a wrong grid.
4. **Provenance is a badge, and users skim badges** — the strongest argument for holding S4, which the operator overrode.
5. **Spent picks linger** unless retired; the Sept-1 hard retire for current-season assigned picks is **not built** (it belongs with M-D's wave).
