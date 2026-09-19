# Feature Scope — Consensus card must not claim "balanced" below the app's own bar

**Date:** 2026-08-19
**Entry point:** direct ask, from the arm-B engine audit's *Bugs neither review found* table, row 2 — [docs/reviews/2026-08-19-armb-audit-consolidated.md](../../reviews/2026-08-19-armb-audit-consolidated.md) (on branch `docs/armb-audit-consolidated`, tip `950fc97`)
**Builder:** client-side session, branch `fix/balanced-claim-fairness-gate` off `origin/main` `50e0451`
**Operator sign-off on waivers:** not needed (no waivers — every section below is answered)

---

## 0. The defect, in one paragraph

`mobile/src/components/TradeCard.tsx` rendered *"This league-mate hasn't ranked players yet — this is
a balanced trade by consensus value."* gated on `data.basis === 'consensus'` **alone**, with no
fairness check of any kind. The identical string sat in `web/js/app.js` as the `consensus-tag`
`title` tooltip, equally ungated. The app's own bar for balanced is **0.75**
(`NORMAL_LOW` / `FAIRNESS_ON_THRESHOLD`), but the mobile fairness default flipped **OFF** on
2026-08-17, so the live generation floor is **0.50** and cards ship down to 0.501.

**Measured read-only against prod `deck_impressions` on 2026-08-19** (`SET TRANSACTION READ ONLY`,
SELECT only):

| Metric | Value |
|---|---|
| Consensus cards served (rows with `features_json`) | **7,293** |
| …carrying a non-NULL `fairness_score` | **7,293 (100%)** |
| …**below 0.75** — i.e. asserting "balanced" while not being balanced | **805 (11.04%)** |
| …below 0.50 (the generation floor) | 0 |
| Fairness distribution (consensus) | min **0.5010**, p10 **0.7302**, p25 0.7890, p50 **0.8590**, p90 0.9750, max 1.0000 |

This reproduces the audit's 805 / 7,282 (11.1%) exactly; the denominator moved 7,282 → 7,293 because
eleven more cards were served between the audit snapshot and this measurement.

**This is the product asserting something untrue by its own definition.** It is not a ranking-quality
question and not an engine question — no engine line is touched by this change.

**Operator amendment, 2026-08-19 — the claim is REMOVED, not replaced.** An earlier revision of this
fix put honest replacement copy below the bar (*"priced from public values, not an even split"*). The
operator struck it: *"We don't need to add the copy suggested.. We already have already features that
provide the value summary/snap assessment on trade valuation."* That is correct — the same card
renders `TradeValueBar` (`TradeCard.tsx`, gated on `hasValueVerdict`) with `giveValue`,
`receiveValue`, **`favors`** and **`gap`**, so direction *and* magnitude are already on screen from
the component its own comment calls the universal value verdict. Replacement prose would restate the
bar. So: **keep the explanation, drop the verdict, let the bar do the verdict's job.**

This also closes the directional-wording question the PRD's B2 line raised ("leans your way" /
"leans theirs"). With `favors`/`gap` already rendered it is duplication, and on web it would
additionally require plumbing `give_value`/`receive_value` into `web/js/app.js`, which carries
neither today. **Recorded so the next reader does not re-open it.**

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `deck_impressions.features_json` already freezes **both**
  `basis` and `fairness_score` at serve time (`backend/server.py:3861`, inside the `features` dict).
  That is precisely the join that measured the 805, and it is the same join that will verify the fix
  post-ship — *"what fraction of served consensus cards sit below 0.75"* is answerable today and will
  stay answerable, with no new event.
- No new event is specced, because **the copy change emits nothing**. The card already logs its
  impression; which of two strings it rendered is a pure function of a field already frozen on that
  row, so a new event would store a derivable value and add a second thing to keep in sync.
- **Not waived, answered:** if we later want to know whether the honest string changes swipe
  behaviour, the existing `deck_impressions` → `deck_outcomes` join already supports it — cut
  outcomes by `fairness_score < 0.75` on `basis='consensus'` rows. No instrumentation work needed.

## 2. Schema & flag scope

- New/changed tables or columns: **none.** No backend file is touched (`git status -- backend/` is
  empty on this branch); `docs/data-dictionary.md` needs no edit.
