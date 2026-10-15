# Scope block — procedure

How an area PM fills `docs/templates/feature-scope.md` for a change, and how the same PM
accepts the built result against it. The template holds the sections; this file holds
the rules for filling them. Root `CLAUDE.md` §Conventions "Feature gates" is the source
rule; D-056 sets the evidence regime.

**Exemplars:** `docs/plans/usage-trends/scope-order-toggle.md` §3 (named sabotages,
real-data checklist) and `docs/plans/home-engagement/scope.md` §3 (guard table with
"must pass UNMODIFIED" suites, a numbered code-walk, a 15-step checklist).

## Contents

- [When and where](#when-and-where)
- [Header](#header)
- [§1 Analytics](#1-analytics)
- [§2 Schema and flags](#2-schema-and-flags)
- [§3 Evidence](#3-evidence)
- [§4 Docs table](#4-docs-table)
- [§5 Ship gate](#5-ship-gate)
- [§6 Flow, states and reviews](#6-flow-states-and-reviews)
- [§7 Platform scope](#7-platform-scope)
- [§8 Model-visible change](#8-model-visible-change)
- [Waivers](#waivers)
- [Re-diff against origin/main](#re-diff-against-originmain)
- [Product acceptance pass](#product-acceptance-pass)

## When and where

Every change touching user-visible behavior, data collection, schema or API gets a
scope block, in any pipeline. Express lane is the only exemption, and only the operator
declares it.

| Work | File |
|---|---|
| Area work (direct ask, NEXT.md, staged-work) | `docs/plans/<slug>/scope.md`, beside `prd.md`. Add the `docs/plans/README.md` row in the same session. |
| Feedback item | `docs/feedback/items/<id>-<slug>/scope.md` (lowest ID for a multi-item fix; INDEX row per that folder's README) |
| A follow-on change to a shipped scope | a sibling `scope-<change>.md` (like `usage-trends/scope-order-toggle.md`) or a dated addendum at the end of the existing file (like `fit-scorecard/scope.md`) |

Copy, never edit in place: `cp docs/templates/feature-scope.md docs/plans/<slug>/scope.md`.

## Header

- **Date:** ISO, the day the scope was written.
- **Entry point:** feedback #, NEXT.md item, or direct ask.
- **Strategy owner** (decision P1 of the org bring-up), one of:
  - an operator direct ask, quoted with its date;
  - `models-lead`, for model behavior, with the packet path;
  - a strategy note by the area PM (hypothesis, why now, success signal), with its path
    and the date `head-product` accepted it.
- **Builder:** the eng lead or session that will build it.
- **Operator sign-off on waivers:** yes, with the date, or "not needed (no waivers)".

## §1 Analytics

- Answer exactly one of (a) new events, (b) existing events cover it, (c) waived.
- Check every event name you cite:
  `git grep -n '"<event_name>"' -- backend/analytics_taxonomy.py`. Client events must
  be in `ALLOWED_CLIENT_EVENTS`, server events in `SERVER_FIRED_EVENTS`. A name that
  isn't there is new: that is (a), not (b).
- For (b), name each event and the question it answers.
- For (a), spec name, properties, trigger moment and client. The emitter's commit must
  also register the name in `backend/analytics_taxonomy.py` and classify it against
  `analytics_queries.NON_INTENT_EVENTS` (add it there if it is not a user-intent
  signal) — same commit, never a follow-up. Name the backend test that pins this
  (exemplar: `backend/tests/test_analytics_taxonomy_home_hub.py`).
- Attach `analytics-lead`'s grant for (a): it holds `analytics_taxonomy.py` and
  `NON_INTENT_EVENTS`. Tracking-plan addenda live in `docs/business/analytics/`.
- Never invent event names.

## §2 Schema and flags

List each item, or write "none":

| Item | Doc it triggers |
|---|---|
| New or changed tables or columns | `docs/data-dictionary.md`, migration reviewed |
| New or changed feature flags | `config/features.json` + `FLAG_KEYS` in `backend/feature_flags.py` + `docs/config-reference.md`; default state and graduation criterion |
| New env vars or `model_config` keys | `docs/config-reference.md`; for risky work, name the deploy-free rollback lever |
| New or changed routes | `docs/api-reference.md` (and the §4 row) |
| Values shared across clients | `docs/cross-client-invariants.md` |

State the flag-off posture here too; the acceptance pass checks it. These contract docs
belong to whoever `head-eng` names for the wave: the scope names the rows, the owner
writes them.

## §3 Evidence

D-056: no Maestro, no simulator, no captures. Four kinds of evidence, each answered or
waived.

**Guard inventory, per touched screen or component.**

```
git grep -l "<ScreenOrComponentName>" -- mobile/tests/
```

List each covering `check-*.js` suite, and flag any touched screen with no guard. Then
split them as `home-engagement/scope.md` §3 does: suites that gain checks, and suites
that must pass **unmodified** (the flag-off regression net). CI's `mobile-typecheck`
job runs every `mobile/tests/check-*.js`, so a new guard gates CI as soon as the file
exists.

**One named sabotage per new assertion.** Name the deliberate break that must turn it
red, and record that it did. A check that has never gone red on a sabotaged build does
not count. Exemplar: `usage-trends/scope-order-toggle.md` §3 lists eight.

**Backend tests by name:** `file::test_name`, with the case each one pins. "Tests
added" is not an answer.

**Code-walk skeleton.** One row per requirement whose behavior no guard can see. Eng
fills the line numbers at build; the PM writes the rows and the regression column.

| AC | Entry (file:line) | State or branch (file:line) | Render or response (file:line) | A regression would look like |
|---|---|---|---|---|
| AC-1 | | | | |

**TestFlight checklist** (when runtime proof matters; it is the only runtime evidence
mobile gets). Rules:

1. Build number and marketing version, e.g. `1.21.3 (166)`.
2. Preconditions: account, league type and platform, first-run or returning state.
3. Flag pins: the `config/features.json` values the steps assume.
4. Exact screen and exact tap.
5. The expected value with real, specific data: names, numbers, copy.
6. Each step catches one named regression.
7. The outcome is logged in `living-memory/TEST_LEDGER.md`.

A step that meets the bar (from `usage-trends/scope-order-toggle.md`): "Under 'Biggest
jumps last week', each card reads 'Jumped from X% to Y% of … plays'. The gap shrinks as
you scroll down. Darius Cooper (22% → 90%) is above Braelon Allen (41% → 94%)." A step
that does not: "Check the list is sorted."

List `testID`s added or renamed; they must pass `mobile/scripts/testid-lint.sh`.

## §4 Docs table

Fill every row: "updated" plus the section touched, or "n/a because …". At spec time
the rows are the plan; at acceptance each "updated" row must have a commit on the branch
that touches that doc.

## §5 Ship gate

As the template says: CI green on the pushed sha, the evidence entry in
`living-memory/TEST_LEDGER.md`, the operator's TestFlight outcome logged if §3 has a
checklist, and whether the operator declared express.

## §6 Flow, states and reviews

- **UX review by `ux-lead`** (decision P16 of the org bring-up). A full review when the change adds a
  visible entry, changes a tab or the IA, adds a deep link, adds an interrupt, or adds a
  new screen's states. A flag-dark registration gets a light check at registration and
  the full review at flag flip. Otherwise waive it with the reason.
- **Design review by `design-lead`** for any UI change, against Chalkline
  (`docs/design/design-system.md`, `components.md`). Waive only with no UI change.
- **States:** fill all six rows (first-run, empty, loading, error, offline, flag-off).
  Flag-off says "byte-identical" and names the guard that proves it, or states the
  difference.
- Both reviews reach you through `head-product`; attach the paths.

## §7 Platform scope

- One row per platform: Sleeper, ESPN, MFL. Fleaflicker is dark (`fleaflicker.link`
  false), so it is n/a unless the change lights it.
- For each: the reads and writes the feature uses, and the behavior — parity, the honest
  `platform_unsupported` payload, fallback copy, or n/a.
- Follow `references/platform-parity.md` (written by `platforms-pm` on its own branch;
  pending until it lands). Until then, `platforms-pm` reviews §7 through `head-product`.

## §8 Model-visible change

- Answer yes or no, with the reason. Yes if the change alters what a model outputs
  (ranking, tiers, matchup selection, values, trade scoring or packaging, deck rules and
  filters, outlook, pick values) or how model output is shown.
- If yes: name the model, fill a packet in the format of
  `references/model-change-packet.md`, save it beside the scope, and attach
  `models-lead`'s sign-off. The route is `head-product` → `head-bizops` →
  `models-lead`.

## Waivers

- Written reasons only. Silence is not a waiver, and "n/a" alone is not a reason.
- Surface every waiver to `head-product` before build. It carries them up the chain for
  the operator's sign-off, which the header records.

## Re-diff against origin/main

Run it before the spec goes to eng, and again before acceptance:

```
git fetch origin main && git log --oneline <spec-sha>..origin/main -- <files the change owns>
```

`<spec-sha>` is the `origin/main` commit the spec was written against. On any hit, stop
and compare designs before going further: concurrent sessions ship overlapping work (the
2026-09-03 [ship] lesson in `.claude/skills/feedback/lessons.md`: a parallel session
shipped the same knob with opposite semantics).

## Product acceptance pass

Run it when `head-product` asks you to accept a built diff or a TestFlight result. Write
it at the end of the scope file (or as `acceptance.md` beside it).

**AC → evidence:**

| AC | Evidence type | Evidence | Result | Verified by |
|---|---|---|---|---|
| AC-1 | test name / check-suite assertion / checklist step | `test_file.py::test_name`, `check-x.js` 2e5, or checklist step 4 | pass / fail / not run, at `<sha>` | the CI run, `release-lead`, or the operator |

Every AC needs at least one row. "Not run" is a finding, never a pass.

**Then check, in order:**

1. **Flag-off posture:** byte-identical when off (name the guard that proves it), or the
   stated difference matches what shipped.
2. **Analytics grant:** attached, and the emitter, registration and classification
   landed in one commit (`git show --stat <sha>`). Or §1 is (b) or (c).
3. **Reviews:** §6 UX and design, §7 platform, §8 `models-lead` — each attached or
   waived with a reason.
4. **Docs rows:** every "updated" row matches a commit; every "n/a" has a reason.
5. **Re-diff:** clean against `origin/main`, or the overlap resolved.
6. **Verdict line:**

```
Verdict: accept | partial (AC-n open: …) | reject (reason) — <area>-pm, YYYY-MM-DD, at <sha>
```

You accept product behavior only. `release-lead`'s independent QA pass and the
operator's go/no-go still gate ship.
