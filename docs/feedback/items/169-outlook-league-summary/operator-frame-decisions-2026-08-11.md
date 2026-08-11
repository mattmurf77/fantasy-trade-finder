# #169 — Operator frame decisions, 2026-08-11

> **Source:** operator selections given verbatim in a `/feedback` session on
> 2026-08-11, recorded here because the mockups they refer to
> (`mockups/outlook-odds/`) are owned by a different session's branch
> (`outlook-league-summary-v2`) and the decisions would otherwise live only in
> chat. **Recorded, not executed** — no code was written from this.
>
> Companions: [`odds-surface-audit.md`](odds-surface-audit.md) ·
> [`status-outlook-v2-build-2026-08-10.md`](status-outlook-v2-build-2026-08-10.md)

---

## Table of Contents

- [1. The decisions, verbatim](#1-the-decisions-verbatim)
- [2. League Summary — Outlook v2](#2-league-summary--outlook-v2)
- [3. Trade Outlook Card v2](#3-trade-outlook-card-v2)
- [4. Consistency check — the selections agree with each other](#4-consistency-check--the-selections-agree-with-each-other)
- [5. What these decisions cost](#5-what-these-decisions-cost)
- [6. Open questions the selections did NOT resolve](#6-open-questions-the-selections-did-not-resolve)
- [7. Second pass — operator answers, 2026-08-11](#7-second-pass--operator-answers-2026-08-11)
- [8. Third pass — operator answers, 2026-08-11 (build session)](#8-third-pass--operator-answers-2026-08-11-build-session)

---

## 1. The decisions, verbatim

> **For: League Summary — Outlook v2**
> B, C1, E are my choices.
>
> **For: Trade Outlook Card v2:**
> C & D, but the Accept/Decline buttons should be right underneath the player
> tile section. And don't remove the value bar.. Keep it as is and above the
> playoff outlook

---

## 2. League Summary — Outlook v2

Frames from `mockups/outlook-odds/league-summary-outlook-v2.html`.

| Frame | What it is | Selected | Build state |
|---|---|---|---|
| A | As built today | — | n/a (baseline) |
| **B** | Weeks 0–5 — bands only | **YES** | **already built** |
| **C1** | Week 6+ — bands persist | **YES** | **already built** (C1 is the built default) |
| C2 | Week 6+ — 5%-rounded percentage | **no** | built as an off-switch, not the default |
| D | IDP league — coverage caption | **not named** | **already built** — see §6 Q1 |
| **E** | Collapsed "your outlook" strip | **YES** | **NOT built** — this is new work |

**Net:** B and C1 confirm what the 2026-08-10 build already shipped dark. **E is
the only new League-Summary work this decision creates.** D is built but was not
named — that is an open question, not a rejection (§6 Q1).

---

## 3. Trade Outlook Card v2

Frames from `mockups/outlook-odds/outlook-card-v2.html`. **Note the frame
letters mean different things in the two files** — league-summary D is the IDP
caption; card D is the week 6+ band variant. The selections were read against
the correct file.

| Frame | What it is | Selected |
|---|---|---|
| A | July card — what died | — (baseline) |
| B | Trade summary, week 6+ (percentage framing) | **no** |
| **C** | Weeks 0–5 — no odds block at all | **YES** (was the mock's own recommendation) |
| ~~D~~ | Week 6+ band variant | **DROPPED** on the second pass — see §7 |

> **Superseded:** the first pass selected C **and** D. On being shown D's cost
> (a with-trade re-sim, §5), the operator revised to **C only**. §7 is
> authoritative.

### Operator modifications to the selected frames

1. **Accept/Decline buttons move directly beneath the player tile section.**
   The mock places its action row at the card's bottom edge.
2. **The value bar stays, unchanged, above the playoff outlook.** The mock
   frames carry only a *text* value verdict ("Even by value — within a Mid
   3rd"); the operator is asking for the real value bar to be retained in
   position. See §6 Q3 for the two ambiguities this raises.

---

## 4. Consistency check — the selections agree with each other

Card frame D is explicitly conditional: its own header reads *"if C2 is
declined"*, and its note says it only makes sense **if bands are also the
league-summary presentation**. The operator chose **C1** (bands persist) over
C2 (percentages) on the league summary. Card D is therefore the correct
dependent choice, and the two selections are coherent rather than coincidental.

This also locks a cross-client invariant: band names, thresholds, and chip
colors must ship in [`docs/cross-client-invariants.md`](../../../cross-client-invariants.md)
**the day either shape ships** — the card and the league summary can no longer
diverge on band grammar.

---

## 5. What these decisions cost

- **Card D is not free.** The mock's own cost note: the week 6+ trade summary
  requires a **with-trade re-sim** (roster-swapped `run_outlook`) — new backend
  work. Bounded at one pair per opened summary; **per-deck-card is explicitly
  rejected** as unbounded. Card C (weeks 0–5) costs nothing, because absence is
  the design.
- **Card D is a backend + API-contract change**, so per `CLAUDE.md`
  §Conventions it is on the bright line and is not express-eligible.
- **League Summary E** is client-only as drawn, but has not been designed
  against the built `SeasonOutlookSection` — it was drawn against the mock.
- `outlook.odds` is **present in `config/features.json` and set `false`**
  (verified on `origin/main`). `living-memory/NEXT.md` item 5 claims the flag is
  in neither `LAUNCHED_FLAG_DEFAULTS` nor `config/features.json` — **that is
  stale**; the endpoint is reachable, just flag-dark.

---

## 6. Open questions the selections did NOT resolve

1. **League-summary frame D (IDP coverage caption) — keep or remove?** It is
   already built (`coverageCaption(meta)`, testID
   `league-summary.odds.coverage-note`). It is an additive edge-case caption
   rather than an alternative to B/C1/E, so "not named" most likely means "not
   considered" rather than "rejected" — but shipping E while silently keeping D
   should be an explicit choice.
2. **Button vocabulary.** The operator said "Accept/Decline". The mock's action
   row reads **"Pass / Send offer"**, and the shipped deck uses
   `trades.pass-btn` / `trades.like-btn`. Three vocabularies for one control.
   Pick one before build; it is a cross-client invariant candidate.
3. **Which value bar, and in what state?** (a) The mock frames show a text
   verdict, not the `TradeValueBar` component — confirm the ask is the real
   component. (b) "Keep it as is" collides with the pending #243 density
   variant (`mockups/polish-lab-2026-08/tradevaluebar-density.html`, 248pt →
   192pt, which also fixes a `fontSize:9` violation). Confirm whether "as is"
   means today's 248pt bar or the post-#243 bar.
4. **Ownership.** Branch `outlook-league-summary-v2` (a different session) holds
   the B+C1+D build. These decisions were captured in a session running the
   #297–#302 batch. Whoever builds E and the card changes should start from
   that branch, not from this record.

---

## 7. Second pass — operator answers, 2026-08-11

Verbatim: *"1. Pass / Like  2. I mean the bar from #243.  3. Let's go with C
then."* Answering §6 Q2, Q3, and the §5 cost note in order.

| # | Question | Answer | Consequence |
|---|---|---|---|
| Q2 | Button vocabulary | **"Pass / Like"** | Neither the mock's "Pass / Send offer" nor a new "Accept/Decline". Matches the shipped deck's existing `trades.pass-btn` / `trades.like-btn` testIDs — so this is the *no-change* answer for the deck and a rename for the mock. Settle it in [`docs/cross-client-invariants.md`](../../../cross-client-invariants.md). |
| Q3 | Which value bar | **The #243 bar** — the density variant from `mockups/polish-lab-2026-08/tradevaluebar-density.html` (248pt → 192pt, fixes the `fontSize:9` violation) | Still above the playoff outlook; still directly retained, not replaced by the text verdict. **See the correction below — this is a no-work answer, not a dependency.** |

> **CORRECTION (2026-08-11, same session).** I first recorded #243's density
> work as a *dependency* of the card change and said so in the handoff to the
> build session. **That was wrong: it already shipped.** Commit `4795a21`
> ("#243: TradeValueBar density (V1) — winner line steps to title, verdict
> behind 'Why?' disclosure, padding trim, 11px floor fix") is on `origin/main`,
> and `whyToggle` is live at `mobile/src/components/TradeValueBar.tsx:175`.
> "The bar from #243" is therefore **the bar as it exists on `origin/main`
> today** — the card change simply keeps the existing component in place. No
> sequencing constraint, no prerequisite work.
>
> Related drift: `docs/feedback/items/243-scroll-audit/status.md` still reads
> **"in-progress · branch `teardown-remediation`"** while four #243 commits
> (`4795a21`, `78d4bb3`, `d89a4ad`, `b2bd078`) sit on `origin/main`. Same
> pattern as the `NEXT.md` / `outlook.odds` drift in §5.
| §5 | Card D's re-sim cost | **Drop D — "let's go with C then"** | **No backend work.** No roster-swapped `run_outlook`, no API-contract change, no new flag surface. This drops the card off the CLAUDE.md bright line entirely: the remaining card change is client-only. |

### Standing from the first pass (unchanged)

- Accept/Decline → **Pass / Like** buttons sit **directly beneath the player
  tile section**, not at the card's bottom edge.
- The value bar (now: the #243 bar) sits **above the playoff outlook**.

### What dropping D means for week 6+ — ASSUMPTION, needs confirmation

Frame C is defined as the **weeks 0–5** state, and its rationale ends *"the
outlook block simply appears at week 6+ (frame B)."* With **B rejected and D
dropped, no frame covers week 6+.** The reading carried into the handoff is:

> **The trade card shows no odds block at all, in any week, for now.** Week 6+
> is deferred, not designed. Absence is the design year-round.

This is coherent — it is the simplest possible card and costs nothing — but it
was *inferred*, not stated. If the intent was instead "C now, revisit week 6+
later", the difference is only in what gets written down, not in what ships
today. **Confirm before the card work is considered complete.**

### Still open after this pass

- **§6 Q1 — league-summary frame D (IDP coverage caption), keep or remove?**
  Asked in the first pass, not answered in the second. It is already built and
  shipping dark. Default assumption: **keep** (it is additive and orthogonal to
  B/C1/E), but it has never been an explicit choice. **Resolved in §8.**

---

## 8. Third pass — operator answers, 2026-08-11 (build session)

Asked at the start of the #169 build session, resolving the two questions §7
left open. Both were put to the operator as explicit choices.

| # | Question | Answer | Consequence |
|---|---|---|---|
| §7 assumption | Card week 6+ coverage (no frame covers it with B rejected, D dropped) | **"C for now"** | The assumption is confirmed: **the trade card shows no odds block at all, in any week, for now.** Week 6+ is deferred, not designed — revisit as its own item when wanted. The card change stays client-only. |
| §6 Q1 | League-summary frame D (IDP coverage caption) — keep or remove? | **Keep** | The built `coverageCaption(meta)` / `league-summary.odds.coverage-note` ships as-is. No work. |

**No open questions remain.** The full decided set: League Summary = B + C1 +
D + E (E is the only new work); Trade card = C in all weeks, Pass / Like
buttons directly beneath the player tile section, the #243 density value bar
above the playoff outlook; C2 rejected; card B rejected; card D dropped.

**Build-session note on ownership (supersedes §6 Q4):** branch
`outlook-league-summary-v2` no longer exists — its content (tip `36618be`)
was verified merged into `origin/main` by content (`SeasonOutlookSection`,
coverage caption, and the platform fix all present on `origin/main`;
`git merge-base --is-ancestor 36618be origin/main` = yes). New work branches
from `origin/main` as normal.
