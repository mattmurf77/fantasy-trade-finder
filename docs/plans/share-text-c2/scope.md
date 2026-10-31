# Feature Scope — C2: shared trades state "Package value" only (remove-only)

**Date:** 2026-10-31
**Entry point:** direct ask. head-bizops decided it under the launch-roadmap approval; head-eng routed it to trades-eng for the 11-06 binary (cutoff about 11-03).
**Builder:** trades-eng
**Operator sign-off on waivers:** not needed. The waivers below are for things this change doesn't touch.

**Why:** the in-app share text and share image said "fair", "win" and "ratio N%". The in-league lines published a read of the partner's board ("Wins by my board — @opp likely disagrees", "@opp wins this one by their board"), which goes against privacy §3: "Your raw ranking list is never shown to other users".

**The change (remove-only, no new copy, no legal review):**
- **The calculator's text share and image fallback:** the "Consensus: X vs Y (ratio N%)" and "Verdict: …" lines go.
- **The in-league image fallback:** the "Consensus: X vs Y" and board / win lines go.
- **Both share images:** the verdict line is now the existing "Package value" (`SHARE_VALUE_LINE`) in every state, and the TOTAL rows are gone. Per-player tier badges and picks' values stay, as on the in-app sides.
- **Unchanged:** the in-app verdict (the calculator's verdict card, LeagueVerdict). Marketing's consensus-only lines come later.

## 1. Analytics scope

- [x] **(c) WAIVED. No analytics needed:** no event is added or changed. `calc_trade_shared` and `share_package_created` fire as before.

## 2. Schema & flag scope

- **New/changed tables or columns:** none.
- **New/changed feature flags:** none.
- **New env vars / `model_config` keys:** none.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-share-text.js` (`npm run test:share-text`). It pins:
  - `SHARE_VALUE_LINE` is "Package value";
  - the share image has no TOTAL row and takes no totals;
  - in each `<ShareTradeImage … />` element (caption, line and fallback), in the calculator's `shareTrade` text and in the card's own render body, no verdict / win / board / ratio / consensus-total string and no verdict function remain;
  - by meaning too (release-lead's #566 QA P3): no `.verdict` read, `point_ratio`, `give_value` / `receive_value`, `favors`, "fair" or "%";
  - each share region states `SHARE_VALUE_LINE`, and the card renders the line it's given exactly once.
  - **Against main's share code it fails 28 checks.** release-lead's four bypasses (a bare `.verdict` in the text share, "`${…}% fair`" in the fallback, the verdict in the caption, a hard-coded "Verdict: fair" in the card) and two variants are each red.
- [x] **Unit tests:** none. This is a client-only copy removal; the guard covers it.
- [x] **Before/after renders** (for the operator's design OK): `renders/calculator-before-after.png`, and `renders/in-league-before-after.png` against a diverging opponent. They're mocks, not device captures (D-056). `renders/render.py` draws them from the code:
  - the layout of `ShareTradeImage`, with main's TOTAL rows in the before pane;
  - `TierBadge`'s pick-value ladder labels ("2 1sts", "1 1st", …; `type.label` uppercases them on the device), drawn in `chalk.base` with a 1px border in the tier's colour;
  - `PositionChip` the same way, with a pick's border in `ink.lineStrong`; a pick shows its number;
  - the wordmark, then the URL footer;
  - the Chalkline tokens and the card's own fonts.
  The first version drew cyan "ELITE" / "STARTER" badges and no URL footer (release-lead's #566 QA P2-2). Redrawn.
- [x] **Manual TestFlight checklist** (operator, on the 11-06 binary). There's no image-capture toggle on an iPhone: the text fallback is the message body sent with the image (`ShareTradeImage.tsx:150`), so steps 2 and 5 read it in Messages.
  1. **Calculator** (live, both sides filled, a pick on one side) → **Share image**. The card shows:
     - the two sides, players with their tier badges and the pick with its number;
     - then "Package value", then the "Dynasty Trade Finder" wordmark and the URL footer;
     - no TOTAL rows, no "Verdict", no "%".
     The on-screen verdict card is unchanged.
  2. **In step 1's share sheet, pick Messages and read the text body.** It's exactly 4 lines, "Trade idea (…)", "Side A: …", "Side B: …", "Package value", then the link. No Consensus, ratio, Verdict, win or board line.
  3. **Calculator → Share** (the text button). The message is the same 4 lines, then "Build your own: <link>" when share landing is on. No "Consensus:", "ratio" or "Verdict".
     - The link's preview still says "% fair" until #511 is live. That's #511's, not C2's.
  4. **In-league calculator**, against an opponent whose board diverges from yours (a "Wins by my board" or "@opp wins" verdict on screen) → **Share image**. The card says "Package value", never a win or board line, with the wordmark and the URL footer. The on-screen verdict is unchanged.
  5. **In step 4's share sheet, pick Messages and read the text body.** It's exactly 4 lines, "Trade idea vs @opp (…)", "I send: …", "I get: …", "Package value", then the link. No Consensus, ratio, Verdict, win or board line.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change; the share-package mint and the landing are unchanged |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` | n/a | no wiring or data flow change |
| `living-memory/HLD.md` | n/a | no new module or flow |
| `docs/cross-client-invariants.md` | n/a | no shared constant (`SHARE_VALUE_LINE` is the mobile share card's own) |
| `docs/glossary.md` | n/a | no new term |
| ADR or `DECISIONS.md` | n/a | head-bizops's decision, recorded in the launch roadmap |
| `mobile/tests/README.md` | updated | lists `check-share-text` |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` (which runs the check suites), `testid-lint`.
- **Evidence recorded:** TEST_LEDGER.
- **TestFlight verification:** the checklist above, by the operator, on the 11-06 binary.
- Express lane declared by the operator? No.
