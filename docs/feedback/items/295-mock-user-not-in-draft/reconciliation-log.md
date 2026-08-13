# Reconciliation log — #295 / #296 (the mock draft never puts the user in the draft)

> Dual-agent record for Phase 1 of the `/feedback` pipeline. The Author drafts,
> the Planner reviews adversarially, and every departure from
> [`plan.md`](./plan.md) is recorded here with its reasoning so the disagreement
> is visible rather than silently resolved.
>
> Deliverables: [`prd.md`](./prd.md) · [`scope.md`](./scope.md)

---

## Table of Contents

- [Round 1 — Author](#round-1--author)
  - [A. Verdict on the plan](#a-verdict-on-the-plan)
  - [B. Departures from the plan](#b-departures-from-the-plan)
  - [C. Adopted verbatim](#c-adopted-verbatim)
  - [D. Citation corrections](#d-citation-corrections)
  - [E. Decisions where the plan left a choice open](#e-decisions-where-the-plan-left-a-choice-open)
  - [F. Where I did NOT independently verify](#f-where-i-did-not-independently-verify)
  - [G. Open questions for the Planner's review](#g-open-questions-for-the-planners-review)
  - [H. Open items for the operator](#h-open-items-for-the-operator)
- [Round 2 — Planner review](#round-2--planner-review)
  - [I. Conceded — the Author's six departures, judged](#i-conceded--the-authors-six-departures-judged)
  - [J. Objections](#j-objections)
  - [K. Answers to the Author's open questions](#k-answers-to-the-authors-open-questions)
  - [L. Verdict](#l-verdict)
- [Round 3 — Author incorporation](#round-3--author-incorporation)
  - [M-1. J-1 accepted — R8.5 had no test](#m-1--j-1-accepted-in-full-r85-had-no-test-and-i-claimed-it-did)
  - [M-2. J-2 accepted — the fixture rewrite's two casualties](#m-2--j-2-accepted-in-full-with-one-narrowing-and-one-addition)
  - [M-3. J-3 accepted — R6 failed on correct code](#m-3--j-3-accepted-in-full-my-r6-assertion-failed-on-correct-code)
  - [M-4. J-6 accepted — degrade, do not refuse](#m-4--j-6-accepted-and-the-orchestrators-ruling-adopted-degrade-do-not-refuse)
  - [M-5. J-5 accepted — the clause stands, my justification does not](#m-5--j-5-accepted-the-clause-stands-my-justification-does-not)
  - [M-6. J-4 accepted — R5's coverage claim](#m-6--j-4-accepted-r5-claimed-coverage-it-does-not-have)
  - [M-7. J-7 decision — named follow-up, not a guard](#m-7--j-7-decision--named-follow-up-not-a-guard-in-this-fix)
  - [M-8. Smaller items](#m-8--smaller-items)
  - [N. Verdict](#n-verdict--implementable-blind-yes)

---

## Round 1 — Author

**Date:** 2026-08-10 · **Base:** `origin/main` @ `2e0b2c7` ·
**Worktree:** `.claude/worktrees/fb-295-296`

### A. Verdict on the plan

**The plan is right about the thing that matters, and it earned that the hard
way.** It reproduced the failure through the real route rather than inferring
it, it disproved the orchestrator's stated hypothesis (an id-namespace
mismatch) instead of confirming it, and it verified the proposed repair on the
same two probes. I re-derived its central claim independently from the committed
corpora and from the shipped code, and it holds:

- `ffv3-predraft/league/1312140920132497408/rosters.json` has **12 rosters, 11
  with an `owner_id`**, and the operator (`313560442465169408`) is roster 1 —
  so `sess["league"].members`, which every client builds by filtering the caller
  out, yields **10** owners for a 12-roster league.
- `backend/server.py:11566` passes that list to `build_settings` as `owners`
  while `server.py:11782` passes the caller as `user_owner_id`, and nothing
  between them checks that the second is in the first.
- `_order_from` (`backend/draft_board_service.py:740-793`) returns
  `ORDER_UNSET` for ffv3's `draft_order: null`, so `build_settings`
  (`mock_draft_service.py:998-1000`) shuffles `owners` — a list without the
  user. There is no slot he could land on. 100 %, every time.

Six departures follow. Two of them change what gets built; four sharpen it.

### B. Departures from the plan

**B-1 — The `teams` rule is a structural invariant, not a second reproduced
failure. The plan's stated trigger for it is wrong.**

[`plan.md`](./plan.md) §6.2 argues the `teams`/`order` rule is independently
load-bearing because *"ffv3 (one ownerless roster) will hit [the truncation] the
moment its commissioner sets a draft order."* **It will not.** With one
ownerless roster, Sleeper's `draft_order` (user → slot) cannot name a user for
that roster's slot, so `_mock_real_draft`'s contiguity guard
(`server.py:11681`, `if by_slot and set(by_slot) == set(range(1, len(by_slot) + 1))`)
either sees a **gap** and drops the order entirely — falling back to
`randomized`, where `resolved_order` *is* `owners` — or sees a contiguous 1..11
map, in which case `len(order) == len(owners) == 11`. Either way the truncation
does not occur.

More importantly: **after R1, `len(owners) == len(order)` on both committed
corpora**, so R1 alone restores lakeview to 12 teams / 48 order rows. The plan's
§1.2 measurement ("one real manager silently deleted from every assigned-order
mock") is a **pre-R1** statement, and R1 fixes it.

*What I did with that:* I kept the rule (PRD **R5**) and re-justified it
honestly — `owner_of` (`mock_draft_service.py:933-951`) resolves a pick by
indexing `settings["order"]`, while `pick_slots` (`:915`) sizes the slot table
from `teams`; `teams = len(owners)` is simply **the wrong quantity**, and it
equals the right one only when the session snapshot and the platform order
agree. They legitimately diverge when a manager joins or leaves between
`session_init` and mock-create, or on a co-owned roster. I also changed the
test: T-295-06 constructs the divergence **directly at the `build_settings`
level** (`owners` of 4, `order` of 5 → `teams == 5`) rather than pretending a
corpus reproduces it, and T-295-03 keeps the lakeview route assertions because
those *do* fail first (11/44/11 today, 12/48/12 after).

**B-2 — `UserNotInDraft` must also honour the ownership overlay, or it will
falsely refuse working mocks.**

The plan (§6.3b) specifies raising when `str(user_owner_id) not in
resolved_order`. That is incomplete. `owner_of`
(`mock_draft_service.py:940-943`) lets the traded-pick **ownership overlay win
over the slot order**, so a manager who traded away his own slot's pick and
acquired someone else's is legitimately on the clock while absent from `order`.
Raising on `resolved_order` alone converts a working mock into a refusal —
which is the same class of harm as the silent exclusion, just louder.

*What I did:* PRD **R8.2/R8.3** requires the check to be
`user_owner_id in resolved_order OR user_owner_id in resolved_ownership.values()`,
placed **after** `resolved_ownership` is built (`:1016`) and before the `return`
(`:1017`). T-295-06 asserts both arms: `order=[a,b,c,d], user="zz"` raises;
the same call with `ownership={"3": "zz"}` **does not**.

> ~~This is not hypothetical on the operator's own data. In
> `lakeview-complete`, the operator's round-1 pick **is** an acquired one:
> `draft_order` puts him at slot 6, his own 1.06 was traded to roster 7, and he
> holds roster 4's slot-10 pick. His first turn is **pick 10**, purely by
> overlay.~~
>
> **RETRACTED in Round 3 (Planner J-5).** Every fact in that paragraph is
> true and **none of it supports the clause** — being on the clock via an
> acquired pick and being *absent from* `resolved_order` are different
> properties. The clause survives on the contract argument alone; the real
> shape that triggers it is the co-owner (J-6/R15), which nobody had found
> yet. Struck rather than deleted: this log is an audit trail, and a builder
> reading B-2 must see the correction, not a clean paragraph. Full reasoning:
> [Round 3 § M-5](#m-5--j-5-accepted-the-clause-stands-my-justification-does-not).

**B-3 — R1 must skip an empty caller id, which is what makes the guard
reachable.**

The plan does not say what to do when `sess["user_id"]` is missing.
`server.py:11782` coerces it to `""`. Appending `""` to `owners` would create a
phantom team nobody controls **and** would make the new refusal rung
permanently unreachable — dead code by construction.

*What I did:* PRD **R1.1** requires the caller to be appended only when the id
is non-empty, and **R7.6** states the consequence: post-repair the
`user_not_in_draft` rung fires exactly for a session carrying no user id. That
is a coherent, testable answer to the plan's open question 2 (*"confirm the rung
is not dead code"*) — it is reachable, it is asserted (T-295-09, T-295-11), and
it is the honest answer for a session we cannot place in a draft.

**B-4 — The Maestro precondition is NOT "one profile entry", and the plan
repeats an estimate the previous batch already disproved.**

[`plan.md`](./plan.md) §9 Tier 3 says *"Clear the `standard.json` profile blocker
(one league entry — it repairs `d1`/`d2` as a side effect)"*, and §7 lists
`profiles/standard.json` as an in-scope file. `living-memory/TEST_LEDGER.md`
(2026-08-10, batch #289–#294) already records the opposite verdict: *"The build
agent's 'one `leagues[]` entry' estimate was checked and does not hold; this is
real seeder work."*

I checked it myself and agree with the ledger. The profile seeder
**synthesises** leagues with generated members and rosters
(`backend/tests/fixtures/seed_ui_test_db.py:383-399`); ffv3 is a *recorded*
Sleeper corpus reached through the `FTF_SLEEPER_FIXTURES_DIR` seam (`:1048`).
Adding a `leagues[]` row produces a synthetic league with no Sleeper draft
object, which the Draft Room cannot render. Closing this means implementing the
"corpus merged into the fixture dir" step the flow headers assume, or
synthesising a draft — either is its own item.

*What I did:* removed `profiles/standard.json` from this fix's file ownership;
kept the `d3` **assertion** (T-295-12) so it is ready when the profile work
lands; and declared the blocker honestly in
[`scope.md` §3.1](./scope.md#31-the-d3-blocker-is-real-pre-existing-and-this-fix-does-not-close-it)
with its consequence stated where the operator cannot miss it — the Tier-1
gate's feature flow cannot run, for the **second batch running on this same
feature**, which promotes the ffv3 + Dependables live-league checks from
"nice-to-have" to the batch's real gate.

**B-5 — The `_mock_capability` off-by-one is not a G2 *divergence* today; it
becomes one if R4 is skipped.**

The plan's §2 table frames `server.py:11621` as *"the G2 probe reports `teams`
one short, so a genuine 4-team league is refused `league_too_small`"*. True —
but the **create route reads the same short list** (`:11566` → `:11826`), so
probe and create currently agree, wrongly, in lockstep. The probe is not lying
relative to the create route; both are wrong by one.

*Why this matters for the build:* it means **R4 is not optional polish — it is
the thing that keeps R1 from breaking G2.** Fix `:11566` without `:11621` and a
4-owner league becomes creatable while the probe still refuses it, which is a
new, real divergence introduced by the fix. PRD **§2.3** and **R4** say this
explicitly, and T-295-08 asserts probe and create agree *and* are correct.

**B-6 — Added a requirement the plan does not mention: the caller's team must
render as a name (PRD R6).**

R1 makes the caller appear in `order[]` for the first time, and every `order[]`
row carries `owner_username` from `ctx.usernames`. `_mock_usernames`
(`server.py:11488`) is built from the session member list — which by definition
excludes him — merged with `load_league_members`. I traced this rather than
assuming: `session_init` writes the caller as the **first** row of
`all_members_for_db` (`server.py:14853-14860`), so he resolves through the
`stored` branch (`:11524-11529`) and **no code change is needed**.

I specified it as a requirement anyway (**R6**, verified by T-295-01 and the
Dependables live check) for two reasons: so a build agent verifies it instead of
"fixing" it, and because MFL is where the D-16 no-raw-id guarantee is sharpest —
the caller's franchise is the one non-synthetic id in the league.

### C. Adopted verbatim

Everything not listed in B, and specifically:

- **The root cause and its file:line.** `server.py:11566`, with `:11544` /
  `:11545` / `:11582` / `:11621` as the same omission at four sites. Re-verified
  line by line.
- **The five client filter sites and the two `session_init` refusal sites.** All
  seven checked individually; all seven exact
  ([`prd.md` §2.1](./prd.md#21-primary--backendserverpy11566)).
- **R2/R3 must move as a pair.** The plan's INV argument is correct: fixing only
  one makes `_available` (`mock_draft_service.py:1071`) derive different pools
  for create and resume, shifting every recap `consensus_rank`. T-295-07 pins
  them as a pair.
- **All six rejected alternatives**, with the plan's reasoning. In particular
  the rejection of a client-side fix (five builders; the field's name and
  contract both say *opponents*; every installed 1.12.0 build would keep the bug
  forever) and of widening `session_init` (~20 `.members` consumers; FB #41
  deliberately went the other way).
- **§5's diagnosis of why #291's verification missed it** — all four gaps,
  re-verified. Gap 4's aside is correct and worth keeping:
  `seed_ui_test_db.py:529-533` builds `opponents` with `if uid != world.app_uid`
  and fills to `total_rosters: 12`, i.e. **the QA profile does reproduce the
  production shape** — the profile blocker (B-4) is the only reason it never
  ran.
- **The sign-off condition.** A mock started and a pick taken on **ffv3 and
  Dependables**, carried into the PRD as a hard done-criterion
  ([`prd.md` §9.4](./prd.md#9-done-criteria)), not a recommendation.
- **The Draft Room is not defective and must stay byte-identical.**
- **`docs/api-reference.md:426` is stale and this batch owns correcting it.** I
  verified it is the **only** remaining wrong location:
  `git grep -n CPU_MODEL_VALIDATED -- docs config` returns one bad hit.

### D. Citation corrections

The plan's citations are dense and mostly exact. Six drifted; none changes a
conclusion.

| plan cites | actual | note |
|---|---|---|
| `test_mock_draft.py:938-942` (the inverted session fixture) | **`:936-945`** (`@pytest.fixture` at 936, `league=` at 940-942, `sess=` at 943-945) | the substance is exactly right |
| `mobile/src/api/mockDraft.ts:36-40` (`MockEmptyReason`) | **`:35-39`** | off by one |
| `mobile/src/screens/DraftRoomScreen.tsx:296-345` (`mockBlock`) | **`:298-354`** (`const mockBlock` at 298; deps array at 355) | 296-297 is the ordering comment, which is worth citing separately |
| `mock_draft_service.py:446-475` (`capability`) | **`:446-476`** | trailing brace |
| `mock_draft_service.py:958-1030` (`build_settings`) | **`:958-1031`** | trailing brace |
| `plan §1.2`: lakeview "user at index 4"; post-fix "on_the_clock.is_user at pick 11 (its traded slot)" | **index 5 (slot 6)**; first user turn at **pick 10** | Derived from the corpus: `draft_order["313560442465169408"] == 6`; round-1 traded rows put roster 2's own pick with roster 7 and roster 4's slot-10 pick with roster 2. The *shape* of the claim (he holds an acquired pick, not his own slot) is correct; the numbers are not. T-295-03 uses the corrected values with the derivation in a comment. |

Everything else I checked was exact, including `server.py:11566`, `:11545`,
`:11582`, `:11621`, `:14374`, `:14380`; `mock_draft_service.py:989`, `:998-1000`,
`:1026`, `:1061`, `:91`; `auth.ts:377`/`:465`; `espn.ts:180`;
`platformLink.ts:280`; `web/js/app.js:820`/`:2562`; and
`test_league_total_teams.py:1-20` (which does name ffv3 and does record both the
under- and over-count failure modes).

### E. Decisions where the plan left a choice open

| # | Decision | Reasoning |
|---|---|---|
| E-1 | **No new feature flag.** Ship on `draft.mock`. | A default-OFF flag ships the bug unfixed; a default-ON flag is one nobody would ever flip, since flipping it restores "no user can pick". The kill switch already exists and is correctly sized. Alternative shape specced in [`scope.md` §2.1](./scope.md#21-should-the-fix-ship-behind-a-new-flag--no) if the operator disagrees. |
| E-2 | **Analytics waived (c), again.** | `backend/analytics_taxonomy.py` is DEFAULT-DENY and carries **zero** `mock_*` events (verified). A `track()` call without registration records nothing while looking live. Same waiver the #290 batch took. Spun out, with this bug as its strongest argument: a 100 % failure was invisible for two days. |
| E-3 | **`user_not_in_draft` placed last on the ladder.** | Adopted from the plan, and I agree with its reasoning verbatim (`mock_draft_service.py:431-435`): a 2-team league should hear its size problem first, and this joins `league_too_small` as a state the user cannot act on. |
| E-4 | **Keyword-only parameter with a `None` default on `start_refusal`.** | Adopted. `None` preserves today's three-rung behaviour byte-for-byte, so the ~8 positional callers and the route need no edits to compile. T-295-05 asserts the two-positional-argument form is unchanged. |
| E-5 | **`ownerless roster → 11-team mock`, not a "vacant" CPU seat.** | The plan's own recommendation, adopted: inventing a manager is worse than omitting an empty chair, and a vacant seat needs a name, a persona and a rendering decision it does not have. Raised to the operator as O-1 because it is a visible number. |
| E-6 | **The caller gets no entry in `_mock_personas`.** | Not in the plan. `build_settings` (`:1002-1006`) already fills a default persona for every owner, and `advance_cpu` returns at the user's slot without ever reading it (`:1181-1182`), so inferring an outlook for a bot that never runs is dead work. Listed out-of-scope in [`prd.md` §7.2](./prd.md#72-also-out-of-scope). |
| E-7 | **The `league.members` convention gets a written recommendation with measured blast radius, and stays out of scope.** | The plan asked; `docs/coding-guidelines.md` §3 answers. Written up in [`prd.md` §7.1](./prd.md#71-the-leaguemembers-excludes-the-caller-convention-itself) as a backlog item with the ~20-consumer measurement, so it is a real proposal rather than a shrug. |
| E-8 | **Sim-gate tier 1 with a requested deviation**, not tier 3. | The mobile delta renders a `mockBlock` arm and screen copy, which is "mobile screen / state change" on the `docs/runbook.md` matrix. The deviation is for the three unrunnable draft flows only; the 11 smoke flows are runnable and required. |

### F. Where I did NOT independently verify

Stated so the Planner can close them rather than assume they were checked.

1. **The two live probe runs in [`plan.md`](./plan.md) §1.1/§1.4.** I re-derived
   their inputs and their arithmetic from the committed corpora and the shipped
   code, and everything I could check statically agrees (owner counts, the
   `draft_order: null` pin, the contiguity guard, the shuffle branch). I did not
   re-execute the probes. The one number I *did* recompute and found wrong is
   D's last row (lakeview slot/pick).
2. **`accounts.py:513` (`migrate_board_data`) and `server.py:10489-10492` (MFL
   `platform_my_team → link_user`).** Both exist at the cited lines; I did not
   trace their full behaviour. They support the plan's "no `acct_` key is in
   play" argument, which I reached independently by a different route (the
   fixture ids and the session id are the same issuer and the same shape), so
   nothing load-bearing rests on them.
3. **`git show 8e146a3:backend/server.py` line 10277.** Quoted from the plan. The
   conclusion it supports — that the defect is original to the feature and not
   introduced by `6c304c7` — is independently supported by `6c304c7`'s own diff,
   which the plan also cites and which is cheap for the Planner to re-run.

### G. Open questions for the Planner's review

1. **Do you accept B-1?** If the `teams` rule is *not* independently
   load-bearing post-R1, is R5 still worth the change under
   coding-guidelines §2 (simplicity first)? My answer is yes — `teams` is the
   wrong quantity and `owner_of` indexes `order`, so the two structures must be
   the same width by construction rather than by luck — but it is a judgement
   call and you should push on it.
2. **Do you accept B-2's ownership clause?** It makes the backstop slightly less
   simple in exchange for not false-refusing a manager who owns only acquired
   picks. The lakeview corpus shows this is a real shape on the operator's own
   data, not a hypothetical.
3. **Is R7 worth having at all, given B-3?** Post-repair the rung fires only for
   a session with no `user_id`. I argue yes — the guard's job is to be
   unreachable, and the *class* of defect here is "silently produced a mock the
   user is not in", which a repair alone leaves intact. But if you think a rung
   that fires only on a malformed session is ceremony, say so; the `build_settings`
   raise (R8) is the load-bearing half and could stand alone.
4. **Should the fixture rewrite (T-295-02) be in this batch?** It will churn the
   expectations of every route test in `test_mock_draft.py`, because those tests
   currently short-circuit at `league_too_small` and will stop doing so. That is
   the point — but it is also the largest diff in the change, and it is worth an
   explicit second opinion on whether it lands here or immediately after.
5. **Have I under-scoped the mobile delta?** I specified one `mockBlock` arm,
   one `emptyCopy` arm and one union member, and explicitly left the
   `capability`-probe wiring out (R9.4 — `git grep capability -- mobile/src`
   finds no consumer, so refusals are only discoverable after a POST). If you
   think the entry card should read the probe *in this fix*, argue it.
6. **Is the §5 sim-gate deviation defensible, or should this batch block on the
   profile-seeder work?** I recommend deviating and shipping the repair, with
   the ffv3 + Dependables live checks as the gate. The counter-argument is
   strong and I want it on the record: this is the second consecutive batch on
   this feature to ship without a simulator run, and the first one is the reason
   this defect exists.

### H. Open items for the operator

Carried into [`scope.md` §7](./scope.md#7-open-items-for-the-operator) and
[`prd.md` §10](./prd.md#10-open-items-for-the-operator) — summarised here:

- **O-1** ffv3's ownerless roster ⇒ an 11-team mock in a 12-roster league.
  Recommend leaving it at 11.
- **O-2** Accept the analytics waiver? Recommend yes, spin the mock funnel out.
- **O-3** Accept the sim-gate deviation, making ffv3 + Dependables the real
  gate? Recommend yes — with the uncomfortable counter-argument stated.
- **O-4** Confirm who applies the three `docs/api-reference.md` edits. The
  `:426` blockquote was missed once already by the batch that claimed to correct
  five such locations.

---

## Round 2 — Planner review

**Date:** 2026-08-10 · **Base:** `origin/main` @ `2e0b2c7` ·
**Method:** every disputed claim re-executed against the committed corpora
through the real route and the real resolvers, not re-read. Probe transcripts
are quoted inline.

**Standing rule for this review.** The previous batch on this feature shipped a
confidently wrong analysis because it had tests that could not fail. So the only
question I asked of each requirement was: *would its test go red on `2e0b2c7`,
and would it go red on a plausible wrong fix?* Three requirements fail that
question. They are objections J-1, J-2 and J-4.

### I. Conceded — the Author's six departures, judged

**B-1 — CONCEDED in full. My §6.2 trigger was wrong.** I re-ran the assigned-order
path with the post-R1 owner set:

```
=== build_settings (post-R1 owners), lakeview-complete ===
teams: 12 | len(order): 12 | len(slots): 48
```

And the ownerless-roster case resolves exactly as the Author reasoned: a vacant
slot yields `original_user_id: None` (`draft_board_service.py:763-766`), which
`_mock_real_draft:11677` skips, so `by_slot` is either non-contiguous — and
`:11681` drops the order into `randomized`, where `resolved_order is owners` —
or contiguous `1..11`, where `len(order) == len(owners) == 11`. Either way the
truncation cannot occur. The re-justification of R5 as a structural invariant is
the honest framing and I adopt it. (It is also more load-bearing than the Author
knew — see J-7.)

**B-2 — arithmetic CONCEDED, justification REJECTED. See J-5.** The numbers are
exactly right and mine were ambiguous: I never named which user §1.2 measured
(my probe took `rosters[0].owner_id` = `852266560109293568`, slot 5), and the
Author correctly read it as a claim about the operator. Verified:

```
draft_order["313560442465169408"] == 6      # slot 6, roster 2
OPERATOR owns picks: [10, 26, 39, 42, 43, 48]   FIRST TURN: 10
owner_of(6) == 852254555294019584           # his own 1.06, traded away
```

T-295-03's tripwire value of **10** is correct. The *reasoning* attached to it is
not.

**B-3 — CONCEDED, and the rung is more reachable than the Author argued.** R1.1
is right and the phantom-owner hazard is real. The Author calls the empty-id path
a malformed session; it is reachable through a shipped route:
`server.py:14297` is `body.get("user_id", DEMO_USER_ID)`, which returns `""` for a
*present-but-empty* key, and the `missing_user_id` guard at `:14294` only fires
`if request.headers.get("X-Session-Token")`. A tokenless `POST /api/session/init`
with `{"user_id": ""}` therefore mints a session with `user_id == ""`. R7.6 is a
real path, not ceremony. Add that citation to R7.6.

**B-4 — CONCEDED in full, and I was repeating a disproved estimate.**
`living-memory/TEST_LEDGER.md:22` reads verbatim: *"The build agent's 'one
`leagues[]` entry' estimate was checked and does not hold; this is real seeder
work. Pre-existing, unfixed, named."* My §9 Tier 3 asserted the opposite and
listed `profiles/standard.json` as in-scope. Removing it is correct; §8.3's
statement of the consequence — second consecutive batch on this feature with no
runnable feature flow — is better than anything in my plan and should stay
exactly as written.

**B-5 — CONCEDED.** Verified: `_mock_capability:11621` and
`_mock_league_context:11566` build the identical list, so probe and create are
wrong in lockstep and there is no G2 divergence today. The Author's inversion is
the important part: **R4 is what stops R1 from creating one.** My §2 table framed
`:11621` as an existing divergence; it is not.

**B-6 — CONCEDED as a requirement.** The trace is right — `session_init` writes
the caller as the first row of `all_members_for_db` (`:14853-14860`) and
`_mock_usernames`'s second loop picks him up from `stored` (`:11524-11529`)
because `seen` only holds session member ids. Specifying it so a builder verifies
rather than "fixes" it is the correct call. R6.1's test, however, is booby-trapped
— J-3.

**Also verified exact, and adopted:** all six citation corrections
(`test_mock_draft.py:936-945`; `mockDraft.ts:35-39` — the union does end
`| (string & {})`; `DraftRoomScreen.tsx:298-354` with the ordering comment at
296-297 and the deps array at 355; the two trailing-brace corrections).

### J. Objections

---

#### J-1 — **BLOCKING.** R8.5 has no test, and its failure mode is a silent 500.

PRD §4 R8 says *"Verified by: T-295-06, T-295-10."* T-295-06 is a pure
`build_settings` unit test (it asserts the exception is *raised*); T-295-10 is a
mobile JSX check. **Nothing exercises R8.5 — the route catching `UserNotInDraft`
and returning the typed-empty.**

That is not a cosmetic gap. `backend/server.py:2071` registers
`@app.errorhandler(Exception)`, so if the builder adds the raise in
`build_settings` and forgets the `try/except` around `server.py:11841`, the route
returns a generic **500** — and no test in §8.1 notices. The requirement most
likely to be half-implemented is the one with no coverage.

**Exact change:** add **T-295-13 (Route)** — monkeypatch `server._mock_real_draft`
to return `{"order": [<every owner except the caller>], "order_source":
"assigned", "traded_slots": {}, "type": "linear"}` on the production-shape ffv3
session, `POST /api/mock-draft`, assert exactly
`200 {"schema": 1, "empty": true, "reason": "user_not_in_draft"}` and no other
keys. Demonstrate red first: red must be **500**, not a wrong reason string. Then
correct R8's "Verified by" line to `T-295-06, T-295-13`.

---

#### J-2 — **BLOCKING.** T-295-02's fixture rewrite breaks two shipped tests, and one of them breaks by *passing*.

PRD §8.1 T-295-02 rewrites the shared `session` fixture and the log's open
question 4 acknowledges churn, but neither names what churns. I enumerated it:

| test | line | what happens post-rewrite |
|---|---|---|
| `test_w2_20_g2_the_capability_probe_answers_without_starting_a_mock` | asserts `cap["can_start"] is False` (`:1242`) and `cap["reason"] == REASON_LEAGUE_TOO_SMALL` (`:1247`) | **fails loudly** — a ≥4-member fixture makes `can_start` true |
| `test_the_abort_criterion_is_enforced_at_the_route` | `:1036-1052`, whose own comment at `:1048` reads *"this fixture league is under MOCK_MIN_TEAMS"* | **keeps passing** — its assertions (`reason != "cpu_model_unvalidated"`, `body["schema"] == 1`) are satisfied by a successfully created mock, so the test survives while its stated premise silently becomes false |

The second row is the exact pattern §8.2 exists to prevent, arriving through the
fix's own largest diff. And the first row's obvious "repair" — flipping the
assertion to `can_start: True` — **deletes the only route-level `league_too_small`
coverage in the suite.**

**Exact change:** PRD §8.1 T-295-02 must (a) name both tests; (b) require the
`league_too_small` route coverage to be *relocated* to a dedicated small-league
fixture, never deleted; and (c) require the abort-criterion test's premise comment
to be re-derived or the test re-pointed at a fixture that still satisfies it. Add
to §8.2: *"a test whose comment states a premise the rewritten fixture no longer
satisfies must be re-pointed or rewritten, not left passing."*

---

#### J-3 — **BLOCKING.** R6's assertion in T-295-01 fails on *correct* code unless the test seeds `league_members`.

T-295-01 requires *"his `order[]` rows carry a non-null `owner_username` with no
`mfl:` (R6)"*. Trace it: `_mock_usernames` (`server.py:11506-11530`) has two
loops — the first over the session `members`, which by construction excludes the
caller, and the second over `stored = load_league_members(league_id)`. In a pytest
run against a fixture league id, `load_league_members` returns `[]`, so `stored`
is empty, the caller appears in neither loop, and `state_payload`
(`mock_draft_service.py:1280`) emits `owner_username: None`.

So a builder who implements R1–R6 perfectly watches T-295-01 fail on the R6
clause, and the nearest "fix" is to edit `_mock_usernames` — which **R6.1
explicitly forbids** (*"No code change is expected"*). A test that fails on a
correct fix is as dangerous here as one that cannot fail.

**Exact change:** T-295-01 must specify that the test seeds a `league_members`
row for the caller (or monkeypatches `load_league_members`) mirroring
`all_members_for_db`'s first row (`server.py:14853-14860`) — `{"user_id":
OPERATOR, "username": <display name>, "display_name": …, "player_ids": …}` — and
that this seeding is what makes R6 an assertion about `_mock_usernames`'s
**existing** merge rather than about the test's own monkeypatch. Add the negative
half too: with `load_league_members` raising, `owner_username` is `None` and the
payload still renders (R6.2).

---

#### J-4 — **NON-BLOCKING, but the PRD states something false.** R5's "Verified by: T-295-03" is wrong.

PRD §3 R5 lists *"Verified by: T-295-03, T-295-06."* Measured post-R1 on
`lakeview-complete`: `teams: 12 | len(order): 12 | len(slots): 48`. Removing R5
changes none of those three numbers, because `len(owners) == len(order)` there —
which is the Author's own B-1 finding. **T-295-03 cannot go red on R5's absence.**
It verifies R1.

**Exact change:** R5's "Verified by" becomes **T-295-06 only**, with a one-line
note that R5's sole failing-first coverage is a synthetic `build_settings` unit
test *because no committed corpus reproduces the divergence* — which is exactly
what B-1 established. Leave T-295-03 under R1. Getting this right matters more
than it looks: a requirement that claims coverage it does not have is how the last
batch convinced itself.

---

#### J-5 — **NON-BLOCKING.** B-2's ownership clause is right; its stated justification is measurably false.

The log asserts: *"This is not hypothetical on the operator's own data. In
`lakeview-complete`, the operator's round-1 pick **is** an acquired one … His
first turn is **pick 10**, purely by overlay."* Both facts are true and neither
supports the clause. I measured the thing the clause actually guards:

```
=== _mock_real_draft, lakeview-complete ===
OPERATOR in order? True | index: 5
owners missing from order[]:            set()
traded-slot owners NOT in order[]:      set()
```

The operator is at `order[5]`. Being *on the clock* via an acquired pick and being
*absent from* `resolved_order` are different properties, and only the second would
trigger R8. In Sleeper's model they cannot coincide: `order` is round 1's
**original** owners across all N slots (`server.py:11670-11678`), so every
rostered manager is in it by construction and "owns only acquired picks" is
unreachable.

**Keep the clause** — it is two comparisons, and MFL's grid could emit the shape
if we ever read it. **Change its label.** Exact change: in R8.3 replace *"a user
who owns only acquired picks is legitimately on the clock while absent from
`order`"* with *"defensive: no current resolver emits an ownership entry for an
id absent from `order` (verified on `lakeview-complete`: both difference sets are
empty), but `build_settings` is public and `owner_of` lets ownership win, so the
invariant is stated where the lookup happens."* Delete the "not hypothetical"
sentence from B-2. T-295-06's second arm stays as a **contract** test, labelled as
such, not as a regression test for a reproduced shape.

---

#### J-6 — **BLOCKING.** A legitimate user *can* be absent from `order` — a co-owner — and the refusal copy tells him to do something that cannot work.

This is the orchestrator's question ("can the rung fire spuriously?"), and the
answer is on the operator's own league.
`backend/tests/fixtures/draft/ffv3-predraft/league/1312140920132497408/rosters.json`
roster 2 carries `co_owners: ["867866820202364928"]` — and that id is a real
member of that league's `users.json` (`lofman`), i.e. a user who can sign into
FTF. `git grep -n "co_owners" -- backend mobile web` returns **fixture hits only**:
nothing in the product reads the field.

Trace him post-fix. `session_init`'s roster lookup keys on `owner_id`
(`mobile/src/api/auth.ts:375`), so he matches no roster and no client filters him
out of anyone's `opponent_rosters`; post-R1 `owners` is 11 primaries **plus
himself**. On ffv3 the order is randomized, so `resolved_order is owners` and he
is fine. **On any assigned-order league, `resolved_order` names only primary
owners — he is absent — and R8 raises. A working manager gets a hard refusal.**

Pre-fix he got a silent CPU-drafted board; post-fix he gets a wall. That is a
different failure, not a fixed one. And §5.3's copy — *"Re-sync the league from
the League tab and try again"* — is an instruction that **can never succeed** for
him, because re-syncing reproduces the same owner set every time. Advice that
cannot work is worse than a generic message.

**Exact change, three parts:**
1. §5 gains a named subsection *"When this fires"* listing the co-owner path with
   the `rosters.json` citation, alongside the empty-`user_id` path.
2. §5.3's copy must not prescribe an action that cannot resolve the state. Use
   the shipped register of the other five arms — state the fact, offer no false
   remedy.
3. **Decide R8's behaviour explicitly.** My recommendation: when the caller is in
   `owners` but absent from an *assigned* `resolved_order`, **degrade to the
   randomized branch and label it `order_source: "randomized"`** rather than
   refuse — that is the shipped KD-6 honest-degradation idiom
   (`server.py:11636-11638`, `:11684-11687`), it keeps a usable mock for
   co-owners, and it leaves `UserNotInDraft` raising only when even the shuffle
   cannot place him (i.e. he is not in `owners` either), which makes R7 and R8
   guard genuinely disjoint states. If the Author prefers the refusal, that is
   defensible — but it must be a **recorded decision with the co-owner case named
   as its cost**, not an unnoticed consequence. Either way it needs a test:
   co-owner session + assigned order → asserted outcome.

---

#### J-7 — **NON-BLOCKING (pre-existing), but it settles the Author's open question 1.** The create route takes owners from the SESSION league and the order from the REQUESTED league.

`_mock_resolve_league` (`server.py:11738-11740`) accepts **any** league with a
`get_league_draft_context` row, and that function (`backend/database.py:7458-7476`)
selects on `sleeper_league_id` with **no user or session scoping**. But
`_mock_league_context` (`:11543-11544`) reads `sess["league"].members`
irrespective of which league was asked for. A `POST /api/mock-draft
{league_id: <B>}` on a session initialized for league A therefore builds owners
from A and the order from B.

This repo fixed the identical class three commits ago — `5cf81e5` *"outlook:
resolve platform from the requested league_id, not the session"*.

Why it matters here: it is a real, non-synthetic producer of
`len(owners) != len(order)`. **The Author's open question 1 — "is R5 a guard
nobody can trip?" — is answered: no.** R5 has a live trigger; it just is not the
one my plan named.

**Exact change:** either add a one-line guard to the create arm (requested
`league_id` must equal `str(sess["league"].league_id)`, else the existing
`league_not_found` 404), or record it in §7.2 as a named out-of-scope item with
this citation and `5cf81e5` as precedent. Do not leave it unstated — it is the
strongest justification R5 has.

---

#### J-8 — **NON-BLOCKING. Scope discipline: confirmed clean.**

I checked for the drift the orchestrator flagged. The PRD does **not** widen the
`league.members` convention: §7.1 rejects it with the measured blast radius, no
requirement writes to `sess["league"].members`, and no client builder is touched.
R1–R6 land in `_mock_league_context`, `_mock_context_from_row`, `_mock_capability`
and `build_settings` only. §7.2's last row correctly forbids any
`draft_board_service.py` edit. Confirmed, and worth stating so a build agent does
not reopen it.

**Also confirmed empirically rather than from the doc (§5.2's D10 claim):**
`mobile/src/api/mockDraft.ts:35-39` ends `| (string & {})`, so an unknown reason
is a legal value of `MockEmptyReason` and cannot break `tsc`; and
`MockDraftScreen.tsx:785-796` has a real `default:` arm. A shipped 1.12.0 build
degrades to generic copy. The claim holds.

### K. Answers to the Author's open questions

| # | Answer |
|---|---|
| 1 | **Keep R5.** Not on my original grounds, which B-1 correctly demolished, and not only on the "wrong quantity" argument — on J-7's cross-league path, which is a live trigger. But fix J-4: stop claiming T-295-03 covers it. |
| 2 | **Accept the clause, reject the justification.** J-5. Two comparisons, cheap, guards a shape no current resolver emits — label it that way. |
| 3 | **Yes, keep R7** — and it is less ceremonial than you argued: the empty-`user_id` path is reachable through `session_init` (B-3 above). You are right that R8 is the load-bearing half. If J-6 part 3 adopts the randomized-degradation option, R7 and R8 become cleanly disjoint, which is a better shape than either alone. |
| 4 | **Yes, in this batch — it is the single highest-value item in the change.** The inverted fixture is *why* #291 shipped wrong. Deferring it means the batch's headline test is the only thing standing between us and a repeat. But it must land with J-2's enumeration attached, or the churn re-creates the disease. |
| 5 | **No, correctly scoped.** Leaving the probe unwired (R9.4) is right: `git grep capability -- mobile/src` has no consumer, so wiring it is a feature, not a fix. One caveat — with the probe unwired, `user_not_in_draft` is only ever seen after a POST, which makes J-6's copy the *entire* user-facing surface of this refusal. That raises the bar on getting the copy right, not on wiring the probe. |
| 6 | **Deviate and ship, with one addition.** Your counter-argument is the honest one and I want it recorded as you wrote it. But since `d3` cannot run and the mobile delta is one `mockBlock` arm, the §9.4 live-league checks are the only real evidence — so make them *falsifiable*: the operator must report the **team count on the order rail** and the **pick number of his first turn**, not "it worked". A number can be wrong; a thumbs-up cannot. |

### L. Verdict

**Implementable blind: no — three BLOCKING items first (J-1 R8.5 untested; J-2
the fixture rewrite's silent-pass casualty; J-3 R6's assertion fails on correct
code), plus J-6's co-owner decision, which is a product call the builder must not
make alone. Everything else is sound, the diagnosis is right, and with those four
resolved this is buildable from the PRD without re-deriving anything.**

---

## Round 3 — Author incorporation

**Date:** 2026-08-10 · **Base:** `origin/main` @ `2e0b2c7` ·
**Method:** every blocking claim re-verified against the code before
incorporating it. The Planner's Round 2 is the strongest review in this folder —
it re-ran what it disputed, conceded six of six, and found three real holes in my
own work plus a product defect nobody had seen. All four blockers are **accepted
in substance**; two are accepted with a changed mechanism, for reasons below.

### M-1 — J-1 ACCEPTED in full. R8.5 had no test, and I claimed it did.

**Verified:** `server.py:2071-2077` is `@app.errorhandler(Exception)` returning
`{"error": "internal_error"}` **500** for any non-HTTP exception. So a builder
who implements the raise and forgets the route's `try/except` ships a 500 that
no test in my Round 1 §8.1 would notice.

My Round 1 wrote *"Verified by: T-295-06, T-295-10"* for R8. T-295-06 is a pure
`build_settings` unit test and T-295-10 is a mobile JSX check — **neither touches
the route's `except` arm.** That is a coverage claim I did not check, in the
batch whose entire thesis is that unchecked coverage claims are how #291
shipped. Conceded without qualification.

**Incorporated:** T-295-13 added; R8's *Verified by* corrected to
**T-295-06 + T-295-13**; R8.5 gains an explicit paragraph on *why* the mapping
is kept even once R15 makes it unreachable (the catch-all handler turns a future
regression into a silent 500), plus the rejected alternative (drop the mapping).

**One change to the Planner's mechanism, and it matters.** J-1 specified
monkeypatching `_mock_real_draft` to return an assigned order missing the
caller. **After the J-6 ruling that input no longer raises — it degrades** (R15).
The proposed test would therefore exercise the degrade path and assert a
typed-empty that never arrives: a test that fails on correct code, which is
precisely J-3's disease. T-295-13 instead monkeypatches `server.mds.build_settings`
to raise directly, which tests R8.5 and nothing else and is immune to R15. The
red-first condition is unchanged and is the important half: **red must be a 500**,
produced by building the raise without the mapping.

### M-2 — J-2 ACCEPTED in full, with one narrowing and one addition.

**Verified both casualties, line by line:**

- `test_w2_20_g2_the_capability_probe_answers_without_starting_a_mock` —
  `assert cap["can_start"] is False` at `:1242`, `cap["reason"] ==
  REASON_LEAGUE_TOO_SMALL` at `:1247`. Fails loudly on a ≥4-owner fixture. ✓
- `test_the_abort_criterion_is_enforced_at_the_route` — `:1036-1051`, comment at
  `:1048` reads *"this fixture league is under MOCK_MIN_TEAMS"*, assertions at
  `:1050-1051` are `reason != "cpu_model_unvalidated"` and `schema == 1`, both
  satisfied by a successfully created mock. **Keeps passing; premise becomes
  false.** ✓

The second is the more dangerous finding in the whole review, because it has
**no red-first state at all** — it passes before and after, so no assertion can
catch it. That is why M-2 adds a *process* rule rather than only a test.

**Narrowing I contribute.** J-2 says repairing the first test would "delete the
suite's only route-level `league_too_small` coverage." Correct — but only
**route-level**. `grep -n "LEAGUE_TOO_SMALL" backend/tests/test_mock_draft.py`
returns three hits: `:1247` (route, the casualty) and `:1276`/`:1280`, both
inside `test_w2_20_g2_a_two_team_league_is_refused_as_too_small`
(`:1269-1285`), which builds its owners through `make_ctx` and is
**fixture-independent**. So the service-level rung coverage is already safe and
the relocation only has to serve the route. That makes T-295-15 smaller and
sharper than "build a second full fixture."

**Incorporated:** T-295-02 now names both tests and specifies both repairs —
(a) flip the two assertions and relocate route coverage to **T-295-15**, never
delete; (b) repair the abort-criterion test by **strengthening** it (add
`empty is not True` and `mock_id is not None`, so it asserts the create actually
succeeds) and rewriting the false comment. §8.2 gains the Planner's rule
verbatim as **R-8.2a**, plus two of mine:

- **R-8.2b** — the fixture rewrite lands as its **own commit**, full suite run
  immediately before and after, **every status change enumerated** in
  `TEST_LEDGER.md`. A status diff is the only detector for a test that breaks by
  passing.
- **R-8.2c** — no route-level coverage may be **deleted** to make a rewritten
  fixture pass; it is relocated, and the relocation is named in the commit
  message.

### M-3 — J-3 ACCEPTED in full. My R6 assertion failed on correct code.

**Verified the trace:** `_mock_usernames` (`server.py:11506-11530`) has two
loops — the first over session `members` (which excludes the caller by
construction), the second over `stored = load_league_members(league_id)`. Against
a fixture league id, `load_league_members` returns `[]`, so the caller is in
neither and `state_payload` emits `owner_username: None`.

So Round 1's T-295-01 would have gone red on a **perfect** implementation of
R1–R6, and the builder's nearest repair — editing `_mock_usernames` — is the one
thing R6.1 explicitly forbids. A test that fails on correct code doesn't just
waste time; it **actively steers a builder into breaking the implementation.**
Same severity as a test that cannot fail, opposite sign.

**Incorporated:** T-295-01 now requires monkeypatching `server.load_league_members`
to return the shape `session_init` writes (`server.py:14853-14860`) — caller's
row first, then opponents — before asserting R6. **Monkeypatch rather than a
seeded DB row**, per the #289–#294 ledger's own finding that two mock tests
accumulated rows in the persistent SQLite DB and produced an unreproducible
failure; a self-clearing row is listed as an acceptable alternative. The R6.2
negative half is added: `load_league_members` raising ⇒ `owner_username is
None`, still `200`, no id substituted — which is `_mock_usernames`'s documented
`except` at `:11507-11512`. And the R6 clause gets its own red-first condition,
which Round 1 lacked: **delete the second loop (`:11524-11529`) and the
assertion goes red.**

### M-4 — J-6 ACCEPTED, and the orchestrator's ruling adopted: degrade, do not refuse.

**Verified the finding, which is the best thing in this review.**
`ffv3-predraft/…/rosters.json` roster 2 carries
`co_owners: ["867866820202364928"]`; that id is `lofman` in the same league's
`users.json` (12 users for 11 owned rosters — the co-owner is the twelfth).
`git grep -n "co_owners" -- backend mobile web extension` returns **fixture hits
only**. Every client's roster lookup keys on `owner_id`
(`mobile/src/api/auth.ts:377`), so he matches no roster, is filtered out of
nobody's `opponent_rosters`, and post-R1 lands in `owners` — while an assigned
`draft_order` names only primary owners.

My Round 1 guard would therefore have converted a **silent failure for a working
manager into a permanent, un-actionable wall**, and my Round 1 copy would have
told him to re-sync a league that is not broken. That is a worse outcome than
the bug being fixed, shipped under the banner of fixing it. Fully conceded.

**Incorporated — R15 (new), plus R16.** R15 requires `_mock_real_draft` to drop
the order **and the overlay together** and return `order_source: "randomized"`
when the caller appears in neither `by_slot.values()` nor `traded_slots.values()`.

**Where the degrade lives is my decision, and it differs slightly from J-6's
sketch.** J-6 left the layer open; I put it in `_mock_real_draft`, not
`build_settings`, for three reasons stated in R15.2 — the shipped idiom already
lives there twice (`:11655`, `:11684-11687`, the latter being *literally* the
"drop the overlay with the order" rule R15 needs); doing it inside
`build_settings` would silently discard a caller-supplied `ownership`, which is
surprising for a public pure function; and it keeps the session-shaped question
in the layer holding the session. R15.3 then requires the two layers' predicates
to be **identical**, because a drift between them is either lossy (over-degrade)
or a 500 (under-degrade).

This produces the shape the Planner predicted in K-3: **R7, R15 and R8 now guard
three disjoint states**, and `build_settings`'s raise becomes unreachable from
the route — which is why M-1's mapping needs its own justification rather than
inheriting one.

**R16 added** as the honest residue the orchestrator asked for: under R15 the
co-owner's mock is **one team wider than his league**, with his roster
represented twice (11 teams for a primary owner, 12 for him, same league).
That is pre-existing app-wide breakage that R15 makes *visible* rather than
*worse*, it is named in PRD §7.2 and `scope.md` §6 as a follow-up with an owner
required, and it is explicitly not fixed here.

**§5.3 "When this fires" added** (J-6 part 1) enumerating all three states, and
the copy rewritten (J-6 part 2) from *"Re-sync the league from the League tab and
try again"* to **"We couldn't find your team in this league's draft, so there's
no seat for you to draft from."** The Planner's K-5 caveat is the reason this
matters more than it looks: with the probe unwired, this copy is the *entire*
user-facing surface of the refusal.

### M-5 — J-5 ACCEPTED. The clause stands, my justification does not.

The Planner's measurement is right and mine was a non-sequitur: `order` is round
1's **original** owners across all N slots (`server.py:11670-11678`), so on
`lakeview-complete` both difference sets are empty and "owns only acquired picks
while absent from `order`" is unreachable in Sleeper's model. Being on the clock
via an acquired pick (true of the operator, pick 10) and being absent from
`resolved_order` (not true of him) are different properties. I conflated them.

**Incorporated:** R8.3 relabelled as a **contract guard** with the Planner's
measurement quoted; T-295-06's second arm relabelled a **contract** test rather
than a regression test; the offending sentence **struck in place** in B-2 rather
than deleted — this log is an audit trail, and a builder who reads B-2 must see
the correction. J-5 also asked me to delete it outright; I am declining that one
narrow instruction and saying so here, because silently editing an earlier round
is the documentation equivalent of a test that cannot fail.

**And the irony is load-bearing:** the shape I invented a justification for
turned out to exist — it is the co-owner (J-6). The clause was right for a
reason neither of us had.

### M-6 — J-4 ACCEPTED. R5 claimed coverage it does not have.

Confirmed: post-R1, `teams: 12 | len(order): 12 | len(slots): 48` on
`lakeview-complete` with or without R5, because `len(owners) == len(order)`
there — my own B-1 finding, which I then failed to apply to my own coverage
claim one section later. **Incorporated:** R5's *Verified by* is now
**T-295-06 only**, with an explicit note that no committed corpus reproduces the
divergence and that claiming otherwise is the pattern that shipped three times
last batch.

### M-7 — J-7: DECISION — named follow-up, not a guard in this fix.

The Planner asked for an explicit call either way. I verified the claim (exact:
`_mock_resolve_league` `server.py:11734-11744`; `get_league_draft_context`
`backend/database.py:7458-7476`, no session scoping; `_mock_league_context`
`:11543-11544` reads the session league) and I am **declining the guard**, on
evidence Round 2 did not have:

1. **It would be dead code today.** No shipped caller passes a differing
   `league_id`. `DraftRoomScreen.tsx:160-164` is `paramLeagueId ?? sessionLeagueId`,
   and the only registration that could set the param passes none —
   `TabNav.tsx:496-503` says so in a comment (*"No `leagueId`: the room reads the
   session's active league"*).
2. **It would pre-emptively break a documented design.**
   `DraftRoomScreen.tsx:153-155`: the seasonal Draft tab's multi-league rule
   *"lands on a SPECIFIC league's room, **which may not be the session's active
   one**"*. A 404 is the wrong answer there; the right answer needs a member
   source for the requested league, and the only candidate is rejected in §7.2.
3. It changes an API contract on the route this fix is already changing.
4. `GET /api/draft/board` has the identical property and is untouchable here.

**What I accept:** J-7 is right that this is R5's only **live** trigger, and R5's
justification now says so. I am also precise about what R5 buys there — it makes
a cross-league mock *structurally consistent* (`teams == len(order)`, no silent
truncation), **not correct**, since the owners still come from the wrong league.
Overclaiming that would repeat J-4. Filed as a follow-up in PRD §7.3 and
`scope.md` §6 with `5cf81e5` as precedent.

### M-8 — smaller items

| item | disposition |
|---|---|
| **B-3 citation** (`server.py:14294`/`:14297` — a tokenless `session_init` with `{"user_id": ""}` mints an empty-id session) | **Verified exact and incorporated into R7.6.** The rung is reachable through a shipped route, not only a malformed session — better than my Round 1 framing. |
| **J-8 scope-discipline confirmation** | Accepted, no change. Worth having on the record so a build agent does not reopen §7.1. |
| **K-6 — make the live-league checks falsifiable** | **Incorporated into §9.4**: the operator reports the **team count on the order rail** and the **pick number of his first turn**, not "it worked". A number can be wrong; a thumbs-up cannot. |
| Test-plan column header | Changed from *"Pre-fix behaviour"* to *"Red-first condition — what fails, on what code"*, and §8.2 now distinguishes **pre-fix regressions** from **half-implementation tripwires**. Five of the fifteen tests exercise code that does not exist on `2e0b2c7` and therefore cannot go red on it; pretending otherwise would have produced exactly the unfalsifiable evidence this batch exists to eliminate. |

### N. Verdict — implementable blind: **YES**

All three Round 2 blockers are closed with specified repairs, and the product
call (J-6) is resolved by the orchestrator's ruling and specced as R15/R16.
Every test in §8.1 now carries an explicit red-first condition naming what fails
and on what code, including the five that can only be shown red against a named
half-implementation.

**Nothing is left unresolved between Author and Planner.** Two mechanism changes
depart from the Planner's exact wording and are argued above rather than
assumed — M-1 (T-295-13 patches `build_settings`, not `_mock_real_draft`,
because R15 would otherwise make the proposed test fail on correct code) and M-5
(the retracted sentence is **struck in place**, not deleted, to preserve the
audit trail). If the orchestrator prefers the Planner's original on either, both
are one-line reversions and neither changes what gets built.

**Two operator items remain open and are not mine to decide** — they are stated
as questions in [`scope.md` §7](./scope.md#7-open-items-for-the-operator):
**O-1** the ownerless-roster team count (11 vs 12) and **O-3** the sim-gate
deviation. A build agent must not proceed past them without an answer.
