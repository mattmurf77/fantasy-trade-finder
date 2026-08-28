# mockups/ — Notes for Claude

Design scratch/prototypes — hand-built, self-contained HTML (Chalkline tokens, no
frameworks), one directory per lab. **NOT shipped code:** never import from here or cite
it as current app behavior. Live design truth is [`docs/design/`](../docs/design/) +
[`web/style-guide.html`](../web/style-guide.html); current app behavior is
[`screens/`](../screens/CLAUDE.md).

## Index

Every lab answers one design question and then freezes. "Status" is about the lab, not the
feature: **historical** means the question was answered and the outcome shipped or was
rejected — read it for reasoning, never for current UI.

| Lab | Item(s) | Last touched | Status | Question it answers |
|---|---|---|---|---|
| [`more-offers-shop-402/`](more-offers-shop-402/README.md) | #402+#403 | 2026-08-27 | in flight | Joint "more offers = shop a player" lab (operator ruling 2026-08-27: one experience, renamed from `shop-a-player-403/`). **Leads with six Rev-2 frames**: the give-side "More offers" entry on a deck card, the several-assets chooser sheet, and the inline shop strip below the trade chip in tier-up / same-value+positions / honest-empty / post-dismiss-undo states — deck pan disabled while the strip is open. Rev-1 frames kept below, sections 1–2 tagged SUPERSEDED (Matches long-press entry, pushed screen); sections 3–7 carry. Embeds the real `screens/mobile/matches/populated--mutual.png` (2026-08-10) in the superseded §1; every other frame is a labelled reconstruction (`scope.md` §3 waiver). Binding docs: `docs/feedback/items/402-more-offers-shop/` — start with `rulings-2026-08-27.md` |
| [`team-review-2026-08-19/`](team-review-2026-08-19/README.md) | #357 #358 #359 | 2026-08-19 | in flight | What "analyst-guided" means for a team read, and where the entry point lives in the find-a-trade experience. Verdicts: stepped beats (not a scroll, not a Q&A); reuse the Analyst persona but **not** the `AnalystGuide` overlay; entry is a collapsing card on `TradesHome`, **not** a seventh mode chip. **Rev 2 (same day): the operator lit `outlook.odds` (D-094), so beat `standing` carries a playoff band chip** — championship odds and bare percentages stay refused. Binding docs: `docs/feedback/items/357-team-review/` |
| [`standing-offer-362/`](standing-offer-362/README.md) | #362 | 2026-08-19 | in flight | Post-like prompt that broadens a liked 1-for-1 into a standing offer (years x teams, independent), and how it surfaces to the selected teams. Embeds the real `screens/mobile/trades/populated.png` (2026-08-10); sections 2-5 are labelled reconstructions |
| [`settings-ia-hub/`](settings-ia-hub/index.html) | — | 2026-08-19 | in flight | Settings as a hub page + five second-level pages, and modal sheet → pushed page. Embeds all three real `screens/mobile/settings/` captures; §2–§5 frames are labelled reconstructions (the captures predate the ESPN/MFL disconnect rows added by 3293f4a). Plan: `docs/plans/settings-ia-hub/` |
| `trade-suggestion-redesign/` | — | 2026-08-16 | **partially built** | The presentation rebuild: hero → Featured → uncapped browse, asymmetric explanations, banded confidence, honest empty state. States 01/03/04/07/09 are BUILT behind `trades.presentation_v2` (`docs/plans/trade-presentation-v2/scope.md`); 02 (MESO variants) and 05 (turn states) are blocked on backend that does not exist — `trade_gen.v2` is dark and there is no trade-thread state machine |
| [`candidates-300-v2/`](candidates-300-v2/README.md) | #300 r2 | 2026-08-12 | most recent | League rankings → trade candidates, round 2, drawn against #299 as shipped. Verdict: one list + one median divider |
| [`candidates-300/`](candidates-300/README.md) | #300 r1 | 2026-08-12 | superseded by v2 | Round 1 of the same question; the trailing-affordance geometry contest |
| [`mock-draft-2026-08-13/`](mock-draft-2026-08-13/README.md) | #295 #296 #305 | 2026-08-13 | historical | Mock-draft repair + manual drafting for all teams. Master viewer `index.html` is link-only (no iframes, works over `file://`). Binding docs: `docs/feedback/items/295-mock-user-not-in-draft/` |
| [`polish-lab-2026-08-11/`](polish-lab-2026-08-11/README.md) | #297 #298 #299 #302 | 2026-08-12 | historical | Single-pin recovery, league tile density, drill-in back affordance |
| `decline-reason-capture/` | — | untracked | in flight | Five ways to learn *why* a trade was declined. Spec: `docs/plans/decline-reason-capture/SPEC.md` |
| [`outlook-odds/`](outlook-odds/feasibility.md) | #169 | 2026-08-10 | historical | Outlook / odds / value surfacing on League Summary, + a feasibility write-up |
| [`polish-lab-2026-08/`](polish-lab-2026-08/README.md) | #206–#234 | 2026-08-09 | historical | The August polish batch — league switcher, hub density, Trade DNA, empty states, rank-method consolidation, de-emoji'd notifications. 15 pages, many with v2/v3 operator iterations |
| `calc-value-clarity/` | #157 | 2026-07-20 | historical | Make the calculator say who wins and by how many picks |
| `picks-quickrank/` | — | 2026-07-20 | historical | Quick Rank first tier with pick slots |
| `trade-finding-hub/` | #156 | 2026-07-20 | historical | Three shapes for the Trade-Finding Hub (mode tabs / launcher / unified brief) |
| [`avatar-lab/`](avatar-lab/ram-poses.html) | — | 2026-08-22 | **in flight** | Three pages, three eras. `ram-poses.html` is **live, awaiting pose sign-off**: the six guide poses for **Fleeced the ram** ([D-155](../living-memory/DECISIONS.md)), generated one at a time from an approved hero via the Higgsfield `character-sheet` workflow (art in `ram-art/`). Carries the **measured** 96/44/38 pt strips, the bubble-anchor horn-clash test, and the `point` flip test. **Key finding: the painted arm passes at 96 pt and fails at 44 pt** — five poses collapse to the same read on Team Review — which makes the flat *Blend* arm the recommended medium. `ram-versions.html` is the companion archive: every generated version including discarded rounds, the four `thinking` attempts, the cut-out evidence on four grounds, and the sprite-budget working (full-colour RGBA fails at 108–121 KB per `@3x`; **256-colour PNG-8 passes at 23–25 KB**). **[D-156](../living-memory/DECISIONS.md) settled it: painted everywhere**, inset to 70% ink width so the ram sits at the Analyst's scale (62–90 pt ink in a 96 pt box). The flat set is built and retired to reference art. Three pages: `ram-decisions.html` (decision record), `ram-poses.html` (poses beside the Analyst at real sizes), `ram-versions.html` (every version incl. discards) — all fully self-contained, images embedded. D2 moved the anchor off-centre; the corner is still open. Brief: `docs/plans/ram-mascot/brief.md`. `analyst-poses.html` is the operator-approved Analyst art that `mobile/src/components/analyst/` translates 1:1 (**still current, still shipped**). `index.html` is the historical, unshipped "Assistant GM" six-character onboarding experiment |
| `quickset-cards/` | #140 | 2026-07-17 | historical | Team abbreviation + age on QuickSet cards — 6 layouts |
| `tier-density/` | #58 | 2026-07-10 | historical | Tier tile density: compact / cozy / current-tightened |
| [`trade-calc/`](trade-calc/README.md) | — | 2026-07-03 | historical, standalone | **The one non-HTML lab** — a full standalone Expo app mocking the manual trade calculator. Own `package.json`, own `node_modules` (gitignored), needs its own App Store Connect record to reach TestFlight. Scope: `APP_PLAN.md` |
| `onboarding-graphics.html` | — | — | historical | Top-level single page: every onboarding visual in one compendium |

