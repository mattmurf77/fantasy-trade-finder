# Manual TestFlight checklist — composite window model (#372)

Under D-056 this is the **only runtime evidence** the mobile side of #372 gets,
so it is written to catch a regression rather than to confirm a screen exists.
Log the outcome in `living-memory/TEST_LEDGER.md`.

**Prerequisites**

- A TestFlight build containing this branch's `TeamReviewScreen.tsx` and
  `api/teamReview.ts`. Build 122 predates all of it — with the flag off the
  window beat is byte-identical there, which is the point, but nothing new
  renders until a fresh build.
- Backend on `main` with this branch merged.
- Flag control: `PUT /api/admin/config/...` is not needed; flags flip via
  `config/features.json` + `POST /api/feature-flags/reload` (`CRON_SECRET` from
  `secrets.local.env`). **No redeploy and no new build is needed to flip
  between any of the states below** — that is the rollback lever being tested.

**The league that matters:** `Fantasy Football Version 3` — this is the league
in all three reports (#365, #371, #372). It is 12-team Sleeper, currently
`pre_draft`, so `completed_weeks == 0` throughout.

---

## A. Baseline — both new flags OFF (`trade.outlook_composite` false)

1. **Open Trades → Team Review → the Window beat on FFV3.**
   *Expect:* the headline reads **Rebuilder**. The kicker reads *"Your window ·
   inferred from roster shape"*. The "Every input behind that call" card shows
   exactly three rows — veteran share, young share, pick capital — plus Total
   score, and the closing line reads *"That is the whole model — roster age and
   pick capital…"*.
   *Fail if:* a "Your starting lineup" or "Playoff likelihood" card appears, or
   the headline is anything but Rebuilder. Either means the flag leaked.

2. **Note the Total score.** It should be a large negative number (≈ −0.49).
   Write it down; step 4 compares against it.

## B. The composite ON (`trade.outlook_composite` true, `trades.window_from_odds` false)

3. **Flip the flag, `POST /api/feature-flags/reload`, pull-to-refresh Team
   Review (do not reinstall).**
   *Expect:* the beat re-renders **without a new build**.

4. **The verdict flips.** Headline reads **Contender**. Kicker reads *"Your
   window · from your starters, your picks and your age"*. Total score is
   positive (≈ +0.20).
   *Fail if:* still Rebuilder. That is the exact defect #372 reports and this
   build's whole purpose.

5. **A "Your starting lineup" card is present**, above the arithmetic card. It
   shows a starter value, a share of the league's starter value (≈ 15 %), and
   copy saying the lineup is **above** an average lineup in this league. It
   also states *"Offensive starters only… kicker and IDP slots carry no
   value"* — FFV3 starts K, DL, LB, DB and IDP_FLEX, so this sentence is not
   decoration.
   *Fail if:* the share row reads 0 %, or the copy says "below average", or the
   IDP sentence is missing.

6. **A "Playoff likelihood" card is present and REFUSES the signal.** With
   `trades.window_from_odds` off it must read *"Playoff odds are switched off
   for this league, so we did not ask for them."*
   *Fail if:* it shows a band, a percentage, or claims the odds counted. A
   **bare playoff percentage anywhere on this screen is a cross-client
   invariant violation** — the band is the only permitted visible rendering.

7. **The arithmetic itemises what it scored, and only that.** The inputs card
   now shows **four** rows plus Total: veteran share × **0.4**, young share ×
   **−0.4**, pick capital × −2, and *"Starters +0.50 vs the league × 0.6"*.
   There is **no** playoff row.
   *Fail if:* the veteran/young rows still read × 1 (the card is describing a
   model it did not run — the D-101 defect), or a playoff row appears, or the
   four contributions do not visibly sum to the Total.

8. **The closing sentence no longer lies.** It must mention your starting
   lineup and say age "counts for less than the rest". The old sentence claimed
   the model *"does not read your… starting lineup"*.

## C. Both flags ON (`trade.outlook_composite` + `trades.window_from_odds`)

9. **Flip `trades.window_from_odds` on, reload, refresh.**
   *Expect:* FFV3 is preseason, so the Playoff likelihood card now reads
   *"Nobody has played a game yet, so we are not letting a preseason simulation
   weigh in on your window. This fills in from week 1."* The headline is still
   **Contender** and the arithmetic still has no playoff row.
   *Fail if:* the headline changes, or the old #371 line *"…so we are not
   letting a preseason simulation set your window. Roster shape below."*
   appears **as well** — that sentence is now suppressed under the composite so
   the same fact is stated once, not twice.

10. **The precedence rule, in season (deferred to week 1+, or test on a league
    with games played).** Once `completed_weeks > 0` on a Sleeper league, with
    both flags on: the Playoff likelihood card shows a **band** (Likely /
    Tossup / Unlikely), the arithmetic gains a *"Playoff odds ±N vs even ×
    0.4"* row, and the headline is whatever the composite scores.
    *Fail if:* the headline is simply the band's implied window (Likely →
    Contender) while the arithmetic says otherwise — that means the band both
    scored **and** overwrote, counting one simulation twice.

## D. Degradation and rollback

11. **A non-Sleeper league (ESPN or MFL), composite ON.**
    *Expect:* the "Your starting lineup" card appears and says *"We do not know
    this league's starting-lineup template… this signal is not counted and the
    reading below falls back to roster age and picks."* The arithmetic card
    shows the **legacy** weights (× 1, not × 0.4) and no Starters row.
    *Fail if:* the card is absent (the user is left wondering), or the share
    reads 0 % as though measured, or the weights read × 0.4 while no starter
    row is present — a lighter age model with nothing put in its place is not
    what was asked for.

12. **Rollback.** Flip `trade.outlook_composite` back to false, reload, refresh.
    *Expect:* the screen returns exactly to step 1 — Rebuilder, three rows, no
    new cards — with **no app update and no redeploy**.
    *Fail if:* anything renders `undefined`, a card lingers, or the app has to
    be reinstalled.

13. **The partners beat agrees with the window beat.** With the composite ON,
    check that the league-mates listed under "pointed the other way" are
    consistent with the composite's own verdicts (from `scope.md` §7.1:
    `PaulSm3nis`, `JohnStanfield`, `jonbonjourvi` and `Bcork` are the
    composite's rebuilders; `dondags20` is **not** one any more).
    *Fail if:* a member appears as an opposed-window partner whose own composite
    verdict is not opposed — that would mean the caller and the members are
    being scored by two different models in one payload.
