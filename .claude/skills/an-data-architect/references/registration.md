# Registering and classifying events

How a name gets into the taxonomy, how it is classified for DAU, and how you prove it lands.
`an-data-architect` writes the spec and the addendum; `eng-backend` / `eng-mobile` / `eng-web` make
the registry and emitter edits; `analytics-lead` reviews. Line numbers are as of `origin/main`
678834ab. If one has moved, grep the quoted text.

Every failure here is silent and answers 200, so a `200` is never evidence; a row read back from
the destination is.

## 1. When to use, and who grants

Use this when a change:
- adds a client or server event (scope §1(a), `docs/templates/feature-scope.md:29`);
- renames one: the client switches to the registered name, no alias (`celebration_fired` →
  `celebration_shown`, `2026-08-11-p0-7-addendum.md:225`);
- adds a prop or widens an enum on a shipped event (`find_trades_tapped.source`,
  `analytics_taxonomy.py:942`; `trade_pass_layer2.detail`, `:1476`);
- corrects what an event means (`2026-08-24-quickset-via-gap.md`), or retires a name from every
  registry (`calc_include_players_toggled`, `2026-08-22-384-calc-finder-addendum.md:111`);
- registers a live emitter that has been dropping, copying its prop row verbatim from the shipped
  call (`2026-08-13-dropped-emitter-backlog.md:18`).

| Registry | Where | What it does |
|---|---|---|
| `ALLOWED_CLIENT_EVENTS` | `backend/analytics_taxonomy.py:38` | Client allowlist. Ingest counts and drops unknown names (`analytics_ingest.py:400`) |
| `CLIENT_EVENT_PROPS` | `analytics_taxonomy.py:916` | Per-event prop allowlist. Ingest pops unknown keys (`analytics_ingest.py:405-411`). Every allowlisted name needs a row, even an empty one, or import fails (`:1786`) |
| `SERVER_FIRED_EVENTS` | `analytics_taxonomy.py:736` | Names written by `database.record_event()`. Overlap with client names fails import, so the app does not boot (`:1781`) |
| `FUNNEL_CRITICAL` | `analytics_taxonomy.py:893` | SDK drop-last list under queue overflow, hand-mirrored in `mobile/src/api/events.ts:69`. Only pre-auth funnel primitives belong |
| `NON_INTENT_EVENTS` | `backend/analytics_queries.py:63` | Deny-list. `INTENT_EVENTS` = everything registered minus this list (`:402`) |
| `WAT_LIVE` | `analytics_queries.py:53` | North-star feeders. Change only on an explicit north-star decision |

**Grant chain.** `analytics-lead` grants `analytics_taxonomy.py` and `NON_INTENT_EVENTS` as one
coupled pair to the emitting area's eng worker, through `head-product` → `head-eng`
(`project-agent-hierarchy` org chart, `analytics-lead` box). Both change **in the emitter's commit**
(`CLAUDE.md:137`). Registration may land before the emitter (an emitter-less name is inert), never
after: then rows are lost behind a success-shaped response (`p0-7-addendum.md:16`).

## 2. Naming

Derived from the 164 client and 44 server names registered today:
- **Lowercase snake_case, `[a-z0-9_]`.** All 164 client names.
- **`<feature>_<object>_<past-tense verb>`.** 146 of 164 end in a past-tense verb. The other 18 are
  older shapes (`league_view`, `client_error`, `usage_trends_action`, `trade_pass_layer1`), not
  precedent.
- **A feature prefix groups the family**, so one `LIKE 'calc_%'` finds it: `calc_` 10, `mock_` 8,
  `deck_` 8, `guide_` 7, `invite_` 6, `paywall_` 5.

| Verb | Meaning | Examples |
|---|---|---|
| `_shown` | the app put something in front of the user | `prompt_shown`, `invite_cta_shown` |
| `_viewed` | a screen, card or summary was seen | `screen_viewed`, `trade_card_viewed`, `deck_summary_viewed` |
| `_opened` | a sheet, overlay or drill-in opened | `notif_inbox_opened`, `league_team_opened`, `shop_opened` |
| `_tapped` | a control was tapped | `find_trades_tapped`, `home_tile_tapped` |
| `_changed` / `_selected` / `_toggled` | a state switch; props report the state after it | `league_basis_changed`, `untouchable_toggled{marked}` |
| `_dismissed` / `_snoozed` | something shown was waved away | `apple_banner_dismissed`, `quickset_prompt_snoozed` |
| `_undone` | an undo | `calc_clear_undone`, `swipe_undone` |
| `_attempted` / `_succeeded` / `_failed` | an attempt and its outcome | `signin_*`; `sleeper_send_*` (success is server-fired) |
| `_started` / `_ended`, `_completed`, `_abandoned` | a flow's lifecycle | `calc_tour_*`, `mock_*`, `guide_tour_completed` |

