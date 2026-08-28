# Plan: Outlook-aware trade engine — window-conditioned age bias and pick flow

> **Purpose:** execution plan for the operator's 2026-08-27 direction: *"H1 speaks to mixing in the
> outlook into the engines. And ensuring that users get more picks offered and give up picks less
> if they are rebuilding or tanking. Let's plan out adding age bias (although there should be some
> implicitly added by the consensus values so that may be what speaks to what you're seeing on
> consensus vs. divergence)."*
> Grounding: [outlook-age-grounding.md](outlook-age-grounding.md) (measured F1–F6) ·
> [outlook-age-code-map.md](outlook-age-code-map.md) (code inventory) ·
> [champion-recommendation.md](champion-recommendation.md) (freeze constraint) ·
> [hypothesis-results.md](hypothesis-results.md) (H1/H3/H5/H7).
> This plan RECOMMENDS; the operator flips every flag and knob, at explicitly chosen moments.
> Authored via dual-agent draft + adversarial cross-review (4 rounds, both lenses signed off);
> reconciliation log at the end.

## 1 · Objective & Definition of Done

**Objective.** Fix the one place the data says the engine is outlook-broken — **pick-flow
direction** — and close the age-bias question with a recorded decision, without repricing assets
against the standing D-079/D-161 flat-firsts rulings, without silently reversing the 2026-07-17
"age = tiebreak" ruling (encoded at `backend/trade_service.py:5710–5716`), and without restarting
the interleaved arm-read clock before a deliberate, batched round boundary.

**The defect (F3, measured):** the declared rebuilder is asked to GIVE picks on 43.9% of served
cards and offered picks on 11.1% — the inverse of operator intent. **F5 proves it is
generation-level:** the inversion existed with the `outlook_direction` reranker ON (receives 6.5%)
and OFF (12.7%); reordering cannot fix inventory-driven pool selection.

**Program Definition of Done** (all offline/dark — the flip is the operator's, and its timing is
outside this program's control):

1. The pick-flow levers exist as `model_config` knobs, default **0 = byte-identical off**, merged
   dark, each with full D-056 evidence (structural tests + code-walk proofs + the offline
   served-mix matrix) in TEST_LEDGER.
2. The age-bias question is **decided and recorded** in DECISIONS.md — hold or overturn, either
   way a D-number. Silence is not done.
3. Rebuilder-detection is dispositioned: composite-into-engine wiring merged dark with a
   label-churn readout, or explicitly deferred with the flip correspondingly scoped
   declared-only (the scope mechanism exists either way — see WS2 invariants).
4. An operator decision packet exists: recommended knob set, kill values, measured offline
   served-mix deltas, TestFlight checklist, and the clock statement (any flip restarts the
   5–7-week arm read; batch everything, restart once).

**Post-flip success criteria** (M5.3 watch, NOT program DoD — they need the operator's flip):
primary = for rebuild-side viewers, served gives-pick % ≤ receives-pick % within 2 weeks (today
43.9% vs 11.1%). Guardrails as hard aborts, all measured as **deltas against the M0.2 frozen
baseline and cut by affected population** (targeted-job empties are segmented out — the untouched
system already sits at 4.89%/5.05% empty, so an absolute >5% trigger would fire on baseline noise
and discredit the abort). The affected population follows the flipped knobs: rebuild-side
viewers' organic decks for the outlook-scoped levers, and **if `give_far_pick_penalty` (A2, the
outlook-independent knob) flips nonzero, the empty-deck abort cut extends to ALL viewer-outlook
organic-deck populations, each against its own M0.2 per-outlook frozen baseline** — a safety net
that doesn't watch the affected population is not a safety net. Empty-deck rate +1.0 pp sustained
7 days in any watched population ⇒ abort; consensus-basis first-5 insult above 3%
(currently 1.48%) ⇒ abort; give-far-first like-rate *within still-served cards* falling ⇒
escalate (R5). Abort execution: the watching session recommends same-day; **the operator writes
the kill values** via the admin config API (deploy-free).

**Pre-declared as unmeasurable (goes in the ledger verbatim):** rebuilder like-rate. One declared
rebuilder and 3 users producing 95% of decisions (F4, readout §Power) means no like-rate read on
this cut can ever be powered in a realistic window. This ships on served-mix evidence + judgment +
deploy-free kill switches, and no future write-up may cite rebuilder like-rate as evidence
(risk R9).

## 2 · Scope

### In scope

- **WS2 — generation-level pick-flow steering** (the build): levers behind neutral-default knobs,
  offline-graded by the logged-deck method.
- **WS3 — age-bias decision memo** + operator decision (recommendation: hold — build nothing new).
- **WS4 — rebuilder-detection wiring** (composite classifier into engine callers), merged dark; a
  flip prerequisite for inferred-outlook coverage and a build prerequisite for M2.4's
  composite-labeled cells.
- **WS1 (conditional) — `outlook_direction` redesign-vs-relight**, graded offline via F8 — runs
  only on explicit go (F8 has a real bring-up cost; see WS1).
- **WS0 — pre-tasks:** age-hydration hygiene, F8 feasibility spike (if WS1 goes), mirror refresh +
  baseline snapshot.
- **WS5 — decision packet, batched boundary flip, post-flip watch.**

### Out of scope — explicit non-goals, each protecting a standing ruling or thread

| Non-goal | Protects | Failure mode if violated |
|---|---|---|
| Any change to pick **pricing** (`pick_year_decay_r1`, `market_r1_yoy_floor`) | **D-079/D-161**, operator-ruled twice | Steering + repricing at once makes both unmeasurable and overturns a twice-made call by side effect |
| Lighting `trade.outlook_blend` without a recorded overturn | **2026-07-17 age-tiebreak ruling** | An assumed overturn of an explicit operator decision |
| Re-lighting `trade.outlook_direction` as-shipped | **F6** — its own experiment metric (fit_outlook pass share 32.2%→15.1% when turned OFF) argues against it | Re-lighting a flag whose only readout opposes it |
| A new global app-side age curve | **F1 + F2** — consensus already prices the RB-27/WR-30 cliffs; user boards lean *against* the youth premium (u23 Δz −0.080) | Double-counts consensus AND fights the users' own boards |
| Champion/arm changes, negmem, F6 value model, H5 QB/format work | Champion doc holds; separate gated threads | Scope creep across measurement streams |
| Any served-config write during the freeze | The 5–7-week arm read | Clock restarts without a decision |
| Mobile/web client changes | — | Not needed: every lever is backend generation/assembly; scope blocks re-verify per item |

**H1 residual, stated honestly:** this program treats the *outlook-conditioned* slice of H1 plus a
mild global far-first-give demotion (Lever A2). It does **not** reach gen_v2's generation (the
worst offender at 46.4% give-far-1st — its exposure is governed by the OQ-3 arm-C decision, where
the champion doc already prefers removal), and the F3 cuts show championship/contender viewers
also dislike pick-gives at strengths this program only partially addresses. §8 keeps a residual-H1
line in NEXT.md; this plan **partially addresses** H1, it does not close it.

