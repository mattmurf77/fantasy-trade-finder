# Before pane: which "current" frame a lab may show

## The rule (operator decision W2, 2026-10-15)

> Embed the screen's real capture only when one exists and `git log` shows the screen's source unchanged since 2026-08-11. Otherwise use a labelled reconstruction from source that names the files changed since then. TestFlight screenshots the operator supplies may also serve as before-panes. They're stored in the mockup's folder, never in `screens/`. Never present a reconstruction as a capture. D-056 stays intact.

Quoted verbatim, here and in `mockups/CLAUDE.md`. Never reword it; the procedure below
only says how to apply it.

## Procedure, per screen the lab revises

Run from the repo root. Everything here is read-only. Never run
`mobile/scripts/screen-capture.sh` or `mobile/scripts/screen-freshness.sh` (out of policy
under D-056), and never write anything under `screens/`.

### (a) Find the screen and its source

The screen dir is the app's testID prefix; `screens/CLAUDE.md` maps dir to source file.
Print the dir's source list and capture times:

```bash
python3 -c "import json,sys; s=json.load(open('screens/manifest.json'))['screens'][sys.argv[1]]; print(*s['source'], sep='\n'); [print(c['captured_at'], c['file']) for c in s['captures']]" <dir>
```

A `KeyError` means the screen was never captured: go to (d). Otherwise build the file list.

- **Strip annotations.** Some entries carry a note after the path
  (`mobile/src/navigation/TabNav.tsx (RankMenu + MoreWaysButton)`, `backend/server.py espn_link`).
  Pass the bare path. The annotated string matches no file, so `git log` returns nothing
  and the screen looks unchanged when it isn't.
- **Confirm every path is tracked:** `git ls-files -- <path>`. An untracked path proves
  nothing. `onboarding` lists `mobile/src/screens/OnboardingScreen.tsx`, which has never
  existed. If you can't name the real files, the screen fails (b).
- **Add the shared components the screen renders.** The manifest list can miss them. For
  each screen file run `git grep -n -E "from '(\.\./)+(components|theme)/" -- <screen file>`
  and add the file behind every name it imports. For example,
  `{ Button, TickLabel } from '../components/chalkline'` adds
  `mobile/src/components/chalkline/Button.tsx` and `TickLabel.tsx`. Add
  `mobile/src/theme/chalkline.ts` as well. Code files only; skip `README.md` and `CLAUDE.md`.

### (b) Check the history

Take the earliest `captured_at` among the states you will embed and pass it whole,
offset included:

```bash
git log --oneline --since=2026-08-10T22:56:34+00:00 -- <files>
```

This one command covers W2's window (since 2026-08-11) and the stricter reading of it: a
commit that landed between the capture and 2026-08-11 is a change too. **Never pass a bare
date.** Git fills in the current time of day, so `--since=2026-08-11` run in the afternoon
silently skips that morning's commits.

- **No output:** unchanged. Go to (c).
- **Any commits:** changed. Go to (d). One exception: commits that cancel out (a change
  and its revert) leave the source unchanged. Prove it, don't assume it:

  ```bash
  git rev-list -1 --before=<captured_at> HEAD    # the build the capture shows
  git diff --stat <that sha> HEAD -- <files>
  ```

  An empty diff goes to (c), and the page cites the empty diff. Any diff at all, a
  comment-only one included, goes to (d).

Write the command, the file list and the result into the page's provenance note. Run it
again at the start of every round, because source moves between rounds.

### (c) Unchanged: embed the capture

```html
<!-- page at mockups/<slug>/index.html: two levels deep, so ../../ reaches the repo root -->
<img src="../../screens/mobile/<dir>/<state>.png" alt="Real capture: <dir> <state>, <date> build">
```

A top-level `mockups/x.html` uses `../screens/…`; `mockups/<slug>/sub/x.html` needs
`../../../`. Count the depth. A broken `<img>` silently turns the pane back into a drawing
from memory, so open the page and look. Stamp the frame "Real capture · <captured_at date>
build". Before designing, open every PNG under `screens/mobile/<dir>/`.

### (d) Changed or never captured: reconstruct from source

- Draw the frame from the current source, not from memory and not from the old capture.
  Copy comes from source strings (SKILL.md § Fidelity rules).
- Stamp every reconstructed frame on the page "Reconstruction from source, not a capture".
- The provenance note names the files changed since the capture and the commits from (b)
  (short sha and subject), plus the sha you read (`git rev-parse --short HEAD`). When no
  capture exists, say so: "No capture of <screen> exists."
- Don't embed the stale capture. W2's "only when" is exclusive. Labs built before
  2026-10-15 (`home-engagement/`, `settings-ia-hub/`) embedded stale captures as labelled
  references under the old interim posture. That isn't a precedent.

### (e) Operator TestFlight screenshots

- The operator supplies them. You may ask for one when a reconstruction can't settle the
  question. Never take one yourself: no simulator, no device automation.
- Store it in the lab: `mockups/<slug>/before/<dir>--<state>--<version>-<build>.png`.
  It never goes in `screens/` and never goes in `manifest.json`. The page references it as
  `before/<file>.png`.
- Label it on the page "TestFlight screenshot · <version> (<build>) · <date> · supplied by
  operator". If the build number or date is missing, ask. Don't guess. It is a real image
  of that build but not a library capture, so never stamp it "Real capture".
- It shows real league data. Before committing it, ask the operator whether leaguemate
  handles may go into the repo. If they say no, crop or mask the handles.

### (f) Never present a reconstruction as a capture

- Every app frame carries exactly one provenance stamp (`lab-layout.md` § Stamps). An
  unstamped frame is a bug.
- Never hand-edit a capture PNG, never save a reconstruction into `screens/`, and never
  edit `manifest.json` to fake freshness.