- **Pair an impression with its action:** `invite_cta_shown`/`_tapped`,
  `prompt_shown`/`prompt_deferred`, `push_primer_shown`/`_accepted`/`_dismissed`.
- **No client or device in the name.** None of the 164 contains `ios`, `android`, `web`, `mobile` or
  `extension`; the `source` and `platform` columns carry that. League platforms that name a feature
  are fine (`sleeper_send_*`, `espn_connect_*`).
- **No duplicate of a shipped name.** A mount is `screen_viewed{screen}`, so there is no
  `calc_opened` (384 addendum `:142`). A new name only when its props mean something on a different
  emitter (`calc_find_a_trade_tapped` vs `find_trades_tapped`, `:136`). Check reserved names first:
  `sleeper_send_*` were held in `WAT_DARK` (`p0-7-addendum.md:85`).
- **Stay out of the server namespace.** A server-fired name (or one in `database._EVENT_TO_USER_COL`
  / `_RANK_STREAK_EVENTS`) cannot be client-registered, which is why the client `quickset_completed`
  emitter was deleted (backlog `:62`). Fire an outcome server-side when it must not be
  client-forgeable (`p0-7-addendum.md:91`).

## 3. Prop rows

- **Exact, both directions.** The row lists exactly the keys the emitter sends. A key missing from
  the row is removed at ingest while `dropped` stays 0. A registered key no emitter sends reads NULL
  forever (`mobile/tests/check-analytics-300.js:185-212`).
- **An empty row (`frozenset()`) is legal, with a comment saying why**, usually that another row
  already carries the fact (`trade_pass_overlay_opened` `:1653`, `deck_search_all_tapped` `:1629`).
- **Closed enums live in the comment beside the row** and in the addendum (`home_tile_tapped.tile`
  `:1695-1709`, `calc_trade_queued.reason` `:1607-1616`). A server validator mirrors the comment
  (`database.PASS_REASON_LAYER2`, `:1483`). Widening an enum edits the comment and the addendum, not
  the registry. Use the literal `none` where absence would look like a strip (swipe-guard `:45`).
- **Counts and booleans, not sets or text.** `shop_positions_selected` carries `n` only (`:1643`);
  `has_free_text` and `banked` are booleans; `calc_trade_queued` leaves out the server's free-text
  `detail` (`:1613`); `api_request_failed.route` is normalized to bound cardinality (`:922`).
- **PII is default-deny: ids only.** Never names, emails, tokens, cookies, credentials, prices or
  receipt ids (`:1680`). Ingest scrubs again: it drops keys containing `token` / `password` /
  `email` (`analytics_ingest.py:160`) and redacts email, bearer and JWT shapes (`:161-165`) and 16+
  digit runs (`:175`).
