# FB-418 backend follow-up (D-178) — QA report A: mechanical correctness and honest evidence

> **Verdict: PASS** (1 NON-BLOCKING coverage finding, 5 NOTEs). No BLOCKING finding.
> **Subject:** commit `77a4e33b` ("D-178: a sent offer is a LIKE on the idea routes"),
> diff base `f13dd96c`. Session tree `happy-golick-345cf1`, branch
> `claude/new-user-feedback-06dabd`. Nothing committed; no source edited in the
> session tree.
> **Reviewer angle:** mechanical correctness and honest evidence. Every builder
> claim below was re-derived from the code or re-run, never accepted.
> **Date:** 2026-09-03

---

## 1. Verdict

The change does what D-178 rules it should do, and the evidence backing it is
honest. Specifically, I independently confirmed:

- **Every** path by which an idea can reach either route's payload is guarded.
  There is no fourth emission site.
- The cap claim — the headline claim most likely to be wrong — is **correct**
  for both routes, for the reason the builder gives.
- The `presentment_key` orientation matches `_load_presentment_exclusions`,
  which matches what `POST /api/trades/queue` writes. An orientation flip is
  caught by 11 tests.
- The suite arithmetic (4587/1 baseline, +12, 4599/1) is exactly right, and the
  brief's 4565 figure is indeed stale.
- The red-proof table reproduces move for move: 7 baseline-red, S1→2, S2→2,
  S3→4.

The one substantive finding is a **coverage gap, not a defect**: a sabotage I
designed (Q-B) removes the slot-yielding half of the fix and the entire
4600-test suite stays green — even though the mutation is live and changes the
payload. The shipped code is correct; nothing pins it.

---

## 2. Findings

