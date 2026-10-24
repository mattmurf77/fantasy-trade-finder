# Verdict template

Write the verdict to:

- `docs/plans/<slug>/design-review.md` for planned work (same folder as `ux-lead`'s
  `ux-review.md` and the scope block), or
- `docs/feedback/items/<id>-<slug>/design-review.md` for a feedback item (multi-ID fixes
  use the lowest ID, per `docs/feedback/items/README.md`).

One file per change. A re-review after fixes appends a dated `## Re-review` section and
rewrites the verdict line; it never deletes the first pass.

## Severity and verdict

| Severity | Means | Examples |
|---|---|---|
| **block** | Breaks a Chalkline rule outside a valid exception, or a floor | Any F-rule hit not cleared; an undocumented exception; flare on a primary affordance; a new hue; position/tier colour with no text label; text contrast below 4.5:1; an interactive boundary below 3:1; a hit target under 44pt with no exception; no visible focus ring; a parallel variant of an existing component; an invariant colour change without joint sign-off |
| **note** | Should change, does not block | A second orchestrated motion on the screen; ice at 3 when 2 would read better; a near-miss on a signature move; a tile hub drawn as a link list |
| **debt** | A violation the diff touches but did not create or worsen | A moved line that already had `fontSize: 9` |

- **pass**: no findings, nothing owed.
- **pass with notes**: no block; at least one note, debt row or docs-owed item.
- **block**: one or more block findings. Name what clears each one.

## Template

```markdown
# Design review — <change name>

**Verdict:** pass | pass with notes | block
**Reviewer:** <worker> for design-lead (or head-product, design-lead unstaffed) · **Date:** YYYY-MM-DD
**Diff:** `<branch>` @ `<sha>` vs `origin/main` @ `<sha>` · mode: committed | uncommitted
**Surfaces:** mobile | web | extension | mockup — <screens / components touched>
**Read:** <PRD or scope block path> · <components.md rows consulted>
**Exceptions relied on:** <E-IDs from the skill's exceptions register, or "none">

## Findings

| # | Severity | file:line | Rule | Finding | Clears when |
|---|---|---|---|---|---|
| 1 | block | `mobile/src/...tsx:123` | Prohibition 5 | `borderRadius: 12` on a card | radius `radii.md` (8) |

## Docs owed

| Doc | What to add or fix | Owner |
|---|---|---|
| `docs/design/components.md` | Row for <component>: spec, testID `<id>`, source file | design-lead |

## Seams handed off

| To | What | Route |
|---|---|---|
| ux-lead | <flow / state question> | via head-product |

## Evidence

### Sweep
Ran `references/sweep.md` §1 (<mode>) at `<sha>`. Summary (`wc -l /tmp/design-review/S*.txt`):

| Rule | Hits | Triage |
|---|---|---|
| S1 emoji | 0 | — |
| S5 radius | 1 | finding 1 |
| S7 shadow | 2 | cleared: both `...shadowSheet` on `FooSheet` (a sheet) |

### Code-walk
Numbered, file:line-cited trace for each judgment item the sweep cannot see (rendered
ice count, hit target after `hitSlop`, label pairing, motion count, component reuse).

### TestFlight checklist (only when runtime matters)
Build `<version (build)>`. Numbered steps: screen, action, what to look at, expected
result. Omit the section when the code-walk settles everything.

### Not run
<e.g. "`npm run test:contrast` not run: no token change">
```

## Rules for the evidence

- Every sweep hit is triaged in the table: a finding number, or "cleared:" plus the
  reason (exception ID, sanctioned use, comment the filter missed).
- A code-walk claim cites the line that proves it, not the file.
- A TestFlight step exists only for something code cannot show (how 5 ice elements
  read together, Dynamic Type growth, a 40pt row's tap feel). D-056 retired the
  simulator, Maestro and screen captures; never offer them as evidence, and never cite a
  `screens/` PNG as proof of current UI (the library froze 2026-08-11).
- "Not run" is a finding about the review, not a silent gap.