## 3 · Workstreams & Milestones

Owners: **[Op]** = operator (decision/flip/TestFlight) · **[Ag]** = agent session. Every build
milestone runs the full feature gates (scope block → D-056 evidence → docs table → TEST_LEDGER).
**No item is express-eligible** — all touch `model_config`/flag surface (the bright line).

### WS0 — Pre-tasks

- **M0.1 — Age-hydration hygiene [Ag].** `backend/server.py:1599, 1618` default missing age to 25,
  making the age curves' "no age ⇒ 1.0" branch mostly unreachable. **Measured blast radius:
  effectively zero today** — 0 of the 202 players above consensus value 300 lack age (2026-08-27
  mirror); nulls concentrate in deep waiver bodies. So this is hygiene, not a blocker: change
  hydration to carry `None` honestly, audit every `Player.age` reader (outlook inference vet/youth
  shares, taste age bands, lanes, narrative) for None-safety, add a unit pinning missing-age ⇒
  multiplier 1.0 end-to-end, **and a structural test asserting the null-age count among top-value
  pool assets stays 0** (a Sleeper dump regression would silently re-arm the default-25 path).
  Because inference reads age, the code-walk must state the live served-behavior delta; if
  nonzero, the deploy queues for the flip boundary. Hard prerequisite only for any future
  age-curve lighting (WS3 options i–iii).
- **M0.2 — Baseline snapshot + mirror refresh [Ag].** Re-pull the read-only mirror (2026-08-27
  ledger protocol) and freeze F3's gives/receives-by-outlook table **and the per-population
  empty-deck baseline (organic vs targeted, by viewer outlook)** as the before-picture every
  offline grade and post-flip abort threshold diffs against. TEST_LEDGER `measured` entry.
- **M0.3 — F8 feasibility spike [Ag] (only if WS1 gets its go).** Two halves: (i) field-coverage
  matrix — can `outlook_direction_mult` (`trade_service.py:3303–3403`) be recomputed per logged
  card from frozen `features_json` (pick direction, per-side positions/ages, serve-time outlook)?
  Name the fallback (mirror-join to `players.age`, age-drift stated) if not. (ii) **F8 bring-up
  reality:** the harness has never run for real — no `data/eval_runs/` exists and no TEST_LEDGER
  entry records the PRD's self-consistency acceptance check
  (`docs/plans/tiktok-discovery/prds/F8-offline-eval.md` §Acceptance). Bring-up (self-consistency
  on prod logs + broken-scorer check) is the spike's second deliverable and a real 1–3-session
  cost. Go/no-go for WS1 stated at the end.

### WS1 — `outlook_direction`: redesign vs relight (CONDITIONAL — off the critical path)

Pure reranker ⇒ exactly what F8's replay/IPS design grades. But three things demote it from the
default path: F6 (its own experiment metric argues against as-is relight), F5 (a reranker cannot
fix served MIX — WS2 owns that), and the unrun-harness bring-up cost (M0.3). **Default: leave
dark; WS2 carries pick flow.** WS1 runs only if the operator wants the redesign question answered
(OQ-4) or spare capacity exists after WS2's critical path is safe.

If it runs — **M1.1 [Ag]:** F8 replay of (a) `outlook_direction` as-shipped and (b) one
"pick-direction-only" redesign variant (age-gap ×0.15 rule softened, contend-side mirror dropped)
against the logged policy. Protocol: time-ordered split; pre-/post-08-20 windows reported
separately (the flag was live pre-08-20); SNIPS primary with IPS and Kish ESS reported;
`ESS < floor ⇒ UNRELIABLE ⇒ no recommendation`. Verdict ∈ {relight as-is (bar deliberately high
given F6), redesign, leave dark}; enters the M5.1 packet only — no serving change in any case.

### WS2 — Pick-flow generation-level treatment (the core build; critical path)

**Design invariants for all levers:**

- Knob in `trade_service._DEFAULT_CFG` + `database._MODEL_CONFIG_DEFAULTS`, default 0 =
  byte-identical off (golden-asserted).