| id | severity | file:line | description | proof |
|---|---|---|---|---|
| **A-1** | **NON-BLOCKING** | `backend/trade_service.py:5591`, `:5713` | The `_emit_best` variant pre-filter and the downgrade-combo skip are what make the PRD's / api-reference's "an excluded idea yields its slot to the next-best" claim true for every `_emit_best`-served group (upgrade both directions; downgrade in the receive direction). **No test in the suite pins them.** Narrowing both to a dismiss-only predicate while keeping the `_emit` backstop leaves the full suite green — yet the mutation is live and changes the payload. | Sabotage **Q-B** below: `4599 passed, 1 skipped` with the mutation applied. Probe (§5) shows shipped code returns `(['P','S2'],['U'])` after `(['P','S1'],['U'])` is excluded; under Q-B the upgrade group comes back **empty**. Suggested fix: one test in `test_asset_ideas.py` with a second sweetener so the upgrade group has ≥2 viable variants, asserting the runner-up takes the slot. |
| **A-2** | NOTE | `backend-prd.md` §5.1; `docs/api-reference.md` (asset-ideas row) | The cap claim is stated absolutely — "yields its slot to the next-best **rather than** shrinking the group". It is only true where an alternative candidate exists. The builder's own `test_route_excludes_a_sent_offer` asserts `after["groups"]["lateral"] == []`, i.e. a group of 1 shrinking to 0. The mechanism is right; the wording overstates it. | Read `trade_service.py:5843-5850` (`out[group] = sorted(chosen, key=key)[:cap]`) — the cap truncates a post-filter list, so it refills *from candidates that exist*. `test_asset_ideas.py::test_route_excludes_a_sent_offer` is the counterexample to the absolute phrasing. |
| **A-3** | NOTE | `backend/database.py:8703-8711`; `backend/server.py:19577` | Inherited fail-open, correctly disclosed in PRD §5.4 but worth restating with its prod shape: `load_awaiting_trades` **drops** a like whose counterparty it cannot recover from the `league_members` roster snapshot. The tests write that snapshot **synchronously**; production writes it from a **best-effort background daemon** at `session_init`, inside a `try/except … continuing` (`server.py:19583`). A session whose daemon upsert failed therefore silently loses the exclusion while the tests can never see it. Fail-open (the idea is re-offered), and identical to what the deck already lives with — not introduced by D-178. | `database.py:8704` `if not partner_id: continue`. `server.py:19577` upsert sits inside the deferred daemon closure described at `:19325-19335`, wrapped at `:19582-19584`. |
| **A-4** | NOTE | `backend/database.py:8607-8617` | Second inherited limit, **not** mentioned anywhere in the PRD or scope block: `load_awaiting_trades` selects the **500 most recent likes across ALL leagues**, and `_load_presentment_exclusions` filters to one league only *afterwards*. A user with heavy like volume in other leagues can have this league's older likes truncated out of the exclusion set, silently. Pre-existing (the deck shares it) and fail-open. | `database.py:8613` `.order_by(created_at.desc()).limit(500)` with no `league_id` predicate; `server.py:5827-5828` filters by league after the call. |
| **A-5** | NOTE | `mobile/src/components/ShopOffersBody.tsx:321-332` | The corrected comment asserts unconditionally that "asset-ideas **now consults** the deck's windowless awaiting-like exclusion set, so the next fetch doesn't re-offer a sent idea either". That holds only while `trade.presentment_rules` is on — and `backend-scope.md` §2 names flag-off as the deploy-free rollback lever, so the comment becomes false in precisely the rollback state. Cosmetic; the code is unaffected. | Route guard `server.py:12360-12362` / `:12607-12609`; scope block §2 "Deploy-free rollback lever". |
| **A-6** | NOTE | `backend/server.py:12245` | Asymmetry, pre-existing: `asset-ideas` takes `league_id = body.get("league_id") or g_league.league_id` with **no** `league_mismatch` guard, while `fair-packages` (`:12549`) and `/api/trades/queue` (`:13290`) both 400. I checked whether a client-supplied foreign `league_id` could build an empty exclusion set against a session-league sweep: it cannot — `_generate_asset_ideas_impl` does `self._leagues.get(league_id)` (`trade_service.py:5357`) and returns empty groups on a miss, so a mismatch yields *no* ideas rather than *unfiltered* ideas. Not a D-178 defect; noted only because D-178 adds a consumer of that unvalidated value. | `trade_service.py:5357-5361`. |

**Nothing untraceable in the diff.** Every changed line in `backend/server.py`,
`backend/trade_service.py` and the two test files maps to R-1…R-9. The mobile
change is comment-only (R-9) and the docs/living-memory changes are the gate
artifacts. No drive-by refactor, no speculative abstraction.

**No requirement is unimplemented.** R-1 (`server.py:12360-12362`, `:12607-12609`),
R-2 (`trade_service.py:2185-2199`), R-3 (§3 below), R-4 (`server.py:12428`,
`:12653` — the payload is built from post-filter groups only), R-5
(`_load_presentment_exclusions` called, never re-written), R-6
(`server.py:5832-5837`), R-7 (`trade_service.py:5528` keeps the dismiss arm),
R-8 (flag reuse, §6 below), R-9 (`ShopOffersBody.tsx:321-332`).

---

## 3. The four verification targets

### 3.1 Emission-path enumeration (brief item 1) — CLAIM VERIFIED

The builder claims `_suppressed` covers all three asset-ideas emission sites
plus a new fair-packages first-statement filter. I did not take that on trust; I
enumerated the **appenders**, which is the only complete way to ask the
question — an idea reaches the payload if and only if it is appended to
`strict`/`relaxed`.

```
$ git grep -n "strict\[group\]\.append\|relaxed\[group\]\.append\|strict\.append\|relaxed\.append" backend/trade_service.py
5569:  strict[group].append(idea)     # inside _generate_asset_ideas_impl._emit
5573:  relaxed[group].append(idea)    # inside _generate_asset_ideas_impl._emit
6010:  strict.append(idea)            # inside _generate_fair_packages_impl._emit
6014:  relaxed.append(idea)           # inside _generate_fair_packages_impl._emit
```

