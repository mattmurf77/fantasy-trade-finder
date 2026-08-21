# HLD — Counterparty breaker · Draft B (failure-modes / risk lens)

**Date:** 2026-08-21 · **Author:** Agent B (independent draft; not a review of draft A)
**Seed (binding):** [PLAN.md](../PLAN.md) + [scope.md](../scope.md). Rulings NOT re-litigated here:
v1 zero ordering effect · no LLM in v1 · fit-challenger operator register stands · objection
vocabulary anchors on `trade_pass_reasons` · sibling seams per PLAN §8.
**Stance of this draft:** the breaker's dominant failure mode is not "it crashes" — it is
**being confidently wrong about a real, named human, in copy the user's league-mate can
screenshot.** Every section below is organized around that. The risk register (§6) is the
spine; the architecture exists to make each risk either impossible, degradable, or measurable.

---

## 1. Context — what this feature can break that nothing else in the app can

The engine today argues one side (96.3% of 1-for-1 cards exist in one direction; 84.5% of served
cards never consult a partner board; consensus-path viewer receives more on 86.3% of cards —
arm-B audit). The breaker's promise is a named, evidenced prediction of the counterparty's
decline reason. That promise has a property no existing surface has: **the copy makes a claim
about a third person's judgment, rendered to someone who knows that person.** Every prior
narrative sentence claims something about the *user's own* roster or about consensus math. The
hesitation line claims something about *Mike*.

Three background facts make "confidently wrong" the default outcome rather than a tail risk:

1. **The window signal the breaker inherits is known-skewed.** `trade.outlook_composite` is dark
   and wired only to Team Review (INV-372b, `trade_service.py:3162-3168`) — the engine-facing
   window is the legacy age/pick vector, which the audit found labels ~65% of teams rebuilders
   (sibling-reported; verify at build, A-4 below). `fit_outlook` — the objection class this skew
   feeds — is also the second-most-filed real pass reason (33% of n=208). The breaker's
   highest-value class sits directly on its worst input.
2. **The data to know the counterparty is mostly absent.** 84.5% unboarded means `value_giving`
   (their seat) usually degrades to consensus optics — which, on a deck where the viewer receives
   more 86.3% of the time, fires almost tautologically (§6 R4).
3. **The validation population barely exists.** `propose` has fired zero times ever; mirrored
   cards are served in both directions ~3.7% of the time. The headline calibration cut (PLAN
   §6.2a, counterparty-seat) starts with an n near zero (§6 R3).

None of this argues against building. It argues for an architecture where wrongness is bounded,
attributable, and cheap to retract — and for an explicit answer, per objection class, to the
PLAN's own unasked question: **is a confidently wrong objection worse than none?** This draft's
answer: yes for user-facing copy, no for dark stamps. The design splits along exactly that line.

### 1.1 Explicit non-goals (v1)

- **No kill, demote, filter, reorder, or draft change** — on any deck, organic or bake-off.
  Interleave discipline (`bakeoff_runner.bypass_rerankers`) is a hard invariant, tested byte-level.
- **No LLM**, no copy generation beyond deterministic templates in `trade_narrative.py`.
- **No learning, no persistence** — no `breaker_` tables (prefix reserved, unused), no
  read of `negmem_*`, no acceptance-model coupling. `acceptance_prior` stays untouched.
- **No G6 changes.** The breaker *mirrors* predicate shapes; it never edits or calls into the
  presentment kill chain's control flow.
- **No counterparty notification, no cross-user surfacing** — the breaker never causes any output
  in the counterparty's own app.
- **No new client element** (default per scope §3): the line rides the existing server-composed
  `narrative` string. If the PRD elects a tappable element, that reopens Chalkline + structural
  guard + taxonomy rows — separate decision.
- **No new ingestion**: reads only state the app already holds.

---

## 2. Architecture

### 2.1 Placement — one seam, two flags, stamp-precedent

```
generation arms ──▶ ranking/draft ──▶ [BREAKER: evaluate + stamp]  ──▶ impression log
   (untouched)        (untouched)       trade.breaker, post-ranking      features_json.breaker
                                              │                          (uniform keys, T2)
                                              ▼
                                        [NARRATIVE: one sentence]
                                        trade.breaker_narrative,
                                        composed at the SAME owner site as
                                        the existing counterparty framing
```

