# Review round: Chalkline check, then an optional verdict sheet

## Before the operator sees a round

Every round gets a Chalkline check from `/design-review` before it goes to the operator.
`/design-review` is a sibling skill on branch `skill/design-review` until it merges. Fix
what it finds, or write down why a finding stands. Your own self-check against the nine
prohibitions (`docs/design/design-system.md`) comes first but doesn't replace the review.
If `/design-review` isn't available yet, run the prohibitions list by hand and say so in
the delivery note.

## Optional: a verdict sheet with `/review-html`

When a round asks the operator to choose between directions or variants, give them a
sheet to answer on. Use user-level `/review-html`.

1. Write `mockups/<slug>/review/round-<N>.md` with one `##` section per direction. Each
   section names its frames and links to the lab anchor (`../index.html#dir-d`).
2. Build the page:
   `python3 ~/.claude/skills/review-html/scripts/build_review.py mockups/<slug>/review/round-<N>.md`
3. Add structured controls from that skill's `references/structured-control-markup.md`.
   Use a `choice` radio group per direction (for example Pick / Keep exploring / Drop)
   with the optional comment, and a `checklist` for which states to carry forward.
   Nothing is pre-selected.
4. Give the operator the path. Their notes autosave in their own browser and come back
   only when they paste the "Copy all notes" export into chat.

**Where its output goes.** By default it writes `<source-stem>-review.html` next to the
source, so here that's `mockups/<slug>/review/round-<N>-review.html`. That page embeds
the absolute local path of the source, and you can rebuild it from the `.md`. **Commit
the `.md` only. Never `git add` the generated HTML.**

**It isn't shipped and isn't a lab frame.** Its light theme and blue accent belong to
the review tool and are outside Chalkline's scope, because it isn't app UI. Don't link
it from `index.html` as a design.

## When the verdicts come back

- Record them in the binding docs, quoted and dated: a `rulings-YYYY-MM-DD.md` file in
  `docs/feedback/items/<id>-<slug>/`, or a section in `docs/plans/<slug>/`. The lab page
  gets a one-line pointer.
- The next round leads with the pick. Tag the frames that lost as SUPERSEDED and keep
  them (SKILL.md § Rounds).
- Update the lab's index row: Last touched, Status and the current candidate.
- A verdict that sets a lasting design rule goes to `design-lead`, who updates
  `docs/design/`.
