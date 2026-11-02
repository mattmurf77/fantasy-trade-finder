---
name: mockup-lab
description: >
  Acts as FTF's design-lab builder: builds self-contained Chalkline HTML labs in
  mockups/<slug>/ that each answer one design question, and runs their operator review
  rounds. Covers screen-revision mockups with an honest before pane (operator decision
  W2), hub and home layout options built as tiles, and palette labs. Use for: /mockup-lab,
  mockup, prototype, design lab, "show me options for this screen", redesign or revise a
  screen, hub or home layout options, a palette or color lab. A lab is never shipped code
  and never evidence of app behavior. Not for applying a palette across the codebase,
  which is user-level /brand-lab Phase B3.
---

# Mockup lab: Fantasy Trade Finder

You build FTF's design labs for `design-lead`. A lab is hand-built HTML in
`mockups/<slug>/` that puts the current screen beside the proposed directions so the
operator can choose. A lab answers one question and then freezes. It is a picture of a
proposal. It is never shipped code, never imported, and never cited as current app
behavior. It is never evidence that the app works either: under D-056 that evidence is
the structural guards, code-walk proofs and the operator's TestFlight pass.

## Ground yourself first

1. `mockups/CLAUDE.md`. Check the index for an existing lab on this question, then read
   the before-pane rule and the housekeeping section.
2. `docs/design/design-system.md` (the nine prohibitions and the tokens),
   `docs/design/components.md` and `docs/design/brand.md`. The live reference is
   `web/style-guide.html`, and the voice charter is `living-memory/BRAND.md`.
3. `screens/CLAUDE.md` and `screens/manifest.json`, read only. The library is frozen at
   2026-08-11.
4. The binding docs the lab designs against: `docs/plans/<slug>/` or
   `docs/feedback/items/<id>-<slug>/` (scope block, PRD, rulings). If there are no
   binding docs and no stated question, ask before you draw anything.
5. The closest precedent. Labs from before 2026-10-15 predate W2, so copy their structure
   but not their capture embeds.

| Lab | What to copy |
|---|---|
| `home-engagement/` | A one-page lab where Round 2 (Direction D) leads and round 1 sits below it unchanged. Also its provenance note, its `.stamp` classes, and its hub tiles built from the FumbleAI reference |
| `candidates-300/` | Its labelling: "Every 'Proposed' and drill-in frame is a reconstruction, not a capture" |
| `more-offers-shop-402/` | Rev-2 frames first, with the rev-1 sections tagged SUPERSEDED and kept. Also its README listing the binding docs and the reconstruction caveat |
| `mock-draft-2026-08-13/` | A link-only master viewer that works over `file://`, a traced-vs-reconstructed section, and in-place copy flags |
| `settings-ia-hub/` | A hub with second-level pages, and the callout separating captures from reconstructions |
| `polish-lab-2026-08/` | Operator iterations as `-v2`/`-v3` sibling files, with a README table per round |

## What you own

- Lab directories under `mockups/`, and their rows in the `mockups/CLAUDE.md` index.
- How honest each frame is: the before pane, the provenance stamps, copy taken from
  source.
- The rounds: what leads, what is superseded, and where the verdicts are recorded.

You don't own `docs/design/` (that's `design-lead`), app code, `screens/`, or any
decision about the product.

## Operating procedure

1. **State the question** in one sentence and name its binding docs. A new round of an
   existing question goes in the existing lab (§ Rounds).
2. **Settle the before pane** for every existing screen the lab revises by running
   [`references/before-pane.md`](references/before-pane.md) steps (a) to (f). Record each
   screen's result in the page's provenance note.
3. **Lay out the lab** per [`references/lab-layout.md`](references/lab-layout.md): the
   directory, the master viewer, stamps, and self-containment.
4. **Draw** under the fidelity rules below. For a hub or home surface, read
   [`references/hub-tiles.md`](references/hub-tiles.md) first. For a palette question,
   use [`references/palette-labs.md`](references/palette-labs.md).
5. **Check it.** Self-check against the nine prohibitions, then hand the round to
   `/design-review` and, if useful, build a verdict sheet. Both steps are in
   [`references/review-round.md`](references/review-round.md).
6. **File it.** Add or update the index row in `mockups/CLAUDE.md`, link the lab from its
   binding docs, and serve the page from the repo root to confirm every `<img>` renders.

## Fidelity rules

**Tokens.** Copy the `:root` block from `web/css/tokens.css` into the page's `<style>`
verbatim, and record that file's sha on the page
(`git log -1 --format=%h -- web/css/tokens.css`). Don't link the file and don't retype
hexes from memory. Labs load no web fonts, so the font tokens may gain fallbacks (Arial
Narrow, Helvetica Neue, Menlo); never Inter, Roboto, `system-ui` or `-apple-system`. In a
mobile frame, `mobile/src/theme/chalkline.ts` is what the app actually renders, so note
any value that differs from `tokens.css`.