- **G-036.** That digit rule turned every Sleeper `league_id` (18 digits) into `"[scrubbed]"` until
  the operator exempted `league_id` from that one rule on 2026-08-12 (`:177-183`, pinned by
  `test_events_api.py:837`; the G-036 entry's "not applied" is stale). Any other id prop of 16+
  digits is still scrubbed: post a realistic value and read it back.
- **League as a prop.** The `league_id` column is NULL on every client-ingested row
  (`analytics_ingest.py:455`), whatever two addenda say about it riding the envelope (384 `:68`,
  swipe-guard `:75`). If the read needs the league, register `league_id` as a prop, as
  `usage_trends_*` (`:980`) and `invite_*` (`:1154`) do.
- **`screen` is an envelope column, not a prop** (`test_analytics_taxonomy_384.py:337`). The server
  stamps `seq` and `ts_suspect` after filtering; never register them (`:912`).
- **Cap loop-prone events** with a ladder and a cap, and state the read in the addendum:
  `swipe_guard_blocked` fires at 1, 2, 3, 5, 10, 25, caps at 50 a session, and is read as
  `max(blocked_n)`, never a row count (swipe-guard `:83-94`).
- **Widen a shipped row in its own reviewed change**, owned by that metric's owner, not inside a
  registration commit (`p0-7-addendum.md:193-199`). If the client already sends the key, call it a
  bug fix (`:942-956`).

## 4. No device `platform` prop

**Rule.** No prop row carries the device platform. Ingest stamps the `user_events.platform` column
once per batch (`analytics_ingest.py:386-388`): the batch body's top-level `platform` if present
(web sends `"web"`, `web/js/events.js:166,204`; the extension sends `"extension"`,
`extension/background.js:180`), else derived from the `X-Device` header that mobile forwards via
`getClientHeaders()` (`mobile/src/api/events.ts:285`; `iphone`/`ipad`/`macos` → `ios`), else NULL.
`source` comes from `X-Source`, default `"mobile"` (`:378`); OS and app version from `X-OS-Version`
/ `X-App-Version`.

**Why.** Commit `9a224321` (2026-08-06) found `platform` NULL on **100% of client rows**: the SDKs
posted with a raw `fetch` and sent neither signal. The fix was headers and body, not a prop. G-068
(fixed 2026-09-02) is the mirror image: web sent no `X-Source`, so its rows read `source: "mobile"`.
A NULL is loud; a wrong value passes for data. A device-platform prop would be a second source of
truth that can disagree with the column and hide it breaking.

**The key `platform` is legal only with another meaning, stated in the row's comment:** the league
platform (`league_selected`, `league_view` `:1084`, `lineup_impact_unavailable`, `mock_*`) or the
paywall config variant (`paywall_viewed` `:1670`). The one device-platform exception is
`trade_pass_layer1/2`, an operator-approved spec (`:1492-1502`); new events do not inherit it.

**Test.** `assert "platform" not in CLIENT_EVENT_PROPS[name]` (384 test `:135`). If the event
carries a league `platform`, pin the meaning instead: `test_events_api.py:470-482` checks that
league `platform` survives and `device_platform` is stripped.

## 5. INTENT vs NON_INTENT

`INTENT_EVENTS = (SERVER_FIRED ∪ ALLOWED_CLIENT) − NON_INTENT_EVENTS` (`analytics_queries.py:402`),
so every name is **intent by default**, and DAU/WAU/MAU, churn and retention count intent (`:59`). A
passive name registered without its `NON_INTENT_EVENTS` row steps DAU/WAU up on ship day and breaks
every series at that seam (384 addendum `:71-77`). Classification is applied at query time, so it is
**retroactive**: moving a name that already has rows rewrites past numbers
(`rankings_import_applied` note, `analytics_taxonomy.py:752`).

**One-line test:** *does the user do this deliberately, and is it more than an echo (a mount,
outcome or terminator) of an intent event that already counts them?* Two yeses: INTENT. Any no:
NON_INTENT.

| NON_INTENT class | Precedents (`analytics_queries.py` line) |
|---|---|
| Mount counter | `trio_session_started` `:238` (RankScreen mount); `calc_tour_started` `:342` (auto-starts on landing) |
| Navigation / lens switch | `tab_selected`, `league_view` `:75`; `home_tile_tapped` `:391` (Home is the launch tab); `receipts_window_changed` |
| Terminator | `league_team_closed` `:95`; `calc_tour_ended` `:343`; `team_review_exited` |
| Diagnostic | `calc_tour_beat_missing` `:344`: a script defect, nothing the user did |
| Exposure / impression | `trade_pass_overlay_opened` `:345`; `prompt_shown`; `invite_cta_shown`; `paywall_viewed` `:376` |
| Dismissal | `apple_banner_dismissed` `:235`; `trade_pass_overlay_dismissed`; `push_primer_dismissed` |
| System refusal | `prompt_deferred` `:347`; `guide_step_suppressed` `:243` |
| System outcome / echo | `rankings_preset_detected` `:263`; `mock_completed`; `share_package_created`; `paywall_purchase_*` (the server's grant row counts) |
| Background job | `receipts_grade_run` `:288` (cron, `user_id` `system:receipts`); `api_call` / `api_request` |

**Stays INTENT** (384 addendum `:99-109`): a configuration change (`calc_mode_switched`,
`stud_tax_mode_changed`); the core gesture (`calc_asset_added`); a destructive action and its undo
(`calc_cleared`, `calc_clear_undone`); a hand-off tap (`calc_find_a_trade_tapped`,
`find_trades_tapped`); a deliberate act the system refused, because a failed intent is still intent
(`calc_trade_queued{queued:false}`, `sleeper_send_failed`, `swipe_guard_blocked`; swipe-guard
`:123-138`).

**Twins of the same kind land on the same side** (`prompt_shown` / `prompt_deferred`, 384 test
`:187`); an impression's action twin stays INTENT. **For every INTENT name, check the seam:** it
should fire behind an intent event that already counts the user that day, or the addendum states the
designed step ("Expect a real, designed step in WAU", `p0-7-addendum.md:176`). **Write the reasoning
beside the names** in `NON_INTENT_EVENTS`: one line per added name plus a "deliberately ABSENT" line
for the intent ones (model: `analytics_queries.py:295-347`).

## 6. Seam dates

- **A new client name has no history.** Every envelope before registration was dropped for good
  (backlog `:21-24`). Report a forward baseline ("zero since instrumentation"), never "the rate
  fell" (swipe-guard `:174`).
- **Write the seam line:** "Rows begin `<date / first build>`. Do not trend across `<date>`."
  (backlog `:28`). A client event starts with the first build carrying the emitter while
  `analytics.client_events` is on, not with the registration commit (usage-trends addendum `:3`); a
  server-fired event starts at the Render deploy.
- **A designed DAU step gets a date and a split** (`p0-7-addendum.md:176`). **Renames** end one
  series and start another; name the build.
- **Semantics corrections get a seam line even with no registry change:** Quick Set `via` ("Do not
  trend `rank_quickset` … across the seam", `quickset-via-gap.md:93`) and the `give_n` recount
  ("Treat the seam as a break", `p0-7-addendum.md:59-64`).

## 7. Addendum template

One file per feature, `docs/business/analytics/YYYY-MM-DD-<slug>-events.md`, in the compact shape of
`2026-10-10-usage-trends-events.md` and `2026-10-10-home-hub-addendum.md`:

```markdown
# Tracking-plan addendum — <feature> (YYYY-MM-DD)

**Status:** registered with <commit/PR> ([scope](../../plans/<feature>/scope.md) §1).
Takes effect from <first release that carries the emitter>; flag `<flag>` <on|off>.
**Registries touched:** ALLOWED_CLIENT_EVENTS, CLIENT_EVENT_PROPS, NON_INTENT_EVENTS
(name any left alone, and why). Pinned by `backend/tests/test_analytics_taxonomy_<feature>.py`.

## Questions these events answer
1. **<question>** — <event + prop that answers it; the comparison that matters>.

## Events
| Event | Class | Properties | Fires when | Client |
|---|---|---|---|---|
| `x_tapped` | INTENT | `a` (`v1`\|`v2`), `n` (int ≥ 0) | <exact moment; never on mount> | mobile |

**Why the classes:** <one line per name, citing the precedent class from §5>.
**Not tracked:** <what was considered and dropped, and why>.
**PII:** <ids only; what is deliberately excluded>.
**Seam:** rows begin <date/build>. Do not trend across <date>. <Any designed DAU step.>
**Privacy delta:** none (usage data already declared) | <new category> → onboarding-pm.
```

## 8. Per-feature test

Write `backend/tests/test_analytics_taxonomy_<feature>.py` by copying
`test_analytics_taxonomy_home_hub.py` (138 lines) or `_384.py`. Drive it off one
`_PROPS = {name: {prop: realistic_value}}` dict and assert:
1. **Membership:** `set(_PROPS) <= ALLOWED_CLIENT_EVENTS`, disjoint from `_SERVER_AUTHORITATIVE`.
2. **Exact prop rows:** `CLIENT_EVENT_PROPS[name] == frozenset(props)`. `==`, not `<=`: an extra key
   is unspecced, a missing one is stripped.
3. **No device-platform prop** (§4).
4. **No duplicate:** pin the shipped neighbours you must not fork (home-hub test `:58-67`).
5. **The intent split:** hand-written `_NON_INTENT` and `_INTENT` sets, a module-level assert that
   they partition `set(_PROPS)`, then membership both ways against `q.NON_INTENT_EVENTS` and
   `q.INTENT_EVENTS` (384 test `:70-107`, `:162-171`).
6. **Ingest round-trip** through `POST /api/events` with the 384 harness (`:244-265`:
   `db_module.engine` and `ingest_engine` patched to one in-memory DB, `ingest.is_enabled` on for
   `analytics.ingest`). Assert `accepted == len(_PROPS)` and `dropped == 0`, then read every row
   back and compare props, ignoring `seq` and `ts_suspect`. Add an **unregistered-sibling control**
   expecting `dropped == 1` and no row (384 test `:297-305`); without it, `dropped == 0` proves
   nothing. `dropped` counts envelopes only, so prop and value survival come from the read-back.

**Add a `mobile/tests/check-analytics-<id>.js` structural guard** when the client half can drift:
sent props vs the registered row both ways, exactly one emitter per moment, or an exposure gate that
must be the render gate itself rather than a re-derived copy. `check-analytics-300.js` is the model;
read comment-stripped source, since comments name the constructs they forbid. CI runs every
`mobile/tests/check-*.js` (`.github/workflows/ci.yml:47`), so these gate merges (CLAUDE.md's "gate
nothing yet" is stale).

## 9. Deploy-liveness check

- After deploy, poll `POST /api/events` with one envelope of a newly registered name and require
  **`accepted ≥ 1 AND dropped == 0`**. The old build answers `{"accepted":1,"dropped":1}`, which a
  loose check on `accepted` reads as live (`.claude/skills/feedback/lessons.md:168`).
- Then read `GET /api/admin/analytics/health` (`backend/server.py:11302`; `X-Cron-Secret` from
  `secrets.local.env`): `dropped_unknown_type`, `dropped_unknown_prop`, `pii_scrubbed`,
  `txn_failed`. Counters reset each deploy (`"since": "deploy"`).
- Both flags must be on: `analytics.client_events` gates clients, `analytics.ingest` the server.
  With ingest off the server answers `disposition: "disabled"` with a 200 (G-017).
- Prod needs the operator's approval: a standing read-only grant recorded for the acting session,
  else an explicit yes. The probe `POST` writes a row, so a read-only grant does not cover it.

## 10. Scope §1 reviewer checklist (`analytics-lead`)

- [ ] The right box: (a) for any new name, prop or enum value; (b) when existing events already
      answer the question; (c) when there is genuinely nothing to measure.
- [ ] (a): the table has class, props with enums, fires-when (never "on mount" unless a mount
      counter), client, PII, and a seam line.
- [ ] (b) names the existing events and the question each answers; (c) gives a reason.
- [ ] Registry and `NON_INTENT_EVENTS` edits are planned for the emitter's commit, through the grant
      chain.
- [ ] The per-feature test (§8) is planned, plus a structural guard if the client half can drift.
- [ ] The privacy delta (§11) is answered.

## 11. Privacy delta

If a new event or prop adds a data category Apple's privacy label would list, notify `onboarding-pm`
through `head-product`. Decision P12 (2026-10-14): labels follow the tracking plan, and
`onboarding-pm` owns the product side of privacy. Product-interaction usage data and identifiers
linked to the user are already declared (`docs/plans/analytics-platform/prd.md:207` NFR-4;
`README.md:42`). A delta is a new category: purchases, search terms, user-typed content, location.
No in-repo record of the current label exists, so name the category and let `onboarding-pm` diff it.

## 12. Health sweep

Run it periodically and before any claim that analytics are "covered"; write the result as a dated
addendum.

```bash
git grep -h -o -E "track\([[:space:]]*['\"][a-z0-9_]+['\"]" -- mobile/src
git grep -h -o -E "FTFTrack\([[:space:]]*['\"][a-z0-9_]+['\"]" -- web
git grep -h -o -E "emitAnalyticsEvent\([[:space:]]*['\"][a-z0-9_]+['\"]" -- extension
git grep -n -E "track\([[:space:]]*[a-zA-Z_]+[,)]" -- mobile/src   # wrappers forwarding a variable
```

1. **Emitted literals vs `ALLOWED_CLIENT_EVENTS`.** Diff the names the first three lines collect;
   resolve the wrappers the fourth finds by hand (`TeamReviewScreen.tsx:165` `emit()`). The
   2026-08-11 sweep found **33 of 73** mobile names unregistered (G-031). At 678834ab it is clean:
   119 mobile, 6 web and 2 extension names, none unregistered.
2. **Drop counters** from the health endpoint (§9). A non-zero `dropped_unknown_type` since deploy
   means a live emitter is still unregistered.
3. **Envelope stamps (G-068).** Look for client rows with NULL `platform`, or a `source` that
   contradicts it (`platform='web' AND source='mobile'`). Known suspect, from a code read and not
   yet checked against rows: web's page-hide flush uses `navigator.sendBeacon`
   (`web/js/events.js:203`), which cannot set `X-Source`, so those batches would land as `"mobile"`.
4. **Value survival (G-036).** For every id prop, confirm real values are not `"[scrubbed]"`.