- **Demote, never hard-exclude** in candidate generation (a pool exclusion is what G-058's co-kill
  data says the conjunctive stack routes around, and it breaks legitimate pick-consolidation
  ideas). **One recorded exemption:** Lever B filters candidates *inside the sweetener passes* —
  acceptable because both passes carry a no-thinning contract (a card the pass cannot close ships
  unsweetened; `trade_optimizer.py:~700–706`), so the filter can never remove a card. Future
  G-058-style audits should read this as the designed exception, not a violation.
- Predicates called through the module object per D-098 (`ts.<fn>(...)`) — never value-bound at
  import (G-058 cause 3).
- **Source-scoped outlook plumbing (required build item, not an option):** today the engine sees
  one unmarked `outlook` value — the user side merges declared and `trade.outlook_seed` inference
  with no source marker (`server.py:5854–5898`), and the opponent side merges
  declared-vs-inferred at `trade_service.py:5809–5821`. The levers thread **`(outlook, source)`**
  through both seams and read a scope knob **`outlook_steer_scope`** (0 = **declared-only**
  [default], 1 = any-resolved), so packet-time scoping (WS4 rule, R3 fallback) is a deploy-free
  config write, and M2.4's label-source cells correspond to real flip-time configurations. (The
  opponent-side seam already threads source into `match_ctx` — `trade_service.py:5813–5821` — so
  the plumbing cost concentrates on the user-side seed overwrite, which slightly de-risks the W2
  estimate.) Flipping `trade.outlook_seed`/`outlook_infer` is NOT the scoping mechanism — those
  feed R5, lanes, and fit, and using them would be collateral behavior change.
- `not_sure`/unresolved outlook ⇒ inert (mirroring `outlook_direction_mult`'s own convention,
  `trade_service.py:3351–3353`); rebuild side = {rebuilder, jets} treated identically (OQ-5
  default). **Second recorded exemption:** `give_far_pick_penalty` (A2) is outlook-independent by
  design — the inert rule and `outlook_steer_scope` do not apply to it (detail in M2.1).
- `MODEL_A_PROFILE` pins every new knob at 0 and `_GOLDEN_FLAG_PINS` gains any new flag **in the
  same commit** (WS4 integrity rules).

**M2.1 — Lever A: give-side pick demotion [Ag].** Two knobs at the shared post-enumeration
scoring seam in v2/v3:
- `outlook_give_pick_penalty` (0 = off): fractional score demotion on packages where a
  **rebuild-side** viewer gives a pick, strongest for far-year firsts — the operator's core ask.
- `give_far_pick_penalty` (0 = off): a milder, **outlook-independent** demotion on far-year-first
  gives — the global H1 exposure treatment (give-far-first cards like at 9.3% across all outlooks;
  championship viewers like pick-gives at 1/10 and pick-receives at 9%, so the aversion is not
  rebuild-specific). Kept as a separate knob so the operator can light the rebuild-side fix
  without the global one, or both; M2.4 grades them separately and jointly. **A2 reads no
  outlook by design: it is unaffected by `outlook_steer_scope` and exempt from the
  not_sure-inert invariant** — a builder must not gate it on resolved outlook, or it silently
  excludes the unlabeled majority it exists to reach. Its abort-population consequence is in §1.

**M2.2 — Lever B: sweetener direction bias [Ag].** Knob `outlook_sweetener_pick_bias` (0 = off).
**Covers BOTH sweetener seams** — under live `trade.picks_in_pool`, PICK pseudo-assets are
injected into the rosters both passes draw candidates from (`server.py:11286–11372`,
`_owned_pick_assets` → `_inject_owned_picks`), so both can draft a viewer's pick out as balancing
currency:
- `close_value_gap` (`trade_optimizer.py:836+`): viewer is rebuild-side and viewer's side would
  add the equalizer ⇒ filter PICK candidates (a rebuilder never has a pick auto-drafted out as
  currency); opponent side adds ⇒ sort pick candidates first (pick equalizers flow TOWARD
  rebuilders).
- `_try_sweeten` (`trade_optimizer.py:770+`): same viewer-side PICK filter in its candidate list.
  Its docstring ("Sweeteners are players only", :786–787) is **stale** — the caller's own C3
  comment (`trade_optimizer.py:681–684`) says "the sweetener can itself be a pick"; the docstring
  is corrected in the same commit.
Zero deck-thinning risk on both (no-thinning contracts). **B ships with A** — without B, the
sweetener passes re-insert the picks A demoted (a known-leaky config otherwise; the packet says
so).

**M2.3 — Lever C: deck-assembly direction quota [Ag] (backstop, expected to stay dark).** Knobs
`outlook_deck_give_pick_cap` / `outlook_deck_recv_pick_floor` (0 = off). Cap = leave-short, never
backfill (D-078); floor = soft promotion up to target, because supply is real — a rebuilder's
opponents may hold no spare picks; unmet floors are stamped, not stuffed. Applied at
`_dedup_and_sort` **plus the two bypass branches** (gen_v2 branch of `_generate_trades_impl`,
`bakeoff_runner.gen_v2_cards`) — the exact D-082 lesson. Named risk: on a 43.9%-gives-pick deck
the cap binds hard (D-082 precedent: a give-headliner cap of 2 removed 23.8% of cards);
co-binding with `deck_give_headliner_cap` measured jointly (G-058 change-in-pairs).

