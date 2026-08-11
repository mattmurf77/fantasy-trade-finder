# LLD — P0-7 · Analytics blindness (taxonomy · server send-leg · client instrumentation)

> **Code-level design. Binding parent:** [`hld.md`](hld.md) — §1.2 Spine B, §2 S-12 /
> S-18 / S-23 / S-30…S-38, §3 commits 1 · 5 · 9 · 10 · 13, §4 W0-TAX + W1-BE + W2-P07,
> §7, §8 R3/R4/R11/R12, §9 LLD-6, §10.1/§10.2.
> **Source plan:** [`plan-p0-7.md`](plan-p0-7.md) · scope block [`scope-p0-7.md`](scope-p0-7.md).
> **PRD twin:** [`prd-p0-7.md`](prd-p0-7.md).
>
> Organised **by executing agent**, because P0-7 is the only finding in this batch that
> spans three waves. Each §W section is a self-contained work order: an agent should be
> able to build its section without reading the other two.
>
> **Every line number below was re-read in this worktree.** They are anchors for a
> `grep`, not coordinates — per §8 R1, re-grep before editing. Where a number is
> load-bearing (P0-6's granted ranges) that is stated explicitly.

## Contents

- [0. Corrections this LLD carries forward from the HLD](#0-corrections-this-lld-carries-forward-from-the-hld)
- [1. §W0-TAX — the taxonomy registration commit (commit 1)](#1-w0-tax--the-taxonomy-registration-commit-commit-1)
- [2. §W1-BE — the server send-leg (commit 5)](#2-w1-be--the-server-send-leg-commit-5)
- [3. §W2-P07 — client instrumentation (commits 9, 10, 13)](#3-w2-p07--client-instrumentation-commits-9-10-13)
- [4. Handoff notes — one-line props in files this LLD does not own](#4-handoff-notes--one-line-props-in-files-this-lld-does-not-own)
- [5. Verification — how each event is proven to land](#5-verification--how-each-event-is-proven-to-land)
- [6. Deviations](#6-deviations)

---

## 0. Corrections this LLD carries forward from the HLD

Four things in `plan-p0-7.md` do not survive the HLD's reconciliation. They are stated
here once so no build agent re-derives the plan's version.

| # | The plan says | This LLD builds |
|---|---|---|
| C-1 | §9.3 step 1 implies wiring/adding navigation instrumentation to prove `screen_viewed` | **`screen_viewed` is already emitted** — `RootNav.tsx:352` (`onReady`) and `:376` (`onStateChange`, which covers tab switches because `getCurrentRoute()` returns the deepest active route). It is already in `ALLOWED_CLIENT_EVENTS` (`analytics_taxonomy.py:40`) **and** already in `NON_INTENT_EVENTS` (`analytics_queries.py:61`). §9.3 becomes a **verification step** (§5.4). **No emission is added, no file is touched for it.** (HLD §10.1, S-38.) |
| C-2 | §6 F1 asserts `experiment_exposed` is needed but never says where it fires | The emission site is designed by HLD §9 LLD-6 and specified in **§3.5** below: provenance recorded in `api/flags.ts` during the `configs[*].flags` merge; **deferred** emit from `useFeatureFlags` on first consumption of an overlaid key, once per key per session, **never during render**. |
| C-3 | §4 change list rows 11-13 have P0-7 editing `TradesScreen.tsx`, `TradeCard.tsx`, `InLeagueCalculator.tsx` | Those three one-liners are **applied by other agents** (HLD §4 contention table). W2-P07 supplies them as specs — §4 below. W2-P07 opens none of those three files. |
| C-4 | §4 registers 8 client names; §3 commit table in the HLD says "12 client names" | The authoritative list is **HLD §4 Wave 0**: **15 client names + 1 server name**. The HLD's own §3 row is stale arithmetic; §4 enumerates every name. §1.1 below is the enumeration. |

Two further settled points that shape code below: **`is_self` is omitted** from
`league_team_opened` (S-33 — identity was never proven, and a guessed prop is worse than
a missing one), and **`sleeper_send_succeeded` must not be added to
`database._EVENT_TO_USER_COL`** (S-34 — that map drives notification gating off
`last_trade_proposed_at`). Verified: it is absent today (`database.py:2516-2532`), so the
requirement is "change nothing", not "remove something".

---

## 1. §W0-TAX — the taxonomy registration commit (commit 1)

**Agent:** W0-TAX. **Files (exclusive):** `backend/analytics_taxonomy.py`,
`backend/analytics_queries.py`, `backend/tests/test_events_api.py`,
`backend/tests/test_analytics_p0.py`,
`docs/business/analytics/2026-08-11-p0-7-addendum.md` (new).
**No other commit in this batch may open either registry file** (S-36).

This commit registers names for events that **do not exist yet**. That is the point: the
allowlist is default-deny behind a 200 (`analytics_ingest.py:379-383` bumps
`dropped_unknown_type` and returns success), so a name registered ahead of its emitter is
inert, while an emitter ahead of its name is a silent data loss with a green dashboard.

### 1.1 `backend/analytics_taxonomy.py` — `ALLOWED_CLIENT_EVENTS`

Append **one commented block** immediately before the closing `})` of the frozenset
(today's last entry is `"espn_connect_abandoned",` at `:98`). Fifteen names:

```python
    # ── P0 remediation batch, 2026-08-11 ────────────────────────────────
    # Plans: docs/plans/audit-p0-remediation/{hld,lld-p0-7,plan-p0-7}.md.
    # Tracking-plan addendum (the precondition line 9-10 demands):
    # docs/business/analytics/2026-08-11-p0-7-addendum.md.
    #
    # REGISTERED BEFORE ANY EMITTER SHIPS. This registry is default-deny
    # behind a 200 (analytics_ingest.py:379-383 counts + drops), so a name
    # that lands after its track() call is a silent data loss with a
    # success-shaped response. Three instances of exactly that already
    # exist in this tree: the NULL-`platform` incident, `invite_shared`
    # (below), and `celebration_fired`.
    #
    # `tab_selected`, `league_view`, `experiment_exposed` and
    # `quickset_abandoned` are ALSO added to
    # analytics_queries.NON_INTENT_EVENTS — INTENT is a deny-list, so
    # without that these impression-class names would step-change DAU/WAU
    # on ship day and break every retention series at that seam.
    #
    # P0-7 — navigation + League surfaces (mobile only; web and the
    # extension fire none of these).
    "tab_selected",
    "league_view", "league_basis_changed", "league_subset_changed",
    "league_team_opened", "league_home_action_tapped",
    # P0-7 — Send in Sleeper. The ATTEMPT and the FAILURE are client-only
    # signals: a tap that never reaches the server, a network/timeout
    # error, and the pre-identity refusals (feature_disabled, no_user,
    # test_mode_propose_disabled) the server cannot attribute to a user.
    # The SUCCESS is server-fired — see SERVER_FIRED_EVENTS below.
    "sleeper_send_attempted", "sleeper_send_failed",
    # P0-3 — the invite loop. `invite_shared` is NOT new: it has been
    # fired by InviteLeaguematesBanner.tsx:47 since it shipped and dropped
    # on the floor every time, which is why "the invite loop converts
    # zero" has never actually been measurable. Registering it is a bug
    # fix, not an addition.
    "invite_shared", "invite_link_opened", "invite_league_pinned",
    "invite_pin_failed",
    # P0-7 §6 F1 — exposure, not assignment. `experiment_exposed` is
    # already in FUNNEL_CRITICAL (line 146) and in the mobile SDK's mirror
    # (events.ts:70) but was NEVER in this allowlist, so anything that
    # fired it was dropped: a live instance of this file's own trap.
    # backend/experiments.py:620,723 uses assignment as an exposure proxy
    # and reports the dilution; every A/B read is diluted until this lands.
    "experiment_exposed",
    # P0-7 §6 F3/F4 — the Quick Set per-rung drop-off curve. quickset_
    # completed is server-fired PER COMPLETED POSITION, so a user who does
    # three rungs of QB and quits is invisible today. quickset_step_
    # advanced stays INTENT (it is real ranking intent); quickset_
    # abandoned is an outcome/impression signal and is NON_INTENT.
    "quickset_step_advanced", "quickset_abandoned",
```

**Count check (build agent must assert this by eye before committing): 15 names.**
`tab_selected` · `league_view` · `league_basis_changed` · `league_subset_changed` ·
`league_team_opened` · `league_home_action_tapped` · `sleeper_send_attempted` ·
`sleeper_send_failed` · `invite_shared` · `invite_link_opened` ·
`invite_league_pinned` · `invite_pin_failed` · `experiment_exposed` ·
`quickset_step_advanced` · `quickset_abandoned`.

### 1.2 `backend/analytics_taxonomy.py` — `SERVER_FIRED_EVENTS`

One name, inside the existing `# Trades` block (`:112-115`), after `"trade_match",
"trades_generated", "calc_trade_evaluated",`:

```python
    # P0-7 — the north-star SEND leg. analytics_queries.WAT_DARK reserved
    # these three names on 2026-07-17 and nothing ever fired them;
    # FUNNEL_STAGES stage 8 and FEATURE_VERTICALS["send_in_sleeper"]
    # already reference this exact string and light up on their own.
    # SERVER-fired because POST /api/trades/propose is the only place the
    # send is KNOWN to have landed in Sleeper — a client-forgeable success
    # would sit in WAT and funnel stage 8 next to server-authoritative
    # trade_ratified. NOT added to database._EVENT_TO_USER_COL: bumping
    # last_trade_proposed_at would change notification gating, which is
    # out of scope for an instrumentation item (hld.md S-34).
    "sleeper_send_succeeded",
```

### 1.3 `backend/analytics_taxonomy.py` — `CLIENT_EVENT_PROPS`

**One row per new client name, all fifteen.** A missing row raises `ValueError` at
import (`:327-332`) and the app does not boot — loud, but it means "half of this commit"
is not a shippable state.

```python
    # ── P0 remediation batch, 2026-08-11 ────────────────────────────────
    # NOTE `platform` on league_view is the LEAGUE platform (sleeper /
    # espn / mfl / fleaflicker), matching league_selected's precedent
    # above. It is NOT the device platform — that is a user_events COLUMN
    # derived server-side in analytics_ingest.py:365-368 from the batch
    # body / X-Device headers (the NULL-`platform` incident). No event in
    # this block carries a device-platform prop, and the prop-stripping
    # test in test_events_api.py pins that.
    "tab_selected":            frozenset({"tab", "from_tab", "refocus",
                                          "intercepted"}),
    "league_view":             frozenset({"surface", "state", "platform",
                                          "team_count", "basis", "subset",
                                          "starters_available",
                                          "outlook_shown", "is_tab_root"}),
    "league_basis_changed":    frozenset({"basis", "from", "boards_differ",
                                          "team_focused"}),
    "league_subset_changed":   frozenset({"subset", "from", "source",
                                          "filter_count", "picks_stripped"}),
    # `is_self` is deliberately ABSENT (hld.md S-33): session-user ↔
    # PowerRankedTeam.user_id identity was never proven, and a guessed
    # prop is worse than a missing one. Adding it later is a one-line
    # taxonomy change plus one client line — do that only with the
    # identity proven.
    "league_team_opened":      frozenset({"via", "rank", "basis", "subset",
                                          "filter_count"}),
    "league_home_action_tapped": frozenset({"action"}),
    "sleeper_send_attempted":  frozenset({"surface", "give_n", "receive_n",
                                          "from_deck", "has_target"}),
    # `error_code` is a CLOSED enum: the 12 server codes of
    # /api/trades/propose plus network | timeout | unknown. 15 values,
    # forever. `kind` is SleeperWriteError.kind, present only on
    # sleeper_rejected / sleeper_write_failed.
    "sleeper_send_failed":     frozenset({"surface", "error_code", "status",
                                          "kind", "give_n", "receive_n",
                                          "from_deck"}),
    # P0-3 invite loop. `league_id` is a Sleeper/platform league id, not a
    # person; no user identifier rides in any of these four.
    "invite_shared":           frozenset({"league_id"}),
    "invite_link_opened":      frozenset({"league_id", "has_ref", "format",
                                          "auth_state"}),
    "invite_league_pinned":    frozenset({"league_id", "source",
                                          "ms_since_open"}),
    "invite_pin_failed":       frozenset({"league_id", "reason"}),
    # `unit` (account|device) is registered but NOT emitted today: the
    # client cannot derive it — GET /api/feature-flags returns the merged
    # experiments/configs maps without the unit_type that
    # experiments.resolve_for_unit knew server-side. Registered now so
    # adding it later is a server change alone, never a taxonomy change.
    # `key` is the flag key whose first consumption triggered the
    # exposure, which is what makes an exposure auditable back to a
    # surface.
    "experiment_exposed":      frozenset({"experiment", "variant", "unit",
                                          "key"}),
    "quickset_step_advanced":  frozenset({"position", "tier_index",
                                          "tier_count", "seeded_accepted",
                                          "picked_n", "via", "ms"}),
    "quickset_abandoned":      frozenset({"position", "tier_index",
                                          "tiers_done", "ms", "reason"}),
```

**Disjointness — pre-verified, do not re-litigate at build time.** None of the fifteen
appears in `SERVER_FIRED_EVENTS`, `_EVENT_TO_USER_COL` (`database.py:2516-2532`, read in
full) or `_RANK_STREAK_EVENTS`. `sleeper_send_succeeded` is server-only and must **not**
be added to the client allowlist — that pairing is precisely what
`_assert_namespaces_disjoint` (`:298-322`) exists to crash on.

**`FUNNEL_CRITICAL` — no change.** `experiment_exposed` is already there (`:146`); the
other fourteen are not pre-auth funnel primitives. Do not add any of them: growing
`FUNNEL_CRITICAL` changes the SDK's overflow drop policy, and the SDK's hand-mirror
(`events.ts:70`) would then be out of sync.

### 1.4 `backend/analytics_queries.py` — three edits, all metric-integrity

**(a) `NON_INTENT_EVENTS` (`:60-63`) — mandatory, not a nicety (S-32).**

```python
NON_INTENT_EVENTS = frozenset({
    "app_opened", "app_backgrounded", "app_open", "screen_viewed",
    "push_sent", "client_error", "api_call", "api_request",
    # P0 remediation 2026-08-11 — impression / navigation / outcome class.
    # INTENT is a deny-list (see INTENT_EVENTS below), so taxonomy growth
    # is intent-by-default: without these four lines, a tab tap and a
    # League mount would make DAU/WAU ≈ app-open count from ship day and
    # every retention and churn series would break at that seam,
    # permanently and silently. Seam date is recorded in
    # docs/business/analytics/2026-08-11-p0-7-addendum.md.
    "tab_selected", "league_view", "experiment_exposed",
    "quickset_abandoned",
})
```

The other eleven new names **stay INTENT deliberately**: a basis toggle, a subset
switch, a team drill-in, a League-home exit tap, a send attempt/failure, an invite share
or pin, and a Quick Set rung advance are all a user acting on the product. That produces
a genuine, desirable step in WAU — a league-browsing or invite-sending user now counts —
and the addendum records it so the step is read as designed rather than as drift.

**(b) `WAT_LIVE` / `WAT_DARK` (`:49-54`).**

```python
# North star — Weekly Active Traders. The send leg went LIVE 2026-08-11
# (P0-7): historical rows carry none of these names, so past WAT is
# unchanged and only the forward series gains the leg.
WAT_LIVE = frozenset({"trade_proposed", "match_swiped", "calc_trade_evaluated",
                      "sleeper_send_attempted", "sleeper_send_succeeded",
                      "sleeper_send_failed"})
WAT_DARK = frozenset()
WAT_EVENTS = WAT_LIVE | WAT_DARK
```

`WAT_EVENTS` keeps its definition and its value. Grep for other readers of `WAT_DARK`
before committing — at time of writing the only ones are this module's own
`WAT_EVENTS` and the caveat in (c).

**(c) The unconditional dark caveat — delete it.** Today, inside the engagement report
(`analytics_queries.py:497-498`), this line runs on **every** call regardless of data:

```python
    caveats.append(_dark_caveat("metric:wat.sleeper_send",
                                "send-leg WAT events not in taxonomy yet; WAT = trade_proposed/match_swiped/calc_trade_evaluated only"))
```

Its text — *"send-leg WAT events not in taxonomy yet"* — becomes **false the moment §1.1
and §1.2 land**, and a comment that contradicts runtime is the A-33 failure class this
batch is trying to stop repeating. **Delete both lines.** No conditional replacement is
needed: the honest-degradation machinery two lines above already does the job —
`wat_dark = is_dark(conn, WAT_LIVE, start_day, end_day)` now includes the three send
names in `WAT_LIVE`, so a window with no send rows still renders `{"value": None, "n":
None, "caveat": "dark"}` per week. Replacing one unconditional string with a second
`is_dark()` call would re-query for a caveat the row-level `caveat: "dark"` already
carries.

`FUNNEL_STAGES` stage 8 (`:79`) and `FEATURE_VERTICALS["send_in_sleeper"]` (`:95`) need
**no edit** — both already name `sleeper_send_succeeded` and light up on their own once
rows exist. Delete the trailing `# dark` comment on `:95` in the same pass.

### 1.5 `docs/business/analytics/2026-08-11-p0-7-addendum.md` (new)

Shape follows `2026-08-06-draft-room-w1-addendum.md` verbatim: parent link to tracking
plan v2 §S3, the default-deny paragraph, "Why now", the event table, and a **"What is
deliberately NOT here"** section. Six things it **must** record, because each is a
decision that a future analyst would otherwise have to reverse-engineer:

1. **The `sleeper_send_*` naming decision (S-30)** — chosen over `06-resolutions.md`'s
   `send_in_sleeper_*` because `WAT_DARK`, `FUNNEL_STAGES` stage 8 and
   `FEATURE_VERTICALS["send_in_sleeper"]` already reserved these exact strings.
2. **The league-`platform` vs device-`platform` distinction** — `platform` on
   `league_view` is `sleeper|espn|mfl|fleaflicker|unknown`; device platform is a
   `user_events` **column**, never a prop.
3. **The DAU/WAU seam date (2026-08-11)** — which four names are NON_INTENT, which
   eleven are INTENT, and that the INTENT eleven produce a real, expected step in WAU.
4. **`invite_shared` has been firing into a default-deny wall since it shipped**
   (`InviteLeaguematesBanner.tsx:47`). Every invite-funnel claim predating this commit
   rests on zero rows.
5. **The "deliberately NOT here" list** — position-filter pills; drill-in close/dwell;
   the Send confirm-dialog cancel; the `validateTradeSend` warning branch; the
   SleeperConnect round-trip (owned by backlog A-19); season-outlook interactions while
   `outlook.odds` is dark (carried as the single `outlook_shown` boolean); P0-6's
   proposed `send_unavailable_shown` / `trade_copied` (see §6 D-4); `is_self` (S-33);
   F2 `first_session_started` (S-37 — arm attribution is already derivable from
   `experiments.stamp_for_event`); and `sleeper_send_succeeded` **not** bumping
   `last_trade_proposed_at` (S-34).
6. **The `find_trades_tapped` empty-prop-allowlist defect (S-12).** In the
   "deliberately NOT here" section, verbatim in substance: `CLIENT_EVENT_PROPS`
   registers `"find_trades_tapped": frozenset()` (`analytics_taxonomy.py:191`), so
   **every** prop on that event is stripped at ingest — including the `source` prop the
   existing `'prefs_changed_strip'` call site sends. The event lands; its only
   dimension does not. Fixing it is a one-word taxonomy change but it belongs to
   whoever owns that funnel metric, not to this commit, which is why it goes to
   `NEXT.md` (HLD §7) and is documented here either way. **W0-TAX must not fix it in
   this commit** — a silent widening of a shipped event's prop surface inside a
   registration commit is the opposite of this commit's discipline.

Also record the **D2 rename** for the record: `celebration_fired` → `celebration_shown`
is executed by **W2-TS** at its three `TradesScreen.tsx` call sites (`:2547`, `:3135`,
`:3153`). The target name is **already registered** (`analytics_taxonomy.py:76`, props
`{beat_key, beat}` at `:225`). **No alias is added** (S-41) — the taxonomy is the
shipped surface and an alias would enshrine a typo. The addendum is where this rename is
*documented*; no taxonomy edit accompanies it.

### 1.6 `backend/tests/test_events_api.py` — three new tests

Follow the existing shape (`test_new_observability_events_accepted` `:335`,
`test_guide_events_accepted` `:366`). The batch cap is 50 envelopes
(`test_oversize_batch_rejected` `:262`), so all fifteen fit in one POST.

```python
def test_p0_remediation_events_accepted(harness):
    """All 15 P0-batch client events land with their full prop sets.

    dropped == 0 AND an exact set(by_type) are the two assertions a
    default-deny allowlist can otherwise fail silently — this is the test
    that would have caught invite_shared and celebration_fired.
    """
    client, engine = harness
    specs = [
        ("tab_selected",  {"tab": "league", "from_tab": "trades",
                           "refocus": False, "intercepted": False}),
        ("league_view",   {"surface": "league_rankings", "state": "ready",
                           "platform": "sleeper", "team_count": 12,
                           "basis": "consensus", "subset": "all",
                           "starters_available": True, "outlook_shown": False,
                           "is_tab_root": True}),
        ("league_basis_changed",   {"basis": "personal", "from": "consensus",
                                    "boards_differ": True,
                                    "team_focused": False}),
        ("league_subset_changed",  {"subset": "starters", "from": "all",
                                    "source": "chart", "filter_count": 0,
                                    "picks_stripped": False}),
        ("league_team_opened",     {"via": "row", "rank": 3,
                                    "basis": "consensus", "subset": "all",
                                    "filter_count": 0}),
        ("league_home_action_tapped", {"action": "find_trades"}),
        ("sleeper_send_attempted", {"surface": "deck", "give_n": 2,
                                    "receive_n": 1, "from_deck": True,
                                    "has_target": True}),
        ("sleeper_send_failed",    {"surface": "deck",
                                    "error_code": "sleeper_rejected",
                                    "status": 409, "kind": "graphql",
                                    "give_n": 2, "receive_n": 1,
                                    "from_deck": True}),
        ("invite_shared",          {"league_id": "123456789012345678"}),
        ("invite_link_opened",     {"league_id": "123456789012345678",
                                    "has_ref": True, "format": "legacy",
                                    "auth_state": "signed_out"}),
        ("invite_league_pinned",   {"league_id": "123456789012345678",
                                    "source": "picker_autopin",
                                    "ms_since_open": 4200}),
        ("invite_pin_failed",      {"league_id": "123456789012345678",
                                    "reason": "not_member"}),
        ("experiment_exposed",     {"experiment": "onboarding_v2_rollout",
                                    "variant": "v2", "unit": "device",
                                    "key": "onboarding.trades_first"}),
        ("quickset_step_advanced", {"position": "QB", "tier_index": 2,
                                    "tier_count": 8, "seeded_accepted": True,
                                    "picked_n": 3, "via": "save", "ms": 5100}),
        ("quickset_abandoned",     {"position": "QB", "tier_index": 3,
                                    "tiers_done": 2, "ms": 41000,
                                    "reason": "nav"}),
    ]
    body = _post(client, [
        _envelope(i, event_type=t, props=p) for i, (t, p) in enumerate(specs)
    ]).get_json()
    _assert_invariant(body, len(specs))
    assert body["accepted"] == len(specs) and body["dropped"] == 0
    by_type = {r._mapping["event_type"]: r._mapping for r in _rows(engine)}
    assert set(by_type) == {t for t, _ in specs}          # every one LANDED
    # Spot-check that props survived the per-event allowlist intact.
    assert json.loads(by_type["league_view"]["props"])["team_count"] == 12
    assert json.loads(
        by_type["sleeper_send_failed"]["props"])["error_code"] == "sleeper_rejected"
    assert json.loads(
        by_type["experiment_exposed"]["props"])["experiment"] == "onboarding_v2_rollout"


def test_sleeper_send_succeeded_is_not_client_submittable(harness):
    """The success leg is server-authoritative — a client POST is dropped."""
    client, engine = harness
    body = _post(client, [
        _envelope(0, event_type="sleeper_send_succeeded",
                  props={"give_n": 1, "receive_n": 1}),
    ]).get_json()
    assert body["accepted"] == 1 and body["dropped"] == 1
    assert _rows(engine) == []


def test_p0_events_reject_device_platform_prop(harness):
    """No P0 event carries a DEVICE platform prop — the column is derived
    server-side (analytics_ingest.py:365-368). A bogus one is stripped."""
    client, engine = harness
    _post(client, [
        _envelope(0, event_type="league_view",
                  props={"surface": "league_home", "state": "ready",
                         "platform": "espn", "device_platform": "ios"}),
    ])
    props = json.loads(_rows(engine)[0]._mapping["props"])
    assert props["platform"] == "espn"          # LEAGUE platform survives
    assert "device_platform" not in props       # device prop stripped
```

The negative case (`a misspelled name is counted-and-dropped`) is already covered by
`test_unknown_type_dropped` (`:246`); add `"sleeper_send_suceeded"` — the single-`c`
misspelling — to its envelope list rather than writing a fourth test, so the guard is
proven armed against a name that *looks* right.

### 1.7 `backend/tests/test_analytics_p0.py` — extend the membership assertion

`test_live_taxonomy_is_disjoint` (`:453`) asserts disjointness plus a membership subset.
Extend the subset and add the server-side membership, in the same test:

```python
def test_live_taxonomy_is_disjoint():
    import backend.analytics_taxonomy as tax
    import backend.analytics_ingest as ingest
    assert not (tax.ALLOWED_CLIENT_EVENTS & tax._SERVER_AUTHORITATIVE)
    assert {"app_opened", "signin_attempted", "quickset_prompt_shown",
            "trade_card_shared", "deck_exhausted_viewed"} <= tax.ALLOWED_CLIENT_EVENTS
    # P0 remediation batch, 2026-08-11 — all 15 client names registered
    # before their emitters ship (hld.md S-36).
    assert {"tab_selected", "league_view", "league_basis_changed",
            "league_subset_changed", "league_team_opened",
            "league_home_action_tapped", "sleeper_send_attempted",
            "sleeper_send_failed", "invite_shared", "invite_link_opened",
            "invite_league_pinned", "invite_pin_failed",
            "experiment_exposed", "quickset_step_advanced",
            "quickset_abandoned"} <= tax.ALLOWED_CLIENT_EVENTS
    # The SEND leg is server-authoritative and must never be client-fireable.
    assert "sleeper_send_succeeded" in tax.SERVER_FIRED_EVENTS
    assert "sleeper_send_succeeded" not in tax.ALLOWED_CLIENT_EVENTS
    assert ingest.ALLOWED_CLIENT_EVENTS is tax.ALLOWED_CLIENT_EVENTS


def test_p0_impression_events_are_non_intent():
    """A tab tap / League mount / exposure / abandon must never read as
    intent — INTENT_EVENTS is a deny-list, so this is the only thing
    standing between the batch and a DAU/WAU step-change on ship day."""
    import backend.analytics_queries as q
    for name in ("tab_selected", "league_view", "experiment_exposed",
                 "quickset_abandoned"):
        assert name in q.NON_INTENT_EVENTS
        assert name not in q.INTENT_EVENTS
    # …and the interaction events deliberately DO count as intent.
    for name in ("league_basis_changed", "league_team_opened",
                 "sleeper_send_attempted", "quickset_step_advanced"):
        assert name in q.INTENT_EVENTS


def test_wat_send_leg_is_live():
    import backend.analytics_queries as q
    assert q.WAT_DARK == frozenset()
    assert {"sleeper_send_attempted", "sleeper_send_succeeded",
            "sleeper_send_failed"} <= q.WAT_LIVE
    assert q.WAT_EVENTS == q.WAT_LIVE
```

> The two import-time asserts need **no test at all**: get the disjointness or the
> missing-props row wrong and the entire suite fails to import. That is the intended
> loud failure and it is already exercised by
> `test_namespace_assertion_trips_on_collision` (`:444`).

### 1.8 Commit-1 green criteria

`python3 -m pytest backend/tests/ -q` passes. No mobile change in this commit, so no
`tsc` or `testid-lint` requirement. Registering fifteen names with zero emitters is
behaviourally inert: no route changes, no schema change, no flag change, and the only
runtime difference is that four names now sit in a deny-list and three now sit in
`WAT_LIVE` — all of which is unobservable until rows exist.

---

## 2. §W1-BE — the server send-leg (commit 5)

**Agent:** W1-BE (sole owner of `backend/server.py` for wave 1).
**Files:** `backend/server.py` (one new helper + one call), `backend/tests/test_analytics_p0.py`
(one unit test — coordinate with W0-TAX, who also edits that file in commit 1; the two
edits are in different regions and commit 1 lands first).

### 2.1 Why a helper exists at all — the testability rationale, quoted

`POST /api/trades/propose` **cannot be driven end-to-end in tests.** Its first statement
is a deliberate fail-closed guard (`backend/server.py:12310-12315`):

```python
    if _TEST_MODE:
        # Fail closed: there is no legitimate automated send. Route-hit
        # accounting happens in test_support's request hook so injected and
        # fail-closed requests count identically (lld.md §4.3c).
        return jsonify({"error": "test_mode_propose_disabled"}), 599
```

The route harness in `test_analytics_p0.py` (`:325-340`) drives real Flask routes, and
under `FTF_TEST_MODE` this one returns 599 before touching a session, a body or Sleeper.
Monkeypatching `_TEST_MODE` **and** `_sleeper_write.propose_trade` **and**
`get_sleeper_credential` **and** `_fetch_league_rosters` to reach the success path would
test four mocks and a route, not the event. S-35 therefore approves the extraction: a
tiny `_record_send_success(...)` helper, called from the success path, unit-tested
directly. It also keeps the route body to one line, which matters on a 12 000-line
handler surface.

### 2.2 The helper

Place it immediately **above** `@app.route("/api/trades/propose")` (`:12294`), next to
the route it serves. Mirrors the `trades_generated` precedent at `:5231-5240` — a
`try/except` around `record_event` so an analytics failure can never break a *completed
Sleeper trade*.

```python
def _record_send_success(user_id: str, league_id: str, give: list[str],
                         receive: list[str], picks: list[str],
                         transaction_id: str | None,
                         from_deck: bool) -> None:
    """P0-7 — the north-star SEND leg (analytics_queries.WAT_LIVE, funnel
    stage 8, FEATURE_VERTICALS["send_in_sleeper"]).

    Extracted rather than inlined because /api/trades/propose fail-closes
    under FTF_TEST_MODE (see the guard at the top of the route), so the
    route cannot be driven end-to-end in a test; this helper is the honest
    seam and keeps the route body to one line (hld.md S-35).

    Server-fired: the row carries event_id=NULL and is not client-forgeable.
    NO user identifier of the counterparty rides in props — `transaction_id`
    is a Sleeper transaction id, which the runbook's reconciliation path
    wants; `their_user_id` is deliberately excluded.

    Never raises: record_event already swallows its own failures, and the
    outer guard covers anything upstream of it. A completed Sleeper trade
    must never be undone by an analytics write.
    """
    try:
        record_event(
            user_id, "sleeper_send_succeeded",
            league_id=league_id,
            source="api",
            props={
                "give_n": len(give),
                "receive_n": len(receive),
                "pick_n": len(picks),
                "from_deck": from_deck,
                "transaction_id": transaction_id,
            },
        )
    except Exception as ev_err:
        log.warning("record_event(sleeper_send_succeeded) failed: %s", ev_err)
```

**Signature notes.**
- `props` are **counts, not ids** — `give_n` / `receive_n` / `pick_n`. Player ids would
  be unbounded-cardinality props with no analytical use here.
- `from_deck` is `bool(body.get("impression_id"))`, computed at the call site so the
  helper stays free of `request` state and is unit-testable with plain arguments.
- `transaction_id` may be `None` when Sleeper returns a bare success; that is honest and
  the prop stays.
- Server-fired props bypass `_scrub_pii` (which is client-only). Nothing here is a
  person.

### 2.3 The call site

In the success tail of `propose_trade_to_sleeper`, **immediately after**
`_save_deck_outcome_safe(...)` and **before** the `return jsonify(...)`
(`server.py:12403-12409` today):

```python
    # F1 (deck.signal_v2) — proposal-sent outcome when the deck card that
    # sourced this send carried an impression_id. Additive/optional; only
    # reached on a successful Sleeper propose.
    _save_deck_outcome_safe(body.get("impression_id"), "propose")
    # P0-7 — the send actually landed in Sleeper. This is the ONLY place
    # in the product that knows that, which is why the success leg is
    # server-fired while attempt/failure are client-fired (hld.md S-30).
    _record_send_success(
        user_id, league_id, give, receive, picks,
        result.get("transaction_id"),
        bool(body.get("impression_id")),
    )
    return jsonify({
        "status": result.get("status") or "proposed",
        "transaction_id": result.get("transaction_id"),
    })
```

Every name used is already in scope at that point: `user_id` (`:12314`), `league_id` /
`give` / `receive` / `picks` (`:12330-12335`), `body` (`:12329`), `result` (`:12376`).
`record_event` is already imported by `server.py` (the `trades_generated` site proves
it) — verify the import rather than adding a second one.

**Position matters.** After `_save_deck_outcome_safe`, so the deck outcome (which feeds
the F1 signal spine) is written first and an analytics hiccup cannot cost it. Before the
`return`, obviously. **Not** inside the `if _TEST_MODE:` guardrail-counter block above
it — that block is structurally dead on this path.

### 2.4 The unit test

```python
def test_record_send_success_writes_server_fired_row(tmp_path):
    """P0-7 — the propose route fail-closes under FTF_TEST_MODE (599), so
    the send-success event is proven at its extracted helper (hld.md S-35)."""
    import backend.server as server
    eng = _file_engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        server._record_send_success(
            "u_send", "123456789012345678",
            give=["a", "b"], receive=["c"], picks=["2027_1_5"],
            transaction_id="txn-9", from_deck=True,
        )
    rows = _ue_rows(eng, "sleeper_send_succeeded")
    assert len(rows) == 1
    assert rows[0]["event_id"] is None            # server-authoritative
    assert rows[0]["league_id"] == "123456789012345678"
    assert json.loads(rows[0]["props"]) == {
        "give_n": 2, "receive_n": 1, "pick_n": 1,
        "from_deck": True, "transaction_id": "txn-9",
    }


def test_record_send_success_never_raises(tmp_path):
    """A completed Sleeper trade must never be undone by an analytics write."""
    import backend.server as server
    with patch.object(server, "record_event", side_effect=RuntimeError("boom")):
        server._record_send_success("u", "1", [], [], [], None, False)   # no raise


def test_send_success_does_not_bump_last_trade_proposed_at():
    """hld.md S-34 — bumping the denorm column would change notification
    gating, which is out of scope for an instrumentation item."""
    from backend.database import _EVENT_TO_USER_COL
    assert "sleeper_send_succeeded" not in _EVENT_TO_USER_COL
```

Reuse the file's existing `_file_engine` / `_ue_rows` helpers; do not introduce new
fixtures.

---

## 3. §W2-P07 — client instrumentation (commits 9, 10, 13)

**Agent:** W2-P07.
**Files (exclusive in wave 2):** `mobile/src/navigation/TabNav.tsx`,
`mobile/src/screens/LeagueScreen.tsx`, `mobile/src/screens/LeagueSummaryScreen.tsx`,
`mobile/src/components/SendInSleeperButton.tsx` (**handlers only**),
`mobile/src/api/flags.ts`, `mobile/src/state/useFeatureFlags.ts`,
`mobile/src/screens/QuickSetTiersScreen.tsx`.

**Hard prohibitions for this agent** (HLD §4, §9 LLD-6): do not open
`TradesScreen.tsx`; do not edit `mobile/.maestro/04-tabs-navigation.yaml` or
`mobile/.maestro/flows/smoke/09-league.yaml` (**any diff to either invalidates P0-7's
Maestro waiver — R12**); do not change `SendInSleeperButton`'s prop signature or render
path before commit 13; do not add an alias for `celebration_fired`.

Every insertion below is a `track()` call. `track` is synchronous, returns `void`, and
swallows every error by contract (`events.ts:188-215`), and it is a **no-op** while
`analytics.client_events` is off. No insertion may change control flow, add an `await`,
or sit inside a render body.

Import line, added once per file: `import { track } from '../api/events';` (screens and
navigation) / `'../api/events'` from `components/`.

**React import deltas, verified in this worktree:** `LeagueScreen.tsx:1` is
`import React, { useState, useMemo } from 'react';` → add `useEffect, useRef`.
`LeagueSummaryScreen.tsx:1` already imports `useEffect, useMemo, useRef, useState` — no
change. `QuickSetTiersScreen.tsx:1` imports `useCallback, useMemo, useState` and uses
`React.useEffect`/`React.useRef` inline throughout — follow that file's existing idiom
rather than widening its import. `QuickSetTiersScreen` additionally needs `AppState`
added to its `react-native` import for §3.6.4.

### 3.1 `TabNav.tsx` — `tab_selected` (commit 9)

Six existing `tabPress` handlers, no new handlers, no behaviour change. **`track` is the
first statement in every one, before any early return, `preventDefault()`, prefetch or
pop** — an intercepted tap and a non-focused re-tap are both real tab selections.

Shared derivation, declared once inside `TabNav`'s body above the `return`:

```tsx
// P0-7 — tab_selected. `from_tab` is the tab that OWNED the bar at press
// time; optional-chained throughout because a null is honest and a throw
// is not (track swallows anyway, but a throw inside a listener would take
// the tap with it). NON_INTENT server-side: a tab tap is navigation, not
// intent (analytics_queries.NON_INTENT_EVENTS).
const trackTab = (
  tab: string,
  navigation: any,
  opts?: { intercepted?: boolean },
) => {
  const st = navigation?.getState?.();
  track('tab_selected', {
    tab,
    from_tab: st?.routes?.[st.index]?.name?.toLowerCase() ?? null,
    refocus: !!navigation?.isFocused?.(),
    intercepted: !!opts?.intercepted,
  });
};
```

No `screen` argument: a tab listener has no route context, and `screen_viewed`
(`RootNav.tsx:376`) already supplies the destination on the very next tick.

**Rank, `rankDest` variant (`:631`).** Note the existing early return — `track` goes
*above* it, or a first-time switch into Rank is never counted:

```tsx
                  tabPress: () => {
                    trackTab('rank', navigation);
                    if (!navigation.isFocused()) return;
                    popNestedToTop(navigation, route);
                  },
```

**Rank, intercepting variant (`:640`).** This is the only handler that
`preventDefault()`s; `intercepted: true` is what distinguishes "opened the Rank action
sheet" from "navigated to Rank" in the data. Note the listener factory here is `() =>
({...})` with **no** `navigation` in scope — change it to `({ navigation }) => ({...})`,
which is the same shape every sibling already uses and is not a behaviour change:

```tsx
              : ({ navigation }) => ({
                  tabPress: (e) => {
                    trackTab('rank', navigation, { intercepted: true });
                    e.preventDefault();
                    setRankMenuOpen(true);
                  },
                })
```

**Trades (`:667`)** — `trackTab('trades', navigation);` as the first line, above the
`retapOn && navigation.isFocused()` block and above the `leagueId` read.
**Draft (`:701`)** — `trackTab('draft', navigation);` first. (The handler only exists
when `draft.tab` is on, which is correct: a tab that is not in the bar cannot be
selected.)
**Matches (`:718`)** — `trackTab('matches', navigation);` first. This listener
destructures `({ navigation })` only; no change needed.
**League (`:737`)** — `trackTab('league', navigation);` first.

`tab` values are the five literals `rank|trades|draft|matches|league` — hardcoded, not
derived from `route.name`, so the enum can never drift with a presentation rename (the
Trades tab already *reads* "Acquire" while its route name stays `Trades`).

### 3.2 `LeagueScreen.tsx` — `league_view` + OPTIONAL-A (commit 9)

#### 3.2.1 `league_view`, surface `league_home`

**Placement is load-bearing.** The screen has an early return at `:280`:

```tsx
  // No league yet — funnel back to the picker. Should be rare since the
  // tab nav only renders this when the user is signed in.
  if (!leagueId) {
    return (
```

React hooks may not sit below a conditional return, so the effect goes **above it** —
place it immediately after `refetchAll` (`:267-276`) and before the `if (!leagueId)`
block. The `state: 'no_league'` branch is exactly why the effect must live there: without
it, the no-league mount would emit nothing.

```tsx
  // ── P0-7 · league_view (surface: league_home) ───────────────────────
  // Once per mount, never per re-render: `firedRef` is the guard and
  // `summaryQuery.isFetched` is the trigger, so the row carries settled
  // data rather than a first-paint skeleton. Declared ABOVE the
  // `if (!leagueId)` early return — hooks may not sit below it, and the
  // no-league state is one of the four states this event exists to count.
  // NON_INTENT server-side: a mount is an impression.
  const viewFiredRef = useRef(false);
  useEffect(() => {
    if (viewFiredRef.current) return;
    if (leagueId && !summaryQuery.isFetched) return;   // wait for settle
    viewFiredRef.current = true;
    const s = summaryQuery.data as any;
    track('league_view', {
      surface: 'league_home',
      state: !leagueId ? 'no_league'
             : summaryQuery.isError ? 'error'
             : s ? 'ready' : 'empty',
      platform: cachedLeagues.find((lg) => lg.league_id === leagueId)
                  ?.platform ?? 'unknown',
      team_count: typeof s?.total_teams === 'number' ? s.total_teams : null,
      basis: null,                 // League Home has no basis control
      subset: null,                // …nor a subset control
      starters_available: null,    // …nor a starters split
      outlook_shown: null,         // …nor the season-outlook layer
      is_tab_root: false,          // LeagueHome is a stack push, never the tab root
    }, 'LeagueHome');
  }, [leagueId, summaryQuery.isFetched, summaryQuery.isError, summaryQuery.data,
      cachedLeagues]);
```

`platform` is the **league** platform, resolved exactly as every other client gate
resolves it — match the active id against the cached league list (`LeagueScreen.tsx:123`
is the existing precedent) — and **`'unknown'` on a miss, never a guess**. `is_tab_root`
is a constant `false` here and is genuinely constant: since #181 the League tab's root is
`LeagueRankings`, and `LeagueHome` is only ever reached by push.

The four `null`s are deliberate and honest: they mean "this surface has no such control",
not "unknown". The addendum records that `league_home` rows always carry them.

#### 3.2.2 OPTIONAL-A — `league_home_action_tapped` (S-31)

Twelve `action` values, all one-line inserts inside existing handlers, none of which
changes control flow. Declare one helper next to `goRank`/`goFindTrade` (`:366`):

```tsx
  // P0-7 OPTIONAL-A — League Home's exit paths are the only question this
  // screen answers. One closed enum, one prop, ~12 one-line inserts.
  const tapAction = (action: string) =>
    track('league_home_action_tapped', { action }, 'LeagueHome');
```

| `action` | Site | Insert |
|---|---|---|
| `rank` | `:366` `const goRank = () => navigation.navigate('Rank');` | `const goRank = () => { tapAction('rank'); navigation.navigate('Rank'); };` |
| `find_trades` | `:367` `goFindTrade` (**two** mount sites: the action row `:491` and the works-now card `:721` — instrumenting the function covers both with one edit) | `const goFindTrade = () => { tapAction('find_trades'); navigation.navigate('Trades', { screen: 'TradesHome' }); };` |
| `whats_new` | `:405-408` `onDismiss` | first line of the `onDismiss` body, **before** `dismissWhatsNew()` |
| `members` | `:452` `onPress={() => setMembersOpen(true)}` | `onPress={() => { tapAction('members'); setMembersOpen(true); }}` |
| `matches_mutual` | `:511` | `onPress={() => { tapAction('matches_mutual'); navigation.navigate('Matches', { segment: 'mutual', at: Date.now() }); }}` |
| `matches_awaiting` | `:518` | same shape, `'matches_awaiting'` |
| `rankings` | `:540` `navigate('LeagueRankings')` | same shape |
| `free_agents` | `:548` `navigate('FreeAgents')` | same shape |
| `draft_room` | `:564` `navigate('DraftRoom')` | same shape |
| `rookie_board` | `:573` `setRookieOpen(true)` | same shape |
| `draft_picks` | `:598` `navigate('PickAssignment')` | same shape |
| `espn_resync` | `:747` `onPress={resyncEspn}` | first line of `resyncEspn`'s body (`:135`), **inside** the function so the `if (!leagueId \|\| !user \|\| resyncing) return;` guard still governs the navigation but the tap is counted — a tap on a disabled-by-guard control is still a user telling us something |

The `espn.link` sign-in button at `:764` is **not** instrumented: it is a failure-recovery
affordance on the ESPN re-sync path, not a hub exit, and `espn_resync` already names that
moment. `draft_room` and `rookie_board` are the same physical slot under different flags
(`:558-577`) — two values, not one, because which occupant was tapped is the question.

**Enum, closed, twelve values:** `rank` · `find_trades` · `matches_mutual` ·
`matches_awaiting` · `rankings` · `free_agents` · `draft_room` · `rookie_board` ·
`draft_picks` · `whats_new` · `members` · `espn_resync`.

### 3.3 `LeagueSummaryScreen.tsx` — `league_view` + three interactions (commit 9)

This screen is registered under **two** route names — `LeagueRankings` (League-tab root)
and legacy root-stack `LeagueSummary` — and `isTabRoot` is already computed for exactly
that reason (`:362` `const isTabRoot = route.name === 'LeagueRankings';`). Both emit
`surface: 'league_rankings'`; `is_tab_root` disambiguates and the `screen` argument
carries the real route name.

#### 3.3.1 `league_view` — the double-fire hazard (R11)

The screen runs **two parallel queries** with `placeholderData: (prev) => prev`
(`:399-412`), so it re-renders often and `query` swaps identity on a basis toggle. Guard
is `firedRef` **plus** `query.isFetched`; the effect must be declared above the
`if (!leagueId)` early return at `:773`. Place it immediately after the `switchSubset`
definition (`:756`), which is above every derived-label block and safely above the
return.

```tsx
  // ── P0-7 · league_view (surface: league_rankings) ───────────────────
  // ONCE per mount. This screen holds two parallel queries with
  // placeholderData (#248), so it re-renders constantly and a naive
  // effect would double-fire; the firedRef is the guard and
  // query.isFetched is the trigger. Declared above the `if (!leagueId)`
  // early return — hooks may not sit below it.
  const viewFiredRef = useRef(false);
  useEffect(() => {
    if (viewFiredRef.current) return;
    if (leagueId && !query.isFetched) return;
    viewFiredRef.current = true;
    track('league_view', {
      surface: 'league_rankings',
      state: !leagueId ? 'no_league'
             : query.isError ? 'error'
             : teams.length > 0 ? 'ready' : 'empty',
      platform: useSession.getState().leagues
                  .find((lg) => lg.league_id === leagueId)?.platform ?? 'unknown',
      team_count: teams.length || null,
      basis,
      subset,
      starters_available: startersAvailable,
      // outlook.odds is OFF in config/features.json, so this is `false` on
      // every row until the flag flips. That is correct and honest — do
      // not read the constant as a bug (plan-p0-7 §10.2).
      outlook_shown: oddsEnabled && outlookSupported,
      is_tab_root: isTabRoot,
    }, route.name);
  }, [leagueId, query.isFetched, query.isError, teams.length, basis, subset,
      startersAvailable, oddsEnabled, outlookSupported, isTabRoot, route.name]);
```

`basis` and `subset` are the values **at mount**, which is what a view event should
carry; subsequent changes are the three interaction events' job. The `platform` read uses
`useSession.getState()` inside the effect rather than a new subscription — this screen
already keeps its session subscriptions deliberately narrow (`:441-445` selects a
*boolean*, with a comment explaining why), and adding a `leagues`-array subscription
would re-render the screen on every league-list refresh for the sake of one prop.

#### 3.3.2 `league_basis_changed` — a new `changeBasis` helper

Today both chips call `setBasis` directly (`:835`, `:841`) and the third is `disabled`
with no handler (`:843-848`). Add the helper next to `switchSubset` — same shape, same
early-return-on-no-op discipline:

```tsx
  // P0-7 — the two BasisChips called setBasis directly; route both through
  // one helper so the event has a single choke point. Guarded on a real
  // change, so re-tapping the active chip emits nothing (a no-op row is
  // noise in a funnel).
  const changeBasis = (b: UiBasis) => {
    if (b === basis) return;
    track('league_basis_changed', {
      basis: b,
      from: basis,
      boards_differ: boardsDiffer,
      team_focused: selectedId !== null,
    }, route.name);
    setBasis(b);
  };
```

Then `onPress={() => changeBasis('consensus')}` (`:835`) and
`onPress={() => changeBasis('personal')}` (`:841`). The redraft chip stays untouched —
it is `disabled` and carries no `onPress`, so there is nothing to instrument and adding
one would fabricate an interaction the user cannot have.

`boardsDiffer` (`:556`) and `selectedId` (`:385`) are both already in scope at the helper's
position. `team_focused` answers a real question: a basis toggle while a team drill-in is
open is a comparison act, not a browse act.

#### 3.3.3 `league_subset_changed` — inside the existing choke point, with a `source`

`switchSubset` (`:746`) is already the single choke point for **both** `SubsetControl`
instances (chart `:944`, drill-in roster `:1157`), and the `:466` auto-fallback calls
`setSubset` **directly** — so it stays silent, which is correct: a server-driven fallback
is not a user switching a subset.

`source` requires threading one argument. `SubsetControl`'s prop type is
`onSwitch: (s: Subset) => void` (`:1371-1375`) and its `Pressable` calls
`onSwitch(s.key)` (`:1388`). Widen both by one optional parameter — additive, no caller
breaks:

```tsx
function SubsetControl({ idPrefix, subset, onSwitch, source }: {
  idPrefix: string;
  subset: Subset;
  onSwitch: (s: Subset, source: 'chart' | 'roster') => void;
  // P0-7 — which of the two mirrored control instances was touched. The
  // two share ONE state (#237), so without this the event cannot tell the
  // chart control from the drill-in roster control.
  source: 'chart' | 'roster';
}) {
  …
            onPress={() => onSwitch(s.key, source)}
```

with `source="chart"` at `:944` and `source="roster"` at `:1157`, and:

```tsx
  const switchSubset = (s: Subset, source: 'chart' | 'roster' = 'chart') => {
    // P0-7 — guarded on a real change; the :466 auto-fallback calls
    // setSubset DIRECTLY and is deliberately silent (a server-driven
    // fallback is not a user switching a subset).
    if (s !== subset) {
      track('league_subset_changed', {
        subset: s,
        from: subset,
        source,
        filter_count: posFilter.size,
        // The synchronous OFF-path PICKS strip below actually fired.
        picks_stripped: !picksAlwaysCounted && s !== 'all' && posFilter.has('PICKS'),
      }, route.name);
    }
    setSubset(s);
    if (!picksAlwaysCounted && s !== 'all') {
      …unchanged…
    }
  };
```

The default `= 'chart'` keeps the function callable with one argument, so any site the
build agent finds that this LLD did not (re-grep!) still compiles. `picks_stripped` is
computed **before** `setPosFilter` runs, reading the same three values the strip itself
reads — so it reports what actually happened, not what was intended.

#### 3.3.4 `league_team_opened` — a new `openTeam` helper

Two drill-in sites, both `setSelectedId`: the bar column (`:1048`
`onPress={() => setSelectedId(id)}`, inside `ranked.map((r, idx) => …)`) and the team row
(`:1294` `onPress={() => setSelectedId(r.tc.team.user_id)}`, also inside
`ranked.map((r, idx) => …)`). Both have `idx` in scope, so `rank` is `idx + 1` — the
**1-based on-screen rank under the active filters**, which is what the bars and rows
themselves display. Do not use `team.rank` (the server's unfiltered rank); they diverge
the moment a position filter is applied.

```tsx
  // P0-7 — the two drill-in entry points. `rank` is the 1-based ON-SCREEN
  // rank under the active filters (what the user actually tapped), never
  // the server's unfiltered team.rank. `is_self` is deliberately absent:
  // session-user ↔ PowerRankedTeam.user_id identity was never proven and a
  // guessed prop is worse than a missing one (hld.md S-33).
  const openTeam = (id: string, via: 'bar' | 'row', rank: number) => {
    track('league_team_opened', {
      via, rank, basis, subset, filter_count: posFilter.size,
    }, route.name);
    setSelectedId(id);
  };
```

`onPress={() => openTeam(id, 'bar', idx + 1)}` at `:1048`;
`onPress={() => openTeam(r.tc.team.user_id, 'row', idx + 1)}` at `:1294`.
`setSelectedId(null)` at `:904` (the "‹ All teams" close control) is **not**
instrumented — drill-in close/dwell is on the deliberately-NOT-here list.

### 3.4 `SendInSleeperButton.tsx` — attempt + failure (commit 10)

**P0-6 lands first (commit 8) and owns this file's signature and render path (S-23).**
P0-6's own §9 proposes the split as *"P0-6 owns lines 30-66 and 273-end; P0-7 owns the
callbacks at 105-271"* — the HLD converts that from a parallel split into a **sequential
handoff**, but the *region* grant stands: **W2-P07 may insert only inside the callback
block that today spans `:105-271` (`openInSleeper` → `goConnect` → `doPropose` →
`confirmSend` → `onPress`), and only in `onPress` and `doPropose`'s `catch`.** Everything
from the `if (!enabled || …) return null;` line down is frozen for this agent, as is the
`interface Props` block. Re-grep after commit 8: P0-6 rewrites the gate, so these line
numbers move.

Two inserts, both first-statement-in-their-block:

**(a) `sleeper_send_attempted` — top of `onPress` (`:231-235` today), after the
`state !== 'idle'` guard and before `haptics.pickup()`:**

```tsx
  const onPress = useCallback(async () => {
    if (state !== 'idle') return;
    // P0-7 — the ATTEMPT leg. Fired in the HANDLER, never at render:
    // after P0-6 a non-Sleeper mount renders a copy affordance rather
    // than a send button, so a mount-time impression event would conflate
    // copy-affordance impressions with send impressions and corrupt the
    // send-funnel denominator (hld.md §1.4).
    // has_target=false means this tap becomes the openInSleeper() handoff
    // below, NOT a real send — the denominator needs that distinction.
    track('sleeper_send_attempted', {
      surface,
      give_n: givePlayerIds.length,
      receive_n: receivePlayerIds.length,
      from_deck: !!impressionId,
      has_target: !!leagueId && !!theirUserId,
    });
    haptics.pickup();
```

No `screen` argument: the component is screen-agnostic and mounted on four surfaces;
`surface` is the dimension that matters, and `screen_viewed` already establishes context.

`surface` is P0-6's prop, declared `surface?: SendSurface` in commit 8 and tightened to
required in commit 13 (§3.7). While optional it may be `undefined` on an un-plumbed
mount — that is the honest value and the reason commit 13 exists.

**(b) `sleeper_send_failed` — first statement of `doPropose`'s catch (`:143-147` today),
before `setState('idle')` and before the alert ladder:**

```tsx
    } catch (err) {
      const body = err instanceof ApiError ? (err.body as any) : undefined;
      // P0-7 — the FAILURE leg. Client-fired because this is the ONLY
      // place that sees network errors, timeouts, and the pre-identity
      // refusals (feature_disabled / no_user / test_mode_propose_disabled)
      // the server cannot attribute to a user — and the only place that
      // knows `surface`. Closed enum: 12 server codes ∪ network | timeout
      // | unknown = 15 values, forever.
      track('sleeper_send_failed', {
        surface,
        error_code: err instanceof ApiError
          ? (err.isTimeout ? 'timeout' : (body?.error ?? 'unknown'))
          : 'network',
        status: err instanceof ApiError ? (err.status ?? null) : null,
        kind: body?.kind ?? null,
        give_n: givePlayerIds.length,
        receive_n: receivePlayerIds.length,
        from_deck: !!impressionId,
      });
      setState('idle');
      const code: string | undefined = body?.error;
      …unchanged ladder…
```

Note the one structural nicety: `const body = …` moves **one line up**, above the
`track` call, because both the event and the ladder need it. `setState('idle')` moves
one line down. Neither is a behaviour change — nothing between them observes state.
`code` and `detail` keep their current declarations; do not re-derive them for the event.

**`err.status` and `err.isTimeout` are confirmed present** — both are public constructor
parameters on `ApiError` (`mobile/src/api/client.ts:167-172`), and `client.ts:377`
already reads `isTimeout` the same way for `api_request_failed`. No new field is
invented; `status` is non-optional on `ApiError`, so the `?? null` is belt-and-braces for
the non-`ApiError` branch only.

**Nothing else in this file is touched.** No impression event, no confirm-dialog-cancel
event, no `validateTradeSend`-warning event, no `goConnect` round-trip event. All four
are on the deliberately-NOT-here list, and the last one belongs to backlog item A-19.

### 3.5 F1 `experiment_exposed` — the emission mechanism (commit 10)

This is the section HLD §10.6 item 10 flags as missing from the plan: F1 exists to fix
"registered but never emitted", so shipping it without a specified emission site would
reproduce the defect inside its own fix.

**The problem being solved.** `backend/experiments.py:620,723` uses **assignment** as an
exposure proxy and reports the resulting dilution. Assignment happens for every unit the
targeting rules match; exposure happens only for the units that reached the gated
surface. For a first-session test the gap is large *and arm-correlated*, so an
assignment-based read is not merely noisy — it is biased.

**What the client already has.** `GET /api/feature-flags` returns
`{flags, experiments: {expKey: variant}, configs: {expKey: client_config}}`
(`server.py:17270-17333`), where a running variant's `client_config.flags` is the
per-unit flag overlay. `mobile/src/api/flags.ts:44-52` merges those overlays over the
base map and **throws `experiments` away**:

```ts
    const configs = res?.configs || {};
    let merged = base;
    for (const key of Object.keys(configs)) {
      const overlay = configs[key]?.flags;
      if (overlay && typeof overlay === 'object' && !Array.isArray(overlay)) {
        merged = { ...merged, ...overlay };
      }
    }
    return merged;
```

So the raw material for exposure — *this flag key's value came from that experiment's
that variant* — exists for exactly one instant and is then discarded.

**(a) `api/flags.ts` — record provenance during the merge.**

```ts
/** P0-7 F1 — flag-key → the experiment overlay it came from.
 *  Rebuilt on every successful fetch and never persisted: it describes the
 *  CURRENT assignment, and a stale one would attribute an exposure to an
 *  experiment the unit is no longer in. Module-level, deliberately not in
 *  the store — it must not cause a re-render. */
export type FlagProvenance = Record<string, { experiment: string; variant: string }>;
let _provenance: FlagProvenance = {};
export function flagProvenance(): FlagProvenance { return _provenance; }
```

and inside the merge loop, alongside the existing `merged = {...merged, ...overlay}`:

```ts
    const configs = res?.configs || {};
    const exps = res?.experiments || {};
    const provenance: FlagProvenance = {};
    let merged = base;
    for (const key of Object.keys(configs)) {
      const overlay = configs[key]?.flags;
      if (overlay && typeof overlay === 'object' && !Array.isArray(overlay)) {
        merged = { ...merged, ...overlay };
        // P0-7 F1 — remember WHICH experiment/variant supplied each key so
        // useFeatureFlags can emit an exposure on first consumption. Last
        // writer wins, exactly like the merge above, so provenance can
        // never disagree with the value the app is actually using.
        for (const fk of Object.keys(overlay)) {
          provenance[fk] = { experiment: key, variant: exps[key] ?? 'unknown' };
        }
      }
    }
    _provenance = provenance;
    return merged;
```

Two invariants: provenance is assigned **only on the success path**, so a failed fetch
leaves the previous map intact (matching `revalidateFlags`'s "keep cached flags"
contract); and `loadFeatureFlags`'s **return type is unchanged** (`Promise<FlagMap>`), so
no caller is touched.

**(b) `state/useFeatureFlags.ts` — deferred emit on first consumption.**

```ts
import { loadFeatureFlags, flagProvenance } from '../api/flags';
import { track } from '../api/events';

// ── P0-7 F1 · experiment_exposed ───────────────────────────────────────
// EXPOSURE, not assignment. backend/experiments.py uses assignment as a
// proxy and reports the dilution; for a first-session test the gap is
// large AND arm-correlated, so an assignment-based read is biased, not
// merely noisy.
//
// Fired at most ONCE PER FLAG KEY PER SESSION, and always DEFERRED —
// `useFlag` runs during render, and calling track() there would queue an
// AsyncStorage write from a render body. setTimeout(0) moves it to the
// next tick, after the commit.
const _exposed = new Set<string>();
function noteFlagConsumed(key: string): void {
  if (_exposed.has(key)) return;
  const p = flagProvenance()[key];
  if (!p) return;                 // not an overlaid key — no experiment, no exposure
  _exposed.add(key);              // claim BEFORE the deferral: two consumers in
                                  // one render must not queue two events
  setTimeout(() => {
    track('experiment_exposed', {
      experiment: p.experiment,
      variant: p.variant,
      key,
      // `unit` is registered in the taxonomy but not emitted: the client
      // cannot derive account-vs-device (the flag endpoint returns the
      // merged maps without unit_type). Adding it is a server change.
    });
  }, 0);
}
```

Wired into the **three** consumption helpers, and only those:

```ts
export function useFlag(key: string): boolean {
  noteFlagConsumed(key);                       // no-op unless key is overlaid
  return useFeatureFlags((s) => !!s.flags[key]);
}

export function useOnboardingFeature(key: string): boolean {
  noteFlagConsumed('onboarding.v2');
  noteFlagConsumed(key);
  return useFeatureFlags((s) => !!s.flags['onboarding.v2'] && !!s.flags[key]);
}

export function onboardingEnabled(key: string): boolean {
  noteFlagConsumed('onboarding.v2');
  noteFlagConsumed(key);
  const flags = useFeatureFlags.getState().flags;
  return !!flags['onboarding.v2'] && !!flags[key];
}
```

**Why this is safe to call from a render body.** `noteFlagConsumed` performs a `Set`
lookup and, at most, one `Set.add` plus a `setTimeout` schedule. It never calls
`set()`, never touches the store, never re-renders, and is idempotent. The `track()`
call — which does hit the zustand flag store and the AsyncStorage queue — runs on the
next macrotask, after commit. This is the whole content of the HLD's "deferred (never
during render)" requirement.

**Coverage, stated honestly in the addendum.** Direct imperative reads of the shape
`useFeatureFlags.getState().flags['x']` — `TabNav.tsx:583` (`draft.tab`),
`InviteLeaguematesBanner`'s `buildInviteUrl`, `FreeAgentsScreen` — bypass all three
helpers and are **not** instrumented. That is acceptable and deliberate: the only live
experiment is `onboarding_v2_rollout`, whose overlay keys are `onboarding.*`, which are
consumed exclusively through `useOnboardingFeature` / `onboardingEnabled` (that is the
kill-switch contract at `useFeatureFlags.ts:110-115`). Instrumenting the raw store read
would mean either a proxy over the flag map or edits to files W2-P07 does not own.
Record the limitation; do not widen the blast radius for it.

**Volume.** Bounded by the number of overlaid keys, once per app session — single
digits. Nowhere near the queue cap.

### 3.6 `QuickSetTiersScreen.tsx` — F3 + F4 (commit 10)

The P0-9 question is *"is 32 taps a grind?"*, which is a **per-rung** question.
`quickset_completed` is server-fired **per completed position** (and this screen's own
client `track('quickset_completed', …)` at `:256` fires only on a full-position
completion), so a user who walks three rungs of QB and quits is invisible today.

#### 3.6.1 The seams, quoted

The walk's advance choke point is `goTo(idx, savedMap)` (`:234-294`), reached from four
places: `saveMutation.onSuccess` → `goTo(tierIdx + 1, nextSaved)` (`:318`), `onSave`'s
nothing-to-do branch → `goTo(tierIdx + 1, savedByTier)` (`:334`), `onSkip` → `goTo(tierIdx
+ 1, …)` (`:365`), and `onBack` → `goTo(tierIdx - 1, …)` (`:366`). **`goTo` itself is the
wrong insertion point**: it is a `useCallback` whose dependency array is `[navigation,
position, rookieScope.isRookie, onboardingReturn]` (`:293`) — `tierIdx` is *not* a
dependency, so reading it inside `goTo` would read a stale value. Instrument the three
**forward** call sites, each of which has a correct `tierIdx` in its own closure.

Completion is `goTo`'s `idx >= TIERS.length` branch (`:236`), which ends in either a
`navigation.navigate('Trades')` (`:263`) or an Alert whose `exit` goes back/navigates
(`:269-286`). Neither reliably **unmounts** the screen — `navigate('Trades')` switches
tabs while the Rank stack stays mounted — which is why F4 hangs off `blur`, not unmount.

#### 3.6.2 State to add

```tsx
  // ── P0-7 F3/F4 · Quick Set per-rung telemetry ───────────────────────
  // Refs, not state: none of this renders, and a blur/unmount handler
  // reads them at a moment when a closed-over state value would be stale.
  const stepStartRef = useRef(Date.now());       // reset on every advance
  const walkStartRef2 = useRef(Date.now());      // whole-walk clock for F4
  const abandonRef = useRef({ tierIdx: 0, tiersDone: 0, position });
  const completedRef = useRef(false);            // set in goTo's done branch
  const abandonFiredRef = useRef(false);         // blur AND unmount both fire
```

Keep `abandonRef.current` in sync with one effect (cheap, no render impact):

```tsx
  useEffect(() => {
    abandonRef.current = {
      tierIdx,
      tiersDone: Object.keys(savedByTier).length,
      position,
    };
  }, [tierIdx, savedByTier, position]);
```

#### 3.6.3 F3 — `quickset_step_advanced`

One helper, three call sites:

```tsx
  // `seeded_accepted` is the operator's fairness point: the grid arrives
  // pre-seeded from consensus (gridPlayers are the players whose CURRENT
  // tier is this rung or unclaimed), so a rung can clear in one tap and
  // "32 taps" overstates the work. True ⇔ the user saved EXACTLY the
  // consensus-seeded set for this rung — no additions, no omissions.
  const trackStepAdvanced = (ids: string[], via: 'save' | 'skip' | 'empty') => {
    const seeded = gridPlayers
      .filter((p) => tierForElo(p.elo, position, fmt) === tier)
      .map((p) => p.id);
    const same =
      ids.length > 0 &&
      ids.length === seeded.length &&
      ids.every((id) => seeded.includes(id));
    track('quickset_step_advanced', {
      position,
      tier_index: tierIdx,
      tier_count: TIERS.length,
      seeded_accepted: same,
      picked_n: ids.length,
      via,
      ms: Date.now() - stepStartRef.current,
    }, 'QuickSetTiers');
    stepStartRef.current = Date.now();
  };
```

| Site | Call |
|---|---|
| `saveMutation.onSuccess` (`:308-319`), **before** `goTo(tierIdx + 1, nextSaved)` | `trackStepAdvanced(ids, 'save');` (`ids` is already destructured from the mutation variables at `:308`) |
| `onSave`'s nothing-picked branch (`:330-336`), before `goTo(tierIdx + 1, savedByTier)` | `trackStepAdvanced([], 'empty');` |
| `onSkip` (`:365`) | rewrite as `const onSkip = useCallback(() => { trackStepAdvanced([], 'skip'); goTo(tierIdx + 1, savedByTier); }, [...]);` |

`onBack` (`:366`) is **not** instrumented — a backward step is not an advance, and
counting it would corrupt the per-rung completion rate this event exists to compute.
The advance is emitted **after a successful save**, not on tap, so a failed save
(`onError` → toast, `:320-322`) never inflates the numerator.

`quickset_step_advanced` stays **INTENT** server-side (§1.4a) — it is real ranking
intent, and it should count toward WAU.

#### 3.6.4 F4 — `quickset_abandoned`

Mark completion inside `goTo`'s done branch, as its **first** statement (`:236`), so
every exit path below it is covered:

```tsx
      if (idx >= TIERS.length) {
        completedRef.current = true;   // P0-7 F4 — walked the ladder; not an abandon
```

Then one effect, declared near the existing focus/footer effects (`:93-98`):

```tsx
  // P0-7 F4 — the drop-off curve. `screen_left` gives dwell but not WHERE
  // in the ladder they stopped, which is the whole question. Fires on
  // blur (the reliable signal: completion navigates to another TAB, which
  // does not unmount this screen) and on unmount, deduped, and only when
  // there is progress to report and the walk did not complete.
  useEffect(() => {
    const fire = (reason: 'nav' | 'background') => {
      if (abandonFiredRef.current || completedRef.current) return;
      const { tierIdx: ti, tiersDone, position: pos } = abandonRef.current;
      if (ti === 0 && tiersDone === 0) return;      // never started — not an abandon
      abandonFiredRef.current = true;
      track('quickset_abandoned', {
        position: pos,
        tier_index: ti,
        tiers_done: tiersDone,
        ms: Date.now() - walkStartRef2.current,
        reason,
      }, 'QuickSetTiers');
    };
    const unsubBlur = navigation.addListener('blur', () => fire('nav'));
    const appSub = AppState.addEventListener('change', (s) =>
      s === 'background' ? fire('background') : undefined,
    );
    return () => {
      unsubBlur();
      appSub.remove();
      fire('nav');                                  // unmount without a blur
    };
  }, [navigation]);
```

`AppState` needs adding to the existing `react-native` import. `NON_INTENT` server-side
(§1.4a): an abandon is an outcome signal, not a reason to count someone as active.

**Position switching** (`onPosition`, `:371-379`) restarts the walk in place without
unmounting or blurring. It therefore does **not** emit an abandon, which is right — the
user is still in Quick Set. `abandonRef` follows `position`, so a later abandon reports
the position they were actually standing in.

### 3.7 Commit 13 — flip `surface` to required

One type change in `SendInSleeperButton.tsx`: `surface?: SendSurface` →
`surface: SendSurface`. **Only after** all four mounts are plumbed — `TradeCard.tsx`
(both, commit 8), `InLeagueCalculator.tsx` (commit 8), `TradesScreen.tsx` (commit 11).
`cd mobile && npx tsc --noEmit` is the acceptance: a missed mount is now a compile error,
which is the enforcement P0-7 wanted and the reason the prop shipped optional first.

If `tsc` is red at commit 13, the correct response is **not** to revert the type — it is
to find the un-plumbed mount, which is exactly the defect the commit exists to surface.
Report it to the orchestrator; do not open `TradesScreen.tsx`.

---

## 4. Handoff notes — one-line props in files this LLD does not own

W2-P07 must **not** open these three files (HLD §4 contention table). The specs below are
what the owning agent applies; they are reproduced here so the owning agent's LLD does
not have to invent them.

| File | Owner / commit | Exact spec |
|---|---|---|
| `mobile/src/components/TradeCard.tsx` (`:577` match variant, `:589` non-match) | **W1-P06**, commit 8 | `surface={variant === 'match' ? 'match' : 'suggested'}` — derived **inside** `TradeCard`, so none of *its* callers changes. Applied in the same edit as P0-6's name props. |
| `mobile/src/components/InLeagueCalculator.tsx` (`:771`) | **W1-P06**, commit 8 | `surface="calculator"` |
| `mobile/src/screens/TradesScreen.tsx` (`:4713`) | **W2-TS**, commit 11 | `surface="deck"` — one line, alongside P0-6's name/opponent props on the same JSX element |

`SendSurface` is declared by W1-P06 in commit 8 as
`type SendSurface = 'deck' | 'match' | 'suggested' | 'calculator';` and exported from
`SendInSleeperButton.tsx`. The four values are the closed enum of
`sleeper_send_attempted.surface` and `sleeper_send_failed.surface`; adding a fifth mount
later means adding a fifth value here and nowhere else.

One further cross-agent note, recorded so nobody adds it defensively: **W2-TS executes
the D2 rename** `celebration_fired` → `celebration_shown` at `TradesScreen.tsx:2547`,
`:3135`, `:3153`. W0-TAX **documents** it in the addendum (§1.5) and adds **no alias**
(S-41). The target name and its props are already registered.

---

## 5. Verification — how each event is proven to land

The Maestro delta is **waived** (scope §3): nothing user-visible changes, and Maestro
asserts on rendered UI — it cannot observe an analytics queue or a `POST /api/events`
batch. The waiver's two conditions are load-bearing: `04-tabs-navigation.yaml` and
`flows/smoke/09-league.yaml` **must pass unmodified** (R12), and verification moves to
the backend tests plus a destination row check.

### 5.1 Automated — the two assertions a default-deny allowlist can fail silently

| Event | Proven by |
|---|---|
| All 15 client names | `test_p0_remediation_events_accepted` — `dropped == 0` **and** exact `set(by_type)` (§1.6). An exact set is the assertion that catches a name that landed as a *different* name. |
| `sleeper_send_succeeded` | `test_record_send_success_writes_server_fired_row` — asserts `event_id IS NULL`, the `league_id`, and the exact props dict (§2.4) |
| Guard still armed | `test_unknown_type_dropped` extended with `"sleeper_send_suceeded"` (§1.6) |
| No device-platform prop | `test_p0_events_reject_device_platform_prop` (§1.6) |
| Server-authoritative names not client-forgeable | `test_sleeper_send_succeeded_is_not_client_submittable` (§1.6) |
| DAU/WAU seam | `test_p0_impression_events_are_non_intent` (§1.7) |
| WAT send leg live | `test_wat_send_leg_is_live` (§1.7) |
| No notification-gating side effect | `test_send_success_does_not_bump_last_trade_proposed_at` (§2.4) |
| Registry drift | The two import-time asserts — get either wrong and the **whole suite fails to import** |
| Mobile | `cd mobile && npx tsc --noEmit`, green at every commit; required-`surface` enforcement at commit 13 |

### 5.2 The test-mode ingest assertion pattern, stated once

Every backend acceptance test above uses the existing `test_events_api.py` harness
verbatim: an isolated in-memory SQLite with **both** `db.engine` and `db.ingest_engine`
patched to the same engine (two `sqlite:///:memory:` engines are different databases),
`analytics_ingest.is_enabled` patched on, `_post()` for the batch, `_rows(engine)` for
the destination, `_assert_invariant(body, N)` for `accepted + deduped + len(rejected) ==
N`. **Do not write a new harness.** The pattern's whole value is that it asserts at the
destination — a 200 at the source is exactly the signal that has lied three times in this
repo.

### 5.3 Manual, on the simulator against a dev backend (both gates on)

1. Tap all five tabs (including a re-tap on the focused one, and the Rank tab in its
   intercepting variant if `rankDest` is unset) → `tab_selected` × N with a mix of
   `refocus` / `intercepted`.
2. Open League Home; tap two hub rows; open League rankings; toggle basis; switch subset
   from both controls; tap a bar and a team row.
3. Enter Quick Set, advance two rungs (one by Save, one by Skip), then leave the screen →
   two `quickset_step_advanced` + one `quickset_abandoned` with `reason: 'nav'`.
4. Wait ≥10 s (`FLUSH_INTERVAL_MS`) **or** background the app to force a flush.
5. At the destination:
   `SELECT event_type, COUNT(*), platform FROM user_events WHERE event_type IN (…) GROUP BY 1,3;`
6. **Assert `platform` is `'ios'`, not NULL** — the direct regression check for the
   incident that motivates the entire prop-spec regime.
7. `GET /api/admin/analytics/health`: `dropped_unknown_type` and `dropped_unknown_prop`
   **flat** across the session. A non-zero bump is the silent-drop signature and is the
   single most important number in this whole verification.
8. **Count `league_view` rows for one League-rankings visit: exactly one** (R11 — the
   screen holds two parallel queries with `placeholderData` and would otherwise
   double-fire).
9. Send leg: a real Sleeper send is ToS-adverse and requires a verified session.
   Verify `sleeper_send_attempted` (tap Send with no linked account → the connect prompt
   path) and `sleeper_send_failed` (force an error). Verify `sleeper_send_succeeded`
   **from prod data after the first real use** rather than manufacturing a send.
10. F1: with the operator's device in `onboarding_v2_rollout`, cold-boot and reach an
    onboarding-gated surface → exactly one `experiment_exposed` per overlaid key, with
    `experiment` / `variant` matching `GET /api/feature-flags`.

### 5.4 The `screen_viewed` verification step (S-38 → C-1)

**No code is written for this.** During the same sim run, confirm at the destination:

- `screen_viewed` rows exist for each of `LeagueHome`, `LeagueRankings`, `Trades`,
  `Rank`, `Matches` — proving `RootNav.tsx:376` fires on tab switches, not only on the
  boot route (`:352`).
- Their `platform` column is `'ios'`, not NULL.
- `dropped_unknown_type` did not move on their account.
- `screen_left` rows carry a plausible non-zero `dwell_ms`.

If all four hold, **time-to-first-value and the LeaguePicker→Trades drop-off are already
readable today**, and P0-9's A6 criterion is satisfiable without any new navigation
instrumentation. Report this to the operator explicitly — it removes a dependency P0-9's
test was said to hang on.

### 5.5 Post-ship metric-seam check

On the analytics dashboard after the deploy: DAU/WAU did **not** step-change on the ship
date (proves §1.4a landed), and WAT's `caveat` flips from `"dark"` to a real value once
the first send lands (proves §1.4b/c). Record both in `TEST_LEDGER.md` with the seam
date.

---

## 6. Deviations

Five, all minor, none reopening a §2 row.

| # | Deviation | From | Why |
|---|---|---|---|
| **D-1** | The name count is **15 client + 1 server**, not the "12 client names + 1 server name + 12 prop rows" in HLD §3's commit-1 row. | HLD §3 table | HLD §4 Wave 0 **enumerates** the names and yields 15; §3's row is stale arithmetic from an earlier draft. §4 is the authority and the operator brief confirms 15. No design change — only the count in a table cell. |
| **D-2** | `quickset_step_advanced` carries **two props beyond plan §6's list**: `via` (`save\|skip\|empty`) and `picked_n`. | plan-p0-7 §6 F3 | Without `via`, the per-rung advance count conflates "saved this tier" with "skipped it" — and "how many rungs get skipped" *is* the grind question. `picked_n` is the tap count per rung, the literal unit of "32 taps". Both are one word each in a frozenset that is being written from scratch in this commit; adding them later would be a taxonomy change. No name changes, no emission-site changes. |
| **D-3** | `experiment_exposed` carries **`key`** (the flag key whose consumption triggered the exposure) and registers but does **not emit** `unit`. | plan-p0-7 §6 F1 | `key` is what makes an exposure auditable back to a surface, and it is the natural output of the provenance mechanism the HLD mandated. `unit` is not derivable client-side — `GET /api/feature-flags` returns merged `experiments`/`configs` without the `unit_type` that `experiments.resolve_for_unit` knew server-side. Registering-but-not-emitting follows S-33's "never guess a prop" while keeping the future server-side fix out of the taxonomy. |
| **D-4** | P0-6's handoff events **`send_unavailable_shown`** and **`trade_copied`** are **not registered**. | plan-p0-6 §9 | HLD §4 Wave 0's name list does not include them, and §1.4/S-23 forbids P0-7 firing anything on `SendInSleeperButton`'s render path — which is exactly where `send_unavailable_shown` would live. Measuring whether the copy fallback gets used is a real question; it goes to `NEXT.md` with the P0-6 rows, and is named in the addendum's deliberately-NOT-here section so the omission reads as a decision. |
| **D-5** | `SubsetControl`'s `onSwitch` signature widens by one parameter, and `switchSubset` gains a defaulted second parameter. | plan-p0-7 §2 ("`source` threaded through `SubsetControl.onSwitch`") | The plan named the requirement but not the shape. This is the minimum: additive, defaulted, every existing call site compiles unchanged. The alternative — two wrapper closures at the two mount sites — duplicates the guard logic that `switchSubset` already owns. |

**Explicitly *not* deviated from:** the reserved `sleeper_send_*` names (S-30);
OPTIONAL-A in (S-31); the mandatory `NON_INTENT` additions (S-32); `is_self` omitted
(S-33); no `last_trade_proposed_at` bump (S-34); the `_record_send_success` extraction
(S-35); taxonomy first and alone (S-36); F1/F3/F4 in and F2 out (S-37); `screen_viewed`
verification-only (S-38); no alias for `celebration_fired` (S-41); no flag defaults
changed anywhere (S-44).