- **Module:** `backend/trade_breaker.py`. Imports `trade_service` / `trade_optimizer` as
  MODULES (`ts.`, `topt.` — the T1 binding trap is a live failure mode here because the breaker
  deliberately reuses live predicate shapes; importing `need_gate_ok` by name would freeze it
  against knob changes). Never imported by `trade_service`; the only production caller is the
  `server.py` stamp site (organic-isolation precedent: `test_organic_never_imports_fit` shape,
  here `test_flag_off_never_imports_breaker`).
- **Stamp site:** immediately adjacent to the M3 `stamp_fit_diag` site (`server.py` `_run_trade_job`,
  post-ranking, pre-F7 — re-cite exact lines at build, A-3). Same non-fatal envelope: outer
  try/except logs a warning and the job proceeds; per-card try/except sets `card.breaker = None`.
  A breaker exception must never kill a deck job — this is a tested invariant, not a convention
  (§5.4 T-2), including a sabotage test that raises inside a predicate.
- **Unlike fit_diag, the breaker also stamps organic decks** (PLAN §3). That widens the blast
  radius of any latency or exception bug from "bake-off jobs" to "every deck job." Consequence:
  the budget ladder (§2.3) and the non-fatal envelope are v1 acceptance criteria, not hardening
  follow-ups.
- **Two flags** (`config/features.json` + `FLAG_KEYS`, default false): `trade.breaker`
  (compute+stamp), `trade.breaker_narrative` (requires `trade.breaker`). Rollback rungs, all
  deploy-free: narrative flag off (kills the only user-visible surface, hot reload) → breaker
  flag off (kills compute and the import) → knob levels 0 (flags on, byte-identical decks).

### 2.2 Evaluation model — two-phase, per-partner amortized

Naive cost is (arms × cards × classes × predicate cost); the expensive inputs are per-*partner*,
not per-card. So:

- **Phase 1 — per-partner snapshot (once per league-mate per job):** roster ids,
  `analyze_roster_strengths` outputs, `infer_team_outlook` (engine-served signal — legacy vector
  today, composite iff/when the engine itself graduates; the breaker takes whatever the engine
  serves and *records which one it got*, §3.2), declared outlook + `asset_preferences` (their
  side, resolved per §3.3), board accessor (raw `member.elo_ratings`, provenance rule T3 — the
  breaker must never touch `_shrink_user_elo`), starter-slot map, depth-chart reads.
- **Phase 2 — per-card class evaluation:** cheap arithmetic against the snapshot. The one
  structurally expensive class is lineup/roster-spot feasibility (`shape_aversion` /
  `fit_new_weakness` via the `_feasible_after` shape). These are the **budget-gated tier** (§2.3).

Every class always emits `{code, severity, evidence}` or an explicit skip marker — never silent
absence (M4-precedent: absence must be impossible, only null/skipped is representable).

### 2.3 Budget and degradation ladder (what breaks first, on purpose)

`breaker_ms_budget` (model_config, five-registration rule) against the 60s job timeout. The
failure design principle: **degradation must be attributable and unbiased-or-labeled** — a stamp
rail whose missingness correlates with deck rank silently poisons the §6.4 filter counterfactual.

| Rung | Trigger | Behavior | Stamp records |
|---|---|---|---|
| 0 | normal | all classes, all cards | full objection list + `ms` |
| 1 | partner snapshot fails | all that partner's cards: cheap classes only where computable, else null | `degraded: "partner_snapshot"` |
| 2 | per-deck budget 50% consumed | expensive tier (feasibility classes) skipped **for all remaining cards** | `skipped: ["shape_aversion","fit_new_weakness"], reason: "budget"` |
| 3 | budget exhausted | remaining cards stamped `null` with reason | `degraded: "budget_exhausted"` |
| 4 | exception (card) | that card `breaker: null` | logged, counted |
| 5 | exception (outer) | deck ships unstamped | warning log + diagnostics counter |

