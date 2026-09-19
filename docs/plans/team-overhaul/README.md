# Team overhaul — engineering handoff

Create an actionable overhaul: choose **Push all in** or **Blow it up**, select an eligible asset pool, like trade ideas, compare roadmaps, rank each sell package's alternatives, send the reviewed batch, and resume as responses arrive.

The owner approved the revised core mockups on **2026-09-06**. The additional **Acquire entry/resume placement** was requested afterward and is shown as a new proposal. [Status and evidence](status.md). This packet specifies future work; platform sending/tracking in the prototype is simulated.

## Start here

| File | Purpose |
|---|---|
| [Mockup gallery](mockups/index.html) | All screens in sequence, including the new entry and resume states |
| [Entry interaction mock](mockups/entry-mock.html) | Proposed placement within the existing Acquire tab; launch and saved-plan variants ([source evidence](mockups/entry-mock-evidence.md)) |
| [Approved interactive review](mockups/team-overhaul-review.html) | Core flow, package-by-package drag/drop priorities, notes and optional audio feedback |
| [Product specification](PRODUCT-SPEC.md) | Confirmed requirements, screen contracts, acceptance criteria and clearly labeled unresolved choices |
| [Engineering specification](ENGINEERING-SPEC.md) | Inspected reuse points, proposed data/API boundaries, solver and execution requirements |
| [Implementation plan](plan.md) | Work items, dependencies, ownership and delivery sequence |
| [Acceptance and evidence](QA.md) | Prototype checks, future engine/execution tests and physical-device checklist |
| [Feature scope](scope.md) | Planned analytics, persistence, flags, documentation and release gates |
| [Owner decisions](owner-decisions.md) | Decision provenance and latest mock revisions |
| [Shareable message](HANDOFF-MESSAGE.md) | Copy into an engineering handoff with this folder or ZIP attached |

## Read before building

- A **roadmap** targets 4–5 independent outgoing **packages**; alternatives within a package share its exact outgoing assets. Target 4–5 alternative roadmaps, which may group assets differently.
- Selected assets are eligible, not all required to move. Incoming and outgoing commitments must remain compatible across independent packages.
- Missing the user's original next-season first triggers an exact-pick recovery offer highlighted as **overall Priority 1**, with advisory execution order.
- Priorities are edited **one package per page**, using drag/drop tiers. Same-tier offers may send together with an explicit first-come, first-served warning. Later tiers wait for user action.
- Insufficient compatible likes mean more generation/review plus a prompt to revisit the pool. Preserve the user-controlled pick budget, return mix, optional position preferences and isolated roadmap settings.
- Nine discovery choices remain explicitly proposed, including launch-platform coverage and resume policy. Approval of the mocks did not turn suggested answers into confirmed requirements.

## Open and share the artifacts

Open `mockups/index.html` for screenshots or `mockups/entry-mock.html` for the added entry interaction. `mockups/team-overhaul-review.html` is a standalone HTML file. Its core mock works without an app backend; network access may load display fonts. Notes persist in the browser. Optional audio/clipboard functionality depends on browser permissions and a secure context such as localhost; speech transcription also depends on browser support.

From this folder, an optional local preview is:

```sh
python3 -m http.server 8768 --bind 127.0.0.1
```

Use an available port, then open the corresponding localhost URL. The gallery and screenshots need no server. No recorded audio, response exports, credentials, bridge delivery code, or private league data are included.

To share without publishing, attach `team-overhaul-handoff.zip` and the message below. Its internal mock/spec links work after extraction. Links to implementation source expect this folder at `docs/plans/team-overhaul` within the Fleeced repository. These local files have not been published as hosted URLs.

## Source and prototype maintenance

Source inspection used checkout `801e00ea`; fetched `origin/main` was `0e3d6b70` (owner-led trade construction, #285). The engineering spec records relevant drift. Implement on freshly fetched main and reverify integration points; this continuation preserved the existing discovery branch and local edits.

The core approved HTML and its editable modules are in `mockups/source`. Rebuild after an intentional prototype edit with:

```sh
python3 mockups/source/build-review.py
```

The resulting HTML remains in `mockups/team-overhaul-review.html`. Sample roster/values, fixed package data and simulated platform behavior must not be imported as production code. The packet's screenshots are dated design evidence, not runtime proof.