Labs with their own `README.md` are linked above; the rest are self-describing —
open `index.html`.

## ⚠ Unresolved: the embed rule vs the screen-library freeze

**Read this before the rule below it — they are in conflict, and no operator decision has
resolved it.**

- **The rule (below, unchanged):** a mockup revising an existing screen must embed that screen's real capture from `screens/` as its "current" pane.
- **The freeze:** operator decision **D-056** (2026-08-15, Active) retired the simulator entirely, screen captures included. [`screens/`](../screens/CLAUDE.md) is frozen at **2026-08-11** and there is no process to refresh it.
- **The consequence:** for any screen changed after 2026-08-11, or any screen that never had a capture, the rule is **unsatisfiable** — and "request a capture run", the escape hatch the rule was written with, is now out of policy.

**Interim working posture** until an operator resolves this — do all three:

1. **Embed a real capture whenever one exists.** For the ~32 captured surfaces, an 2026-08-11 capture is still exact ground truth for that build and still beats drawing from memory. This covers most work.
2. **When no usable capture exists, reconstruct from source and label it.** Check `git log` on the screen's source files against the capture date, state on the page and in the deliverable which files moved since, and mark every reconstructed frame as a reconstruction. `mockups/candidates-300/` already does exactly this ("Every 'Proposed' and drill-in frame is a reconstruction, not a capture").
3. **Never present a reconstruction as a capture, and never silently skip the "current" pane.** The #256/#257 failure below is what happens when the current state is invented; the freeze does not make that safer, it makes it likelier.

**This needs an operator call:** either the embed rule is formally relaxed to
"embed-if-captured, else labelled reconstruction", or screen captures get an exemption
from D-056. Do not resolve it yourself.

## The one hard rule: embed the real capture

Any mockup revising an **existing** screen must show that screen's actual capture as
its "current"/"before" pane — not a redrawn approximation, not a reading of source:

```html
<!-- from mockups/<project>/index.html — two levels deep, so ../../ reaches the repo root -->
<img src="../../screens/mobile/<screen>/<state>.png">
```

`mockups/` and `screens/` are siblings at the repo root, so a file at
`mockups/<project>/index.html` — the normal case, and where all but one mockup lives —
uses exactly `../../screens/mobile/…`. A top-level `mockups/x.html` uses `../screens/…`;
one level deeper (`mockups/<project>/sub/x.html`) needs `../../../`. Count the depth; a
broken `<img>` silently degrades the mockup back into a from-memory drawing.

~~Missing capture, or stale? Request `mobile/scripts/screen-capture.sh --screen <x>`
before designing.~~ **No longer available** — see the freeze section above. Say so in the
deliverable and fall back to a labelled reconstruction.
See [`screens/CLAUDE.md`](../screens/CLAUDE.md).

**Why this rule exists (#256/#257):** the TradesHome full-sheet mockups carried
placeholder copy invented from memory — lane pills labelled "Win-now moves" when the
shipped screen said "Team-fit moves" / "Value moves" — and the divergence had to be
caught and corrected by operator decision at build time
(`docs/feedback/items/257-edit-full-sheet/status.md`, decision Q3). Embedding the real
capture makes that class of drift impossible.

## Housekeeping

- `mockups/` and `screens/` are both listed in `.easignore`, so neither ships in the EAS build archive.
- `mockups/*/node_modules/` is gitignored (307 MB in `trade-calc/` alone). Keep every other lab self-contained — inline CSS/JS; the capture `<img>` is the only expected cross-directory reference.
- New lab? Give it a directory, an `index.html` master viewer, and a row in the table above.
