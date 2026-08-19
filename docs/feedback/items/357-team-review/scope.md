# Feature Scope — Team Review (analyst-guided team read)

**Date:** 2026-08-19
**Entry point:** feedback #357 / #358 / #359 (tester `jonbonjourvi`, v1.15.0) + operator framing 2026-08-19
**Builder:** planning session `claude/team-review-analysis-plan-1f91e3` (worktree `jolly-leakey-d20295`)
**Operator sign-off on waivers:** **2 of 3 RESOLVED 2026-08-19** — waiver 1 (forward PPG) ratified by the operator (*"Forward PPG cut"*); waiver 2 (championship odds) is a notification, not a choice, and stands; **waiver 3 (PPG rank Sleeper-only/preseason-empty) is still open**. See §6.

> **NOT express lane.** This change adds a route, a feature flag, and analytics
> events, and it writes to `league_preferences`. That is squarely across the
> CLAUDE.md bright line ("schema, API contracts, feature-flag surfaces, or
> analytics events is not a quick fix"). All four gates apply: scope block →
> evidence → docs → ledger.

Companion docs in this folder: [`prd.md`](prd.md) · [`hld-delta.md`](hld-delta.md) · [`lld-delta.md`](lld-delta.md) · [`reconciliation-log.md`](reconciliation-log.md) · [`status.md`](status.md).
Design lab: [`mockups/team-review-2026-08-19/`](../../../../mockups/team-review-2026-08-19/index.html).

---

## 0. What this is, in one paragraph

A six-beat guided read of the user's own team, entered from a card at the top of
`TradesHome`. Each beat states one finding from data that already exists, says
what it means in ordinary words, and offers one action — and four of the six
actions write `league_preferences`, which is what the trade engine already reads.
It is an idea-generation surface whose exit is a deck that has been reshaped by
what the user just agreed to, not a report. It ships **odds-free**;
`outlook.odds` stays dark (§7).

---

## 1. Analytics scope

**(a) New events specced** — four, all client-fired, mobile only.

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `team_review_opened` | `league_id`, `source` ∈ `trades_home_card` \| `collapsed_row` \| `deck_empty` | The Team Review screen mounts. One row per entry, not per beat. | mobile |
| `team_review_beat_viewed` | `league_id`, `beat` ∈ `standing`\|`window`\|`depth`\|`divergence`\|`partners`\|`plan`, `index` (1-based) | A beat becomes the active step, including on back-navigation. | mobile |
| `team_review_exited` | `league_id`, `beat`, `index`, `outcome` ∈ `completed` \| `abandoned` | The screen unmounts. `completed` iff the user reached the `plan` beat. Exactly one row per `team_review_opened`. | mobile |
| `team_review_action_taken` | `league_id`, `beat`, `action` ∈ `outlook_set` \| `positions_set` \| `asset_pinned` \| `partner_scoped` | An action button on a beat commits. | mobile |

**(b) Existing events cover the two most important writes** — deliberately, rather than
duplicating them:

- `outlook_saved` (`ALLOWED_CLIENT_EVENTS`, property `source` ∈ `guide`\|`sheet`\|`strip`)
  — **extend the enum with `review`.** Beat B2's outlook write is the same write
  the guide and the Trade DNA sheet already make; a separate event would split
  the adoption series that already exists for exactly this question.
- `finder_target_pinned` (property `source`) — **extend with `review`.** Beat B4's
  pin is the same pin.

So B2 and B4 each emit **two** rows: the shared receipt (`outlook_saved` /
`finder_target_pinned`, with `source: "review"`) and `team_review_action_taken`
for funnel completeness within the flow.

**Intent classification — required in the same commit** (`analytics_queries.NON_INTENT_EVENTS`;
INTENT is a deny-list, so taxonomy growth is intent-by-default and an
unclassified impression event step-changes DAU on its ship date):

| Event | Class | Why |
|---|---|---|
| `team_review_beat_viewed` | **NON-INTENT** | An impression, peer of `league_pos_candidates_viewed` and `tab_selected`. The user already emitted `team_review_opened` to get here; admitting beat views would let one flow mint six user-days. |
| `team_review_exited` | **NON-INTENT** | A terminator, the `league_team_closed` / `quickset_abandoned` class. Every exit is preceded by an open, which is already intent. |
| `team_review_opened` | **INTENT** (absent from the deny-list) | The user asked for a read of their team. Peer of `find_trades_tapped` and `league_team_opened`. |
| `team_review_action_taken` | **INTENT** (absent from the deny-list) | It changes engine configuration. This is the strongest intent signal the feature produces. |

→ follow-through: `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS` +
the per-event property allowlist + the two `source` enum extensions),
`analytics_queries.NON_INTENT_EVENTS`, and a tracking-plan addendum at
`docs/feedback/items/357-team-review/analytics.md` — all in the **same commit
as the emitters**, per the CLAUDE.md common-tasks rule and the NULL-`platform`
lesson.