- New/changed feature flags: **none — deliberately.**

  > **Why this ships unflagged.** A flag's OFF state must be a safe fallback. Here the OFF state *is
  > the defect*: it re-ships a false statement to 11% of consensus cards. Flagging it would mean
  > building, and then maintaining, a switch whose only function is to turn the lie back on. Same
  > reasoning as [D-091](../../../living-memory/DECISIONS.md) ("its OFF state is the defect, so
  > shipping it off ships nothing"). The rollback lever is a revert of this commit.

- New env vars / `model_config` keys: **none.** The 0.75 bar is a **constant, not a knob** — see §6.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-consensus-balance-claim.js` — **36 assertions**,
      registered as `npm run test:consensus-balance-claim`. It **transpiles and RUNS** the real
      `consensusNote.ts` (the `check-fairness-default.js` idiom) rather than grepping JSX, so §1 of it
      is behavioural. It pins:
      1. the gate at the band edges — 0.75 → balanced; 0.7499, 0.7302 (prod p10), 0.55, 0.501 (prod
         min) → **truncated**;
      2. the **fail-safe direction** — `undefined` / `null` / `NaN` / `±Infinity` → the truncated
         string, **never** "balanced";
      3. that the function yields exactly **two** distinct strings, and only the at-or-above-bar one
         contains the word "balanced";
      4. that **every** state keeps the `hasn't ranked players yet` explanation (the fix removes the
         claim — it does not hide the line);
      5. that **no value prose is re-added** below the bar — the sub-threshold string must *end* at
         the true half, and `priced from public values` / `even split` / `leans` must appear nowhere;
      6. that **no** state names a winner (`fairness` is a symmetric min/max ratio);
      7. **threshold agreement** across all four spellings of 0.75 (§6);
      8. **cross-client byte parity, reconstructed rather than remembered** — §3 of the check pulls
         web's `prefix` literal and both tooltip templates out of `web/js/app.js`, expands them, and
         compares the results **byte for byte against the mobile module's own output**. It never
         compares either client to a string typed into the test, so it cannot pass vacuously when the
         wording changes, and it catches silent *drift* as well as a missing gate.
- [x] **Unit tests (backend pytest):** **none added, and none needed** — no backend file changed. The
      backend contract this fix depends on (`fairness_score` serialized on every card) is pre-existing
      and already exercised; see the code-walk below for where it is produced.
- [x] **Code-walk proof:** §7.
- [x] **Manual TestFlight checklist:** §8.
- `testID`s added: `trade-card.consensus-note`, `trade-card.consensus-note.body`. Neither is
  interactive (they wrap `View`/`Text`), but the checklist in §8 needs a stable anchor and the note
  previously had none. `mobile/scripts/testid-lint.sh` → **OK, exit 0**.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. `fairness_score` and `basis` were already both serialized by `trade_card_to_dict`; this change only *reads* fields that were already on the wire. |
| `living-memory/LLD.md` | **n/a** | No schema, route, or convention shift. The one new convention — "the balanced bar is a constant with four pinned spellings" — is a cross-client encoding, so it lands in `cross-client-invariants.md` (below), which is where the existing `NORMAL_LOW` scope block already said it must go. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change. One new pure leaf util under `mobile/src/utils/`, imported by one existing component. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **updated** | Rewrote the consensus row of **§ Trade-card copy strings (v2 engine UI)** and added a new **§ Consensus balance claim — the 0.75 bar (D-097)** carrying the two strings, the three non-negotiable rules (no replacement prose; the explanation is never dropped; fail-safe down), the prod measurement, and the four-spelling threshold table. **This was mandatory, not optional:** [docs/plans/trade-presentation-v2/scope.md:126](../trade-presentation-v2/scope.md) recorded in advance that `NORMAL_LOW` is "client-only presentation geometry… **If web or the extension ever renders this band, it becomes an invariant and must move.**" Web now renders it. It moved. |
| `docs/glossary.md` | **n/a** | No new domain term. "Fairness", "consensus basis" and "balanced" are all existing entries; this change narrows *when the app is allowed to say* balanced, not what it means. |
| ADR or `DECISIONS.md` entry | **updated** | **D-097** in `living-memory/DECISIONS.md` (id reserved by the operator; siblings hold D-095/D-096 — **not** computed as max+1). Not a full ADR: this is a single client-side copy gate, not an architecture choice. |

## 5. Ship gate declaration

