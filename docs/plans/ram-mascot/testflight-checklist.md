# TestFlight checklist — Fleeced the ram (`onboarding.mascot_ram`)

**Under [D-056](../../../living-memory/DECISIONS.md) this is the only runtime evidence this change can get.** The
structural guard proves shape; `tsc` proves types. Neither can see a sprite render at 44 pt on a real screen.

**Prerequisites** — all three, or the checklist tests nothing:
1. A build containing `mobile/assets/mascot/ram/` is installed (the sprites are bundled; there is no OTA channel).
2. `mascot_ram_rollout` is `running` ([experiment.md](experiment.md) §4).
3. The device is in `config/tester_allowlist.json`.

Log the outcome in `living-memory/TEST_LEDGER.md` either way.

---

## A. Flag OFF is byte-identical (do this FIRST, before the experiment is launched)

| # | Step | Expected |
|---|---|---|
| A1 | Fresh install, tour runs (`Show me around` on the calculator) | **The Analyst** — the bespectacled football, exactly as today |
| A2 | Team Review entry card on TradesHome | The Analyst at small size |
| A3 | Open Team Review, step through its beats | The Analyst at every beat |

**If any of A1–A3 shows a ram, stop.** The flag is not gating and nothing below is worth running.

## B. Flag ON — the six poses at 96 pt

Launch the experiment, then force a flag refetch (cold boot, or background ≥30 min and return).

| # | Step | Expected |
|---|---|---|
| B1 | Calculator → `Show me around` | The **ram** in the bubble, not the Analyst |
| B2 | Step the whole tour to the end | All six poses appear. Each is recognisably a different expression — **the one to watch is `computing` vs `thinking`**, which must not read as the same face |
| B3 | A spotlight beat pointing at something on the **right** | Ram faces **right**, toward its target |
| B4 | A spotlight beat pointing at something on the **left** | Ram faces **left** — the mirrored `point`. A ram facing away from its own spotlight is the failure |
| B5 | The bubble header | Still reads **"The Analyst"**. Expected: the copy split is deferred (D-155). Not a bug |
| B6 | The ram against the bubble | No dark box or square matte behind it; no pink halo bleeding onto the card |
| B7 | Ram vs the bubble's bottom edge | Sits on the same bottom line as the bubble. It is **taller** than the Analyst was — expected and sanctioned |

## C. Flag ON — small sizes, where this is most likely to disappoint

| # | Step | Expected |
|---|---|---|
| C1 | Team Review entry card on TradesHome (38 pt) | Legibly the ram: brown head, ice horns, pink eyes. Recognition only — expression is not expected to read at this size |
| C2 | Team Review beats (44 pt) | Ram renders cleanly, no clipping, no stretched aspect |
| C3 | **Look hard at C2 across beats** | **Known accepted cost (D-156):** the five 44 pt poses will look broadly alike. Painted detail does not survive 44 pt; the flat set was the alternative and was declined. Log it as *observed*, not as a bug — unless it is worse than "similar", e.g. actually unreadable or visibly the wrong pose |

## D. Non-regression around the swap

| # | Step | Expected |
|---|---|---|
| D1 | Complete a full tour with the ram | Every beat advances as before. No beat stalls, no missing target |
| D2 | Skip a step (✕), then re-enter via `Show me around` | Behaves exactly as on the Analyst build |
| D3 | Dark and light ambient conditions / auto-brightness | Ram stays legible; horns do not blow out |
| D4 | VoiceOver on, run the tour | Bubble copy is announced as before. The avatar itself announces **nothing** — it is decorative in both mascots |
| D5 | Largest Dynamic Type setting | Bubble text scales; the avatar does not distort or overlap the text |
| D6 | Backgrounded mid-tour, return | Tour resumes on the same beat with the same pose |

## E. Rollback

| # | Step | Expected |
|---|---|---|
| E1 | Transition `mascot_ram_rollout` → `stopped` | — |
| E2 | Cold boot the app | **The Analyst returns.** No deploy, no rebuild, no reinstall |

---

## Reporting

For each failure record: step id, pose, surface, size, and a screenshot. The two failures that would block graduation
are **B4** (direction wrong or unreadable when mirrored) and **A1–A3** (flag not gating). Everything in C3 is expected
and pre-accepted; report it as an observation.
