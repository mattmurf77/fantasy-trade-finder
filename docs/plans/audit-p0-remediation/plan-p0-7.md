# P0-7 — Targeted analytics additions (navigation · League surfaces · Send-in-Sleeper)

> **Status:** plan only — no code written. Re-verified against worktree
> `ftf-p0-remediation` @ `ab9368f` (branch `p0-remediation-2026-08-10`).
> **Source:** audit `04-priority-backlog.md` §P0-7, `06-resolutions.md` §P0-7.
> **Gate posture:** full gates. Root `CLAUDE.md` bright line — *"a change touching
> schema, API contracts, feature-flag surfaces, or **analytics events** is not a
> quick fix."* Operator has confirmed. Scope block: [`scope-p0-7.md`](scope-p0-7.md).

## Contents

- [1. Verified current state](#1-verified-current-state)
- [2. Event spec](#2-event-spec)
- [3. Server registration change](#3-server-registration-change)
- [4. Exact change list](#4-exact-change-list)
- [5. Surface changes](#5-surface-changes)
- [6. Optional — P0-9 first-session funnel events](#6-optional--p0-9-first-session-funnel-events)
- [7. Maestro delta](#7-maestro-delta)
- [8. Docs impact](#8-docs-impact)
- [9. Test plan](#9-test-plan)
- [10. Risks, collisions, open questions](#10-risks-collisions-open-questions)

---

## 1. Verified current state

### 1.1 Client plumbing — exists and is healthy

| Piece | Location | State |
|---|---|---|
| Client SDK | `mobile/src/api/events.ts:188` `track(eventType, props?, screen?)` | Live. Queue + backoff + AsyncStorage persistence. Fire-and-forget, swallows all errors. |
| Emission gate | `events.ts:52` `FLAG_KEY = 'analytics.client_events'`; `flagEnabled()` at `:112` | **`config/features.json` → `analytics.client_events = True`** (verified). `undefined = off` by design. |
| Ingest gate | `backend/analytics_ingest.py` / `POST /api/events` | **`analytics.ingest = True`** (verified). Both sides on — G-017's paired-gate trap is not currently armed, but see §9. |
| Screen views | `RootNav.tsx:352` (boot) and `:376` (`onStateChange`) fire `screen_viewed`; `:181` and `:365` fire `screen_left` with real `dwell_ms` | Live for **every** route, including `LeagueHome` / `LeagueRankings`. This is why P0-7 is *targeted additions*, not "instrument navigation from zero". |
| Transport-failure signal | `mobile/src/api/client.ts:371` fires `api_request_failed` on every failed `apiRequest` | Live. Covers `/api/trades/propose` network/timeout failures already. |

**Platform property handling — the load-bearing detail.** `platform` is **not an event
prop**. It is a *column* on `user_events`, derived server-side in
`analytics_ingest.py:365-368` from the batch body's `platform` field, falling back to
`X-Device` → `device_type`. `events.ts:285` spreads `getClientHeaders()` into every
`POST /api/events` so those headers are always present — the fix for the pre-2026-08-05
NULL-`platform` bug documented in that file's own comment (*"landed every client event
with those columns NULL, which blinded per-platform and per-release reporting"*) and
cited in `analytics_taxonomy.py:262` as the reason prop specs exist at all.

**Consequence for this plan:** no new event carries a device-`platform` prop. Where a
*league* platform is wanted (`sleeper`/`espn`/`mfl`/`fleaflicker`) the prop is named
`platform` to match the existing `league_selected` precedent
(`analytics_taxonomy.py:185`) — and the ambiguity is called out explicitly in the
tracking-plan addendum so no analyst confuses the two.

### 1.2 Server allowlist mechanism — default-deny, two registries, import-time asserts

`backend/analytics_taxonomy.py` is the single source of truth. Three enforcement points:

1. **`ALLOWED_CLIENT_EVENTS`** (`:38-99`) — `analytics_ingest.py:379-383`: an event whose
   `event_type` is not in this frozenset is `_health_bump("dropped_unknown_type")`,
   counted as **accepted and dropped**, and returns 200. *Silent by contract.* This is
   the trap the build handoff warns about.
2. **`CLIENT_EVENT_PROPS`** (`:165-255`) — `analytics_ingest.py:384-389`: unknown prop
   keys are **stripped** (event still lands). An allowlisted event with **no**
   `CLIENT_EVENT_PROPS` entry raises `ValueError` at **import** (`:327-332`) — i.e. the
   app fails to boot. Both registries are mandatory, together.
3. **Namespace disjointness** (`:298-322`) — `_assert_namespaces_disjoint` raises at
   import if a client name collides with `SERVER_FIRED_EVENTS ∪ _EVENT_TO_USER_COL ∪
   _RANK_STREAK_EVENTS`. A collision crashes the app at boot.

Server-fired events go in **`SERVER_FIRED_EVENTS`** (`:105-136`) and are written with
`database.record_event(user_id, event_type, league_id=…, source=…, props=…)`
(`database.py:2592`). `record_event` swallows its own failures. An event_type absent from
`_EVENT_TO_USER_COL` (`database.py:2518`) simply gets no denorm-column bump — safe.

**Downstream registry that also matters:** `backend/analytics_queries.py:64` —
`INTENT_EVENTS = (SERVER_FIRED_EVENTS | ALLOWED_CLIENT_EVENTS) - NON_INTENT_EVENTS`.
Taxonomy growth is **intent-by-default**, so every new name silently enters DAU / WAU /
retention / churn unless it is added to `NON_INTENT_EVENTS` (`:60-63`). This is a real
metric hazard and §3 handles it.

### 1.3 The three surfaces, as they stand today

**Navigation — `mobile/src/navigation/TabNav.tsx`.** Five `Tab.Screen`s: `Rank` (`:608`),
`Trades` (`:647`), `Draft` (`:689`, conditional on `draft.tab` read once at mount, `:582`),
`Matches` (`:709`), `League` (`:729`). **Every one already has a `tabPress` listener** —
they do prefetch and re-tap-pop work. Rank has *two* listener variants (`:623` normal
tab behaviour when `rankDest`; `:636` the intercepting variant that `e.preventDefault()`s
and opens the Rank action sheet). Zero `track()` calls in the file. Adding `tab_selected`
is a one-line insert per existing handler — no new handlers.

**`mobile/src/screens/LeagueScreen.tsx`** (1 195 lines, route `LeagueHome`). Zero
`track()`. It is a hub: `goRank`/`goFindTrade` (`:366-367`), Matches tiles (`:511`,
`:518`), Explore rows to `LeagueRankings` (`:540`), `FreeAgents` (`:548`), `DraftRoom`
(`:564`), rookie board (`:568`), `PickAssignment` (`:598`), plus ESPN re-sync (`:744`).
Primary query `summaryQuery` at `:167`.

**`mobile/src/screens/LeagueSummaryScreen.tsx`** (2 347 lines — confirmed the
season-outlook v2 growth; the new layer is `SeasonOutlookSection` / `OutlookUnsupportedRow`
rendered at `:860`+ behind `oddsEnabled = useFlag('outlook.odds')`, `:424`). Zero
`track()`. Registered under **two route names**: `LeagueRankings` (League-tab root) and
legacy root-stack `LeagueSummary`; `isTabRoot` is computed at `:362` from
`useRoute().name`. Interaction choke points, all verified:

| Interaction | Choke point | Notes |
|---|---|---|
| Basis toggle | `setBasis('consensus')` `:835`, `setBasis('personal')` `:841` | Two call sites, no helper yet. `BasisChip` redraft is `disabled`, no handler. |
| Subset change | **`switchSubset(s)` `:746`** | Single helper already, called by *both* `SubsetControl` instances (`:946` chart, `:1160` drill-in roster). The auto-fallback at `:466` calls `setSubset` **directly**, so it will not emit — correct. |
| Team drill-in | `setSelectedId(id)` `:1048` (bar column), `setSelectedId(r.tc.team.user_id)` `:1294` (team row) | Two sites. `setSelectedId(null)` `:904` closes. |
| Position filter | `togglePos(setPosFilter)` `:958`, `:1166` | **Out of scope** — the resolutions doc lists basis / subset / drill-in only. |

`outlook.odds = False` in `config/features.json` (verified) — the season-outlook layer is
**dark**. Instrumenting it with dedicated events would produce zero rows; §2 carries it as
a single boolean prop on `league_view` instead.

**`mobile/src/components/SendInSleeperButton.tsx`** (291 lines). Zero `track()`. Four
mount sites: `TradesScreen.tsx:4713` (deck), `InLeagueCalculator.tsx:771` (calculator),
`TradeCard.tsx:577` (`variant === 'match'`) and `:589` (non-match). Flow:
`onPress` `:231` → guard `state !== 'idle'` → no-league fallback `openInSleeper()` `:239`
→ link check → `confirmSend()` `:198` → `doPropose()` `:117` → success `:127` or the
error ladder `:143-191`.

**Server side is genuinely blind.** `/api/trades/propose` (`server.py:12294`) has **no**
`record_event` on any path — verified by reading the success path at `:12404`, whose only
side effect is `_save_deck_outcome_safe(…, "propose")`. The closed error enum is:

```
test_mode_propose_disabled · feature_disabled · no_user · verification_required
bad_request · sleeper_not_linked · sleeper_unconfigured · sleeper_expired
roster_not_found · opponent_roster_not_found · sleeper_rejected · sleeper_write_failed
```

### 1.4 The finding that changes the naming — reserved names already exist

`backend/analytics_queries.py:52-53`:

```python
WAT_DARK = frozenset({"sleeper_send_attempted", "sleeper_send_succeeded",
                      "sleeper_send_failed"})
```

The north-star metric **Weekly Active Traders** already reserves these three names, and
they are referenced in three more places: `FUNNEL_STAGES` stage 8 (`:79`),
`FEATURE_VERTICALS["send_in_sleeper"]` (`:95`), and an unconditional dark caveat at
`:497` reading *"send-leg WAT events not in taxonomy yet"*. Tracking plan v2 §S3 (`:76`)
specs `sleeper_send_attempted/succeeded/failed` by name, and
`docs/business/analytics/2026-08-05-trade-impact-and-rank-integrity.md:40` calls them
**"the single highest-value instrumentation gap."**

> **Recommendation: adopt `sleeper_send_*`, not the resolutions doc's
> `send_in_sleeper_*`.** Same three events, same cost — but using the reserved names
> lights up the north-star send leg, funnel stage 8, and the `send_in_sleeper` feature
> vertical for free. Using new names would leave all four permanently dark while the
> data sits one alias away. This is the only place this plan deviates from the wording in
> `06-resolutions.md`, and it deviates *toward* an existing spec, not away from one.

---

## 2. Event spec

Naming convention (tracking plan v2 §S3): `object_action`, snake_case, **past tense**.

### Addition 1 — navigation

| Event | Props (type) | Trigger | Client | Screen arg |
|---|---|---|---|---|
| `tab_selected` | `tab` str ∈ `rank\|trades\|draft\|matches\|league`; `from_tab` str\|null (focused tab at press time); `refocus` bool (`navigation.isFocused()` — a re-tap, not a switch); `intercepted` bool (true only on the Rank action-sheet variant, which `preventDefault()`s) | First statement inside each existing `tabPress` handler — **before** `preventDefault()`, prefetch or pop, so an intercepted tap is still counted | `TabNav.tsx` | omitted (no route context in a tab listener; `screen_viewed` supplies the destination) |

`from_tab` derivation: `const st = navigation.getState(); st?.routes?.[st.index]?.name?.toLowerCase() ?? null`. Optional-chained throughout — a null is honest, a throw is not (and `track` swallows anyway).

### Addition 2 — League surfaces

| Event | Props (type) | Trigger | Client | Screen arg |
|---|---|---|---|---|
| `league_view` | `surface` str ∈ `league_home\|league_rankings`; `state` str ∈ `ready\|empty\|error\|no_league`; `platform` str ∈ `sleeper\|espn\|mfl\|fleaflicker\|unknown` (**league** platform, not device); `team_count` int\|null; `basis` str\|null; `subset` str\|null; `starters_available` bool\|null; `outlook_shown` bool\|null; `is_tab_root` bool | Once per mount, from a `useEffect` guarded by a `firedRef`, when the primary query first settles (`query.isFetched`) or immediately when there is no `leagueId` | `LeagueScreen.tsx` (surface `league_home`, primary query `summaryQuery`) and `LeagueSummaryScreen.tsx` (surface `league_rankings`, primary query `query`) | `route.name` (`LeagueHome` / `LeagueRankings` / legacy `LeagueSummary`) |
| `league_basis_changed` | `basis` str ∈ `consensus\|personal`; `from` str; `boards_differ` bool; `team_focused` bool (drill-in open) | New `changeBasis(b)` helper (mirrors the existing `switchSubset` shape) called by both `BasisChip`s. **Guarded:** returns early when `b === basis`, so no no-op rows | `LeagueSummaryScreen.tsx` | `route.name` |
| `league_subset_changed` | `subset` str ∈ `all\|starters\|bench`; `from` str; `source` str ∈ `chart\|roster`; `filter_count` int (`posFilter.size`); `picks_stripped` bool (the flag-OFF PICKS strip actually fired) | Inside the existing `switchSubset` `:746`, guarded on `s !== subset`. The `:466` auto-fallback calls `setSubset` directly and is deliberately silent | `LeagueSummaryScreen.tsx` | `route.name` |
| `league_team_opened` | `via` str ∈ `bar\|row`; `rank` int (1-based); `basis` str; `subset` str; `filter_count` int; `is_self` bool *(omit the prop entirely if session-user↔`team.user_id` identity cannot be resolved — never guess)* | New `openTeam(id, via, rank)` helper called from `:1048` and `:1294` | `LeagueSummaryScreen.tsx` | `route.name` |
| **OPTIONAL-A** `league_home_action_tapped` | `action` str ∈ `rank\|find_trades\|matches_mutual\|matches_awaiting\|rankings\|free_agents\|draft_room\|rookie_board\|draft_picks\|whats_new\|members\|espn_resync` | Each hub row/tile `onPress` on `LeagueHome` | `LeagueScreen.tsx` | `'LeagueHome'` |

> **OPTIONAL-A is an orchestrator call.** `06-resolutions.md` lists exactly four League
> interactions (view, basis, subset, drill-in) and three of those live on
> `LeagueSummaryScreen`. Without OPTIONAL-A, `LeagueScreen` gets a mount event and nothing
> else, which arguably under-delivers *"mount **and interaction** events on **both**
> League screens."* With it, League Home's exit paths become readable — which is the one
> question that screen exists to answer. It is ~11 one-line inserts and one registry row.
> Drop it cleanly by deleting one taxonomy entry and one props entry.

### Addition 3 — Send in Sleeper

**Split design (recommended):** attempt + failure **client**-fired, success
**server**-fired.

| Event | Props (type) | Trigger | Client | Screen arg |
|---|---|---|---|---|
| `sleeper_send_attempted` | `surface` str ∈ `deck\|match\|suggested\|calculator`; `give_n` int; `receive_n` int; `from_deck` bool (`!!impressionId`); `has_target` bool (`!!leagueId && !!theirUserId` — false ⇒ the `openInSleeper()` handoff, not a real send) | Top of `onPress` (`SendInSleeperButton.tsx:231`), immediately after the `state !== 'idle'` guard and before `haptics.pickup()` | `SendInSleeperButton.tsx` (**client**) | omitted (component is screen-agnostic; `surface` is the dimension that matters) |
| `sleeper_send_failed` | `surface` str; `error_code` str (closed enum, §1.3 ∪ `network` \| `timeout` \| `unknown`); `status` int\|null; `kind` str\|null (`SleeperWriteError.kind`, present on `sleeper_rejected` / `sleeper_write_failed`); `give_n` int; `receive_n` int; `from_deck` bool | First statement in the `doPropose` catch block (`:143`), before the alert ladder | `SendInSleeperButton.tsx` (**client**) | omitted |
| `sleeper_send_succeeded` | `give_n` int; `receive_n` int; `pick_n` int; `from_deck` bool; `transaction_id` str\|null | `/api/trades/propose` success path, `backend/server.py:~12404`, next to `_save_deck_outcome_safe(…, "propose")`. `record_event(user_id, "sleeper_send_succeeded", league_id=league_id, source="api", props=…)` | **server** (`event_id` NULL, not client-forgeable) | n/a |

`error_code` derivation in the catch:

```
err instanceof ApiError
  ? (err.isTimeout ? 'timeout' : ((err.body as any)?.error ?? 'unknown'))
  : 'network'
```

Bounded cardinality: 12 server codes + 3 client-synthetic = 15 values, forever.

**Why the split** (three options were weighed):

- **A — attempted client, succeeded + failed server.** Loses `surface` on the outcome legs
  and cannot see network failures or the pre-identity returns (`feature_disabled`,
  `no_user`, `test_mode_propose_disabled` all return before `user_id` is resolved, and
  `record_event` requires a `user_id`). Would need failure plumbing at 12 return sites.
- **B — all three client.** One code site, `surface` everywhere — but
  `sleeper_send_succeeded` becomes client-forgeable while sitting in WAT and funnel stage
  8 alongside server-authoritative `trade_ratified`, and a lost SDK queue silently
  undercounts the north star.
- **C — attempted + failed client, succeeded server. ← recommended.** Success stays
  authoritative where the server has the truth; failures stay complete (including
  network, timeout and every pre-identity refusal, all of which the client's `ApiError`
  sees) and carry `surface`. Server cost is **three lines**. Namespaces stay disjoint —
  the three names are distinct, so the import-time assert is satisfied.

**`surface` plumbing.** New required prop on `SendInSleeperButton`. Three caller edits:
`TradesScreen.tsx:4713` → `surface="deck"`; `InLeagueCalculator.tsx:771` →
`surface="calculator"`; `TradeCard.tsx:577`/`:589` → `surface={variant === 'match' ? 'match' : 'suggested'}` (derived
inside `TradeCard`, so no change reaches *its* callers).

**Deliberately NOT instrumented** (minimality — three additions, not a programme): the
confirm-dialog cancel, the pre-flight `validateTradeSend` warning branch (`:208`), the
`goConnect` round-trip and its focus-handler outcome (`:77-103`). Named here so a future
session sees these were considered, not overlooked. A19 in the P1 backlog already owns
the Sleeper Connect flow's four events.

---

## 3. Server registration change

**Do this first, in its own commit, before a single `track()` call is wired.** The
allowlist is default-deny and its failure mode is a silent 200.

### 3.1 `backend/analytics_taxonomy.py`

**(a) `ALLOWED_CLIENT_EVENTS` (`:38-99`)** — append a new commented block before the
closing brace:

```python
    # P0-7 remediation (docs/plans/audit-p0-remediation/plan-p0-7.md; addendum
    # docs/business/analytics/2026-08-11-p0-7-addendum.md). Navigation +
    # League-surface + Sleeper-send instrumentation. `tab_selected` and
    # `league_view` are ALSO added to analytics_queries.NON_INTENT_EVENTS —
    # they are impression-class and must not inflate DAU/WAU.
    "tab_selected",
    "league_view", "league_basis_changed", "league_subset_changed",
    "league_team_opened",
    # OPTIONAL-A — drop this line and its CLIENT_EVENT_PROPS row together.
    "league_home_action_tapped",
    # Send-in-Sleeper: the ATTEMPT and the FAILURE are client-only signals
    # (a tap that never reaches the server, a network/timeout error, and the
    # pre-identity refusals the server cannot attribute to a user). The
    # SUCCESS is server-fired — see SERVER_FIRED_EVENTS below.
    "sleeper_send_attempted", "sleeper_send_failed",
```

**(b) `SERVER_FIRED_EVENTS` (`:105-136`)** — in the `# Trades` block:

```python
    # P0-7 — the north-star send leg (analytics_queries.WAT_DARK reserved
    # these names on 2026-07-17 and nothing ever fired them). Server-fired
    # because /api/trades/propose is the only place the send is KNOWN to have
    # landed in Sleeper; a client-forgeable success would sit in WAT and
    # funnel stage 8 next to server-authoritative trade_ratified.
    "sleeper_send_succeeded",
```

**(c) `CLIENT_EVENT_PROPS` (`:165-255`)** — one row per new **client** event
(a missing row raises at import and the app will not boot):

```python
    # ── P0-7 remediation ────────────────────────────────────────────────
    # NOTE `platform` here is the LEAGUE platform (sleeper/espn/mfl/
    # fleaflicker), matching league_selected's precedent — NOT the device
    # platform, which is a user_events COLUMN derived from the X-Device
    # headers in analytics_ingest (the NULL-`platform` incident).
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
    "league_team_opened":      frozenset({"via", "rank", "basis", "subset",
                                          "filter_count", "is_self"}),
    "league_home_action_tapped": frozenset({"action"}),   # OPTIONAL-A
    "sleeper_send_attempted":  frozenset({"surface", "give_n", "receive_n",
                                          "from_deck", "has_target"}),
    "sleeper_send_failed":     frozenset({"surface", "error_code", "status",
                                          "kind", "give_n", "receive_n",
                                          "from_deck"}),
```

**(d) Disjointness — pre-verified.** None of the eight new client names appears in
`SERVER_FIRED_EVENTS`, `_EVENT_TO_USER_COL` (`database.py:2518-2534`) or
`_RANK_STREAK_EVENTS`. `sleeper_send_succeeded` is server-only and is **not** added to
the client allowlist. The import-time assert will pass.

**(e) `FUNNEL_CRITICAL` — no change.** None of these is a pre-auth funnel primitive.

### 3.2 `backend/analytics_queries.py` — three edits, all metric-integrity

**(a) `NON_INTENT_EVENTS` (`:60-63`)** — *required, not optional*:

```python
    # P0-7: a tab tap and a screen mount are navigation/impression class.
    # INTENT is a deny-list (line 64), so without these two lines DAU/WAU
    # would jump to ~app-open count on the day this ships and every
    # retention/churn series would break at that seam.
    "tab_selected", "league_view",
```

The other five League events **stay INTENT** — a basis toggle or a team drill-in *is* a
user acting on the product. This still produces a genuine, desirable step in WAU (a
league-browsing user now counts). Note the seam date in the addendum.

**(b) `WAT_LIVE` / `WAT_DARK` (`:51-54`)** — the send leg is no longer dark:

```python
WAT_LIVE = frozenset({"trade_proposed", "match_swiped", "calc_trade_evaluated",
                      # P0-7 — the send leg, live 2026-08-11 onward. Historical
                      # rows carry none of these names, so past WAT is unchanged;
                      # only the forward series gains the leg.
                      "sleeper_send_attempted", "sleeper_send_succeeded",
                      "sleeper_send_failed"})
WAT_DARK = frozenset()
```

**(c) The unconditional dark caveat (`:497-498`)** currently asserts *"send-leg WAT
events not in taxonomy yet"* — false the moment 3.1 lands. Make it conditional on an
actual `is_dark(conn, {"sleeper_send_succeeded", …}, start_day, end_day)` check, or delete
it. Leaving a stale caveat is exactly the A-33 failure class (a comment contradicting
runtime).

`FUNNEL_STAGES` stage 8 and `FEATURE_VERTICALS["send_in_sleeper"]` need **no** edit —
they already reference `sleeper_send_succeeded` and light up on their own.

### 3.3 Tracking-plan addendum — the precondition the registries' own comments demand

New file `docs/business/analytics/2026-08-11-p0-7-addendum.md`, following the shape of
`2026-08-06-draft-room-w1-addendum.md` verbatim: parent link to tracking plan v2 §S3, the
default-deny paragraph, a "Why now" section, the event table, and a **"What is
deliberately NOT here"** section (position filter, drill-in close/dwell, confirm-dialog
cancel, connect round-trip, season-outlook interactions while `outlook.odds` is dark).
Must also record: the `sleeper_send_*` vs `send_in_sleeper_*` naming decision, the
league-`platform`-vs-device-`platform` distinction, and the DAU/WAU seam date.

---

## 4. Exact change list

Ordered. Steps 1–3 are a standalone commit that ships **before** any client wiring —
that ordering is the whole point of this finding.

| # | File | Change |
|---|---|---|
| 1 | `backend/analytics_taxonomy.py` | §3.1 (a)(b)(c) — 8 client names, 1 server name, 8 prop rows |
| 2 | `backend/analytics_queries.py` | §3.2 (a)(b)(c) — NON_INTENT, WAT_LIVE/DARK, dark caveat |
| 3 | `docs/business/analytics/2026-08-11-p0-7-addendum.md` | new — §3.3 |
| 4 | `backend/tests/test_events_api.py` | new test: all 7 new client events accepted with full props (§9) |
| 5 | `backend/tests/test_analytics_p0.py` | extend `test_live_taxonomy_is_disjoint` membership assertion with the new names |
| 6 | `backend/server.py` `:~12404` | `record_event(user_id, "sleeper_send_succeeded", league_id=league_id, source="api", props={…})` in a `try/except` mirroring the `trades_generated` site at `:5232-5240` |
| 7 | `mobile/src/navigation/TabNav.tsx` | one `track('tab_selected', …)` per existing `tabPress` (6 handlers: Rank×2, Trades, Draft, Matches, League) + `import { track } from '../api/events'` |
| 8 | `mobile/src/screens/LeagueScreen.tsx` | `league_view` mount effect (+ OPTIONAL-A `league_home_action_tapped` on ~11 handlers) |
| 9 | `mobile/src/screens/LeagueSummaryScreen.tsx` | `league_view` mount effect; `changeBasis()` helper wired to both `BasisChip`s; `track` inside `switchSubset`; `openTeam()` helper at the two `setSelectedId` sites; `source` threaded through `SubsetControl.onSwitch` |
| 10 | `mobile/src/components/SendInSleeperButton.tsx` | required `surface` prop; `sleeper_send_attempted` in `onPress`; `sleeper_send_failed` in the `doPropose` catch |
| 11 | `mobile/src/screens/TradesScreen.tsx` `:4713` | add `surface="deck"` (**one line — see §10 collision**) |
| 12 | `mobile/src/components/InLeagueCalculator.tsx` `:771` | add `surface="calculator"` |
| 13 | `mobile/src/components/TradeCard.tsx` `:577`, `:589` | add `surface={variant === 'match' ? 'match' : 'suggested'}` |
| 14 | `docs/cross-client-invariants.md` §"Client analytics event contract" | note the P0-7 additions + the addendum link |
| 15 | `docs/data-dictionary.md` `user_events` "Trade:" bullet (~`:721`) | add `sleeper_send_succeeded` with its props |

**Zero UI change. Zero new testIDs. Zero route changes. Zero schema change.**
`user_events` already stores every one of these; no migration.

---

## 5. Surface changes

**Analytics events: YES.** Complete enumeration of every new name:

**Client-fired (7, or 6 without OPTIONAL-A) — `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS`:**

1. `tab_selected`
2. `league_view`
3. `league_basis_changed`
4. `league_subset_changed`
5. `league_team_opened`
6. `league_home_action_tapped` *(OPTIONAL-A)*
7. `sleeper_send_attempted`
8. `sleeper_send_failed`

**Server-fired (1) — `SERVER_FIRED_EVENTS`:**

9. `sleeper_send_succeeded`

**Other surfaces:** API routes — none added or contract-changed (`POST /api/events`
accepts new names purely by registry membership; `/api/trades/propose` gains a
side-effect only). Feature flags — none added; behaviour rides the existing
`analytics.client_events` + `analytics.ingest` pair. Schema — none. Env vars — none.
UI — none.

---

## 6. Optional — P0-9 first-session funnel events

> **Separable section.** Include or drop wholesale; nothing in §§1–5 depends on it. This
> exists because the build handoff (`07-build-handoff-prompt.md:127`) surfaces the P0-7 ↔
> P0-9 dependency: a trades-first-vs-quickset test that cannot be read is not a test.
> A second agent is planning the P0-9 test-prep with flags OFF.

**Good news first — most of the first-session funnel already exists and is registered.**
Verified live in the taxonomy today: `signin_attempted/_succeeded/_failed`,
`league_selected`, `demo_entered`, `rank_method_selected`, `find_trades_tapped`,
`trade_card_viewed` (**already carries `ms_since_open` and `cold_start`, so
time-to-first-trade-viewed is derivable with no new event**), `deck_card_viewed`,
`first_session_like` / `_deck_completed` / `_adaptation_shown` (`deck.first_session` is
**ON**), `quickset_prompt_shown/_accepted/_snoozed`, the five `guide_*` events, and
server-fired `quickset_completed` (`position, players_placed, duration_ms, skipped`),
`quickrank_completed`, `trades_generated`, `ranking_complete_first_time`.

Four genuine gaps remain, in strict priority order:

| # | Event | Props | Trigger / client | Why the test is unreadable without it |
|---|---|---|---|---|
| **F1** | `experiment_exposed` | `experiment` str; `variant` str; `unit` str ∈ `account\|device` | Client, at first render of an experiment-gated surface | **This is the one that matters.** It is already in `FUNNEL_CRITICAL` (`analytics_taxonomy.py:146`) and in the mobile SDK's mirror (`events.ts:70`) — but it is **NOT in `ALLOWED_CLIENT_EVENTS`**, so if anything fired it today it would be silently dropped. Prior art of the exact trap, sitting in the repo right now. `backend/experiments.py:620,723` currently uses *assignment as an exposure proxy* and reports dilution. An A/B read on assignment rather than exposure is diluted by every user who never saw the surface — which, for a first-session test, is a large and *arm-correlated* fraction. |
| **F2** | `first_session_started` | `entry` str ∈ `quickset\|trades\|league_picker\|rank_home`; `arm` str\|null | Client, once per device on the first authed screen after league selection | Names the arm at the funnel's origin. Without it, arm attribution is a server-side join against assignment tables at read time — doable but fragile, and it cannot see the pre-auth leg. |
| **F3** | `quickset_step_advanced` | `position` str; `tier_index` int; `tier_count` int; `seeded_accepted` bool (the user tapped Continue without changing the pre-seeded tier); `ms` int | Client, `QuickSetTiersScreen` per Continue/save tap | `quickset_completed` is fired **per completed position**. A user who does three tiers of QB and quits is completely invisible. The whole P0-9 question is *"is 32 taps a grind?"* — that is a **per-step** question, and `seeded_accepted` is precisely the operator's fairness point (the audit notes cards arrive pre-seeded, so a tier can clear in one tap). |
| **F4** | `quickset_abandoned` | `position` str; `tier_index` int; `tiers_done` int; `ms` int; `reason` str ∈ `nav\|background` | Client, `QuickSetTiersScreen` unmount / background with progress > 0 and completion not reached | The drop-off curve itself. `screen_left` gives dwell but not *where in the ladder* they stopped. |

Registration cost is identical in kind to §3: names into `ALLOWED_CLIENT_EVENTS`, rows
into `CLIENT_EVENT_PROPS`, an addendum section. `experiment_exposed`,
`first_session_started` and `quickset_abandoned` are impression/outcome class and should
join `NON_INTENT_EVENTS`; `quickset_step_advanced` is real ranking intent and should not.

**If the orchestrator includes only one item from this section, make it F1.**

---

## 7. Maestro delta

**Waived — with reasoning, per the `CLAUDE.md` §Conventions waiver convention.**

`CLAUDE.md` requires *"every user-visible mobile change ships a new/extended flow in
`mobile/.maestro/` (or a written waiver in the scope block)."* This change is
**not user-visible**: no rendered element, copy, layout, colour, timing or navigation
behaviour changes anywhere. Every insertion is either a `track()` call (fire-and-forget,
returns `void`, swallows every error by contract — `events.ts:209`) or a pass-through
prop. Maestro asserts on rendered UI; it has no visibility into an analytics queue and
cannot observe a `POST /api/events` batch. A Maestro flow here would assert the *absence*
of a regression, which the existing smoke suite already does.

Two consequences that make the waiver defensible rather than convenient:

1. **The existing flows still have to pass, unchanged and unmodified.** They are the
   regression proof — specifically `04-tabs-navigation.yaml` (drives every `tabPress`
   handler this change edits) and `smoke/09-league.yaml` (mounts both League screens).
   Any diff to those flows invalidates the waiver.
2. **Verification moves to the backend + a manual sim observation** (§9). The events are
   proven by rows landing in `user_events`, not by pixels.

**No `testID`s added or renamed** ⇒ `mobile/scripts/testid-lint.sh` is unaffected.
**No capture delta** ⇒ no `screen-capture.sh` run.

**Sim-gate tier: 2** (`docs/runbook.md` §Pre-ship simulator gate — *"Mobile logic touched,
no UI change"*): the feature has no own flow, so run the affected smoke subset —
`04-tabs-navigation`, `smoke/09-league`, `smoke/05-trades-render`, `smoke/06-trades-deck`,
`smoke/07-calculator` — plus `mobile/scripts/screen-freshness.sh`, re-capturing only what
it flags (expected: nothing). Log in `TEST_LEDGER.md`, write `qa/sim-runs/last-sim-run.json`.

> An argument exists for tier 1: `TabNav.tsx` is navigation. It is answered by the fact
> that no *navigation behaviour* changes — the handlers already exist and keep their
> exact control flow, including the Rank variant's `preventDefault()`. If the orchestrator
> prefers tier 1, that is an operator-recordable deviation, not a correction.

---

## 8. Docs impact

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| **`docs/business/analytics/2026-08-11-p0-7-addendum.md`** — **the load-bearing row** | **NEW (mandatory)** | The tracking plan is the *precondition* the registry comments demand (`analytics_taxonomy.py:9-10` — *"New client event types require a tracking-plan addendum first"*). Parent: tracking plan v2 §S3. Must record the `sleeper_send_*` naming decision, the league-vs-device `platform` distinction, and the DAU/WAU seam date. |
| `docs/cross-client-invariants.md` §"Client analytics event contract" (`:268`) | Updated | That section already states event names are *"shared verbatim by every client SDK … and the backend allowlist. Changing either side alone breaks ingestion silently."* Add the eight new names + addendum link. Web (`web/js/events.js`) and extension (`extension/background.js`) fire **none** of them — noted explicitly so the omission reads as deliberate. |
| `docs/data-dictionary.md` `user_events` (`:691`, "Trade:" bullet ~`:721`) | Updated | `sleeper_send_succeeded` is a stored server-fired event_type; the file's own rule (`:264`) is *"when adding a new event_type, add it to that list."* Client events land in the same table but are documented via the taxonomy + addendum, matching how `guide_*` and `draft_room_*` were handled. |
| `docs/api-reference.md` | n/a | No route added, renamed, removed or contract-changed. `POST /api/events` accepts new names by registry membership alone; its request/response shape is untouched. `/api/trades/propose` gains a side effect, not a contract change. |
| `living-memory/LLD.md` | n/a | No schema/route/invariant *convention* shifts. The default-deny-then-wire ordering is an existing convention this plan obeys, not a new one. |
| `docs/architecture.md` | n/a | No module wiring or data-flow change; every new call uses existing paths (`track` → queue → `/api/events`; `record_event` → `user_events`). |
| `living-memory/HLD.md` | n/a | No architectural shift. |
| `docs/glossary.md` | n/a | No new domain term (`basis`, `subset`, `WAT` all already defined). |
| `docs/config-reference.md` | n/a | No flag, env var or `model_config` key added. |
| ADR / `living-memory/DECISIONS.md` | **`DECISIONS.md`, next id `D-011`** | Two non-obvious choices worth the record: (1) adopting the reserved `sleeper_send_*` names over the resolutions doc's `send_in_sleeper_*`, lighting up WAT/funnel-8/feature-vertical; (2) the client/server split — success server-authoritative, attempt and failure client-side. |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | On ship | Per `CLAUDE.md` §Session memory. TEST_LEDGER must carry the tier-2 sim run **and** the row-landed verification from §9.3. |
| `living-memory/GOTCHAS.md` | Conditional | Only if §9.3's end-to-end check surprises. G-017 (paired gates fail silently) already covers the known trap. |

---

## 9. Test plan

### 9.1 Backend — allowlist acceptance (the actual failure mode)

The precedent is `backend/tests/test_events_api.py:335` `test_new_observability_events_accepted`
and `:366` `test_guide_events_accepted`. Add one test in the same shape:

```
test_p0_7_events_accepted(harness):
  POST /api/events with one envelope per new CLIENT event, each carrying its
  FULL prop set from §2.
  assert body["accepted"] == N and body["dropped"] == 0
  _assert_invariant(body, N)
  assert set(by_type) == {all 7 names}          # every one LANDED
  assert json.loads(by_type["sleeper_send_failed"]["props"])["error_code"] == "sleeper_rejected"
  assert json.loads(by_type["league_view"]["props"])["team_count"] == 12
```

This is the test that would have caught the prior-art failure: `dropped == 0` and an
exact `set(by_type)` are the two assertions a default-deny allowlist can fail silently.
Mirror `:246` `test_unknown_type_dropped` for the negative: a deliberately misspelled
`sleeper_send_suceeded` must be counted-and-dropped, proving the guard is still armed.

**Prop-stripping test:** post `league_view` with a bogus `device_platform` prop; assert
the event lands and the prop is gone. This pins the §2 decision that no event carries a
device-platform prop.

**Server-fired path** — extend `backend/tests/test_analytics_p0.py`'s route-harness
pattern (`:337` `test_quickset_completed_fires_with_props` is the template): drive the
propose route's success path and assert a `sleeper_send_succeeded` row exists with
`event_id IS NULL`, the right `league_id`, and `props.give_n`. **Blocker:**
`/api/trades/propose` returns `599 test_mode_propose_disabled` under `FTF_TEST_MODE`
(`server.py:12310`) as a deliberate fail-closed guard, so the route cannot be driven
end-to-end in tests. Options, in preference order: (a) unit-test a small extracted
`_record_send_success(user_id, league_id, give, receive, picks, txn_id)` helper directly —
cheapest and honest; (b) monkeypatch `_sleeper_write` and the test-mode flag; (c) accept
manual verification only. **Recommend (a)** — it also keeps the route body to one line.

**Taxonomy invariants** — `test_analytics_p0.py:453` `test_live_taxonomy_is_disjoint`
already asserts disjointness and a membership subset. Extend the membership set with the
new names. The two import-time asserts (disjointness, and every allowlisted event having
a `CLIENT_EVENT_PROPS` row) are self-enforcing: get either wrong and **the whole test
suite fails to import**, which is the intended loud failure.

### 9.2 Mobile

`cd mobile && npx tsc --noEmit` — the required `surface` prop makes any missed
`SendInSleeperButton` mount site a **compile error**, which is exactly the enforcement
wanted. No RN unit tests exist for `track()` call sites; none are proposed.

### 9.3 End-to-end — verify a row at the destination, not a 200 at the source

G-017's prevention rule, verbatim. On the simulator against a dev backend, with both
`analytics.client_events` and `analytics.ingest` on:

1. Tap all five tabs; open League Home; open League rankings; toggle basis; switch subset;
   tap a bar and a team row.
2. Wait ≥10 s (`FLUSH_INTERVAL_MS`) or background the app to force a flush.
3. Query the destination:
   `SELECT event_type, COUNT(*), platform FROM user_events WHERE event_type IN (…) GROUP BY 1,3;`
4. **Assert `platform` is `'ios'`, not NULL** — the direct regression check for the
   incident that motivates the whole prop-spec regime.
5. Check `GET /api/analytics/health` for `dropped_unknown_type` / `dropped_unknown_prop`
   staying flat across the session. A non-zero bump is the silent-drop signature.

For the send leg, a real Sleeper send is ToS-adverse and gated on a verified session —
verify `sleeper_send_attempted` and `sleeper_send_failed` (easy: tap Send with the flag
on and no linked account, which yields the connect prompt path, then force an error), and
verify `sleeper_send_succeeded` from prod data after first real use rather than
manufacturing a send.

### 9.4 Metric-seam check

After ship, confirm on the analytics dashboard that DAU/WAU did **not** step-change on the
ship date (proving §3.2(a) landed), and that WAT's `caveat` field flips from `"dark"` to a
real value once the first send lands (proving §3.2(b)(c)).

---

## 10. Risks, collisions, open questions

### 10.1 File collisions — **for the HLD / orchestrator**

| File | This item needs | Also claimed by | Suggested resolution |
|---|---|---|---|
| **`mobile/src/components/SendInSleeperButton.tsx`** | required `surface` prop (signature + 4 call-site plumb); `track` at `:231` and in the `:143` catch | **P0-6** — replaces the silent `null` at `:273` (`if (!enabled \|\| isEspn) return null`) with an explanatory ESPN state + copy-to-clipboard | **Give the file to P0-6; P0-7 supplies its diff as a spec.** P0-6 restructures the render path and adds a branch; P0-7 only inserts into `onPress`/`catch` and adds a prop. Sequencing P0-6 first and P0-7 as a follow-up insert is far cheaper than merging two independent rewrites. **Bonus if merged:** P0-6's new ESPN branch is itself an event-worthy moment — a `sleeper_send_attempted` with `surface` + a `platform:'espn'`-style marker, or a dedicated copy-fallback event, would measure whether the fallback is used. **Not specced here** (out of P0-7's three additions) but it is the cheapest possible add-on if the two land together, and the taxonomy PR is already open at that moment. |
| **`mobile/src/screens/TradesScreen.tsx`** | **one line** at `:4713` (`surface="deck"`) | **P0-2** (error empty-state ladder ~`:4910`, toast z-order) and **P0-8** (`s8.1` gating ~`:2456`, `:3129`) | Line-level, far from both other regions in a 6 158-line file. Whoever merges last rebases; conflict risk is negligible but non-zero. |
| `mobile/src/components/TradeCard.tsx`, `InLeagueCalculator.tsx` | one line each | none found | Clean. |
| `mobile/src/navigation/TabNav.tsx`, `LeagueSummaryScreen.tsx` | edited | none found | Clean. P0-5 touches `RootNav.tsx:398`, not `TabNav`. |
| `mobile/src/screens/LeagueScreen.tsx` | `league_view` (+ OPTIONAL-A) | **P0-1** *reads* `:328-334` but its fix is backend-only (save handlers + backfill) | Verify before build; expected clean. |
| `backend/analytics_taxonomy.py`, `analytics_queries.py` | edited | none | Clean — no other P0 touches analytics. |

### 10.2 Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Client wired before server registered** → every new event counted-and-dropped, 200 responses throughout, and a plausible-looking dashboard with no rows. Prior art in this repo. | **High** | §3 ships as its own commit and merges first. §9.1's `dropped == 0` + exact-set assertions are the automated guard; §9.3's health-counter check is the manual one. |
| **DAU/WAU step-change** on ship day if `tab_selected` / `league_view` land as INTENT (deny-list default). Every retention and churn series breaks at that seam, silently and permanently. | **High** | §3.2(a) is mandatory, not optional. §9.4 verifies. Seam date recorded in the addendum. |
| **Missing `CLIENT_EVENT_PROPS` row** → `ValueError` at import → **the app does not boot**. | High but loud | Fails instantly and unmissably in CI. Not a production risk; a "don't ship half of §3.1" risk. |
| **Name collision** with a server-authoritative name → import-time crash. | High but loud | Pre-verified in §3.1(d). |
| `LeagueSummaryScreen` re-renders frequently (two parallel queries + `placeholderData`), so a naive mount effect could double-fire `league_view`. | Medium | `firedRef` guard + `query.isFetched` dep, spelled out in §2. Test on the simulator by counting rows for one visit. |
| `league_view` on the legacy root-stack `LeagueSummary` route reports `surface: 'league_rankings'` with `is_tab_root:false`, which could read as two surfaces. | Low | `is_tab_root` disambiguates; `screen` carries the actual route name. Documented in the addendum. |
| `outlook.odds` is **OFF**, so `outlook_shown` will be `false` on every row until the flag flips. | Low | Correct and honest. Recorded so nobody reads the constant `false` as a bug. |
| Analytics volume: `tab_selected` is high-frequency. Queue cap 500, batch 50, flush 10 s. | Low | Small props, well inside `MAX_PROPS_BYTES`. `trimQueue` drops non-critical oldest-first and none of these is `FUNNEL_CRITICAL`, so pressure degrades gracefully. |
| `transaction_id` on `sleeper_send_succeeded` is an external identifier in an analytics prop. | Low | Server-fired props bypass `_scrub_pii` (client-only). It is a Sleeper transaction id, not a person; the runbook's reconciliation path wants it. **No user id is included** — `their_user_id` is deliberately excluded. Flagged for the HLD to confirm rather than assume. |

### 10.3 Open questions — for the orchestrator or operator

1. **Naming — `sleeper_send_*` (recommended) or `send_in_sleeper_*` (as literally written
   in `06-resolutions.md`)?** §1.4 is the argument for the former. This is the single
   decision that most changes the value of the work, and it costs nothing either way.
   *Recommend: `sleeper_send_*`.*
2. **OPTIONAL-A (`league_home_action_tapped`) — in or out?** In = both League screens get
   real interaction coverage as the resolution's wording implies. Out = strictly the four
   listed interactions. *Recommend: in — it is one registry row and eleven one-line
   inserts, and League Home's exit paths are the only question that screen answers.*
3. **§6 P0-9 funnel events — none, F1 only, or all four?** *Recommend at minimum F1
   (`experiment_exposed`): it is already in `FUNNEL_CRITICAL` and the SDK mirror but
   missing from the allowlist, so it is a live instance of the exact trap this finding
   is about, and without it any A/B read is exposure-diluted.*
4. **Is `is_self` derivable on `league_team_opened`?** Requires session-user-id ↔
   `PowerRankedTeam.user_id` identity, which this pass did not prove. *If the builder
   cannot confirm it, omit the prop — do not guess.*
5. **Should `sleeper_send_succeeded` bump `last_trade_proposed_at`** via
   `database._EVENT_TO_USER_COL`? It would be defensible (a send is the strongest
   possible propose signal) but it changes **notification-gating behaviour**, which is
   out of scope for an instrumentation item. *Recommend: no, and say so in the addendum.*
6. **Test approach for the server-fired success event**, given `FTF_TEST_MODE` fail-closes
   `/api/trades/propose` (§9.1). *Recommend (a): extract a tiny `_record_send_success`
   helper and unit-test it.*
7. **Out-of-scope observation, worth a ticket:** `FUNNEL_CRITICAL` contains
   `app_opened_first` and `experiment_exposed`; the mobile SDK mirror (`events.ts:70`)
   contains `app_opened` and `experiment_exposed`. **Neither `app_opened_first` nor
   `experiment_exposed` is in `ALLOWED_CLIENT_EVENTS`** — both would be silently dropped
   if fired, and the two lists have drifted from each other besides. That drift is
   pre-existing and unrelated to P0-7 except that §6-F1 would fix half of it. Not fixed
   here; recorded so it is not lost.