- **CI green** — measured on this branch:

  | Gate | Result |
  |---|---|
  | `mobile/tests/check-*.js` (all) | **61 / 61 passed, 0 failed** (60 pre-existing + 1 new) |
  | `mobile/tests/check-consensus-balance-claim.js` | **36 / 36 passed** |
  | `mobile/scripts/testid-lint.sh` | **OK, exit 0** |
  | `npx tsc --noEmit` (mobile) | **1 error, pre-existing and environmental** — `ImportRankingsSheet.tsx(11,33): TS2307 Cannot find module 'expo-document-picker'`. `mobile/node_modules` is **empty in the main checkout**, so it was symlinked from `ftf-test-clone`, whose install predates the `expo-document-picker@~14.0.8` dependency. **Proven pre-existing, not assumed:** stashing this branch's `.tsx`/`package.json` edits and re-running produced byte-identical output. **My diff adds zero type errors.** |
  | `pytest backend/tests -q` | **3524 passed, 1 skipped, 0 failed** — run as insurance only; **no backend file is touched by this branch.** |
  | Maestro / simulator | **n/a — retired by D-056.** No flow authored, none run, no `screens/` capture taken. |
  | Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |

- **Sabotage test of the structural guard** (a check that passes with *and* without the fix is
  worthless). Four independent reverts, each applied, measured, and restored:

  | # | Sabotage | Result |
  |---|---|---|
  | S1 | Revert the gate — `balanced` forced `true`, i.e. always claim balanced | **RED, 14 failures**, exit 1 |
  | S2 | Flip the fail-safe — unknown fairness returns the balanced claim | **RED, 7 failures**, exit 1 |
  | S3a | Fix mobile, leave web stale — collapse the web ternary to the unconditional string | **RED, 5 failures**, exit 1 |
  | S3b | **The subtle one** — web keeps its gate but *drifts the wording* (`— no rankings on file.`) | **RED, 2 failures**, exit 1 |
  | S4 | Re-inline the literal into `TradeCard.tsx`'s JSX, bypassing `consensusNote` | **RED, 2 failures**, exit 1 |
  | S5 | Re-add value prose below the bar (the copy the operator struck) | **RED, 12 failures**, exit 1 |
  | — | Restore all | **GREEN, exit 0**, `git diff --stat` byte-identical to pre-sabotage |

  **S3a/S3b are the pair that matter most** for this fix: the standing warning is that *a string fixed
  in mobile and stale in web is worse than not fixing it*, because the two surfaces then disagree
  about the same card. S3b is the harder half — web still gates correctly, it just says something
  different — and it is caught only because the parity assertions compare the two clients **to each
  other** rather than to remembered wording. Those assertions are deliberately **not** wrapped in an
  `if (extraction succeeded)` guard: a failed extraction means web no longer has the shape the parity
  depends on, which is itself the divergence being guarded against, so it must fail rather than skip.

- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, entry `2026-08-19h`.
- **TestFlight verification:** checklist written in §8. **UNRUN** — it is the operator's to run, and
  it is the only runtime evidence this change gets under D-056.
- Express lane declared by the operator? **No.** Full gates.

## 6. The threshold: a constant, not a knob — and do the two existing ones agree?

**They agree.** Both are hardcoded module constants and both are `0.75`:

| Spelling | Location | Value | Role |
|---|---|---|---|
| `NORMAL_LOW` | `mobile/src/utils/tradePresentation.ts:147` | 0.75 | the league-normal band floor; its own docstring calls it "the balanced-mode generation threshold… what this league's own engine calls balanced" and cross-references the next row |
| `FAIRNESS_ON_THRESHOLD` | `mobile/src/api/tradePregen.ts:25` | 0.75 | the `fairness_threshold` actually sent to the generator when the user's fairness toggle is ON |
| `CONSENSUS_BALANCED_MIN` | `mobile/src/utils/consensusNote.ts:56` | 0.75 | **new — re-exports `NORMAL_LOW`, never redeclares it** |
| `FAIRNESS_BALANCED_MIN` | `web/js/app.js:1165` | 0.75 | the one unavoidable literal — web is vanilla JS and cannot import from TS |

They agreed **by coincidence of maintenance, not by construction**: nothing tested it, and the two
files knew about each other only through a prose comment. `check-consensus-balance-claim.js` §2 now
pins all four to each other, including parsing the literal back out of `web/js/app.js`.

