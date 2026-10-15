# mockups/ — Notes for Claude

Design scratch/prototypes — hand-built, self-contained HTML (Chalkline tokens, no
frameworks), one directory per lab. **NOT shipped code:** never import from here or cite
it as current app behavior. Live design truth is [`docs/design/`](../docs/design/) +
[`web/style-guide.html`](../web/style-guide.html); current app behavior is
[`screens/`](../screens/CLAUDE.md).

To build a lab, use `/mockup-lab`.

## Index

Every lab answers one design question and then freezes. "Status" is about the lab, not the
feature: **historical** means the question was answered and the outcome shipped or was
rejected — read it for reasoning, never for current UI.

| Lab | Item(s) | Last touched | Status | Question it answers |
|---|---|---|---|---|
| [`home-engagement/`](home-engagement/index.html) | — | 2026-10-10 | in flight | What should Home look like so returning users see their trade opponents and get pulled into League Summary's buyers/sellers split? **Round 2: Direction D (operator revision, current candidate)** first: status rows (team outlook, current standings, overall rank), 2×2 position tiles with Buy/Sell, five task tiles, both Buy/Sell landings (decided pinned banner; Buy = list top, Sell = list end), a new Standings page (Current | Projected; projections fetched only on selection) and the D edge states. Round 1 below it, unchanged: three tile directions modelled on the FumbleAI Home hub (A Hub, recommended then; B League plan; C Partner rails), the A tap-through to League rankings pre-filtered + drill-in, and eight A edge states. **No capture of Home exists** (shipped 2026-10-08, after the freeze): the "before" pane is a labelled reconstruction from `HomeScreen.tsx`; the only embedded capture is `screens/mobile/league-summary/populated.png`. Binding docs: `docs/plans/home-engagement/` |
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

## The before-pane rule (operator decision W2, 2026-10-15)

> Embed the screen's real capture only when one exists and `git log` shows the screen's source unchanged since 2026-08-11. Otherwise use a labelled reconstruction from source that names the files changed since then. TestFlight screenshots the operator supplies may also serve as before-panes. They're stored in the mockup's folder, never in `screens/`. Never present a reconstruction as a capture. D-056 stays intact.

The rule is quoted verbatim; never reword it. It resolves the conflict that this file
used to carry as "⚠ Unresolved: the embed rule vs the screen-library freeze", which labs
built before 2026-10-15 still cite. Those labs followed an interim posture, and some of
them embed captures this rule would now reject. Treat them as history.

**Procedure.** The full version, with commands, is in
[`.claude/skills/mockup-lab/references/before-pane.md`](../.claude/skills/mockup-lab/references/before-pane.md).

1. Find the screen's dir in [`screens/manifest.json`](../screens/manifest.json). Take its
   `source` list (bare paths, each confirmed with `git ls-files`) plus the shared
   components the screen file imports.
2. Run `git log --oneline --since=<captured_at> -- <files>`, passing the earliest
   `captured_at` whole. A commit that landed between the capture and 2026-08-11 counts
   too. Never pass a bare date: git fills in the current time of day.
3. If there are no commits, embed the capture (mechanics below). A change and its revert
   also count as unchanged, but only once an empty `git diff` from the capture's build to
   `HEAD` proves it.
4. If there are commits, or no capture exists, reconstruct from source.
5. A TestFlight screenshot the operator supplies may serve as the before pane instead.
6. Never present a reconstruction as a capture.

**Labelling.** Every app frame carries exactly one provenance stamp:

- "Real capture · <date> build"
- "TestFlight screenshot · <version> (<build>) · <date>"
- "Reconstruction from source, not a capture"
- "Proposed"
- "Wireframe"

A reconstruction's provenance note names the source files and commits changed since the
capture, or says that no capture exists, and gives the sha that was read.
`mockups/candidates-300/` is the model ("Every 'Proposed' and drill-in frame is a
reconstruction, not a capture"). A capture of a screen whose source has changed is not
embedded at all.

**Operator TestFlight screenshots** live in the lab's own folder, at
`mockups/<lab>/before/`, and never in `screens/`. Each one is labelled with its version,
build number and date. Ask the operator before committing real leaguemate handles.

Build labs with the `mockup-lab` skill (`/mockup-lab`).

## Embedding a capture (when the before-pane rule allows it)

When the rule above says to embed, the "before" pane shows that screen's actual capture,
not a redrawn approximation:

```html
<!-- from mockups/<project>/index.html — two levels deep, so ../../ reaches the repo root -->
<img src="../../screens/mobile/<screen>/<state>.png">
```

`mockups/` and `screens/` are siblings at the repo root, so a file at
`mockups/<project>/index.html` — the normal case, and where all but one mockup lives —
uses exactly `../../screens/mobile/…`. A top-level `mockups/x.html` uses `../screens/…`;
one level deeper (`mockups/<project>/sub/x.html`) needs `../../../`. Count the depth; a
broken `<img>` silently degrades the mockup back into a from-memory drawing.

The library is frozen under D-056, so never request or run a capture. See
[`screens/CLAUDE.md`](../screens/CLAUDE.md).

**Why this rule exists (#256/#257):** the TradesHome full-sheet mockups carried
placeholder copy invented from memory — lane pills labelled "Win-now moves" when the
shipped screen said "Team-fit moves" / "Value moves" — and the divergence had to be
caught and corrected by operator decision at build time
(`docs/feedback/items/257-edit-full-sheet/status.md`, decision Q3). Embedding the real
capture makes that class of drift impossible. Where no current capture exists, the guard
is a reconstruction drawn from source with its copy taken from source strings, and the
label is what keeps it honest.

## Housekeeping

- `mockups/` and `screens/` are both listed in `.easignore`, so neither ships in the EAS build archive.
- `mockups/*/node_modules/` is gitignored (307 MB in `trade-calc/` alone). Keep every other lab self-contained — inline CSS/JS; the capture `<img>` is the only expected cross-directory reference.
- New lab? Give it a directory, an `index.html` master viewer, and a row in the table above.
