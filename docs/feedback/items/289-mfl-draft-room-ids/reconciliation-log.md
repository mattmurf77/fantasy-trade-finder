# Reconciliation log — FB-289 (G1)

Dual-agent record for the MFL Draft Room identity fix. Planner authored
[`plan.md`](./plan.md); Author produced [`prd.md`](./prd.md) +
[`scope.md`](./scope.md). Rounds are appended, never rewritten.

---

## Table of Contents
- [Round 1 — Author](#round-1--author)
- [Round 2 — Planner review](#round-2--planner-review)
- [Round 3 — Author incorporation](#round-3--author-incorporation)

---

## Round 1 — Author

**Date:** 2026-08-10 · **Base:** `origin/main` @ `7cea1fa` ·
**Worktree:** `.claude/worktrees/fb-289-294`

### Verification performed

Every load-bearing citation in the plan was re-read from the base commit rather
than inherited. Confirmed: `draft_board_service.py:1049` (`username = {}`),
`:1072` (`owner_username` resolves `None`), `:1087-1089` (hard-coded
`""`/`""`/`None`), `server.py:10462-10476` (`_mfl_board_binding` loads
`league_members` and discards the name columns), `server.py:9201-9207`
(`_sync_mfl_owned_picks`'s `Team {fid}` lookup), `DraftRoomScreen.tsx:1140`
and `:1152`/`:1176` (client fallbacks), the `mfl_league` route fixture's
username-less rows (`test_draft_board.py:931-934`), `draft.mfl == true`
(`config/features.json:151`), and the `mfl-complete` corpus's pick-object key
set. The plan's core diagnosis is correct in every respect.

**Verdict: the plan is accepted as the basis for the PRD**, with three changes
and one addition, below.

### Decisions taken

**D1 — Option A (route injection) adopted; Option B rejected.**
Per the orchestrator ruling in `batch-plan.md` § `backend/server.py` — REGION
ownership. G1 owns `_mfl_board_binding` (~L10411-10493); G2 owns the mock shims
(~L11380+); ~900 lines apart. The PRD specs `BoardRequest.mfl_usernames` filled
inside the loop that already walks `members` — zero extra queries. The defaulted
`members_fn` fetcher is not specced anywhere. *No disagreement with the Planner
here — the plan itself recommended Option A and correctly escalated the
collision rather than assuming it away.*

**D2 — Franchise-name fallback is `Team <franchise_id>`, matching the sibling.**
As the plan proposed. The ladder is `username` → `display_name` →
`f"Team {fid}"`, and `owner_username` stays `null` **only** when the grid states
no franchise (so the client's `Unassigned` remains reachable). PRD R-1/R-2/R-3.

**D3 — Three-tier player-name resolution replaces the plan's "leave `name: ''`".**
See disagreement §1.

**D4 — Spike S-2 is not required before build; it is folded into live QA.**
With a total-precedence fallback that has no bare-id outcome, crosswalk coverage
cannot change the code that must be written — it is a quality number, not a
design input. Per the orchestrator's mid-task ruling it is now measured on the
real Dependables board (PRD §9's counting script + thresholds). Spike S-1
(are 62846's franchise names actually stored?) is likewise demoted: the code
path is identical whether they are or not, and a missing row degrades to
`Team 0001`, which is still a fix. Both are QA measurements, not build gates.

**D5 — Maestro: no authored flow; live-league QA on Dependables (62846) substitutes.**
Per the operator ruling. The scope block states the mechanical reason (no MFL
seam in the harness) *and* names the three pieces a future seam would need, as a
distinct backlog item. The waiver is no longer worded as "untestable".

**D6 — Sim tier 3 confirmed.** Checked against `docs/runbook.md:93-98`. Tier 4
is for backend work mobile does not consume; this changes the values mobile
renders. Two flows: `rookie/d1`, `rookie/d2`.

**D7 — No new feature flag.** `draft.mfl` (already `true`) is the existing
deploy-free rollback lever; wrapping a defect fix in a second switch would ship
a code path whose "off" state is the bug.

**D8 — Analytics waived (no new events), with the existing Draft Room W1 events
named as the observational read.** Surfaced to the operator, not assumed.

### Disagreements with the Planner

**1. Crosswalk miss must not fall through to a raw id — the plan's F2 is overturned.**

Plan §4 F2: *"An MFL id the DP crosswalk did not resolve … leave `name: ""` in
that case. That is honest … the client's existing `pick.name || pick.player_id`
fallback keeps the row visible."* Plan §6 R-4 then concedes: *"the fix may not be
100% on the 'names' half."*

I disagree. `pick.name || pick.player_id` rendering a bare number **is** the
reported bug. Accepting it on the rows most likely to hit — rookies, in a rookie
draft, where the DP crosswalk is weakest — means shipping a fix that fails the
user's literal ask on the population that prompted it. The orchestrator's
directive is explicit on this point, and I would have reached the same
conclusion independently.

The PRD therefore specs three tiers (contract in §4): our `players` row →
DP crosswalk name/position → `Player <mfl_id>`. There is no input for which the
payload emits `""` or a bare id.

**2. `Crosswalk.by_mfl_id` should be used, not shelved.**

Plan §4 rejects it: *"carries no `team`, uses DP's name formatting rather than
ours (a second name source on one screen), and requires threading a third map
through `BoardRequest`."*

Each objection is real but small, and the plan weighed them against a benefit it
had already discounted by accepting outcome (1):

- *No `team`*: true, and accepted. The row reads `RB Cam Skattebo` without
  ` · ARI`; `DraftRoomScreen.tsx:1153` already renders the team suffix
  conditionally. A name without a team beats a number without a name.
- *A second name source*: dissolves under total precedence. Tier 2 is consulted
  **only** when tier 1 produced nothing, so the two can never disagree about a
  rendered row. This is a fallback, not a competing source.
- *A third map through `BoardRequest`*: it is the same injection the module has
  always used, and — decisively — `by_mfl_id` is **already on the object the
  binding already fetches** (`_shared_crosswalk()`, `server.py:10479`). No new
  query, no new network call, no new import. Reading
  `espn_service._parse_crosswalk_rows` (`:590-632`), `by_mfl_id` is inserted at
  `:612`, *before* the `if sid in ("", "NA"): continue` guard at `:613-614`
  (`by_mfl_sleeper` is filled only at `:619`), so its coverage is a
  **strict superset** of `by_mfl_sleeper`'s — a brand-new rookie present in DP
  but not yet mapped to a Sleeper id is precisely the row tier 1 misses and
  tier 2 catches. That is the exact failure mode the plan's own R-4 flagged.

Cost of the change: about four lines. I judge it clearly worth it, and it is why
D4 can demote the spike.

**3. Minor — the plan under-weights the "from —" artifact.**

Plan §10.1 keeps `original_username` null for MFL (agreed — parsing `comments`
prose is not a contract). But traded MFL rows then render a literal
`from —` at `DraftRoomScreen.tsx:1143`, which a user reading this fix's release
note may reasonably file as "still broken". PRD §7.1 names it explicitly and
notes the honest remedy is client-side (suppress the suffix when
`original_username` is null) — which would make this sim Tier 1, so it stays
out of scope. Flagged so the operator is not surprised.

### New finding, not in the plan

**Id-space collision hazard — `fetchers.players` must be queried only with
crosswalked ids (PRD R-7, test T-289-06).**

The natural implementation of F2 is `fetchers.players([p["player_id"] for p in
picks])`. But `player_id` is `pid_map.get(mfl_pid, mfl_pid)`
(`draft_board_service.py:1086`) — it holds the **raw MFL id** whenever the
crosswalk missed, and MFL ids and Sleeper ids are both bare numeric strings in
an overlapping range (the committed `players-bulk` fixture alone holds Sleeper
ids `4034` and `13287`; MFL ids for non-rookies sit squarely inside that band).
A raw MFL id can therefore match a real, unrelated `players` row and render a
**different player's name on the pick** — strictly worse than the bug being
fixed, and silent.

The guard: build the lookup list only from picks whose `mfl_pid` is present in
`req.mfl_player_ids`. Two useful side effects — when the crosswalk is empty the
list is empty and **no** query is issued at all (R-13), and the guard is cheap
enough to be unconditional.

The plan does not mention this. It is the single most important addition in
this round.

### Open for the Planner's adversarial pass

1. Is `Player <mfl_id>` the right terminal string, or is there a better
   placeholder? I chose it for exact symmetry with the shipped `Team <fid>`
   convention and because it keeps the row diagnosable and greppable (which is
   what makes PRD §9's coverage count mechanical). Alternatives considered and
   rejected: `"Unknown player"` (throws away the only identifier we have) and
   `""` (the plan's proposal — see disagreement 1).
2. Is the 10% tier-3 threshold in PRD §9 the right escalation bar, and is
   "stale player cache / stale DP file" the right diagnosis to point QA at?
3. Should `owner_username` really become `Team 0003` for a franchise with **no**
   `league_members` row at all (`owner_user_id is None`)? I say yes — the grid
   states the franchise exists, so `Unassigned` would be a lie — but it does
   mean emitting a name alongside a null owner id. Confirm or push back.
4. Does claiming `backend/tests/test_draft_board.py` for G1 need more than the
   orchestrator ack the plan asked for? G2's tests are in
   `test_mock_draft.py`, G3 is mobile-only.

---

## Round 2 — Planner review

**Date:** 2026-08-10 · **Base:** `origin/main` @ `7cea1fa` ·
**Reviewer:** Planner (adversarial pass on the Author's PRD)

Every load-bearing claim in the PRD was re-verified against the base commit, and
the three substantive departures from the plan were re-derived from source
rather than taken on the Author's word. Two of the three are **correct and the
plan was wrong**; the third is correct in direction but **under-specified in a
way that would ship the exact defect it exists to prevent**.

### Where the Author improved on the plan (stated plainly, for the audit trail)

1. **The id-space collision hazard is real, and I missed it entirely.** This is
   the most valuable finding in either document. It is also **materially worse
   than the PRD states** — see objection 1 for the measurement.
2. **Overturning the plan's `name: ""` recommendation was right, and my draft was
   internally inconsistent.** Plan §6 R-4 flagged that rookies are the
   crosswalk's weakest segment and that a rookie draft is exactly where they
   appear — and then plan §4 F2 accepted a bare id on precisely those rows.
   Flagging a risk and then accepting its worst outcome is not a tradeoff, it is
   an oversight. The Author is correct that `pick.name || pick.player_id`
   rendering a number **is** the reported bug.
3. **The `by_mfl_id` superset argument is correct, and I verified it
   empirically.** `backend/espn_service.py:607-612` inserts `by_mfl` inside
   `if raw_name and pos:` — *before* the `if sid in ("", "NA"): continue` guard
   at `:613-614` — while `by_mfl_sleeper` is filled only at `:619`. Measured on
   the committed snapshot (`backend/tests/fixtures/dp_playerids_snapshot_2026-07-11.csv`):
   **`by_mfl_id` = 3563 ids vs `by_mfl_sleeper` = 2828**, with **735 ids
   reachable only through tier 2 and zero counterexamples** in the other
   direction. My "second name source on one screen" objection does dissolve
   under total precedence. Tier 2 is justified; I withdraw the rejection.
4. **Demoting spikes S-1/S-2 from build gates to QA measurements is sound
   reasoning.** With a total-precedence fallback that has no bare-id outcome,
   coverage genuinely cannot change the code that must be written. I accept D4.
5. **PRD §11's citation-correction table caught real drift in my plan**
   (`1086-1088` → `1087-1089`, `11437` → `11438`) and found a third member-name
   writer at `server.py:20428-20431` that I had not cited. Verified; all correct.

---

### Objection 1 — BLOCKING. R-7's mitigation does not close the hazard it names, and T-289-06 would pass on the broken implementation.

**The hazard is confirmed and is far larger than the PRD claims.** The PRD says
MFL and Sleeper ids "sit squarely inside that band". Measured against the
committed crosswalk snapshot, **255 MFL ids in that one trimmed file are also a
*different* player's Sleeper id.** Real examples, all from
`backend/tests/fixtures/dp_playerids_snapshot_2026-07-11.csv`
(columns `name,merge_name,position,team,sleeper_id,espn_id,mfl_id,…`):

| Raw MFL id | Is actually | But as a Sleeper id it is |
|---|---|---|
| `13674` | Dallas Goedert | **Chris Hilton Jr.** |
| `13189` | Evan Engram | **Luke Floriea** |
| `13595` | Mason Rudolph | **Cash Jones** |

This is **structural, not coincidental**: MFL ids in the 13xxx band are
2017–2018 veterans while Sleeper ids in the 13xxx band are 2025–2026 rookies.
The two spaces increment from different epochs and overlap densely in exactly
the range a **rookie draft** touches. So the failure mode is not a rare edge —
on a rookie board, an uncrosswalked pick is *likely* to land on an occupied
Sleeper id.

**Now the actual defect in the mitigation.** R-7 is worded as a constraint on
the *query list*: "Only picks whose MFL player id is present in
`req.mfl_player_ids` may be **passed to** `fetchers.players`." That is necessary
but **not sufficient**, because `load_players_by_ids` returns
`{player_id: row}` (`backend/database.py:7318-7333`) and the natural way to
consume it is `rows.get(pick["player_id"])`. Cross-contamination then happens
*within a fully legal query*:

- Pick A: `mfl_pid = "17472"`, crosswalks to our id `"13287"`. Legally queried.
- Pick B: `mfl_pid = "13287"`, **not** in the crosswalk, so
  `player_id = pid_map.get(mfl_pid, mfl_pid)` leaves it `"13287"`
  (`draft_board_service.py:1086`).
- `rows` legitimately contains `"13287"` — fetched for pick A.
- `rows.get(pick_B["player_id"])` → **pick B renders pick A's player.**

Every id in this example is real: `dp_playerids_snapshot_2026-07-11.csv:11` is
`Jeremiyah Love,…,13287,4870808,17472,…` — sleeper `13287`, mfl `17472`.

**T-289-06 as specified cannot catch this.** Its fetcher "(a) raises on any id
absent from `mfl_player_ids.values()`" and "(b) holds a row whose `player_id`
equals an uncrosswalked MFL id". Under (a) that row is *never queried*, so it is
never in `rows`, so `rows.get(raw_mfl_id)` returns `None` and the buggy
implementation **passes the test**. The test proves the query list is clean; it
does not prove the *consumption* is keyed correctly.

**Required changes:**

- **Reword R-7** so the guard is on **per-pick tier-1 eligibility**, not on the
  query list: *"A pick may take tier 1 **only if its own `mfl_pid` is a key in
  `req.mfl_player_ids`**. The hydration result must be keyed by that pick's
  crosswalked id, never by `pick["player_id"]` — those differ precisely when the
  crosswalk missed."* PRD §4's table row and its "Tier 1 is skipped entirely —
  not merely unmatched" sentence already say this correctly; R-7 must not
  contradict them, because a build agent reading R-7 alone will write the bug.
- **Respec T-289-06** to construct the collision *inside* the returned rows,
  using ids already in the corpus (`mfl-complete`'s first picks are
  `17472` / `17473` / `17497`):
  - `mfl_player_ids = {"17472": "17473"}` — pick A's MFL id crosswalks onto a
    value that is *also* pick B's raw MFL id;
  - the `players` fetcher holds one row: `{"17473": {"full_name": "WRONG"}}`;
  - assert pick A (`mfl 17472`) resolves to `"WRONG"` (tier 1, correct), **and**
    pick B (`mfl 17473`, uncrosswalked) resolves to `"Player 17473"` or its tier-2
    name — **never** `"WRONG"`.
  - This test **fails** on `rows.get(pick["player_id"])` and passes on the
    per-pick-gated implementation. That is the discriminating assertion.

---

### Objection 2 — BLOCKING. R-3 is factually wrong about MFL, and T-289-08 cannot be written against any committed corpus.

Two coupled errors that together make R-3 unimplementable as written.

**(a) `order_confidence` is never `"unset"` on an MFL board.** R-3 says the
franchise-less case is "the `order_confidence: "unset"` case". It is not:
`_render_mfl` emits `ORDER_ASSIGNED if assigned else ORDER_UNKNOWN`
(`backend/draft_board_service.py:1133`). `ORDER_UNSET` is produced only by
`_order_from`, the **Sleeper** path (`:783`). A build agent writing the test
from R-3's parenthetical will assert `order_confidence == "unset"` and get
`"unknown"`. Change the parenthetical to `order_confidence: "unknown"`.

**(b) No committed corpus contains a franchise-less pick.** T-289-08 says to use
"`mfl-made0` or a trimmed grid". Verified across all four corpora:

| corpus | picks | franchise-less |
|---|---|---|
| `mfl-complete` | 30 | **0** |
| `mfl-made0` | 60 | **0** |
| `mfl-multi-unit` | 192 | **0** |
| `mfl-partial` | 72 | **0** |

That is not accidental — every manifest pins *"franchise populated on EVERY
pick, made or not (D8's premise)"*. So `mfl-made0` **cannot** drive T-289-08, and
the PRD's "or a trimmed grid" silently hands the build agent an unspecified
fixture-authoring job. Specify it: T-289-08 must use an **inline synthetic
`draftResults` dict** (not a new committed corpus file — a corpus is
recorded-live provenance and must not be hand-edited) with one pick carrying
`"franchise": ""`, and assert `owner_user_id is None`, `owner_username is None`,
and `order_confidence == "unknown"`.

---

### Objection 3 — BLOCKING. The `player: "0000"` sentinel is an unconsidered input, and the PRD's global "never empty, never a bare id" contract silently blesses it.

`mfl-multi-unit` contains **one pick with `"player": "0000"`**. `_render_mfl`
gates on `if mfl_pid:` (`draft_board_service.py:1080`), and `"0000"` is a
**truthy string**, so it is already counted as a made pick and emitted into
`picks[]` today. Post-fix it will render **`Player 0000`** — a placeholder that
reads as a real, if unnamed, player.

`0000` is not a player. MFL's convention (documented in
`mfl_service.fetch_draft_results`'s own docstring: *"unmade picks come back with
`player: ""`"*) covers the empty case; `0000` is a distinct sentinel — a
forfeited, skipped, or auto-passed slot — and it appears in **recorded-live**
data, so it is production-real, not a fixture artifact.

Why this is blocking rather than cosmetic:

- PRD §5 claims *"there is no input for which the payload emits a bare id or an
  empty name"*. There **is** an input the contract never enumerated, and the
  answer for it is not obviously `Player 0000`.
- **T-289-05 would enshrine it**: its global assertion is "every `picks[]`
  entry's `name` matches `^Player \d+$`" — `Player 0000` matches, so the test
  goes green on a nonsense row.
- **The §9 QA count is skewed by it**: the counting script's tier-3 regex
  `Player \d+` matches `Player 0000`, inflating the coverage-failure number with
  a row that was never a player.

**Required:** the PRD must make an explicit call and state it, rather than
leaving the build agent to improvise. Recommended minimal option — **do not
touch pick inclusion** (that lives in `_mfl_counts` and would move `made`/`state`,
which is out of scope), but add a fourth row to §4's resolution table: *"`mfl_pid`
consists only of zeros ⇒ `name = ""`, `position = ""`, `team = None`; this is
MFL's unmade/forfeited-slot sentinel, not a player, and is the one documented
exception to R-9."* Then exclude it from T-289-05's global assertion and from the
§9 tier-3 denominator (count it on its own line).

---

### Objection 4 — NON-BLOCKING. The 10% tier-3 threshold is invented, and the only available measurement suggests it may be badly exceeded.

Answering the Author's open question 2 with data. Replaying all four corpora's
111 distinct MFL player ids against the committed snapshot:
**tier 1 = 51, tier 2 = 6, tier 3 = 54 (49%)** — five times the PRD's pass bar.

That number does **not** predict production: the committed CSV is a *trimmed*
test snapshot (3563 mfl ids; the live DP file is several times larger), and the
tier-3 ids are a contiguous `17550`–`17558`+ block, i.e. a 2026 rookie cohort
absent from a July-2026 trim. But it does establish that **10% is an unvalidated
guess**, and that the plausible failure mode is "tier 3 is common", which would
mean a board of `Player 17550` rows — better than bare numbers, but not a fix
the operator would call done.

Recommend: keep the count, **drop the hard pass/fail bar on it**. Make §9 read
*"record the tier-3 count and percentage; any non-zero tier-3 rate is reported to
the operator with the number, who decides ship / refresh-and-recount"*, and
keep the hard-FAIL conditions (empty name, bare id, `mfl:` in owner) exactly as
specced — those are correctly absolute. Pointing QA at
`docs/runbook.md` § Player-cache refresh (verified to exist, `:482`) as the first
remedy is right and should stay.

---

### Objection 5 — NON-BLOCKING. "Strict superset" is empirically true here but not structurally guaranteed; word it accurately.

`by_mfl_id` requires `raw_name and pos` (`espn_service.py:607`), which
`by_mfl_sleeper` does not (`:618-619`). A DP row carrying an `mfl_id` and a
`sleeper_id` but a blank name or position would land in `by_mfl_sleeper` only,
breaking strictness. I measured **zero such rows** in the committed snapshot, and
the case is immaterial anyway — tier 1 wins on any row that has a `sleeper_id`.
For the audit trail, change "strict superset" to *"a superset in practice (0
counterexamples in the committed snapshot); the guard order means the only
theoretical exception is a nameless DP row, which tier 1 already covers."*
Applies to PRD §5, reconciliation §Round 1 disagreement 2, and the proposed
`DECISIONS.md` entry in `scope.md` §4.

---

### Objection 6 — NON-BLOCKING. R-6/T-289-07 offers the build agent a choice where the contract should pick one.

R-6's pass criterion ends "*count them independently or assert on the hydration
call's id list*". An `or` in a test spec is how two engineers write two different
tests. Note also that a non-suppressed MFL render makes **two** `fetchers.players`
calls — the new hydration plus the pre-existing `_undrafted` call
(`draft_board_service.py:934`) — so a naive `call_count == 1` assertion fails for
the wrong reason.

Pick one and state it: *"assert the hydration call's id list is exactly
`{mfl_player_ids[pid] for picks whose pid crosswalked}` — which simultaneously
proves R-6 (one batched call) and R-7 (no raw ids queried)."* That single
assertion is strictly stronger than counting.

---

### Objection 7 — NON-BLOCKING. Two small holes in the §9 counting script.

- `bare_id = [p for p in picks if (p['name'] or '') == p['player_id']]` only
  catches a *regression to the old behaviour*. It will not catch `name == "0000"`
  or any other non-name string. Add a positive check instead:
  `weird = [p for p in picks if not re.search(r'[A-Za-z]', p['name'] or '')]` —
  "a rendered name must contain at least one letter" is the property actually
  wanted, and it subsumes both the bare-id and the `0000` cases.
- The script assigns `order = b['order'] + b.get('my_picks', [])` and then only
  uses it for the `mfl:` scan. That is correct but double-counts the operator's
  own rows in nothing that is reported — harmless, worth a comment so a reader
  does not think `len(order)` is meaningful.

Everything else in §9 verified executable: `qa/lib/harness.py` exists with
`make_scratch_db` / `boot_server`, `docs/runbook.md:482` is the Player-cache
refresh section, and `positionOf` really is at
`mobile/src/components/draft/DraftRows.tsx:51`. The procedure is runnable by
someone who is not me — which was the bar.

---

### Answers to the Author's four open questions

**Q1 — Is `Player <mfl_id>` the right terminal string?** **Yes, adopt it**, with
objection 3's carve-out for the `0000` sentinel. The symmetry with the shipped
`Team <fid>` convention is the deciding argument, and greppability
(`^Player \d+$`) is what makes the §9 count mechanical rather than eyeballed.
`"Unknown player"` would discard the only identifier we hold and make the QA
count impossible. No cross-client-invariants entry is needed: like `Team <fid>`,
it is a single-producer server-side display string, never re-derived by a client
— `scope.md` §4's reasoning is correct and consistent with `Team <fid>` having no
entry today.

**Q2 — Is 10% the right bar, and is "stale cache / stale DP file" the right
diagnosis?** The diagnosis is right; the bar is not. See objection 4 — replace
the hard bar with report-and-operator-decides, and keep the three absolute FAIL
conditions.

**Q3 — Should `owner_username` become `Team 0003` when there is no
`league_members` row at all (`owner_user_id is None`)?** **Yes — confirmed, and
your §4 formula already expresses it unambiguously.** The grid asserts the
franchise exists, so `Unassigned` would be a lie, and `Team 0003` is what the
sibling surface already emits for the same condition (`server.py:9207` returns
`f"Team {fid}"` on a missing member row). Two guardrails to add explicitly: the
build agent must **not** invent an `owner_user_id` to go with the name (it stays
`None`, protecting `my_picks`' slice at `:1151`), and the client renders this
correctly today — `slot.owner_username ?? slot.owner_user_id ?? 'Unassigned'`
(`DraftRoomScreen.tsx:1140`) shows `Team 0003`. Note this is a *different* case
from R-3's franchise-less pick, and objection 2 asks you to make that distinction
sharp, because the two currently read as one paragraph.

**Q4 — Does claiming `backend/tests/test_draft_board.py` need more than an
orchestrator ack?** **No — an ack is sufficient.** Verified: G2's mock tests are
in `backend/tests/test_mock_draft.py`, G3 is mobile-only, and no other group's
lane imports or edits `test_draft_board.py`. Duplicate-franchise-name handling,
which the orchestrator asked about separately, needs no contract change either —
`mfl_usernames` is keyed by user id, so two franchises sharing a display name
collide nowhere; they simply render the same text, which is what MFL shows too.

---

### Scope and gate check

No scope creep found. The three-tier resolution is the reported ask, not an
extension of it; PRD §6.2 explicitly forbids the refactor that
`docs/coding-guidelines.md` §3 would prohibit, and tier 2 is a measured
capability (+735 reachable ids) rather than the speculative abstraction §2
prohibits. The four gates are all addressed: scope block filled with two surfaced
waivers, Maestro waiver carrying an operator ruling plus a named backlog item,
docs table filled row-by-row with proposed text for the orchestrator-owned files,
and sim Tier 3 declared with flows and evidence paths. `mobile/` remains
untouched, so the Tier-3-not-Tier-1 reading holds.

---

### Verdict

**No — not ready for a build agent to implement blind.** Three blocking fixes are
required, all cheap and all confined to the PRD text: respec T-289-06 plus reword
R-7 (objection 1), correct R-3 and specify T-289-08's synthetic grid
(objection 2), and rule on the `0000` sentinel (objection 3). The design is
sound and better than my plan's — this is a Round 3 Author revision, not a
re-plan.

---

## Round 3 — Author incorporation

**Date:** 2026-08-10 · **Base:** `origin/main` @ `7cea1fa` ·
**Author** responding to the Planner's Round 2 adversarial pass.

**Every Planner measurement was independently re-run before being incorporated
— none was taken on trust.** All of them reproduced exactly:

| Planner claim | Author's re-measurement | Verdict |
|---|---|---|
| 255 MFL ids are also a *different* player's Sleeper id | 255, with the same three exemplars (`13674` Goedert/Hilton, `13189` Engram/Floriea, `13595` Rudolph/Jones) | confirmed |
| snapshot row 11 = `Jeremiyah Love, sleeper 13287, mfl 17472` | exact | confirmed |
| `by_mfl_id` 3563 vs `by_mfl_sleeper` 2828, 735 tier-2-only, 0 counterexamples | exact | confirmed |
| All four corpora have 0 franchise-less picks | `mfl-complete` 30/0, `mfl-made0` 60/0, `mfl-multi-unit` 192/0, `mfl-partial` 72/0 | confirmed |
| `mfl-multi-unit` carries one `"player": "0000"` pick | exactly one, round 05 pick 11 | confirmed |
| MFL emits `ORDER_UNKNOWN`, never `ORDER_UNSET` | `:1133` vs Sleeper-only `:783` | confirmed |
| `docs/runbook.md:482` is § Player-cache refresh | exact | confirmed |

### Outcome of each objection

| # | Objection | Outcome |
|---|---|---|
| 1 | R-7 insufficient; T-289-06 non-discriminating | **ACCEPTED in full** |
| 2 | R-3 wrong enum; T-289-08 unwritable | **ACCEPTED in full** |
| 3 | `player: "0000"` sentinel unconsidered | **ACCEPTED as a defect; treatment PARTIALLY REBUTTED** — see below |
| 4 | 10% tier-3 bar is invented | **ACCEPTED** |
| 5 | "strict superset" overclaims | **ACCEPTED** |
| 6 | R-6's `or` invites two tests | **ACCEPTED** |
| 7 | Counting-script holes | **ACCEPTED** |

---

### B1 — ACCEPTED IN FULL. The most important correction in this round.

The Planner is right, and my R-7 would have shipped the bug it was written to
prevent. Constraining the *query list* is necessary but not sufficient: with
`load_players_by_ids` returning `{player_id: row}` (`database.py:7318-7333`),
the natural consumption `rows.get(pick["player_id"])` cross-contaminates inside
a query that is itself entirely legal. And my T-289-06 could not have caught it
— its fetcher raised on uncrosswalked ids, so the colliding row never entered
`rows`, so `rows.get(raw_mfl_id)` returned `None` and the buggy implementation
went green. **A test that cannot fail on the defect it names is worse than no
test**, because it manufactures confidence.

Changes made:

- **R-7 rewritten** from a query-list constraint to a *per-pick tier-1
  eligibility* rule plus an explicit keying mandate: the row is read by
  `req.mfl_player_ids[mfl_pid]`, **never** by `pick["player_id"]`. The 255
  measured collisions and the A/B walk-through are now in the requirement body,
  not a footnote, so a build agent reading R-7 alone cannot write the bug.
- **§4 gains normative pseudocode** binding `crosswalked` before the branch, so
  the correct keying is the path of least resistance rather than a caveat.
- **T-289-06 replaced** with the Planner's discriminating construction
  (`mfl_player_ids = {"17472": "17473"}`, one `players` row keyed `"17473"` named
  `WRONG`), spec'd inline in §8 with all three assertions. It fails on
  `rows.get(pick["player_id"])` and passes only on the gated implementation.

### B2 — ACCEPTED IN FULL.

Both halves were my errors.

- `order_confidence: "unset"` corrected to `"unknown"` in R-3, with the
  `:1133` / `:783` evidence inline so the correction is self-justifying.
- **T-289-08 now specifies an inline synthetic `draftResults` dict**, with the
  minimum shape written out. I also added the Planner's reasoning explicitly:
  corpora carry `"provenance": "recorded-live"` and hand-editing one would
  falsify that — so the synthetic grid belongs in the test body, not in
  `fixtures/`. "Or a trimmed grid" was an unspecified job handed to the build
  agent and is gone.
- I additionally split R-3 from R-2 with a callout block, because the Planner's
  answer to my Q3 noted the two currently "read as one paragraph". R-2 is
  *franchise named, member row missing* → `Team 0003` with `owner_user_id`
  staying `None`; R-3 is *no franchise at all* → both `None`. The discriminator
  is `fid`, not `owner`.

### B3 — Defect ACCEPTED. Recommended treatment PARTIALLY REBUTTED.

**The finding is correct and I missed it.** `mfl-multi-unit` carries
`"player": "0000"` (round 05, pick 11 — re-verified, and it is the only such
pick in any corpus). `_render_mfl` gates on `if mfl_pid:` (`:1080`) and `"0000"`
is truthy, so the row is already emitted today. My §5 claim that "there is no
input for which the payload emits a bare id or an empty name" was false. That
claim is now scoped to the enumerated tiers and annotated with how it was
broken.

**I do not adopt the recommended `name = ""`.** Reasoning:

`name = ""` sends the client straight back to `pick.name || pick.player_id`
(`DraftRoomScreen.tsx:1152`), which renders the literal string `0000`. That is a
bare numeric id in the player-name position — the exact failure class this PRD
exists to eliminate — and unlike a crosswalk miss it is one we can predict in
advance. Trading a known-bad render for spec tidiness is the wrong direction.

`Player 0000` (my prior spec) is also wrong, for the Planner's stated reason: it
asserts a player exists.

**Adopted instead: tier S → `name = "No selection"`, `position = ""`,
`team = None`.** It claims only what we can defend — the slot produced no
selection — while never rendering digits. It is a single-producer server-side
display string, the same class as the shipped `Team <fid>`, so it needs no
cross-client-invariants entry (the Planner's own Q1 answer establishes that
precedent).

Everything else in the objection is adopted verbatim: the sentinel is defined
exactly (`mfl_pid and set(mfl_pid) == {"0"}`, distinct from MFL's `player: ""`
unmade convention at `mfl_service.py:375`), **pick inclusion is untouched**, and
the sentinel is excluded from T-289-05's global regex and from §9's tier-3
denominator.

**One point the objection understated, which I verified and which closes the
question of whether exclusion was ever an option:** dropping the row from
`picks[]` would not merely be out of scope, it would **break a currently-passing
test**. `_mfl_counts` counts `"0000"` as made (`:656`), and
`test_m5_mfl_grid_states_through_the_injected_opener` asserts
`len(payload["picks"]) == man["made"]` — 192 for `mfl-multi-unit`
(`test_draft_board.py:640`). So inclusion is pinned by the existing suite, not
just by §6.2. That evidence is now in R-15.

### Objection 4 — ACCEPTED. Bar removed.

The 10% figure was mine and it was a guess; 49% across the corpora settles it.
§9 now **reports** the tier-3 count and rate to the operator and never auto-fails
on it, while the absolute FAILs stay hard. I also agree with the framing the
orchestrator added: a gate that fails on first contact with real data trains
people to ignore gates. `no position chip` is likewise demoted to reported.
The stale-cache diagnosis and the `docs/runbook.md:482` remedy stay.

### Objection 5 — ACCEPTED. Wording corrected in all three places.

"Strict superset" → "a superset in practice, 0 counterexamples measured", with
the 3563 / 2828 / 735 figures and the reason strictness is not structurally
guaranteed (`by_mfl_id` additionally requires `raw_name and pos`,
`espn_service.py:610`). Corrected in PRD §5 and in `scope.md` §4's proposed
`DECISIONS.md` text. Round 1's disagreement 2 above is left as written — it is a
historical record of that round — and this entry is its correction.

### Objection 6 — ACCEPTED, and the catch about `_undrafted` is a real trap.

R-6 now specifies exactly one assertion: the hydration call's id set equals
`{mfl_player_ids[pid] for non-sentinel picks that crosswalked}`. The PRD
explicitly warns against `players.call_count == 1`, since a non-suppressed MFL
render legitimately makes two `players` calls (hydration + `_undrafted` at
`:934`) — an assertion that would have failed for the wrong reason and sent a
build agent hunting a non-bug.

### Objection 7 — ACCEPTED. Script rewritten.

`bare_id` (equality to `player_id`) replaced with
`re.search(r'[A-Za-z]', name)` — "a rendered name must contain a letter" — which
subsumes empty names, bare ids and sentinel digits in one property. This is now
also R-9's **global test assertion**, replacing the `^Player \d+$` regex that
would have blessed `Player 0000`. The sentinel gets its own reported line and is
removed from the tier-3 denominator. The `order + my_picks` union carries a
comment noting it double-counts and that its length is not a meaningful total.

---

### Remaining disagreement

**One, narrow, and it does not block implementation:** the rendered string for
MFL's all-zeros sentinel.

- **Planner:** `name = ""` — "`0000` is not a player; emit nothing."
- **Author:** `name = "No selection"` — `""` makes the client render the bare
  string `0000` via `pick.name || pick.player_id`, which is the defect class
  #289 reports, on a row we can predict.

Both positions are recorded for the orchestrator. The PRD specs
`"No selection"`. This is a one-line change either way and touches nothing
else in the contract — if the orchestrator prefers the Planner's version, the
only consequential follow-on is that R-9's global letter-containing assertion
must then carve out the sentinel explicitly, and §9's hard-FAIL list must gain
an exception for it. I judge that a worse contract, hence the recommendation.

Everything else raised in Round 2 is resolved.

### Implementability verdict

**Yes — the PRD is now implementable blind by a build agent.**

The three blocking objections are closed in PRD text: R-7 is rewritten as a
keying mandate with normative pseudocode; T-289-06 is spec'd inline as a
discriminating test; R-3's enum is corrected and T-289-08's synthetic grid is
written out; and the `0000` sentinel has an explicit tier with an exact
predicate. The three tests that could not be improvised (T-289-06, T-289-08,
T-289-14) now carry full inline specifications rather than one-line table rows.
No requirement offers the build agent a choice, no fixture work is left
unspecified, and every pass criterion is mechanical.

The one open disagreement above is a single string constant with both positions
stated; the build agent should implement the PRD as written unless the
orchestrator rules otherwise.

---

## Round 4 — Orchestrator arbitration (2026-08-10)

One disagreement survived Round 3. Phase 1 for G1 closes here.

### The `"0000"` sentinel name — RULED FOR THE AUTHOR

**Positions.** Planner: emit `name = ""` for the `mfl-multi-unit` pick whose
`player` field is `"0000"`. Author: emit a tier-S sentinel `"No selection"`,
predicate `mfl_pid and set(mfl_pid) == {"0"}`.

**Ruling: `"No selection"`.** Reasons, in priority order:

1. `name = ""` is not a neutral choice — it hands the row back to the client's
   `pick.name || pick.player_id` fallback, which renders the literal string
   `0000`. That is a bare numeric id in the name position: the exact defect
   class this item exists to eliminate, on a row we can predict in advance.
   Fixing "shows an id" by emitting a different id is not a fix.
2. It weakens the contract elsewhere. R-9's global "a name must contain a
   letter" assertion and §9's hard-FAIL list would each need an explicit
   sentinel carve-out. Two carve-outs to save one line of code is the wrong
   trade — a contract with holes in it is what lets a build agent ship
   something defensible-but-wrong.
3. `Player 0000` was correctly rejected by both parties: it asserts a player
   exists when none does.

**Accepted alongside it:** the Author's verified finding that dropping the row
from `picks[]` is not merely out of scope but would break a currently passing
test — `_mfl_counts` counts `"0000"` as made (`draft_board_service.py:656`) and
`test_m5_mfl_grid_states_through_the_injected_opener` asserts
`len(picks) == man["made"]` = 192 (`:640`). Inclusion is pinned by the suite.
Recorded as R-15.

**Residual risk, accepted:** `"No selection"` is an inference about what MFL's
`"0000"` sentinel *means*. It is honest about the absence either way, and no
alternative reading produces a better string, but if the operator later learns
`"0000"` encodes something specific (a forfeited or voided pick), the copy
should follow the truth. One-line change, no contract impact.

### Phase 1 verdict for G1

**Closed — implementable blind.** Both agents converged; the Planner conceded
two of its own recommendations (the bare-id fallback, the `by_mfl_id`
rejection) and the Author accepted all three blocking objections. Every
measurement in the log was independently re-run by the opposing agent and
reproduced exactly. Proceeding to Phase 2 with 15 requirements and 14 tests.

### Operator rulings folded into G1

- QA runs against the live **Dependables** MFL league (62846); spike S-2 folded
  into that pass (batch-plan D-3).
- The **10% tier-3 threshold is removed** — replaying all four corpora measured
  49%, five times the proposed bar. A gate that fails on first contact with
  real data teaches its reader to ignore it. Replaced with report-the-rate +
  escalate, keeping the three absolute FAIL conditions (empty name, bare id,
  raw `mfl:` in an owner cell) as hard stops.
