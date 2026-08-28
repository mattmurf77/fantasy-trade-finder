---
name: feedback-board
description: >
  Fetch open in-app feedback for Fantasy Trade Finder and republish it as the
  operator's living feedback board — one Artifact, one stable URL, updated in
  place every run. Use whenever the user says "fetch feedback", "update the
  feedback board", "refresh the board", "show me the feedback board", or asks
  to see the open items. This is the READ path: fetch, describe in plain
  language, publish, hand back the link. It ships no code and changes no item
  statuses. When the user wants items actually BUILT — triage, planning, build
  agents, QA, ship — that is the separate `feedback` skill; this one is
  frequently the step before it.
---

# Feedback board — fetch, describe, republish, hand back the link

One artifact, one URL, updated in place. The operator keeps the link; every
run refreshes what is behind it.

**This skill does not change statuses and does not build anything.** If a run
surfaces items that look closed, say so and offer — the `feedback` skill owns
those transitions.

## The four steps

### 1. Build the board

```bash
python3 .claude/skills/feedback-board/scripts/build_board.py
```

Fetches every open item from the prod admin API, joins it against
`descriptions.json` (the plain-language layer), and writes `board.html` next
to the skill. It needs `CRON_SECRET` from `secrets.local.env` at the repo root.

**In an agent worktree that file will not exist** — it is gitignored and lives
only in the main checkout. Symlink it rather than asking the operator for the
secret:

```bash
ln -sf "/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/secrets.local.env" secrets.local.env
```

A 401 means the secret doesn't match Render's env var; a blank value means the
operator needs to fill it in.

### 2. Describe anything new

The script prints `MISSING DESCRIPTIONS` on stderr for any open item with no
entry in `descriptions.json`, followed by that item's raw text. **Write a
description for each one and re-run the script.** A board that renders raw
tester text has failed at its only job.

Each entry is keyed by feedback id:

```json
"404": {
  "area": "Rank",
  "plain": "'Add a league' in the header dropdown drops you on the ranking page instead of the add-a-league flow.",
  "state": "open",
  "note": ""
}
```

- **`area`** — one of the sections in `AREA_ORDER` in the script. Anything
  unrecognised falls into "Other", which is a signal you picked the wrong name.
- **`plain`** — the item in ordinary words, for someone who does not have the
  codebase in their head. Say what the person wants and why, not which
  component is involved. Expand terse reports ("And pick #'s") into the
  sentence they meant. Keep the operator's own framing where it carries
  meaning, in quotes.
- **`state`** — `open` · `dark` (built, flag off) · `partial` (some clauses
  shipped, others didn't) · `discuss` (needs a decision, not a build).
- **`note`** — the short qualifier beside the chip: the flag name for `dark`,
  what's missing for `partial`, a cross-reference to a related item.

**`state` is a claim about the code, so verify it before writing it.** Three
signals must agree: a shipped CHANGELOG entry, the flag's live value in
`config/features.json`, and the code present on current `origin/main`. Never
infer state from the stored status field alone — the database lags reality in
both directions, and a finished work folder is the classic trap: five items on
this board have complete PRDs, code-walks and merged code, and are invisible to
testers because their flags read `false`. **Built-but-dark is not fixed.**

The script also prints `CLOSED SINCE LAST BUILD` for descriptions whose items
have left the open list. They drop off the board on their own; prune them from
`descriptions.json` when convenient.

### 3. Republish to the same URL

Read the URL from `.claude/skills/feedback-board/artifact.json` and pass it as
`url` to the Artifact tool along with the `board.html` path.

**Passing the `url` is what makes this an update instead of a new artifact.**
Publishing without it mints a second board at a fresh URL and the operator's
saved link quietly goes stale. Keep the title and favicon stable for the same
reason — people find the tab by its icon.

### 4. Hand back the link

Give the operator the URL plus what actually changed since last time: new
items, anything that dropped off, and any state you corrected. Lead with the
change, not the process. If nothing moved, say that in one line.

## Design

`board.html` follows Chalkline (`docs/design/design-system.md`) because it
describes this product: dark-only ink surfaces, Barlow Condensed / Archivo /
IBM Plex Mono, ice for actions and flare for what's worth noticing, no
gradients, no emoji, nothing above an 8px radius. Chalkline is dark-only by
design, so the page deliberately commits to one theme and paints every colour
explicitly rather than shipping a light variant.

All markup and CSS live in `scripts/build_board.py` — edit the generator, never
`board.html`, which is overwritten on every run.

## Files

| Path | What it is |
|---|---|
| `scripts/build_board.py` | Fetches, joins, renders. Holds the markup and CSS. |
| `descriptions.json` | The plain-language layer, keyed by feedback id. Durable across runs — the reason a refresh is cheap. |
| `artifact.json` | The one URL this skill owns. Always pass it when publishing. |
| `board.html` | Generated output. Overwritten every run; not hand-edited. |
