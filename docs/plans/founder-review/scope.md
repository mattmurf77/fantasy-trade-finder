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

---

## Addendum 2026-11-12 — any label for any player

**Ask (operator):** "For founder's review player labels, remove the controls limiting which label I can
assign." **Branch:** `fix/founder-labels-any-label` (from `origin/main` `12ac0f1d`). Express lane: no.

### What changed

- **The rule.** Any of the four labels for any rostered QB / RB / WR / TE on the page: a starter may be made
  Rebuild piece or Depth, a bench player Cornerstone or Win-now piece, a borderline or unprojected player (No
  label) any label; mixed selections move together. The stored label **is** the label the engine uses
  (`season_value.overridden_label`), replacing D-242's future-axis swap (design.md §2.1 is superseded, kept as
  record). `startable`, `future`, the starter line and the lineup never move, so a label may disagree with
  whether the player starts.
- **Server.** `season_value.with_label_overrides` also keeps overrides for players rostered here without a
  projection (`evidence["unprojected"]`), so their digest moves with them; `league_profile` applies an override
  to a borderline, unprojected or no-line player too (it used to `continue` past them). `founder_review.rows`:
  `movable_to` is all four on every row (kept for builds up to 1.22.0 (187), which enable chips from it);
  `why_unlabelled` says why the **engine** has no label (set even when an override labels him); the summary's
  `corrections` use `"none"` for an unlabelled side (a None side used to make no sense to the app and could not
  be sorted against a label). The write route needed no change: `parse_write` never consulted `movable_to`.
- **App.** `utils/founderReview`: no longer reads `movable_to`; `targetsFor` is all four once anyone is
  selected; a draft may hold `'none'` (back to the engine's no label); Reset returns an unlabelled player to No
  label and Save clears his override; "engine: No label" note. `LabelBandBoard`: no read-only chip; every chip
  has a VoiceOver action per other label; a chip in No label says why the engine has none.
- **Unchanged.** Scope (QB per QB format, RB / WR / TE `all`), founder-only access (404 for everyone else), the
  table, the flag, `DECK_PIPELINE_VERSION` (the digest test did not fail: no listed `server.py` function
  changed). `season_value.py` is in the engine code hash, so stored pages cold once on deploy.

### Consumers when the label and `startable` disagree, or a labelled player has no projection

| Consumer | Label disagrees with `startable` | Labelled, no projection |
|---|---|---|
| `_season_lean` (All-in / Contending viewer, revision 5) | Reads the label only for a player who starts for the team: a starter labelled Rebuild / Depth gets `LEAN_STARTS` (.25) not .40; a bench player is `LEAN_BENCH` whatever his label | Returns None before reading the label: revision 2's age rule (unchanged; open question 2) |
| `_mirror_parts` / `_shed_plan_asset` (Rebuilding / Tanking label fit) | Label read as given (board-led refinements keep precedence) | Label read as given; `young` from age |
| `_older_producer` / `_sell_share` (D-244 sell bonus) | Win-now piece or older Cornerstone counts as an older producer, starting or not | Same |
| `plan_conflict` (label rule) | Label read as given | `future` None counts as market value (existing rule) |
| `_season_signal` assets / `trade_narrative.season_block` | Founder's label printed; "starts for you" independent | No tag (`_season_projected` guard), no crash |
| Founder page, admin label route (`rows_from_search`) | Shows the founder's label | Shows the founder's label |

### Evidence

- `backend/tests/test_founder_review.py`: any label for a starter, a bench, a borderline and an unprojected
  player (pure rule, 24 cases); an unprojected player's override joins the evidence and digest; the route test
  sets all four kinds, reads them back from the page and the admin route, checks the summary adds up and
  `why_unlabelled`, then clears (move back / Reset) and gets the engine's labels back; consumers on the fixture
  league with every label set against `startable` (3 outlooks); a whole revision 5 deck (label fit, sell bonus,
  partner matching) prints the founder's labels. Access tests unchanged (404 for non-founders).
- `mobile/tests/check-founder-review.js`: 3b / 3c / 3e and 4a–4c, 4f, 4h, 6e–6g replace the old restriction
  checks. Each new or changed check sabotaged red, then green with the file's checksum unchanged (build report).
- Runs and counts: build report.

### Manual TestFlight checklist (replaces items 4–6, 8–9 above)

Works on build 187 with the server deploy alone except where marked **(new build)**.

4. Tap a starter, then **Depth**. Expected: he moves to Depth with "engine: Win-now piece" (or Cornerstone);
   Save; leave and return: he stays in Depth.
5. Tap a bench player and a starter together. Expected: all four Move-to chips are lit; tap **Cornerstone**:
   both move.
6. In No label, tap a borderline player and an unprojected one, then **Win-now piece**. Expected: both move;
   Save; they stay; the summary reads "No label → Win-now piece: 2" (on 187 the moved chips show no "engine"
   note; **(new build)** "engine: No label").
7. Move a labelled player back to the band of his "engine: …" note, Save. Expected: the note goes, the summary
   count drops.
8. **(new build)** Reset to engine on that position. Expected: the two players from step 6 return to No label,
   each saying "near the starter line" / "no projection"; Save; they stay there. On 187 Reset leaves them where
   they are (see the build report).
9. VoiceOver on a No-label chip: "Move to …" actions for all four labels.

### Docs

| Doc | Updated? |
|---|---|
| `docs/api-reference.md` | updated (`/api/founder/labels` GET `movable_to`, `why_unlabelled`, summary `"none"`; POST: any label) |
| `docs/cross-client-invariants.md` | updated (Founders' review: Moves) |
| `docs/glossary.md` | updated (Label override) |
| design.md | updated (§2.1 superseded note, §2.2 rewritten, §4 seam) |
| `docs/architecture.md`, `living-memory/HLD.md` | n/a because no module was re-wired |
| `living-memory/*` (DECISIONS: amends D-242; TEST_LEDGER) | n/a here: the main session writes living-memory |
| `docs/data-dictionary.md`, `docs/config-reference.md` | n/a because no schema, flag or knob changed |