Exactly four, and all four sit **below** a guard:

- `trade_service.py:5540` — `if _suppressed(give_ids, recv_ids): return`, the
  first statement of the asset-ideas `_emit`. All five call sites (`:5665`,
  `:5730`, `:5778`, and `_emit_best`'s single `:5611`) funnel through it.
- `trade_service.py:5992` — `if presentment_key(give_anchor, recv_ids) in
  _excl_keys: return`, the first statement of the fair-packages `_emit`. Both
  call sites (`:6036`, `:6041`) funnel through it.

The other two sites the builder names — `:5591` (the `_emit_best` variant
filter) and `:5713` (the downgrade-combo skip) — are **not** emission paths.
They are pre-filters whose only job is slot-yielding, which is why A-1 matters
and why nothing about *presence* depends on them.

Both routes serialize only what the generator returned (`server.py:12428`
`{k: [_idea_row(i) for i in v] for k, v in groups.items()}`; `:12653`
`[_idea_row(i) for i in result.get("ideas") or []]`) and add no ideas of their
own. There is no fourth path.

There is a fifth `_emit` in the file at `:7381` — that is the v2 deck
generator, which already carries the deck's own `presentment_ok_fn` gate
(`:7376`). Out of scope, and correctly untouched.

### 3.2 The cap claim (brief item 2) — CLAIM VERIFIED, both routes

The claim: filtering at emission means an excluded idea "yields its slot to the
next-best rather than shrinking the group". The failure mode to look for is
suppression happening *after* a truncation.

**`asset-ideas` / `asset_ideas_group_cap`.** The generator accumulates into
unbounded `strict`/`relaxed` dicts throughout the sweep. The cap appears
**once**, in the final loop:

```
trade_service.py:5849-5850
    chosen = strict[group] or relaxed[group]
    out[group] = sorted(chosen, key=key)[:cap]
```

`cap` is read at `:5383` but not applied until `:5850`. Suppression at `:5540`
therefore removes a candidate from an untruncated pool; the sort-and-truncate
then draws the cap'th slot from whatever remains. Generation does **not** stop
early on a suppression — nothing in the sweep loops is bounded by the emitted
count. **Correct.**

**`fair-packages` / `fair_packages_cap`.** Same shape:

```
trade_service.py:6045-6058
    chosen = strict or relaxed
    was_relaxed = not strict and bool(relaxed)
    ...
    cap = max(1, int(_c("fair_packages_cap")))
    "ideas": sorted(chosen, key=_key)[:cap]
```

Suppression at `:5992` precedes both the `strict or relaxed` #189 choice and
the cut. So a sweep whose entire strict band was already offered genuinely
falls through to the widened band rather than returning an empty list —
a second-order consequence the builder claims and which the code supports.
**Correct.**

One qualification, recorded as **A-2**: this refills the cap *from candidates
that exist*. Where the suppressed idea was the only one, the group still
empties. The absolute phrasing in the PRD and api-reference overstates that.

### 3.3 Orientation (brief item 3) — CLAIM VERIFIED

Traced end to end rather than assumed:

1. `POST /api/trades/queue` writes `save_trade_decision(give_player_ids =
   card.give_player_ids, receive_player_ids = card.receive_player_ids)`
   (`server.py:13371-13377`), where the docstring and body binding make
   `give` = *what the caller sends* (`:13221`, `:13280`).
2. `load_awaiting_trades` (`database.py:8582`) reads that row straight through:
   `"my_give": give, "my_receive": receive` (`:8716-8717`). No flip. For a like
   the caller **made**, `my_give` is the caller's send side.
   For a like made *against* them there is no row — the counterparty's like
   lives under *their* `user_id`, and only matures into a `trade_matches` row,
   which `load_matches_for_exclusion` mirrors explicitly when the caller is
   `user_b` (`database.py:8574-8577`). So both arms land in the caller's frame.
3. `_load_presentment_exclusions` (`server.py:5825-5833`) builds
   `(frozenset(my_give), frozenset(my_receive))`.
4. `presentment_key(give_ids, recv_ids)` returns
   `(frozenset(give_ids), frozenset(recv_ids))` (`trade_service.py:2199`).
5. In `_generate_asset_ideas_impl`, `give` is always the user's side in both
   directions: `direction="give"` emits `_emit(member, [asset_id], [c], …)`
   with `asset_id ∈ user_roster` (`:5665`); `direction="receive"` emits
   `_emit(owner, [g], [asset_id], …)` with `g ∈ give_pool ⊆ user_roster`
   (`:5778`). In `_generate_fair_packages_impl` the key is
   `presentment_key(give_anchor, recv_ids)` where `give_anchor` is the canvas
   give side (`:5992`).

Orientations agree at every hop. Empirically confirmed by sabotage **Q-A**
below: flipping `presentment_key` turns 11 tests red — so the suite pins this
hard, and it also pins that the D-067 dismiss keys share the same orientation
(3 of those 11 are dismiss tests).

### 3.4 Fixture honesty (brief item 4) — HONEST, with two inherited caveats

The three fixture ingredients each produce a production shape:

| Fixture | Production equivalent | Same? |
|---|---|---|
| `POST /api/trades/queue` | The shop's ✓ and the pushed fair deck's ✓ are literally this route | **Yes** — the shipped route, not a hand-written `trade_decisions` insert |
| `POST /api/trades/awaiting/dismiss` | #318, the only retraction surface | **Yes** |
| `upsert_league_members(league_id, [{user_id, username, player_ids}])` | `session_init`, `server.py:19577`, same call, same `player_ids` key → `roster_data` JSON (`database.py:7224`) | **Same writer**, but see A-3 for the timing divergence |

Counterparty resolution in the test path is genuinely the production path:
`load_awaiting_trades` walks `owner_by_league_pid` built from `roster_data`
(`database.py:8657-8663`), and `upsert_league_members` is the only writer of
that column. The `route_db` / `harness` fixtures patch
`backend.database.engine`, which those functions resolve as a module global at
call time, so the patch reaches them.

The `route_client` fixture also matches the FB-409 caller-exclusion convention
(`league.members` holds only `opp`) while the persisted snapshot holds both —
which is exactly the production asymmetry. The `test_fair_packages` harness
*includes* `ME` in `league.members`, a small divergence from that convention,
but it cannot cause a false pass: `_generate_fair_packages_impl` filters the
caller out itself (`trade_service.py:5975`), and `/api/trades/queue` looks up
only `opponent_user_id`.

**Could the tests pass while prod fails?** Two ways, both fail-**open** and
both inherited rather than introduced: **A-3** (the `league_members` snapshot is
written by a best-effort background daemon in prod, synchronously in tests) and
**A-4** (the 500-row cross-league like cap). Neither produces a wrong answer —
they weaken the exclusion, re-offering an idea, which is the pre-D-178
behavior. There is no divergence that would make the feature a systematic
no-op in production. A-3 is disclosed in PRD §5.4; A-4 is not disclosed
anywhere.

---

## 4. Command results

All run in the session tree unless noted; the red-proof and sabotages ran in a
throwaway worktree at `77a4e33b` (created and removed, branch `qa178-a`
deleted — see §7).

| # | Command | Result |
|---|---|---|
| 1 | `python3 -m pytest backend/tests -q` (session tree) | **4599 passed, 1 skipped** in 344.95 s ✅ matches the claim |
| 2 | `pytest backend/tests -q --collect-only` @ `77a4e33b` | **4600 collected** |
| 3 | Same, with both test files reverted to `f13dd96c` | **4588 collected** → +12 exactly, none lost ✅ arithmetic verified independently; baseline = 4587 passed / 1 skipped, the brief's 4565 is stale |
| 4 | `pytest test_asset_ideas.py test_fair_packages.py -q --collect-only` | 101 vs 89 at baseline → +12 ✅ |
| 5 | `git checkout f13dd96c -- backend/server.py backend/trade_service.py` then run both test files | **7 failed, 94 passed** — precisely the 7 the red-proof table names ✅ |
| 6 | `cd mobile && npm run test:shop-deck` | **153 PASS** ✅ ; `grep -n "#418" tests/check-shop-deck.js` shows all three k8 sites intact |
| 7 | `cd mobile && npx tsc --noEmit` | clean, exit 0 ✅ |

The TEST_LEDGER's "415 s" for the suite is 345 s on this machine — immaterial,
noted only for completeness.

---

## 5. Sabotage table

Builder's three, reproduced verbatim, plus two of my own aimed at what the
tests do **not** pin.

| id | Sabotage | Expected | Observed | Caught by |
|---|---|---|---|---|
| **S1** | Flag guard removed at both new call sites (`if FLAGS.trade_presentment_rules:` → `if True:`) | tests 11–12 red | **2 failed, 99 passed** | `test_route_flag_off_is_byte_identical`, `test_flag_off_is_byte_identical` ✅ as claimed |
| **S2** | `_load_presentment_exclusions`' `except` re-raises (equivalent to hoisting the load out of the try/except) | tests 9–10 red | **2 failed, 99 passed**, both with the injected `RuntimeError("awaiting load exploded")` escaping | `test_route_serves_unfiltered_when_the_load_breaks`, `test_a_broken_exclusion_load_serves_unfiltered` ✅ as claimed |
| **S3** | `_suppressed` narrowed to `key in _excl_keys` (dismiss arm dropped) | 4 dismiss tests red | **4 failed, 97 passed** | `test_dismissed_package_excluded_from_asset_ideas`, `test_dismissed_package_excluded_receive_direction`, `test_route_excludes_dismissed_packages`, `test_route_dismiss_behaviour_is_unchanged` ✅ as claimed |
| **Q-A** *(mine)* | **Orientation flip** — `presentment_key` returns `(frozenset(recv_ids), frozenset(give_ids))` | the brief's headline silent-failure risk | **11 failed, 4588 passed, 1 skipped** on the FULL suite | 7 D-178 tests + 3 pre-existing dismiss tests + `test_route_dismiss_behaviour_is_unchanged`. **Well covered** — and it incidentally proves the D-067 dismiss keys share the same orientation |
| **Q-B** *(mine)* | **Slot-yielding removed** — a `_dismiss_only` predicate replaces `_suppressed` at `:5591` (`_emit_best` variant filter) and `:5713` (downgrade-combo skip); the `_emit` backstop at `:5540` is left intact, so *presence* is still correct | ? | **4599 passed, 1 skipped — FULL SUITE GREEN** | **NOTHING.** → finding **A-1** |

**Q-B is a live mutant, not an equivalent one.** The suite fixture never gives
an `_emit_best` group two viable variants, so the mutation is invisible to it.
A hand-built probe (user roster `["P","S1","S2"]` with `S2` a near-equal second
sweetener, so the upgrade group has both `([P,S1],[U])` and `([P,S2],[U])`)
separates them cleanly:

```
                       shipped 77a4e33b            with Q-B applied
UPGRADE BASE:          [(['P','S1'], ['U'])]       [(['P','S1'], ['U'])]
UPGRADE AFTER EXCL:    [(['P','S2'], ['U'])]       []          ← group lost
```

The shipped code yields the slot; Q-B loses the whole group. So `:5591` and
`:5713` are load-bearing and untested. The probe was a scratch file in the
throwaway worktree and was deleted with it.

**Two candidates I evaluated and did not run as sabotages**, because reading
settled them:

- *`exclusion_keys or None` collapsing an empty set.* Not a mutation site.
  `set() or None` → `None`; the callee does `exclusion_keys or frozenset()`
  (`trade_service.py:5525`, `:5987`), so `None` and `set()` are the same value.
  Harmless no-op, no behavioral surface to break.
- *Flag guard inverted* (`if not FLAGS...`). Strictly weaker than S1 — it is
  S1 plus a flag-off exclusion, so it is caught by the same two tests plus the
  seven baseline tests. No new information.

---

## 6. Flag reuse (deviation 2, brief item 7)

**Consistent with the deck.** The deck's own build is
`server.py:5981-5983`:

```python
exclusion_keys: set = set()
if FLAGS.trade_presentment_rules:
    exclusion_keys = _load_presentment_exclusions(g_user_id, league_id)
```

Both new sites (`:12360-12362`, `:12607-12609`) are byte-for-byte the same
three lines. Same flag, same loader, same non-fatal posture. `FLAGS` is a live
proxy over `flags_dict()` (`feature_flags.py:1250-1260`), so a
`POST /api/feature-flags/reload` genuinely reaches both routes — the rollback
lever the scope block advertises works.

`config/features.json` has `trade.presentment_rules: true`, so the shipped
posture is ON, and the test harnesses set it True to match rather than
inventing a posture (`test_fair_packages.py:129-135`, `_ROUTE_FLAGS` in
`test_asset_ideas.py`).

**Flag-off byte-identity: genuine on both routes.** With the guard False,
`exclusion_keys` stays `set()`, the route passes `set() or None` → `None`, and
each generator binds `_excl_keys = frozenset()`. In `_suppressed`,
`key in frozenset()` is always False, so the predicate reduces to the exact
pre-D-178 `_dismissed` expression. In fair-packages' `_emit`, the new first
statement short-circuits to a no-op and the next statement is the original
`seen` claim. Both routes reduce to their `f13dd96c` behavior. Pinned by
`test_route_flag_off_is_byte_identical` / `test_flag_off_is_byte_identical`,
and S1 proves those tests bite.

**Is `docs/config-reference.md` consistent?** Yes, and it was updated in the
same commit — the flag row now names both routes, and the "R4 bypass"
paragraph adds that the two new consult sites are deliberately **outside**
`r4_bypass()`. I checked that claim: `r4_bypass()` is applied at the
consumption sites, not inside `_load_presentment_exclusions`, and neither
route runs inside `model_a()`. The claim holds. The consequence is real and
worth the operator knowing: a bake-off arm-A user has R4 bypassed on the deck
but **not** in the shop. Documented, not hidden.

**A state where the flag is off but a client believes the server remembers?**
Not in behavior — the mobile `suppressed` set still bridges the session for
both ✓ and ✕, which is exactly the pre-D-178 posture, and no client branches on
anything new. Only in the *comment*: see **A-5**.

---

## 7. My own code-walk — one full request, send → next fetch → excluded

Post-change line numbers at `77a4e33b`. Derived by reading, not copied from
PRD §6; it agrees with the builder's, and I add the two facts the builder's
walk leaves implicit (steps 4b and 8b).

1. **The send.** The shop's ✓ posts `POST /api/trades/queue`
   (`server.py:13216`). After the `calc.merged_layout` gate (`:13265`), the
   league match (`:13290`) and the opponent resolution (`:13318-13322`), it
   builds a deterministic `trade_id` (`:13325`), probes idempotency
   (`:13330`), reconstructs the card (`:13337`), records the in-memory
   decision (`:13353`) and persists:
   `save_trade_decision(user_id=g_user_id, league_id=league_id,
   give_player_ids=card.give_player_ids,
   receive_player_ids=card.receive_player_ids, decision="like")`
   (`:13371-13377`). Row written, `retracted_at` NULL, `give` = the caller's
   send side.
2. **The refetch.** Closing and re-opening the shop window issues
   `POST /api/trades/asset-ideas` (`server.py:12211`). Flag gate `:12233`,
   session `:12235`, `g_user_id = sess["user_id"]` `:12237` — **the same id
   `save_trade_decision` wrote under**, which is what makes step 4 find the
   row.
3. **The set is built**, after the preference loads and before the pick
   injection:
   `server.py:12358-12362` — `exclusion_keys: set = set()` /
   `if FLAGS.trade_presentment_rules:` /
   `exclusion_keys = _load_presentment_exclusions(g_user_id, league_id)`.
4. **Inside the loader** (`server.py:5811`): `load_awaiting_trades(user_id)`
   (`database.py:8582`) selects `decision == "like" AND retracted_at IS NULL`
   ordered newest-first, limit 500 (`:8607-8615`); drops keys already matured
   into a `trade_matches` row (`:8697`); de-dups re-likes of the same
   underlying trade (`:8699`); resolves the counterparty from the
   `league_members` roster snapshot (`:8692-8704`). The loop at
   `server.py:5826-5829` keeps only this league's rows and adds
   `(frozenset(t["my_give"]), frozenset(t["my_receive"]))`;
   `load_matches_for_exclusion` (`database.py:8537`) adds `pending`/`accepted`
   matches in the caller's frame.
   **4b —** the whole body is inside one `try` whose `except` logs and
   `return set()` (`server.py:5832-5837`). This is the only reason R-6 holds:
   the routes contain no error handling of their own.
5. **Threaded down:** `server.py:12403` —
   `exclusion_keys = exclusion_keys or None` in the
   `trade_service.generate_asset_ideas(...)` kwargs (`:12386-12404`), through
   the `stud_tax_override` wrapper at `:5195` into
   `_generate_asset_ideas_impl` (`:5201`, kwarg declared `:5231`).
6. **Bound and consulted:** `_excl_keys = exclusion_keys or frozenset()`
   (`:5525`); `_suppressed` (`:5526-5528`) returns True when
   `presentment_key(give_ids, recv_ids)` — `(frozenset(give), frozenset(recv))`,
   `:2185-2199` — is in the dismiss set **or** `_excl_keys`.
7. **Every candidate meets it.** The `_emit` backstop `:5540` is the guard that
   matters (all four appenders, `:5569`/`:5573` and the fair-packages pair,
   sit below one of the two `_emit` guards); `:5591` and `:5713` are the
   slot-yielding pre-filters. The sent package returns at `:5541` and never
   reaches `strict`/`relaxed`.
8. **The cap runs afterwards:** `:5849-5850`, `chosen = strict[group] or
   relaxed[group]` then `sorted(chosen, key=key)[:cap]` — a post-filter list,
   so the group refills from the next-best candidates.
   **8b —** the group is also where the #189 strict/relaxed choice happens, so
   suppressing the last strict idea correctly falls through to the labeled
   relaxed band rather than returning an empty group.
9. **Serialization adds nothing:** `server.py:12428` —
   `"groups": {k: [_idea_row(i) for i in v] for k, v in groups.items()}`.
   `_idea_row` (`:12406-12424`) hydrates players and attaches the #216
   verdict; it never adds an idea. The sent package is therefore absent from
   the payload, and so from the mode-chip counts and the `1 / X` pager the
   client derives from it — which is R-4, satisfied with no client change.
10. **Retraction restores it.** `POST /api/trades/awaiting/dismiss` marks the
    row `retracted_at = now` (`database.py:8731`, set-equal on both sides), so
    step 4's `retracted_at IS NULL` predicate stops returning it and the idea
    reappears on the next fetch. Nothing about retraction lives on these
    routes.

---

## 8. Cleanup

Throwaway worktree `.../scratchpad/wt-qa178-a` created at `77a4e33b` on branch
`qa178-a`, removed with `git worktree remove --force`; branch deleted
(`Deleted branch qa178-a (was 77a4e33b)`). No ledger entry needed — the branch
carried no unique content (it was created at, and deleted at, `77a4e33b`,
which is the session tree's own HEAD). Session tree left clean; no source file
edited there; nothing committed.
