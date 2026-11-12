# Feature Scope — Founders' review (player label review)

**Date:** 2026-11-11
**Entry point:** direct ask (operator, 2026-11-11): "a feature page just for me … a new tab in calibration: for Founders' review"
**Builder:** subagent on `feat/founder-label-review` (worktree `.claude/worktrees/founder-review`, cut from `release/2026-11-12-train`)
**Operator sign-off on waivers:** needed for §1 (analytics waived) — surfaced in the build report

Design and the override rule table: [design.md](design.md).

**Operator ruling 2026-11-12 (QB scope):** "The labels should be settings specific for QBs. Cornerstone QBs in
SF are not cornerstone in other leagues." QB overrides are scoped by the league's QB format (superflex / 2QB vs
single-QB, the repo's one superflex test on lineup slots); RB / WR / TE overrides stay global. The table carries
a `scope` column so another position can take a scope later (TE premium: open question, not built).

---

## 1. Analytics scope

- [ ] (a) New events specced — none.
- [ ] (b) Existing events cover it — n/a.
- [x] **(c) WAIVED — no analytics needed because:** the page is founder-only tooling (an allow-list of
  account ids, normally one); it emits no client event, so nothing needs registering in
  `backend/analytics_taxonomy.py` (the taxonomy governs emitted events, and the default-deny ingest would
  drop an unregistered one). The founder's actions are recorded in `founder_label_overrides` itself, and the
  read route returns the aggregate review summary (design §6). No player-level data is in any event because
  there is no event. Generic `api_request_failed` from `api/client.ts` still fires on a failed call, as for
  every route (route-normalised, no player data); the capability probe's routine 404 is opted out with
  `quietStatuses`.

## 2. Schema & flag scope

- **New table:** `founder_label_overrides` (player_id + scope PK, label, set_by, set_at) — additive, created by
  `metadata.create_all`, no destructive migration → `docs/data-dictionary.md`. Account deletion anonymizes
  `set_by` (`backend/accounts.py`).
- **New flag:** `founder.review` — default False in `backend/feature_flags.py`, false in
  `config/features.json`, mirrored false in `backend/tests/fixtures/flags/{release,onboarding-v2,profiles-on}.json`
  → `docs/config-reference.md`. Graduation: none planned; it stays an operator switch. Off ⇒ all three
  `/api/founder/*` routes 404 and the app shows nothing.
- **New env var:** `FOUNDER_ACCOUNTS` (comma-separated account ids; unset ⇒ routes 404) →
  `docs/config-reference.md`, runbook entry. No real id in the repo.
