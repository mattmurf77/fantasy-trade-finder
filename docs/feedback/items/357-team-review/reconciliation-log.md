# Reconciliation log — Team Review (#357 / #358 / #359)

**Date:** 2026-08-19 · **Session:** `claude/team-review-analysis-plan-1f91e3`

---

## How this document was produced — read this first

`.claude/skills/feedback/references/plan-phase.md` prescribes a **dual-agent
loop**: a Planner subagent drafts, an Author subagent writes the docs, the
Planner reviews, the Author rebuts, and the orchestrator arbitrates anything
still open.

**That is not what happened here.** This session ran under a standing
instruction not to spawn subagents, so the plan was authored and reviewed in a
single context: draft first, then a deliberate adversarial pass over the draft
hunting for contract ambiguity, missing error cases, and repo-invariant
violations — the Planner's review checklist applied by the same author.

That is a genuinely weaker process than two blind agents, and the weakness is
specific and worth naming: **a single author cannot catch an error that follows
from a wrong assumption it still holds.** Every objection below was found by
re-reading the *source* against the draft, which is the one check that does not
depend on the author's assumptions — and that is exactly how O-1, the only
blocking objection, surfaced. Objections that would have required a genuinely
independent reading of the *problem* may still be missing.

**Recommended before build:** an independent reviewer (agent or human) reads
[`lld-delta.md`](lld-delta.md) §2–§3 against `backend/ranking_service.py`,
`backend/trends_service.py` and `backend/power_rankings.py` and confirms the
contract. Logged as an open item, not waved away.

---

## Round 1 — adversarial pass over the draft

### O-1 — `len(user_elo)` is not a measure of how much a user has ranked · **BLOCKING · accepted, fixed**

**Objection.** The draft skipped the `divergence` beat when
`user_elo is None or len(user_elo) < 10`. That condition can never fire.
`RankingService.get_rankings(position=None)` calls `_pool(None)`, whose docstring
is *"Return ALL players for a position (unfiltered)"*, and `_compute_elo` assigns
every one of them a rating. A user who has made **zero** comparisons still gets a
full-pool `user_elo` map, every entry sitting at the consensus seed.

Two failures follow. The skip never triggers, so a brand-new user reaches beat
`divergence`; and because an un-judged player's board Elo *is* the seed, the
seed-delta fallback computes `gap = 0` for all of them and renders five
meaningless rows on each side. The beat designed to say "here is where your
opinion differs from the market" would confidently show a user with no opinions.

**Resolution — accepted in full.**
- Skip condition is now `RankSet.threshold_met` for `position=None` — the
  ranking service's **own** confidence bar (`interaction_count >= 16`,
  `POSITION_THRESHOLDS[None]`). Deliberately not a new number: this repo has an
  explicit precedent against invented thresholds (D-078's rejected
  "re-tune to match measured supply — a magic number buys less and has to be
  re-tuned whenever supply drifts").
- Every divergence candidate is filtered on `RankedPlayer.wins + losses > 0`
  before any gap is computed, in **both** the `league_community` and
  `consensus_seed` branches.
- `board_players_ranked` was renamed `board_judged_players` and redefined as the
  count passing that filter, with `board_interactions` added alongside it — the
  old name invited exactly the misreading that caused this.
- The trap is written up as its own subsection in [`lld-delta.md` §3](lld-delta.md)
  rather than left as a field comment, because the next person to touch this
  code will reach for `len(user_elo)` for the same intuitive reason.
- New test `test_divergence_judged_only`; new sabotages in
  [`prd.md` §7.3](prd.md) for both halves; new requirement **R-25a**; **R-25**
  rewritten.

**Note for whoever builds this:** the same trap sits under any future feature
that wants "has this user ranked enough". Check `threshold_met`, never a map
length.

---

### O-2 — the `overflow` analytics source named a surface that does not exist · **BLOCKING · accepted, fixed**

**Objection.** `team_review_opened.source` was specced as
`trades_home_card | deck_empty | overflow`, and the HLD said a dismissed entry
card "survives in the overflow row". No overflow row was ever specified — not in
the LLD's mobile section, not in the file-ownership table, not in the mockup. A
build agent would either invent one or silently drop the enum value.

Worse, the underlying design was wrong independently of the naming: a
permanently dismissible entry means the user who most needs this feature can
lose its primary surface forever with one accidental tap.

**Resolution — accepted, and the design changed rather than the label.**
Dismissing the card now **collapses it to a one-line row**; it never disappears.
This is D-025's ruling applied verbatim — the League-Summary outlook section
"defaults to a collapsed one-line 'your outlook' strip (per-league, per-user
persisted) with the full section one tap away". Reusing an operator-decided
pattern beats inventing a second dismissal vocabulary. The enum is now
`trades_home_card | collapsed_row | deck_empty`, every value backed by a
specified surface. `AsyncStorage` key renamed `…entry_collapsed.<league_id>`.
TestFlight steps A3 and B4 rewritten to test collapse rather than disappearance.

---

### O-3 — the hand-off to a reshaped deck reinvented an existing mechanism · **NON-BLOCKING · accepted, fixed**

**Objection.** R-16 required the `plan` beat to return to `TradesHome` "with the
deck regenerated against the preferences just written", and beat `partners`
required scoping the deck to a member — both stated as outcomes, with no
mechanism named. There already is one: `mobile/src/state/useFinderTargets.ts`
carries the #330 one-shot, focus-gated handoff store
(`{opponent, autoRun, seq}`), consumed by `TradesScreen` on focus, with an epoch
guard and a documented degrade-to-prefill-without-autorun path. Leaving the
mechanism unnamed invites a parallel one.

