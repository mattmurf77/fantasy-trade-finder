# Plan: Mock Draft for Rookie Drafts (+ Computer Drafter Logic)

**Date:** 2026-08-06 · **Status:** Reviewed 2026-08-06 (subagent draft; orchestrator verified all cited symbols against the tree and revised §4 constraint, §6.2 pick_share sourcing, §6.3 wording)
**Parents (normative):** [plan.md](plan.md) (FINAL, dual-agent converged) · [hld.md](hld.md) · [lld.md](lld.md). D1–D10, M0–M8, KD-*, I-*, RB-* references resolve to those documents. Nothing here re-opens a settled decision.

---

## 1. Summary

Let a user run a **simulated rookie draft for their real league**: the user makes their own team's picks; computer agents pick for every other team. CPU drafters are differentiated by a **persona derived from each team's outlook** (the existing `team_outlook` enum / `infer_team_outlook` inference): rebuild-leaning teams draft close to Best Player Available; contend-leaning teams reach 2–3 rookie-rank slots to fill positional needs. All personas run **one scoring function** with different parameters — no per-persona code paths.

**Scope clarification vs the parent plan.** plan.md §2 lists "mock drafts" as out of scope, defined there as *Sleeper's platform mock drafts* ("no league binding; used only as QA fixtures"). This feature is different and does not contradict that position: it is an **FTF-native simulation bound to a real league** — its rosters, its pick ownership (traded picks included), its outlooks. No platform draft is created, joined, or written (KD-7/D9 hold unchanged).

## 2. Dependencies on the rookie draft plan

This plan builds strictly on top of the parent milestones. Explicit dependencies:

| Depends on | What we consume | Hard/soft |
|---|---|---|
| **M0 — data foundation** | Fresh player cache; `load_rookie_player_ids(season)` as THE rookie predicate (I-2, `backend/database.py:6915`); the pool generation memo; the class-load state (`class_not_loaded`) | **Hard** — a mock over a stale/pre-load class is garbage-in |
| **M1 — fixture harness** | Draft corpora + replayer for tests (Lakeview, ffv3-predraft) | Hard for testing |
| **M3 — `draft_board_service.py`** | The `schema:1` vocabulary (`order[]`, `picks[]`, `undrafted[]`, `order_confidence`, `notice`); `_undrafted()` (D7 list = `rookie_year` − drafted − rostered, consensus- or my-board-ordered); the `kind: rookie|startup` classification; pre-draft ownership from `draft_picks` (divergence rule: pre-draft ownership truth) | **Hard** — the mock's board payload reuses I-6's shapes verbatim where applicable |
| **M4 — Draft Room UI** | The `DraftRoom` screen is the mock's entry point; the `FreeAgents` root-stack pattern incl. the `HeaderBack` iOS-26 workaround; the Consensus \| My-board `BasisChip` pattern | **Hard** — no separate Explore tile; mock lives inside the room |
| **M6 — slot values** | Optional display of slot values on mock picks | Soft — degrades to absent |
| Flags | `draft.room` must be ON for the entry point to exist; the new `draft.mock` flag is additionally required | Hard |

Also consumed from the wider codebase (verified in tree):
- **Outlook enum** — `league_preferences.team_outlook` ∈ `championship | contender | rebuilder | jets | not_sure` (`backend/database.py:643-655`, validated by `_VALID_OUTLOOKS`); resolved-vs-inferred precedence precedent in `mobile/src/screens/TradeFinderHubScreen.tsx:307-309` (`team_outlook ?? inferred_outlook`).
- **Outlook inference** — `trade_service.infer_team_outlook(roster_ids, players, pick_share, num_teams)` (`backend/trade_service.py:1531`): pure function, returns only `contender | not_sure | rebuilder` (extremes reserved for self-declaration — we keep that stance).
- **Outlook → weight map** — `trade_service.outlook_alpha(outlook)` (`:1314`) with config keys `outlook_alpha_championship=1.0 / _contender=0.75 / _not_sure=0.5 / _rebuilder=0.25 / _jets=0.1`. We reuse this exact map as the persona need-weight (see §6).
- **Lineup template** — `power_rankings.LINEUP_SLOT_ELIGIBILITY` (`backend/power_rankings.py:38`) + `optimal_starter_slots` (`:120`) + the league's `roster_positions` slot template (`server.py:15806` `_league_lineup_slots`-style filter) for positional-need computation.
- **Draft type** — Sleeper `draft.type` ∈ `linear | snake` (verified in `docs/feedback/items/207-rookie-draft-detection/research-platforms.md` §1.3; Lakeview rookie drafts are `linear`, the startup was `snake`).
- **Tier floors** — cross-client Elo bands (`docs/cross-client-invariants.md`): `third` floor 1280 is used as the "viable player" bar in need severity.