**M2.4 — Offline grade + recommendation [Ag].** Generation-level change ⇒ **logged-deck replay
method, not F8** (champion doc §Method note): regenerate decks offline against the M0.2 mirror's
real league inputs for the matrix {off, A1, A2, A1+A2, B, C, A1+B, A1+A2+B, A1+A2+B+C} — the A
split is required because M2.1 ships two knobs and the G-058 rule demands per-knob unique effect;
**the pre-registered "A+B primary" means A1+B, with A2's value (including 0) decided by its own
matrix cells** — each cell × viewer outlook ×
**label source (declared-only / legacy-inferred / composite-inferred)**, where the label-source
axis exercises the real shipped `outlook_steer_scope` mechanism and quantifies detection-quality
sensitivity (feeds OQ-2). **The composite-inferred cells import M4.1's merged resolution wiring —
hard ordering, see §4; if M4.1 slips, the matrix ships declared/legacy-only and OQ-2 defaults
declared-only.** The readout states which generators were regenerated (v2/v3 + consensus; gen_v2
only via the bake-off adapter) and **weights predicted served-mix deltas by current interleave arm
shares** — the prediction is only honest under an explicit arm-mix assumption, and it interacts
with OQ-3's arm-C decision.
Per cell: gives/receives-pick mix (the F3 table, corrected); deck-size distribution, worst deck,
distance to `_DECK_MIN_CARDS = 5`, empty-rate vs the M0.2 per-population baseline; **unique-effect
attribution per knob** (G-058: a knob showing zero unique effect is not shipped — redesigned or
dropped, null recorded in MISTAKES.md); H8 consensus insult rule ≤ 3% and fairness guardrails per
cell (a failing cell is disqualified outright).
*Pre-registered recommendation to validate, not assume:* **A+B primary; C stays dark as backstop**
unless the matrix shows A+B insufficient to de-invert the mix.
*Done bar:* matrix readout; one recommended knob-value set with expected served-mix deltas +
arm-mix assumption; kill-value goldens (knobs at 0 ⇒ byte-identical decks) in the suite;
scope-block Docs table (per-knob `docs/config-reference.md` rows — mandatory; api-reference n/a;
LLD generation-seams note incl. the `(outlook, source)` plumbing); TEST_LEDGER entries.

### WS3 — Age bias: decision memo + operator decision

- **M3.1 — Decision memo [Ag].** Four options with the measured case, recommendation **(iv)**:

  | Option | Case for | Case against |
  |---|---|---|
  | (i) Light `outlook_blend` as-is | Built + unit-tested; curves specced (tier-2 2.2) | Reverses the age-tiebreak ruling; F1 double-count on the *now* axis; F2 headwind; **never reaches consensus-basis cards (~62% of decided — `_consensus_kw` passes no alpha, `trade_service.py:5825–5848`) or gen_v2** ⇒ a two-regime deck plausibly worse than either pure regime and unmeasurable at our n; zero offline evidence |
  | (ii) Soften the α map, then light | Milder tilt | Same reversal, same 62% coverage hole, same F1/F2 headwind — tuning doesn't answer the objections |
  | (iii) Extend the blend to the consensus path, then light | Closes the coverage hole | Largest blast radius: touches the fairness-adjacent consensus generator; FR8 golden ("outlook moves surpluses, never fairness", `test_fairness_gate_golden.py:224–245`) must keep passing; full re-capture review; still reverses the ruling, still fights F1/F2 |
  | **(iv) Hold — build nothing new** *(recommended)* | F1: age is already in the prices. F2: the market's youth premium already overshoots these users' boards. The swipe-side youth appetite (H3) is an *acquisition* appetite the live taste layer already learns per user; window-conditioning belongs in exposure — which is WS2. Honors the standing ruling and directly answers the operator's parenthetical: **the consensus-carries-age suspicion is confirmed (F1)** | Leaves built machinery dark; a *visible* window-tilted value never ships |

- **M3.2 — Operator decision [Op].** One sitting with the memo. Outcome is a DECISIONS.md entry
  either way: a hold record citing F1/F2 (closes the ask), or an explicit overturn D-number — in
  which case options i–iii become a NEW full-gates item with its own plan (prereqs: M0.1,
  consensus-path coverage design for (iii), golden re-capture review), **not absorbed into this
  program's timeline** (risk R7). Default if unanswered: hold.

### WS4 — Rebuilder-detection wiring + test-surface integrity

- **M4.1 — Composite-into-engine wiring [Ag], merged dark.** The legacy inference vector
  (`vet_share − youth_share − 2·(pick_share − 1/teams)`, `trade_service.py:3634–3865`)
  misclassified the operator's own all-in team as a rebuilder — and it reads high pick-share as
  rebuild, so a pick-hoarding contender would get exactly the wrong steering. Dark
  `trade.outlook_composite` (D-140) fixes it but reaches only Team Review (needs a caller-supplied
  `starter_signal`). Wire `starter_signal` (and, where cheap, the net-firsts ledger) into the
  engine's outlook resolution (`server.py:5854–5898` user side; `server.py:5915–5946` +
  `trade_service.py:5809–5821` opponent side — the same seams the WS2 `(outlook, source)`
  plumbing touches), behind the existing flags — no new flag. *Done bar:* code-walk proof of every
  inference call-site now composite-capable; mirror re-classification of all league members
  legacy-vs-composite with **label churn reported** (every changed label also moves R5 gating and
  lane framing — say so); the operator's team classifies correctly; docs + ledger. The #365
  TestFlight checklist folds into M5.2's.
- **Flip-scoping rule:** the flip packet offers `outlook_steer_scope = 1` (any-resolved,
  composite-informed) **only if** M4.1 is merged and its label-churn spot-check passed; otherwise
  the packet recommends the default `outlook_steer_scope = 0` (declared-only — honest reach: ~1
  rebuilder today, a correctness-and-containment ship). Both are packet-time config writes
  because the scope knob ships in WS2. False-rebuilder is the dangerous direction; `not_sure`
  stays fail-open forever.