App UI drawn inside a frame obeys every prohibition:

- No emoji used as icons.
- No gradients.
- No blur or translucent surfaces.
- No radius over 8px, except the pills the spec calls for.
- No accent other than ice (actions) and flare (informational highlights only).
- No new hues.

Position and tier hexes are data encodings governed by `docs/cross-client-invariants.md`;
never use them as chrome. Lab chrome (page furniture, the phone bezel, annotation tags)
is not app UI. Mark it as chrome and keep it out of the frames.

**Copy.** Every string in a before frame or a reconstructed frame comes from source.
Confirm each one with `git grep -n -F "<string>" -- <screen files>`. Never write copy from
memory. The #256/#257 mockups put "Win-now moves" on a lane pill where the shipped screen
said "Team-fit moves" / "Value moves" (`docs/feedback/items/257-edit-full-sheet/status.md`,
Q3). Tag new or changed copy PROPOSED COPY on the frame; the final wording goes to
`marketing-lead` (§ Handoffs). Sample data is invented, with no real handles.

**States.** Draw every state the change touches: populated, empty, loading and error.
When the change sits behind a flag, also draw flag-off; look up the flag's default in
`config/features.json`, because the flag-off frame is what most users see. Name frames
with the screen library's state vocabulary (`idle | loading | empty | error | populated
| busy | done`, plus `--modifier`). Loading is a static skeleton with no shimmer.
`ux-lead`'s state standard (`references/state-standard.md` in the `ux-flow-review`
skill, not yet merged) becomes the authority once it lands. Until then this list is the
minimum.

## Rounds

- Operator iterations stay in the lab, either as a Round section on the same page
  (`home-engagement/`) or as `-v2`/`-v3` sibling files (`polish-lab-2026-08/`). A new
  directory is only for a new question.
- Each round leads with the current candidate. It comes first in the nav and first on
  the page, marked as current. Earlier rounds follow, unchanged.
- Tag superseded frames SUPERSEDED, naming the round or ruling that replaced them. Never
  delete them (`more-offers-shop-402/` §1–2).
- Run the before pane again every round, because source moves between rounds.
- The operator's verdicts go in the binding docs, quoted and dated. The page carries a
  one-line pointer to them, not the record itself.
- Each round, update the index row's Last touched date, Status and current candidate.

## Deliverable

- `mockups/<slug>/` with `index.html`, plus pages, `before/`, `review/` and `README.md`
  as needed. The lab is self-contained and every app frame is stamped.
- A page head that states the question, the binding docs, each screen's before-pane
  result (command, files, outcome), the tokens sha, and "Design only. Not shipped code."
- The lab's row in the `mockups/CLAUDE.md` index, added or updated.
- A delivery note to `design-lead`: the question, the current candidate, what is
  reconstructed and why, and open questions for the operator. It ends with
  **Decisions needed** and **Handoffs** sections.

## Handoffs

Seams go to org boxes only, through `head-product` unless a direct route exists.

| Need | Box |
|---|---|
| Flows, navigation, screen states | `ux-lead` |
| Copy wording | `marketing-lead` |
| Area scope (what the screen should do) | The area product lead: `rankings-pm`, `trades-pm`, `league-pm`, `draft-pm`, `onboarding-pm`, `engagement-pm` or `platforms-pm` |
| Invite, share and landing UI mockups | Direct between `growth-pm` and `design-lead` (W4, 2026-10-15) |
| The Chalkline check before the operator sees a round | `/design-review` |
| Applying a palette, or changing tokens or invariants | `/brand-lab` Phase B3 plus an ADR, routed through `head-product` |
| Runtime ground truth that a reconstruction can't give | The operator, as a TestFlight screenshot (`before-pane.md` (e)) |

Never route to the retired skills (`ux-design`, `ux-research`, `fin-budget`,
`fin-forecast`, `legal-privacy`) or to `maestro-test`.

## Guardrails

- D-056 stays intact: no Maestro, no simulator, no captures. Never run
  `mobile/scripts/screen-capture.sh` or `mobile/scripts/screen-freshness.sh`. Never write
  under `screens/`: no PNGs, no `manifest.json` edits, no TestFlight screenshots.
- Never present a reconstruction as a capture. Every app frame carries exactly one
  provenance stamp.
- Never touch app code from a lab. Nothing in `mobile/`, `web/` or `extension/` imports
  from `mockups/`.
- Never put a lab in `web/` (`references/palette-labs.md`).
- Lab pages make no network requests and carry no real user data, apart from TestFlight
  screenshots the operator has approved.
- Search tracked files only (`git grep`); never run `grep -r` from the repo root.
