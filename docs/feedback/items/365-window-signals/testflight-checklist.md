# Manual TestFlight checklist — #365 net firsts, #371 playoff-odds window

**Owed by:** the operator. **This is the only runtime evidence mobile gets** (D-056 retired the
simulator entirely), and it is the **gate on graduating either flag** — do not flip either one in
production until §B and §C have been walked.

Both flags default **OFF** and are hot-reloadable: edit `config/features.json`, then
`POST /api/feature-flags/reload` with `CRON_SECRET`. No deploy, no client release.

- `trade.outlook_net_firsts` — the net-firsts term (#365)
- `trades.window_from_odds` — the playoff band driving the window (#371)

Every step below is on the **Team Review → beat 2 "Your window"** screen unless it says otherwise.

---

## A. Both flags OFF — prove nothing changed (do this FIRST)

The whole build rests on this being boring.

| # | Step | Expected |
|---|---|---|
| A1 | Open Team Review on the Lakeview league. Step to the window beat. | Identical to today: kicker "Your window · inferred from roster shape", the three share rows, the "Every input behind that call" card with three contribution rows and a total. |
| A2 | Read the last paragraph of the inputs card. | Ends "…or which picks you have already traded away, so a young team going all-in reads as rebuilding here." — the **original** sentence, word for word. |
| A3 | Confirm no First-round picks card is present anywhere on the beat. | Absent. |
| A4 | Confirm no sentence mentions playoff odds on this beat. | Absent. (The playoff **band** on beat 1 "standing" is unrelated and should be exactly as before.) |
| A5 | Open the trade deck and note the top 3 cards. Screenshot. | Baseline for A6. |
| A6 | Run a mock draft; note the first 5 CPU picks. | Baseline for C5. |

**If anything in A1–A4 differs from the shipped build, stop.** The flags are off; nothing should
have moved.

---

## B. `trade.outlook_net_firsts` ON — the #365 signal

Turn on `trade.outlook_net_firsts` only. Leave `trades.window_from_odds` off.

| # | Step | Expected |
|---|---|---|
| B1 | Reopen Team Review on a **Sleeper** league whose picks have synced (Lakeview). Window beat. | A new **First-round picks** card appears between the shares card and the arithmetic card, with three rows: You hold / Yours, traded away / Acquired from others. |
| B2 | Check the three counts against Sleeper's own traded-picks view for your team. | They match exactly. If "Yours, traded away" reads 0 while Sleeper shows firsts you have shipped, the ledger is not seeing them — **report before graduating**, this is the §7.1 risk. |
| B3 | Read the sentence under the counts. | One of: "Net +N: you are collecting firsts…" / "Net −N: you have spent firsts…" / "Net even…". It must agree in sign with the counts above it. |
| B4 | Look at the arithmetic card. | It now has a **fourth** contribution row, "Net firsts ±N of M × −0.1", with a signed number. Selling firsts ⇒ a **positive** contribution. |
| B5 | Add the four contribution rows by hand. | They sum to the "Total score" row (±0.01 rounding). If the total does not equal the visible rows, the card is hiding a term — **stop**. |
| B6 | Read the last paragraph. | Now reads "…roster age, pick capital, and the firsts you have moved. It still does not read your record or your starting lineup." The old "which picks you have already traded away" clause must be **gone**. |
| B7 | Open Team Review on **FFV3**. | Expected per §7.1: the card either shows "We have no draft-pick records for this league" or "No first-round pick in this league is recorded as having changed hands…". Either way **no fourth arithmetic row** appears and the total is unchanged from §A. Note which of the two sentences appears — that is the answer to the open question in the scope block. |
| B8 | Open Team Review on an **ESPN or MFL** league. | Same degraded card, no crash, review completes. |
| B9 | Compare your window verdict to §A. | For most teams it will be **unchanged** — the term is bounded at ±0.075 against a ±0.08 band. A one-bucket move is expected only at an extreme ledger. A two-bucket move is a bug. |
| B10 | Open the trade deck. Compare the top 3 cards to A5. | **Identical.** This is INV-365b: the engine does not read the ledger. If the deck moved, something is passing a ledger to `infer_team_outlook` outside the Team Review route — **stop and report**. |

---

## C. `trades.window_from_odds` ON — the #371 window

Turn on `trades.window_from_odds`. `outlook.odds` must already be on (it is).

| # | Step | Expected |
|---|---|---|
| C1 | **In preseason** (`completed_weeks == 0`, which is today), open Team Review on a Sleeper league. | Kicker still reads "inferred from roster shape". A new fine-print line appears: "Your playoff odds read *likely/toss-up/unlikely*, but nobody has played a game yet, so we are not letting a preseason simulation set your window." The verdict must **match §A's verdict** — preseason odds are refused. |
| C2 | Check that the band named in C1 matches the playoff band shown on beat 1 (standing). | Same word. If they disagree, two reads of the same simulation disagree — report. |
| C3 | Open Team Review on an **ESPN or MFL** league. | Fine print reads "We do not have playoff odds for this league, so this is roster shape only." Verdict from roster shape. **No blank window, no crash** — this is the reason odds do not replace the heuristic. |
| C4 | **Once week 1 has been played** (repeat this section then): Sleeper league, window beat. | Kicker becomes "Your window · from your playoff odds". A line reads "Your playoff odds read *X*, so that is the call. Roster shape alone said *Y*." The verdict must equal the band mapping: likely→Contender, toss-up→Not sure, unlikely→Rebuilder. |
| C5 | With C4 live, check beat 5 "Who to deal with". | The partners list is oriented against the **odds-driven** window (a contender is shown rebuilders). It is meant to follow the window; if it follows the roster verdict instead, report. |
| C6 | Run a mock draft; compare the first 5 CPU picks to A6. | **Identical.** #371 changes no engine value at all. |
| C7 | On any beat, tap through to the end and confirm the flow still completes and the outlook chip still writes. | Preferences saved; the entry card minimises as before. |

---

## D. Both ON — no interaction

| # | Step | Expected |
|---|---|---|
| D1 | Both flags on, Sleeper league, preseason. | The firsts card AND the preseason-refusal line both appear. The arithmetic card shows four rows and the roster verdict is what beat 2 acts on. |
| D2 | Both flags on, in-season (repeat after week 1). | Kicker says "from your playoff odds"; the arithmetic card still shows all four rows plus the line "Your playoff odds outrank this arithmetic while the season is running — the numbers above are what roster shape alone says." No contradiction on screen. |
| D3 | Turn both flags back off and reload flags. | The beat returns to exactly §A, including the original last paragraph. **The kill switch is the acceptance test** — verify it before leaving either flag on. |

---

## E. What to report back

1. **B2** — did the ledger counts match Sleeper for your own team?
2. **B7** — which of the two degraded sentences did FFV3 show? (This is the §7.1 open question and
   it decides whether #365 can actually fix the report that started it.)
3. **B9** — did your window verdict change in any league, and in which direction?
4. **B10 / C6** — did the deck or the mock draft move? (Expected: no. Any movement is a stop.)
5. **C4** — once games are played, does the odds-driven verdict read true to you?

Log the outcome in `living-memory/TEST_LEDGER.md` under the 2026-08-20 entry for this branch.