**Constant, not a knob, for a specific reason.** The number that moves is the *generation floor* —
it is 0.50 today because the fairness default flipped off on 2026-08-17, and it will move again. The
number that must **not** move with it is the *definition of balanced*. Binding the copy to the
generation floor would make the sentence self-fulfilling: whatever the app happened to generate would
be called balanced, which is exactly the failure being fixed, one level of indirection up. So the
claim is pinned to the definition (0.75) and is deliberately independent of what the user is
currently generating at. This also matches what the two existing constants already do — neither is a
server flag or a `model_config` key — so no parallel mechanism is invented.

## 7. Code-walk proof

**Question 1 of the brief: does `fairness_score` actually reach both clients? YES — verified at the
producer, at both consumers, and against prod data. Not inferred from any other field.**

**Producer.** `backend/server.py:10637` `def trade_card_to_dict(card, players)` builds one dict that
carries **both** fields, unconditionally, ~3 lines apart:

- `:10657` → `"fairness_score":    card.fairness_score,`
- `:10660` → `"basis":             getattr(card, "basis", "divergence"),`

Neither is behind a flag, a `if` branch, or a conditional key-insert (contrast `retest` / `wildcard`
just below, which *are* conditionally inserted). Every deck-serving route funnels through this one
function — `:2863`, `:5408`, `:5449`, `:5499`, `:5594`, `:5635`, `:5683`, `:5797`, `:11185`,
`:11527`, `:14553`. **So `fairness_score` is on the wire wherever `basis` is, by construction: if a
card can say "consensus", it can say how fair it is.**

Corroborated against prod rather than asserted: **7,293 of 7,293** consensus `deck_impressions` rows
carry a non-NULL `fairness_score` in `features_json`. Zero nulls.

**Mobile consumer.** `mobile/src/api/trades.ts:84` maps it into the client type —
`: typeof raw?.fairness_score === 'number' ? raw.fairness_score` — landing on
`TradeCard.fairness` (`mobile/src/shared/types.ts:168`, `fairness: number; // 0–1 ratio`), two lines
away from where `:183` derives `basis`. The normalizer keeps a defensive `undefined` tail for
cached/legacy snapshots, which is **why the third string exists**: the type says `number`, runtime
does not guarantee it, and the gate must not lie when it is absent.

**Web consumer.** `web/js/app.js` already read `card.fairness_score` **at the same call site**, ~10
lines below the consensus tag, to draw the fairness meter. The value was literally already in scope
where the false claim was being rendered.

**Conclusion: no backend change is required, and none was made.** The field was there the whole time;
the clients simply never consulted it before making the claim.

**The gate itself.**

- `mobile/src/utils/consensusNote.ts:56` — `export const CONSENSUS_BALANCED_MIN = NORMAL_LOW;`
- `export function consensusNote(fairness: number | undefined | null)` computes `balanced` as a
  **single conjunct** — `typeof fairness === 'number' && Number.isFinite(fairness) && fairness >=
  CONSENSUS_BALANCED_MIN` — which makes the fail-safe **structural rather than merely tested**: an
  absent or non-finite score fails the conjunct, so the claim cannot be minted at all.
  **`Number.isFinite`, not `isFinite`**: the latter coerces, so `isFinite('0.9')` is `true` and a
  stringified payload would reach the comparison and compare as a string. Pinned by the
  `NaN`/`±Infinity` assertions and by an explicit source assertion.
- `>=`, so exactly 0.75 is balanced — the bar is inclusive, matching `fairnessBand`'s
  `fairness >= NORMAL_LOW` at `tradePresentation.ts:176`.
- The balanced string is byte-identical to the pre-fix copy; the other is the prefix plus a period,
  and nothing else.

**The mobile render site.** `mobile/src/components/TradeCard.tsx`:

- `:21` — `import { consensusNote } from '../utils/consensusNote';`
- `:166` — `const isConsensus = data.basis === 'consensus';` *(unchanged)*
- `:170` — `const note = consensusNote(data.fairness);` — computed unconditionally at component top
  (a pure call on a number, no hook, no branch, so it cannot violate hook ordering), read only inside
  the `isConsensus` block.
- `:463-468` — the block now renders `{note.label}` and `{note.body}`. **No string literal remains in
  the JSX**, which is what makes S4 catchable.