**Resolution — accepted.** R-16 and [`lld-delta.md` §4](lld-delta.md) now name
`setHandoff({opponent, autoRun: true})` explicitly, and the file-ownership table
marks `useFinderTargets.ts` **read, do not modify** so the mobile agent does not
"improve" a store another feature owns.

---

### O-4 — the scope block mis-stated how the structural suite reaches CI · **NON-BLOCKING · accepted, fixed**

**Objection.** The draft said `check-team-review.js` "must be added to that job's
script list, not only to `package.json`". Reading `.github/workflows/ci.yml`:
`mobile-typecheck` runs `for f in tests/check-*.js; do node "$f" || exit 1; done`
— a **glob**. The file gates CI the moment it exists; no CI edit and no npm
script are needed. The ci.yml comment says so in as many words: *"a guard is live
in CI the moment the file exists — no npm script needed."*

**A second, larger finding fell out of this.** Root `CLAUDE.md` §Stack states the
`mobile/tests/check-*.js` suites are "`npm run`-only and **gate nothing yet**
(open item in NEXT.md)". Against ci.yml that is **stale and materially
misleading** — it understates the repo's actual evidence posture, and under
D-056 these suites are the primary client-invariant regression net. Any agent
trusting CLAUDE.md would believe its structural guard is decorative.

**Resolution — accepted.** [`scope.md` §3 and §5](scope.md) corrected; the npm
script is still added for convention parity with the 42 existing suites, but
labelled as convention rather than a requirement. The CLAUDE.md staleness is
**out of this feature's scope to fix unilaterally** and is logged as
**Q-024** for the operator.

---

### O-5 — one call for six beats pays for work an abandoning user never sees · **NON-BLOCKING · rebutted, with the cost recorded**

**Objection.** A single `GET` computes all six beats; a user who abandons at beat
2 paid for beats 3–6, including the per-member `infer_team_outlook` and
`analyze_roster_strengths` sweep in `partners`.

**Rebuttal, and it stands.** Six beats fetching independently is six loading
states inside a flow whose entire value is feeling like one continuous read —
that trade is the wrong way round. On cost: `compute_power_rankings` and
`analyze_roster_strengths` are calls the Trades tab already makes, and the
genuinely additive work is a pure function over data already in memory,
bounded by league size (≤14 members × ~25 roster entries ≈ 350 dict lookups).
That is not a latency risk worth six spinners.

**But the objection is not dismissed.** A p95 budget of **800 ms** is now written
into [`prd.md` §6](prd.md) with the remedy named in advance — *cache the
power-rankings half, do not split into per-beat fetches* — so that if the budget
is missed, the fix is decided before anyone is under pressure to reach for the
tempting wrong one.

---

### O-6 — `equal_pick_share` is derivable client-side · **NON-BLOCKING · rebutted**

**Objection.** `window.signals.equal_pick_share` is just `1 / num_teams`, which
the client already has from `meta.num_teams`. Redundant field.

**Rebuttal.** It is redundant *arithmetically* and load-bearing *semantically*:
it is the centring constant `infer_team_outlook` actually uses, and shipping it
explicitly stops the client from re-deriving a server concept and drifting if the
centring ever changes. This is the same reasoning that governs tier bands and
playoff outlook bands — a client reads the encoding, it never re-derives it. Kept.

---

### O-7 — beat `partners` can put the same member in both lists · **NON-BLOCKING · rebutted**

**Objection.** A member may appear in both `opposed_window` and
`fills_your_need`, which reads as a duplication bug.

**Rebuttal.** A league-mate who is pointed the opposite way *and* deep exactly
where you are thin is the single best trade partner in the league. Suppressing
the second appearance would hide the strongest signal the beat can produce. It is
called out in [`lld-delta.md` §3](lld-delta.md) as intentional so no one
"fixes" it later.

---

## Round 2 — invariant sweep

Checked against `docs/cross-client-invariants.md` and CLAUDE.md §Conventions. No
new objections; four confirmations worth recording because each is a rule this
feature could plausibly have broken:

| Invariant | Status |
|---|---|
| `title_pct` unrenderable at any week, in any form | **Held.** Not in the payload, not on any screen; mechanically pinned by `test_no_odds_fields` and `check-team-review.js` #3. |
| `playoff_pct` renders only as a three-band chip | **Held vacuously** — the field is absent. The future mount point (beat `standing`) is recorded as a pointer so the invariant travels with it. |
| Tab-stack screens must not mount their own `FeedbackFAB` (#188 / #196 / #197) | **Held.** `TeamReview` is a tab-stack screen; no local mount; pinned by `check-team-review.js` #2. |
| Position/tier hexes are data encodings, never re-derived | **Held.** [`lld-delta.md` §5](lld-delta.md) requires `chalkline.position`, which re-exports `colors.ts`. |

---

## Unresolved / carried forward

| # | Item | Owner |
|---|---|---|
| U-1 | The three waivers in [`scope.md` §6](scope.md) — forward PPG cut, championship odds refused, PPG rank Sleeper-only-and-preseason-empty — need an operator yes before build. Logged as **Q-025**. | Operator |
| U-2 | Root `CLAUDE.md` §Stack is stale about `check-*.js` CI gating (O-4). Logged as **Q-024**. | Operator |
| U-3 | An independent read of [`lld-delta.md`](lld-delta.md) §2–§3 against the four source modules, to compensate for the single-context review noted at the top. | Next session / build agent |

**Zero unresolved blocking objections.** O-1 and O-2 were blocking and are both
fixed in the documents.