Rung 2 drops a *class tier* across remaining cards rather than dropping *cards*, precisely so
that class coverage is uniform within a deck wherever possible; rung 3 missingness is
rank-correlated by construction and therefore **must be labeled**, so the readout can exclude
budget-truncated decks instead of silently absorbing the bias. Coverage per rung rides the job
diagnostics (FitReport precedent) — this is how "stamps are missing" is *known* rather than
discovered (§5.3).

### 2.4 The consistency spine — breaker predicates are mirrored live predicates

The mirrored-card coherence problem (§6 R5b): if user A's card says "B will object: takes their
only startable TE," while the byte-mirrored card serves happily in B's own deck as a good trade,
the app contradicts itself in front of two people who talk to each other. The structural defense:
**where an objection class has a live viewer-seat predicate, the breaker evaluates the SAME
predicate shape, module-imported, seat-swapped** — `fit_new_weakness` mirrors R5/`need_gate_ok`
logic and `_starters_at`; `fit_duplicate` reads the same `analyze_roster_strengths` the viewer
seat uses; `value_giving` (boarded) reuses the fit arm's them-lens quantities (read from
`fit_diag`/`fit` stamps when present rather than rescoring — cheaper AND definitionally
consistent). Then cross-seat contradiction is a *bug with a test* (T-6: for a mirrored card,
high breaker severity from seat B ⟺ B's own viewer-seat gate would have flagged it), not a
vibes problem. Where no live predicate exists (`shape_aversion`, `roster_crunch`), the class is
new logic and gets the conservative narrative treatment (§4, D-B2).

---

## 3. Data

### 3.1 Inputs — with a per-input wrongness account

The breaker is only as honest as its worst input. This table is normative: every input row
carries its known failure mode and the mandated degradation. "Degrade" always means: the class
still stamps, with a `basis`/`confidence` marker; it does NOT mean silently compute on bad data.

| Input | Source | Known wrongness | Mandated handling |
|---|---|---|---|
| Counterparty roster | league sync | G-045: pool prune can drop a league-mate entirely | partner absent from pool → rung 1, `partner_snapshot` degrade |
| Partner board | `LeagueMember.elo_ratings` (raw, T3) | 84.5% absent; staleness unbounded (board ranked in July, roster is August's) | absent → board-based classes fall to consensus basis, marked `basis:"consensus"`; staleness: record board age if derivable, else log Q-B1 (open question — is last-ranked-at recoverable?) |
| Inferred window | `infer_team_outlook` as the ENGINE serves it | legacy vector ~65% rebuilder skew (verify: A-4); composite dark (INV-372b) | severity haircut for inferred (vs declared) window; stamp `outlook_src: "legacy"|"composite"|"declared"` so the calibration readout can cut by source — and so the day the composite graduates is visible in the data instead of silently shifting calibration |
| Declared window | `league_preferences` | stale self-declarations (declared preseason, roster since gutted) | prefer declared over inferred for direction, but stamp declared-at age when available; no recency data → treat as declared, log in evidence |
| `analyze_roster_strengths` | live | `_POS_TIER_CUTS` assumes 12-team (`trade_service.py:2070`); superflex only via `sf` prefix; G-026: IDP/K assets price 0.0 → depth profiles wrong in those leagues | league-size/format envelope check (§3.4): outside envelope → depth-based classes (`fit_new_weakness`, `fit_duplicate`, `roster_crunch`) emit with `format_gap` marker and are EXCLUDED from narrative eligibility |
| `asset_preferences` (their side) | account-keyed table | (a) privacy: another user's private list (§5.1); (b) co-owner identity split (§3.3); (c) staleness | stamp-only in v1 — never narrative-eligible (D-B1); resolve via owner ∪ co-owners |
| Depth chart | `players.depth_chart_*` | partial coverage (~149/603 RBs), not a usage model (D-121 note) | facts only in evidence ("RB2 on his NFL depth chart"), never workload claims |
| League settings / starter slots | league sync | superflex/IDP variance | feeds the envelope check |
| `fit`/`fit_diag` stamps | M3 rail | bake-off decks only; null on unscored cards | reuse when present; recompute via same code path when absent (organic decks) |

### 3.2 Stamp shape and versioning

```json
"breaker": {
  "ver": "brk-1",              // BREAKER_VERSION — bumped on ANY predicate, severity,
                               // threshold, template, or evidence-shape change (fit
                               // SCORER_VERSION precedent: the readout refuses to
                               // compare across versions). Copy changes bump it too:
                               // a reworded template changes user behavior, and a
                               // calibration window straddling it is two experiments.
  "top": {"code": "fit_outlook", "severity": 0.82, "basis": "inferred",
           "evidence": {"outlook_src": "legacy", "...": "..."}},
  "objections": [ ... ],       // every class: scored, skipped, or degraded — never absent
  "narrated": true,            // whether the hesitation line rendered (flag + floor + eligibility)
  "degraded": null,            // rung marker per §2.3
  "ms": 4.1
}
```

- Rides the card attribute → copied into `deck_impressions.features_json.breaker` inside the
  existing features block. **T2 executemany discipline:** the key is present (null-valued when
  unscored) on EVERY row of a deck — extend `test_impressions_uniform_columns`. It rides INSIDE
  `features_json` (one column), so the first-row-keys compilation trap cannot drop it.
- **Both draft paths** (fit F-6 trap): any logic keyed to "served" cards must hold under
  `compose_deck` AND `team_draft` (`group_size` ∈ {0, N}); the stamp itself is draft-agnostic
  (applied to ranked lists pre-draft), which is the safer default — keep it that way.
- Evidence values are ids + numbers + enum codes only — no free text, no player names inside
  evidence (names are resolved at template time, narrative-honesty rule §5.2).

### 3.3 Identity: whose preferences, whose board (co-owner trap)

`card.target_user_id` is a LEAGUE identity (roster `owner_id`); `asset_preferences` and
member boards are ACCOUNT-adjacent state. For sole owners the strings coincide; for co-owned
rosters (ADR-012) the roster's declared prefs may live under a co-owner's id. Rule: resolve
counterparty state over **`{owner_id} ∪ co_owner_ids(roster)`** via `sleeper_roster` — the ONE
predicate, never a hand-rolled comparison. Conflicts (two co-owners, contradictory lists): union
for `untouchable`/`not_interested` (either owner's veto is a veto — matches how the give-side
untouchable filter would behave for them), and if two boards exist, the canonical owner's board
wins with `board_src` recorded. This is a deterministic, documented choice, not a claim it's
right — it's *consistent*, which is what calibration needs.

### 3.4 Format envelope (v1)

Fully-scored envelope: Sleeper-format leagues whose starter structure `analyze_roster_strengths`
actually models (1QB/2RB/2WR/1TE base, `sf` superflex QB handling), non-IDP scoring for
depth-based classes. Outside it, the breaker does not guess: affected classes stamp with
`format_gap` and are narrative-ineligible. A 14-team or IDP league gets fewer named hesitations,
not wrong ones. The envelope is enumerated in the LLD and the marker makes its cost measurable
(share of decks with ≥1 format-gapped class rides diagnostics) — that number is the case for or
against widening the envelope in v2, instead of an anecdote.

---

## 4. Decisions (proposed here, for reconciliation; defaults chosen for containment)

| # | Decision | Proposal + why |
|---|---|---|
| D-B1 | **Narrative evidence whitelist — public-observable signals only.** | The hesitation line may be built ONLY from state the counterparty's league-mates can already observe: roster composition, depth-chart facts, league settings, window inferred from public roster shape, or window the counterparty has effectively made public. It may NEVER render from `asset_preferences`, their private board deltas, or their declared-but-not-public preferences. Those classes still *stamp* (dark, server-side, measurement-only). Rendering "they've marked X untouchable" discloses one user's private in-app list to their direct negotiation adversary — a trust breach with no rollback (once read, it's known), and asymmetric: the harmed party never sees the screen that harmed them. §5.1 carries the full argument; PLAN decision register gains a row (this is the sharpest operator question in this draft). |
| D-B2 | **Class maturity ladder: stamp-eligible vs narrative-eligible.** | v1 narrative-eligible: `fit_outlook` (declared or high-margin inferred only), `fit_new_weakness`, `fit_duplicate` (both inside format envelope). Stamp-only in v1: `value_giving`, `other_player_keep`, `roster_crunch` (privacy per D-B1), `shape_aversion` (new logic, no live mirror, no calibration history). A class graduates to narrative by per-class calibration precision from the readout — not by shipping-week optimism. |
| D-B3 | **One composition owner for counterparty-facing copy.** | `build_narrative._opponent_frame` already renders "They're rebuilding — the youth going back fits their timeline" from the same outlook signals the breaker reads. Two independent writers of they-statements WILL contradict on one card ("their rebuild makes this fit" + "their likely hesitation: they're rebuilding"). Rule: when `trade.breaker_narrative` is on, the counterparty-facing sentence slot is owned by one composition site that sees both the frame and the breaker top objection and renders at most one they-sentence, from one shared input snapshot. Flag off ⇒ `build_narrative` byte-identical (guarded by existing snapshot tests). |
| D-B4 | **Severity floors are per-class, not global, and `breaker_min_severity` gates narrative only.** | A single global floor cannot survive R4 (consensus `value_giving` fires near-tautologically at any calibratable global level). Per-class floors are knobs (`breaker_floor_<class>`, five registrations each); the global `breaker_min_severity` is the narrative gate on the surviving top objection. Defaults set from the dark-stamp distribution readout, never shipped-guessed (PLAN §9.4 stands). |
| D-B5 | **The breaker reads the engine's outlook, not its own.** | Tempting fix for the 65% skew: have the breaker call the composite directly. Refused — the breaker would then disagree with the engine that built the card (a card generated *because* the legacy vector called them a rebuilder, breaker says contender — incoherent product). The breaker inherits the served signal, stamps `outlook_src`, and the skew is handled by severity haircut + narrative eligibility (D-B2), not by forking the window model. When the composite graduates for the engine, the breaker follows for free and the stamp shows the seam date. |
| D-B6 | **Anti-repetition guard on the hesitation line.** | Frequency cap: if the same (partner, code) hesitation would render on more than `breaker_max_repeat_frac` of a deck's cards for that partner, render it on the top-severity card only and stamp `narrated:false, suppressed:"repetition"` on the rest. A deck where every card says "they're rebuilding" teaches the user to ignore the line (banner blindness) and reads as a bug. Suppression is stamp-recorded so the A/B readout can distinguish "no objection" from "objection muted." |

---

## 5. Cross-cutting

### 5.1 Trust boundary and privacy (the section that must survive review)

Two distinct exposures, one shared property — the harmed party can't see the harm:

- **Private-state disclosure (D-B1).** `asset_preferences` rows and personal boards are entered
  by a user in their own app with no notice that league-mates might see derived output.
  "Their untouchables: they won't move Chase" rendered to a rival converts a private negotiating
  position into shared knowledge. Even indirection leaks: "they demonstrably value X above
  consensus" is their board. v1 whitelist (D-B1) makes the leak structurally impossible in copy
  while preserving the measurement value of the dark stamp. If the operator wants these classes
  user-facing in v2, that's a consent/product decision (e.g., surfacing only what the
  counterparty has posted to a public trade block via `trade_block_service` — genuinely public),
  not a template edit.
- **Assertions about a person (tone / defamation-adjacent).** The line predicts a named
  league-mate's judgment. Copy rules, enforced by the honesty test (T-4): (1) claims are about
  the ROSTER or observable facts, never mental states — "their roster leans rebuild," never
  "they don't rate your RB" or "they said"; (2) hedged modality is part of the template contract
  ("likely," "may balk"), not optional styling; (3) every named player/position resolves from the
  objection's own evidence ids (D-053 / `_top_received` positions-discipline precedent — the
  sentence can never name what the analysis didn't produce); (4) no template implies FTF has
  inside knowledge of that manager ("FTF data shows Mike…" is banned even where true — it
  advertises surveillance to the one audience guaranteed to include Mike).
- **The mirrored-story check.** When both managers are FTF users, each may read the other's app.
  The structural defenses are D-B3 (one they-sentence per card), §2.4 (mirrored predicates ⇒
  cross-seat coherence is tested), and D-B1 (nothing renders that the counterparty didn't
  effectively publish). Residual risk — two users comparing screens see A's card hedge about B
  while B's mirrored card is enthusiastic — is accepted and bounded: both statements are
  roster-fact-grounded and hedged, so they read as two perspectives, not a contradiction of fact.

### 5.2 Narrative honesty, mechanically

The line renders from `breaker.top.evidence` ids through templates in `trade_narrative.py` —
same file, same no-LLM covenant, deterministic per (evidence, template version). T-4 asserts:
every player name, position, and number in the rendered sentence exists in the evidence dict;
no template renders for a class below its floor, outside its eligibility (D-B2), or outside the
whitelist (D-B1). Sentence-cap note: `build_narrative` caps at 2 sentences today — the
hesitation line's slot within that cap is a PRD/copy decision, but the cap is not silently
raised (mobile card layout was built against it).

### 5.3 Observability — knowing the stamps are missing

- Per-job diagnostics block (FitReport precedent): cards seen / stamped / degraded-by-rung /
  narrated / suppressed, class-fire histogram, p50/p95 ms — riding the existing job diagnostics
  channel, queryable without new tables.
- **Null-share tripwire** (M4 precedent): share of served impressions with `features_json.breaker`
  null, cut by rung marker. Alert threshold = graduation criterion inverted (≥99% coverage means
  the tripwire fires below that).
- **Class-entropy monitor:** a top-objection distribution collapsing to one class (R4) is the
  "wallpaper" failure and is invisible in coverage metrics — entropy over `top.code` per week
  rides the same diagnostics; the calibration readout reports per-class precision *and* fire
  rate, never accuracy alone (majority-class trap, §6 R3).
- Version discipline: every readout query filters `ver = BREAKER_VERSION`; cross-version
  comparison refuses (fit M2 precedent).

### 5.4 Test spine (beyond scope §3's list — the sabotage set)

| # | Test | Kills which risk |
|---|---|---|
| T-1 | byte-identity: flags off ⇒ decks byte-identical, module never imported | R8 |
| T-2 | exception sabotage: predicate raises ⇒ deck job completes, card null-stamped, counter incremented | R7-adjacent (isolation) |
| T-3 | interleave inertness: stamp+narrative on ⇒ deck ORDER identical on bake-off decks, both draft paths (`group_size` ∈ {0, N}) | R8 |
| T-4 | narrative honesty + whitelist: rendered sentence ⊆ evidence; private-source classes never render | R1, R6 |
| T-5 | uniform columns: `breaker` key on every impression row (extend `test_impressions_uniform_columns`) | R8 |
| T-6 | cross-seat coherence: mirrored fixture card — breaker(seat B) high-severity ⟺ B's viewer-seat predicate flags the mirror | R5b |
| T-7 | binding sabotage: monkeypatched `ts` predicate/knob propagates into breaker verdict (T1 trap) | drift class |
| T-8 | budget ladder: forced-slow predicate ⇒ rung markers correct, no unlabeled missingness | R2 |
| T-9 | co-owner fixture: prefs under co-owner account are found; two-board conflict resolves per §3.3 | R6 |
| T-10 | envelope: 14-team / IDP fixture ⇒ depth classes `format_gap`, narrative-ineligible | R6 |
| T-11 | anti-repetition: N same-partner same-code cards ⇒ one narrated, rest `suppressed:"repetition"` | R4 |
| T-12 | determinism: same snapshot + card ⇒ identical stamp bytes across runs | calibration validity |

---

## 6. Risk register (the star) — ranked

Severity = product damage × likelihood-as-designed-without-the-mitigation. Every row carries a
proposed fix or a sharp question; no row is decoration.

| # | Sev | Risk | Mechanism | Fix / question |
|---|---|---|---|---|
| **R1** | **Critical** | **Private-preference leak to a negotiation adversary.** | `other_player_keep`/`roster_crunch`/board-basis `value_giving` render another user's private lists/board in the viewer's copy; harmed party never sees the screen; no retraction possible. | D-B1 whitelist: private-source classes stamp dark, never render, v1. **Operator question (decision-register row): do you accept that `other_player_keep` — arguably the most persuasive objection — is measurement-only until a consent story exists (e.g., public trade-block state only)?** |
| **R2** | **Critical** | **Systematically wrong window objections at scale.** | Engine-facing outlook = legacy vector, ~65%-rebuilder skew (A-4); declared outlooks stale; `fit_outlook` is the marquee class (33% of real pass reasons). Wrongness is *correlated*, not noise: the same wrong claim about the same manager on card after card, screenshot-able. A confidently wrong objection is worse than none — it spends trust the calculator never had to earn. | D-B5 (inherit + `outlook_src` stamp) + D-B2 (inferred-window narration only above a high margin; declared preferred) + severity haircut by source + calibration readout cut BY `outlook_src` before narrative graduation. Sharp question: should `fit_outlook` narration wait for the composite to graduate engine-wide, full stop? Default here: no — declared-window cases are safe now; inferred-window cases wait on the margin bar. |
| **R3** | **High** | **Calibration theater.** | §6.2a's counterparty-seat cut needs both-FTF pairs AND a served mirror: 96.3% one-directional × 84.5% unboarded ⇒ n≈0 for quarters. The same-seat shadow (§6.2b) validates viewer-seat prediction — a *different quantity* (selection: viewers file reasons about cards SERVED to them; the breaker predicts declines of cards that mostly never reach the counterparty). And with 40% `value_giving` base rate, "always predict value_giving" scores 40% match — a readout reporting match-rate alone will flatter. | Preregister the readout: per-class precision/recall vs majority-class and stratified-random baselines; minimum n per cell before any graduation claim; label §6.2b explicitly as proxy validation with its selection caveat in the readout doc; treat §6.2a as a long-horizon accumulator, not a launch gate. Add the §2.4 internal-consistency check (breaker vs mirrored viewer-gates) as a third, population-independent validity signal. |
| **R4** | **High** | **Dominant-objection collapse / wallpaper.** | Unboarded ⇒ their-seat `value_giving` = consensus optics; viewer receives more on 86.3% of consensus cards ⇒ the class fires near-universally; the hesitation line becomes "they'll want more" on every card → banner blindness kills the feature's information value, and the stamp distribution becomes useless for §6.4. | D-B4 per-class floors (consensus-basis `value_giving` floor set materially higher than board-basis) + D-B6 repetition suppression + §5.3 entropy monitor with an explicit red line before narrative graduation. |
| **R5** | **High** | **(a) Self-contradicting card copy; (b) cross-seat story mismatch.** | (a) `_opponent_frame` and the breaker write they-sentences from the same signals via different code → one card asserting "fits their rebuild" and "they'd balk: rebuilding" (or window fine-print drift between the two). (b) A's breaker damns a card whose mirror B's app served approvingly. | (a) D-B3 single composition owner, one they-sentence max, shared snapshot. (b) §2.4 mirrored-live-predicates rule + T-6; residual accepted per §5.1. |
| **R6** | **High** | **Wrong counterparty state — the input-wrongness family.** | Co-owner identity split (prefs/board under the other account); G-045 partner missing from pool; G-026 IDP/K zero-values corrupting depth; `_POS_TIER_CUTS` 12-team assumption mis-tiering 10/14-team leagues; stale boards. Each yields a specific, checkable, WRONG hesitation. | §3.1 handling table is normative: every input has a degrade path and a stamp marker; §3.3 co-owner resolution via the ONE predicate; §3.4 envelope with `format_gap`; T-9/T-10. Boards staleness: Q-B1 (is board age recoverable? if not, log as OPEN_QUESTIONS — shipping board-based severity with unbounded staleness gets a haircut knob). |
| **R7** | **Med** | **Latency on the widened path.** | Unlike fit_diag, organic decks are stamped too; per-card feasibility across 4 arms × N cards can eat the 60s job budget; naive over-budget truncation biases stamps by rank and poisons §6.4. | §2.2 per-partner amortization + §2.3 tiered ladder with labeled missingness + `breaker_ms_budget` p95 gate as a graduation criterion + W0-style dry-run ms number handed to the operator before flag-on (fit precedent). |
| **R8** | **Med** | **Ordering/serving contamination.** | Any reorder — even accidental (dict iteration, in-place sort in a predicate, narrative site touching composition) — breaks bake-off attribution (`bypass_rerankers` discipline) silently. Also T2: a conditionally-present `breaker` key dropped by executemany on mixed decks. | T-1/T-3/T-5 byte-level tests; stamp is attribute-only, no return values consumed; narrative append happens at composition, never at ranking; uniform-keys extension. |
| **R9** | **Med** | **Version-skew corruption of the readout.** | Predicate tweaks, floor changes, or a mere template rewording mid-window changes user behavior and predicted-code distribution; a calibration window straddling versions is two experiments summed. | `BREAKER_VERSION` bumps on ANY logic/threshold/template/evidence change (§3.2); readout refuses cross-version; `model_config_changes` censors windows (M1 rail); knob flips via `set_knob.py` only. |
| **R10** | **Med** | **Measurement inheritance traps.** | Ghost rows (ended 2026-08-21, A-1 unverified), D-091 phantom-pick window, one-engine-change-per-tester-week collisions with sibling flips. | Data boundaries restated in the readout spec verbatim from PLAN §6; A-1 verified via `model_config_changes` before defining any window; change-control calendar shared across the three-sibling batch (one operator, three eager plans — name the collision risk in the reconciliation log). |
| **R11** | **Low** | **Scope creep at the seam: breaker verdicts get read by generation.** | Once stamps exist, it is one tempting line for a generator or reranker to consult `card.breaker` — silently becoming v2 without gates. | Inertness test (T-3) + explicit grep-guard test: no module outside the stamp site and serialization reads the attribute (`test_fit_diag_inert` precedent, extended); v2 bright line restated in DECISIONS entry. |
| **R12** | **Low** | **Sibling taxonomy drift.** | Extensions (`shape_aversion`, `roster_crunch`) land in taxonomy 1.1.0 via this session's PR; if negmem starts recording historical rejections in a divergent private vocabulary while sign-off pends, the "one vocabulary, two tenses" promise dies quietly. | Taxonomy §5 already reserves the section with producer-column convention; the extension PR is a deliverable of THIS thread (before PRD), not an afterthought; A-2 reconciliation before operator delivery. |

## 7. Assumptions to verify at build (extends PLAN §10)

- **A-4:** the ~65%-rebuilder legacy-outlook skew figure — sibling/audit-reported; re-derive from
  current data before setting `fit_outlook` haircuts.
- **A-5:** mirrored-card served-both-directions rate (~3.7% implied by the 96.3% figure) — the
  §6.2a population estimate; measure precisely before promising that cut a timeline.
- **A-6:** whether board last-ranked-at is recoverable for staleness handling (Q-B1).
- **A-3 (inherited):** exact stamp-site line numbers; drift expected.

## 8. Open questions for the operator (decision-register candidates)

1. **R1:** accept `other_player_keep`/`roster_crunch`/board-basis-`value_giving` as dark-stamp-only
   in v1 (D-B1)? If no — what consent/visibility story makes rendering them acceptable?
2. **R2:** should inferred-window `fit_outlook` narration wait for the composite's engine-wide
   graduation, or ship behind the high-margin bar proposed here?
3. **D-B6:** is per-deck repetition suppression acceptable, given it makes the narrative line's
   presence depend on deck context (same card, different decks, different narration)?
4. Sentence budget: does the hesitation line get the second slot of the existing 2-sentence cap
   (displacing pick/window framing), or a third sentence (layout review)?

---

*Draft B ends. Deliberately not written: knob-by-knob LLD tables, template texts, exact
predicate pseudo-code — LLD territory. This draft's claim is narrower: if the risk register's
Critical and High rows are not answered in the reconciled HLD, the feature will ship as a
confident-sounding wrongness generator with an unmeasurable calibration story, and the first
screenshot of a wrong hesitation about a real league-mate will cost more trust than every
correct one earned.*
