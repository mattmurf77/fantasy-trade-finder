# Lab layout: one directory, one question

## Directory

```
mockups/<slug>/
  index.html       master viewer, or the lab itself when it is one page
  <page>.html      one page per facet of the question, when there is more than one
  <page>-v2.html   operator iterations, unless the round lives as a section on the same page
  before/          operator TestFlight screenshots (before-pane.md (e)), only if supplied
  review/          round-<N>.md verdict sheets (review-round.md), optional
  README.md        optional: pages table, traced-vs-reconstructed, binding docs, verdict pointer
```

**Slug:** a kebab-case topic. Feedback work adds the item ID, and multi-ID work uses the
lowest (`more-offers-shop-402`). Batch work adds a date (`polish-lab-2026-08`). Never
reuse a slug for a different question.

## Master viewer

- Make it **link-only**: a card per page, each an `<a href>` to a sibling file. Don't use
  iframes. It must work over `file://`. `mock-draft-2026-08-13/index.html` is the model.
  `srcdoc` iframes break relative `<img>` paths, as `candidates-300/index.html` notes.
- A one-page lab makes `index.html` the lab itself (`home-engagement/`,
  `settings-ia-hub/`), with a section nav that lists the current candidate first.
- Every lab opens with a head note. It states the question, the binding docs, the
  before-pane result per screen, the tokens sha, that sample data is invented ("no real
  handles"), and "Design only. Not shipped code."

## Stamps

Every app frame carries exactly one provenance stamp. Reuse the `.stamp` classes from
`home-engagement/index.html` (`capture`, `recon`, `prop`, `wire`) and add `tf` for
TestFlight screenshots.

| Stamp text | Use it for |
|---|---|
| Real capture · <date> build | A `screens/` capture that passed before-pane (b) |
| TestFlight screenshot · <version> (<build>) · <date> | An operator-supplied screenshot stored in `before/` |
| Reconstruction from source, not a capture | A frame drawn from source at a named sha |
| Proposed | A direction or variant |
| Wireframe | Structure only, no styling claims |

SUPERSEDED · <round or ruling> sits *on top of* a frame's stamp once a later round
replaces it (SKILL.md § Rounds). New copy is tagged PROPOSED COPY in place.

## Self-contained

- Inline all CSS and JS. Use no CDN, no Google Fonts and no network request of any kind.
  Font tokens fall back (SKILL.md § Fidelity rules).
- The only expected cross-directory reference is a capture `<img>`
  (`../../screens/mobile/…`). TestFlight screenshots sit in `before/`. Draw every other
  image as inline SVG or embed it as a data URI.
- `mockups/*/node_modules/` is gitignored; never commit one. `trade-calc/` is the only
  lab that isn't HTML.
- `mockups/` and `screens/` are both listed in `.easignore`, so neither ships in the EAS
  archive. Nothing in `mobile/`, `web/` or `extension/` may import from `mockups/`.

## Binding docs

Link them from the page head and from the README. They are `docs/plans/<slug>/` (scope
block, research) or `docs/feedback/items/<id>-<slug>/` (PRD, rulings). The lab is the
picture and the binding docs hold the decision. A verdict that exists only on a lab page
is lost.

## Index row

Add or update the lab's row in `mockups/CLAUDE.md` § Index:

```
| [`<slug>/`](<slug>/README.md or index.html) | #<id> or — | YYYY-MM-DD | <status> | <question>; current candidate first; captures embedded vs reconstructions; binding docs |
```

Columns: Lab, Item(s), Last touched, Status, Question it answers. Status is one of: in
flight · most recent · superseded (by …) · partially built · historical. Status
describes the lab, not the feature. Never rewrite an older row's history.

## Viewing

Serve from the **repo root** so `../../screens/…` resolves:

```bash
python3 -m http.server 8000      # from the repo root
# open http://localhost:8000/mockups/<slug>/index.html
```

`file://` works too. Don't use the `mockups-preview` config in `.claude/launch.json` for
a lab that embeds captures. Its document root is `mockups/`, so `../../screens/…` points
outside it and the images break (`more-offers-shop-402/README.md`, "Viewing note").
Before handing a lab over, look at every embedded image.