- **Integrity rules (every WS2/WS4 merge):** new flags join `_GOLDEN_FLAG_PINS`
  (`backend/tests/support/bakeoff_harness.py:80–91`) in the same commit; every new `_DEFAULT_CFG`
  knob is dispositioned in the arm-A knob-inventory guard (`test_bakeoff_arm_a_golden.py:455+`):
  pinned at kill in `MODEL_A_PROFILE` or excluded with written proof. The goldens are pinned to
  `outlook_direction: True` — levers at kill values must not disturb them; asserted in CI.
  **Shared-file merge protocol:** M2.x and M4.1 edit the *same resolution seams*
  (`server.py:5854–5898`, `trade_service.py:5809–5821`), not just the same files — so M4.1
  sequences **after** the M2.1+M2.2 merge (the `(outlook, source)` plumbing lands first and M4.1
  builds on it); any second merger into shared files rebases, re-runs the arm-A golden AND the
  `(outlook, source)` plumbing's own unit assertions before push — the golden catches kill-value
  drift but not a semantic mis-merge of the source marking.

### WS5 — Decision packet, batched flip, post-flip watch

- **M5.1 — Operator decision packet [Ag], maintained as a LIVING DRAFT from W2 and
  decision-ready by end of W4** (see §5 — at the early end of the read window the packet, not the
  clock, gates the flip). Contents: recommended knob set + measured offline deltas (M2.4) +
  arm-mix assumption; flip-scoping per the WS4 rule; WS1 verdict if it ran; M3.2's decision
  record; complete flip list with kill values (all deploy-free); the TestFlight checklist; and
  the clock statement in bold: **each of these is a served-config change; they restart the
  5–7-week interleaved arm read and must land together at a round boundary, batched with every
  other pending flip the operator wants — the standing `overpay_adjusted` Q-034 record, Q-031's
  `bakeoff_include_gen_v2` call, any knockout residue, negmem's D-147 two flips — so the clock
  restarts once, not four times.** Named pollution risk: if WS2 suppresses give-far-firsts in arm
  `current` while gen_v2 (46.4% give-far-1st) keeps serving, the deck-level H1 read is polluted
  by arm mix — either arm C leaves the roster in the same batch (champion doc's preference) or
  the readout segments by `model_arm`; decided in OQ-3, not discovered in the readout.
- **M5.2 — The flip [Op].** At the operator's boundary — defined as
  **max(powered-read maturity, packet-ready)**: recommended on/after the powered read
  (~2026-09-24 → 10-15 at current traffic), and if the read matures before the packet, the
  boundary honestly slips to packet-ready rather than flipping unreviewed. Earlier only by
  explicit operator call trading the remaining read for the fix (F3 is live harm to rebuilders;
  that trade is theirs — OQ-1). Operator flips, runs the TestFlight checklist (a rebuild-outlook
  account's deck: no pick auto-drafted from their side as equalizer in either sweetener pass;
  give-pick cards demoted; deck not visibly thin; Team Review outlook beat sane under composite),
  session logs CHANGELOG + TEST_LEDGER + the new arm-clock start date.
- **M5.3 — Post-flip watch [Ag].** Week-1 and week-2 served-mix readout (F3's exact query) vs
  M2.4's predicted deltas; guardrail deltas vs the M0.2 baseline per §1 — **watching every
  population §1 puts in scope for the flipped knob set** (all outlooks' organic decks when A2 is
  nonzero); abort table §6 governs (agent recommends, operator writes). **Pre-stated read rules:**
  minimum 150 served rebuild-side cards in the window, else the watch extends rather than
  concludes — bounded: after two extension weeks with n still short, the watch concludes
  **"unread — abort triggers remain standing"** rather than extending silently; the "improved but
  not de-inverted" case has a pre-registered disposition — raise A/B knob values within the
  packet-approved range first, light C only if the raised values still miss, never improvise a
  third mechanism.

## 4 · Sequencing & Dependencies

```
WS0: M0.2 mirror ─┬─► M2.1+M2.2 ─► (M2.3) ─┬─► M2.4 matrix ──────────┐
                  │                        │   (composite cells      │
     M4.1 composite wiring ────────────────┴──► need M4.1 merged)    ├─► M5.1 packet (living draft W2→W4)
     M0.1 hygiene (independent; hard prereq only for WS3 i–iii)      │
     M0.3 spike ──► [go?] WS1 M1.1 F8 replay (off-path) ─────────────┤
WS3: M3.1 memo ─► M3.2 [Op ruling] ──────────────────────────────────┘
                                                                     ▼
                     boundary = max(powered read ~09-24→10-15, packet-ready) or operator override
                                                                     ▼
                                           M5.2 [Op batched flip] ─► M5.3 watch
```

- **Critical path:** M0.2 → M2.1+M2.2 → M2.4 → M5.1 → *[boundary]* → M5.2 → M5.3.
- **Hard ordering:** M3.2 before any blend build (never build on an assumed overturn); M2.2 ships
  with M2.1; **M4.1's resolution wiring merges before M2.4's composite-inferred cells run — M2.4
  imports the merged code path, never hand-rolls harness-local composite wiring** (if M4.1 slips:
  matrix ships declared/legacy-only, OQ-2 defaults declared-only); M4.1 merged before an
  `outlook_steer_scope = 1` flip recommendation; WS1's verdict flips nothing by itself; **no
  `model_config` or flag write that reaches generation or serving during the freeze — no "it was
  minor" exemption** (risk R4).
- **The freeze is the build window, not idle time:** every offline milestone completes inside it.
- **Session discipline:** M2.1+M2.2 are ONE session (shared `trade_service`/`trade_optimizer`
  seams — G-058's namespace traps make split ownership dangerous); M2.3, M4.1, and WS1 can run
  parallel in separate worktrees under the WS4 shared-file merge protocol — for M4.1 that means
  **develop in parallel, merge in sequence**: its resolution-seam edits rebase onto the merged
  M2.1+M2.2 plumbing before push, never onto a pre-plumbing `origin/main`; standard rules (branch
  from fresh `origin/main`, recovery-ledger every worktree).

## 5 · Timeline & Effort (start 2026-09-01; agent-sessions; confidence stated)

| Week | Work | Sessions | Confidence |
|---|---|---|---|
| W1 | M0.1, M0.2, M3.1 memo, WS2 scope blocks; M0.3 only if WS1 go (OQ-4 answered by end of W1) | 3–4 | High — read/measure/spike on known code |
| W1–W2 | M3.2 ruling [Op, async; ask-by end of W2] | — | High for option iv; i–iii spawns a new program |
| W2 | M2.1+M2.2 build + tests + code-walks (incl. the `(outlook, source)` plumbing) | 3–5 | Medium — the plumbing, the G-058 checks ×3, and the test-retarget list (~1 session alone) are where estimates slip |
| W2–W3 | M2.3 build (incl. both bypass branches) ∥ M4.1 wiring + churn readout | 2–4 | Medium |
| W3–W4 | M2.4 matrix (9 cells × outlook × label-source; estimate holds from the 6-cell draft — the added cells are replay compute, not new authoring) | 2–3 | Medium — replay infra exists (D-082 method) but unique-effect attribution is new arithmetic |
| W2→W4 | M5.1 living draft, decision-ready end of W4 | 1 (spread) | High |
| (opt) | WS1: M0.3 + F8 bring-up + M1.1 | +2–4 | Low — harness never run; self-consistency unproven |
| W5 | Packet finalization; docs/ledger sweep; slack | 1 | High |
| ~W4–W7 | *Wait:* powered read matures (traffic-paced; the champion doc's own 5–7-week spread) | — | Low on the date |
| Boundary | M5.2 [Op] + M5.3 | 0.5 + [Op ~30 min] | High mechanically |

Total agent effort ≈ **12–18 sessions** (+0.5 at the boundary; +2–4 if WS1 runs) over ~5 working
weeks. **Timeline
honesty:** at the *early* end of the read window (~09-24), the packet — not the clock — gates the
flip; that is why M5.1 runs as a living draft with a W4 decision-ready bar. Only at the late end
(~10-15) does the plan have genuine slack. "The clock is the critical path" holds only if M2.x
lands on the optimistic end; the boundary definition in M5.2 (max of the two) makes the slip
honest instead of silent.

## 6 · Risks & Mitigations (abort/rollback per risk)

| # | Risk | Mitigation | Abort / rollback trigger |
|---|---|---|---|
| R1 | Lever C thins rebuilder decks hard (43.9% of their cards are pick-gives; D-082 precedent: 23.8% loss from a cap of 2); empty-rate baseline already marginal | C is backstop-dark by default; demote-not-gate in generation; soft floor; M2.4 measures thinning per value | Matrix: thinning >15% or any deck near `_DECK_MIN_CARDS` ⇒ C not recommended. Post-flip: empty-deck **+1.0 pp over the M0.2 per-population baseline** (rebuild-side organic decks; ALL outlooks' organic decks when A2 is nonzero — §1), sustained 7 days ⇒ agent recommends same-day, operator writes knobs→0 |
| R2 | **G-058 lying nulls** — a knob measures "no effect" via a hardcoded sibling, co-kill redundancy, or import-bound predicates | Per-knob checklist in the scope block: grep every read; no sibling constants; module-object calls (D-098); M2.4 quotes **unique** effects only | Zero unique effect offline ⇒ don't ship the knob — redesign or drop, record in MISTAKES.md; never leave it dark-and-doubted |
| R3 | **Detection misfire:** legacy vector reads pick-hoarding contenders as rebuilders ⇒ steering aims at exactly the wrong teams | `outlook_steer_scope` defaults declared-only (the mechanism ships in WS2 — deploy-free scoping is real, not aspirational); scope 1 only after M4.1 + churn check; not_sure inert forever | Any operator/tester report of anti-intent steering on a declared team ⇒ same-day knobs→0 recommendation. M4.1 slips ⇒ flip at scope 0, don't hold the packet |
| R4 | **Accidental clock restart** — a merge leaks served behavior early (M0.1's inference inputs are the sneaky one) | Every merge's code-walk carries a "served-behavior delta: none / queued-for-boundary" line; kill-value goldens asserted | A served write lands early ⇒ record the new clock start honestly; no silent "it was minor" |
| R5 | **Steering masks the far-first price tension** instead of fixing it (D-079/D-161 held ⇒ calculator/matches still price flat; "improvement" may be composition, not preference) | Log suppression counts per deck; track give-far-first like-rate *within still-served* separately from serve-share; price explicitly out of scope | Within-served like-rate falls while serve-share falls ⇒ escalate to operator as the pricing question it is (theirs, twice ruled) |
| R6 | **Golden/pin drift** — new flag or knob silently re-prices the arm-A golden (goldens pinned to `outlook_direction: True`) | Pin additions ride the same commit as every new flag/knob; arm-A golden + knob-inventory guard in CI; shared-file merge protocol (second merger rebases + re-runs) | Guard red ⇒ merge blocked |
| R7 | Operator overturns age-tiebreak (M3.2 = i–iii), expanding scope mid-program | Memo pre-scopes each option's cost + FR8 invariant; the resulting build is a NEW gated item | Program still closes on its own DoD (the decision record) |
| R8 | Insult/fairness regression from re-mixed decks | M2.4 re-runs H8 (≤3%, currently 1.48%) + empty-deck per matrix cell | Failing cell disqualified from the recommendation outright |
| R9 | Unpowered rebuilder read gets retro-narrated as success | DoD names served-mix only; ledger pre-declares the unmeasurable; M5.3 min-n and extend rule pre-stated | Anyone citing rebuilder like-rate as evidence ⇒ strike it |
| R10 | `outlook_direction` relight sneaks in as "part of the outlook work" | F6 named in the scope block as standing counter-evidence; any relight path requires F8 bring-up + grade + the M5.1 packet | — |

**Global rollback:** every mechanism has a 0 kill value writable deploy-free via the admin config
API; flags dark ⇒ byte-identical generation (golden-asserted). The M0.1 hydration fix is the only
deploy-coupled piece — rollback is revert-and-redeploy, which is why it rides a release.

## 7 · Resourcing

- **Agent sessions:** all [Ag] milestones; realistic peak parallelism 2 in W2–W3 (M2.1+M2.2 as
  one thread alongside M2.3; M4.1 develops in parallel but merges in sequence after the plumbing
  lands, so the three threads are never simultaneously in flight; +1 if WS1 runs) under the
  shared-file merge protocol. eng-backend profile for builds;
  an-user-data profile for M0.2/M2.4 readouts (needs the fresh mirror; read-only SELECT-copy
  protocol).
- **Operator:** three decision-shaped touchpoints — M3.2 (one sitting; ask-by end of W2), M5.1
  review + boundary call (OQ-1/OQ-3), M5.2 flip + ~30-min TestFlight checklist. Plus one one-line
  answer each for OQ-4 (end of W1) and OQ-5 (before M2.4). No operator coding.
- **Infrastructure:** prod mirror (read-only), admin config API (`CRON_SECRET` from
  `secrets.local.env`), F8 harness only if WS1 goes (registered scorer; harness unmodified).
- **CI:** every merge green (`pytest backend/tests`, `tsc --noEmit`, testid-lint);
  `FTF_SKIP_SIM_GATE=1` standing posture with evidence noted (D-056).
- **Deliberately not resourced:** WS1 by default (conditional), v2 inferred-coverage expansion
  beyond M4.1, any mobile client work, F8 nightly automation.

## 8 · Open Questions & Decisions Needed

| ID | Question | Blocks | Ask by | Owner | Default if unanswered |
|---|---|---|---|---|---|
| OQ-1 | **Flip timing:** wait for boundary = max(powered read, packet-ready), or trade the remaining read for an earlier fix? F3 is live harm; the freeze is live evidence value. | M5.2 date | M5.1 review | Operator | Wait for the boundary |
| OQ-2 | **Flip scoping:** `outlook_steer_scope` 1 (any-resolved; requires M4.1 + churn check) or 0 (declared-only; reaches ~1 user)? M2.4's label-source axis gives the measured difference. | M5.1 packet | M5.1 review | Operator, informed by M2.4 | Scope 1 only if M4.1 landed **and** the churn check passed; scope 0 otherwise |
| OQ-3 | **What batches at the boundary?** Q-034 (`overpay_adjusted`), Q-031 (`bakeoff_include_gen_v2` — also the H1-readout pollution fix), knockout residue, negmem's two flips. One clock restart either way. | M5.1 | M5.1 review | Operator (list) / Agent (packet) | Packet lists all; only this program's flips recommended by default |
| OQ-4 | **Does WS1 run?** F8 bring-up (+2–4 sessions) buys an offline verdict on `outlook_direction` redesign-vs-dark — and first-class offline grading for every future reranker. | WS1, M0.3 slot | End of W1 | Operator | No — leave dark; WS2 carries pick flow |
| OQ-5 | **`jets` treatment:** identical to rebuilder (default) or stronger? | M2.4 | Before M2.4 | Operator (one line) | Identical |
| OQ-6 | **Declaration coverage nudge:** 13 declarations total is why everything leans on inference — a Team Review prompt to declare outlook would improve every outlook feature. Own item? | Nothing here | — | Operator | Logged to NEXT.md as a candidate, not built |

**Docs/ledger owed at program close:** per-knob `docs/config-reference.md` rows (mandatory);
LLD generation-seams note (incl. `(outlook, source)` plumbing); DECISIONS.md entries (M3.2 ruling;
M2.4 lever choice; WS4 flip-scoping disposition); the stale `_try_sweeten` docstring fix;
CHANGELOG per merge; TEST_LEDGER per evidence run; HANDOFF at each stop; OPEN_QUESTIONS rows for
OQ-1/2/3/4 until closed; NEXT.md — this program **partially addresses** the review's H1 line: a
residual-H1 entry stays (non-rebuild give-far-first exposure at full strength + gen_v2 coverage,
the latter governed by OQ-3/Q-031).

---

## Reconciliation Log

**Document type:** Plan **Rounds run:** 4 (parallel drafts → candidate → cross-review → revision
→ re-review → final deltas → joint sign-off) **Converged:** yes — both lenses signed off in
round 4.

### Round 1 (independent drafts) — structural disagreements found

- **v1 coverage:** Risk lens wanted declared-only v1 (reaches ~1 user); execution lens wanted
  inferred-inclusive with composite wiring as a flip prerequisite. **Resolution:** levers built
  source-scoped with `outlook_steer_scope` defaulting declared-only; scope 1 offered only after
  M4.1 + churn check — both containment and coverage, chosen at packet time.
- **WS1/F8:** Execution lens scheduled an F8 replay of `outlook_direction`; risk lens noted F8
  has never run (no `data/eval_runs/`, self-consistency unproven) and designed it out.
  **Resolution:** WS1 conditional, off the critical path, bring-up cost named, default = leave
  dark.
- **DoD:** Execution lens closed the program on offline evidence + decision trail; risk lens
  wanted post-flip success bars. **Resolution:** program DoD = offline/dark deliverables;
  post-flip criteria kept separately as M5.3's pass bars.

### Round 2 (cross-review of the candidate)

- **A raised (blocking):** the declared-only fallback had no mechanism — declared and seeded
  outlook merge unmarked at `server.py:5854–5898`, so packet-time scoping was unbuildable as
  written. → Fixed: `(outlook, source)` plumbing + `outlook_steer_scope` knob added to the WS2
  design invariants, M2.1's build scope, and M2.4's axis mapping.
- **B raised (blocking), same defect independently** — convergent with A's; same fix.
- **B raised (blocking):** M2.2's "`_try_sweeten` is players-only — confirmed-no-edit" was
  factually wrong — the stale docstring says players-only, but the caller's C3 comment
  (`trade_optimizer.py:681–684`) states "the sweetener can itself be a pick" and
  `_owned_pick_assets`/`_inject_owned_picks` (`server.py:11286+`) inject PICK pseudo-assets into
  the rosters it draws from. **Orchestrator verified in source** (both agents had cited opposite
  lines; the file settles it for B). → Fixed: Lever B covers both sweetener seams; docstring fix
  owed in the same commit; round-2 A's contrary verification is noted as the error.
- **B raised (blocking):** the "build lands ~2 weeks before the earliest boundary" slack claim
  was arithmetically false on the plan's own dates and misled OQ-1. → Fixed: boundary redefined
  as max(powered read, packet-ready); M5.1 became a living draft decision-ready by W4; §5 states
  the honest early-window case. (A had flagged the same arithmetic as non-blocking.)
- **B raised (blocking):** the post-flip empty-deck abort (">5%") was already breached by the
  4.89–5.05% baseline — a trigger the untouched system violates is a coin-flip, not a safety
  net. → Fixed: aborts measure deltas vs the M0.2 frozen baseline (+1.0 pp), cut to the affected
  population (rebuild-side organic decks).
- **B raised (blocking):** M2.4's composite-inferred cells silently depended on M4.1 with no
  drawn edge. → Fixed: hard ordering added (M2.4 imports M4.1's merged path; degradation to
  declared/legacy-only stated).
- **B raised (blocking):** §8 retired the review's H1 line while treating only the
  outlook-conditioned slice (gen_v2 unreached; non-rebuild give-far-first partially treated). →
  Fixed: Lever A gains the outlook-independent `give_far_pick_penalty` knob; scope §2 and §8 now
  say "partially addresses" with a residual-H1 line kept in NEXT.md.
- **Non-blocking applied:** Lever B's hard-filter exemption recorded in the invariants; shared-file
  merge protocol; M5.3 min-n/extend/partial-success pre-registration; null-age structural test;
  M2.4 generator/arm-weighting statement; abort executor named; OQ ask-by column; session-total
  and diagram corrections.

### Round 3 (re-review of the revision)

- **A returned SIGN-OFF: yes** — verified the scope-knob mechanism, the A2 pin discipline, and
  the timeline arithmetic against source; non-blockings applied (A2's outlook-independence stated
  in M2.1 so a literal reading of the not_sure-inert invariant can't gate it; OQ-2 conjunct;
  session-total; match_ctx cost note).
- **B raised (blocking):** round-2 fix #6 broke fix #4 — the new outlook-independent A2 knob
  means one shippable configuration touches every viewer's organic decks, while the §1/R1/M5.3
  abort net watched only rebuild-side decks. → Fixed: the abort population follows the flipped
  knobs — A2 nonzero extends the empty-deck +1.0 pp abort to ALL viewer-outlook organic-deck
  populations, each vs its own M0.2 per-outlook frozen baseline. B's non-blockings also applied:
  9-cell A-split matrix with "A+B primary = A1+B"; bounded M5.3 extension ("unread — abort
  triggers remain standing"); same-lines (not same-files) merge hazard → M4.1 merges after the
  M2.1+M2.2 plumbing and the second merger re-runs the plumbing's unit assertions, not just the
  golden.

### Round 4 (final deltas)

- Both lenses returned **SIGN-OFF: yes — no blocking objections.** B verified the abort-scope fix
  end-to-end (§1 ↔ R1 ↔ M5.3, data side already frozen by M0.2) and that no fix introduced a new
  defect; A verified every delta against its mirrors and the timeline (M4.1 serialization
  coherent with the W2–W3 window; no milestone lost its done-bar). Last non-blockings applied:
  "develop in parallel, merge in sequence" clause in §4; A2 as the second recorded exemption in
  the WS2 invariants list; §7 peak-parallelism honesty; M2.4 estimate note; round-count
  bookkeeping.

### Unresolved disagreements

None — both lenses signed off. One judgment call worth the operator's eyes anyway: **how much
global (non-rebuild) far-first-give demotion to recommend** (`give_far_pick_penalty`'s value) is
left to M2.4's measured matrix rather than argued from the F3 cuts here — the fallback if the
matrix is ambiguous is to ship it at 0 (off) and let the rebuild-side fix stand alone.