**Not stored beyond `user_events`** — no new analytics table, so
`docs/data-dictionary.md` needs no row for these.

---

## 2. Schema & flag scope

**New/changed tables or columns: none.** The feature reads existing tables and
writes `league_preferences` through the **existing** `POST /api/league/preferences`
route — no new write surface, no migration. → `docs/data-dictionary.md` **n/a**.

**New feature flags: one.**

| Flag | Default | Namespace rationale | OFF behavior | Graduation criterion |
|---|---|---|---|---|
| `trades.team_review` | **`false`** (dark) | `trades.*` is the client-surface namespace in the Trades tab (`trades.finder_hub`, `trades.presentation_v2`); `trade.*` is the engine. This is a client surface. | `GET /api/league/team-review` returns 404; the `TradesHome` entry card does not render; the route is not registered in `TradesStackNav`. Every existing generation and preference path is byte-identical. | Operator flips it after the TestFlight checklist (§3) passes on a real Sleeper league **and** one ESPN or MFL league (to exercise the degraded PPG card). |

→ `config/features.json` + `backend/feature_flags.py` `FLAG_KEYS` + `docs/config-reference.md`.

**New env vars / `model_config` keys: none.** The feature adds no tunable —
every threshold it displays (`infer_contender_cut`, `_STARTER_NEED`,
`_SURPLUS_AT`, tier bands) is an existing knob owned by the module that already
owns it. **Deploy-free rollback lever:** `trades.team_review` → `false` is the
kill switch, and it is a hot-reload (`POST /api/feature-flags/reload`), so
rollback needs no deploy and no client release.

---

## 3. Evidence scope

**D-056 applies** — no Maestro, no simulator, no `screens/` captures.

