# Consolidated operator TestFlight checklist — 2026-08-24 feedback wave

> The batch's ONLY runtime evidence (D-056). Run against the first build ≥ **1.16.4**
> containing merge `c8b0e224`+. Backend halves (C, F) go live on Render deploy and can be
> partially exercised on any installed build. Log outcomes back to
> `living-memory/TEST_LEDGER.md`. Full step detail + preconditions live in each group's
> PRD §checklist — this file is the run order and the pass bars.

## Run order (cheapest re-arm last)

### 1 — Group C: lineup impact (#395/#396) — no re-arm needed, backend live on deploy
1. FFV3 (superflex): calculator or deck card trading **Jayden Daniels away for picks only**
   → lineup impact shows **exactly one row: `SF: Daniels → <backup>`** — no phantom `QB:` row.
2. Any 2-WR+flex league: no lineup row ever reads "WR3" as a slot; a flex-started WR's slot
   says **FLEX**; rank chips read **"WR #3"** style (space + #) on build ≥ 1.16.4.
3. If an ESPN or MFL league is linked: open one trade's lineup impact — slots come from the
   new platform template (QB/2RB/2WR/TE/2FLEX +SF where sf_tep); no "WR3".

### 2 — Group A: outlook & filters row (#376/#379/#394) — build ≥ 1.16.4
Full 7 steps: [376-finder-filters-regression/prd.md](../376-finder-filters-regression/prd.md) §checklist.
Pass bars: the minimized **"Outlook & filters"** row renders on TradesHome below the receipt
position (outlook declared AND undeclared states); **Change opens the full DNA sheet**
(fairness, lanes, positions, targeting); apply → row reflects it; the top utility-row
**Filters icon is gone**; control-variant check per the PRD's step 6 (stage account or
jonbonjourvi; the chip mode bar + the same row = correct).

### 3 — Group D: analyst pop-up over playoff odds (#386/#391) — needs beat n5 armed
Precondition + feasibility probe: [386-analyst-playoff-odds/prd.md](../386-analyst-playoff-odds/prd.md) §5c —
n5 may be **receipt-retired** on your install (one `league_filter_applied` ever). Probe first;
fallback = fresh Sleeper account; if neither works, record "degrades to code-walk" in the ledger.
Key step is a **cold start**: expand playoff projection → force-quit → relaunch → League tab →
bubble ring sits ON the position pills, no hole punched through the expanded odds section;
collapse/re-expand while the tour is up → ring follows.

### 4 — Group F: QuickSet HOLD (#346/#381) — backend live on deploy; client half ≥ 1.16.4
7 steps: [prd.md](prd.md) §checklist (≥2 players placed on the rung, per O-4).
The Nabers walk: set a player at "4+ 1sts" → save the tier having selected 3 OTHER players →
proceed to "3+ 1sts" → **the player still shows at 4+ 1sts and is selectable** — not FA, not
vanished. Then prove explicit demotion still works (FA rung / revisit-deselect).
Note: players 1100-pinned by the OLD rule stay where they are — re-place them manually.

### 5 — Group B: swipe-tour placement (#397/#398) — needs first-run state (heaviest re-arm, run last)
Re-arm: [397-swipe-tour-placement/prd.md](../397-swipe-tour-placement/prd.md) §6c step 1 —
guided-tour toggle is NOT enough; use Settings → Testing → **Test stages → Factory reset**
(signs you out) or a stage-user spawn; if the Test-stages row is absent, flip
`testing.stage_users` + `POST /api/feature-flags/reload` for the window, flip back after.
Pass bar: the s2.2 swipe beat's bubble renders **top of screen above the chip strip**, card +
Pass/Like fully visible (minor ring-top graze OK at max text size); n12/n19/one untargeted
beat unmoved; works with the ram mascot.