**The web render site.** `web/js/app.js:3617-3629` — `card.basis === 'consensus'` still decides
*whether* the tag renders (unchanged); an IIFE then picks the tooltip from `card.fairness_score`
(`:3619`) against `FAIRNESS_BALANCED_MIN` (`:3624`), with the same three-state shape and the same
same two-string shape and the same single-conjunct `balanced` computation. Two hardening details: the
tooltip is now passed through `escapeHtml` (it was a fixed literal before and is an interpolated
string now, so escaping is required rather than optional), and the guard is `Number.isFinite`,
**not** the coercing global `isFinite` — the global returns `true` for a stringified `"0.9"`, which
would then compare as a coerced string and claim balanced. Both clients use the non-coercing form and
the structural check pins both.

**What is provably unchanged.** `isConsensus` still gates *whether* the note appears, so no card
gains or loses the note; only its second clause moves. For the **6,488 of 7,293 (88.96%)** prod cards
at or above 0.75, the rendered bytes are **identical to before this change**.

## 8. Manual TestFlight checklist (operator)

This is the **only** runtime evidence this change gets under D-056. Setup matters: the sub-0.75 band
only appears when the fairness toggle is **OFF**, which is the default — so do **not** turn it on.

| # | Step | Expected |
|---|---|---|
| 1 | Fresh install / launch, open a league where at least one league-mate has **not** ranked players (consensus cards need an unranked partner). Leave the Find-a-Trade fairness toggle at its default (**OFF** — the wide 0.50 net). | Deck generates. |
| 2 | Swipe the deck and find a card showing the **"Fair-value idea"** label. | The label still reads exactly `Fair-value idea` — unchanged in every state. |
| 3 | On that card, read the sub-line **and** the `TradeValueBar` underneath it together. | Sub-line **always** begins `This league-mate hasn't ranked players yet` — the explanation half is never missing, in any state. |
| 4 | Find a consensus card whose two sides are visibly **close** in the pick-denominated value bar (`gap` small / `favors: even`). | Sub-line ends `— this is a balanced trade by consensus value.` (the pre-existing sentence). |
| 5 | **The one that matters.** Find a consensus card whose value bar shows a visibly **lopsided** package — one side clearly heavier. Expect roughly **1 in 9** consensus cards (11.0% measured). | Sub-line reads exactly `This league-mate hasn't ranked players yet.` and **stops there** — no dash, no clause after it. **The word "balanced" must not appear anywhere on this card.** |
| 6 | On that same lopsided card, check that the value story is still being told — by the **bar**, not by prose. | `TradeValueBar` shows the lean and the gap as usual. The sub-line says nothing about value: no "even split", no "leans your way", no "priced from public values". That is the intended division of labour — the bar is the verdict, the sentence is the basis. |
| 7 | Turn the fairness toggle **ON** (0.75), regenerate, and swipe the whole deck. | **Every** consensus card shows the full `— this is a balanced trade by consensus value.` sentence; **none** shows the truncated form. At a 0.75 floor nothing below the bar is generated, so a truncated card here means the generator is serving below its own stated threshold (a different bug — the audit's *Bugs neither review found* row 5) and should be reported with the card. |
| 8 | Kill the app, relaunch, and reopen the same deck from cache. | Cards render the same sentence they rendered before the relaunch — no card silently regresses to the "balanced" claim on a cache-rebuilt path. |
| 9 | Open the same league in the **web** app, find a consensus card, and hover the `Fair-value idea` tag. | The tooltip text matches the mobile sub-line **character for character** for the same card. This is the cross-client half of the fix and is invisible to every automated gate except the string comparison in the structural check. |

**Regression watch:** any consensus card where the sub-line is missing entirely, or where the
`Fair-value idea` label renders without a body, is a failure — the fix truncates the sentence and must
never *hide* the line.

## 9. Adjacent, deliberately NOT fixed here

`mobile/src/utils/tradePresentation.ts:260-265`, `counterpartyStatement()`, asserts partner interest
**unconditionally**:

> `Based on their roster needs and recent activity, ${who} is likely to be interested in this deal.`

There is no signal behind that sentence for the `likesYou !== true` branch — the function's own
docstring forbids it from reading `match_context.opponent_surplus`, `partner_fit`, or any value field
(deliberately, as a privacy guard), which means it makes a confidence claim from strictly nothing.
**Structurally the same defect class as the one fixed here: an unconditional assertion about a
counterparty.**

It is **dark** — `trades.presentation_v2` is `false` in `config/features.json` (operator-disabled
2026-08-19), so nothing renders it — and it belongs to a surface under separate review. **Left
untouched on purpose.** Recorded here and in D-097 so it is not lost when that flag is next
considered for turn-on; **that surface must not ship with this string as-is.**