- [x] **Structural guard:** `mobile/tests/check-team-review.js` (dependency-free,
      plain node). **It gates CI the moment the file exists** — `.github/workflows/ci.yml`
      `mobile-typecheck` runs `for f in tests/check-*.js; do node "$f" || exit 1; done`,
      a glob, so no CI edit and no npm script are required. Add
      `npm run test:team-review` anyway, matching the 42 existing suites' convention.
      *(Note: root `CLAUDE.md` §Stack still says these suites are "`npm run`-only and
      gate nothing yet". That is **stale** — see Q-024.)* Pins:
      1. `TeamReviewScreen` is registered in `TradesStackNav` and **nowhere else**
         (a second registration would give it two entry stacks).
      2. `TeamReviewScreen` does **not** mount `FeedbackFAB` — it is a tab-stack
         screen and is already covered by `RootNav`'s global mount. A local mount
         is the #196/#197 double-FAB bug.
      3. The screen never renders a bare percentage for any odds figure and
         never references `title_pct` outside a comment — the band chip is the
         only permitted odds rendering ([D-094](../../../../living-memory/DECISIONS.md)).
         *(Amended 2026-08-19: this pin originally enforced "ships odds-free",
         which the operator's override retired. The band invariant itself is
         pinned separately and more thoroughly by the new
         `mobile/tests/check-outlook-bands.js`.)*
      4. Every beat id in the step array has a matching `testID` of the form
         `team-review.beat.<id>`.
      5. The entry card is **not** added to `TradeFinderModeBar`'s `CHIPS` array
         (pins §3's entry-point decision against drift).
- [x] **Unit tests (backend pytest):**
      - `backend/tests/test_team_review.py` — **new.** Payload shape; the
        preseason branch (`scoring: null`, `reason: "preseason"`); the
        non-Sleeper branch (`reason: "platform_unsupported"`, and **no**
        `NotImplementedError` escapes); `divergence_source` falls back
        `league_community` → `consensus_seed` → `null` as ranker count and board
        size drop; flag-off returns 404; `basis=personal` honors the P2.5 read
        gate; **`title_pct` and `playoff_pct` appear nowhere in the payload**
        (asserted over the serialized JSON, not the dict).
      - `backend/tests/test_analytics_taxonomy.py` — extend: the four new names
        are in `ALLOWED_CLIENT_EVENTS`, their property allowlists match §1, the
        two non-intent names are in `NON_INTENT_EVENTS`, and `review` is in both
        extended `source` enums.
      - **Sabotage proof required** (2026-08-10 lesson): each new behavioral
        assertion must be shown failing on a deliberately broken build before it
        counts. Named sabotages in [`prd.md` §7.3](prd.md).
- [x] **Code-walk proof:** `docs/feedback/items/357-team-review/code-walk.md`,
      written at build time. It must trace, file:line, the two claims no
      structural check can make: (1) that a `team_outlook` written from beat B2
      reaches trade generation and changes the deck — the chain from
      `POST /api/league/preferences` → `load_league_preference` →
      `trade.outlook_direction` / `classify_lane`; and (2) that the six-beat
      payload is assembled **without** importing `backend/outlook/`'s simulator,
      so a dark `outlook.odds` cannot affect it.
- [x] **Manual TestFlight checklist:** required — this is a new user-facing flow
      and the only runtime evidence mobile gets. Full numbered checklist in
      [`prd.md` §7.4](prd.md), covering: cold entry from the card, each beat's
      action committing and surviving a kill-and-relaunch, the preseason PPG
      card, the ESPN/MFL degraded card, the thin-board B4 skip, back-navigation
      mid-flow, and the B6 → deck hand-off actually changing the deck.
- **`testID`s added:** `team-review.entry-card`, `team-review.entry-dismiss`,
  `team-review.beat.standing` · `.window` · `.depth` · `.divergence` ·
  `.partners` · `.plan`, `team-review.next`, `team-review.skip`,
  `team-review.action.<action>`, `team-review.finish`. All must pass
  `mobile/scripts/testid-lint.sh` (still in CI).

**Capture delta: none, and it cannot be otherwise.** D-056 froze `screens/` at
2026-08-11. The design lab embeds the three real captures that exist and labels
every reconstructed frame — see the lab's §0 and the standing conflict recorded
in `mockups/CLAUDE.md`.

---

## 4. Docs scope (MANDATORY)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **must update at build** | New `GET /api/league/team-review`. Full contract in [`lld-delta.md` §2](lld-delta.md). |
| `living-memory/LLD.md` | **must update at build** | New convention: *a read-only aggregate route may compose existing service functions but must not import a flag-dark subsystem* (the rule that keeps Team Review independent of `outlook.odds`). |
| `docs/architecture.md` | **must update at build** | New backend module `backend/team_review.py` and its position in the data flow (composer over `power_rankings` / `trade_service` / `trends_service`). |
| `living-memory/HLD.md` | **must update at build** | A new client surface + a new composer module is a genuine shift, not a tweak — see [`hld-delta.md`](hld-delta.md). |
| `docs/cross-client-invariants.md` | **must update at build** | One new invariant: **Team Review beat order and beat ids** are a cross-client encoding (analytics `beat` property and `testID`s bind to them). Plus a pointer from § "Playoff outlook bands" naming beat `standing` as the designated seam for a future odds chip. |
| `docs/glossary.md` | **must update at build** | New terms: *Team Review*, *beat*, *window* (as distinct from the already-defined *team outlook mode*). |
| ADR or `DECISIONS.md` entry | **written this session** | **D-092** (the form + entry point + preference-write spine) and **D-093** (odds-free, `outlook.odds` stays dark, with lighting criteria). Plus **Q-025** (the three §6 waivers) and **Q-024** (the CLAUDE.md `check-*.js` staleness found while writing §3). No ADR — this is a feature shape, not a cross-cutting architectural rule. |

---

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (whose glob picks up
  `check-team-review.js` automatically — no job edit needed) +
  `maestro-testid-lint` — all passing on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the pytest
  file + pass count, the structural suite + which of its five pins fired under
  sabotage, and the code-walk doc.
- **TestFlight verification:** required (checklist written, §3). Operator-run;
  outcome logged in TEST_LEDGER before `trades.team_review` is flipped.
- **`githooks/pre-push`:** `FTF_SKIP_SIM_GATE=1` is the standing posture under
  D-056; note the evidence run in its place.
- **Express lane declared by the operator?** **No.** Bright-line change (route +
  flag + analytics), full gates.

---

## 6. Waivers — operator decision needed before build

Three, all surfaced rather than assumed:

1. **Forward per-player PPG is CUT from scope. — ✅ RATIFIED by the operator 2026-08-19 (*"Forward PPG cut"*).** #357's "here's 6 extra PPG this
   year" has no data source. `projection-source-research.md` evaluated every
   candidate: Sleeper's projections endpoint is undocumented with no commercial
   guarantee, FantasyPros' terms bar building a competing product, RosterAudit
   mandates an attribution backlink it revokes keys over, and NFLverse — the one
   license-clean option — ships historical and *retrospective* expected points,
   no forward projection, so "use nflverse" means building a projection model.
   **Ruling: cut, do not source, do not proxy.** What #357 gets instead is
   `starter_impact.slots[].before/after` with tier + positional rank
   (`trade.position_impact`, already ON) — a slot-by-slot read of what the trade
   does to the starting lineup. Waiver needed because it declines part of a
   tester's stated ask. *(If the operator instead wants the Sleeper projections
   feed spiked, that is its own scoped project — it is a new external dependency
   on a gray-ToS endpoint and belongs in `DEPENDENCIES.md`, not smuggled in
   here.)*
2. **Championship odds cannot be honored, at all. — STANDS (a notification, not a choice; unaffected by the `outlook.odds` lighting).** #357's "championship odds to
   Y" is `title_pct`, which `docs/cross-client-invariants.md` § "Playoff outlook
   bands" makes unrenderable at any week in any form — not a calibration
   judgement but an absence of skill (pooled skill +4.2%, 90% CI [−13.1%,
   +20.0%]; 3 of 6 backtested league-seasons worse than climatology; eight
   predictions above 0.4 containing one champion). No waiver can license it;
   this row exists so the operator sees the refusal rather than discovering it.
3. **Retrospective PPG rank is Sleeper-only and empty in preseason. — ⏳ STILL OPEN.** Jon's
   "you're sitting 6th in value and 11th in PPG this year" — the value half
   works everywhere, always. The PPG half needs `LeagueState.weekly_scores`
   (`backend/outlook/league_state.py:66,93`), which has a provider for Sleeper
   only (`league_state.py:295–320` raises for ESPN, MFL and Fleaflicker), and
   which is empty at `completed_weeks == 0` — i.e. **today**. **Ruling: ship the
   card in its degraded state** naming the actual reason, rather than hiding the
   row or gating the whole feature on Sleeper. Waiver needed because a tester
   asked for a number that most users will not see for the first six weeks of
   their exposure to this feature.

---

## 7. The `outlook.odds` call — LIT BY THE OPERATOR

**This section's original recommendation (keep it dark) was overruled on
2026-08-19.** The flag is now **`true`** in `config/features.json`; the reversal
is [D-094](../../../../living-memory/DECISIONS.md), superseding D-093. Full
reasoning, including the two objections of mine that turned out to be weaker than
stated, is in [`hld-delta.md` §5](hld-delta.md).

**Consequences for this scope block:**

- **§2 flag scope gains a second flag**, already flipped:
  `outlook.odds` `false` → **`true`**, with a comment block in
  `config/features.json` stating what the flip does and does not license.
  Deploy-free rollback via `POST /api/feature-flags/reload`; no client release
  needed, since the surface has shipped in every build since 2026-08-11.
- **§3 evidence gains a second structural guard**, already written and passing:
  `mobile/tests/check-outlook-bands.js` — 7 assertions, **all six sabotage cases
  proven red** before acceptance. It gates CI automatically via the
  `tests/check-*.js` glob.
- **The Maestro flow this lighting owed is waived** by the operator and was
  already void under D-056. `NEXT.md` item 7 is closed.
- **What did not move:** `title_pct` stays unrenderable and is no longer even
  serialized by Team Review; `playoff_pct` renders only as the three-band chip;
  `OUTLOOK_WEEK6_PERCENT_ENABLED` stays `false`.
- **Beat `standing` is no longer a "seam" — it is the live mount point** for the
  band chip. See [`lld-delta.md` §2](lld-delta.md) for the payload block and §8
  for the degradation matrix.