- **Rollback levers (deploy-free):** flag `founder.review` false hides the page. The overrides only reach users
  through revision 5 (`owner_bilateral_revision_5_enabled`, 0 today); deleting rows (or the page's "Reset to
  engine" + Save) returns players to the engine's labels.
- `DECK_PIPELINE_VERSION` 27 → 28 (`_season_evidence` changed).

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-founder-review.js` (`npm run test:founder-review`) — pins:
  the section renders only on the server capability (no flag or local check), the band order and
  vocabulary equal the server's `founder_review.BANDS` / `LABELS`, tap-then-band wiring, the changed count,
  save sends only changed players (set vs clear), reset clears to the engine label, the empty state shows the
  server's reason, testIDs, no local `FeedbackFAB`; executes `src/utils/founderReview.ts` under node.
- [x] **Unit tests:** `backend/tests/test_founder_review.py` — allow-list enforcement (flag off, env unset,
  non-listed account, unverified session, demo session, device id / body id never grant; 404 with no state
  change), vocabulary validation, unknown and pick ids rejected, set / clear / idempotent, the
  (engine label, override) table case by case, `league_profile` byte-identical without overrides, overrides
  reaching plan fit, the conflict rule, the card's `season_block` labels and the admin route identically,
  the digest / request hash moving only for an override that can matter, the pipeline pin, account
  deletion. Updated: `test_deck_pipeline_digest.py` (FROZEN_PINS row 28).
- [x] **Code-walk proof:** in the build report (file:line trace from the Save tap to the stored row, and from
  the stored row to the label on a revision 5 card).
- [x] **Manual TestFlight checklist:** below.
- `testID`s added: `calibration.segment.grading`, `calibration.segment.founder`, `founder-review.*` (see the
  guard). testid-lint must stay green.

### Manual TestFlight checklist (operator)

Setup: `FOUNDER_ACCOUNTS=<your account id>` on the server, flag `founder.review` true, a Sleeper league with a
current saved season forecast selected in the app, signed in on a **verified** session.

1. Open Calibration. Expected: a "Grading | Founders' review" control at the top; Grading is selected and
   behaves exactly as before.
2. Sign in on a second device / account that is not in `FOUNDER_ACCOUNTS`. Expected: no control at all.
3. Tap Founders' review. Expected: QB / RB / WR / TE segments, five bands in the order Cornerstone, Win-now
   piece, Rebuild piece, Depth, No label, each with a count; each chip shows name, team, age, pts/game, value;
   the starter line is printed for the position. On QB the heading reads "QB labels · Superflex leagues" in a
   superflex league and "QB labels · 1-QB leagues" in a 1-QB league, with one line about the other format.
4. Tap a starter (in Cornerstone or Win-now). Expected: ice border + check; footer shows the four labels with
   only Cornerstone and Win-now enabled. Tap Win-now (or Cornerstone). Expected: the chip moves bands, shows
   "engine: <old label>", counts update, "1 changed".
5. Tap a bench player (Rebuild / Depth) plus a starter together. Expected: no target chip is enabled (no
   label is legal for both). Deselect one; the two legal chips light.
6. No label band: tap a chip. Expected: nothing happens (read-only); its line says borderline or no projection.
7. Save. Expected: "Saved" toast, "0 changed", the moved chip keeps its new band after leaving and returning
   to the tab; the summary shows e.g. "RB: 1 moved · Win-now piece → Cornerstone 1".
8. Move that player back to the band showing "engine: …", Save. Expected: the note disappears; summary moved
   count drops (the override was cleared).
9. Make two moves, then Reset to engine. Expected: both return; "0 changed"; Save is disabled.
10. Select a league with no saved forecast (or a non-Sleeper league). Expected: an empty state naming why
    ("No saved season forecast for this league" / "Only Sleeper leagues have season forecasts").
11. Move a QB in a superflex league and Save; switch to a 1-QB league. Expected: that QB shows the engine's
    label there (no "engine: …" note, not counted in the summary); back in the superflex league the move holds.
12. Turn `founder.review` off and reopen the app. Expected: the control is gone; Calibration is the grading
    page only.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | three `/api/founder/*` routes |
| `living-memory/LLD.md` | n/a because this agent may not touch `living-memory/` (the main session writes back); no convention shifted — the founder gate is a new route-level predicate documented in api-reference |
| `docs/architecture.md` | n/a because no module was re-wired: overrides enter through the existing `_season_evidence` → `league_profile` path; the new `founder_review.py` is a leaf used only by its routes |
| `living-memory/HLD.md` | n/a because no architecture shift (and not this agent's to write) |
| `docs/cross-client-invariants.md` | updated | label vocabulary and band order shared by server and app |
| `docs/glossary.md` | updated | Founders' review, label override |
| ADR or `DECISIONS.md` entry | design.md §2 records the global / future-axis decision; a DECISIONS.md row is for the main session (living-memory is out of scope here) |
| `docs/data-dictionary.md` | updated | `founder_label_overrides` |
| `docs/config-reference.md` | updated | `founder.review`, `FOUNDER_ACCOUNTS` |
| `docs/runbook.md` | updated | enabling Founders' review for an account |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (+ `check-*.js`) + testid-lint — run locally in this
  worktree, results in the build report; nothing pushed.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry is for the main session to write.
- **TestFlight verification:** the checklist above, by the operator, after the next build.
- Express lane declared by the operator? no.