## 3. Product scope

**What a mock draft is (v1):** a turn-based, single-user simulation of the league's upcoming rookie draft. Order and per-slot ownership come from the real draft where known (traded picks included); the user is on the clock only for picks their team owns; every CPU pick resolves instantly server-side. No timer. The mock persists server-side so a backgrounded app or a Render cold boot doesn't lose it.

**User flow:**
1. Draft Room (M4) shows a **"Mock draft"** CTA when `draft.mock` is on and the board `kind == "rookie"` and the class is loaded.
2. Setup sheet: rounds (default = platform draft's rounds, else 4; range 1–8 per `ROOKIE_MAX_ROUNDS`), type (default = platform `draft.type`, else `linear`), order source (real order when `order_confidence == "assigned"`; otherwise randomized-and-labeled — never an invented "real" order, KD-6).
3. Server creates the mock, simulates CPU picks up to the user's first turn, returns the board.
4. On the clock: user sees the undrafted list (Consensus | My-board basis toggle, reusing M3's `basis` machinery) and taps a player to pick.
5. Repeat until complete → recap: full board, user's picks highlighted, per-pick "vs consensus rank" delta.

**In v1:** Sleeper + MFL leagues (anything M3 can produce a rookie board for) · one active mock per user per league · resume · abandon/restart · recap.
**Out of v1 (positions, not omissions):** pick trades during the mock · multi-user mocks · drafting for multiple teams · a pick timer · CPU pacing/animation delays (client may animate, server is instant) · undo (restart is the escape hatch — see O-M3) · persisting completed recaps beyond the single row · web/extension parity · startup-draft mocks (same label-and-suppress stance as the parent plan).

## 4. Data model

One new table (the parent plan's "no new tables" applies to *its* milestones; a resumable simulation is genuinely stateful — in-memory state dies on Render spin-down, which is a real event on the free plan per O8):

```python
# backend/database.py — mock_drafts
mock_drafts_table = Table("mock_drafts", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("user_id",    String,  nullable=False),
    Column("league_id",  String,  nullable=False),
    Column("season",     Integer, nullable=False),
    Column("status",     String,  nullable=False, default="active"),  # active | complete | abandoned
    Column("settings",   Text,    nullable=False),   # JSON, see below
    Column("picks",      Text,    nullable=False, default="[]"),  # JSON array, append-only
    Column("rng_seed",   Integer, nullable=False),
    Column("created_at", String),
    Column("updated_at", String),
)
```

- `settings` JSON: `{rounds, type: "linear"|"snake", order: [roster_id per slot], order_source: "assigned"|"randomized", ownership: {pick_no: roster_id}, personas: {roster_id: {outlook, source: "declared"|"inferred"|"default"}}, basis_teams, scoring_format}`. Ownership is snapshotted at creation (from the M3 pre-draft ownership overlay) so a mid-mock `draft_picks` resync can't shift picks under the user.
- `picks` JSON rows: `{pick_no, round, slot, roster_id, player_id, by: "user"|"cpu"}`.
- `rng_seed` makes CPU jitter deterministic **within** a mock (resume replays identically; two mocks differ). Per-pick RNG = `Random(rng_seed * 10_007 + pick_no)`.
- **One active mock per user+league is enforced in application code**, not a DB constraint: `POST /api/mock-draft` abandons any prior active row inside the same transaction before inserting. (A naive `UniqueConstraint(user_id, league_id, status)` would also block a second *abandoned* row; a partial unique index fixes that but is dialect-divergent across SQLite/Postgres — not worth it for a single-writer create path.)
- Docs: `docs/data-dictionary.md` new §`mock_drafts`.

No changes to `players`, `league_preferences`, `users`, or any parent-plan structure.

## 5. Backend design

**New flat module `backend/mock_draft_service.py`** (KD-1 convention — beside `draft_board_service.py`), pure logic with injected inputs so M1 corpora and unit tests drive it without HTTP:

```python
def create_mock(league_ctx, user_roster_id, settings, rng_seed) -> MockState
def advance_cpu(state, pool, needs, personas, rng) -> MockState   # runs CPU picks until user turn or complete
def apply_user_pick(state, player_id) -> MockState                # validates turn + eligibility
def cpu_pick(candidates_ranked, persona, needs_for_team, rng) -> player_id   # §6 — the scoring function
def positional_needs(roster_rows, lineup_slots) -> dict[pos, float]          # §6.2
```

**Routes** (thin shims in `server.py`, `_require_session`; every route 404s `{"error":"feature_disabled"}` unless `is_enabled("draft.mock")` — repo convention):

| Route | Does |
|---|---|
| `POST /api/mock-draft` `{league_id, rounds?, type?}` | Creates (abandoning any prior active mock for that user+league), resolves order/ownership/personas, advances CPU to the user's first turn, returns state. `400 {"error":"not_rookie_draft"}` when the M3 board's `kind != "rookie"`; `200 {empty:true, reason:"class_not_loaded"}` mirrors M2's typed-empty. |
| `GET /api/mock-draft?league_id=` `&basis=consensus\|my_board` | Active (or most recent complete) mock state. |
| `POST /api/mock-draft/pick` `{mock_id, player_id}` | Validates it's the user's turn and the player is undrafted+in-class; appends the pick; advances CPU; returns state. `409 {"error":"not_your_turn"}` / `400 {"error":"player_unavailable"}`. |
| `POST /api/mock-draft/abandon` `{mock_id}` | Marks abandoned. |

**State payload** reuses I-6 vocabulary: `{schema:1, mock_id, status, on_the_clock: {pick_no, round, slot, roster_id, is_user}, order[], picks[], undrafted[], my_picks[], settings_echo, notice}` — same entry shapes as `GET /api/draft/board` (`order[]`/`picks[]`/`undrafted[]` fields per lld.md §2.1) so the mobile client reuses the M4 rendering components. `undrafted[]` honors D7 verbatim: unvalued rookies are shown ("no consensus value"), never dropped — CPU drafters simply rank them last.

**Draft loop mechanics:**
- **Turn order:** slot order from settings; `snake` reverses even rounds; ownership map (traded picks) resolves `pick_no → roster_id` on top of the slot order — a team can be on the clock twice in a row.
- **User pick vs CPU pick:** strictly turn-based, no timer. `advance_cpu` loops CPU picks synchronously (each pick is an argmin over ≤ ~10 candidates — microseconds; a full 60-pick CPU tail is trivially cheap on the single worker) and stops at the first user-owned pick or the end.
- **Pool:** `load_rookie_player_ids(season)` − already-rostered − picks made in *this mock*. Consensus order = the same seed-Elo/DP ordering `_undrafted()` uses. Generic pick rungs (O10) are **excluded** from the mock pool — a mock drafts players, not rungs.
- **CPU basis is always consensus.** The user's `my_board` Elo never leaks into opponents' decisions (it would make every mock a mirror of the user's own opinions); `basis=my_board` affects only how the *user's* undrafted list is sorted.
- **No platform reads during the mock** beyond the create-time snapshot; the mock is self-contained after creation (no polling, no TTL, no budget interaction with M3's cache).

## 6. Computer drafter methodology (the heart)

### 6.1 One scoring function, persona = parameters

For the CPU team `t` on the clock, over the top `K = ceil(max_reach) + 5` undrafted candidates by consensus rank (rank is 1-based over the current pool):

```
score(c) = rank(c) − need_bonus(t, pos(c)) − jitter(c)
pick     = argmin score          (ties → better consensus rank)

need_bonus(t, pos) = need_weight(t) × severity(t, pos) × MOCK_MAX_REACH   # rank-slot units
jitter(c)          = rng.uniform(0, MOCK_JITTER_SLOTS)
```

- `need_weight(t) = outlook_alpha(persona_outlook(t))` — **the existing map, reused verbatim** (`outlook_alpha_*` model_config keys). This is the single knob that makes contenders needs-drafters and rebuilders BPA-drafters; it is already operator-tunable and already documented.
- `MOCK_MAX_REACH` (new `model_config` key, default **3.0**) caps the reach structurally: `need_bonus ≤ 1.0 × 1.0 × 3 = 3` rank slots, ever. A championship team with a desperate need reaches up to 3 slots; a contender up to 2.25; a rebuilder up to 0.75 (~BPA with a nudge); jets up to 0.3 (~pure BPA). This satisfies the "reach 2–3 slots" product bar with **no separate code path per persona**.
- `MOCK_JITTER_SLOTS` (new key, default **1.25**): uniform noise per candidate so mocks aren't deterministic across runs — enough to occasionally swap adjacent ranks, never enough to produce a 5-slot howler. Drawn from the per-pick seeded RNG (§4) so a resumed mock replays identically.
- Unvalued rookies (D7 tail) sit after all valued ranks; a CPU team only reaches them when the valued pool is exhausted.

### 6.2 Persona assignment from team outlook

Per team at mock creation, precedence mirrors the Hub's resolved-outlook rule:

1. **Declared:** that roster's FTF user has a `league_preferences.team_outlook` row for this league (only exists for leaguemates who use FTF).
2. **Inferred:** `infer_team_outlook(roster_ids, players, pick_share, num_teams)` — yields `contender | not_sure | rebuilder` only (extremes stay self-declared, per its stated design). The `pick_share` input per CPU team comes from the existing opponent-pick-share computation (`server.py:4113-4132` builds `opponent_pick_shares` from `draft_picks` totals; the user's own comes from `_user_pick_share`, `server.py:3979`) — reuse that machinery at mock creation, don't re-derive it.
3. **Default:** `not_sure`.

The persona (outlook + source) is snapshotted into `settings.personas` and shown in the UI (e.g. a small "rebuilder · inferred" line on the team header) so CPU behavior is explainable.

| Outlook | Reads as | `need_weight` (= `outlook_alpha`) | Max effective reach (× 3.0) | Behavior |
|---|---|---|---|---|
| `jets` | tanking | 0.10 | 0.3 slots | Pure BPA (jitter dominates) |
| `rebuilder` | rebuilding | 0.25 | 0.75 slots | BPA with a whisper of need |
| `not_sure` | unknown/default | 0.50 | 1.5 slots | Mild need lean |
| `contender` | contending | 0.75 | 2.25 slots | Clear need drafter |
| `championship` | all-in | 1.00 | 3.0 slots | Max need drafter |

Tuning any of this is `model_config`, not code: the `outlook_alpha_*` keys already exist; `mock_max_reach_slots` and `mock_jitter_slots` are the only new keys (documented in `docs/config-reference.md` §model_config).

### 6.3 Positional need severity

The **inputs** (`S`, `B`, and the roster-derived `viable` counts) are computed once per team at mock creation — the platform roster doesn't change mid-mock. The **severity** itself is cheap arithmetic re-evaluated at each of that team's picks, with one mutation: after team `t` drafts pos `p` in the mock, `viable(t, p) += 1`, so its severity at `p` drops and the team doesn't triple-tap RB:

```
S(pos)      = count of DEDICATED starter slots for pos in the league's
              roster_positions template (LINEUP_SLOT_ELIGIBILITY keys;
              flex slots excluded from S — v1 simplification, see O-M5)
B(pos)      = bench target: 1 for RB/WR; 1 for QB iff superflex (sf_tep);
              0 for TE and 1QB-league QB
viable(pos) = count of team players at pos with consensus Elo ≥ 1280
              (the `third` tier floor — "worth a 3rd or better";
              roster-clogging depth doesn't count)

severity(pos) = clamp01( (S(pos) + B(pos) − viable(pos)) / (S(pos) + B(pos)) )
```

Examples (12-team, QB/2RB/3WR/TE/2FLEX template): a team with zero viable RBs → RB severity `(2+1−0)/3 = 1.0`; with two viable RBs → `0.33`; a 1QB team with one decent QB → QB severity `(1+0−1)/1 = 0` (CPU won't reach for QBs in 1QB — emergent, not special-cased). Positions are only ever QB/RB/WR/TE (the pool's universe).

Severity uses **consensus** values (`dynasty_value`/seed Elo — the same signals `infer_team_outlook` uses), never any user's board.

### 6.4 Worked example

Contender (`need_weight 0.75`), RB severity 1.0, on the clock; pool ranks: 1 WR, 2 WR, 3 RB, 4 TE.
`need_bonus(RB) = 0.75 × 1.0 × 3 = 2.25` → RB3 scores `3 − 2.25 = 0.75` vs WR1's `1.0` (before jitter) → the RB goes 2 slots early. The same board under a `rebuilder` (`0.25 × 3 = 0.75`): RB3 scores `2.25` vs WR1's `1.0` → BPA holds. That is the entire differentiation mechanism.

## 7. Mobile UI sketch

Chalkline throughout (`docs/design/design-system.md` + `components.md`; ADR-004/005): no emoji icons, no gradients, radius ≤ 8px, **ice** for the pick action/CTA, **flare** only for informational highlights (e.g. "on the clock" marker, reach/value deltas in the recap); position and tier hexes are data encodings per `cross-client-invariants.md` and are not restyled.

- **Entry:** inside `DraftRoomScreen` (M4) — a "Mock draft" CTA row when `draft.mock` is on, `kind == "rookie"`, class loaded. Resumes the active mock if one exists ("Resume mock — pick 2.04").
- **Setup sheet:** modal sheet (no FeedbackFAB, per the modal exception): rounds stepper, linear/snake toggle (pre-filled from the platform draft), an "order randomized" notice when `order_confidence != "assigned"` (honest-state rule, KD-6).
- **`MockDraftScreen`:** root-stack push route registered in `mobile/src/navigation/RootNav.tsx` copying the `FreeAgents` block *including the `headerBackVisible:false` + custom `HeaderBack` workaround* (lld.md §4.5); mounts `<FeedbackFAB activeScreen="MockDraft" aboveTabBar={false} />` (#188 rule). Layout: sticky "on the clock" header (team name, persona line, pick number) · pick ticker (last few picks) · undrafted list with the `BasisChip` Consensus | My-board toggle (M4's component) and position filter chips · tapping a row when the user is on the clock shows a confirm affordance, then `POST /pick`. When a CPU run resolves several picks at once the client animates them in sequence (client-side pacing only).
- **Recap state:** same screen, `status == "complete"`: full board grouped by round, user's picks ice-accented, per-pick `consensus rank − pick_no` delta ("+2 value" / "reached 1") as flare-tinted informational text. "Run it back" (restart) and Done.
- **No new global state:** TanStack query keyed `['mock-draft', leagueId]`, refetch on mutation responses only — **no polling** (the mock only changes when the user acts, so this screen never touches the RV-8 `refetchInterval` machinery).

## 8. Feature flag & rollout

- **One new flag: `draft.mock`**, default OFF, full 4-touch convention (lld.md §6.1: `feature_flags.FLAG_KEYS` + `config/features.json` + `backend/tests/fixtures/flags/release.json` + `docs/config-reference.md`), plus a flag-off test (404, no other route changed).
- Effective gating: entry renders only when `draft.room` AND `draft.mock`. `draft.mock` does not depend on `draft.live_poll` (no polling), `draft.mfl` live mode, or `picks.slot_values`.
- **Sequencing:** builds after M3 lands (payload vocabulary + `_undrafted`) and after M4's first batch (screen patterns). Call it **M9 — Mock draft** to keep the parent numbering intact: M9a backend (table + service + routes + tests, 1 batch) → M9b mobile (screen + setup + recap, 1 batch) → M9c polish (persona display, recap deltas, Maestro, 1 batch). `server.py` single-writer rule applies (plan §4): M9a must not run concurrently with any other server.py wave.
- **Rollout:** operator-only first via the tester allowlist (the `onboarding_v2_rollout` precedent), then wide. Kill = flag off; no data migration risk (the table is additive; rollback leaves orphan rows, harmless).
- **Docs to touch:** `data-dictionary.md` (table) · `api-reference.md` (new `## Mock draft (flag draft.mock)` section) · `config-reference.md` (flag + `mock_max_reach_slots` / `mock_jitter_slots`) · `glossary.md` ("Mock draft", "Drafter persona", "Need severity") · this folder's status files per the plans protocol.

## 9. Testing plan

`backend/tests/test_mock_draft.py` (run per lld.md §7: `python3 -m pytest backend/tests/`, human gate, expected-count stated at exit):

| ID | Proves |
|---|---|
| T-M9-01 | Flag off ⇒ every mock route 404s `feature_disabled`; no other route's response changes |
| T-M9-02 | Snake vs linear turn order; ownership map (traded picks) puts the right roster on the clock, incl. back-to-back picks |
| T-M9-03 | `cpu_pick` reach cap: with `need_weight=1.0`, `severity=1.0`, jitter zeroed, the needed-position player is taken at exactly ≤ `mock_max_reach_slots` slots early — and never earlier |
| T-M9-04 | BPA persona: `jets` over 500 seeded draws never deviates > 1 slot from consensus with default jitter |
| T-M9-05 | Determinism: same `rng_seed` ⇒ identical full CPU draft; different seeds ⇒ different (statistically) |
| T-M9-06 | Need severity table: the §6.3 examples verbatim (0-viable-RB ⇒ 1.0; 1QB-with-QB ⇒ 0.0; superflex B(QB)=1) |
| T-M9-07 | Persona resolution precedence: declared > inferred > `not_sure`; inference never yields `championship`/`jets` |
| T-M9-08 | Per-team need decrements after that team's pick (no RB triple-tap under full jitter=0 severity) |
| T-M9-09 | User pick validation: `not_your_turn` 409; `player_unavailable` 400 (drafted-in-mock and already-rostered both) |
| T-M9-10 | D7 in the mock pool: unvalued rookies present, ranked last, CPU-draftable only after valued pool exhausts |
| T-M9-11 | Resume: reload mid-mock from the row ⇒ identical state; abandon ⇒ create allows a fresh mock |
| T-M9-12 | `kind != "rookie"` (startup corpus) ⇒ `not_rookie_draft`; class-not-loaded ⇒ typed `200 {empty:true}` |
| T-M9-13 | Zero platform egress after creation (fixture-seam counters, the T-M1-01 pattern) |

Mobile: Jest for the confirm-to-pick flow and the no-polling guarantee (zero refetches while idle — instrumented, not assumed); Maestro flow: setup → three user picks → recap renders (pinned `FTF_TEST_MODE` cache + a seeded mock, fixed `rng_seed` via a test-only query param or model_config).

## 10. Open questions

- **O-M1 — Should CPU teams consider `acquire_positions`/`trade_away_positions`?** `league_preferences` already carries declared position intent. A cheap add: `severity(pos) = max(severity, 0.7)` for a declared acquire position. Recommend YES for declared-persona teams only (data already there, one line), NO for inferred.
- **O-M2 — Persist completed recaps?** v1 keeps only the latest row per user+league. History ("my last 5 mocks") is a possible V1.5; the table shape already supports it (drop the one-active constraint semantics).
- **O-M3 — Undo last user pick?** Recommend NO for v1 (restart is the escape hatch); undo requires replaying CPU picks after the undone pick with the same seed, which the per-pick RNG actually makes trivial — revisit on feedback.
- **O-M4 — Should the user be able to force a persona per team** ("my rival always reaches for QBs")? Fun, but adds a settings surface; defer.
- **O-M5 — Flex slots in `S(pos)`:** v1 excludes flex from severity. If contenders under-reach for WR in 3-flex leagues, add fractional flex credit (`+ flex_count × 1/len(eligible_positions)`) as a tuning pass, not a redesign.
- **O-M6 — MFL leagues at launch:** M3's MFL board (M5) is fixture-tested but its live latency is unverified; the mock only needs the create-time snapshot, so MFL mocks should work whenever the M5 board does. Confirm during M9a QA rather than gating on `draft.mfl` live mode.
- **O-M7 — `not_rookie_draft` for leagues with no draft object at all:** a dynasty league between drafts has next season's picks but maybe no platform draft. Recommend: allow the mock anyway (order = randomized-and-labeled, rounds = 4 default) — the whole point is simulating a draft that hasn't been scheduled yet. Needs an operator call because it widens the create path beyond the M3 board states.
