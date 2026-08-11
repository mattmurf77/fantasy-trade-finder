# HLD — P1 audit-remediation round (reconciliation)

> **Purpose.** Seven P1 plans were written in parallel by seven agents who could not see each
> other's work, all against `ab9368f`, which does **not** contain the in-flight P0 build. This
> document is the single reconciliation layer: it resolves every file collision across the P1
> set *and* across the P0/P1 boundary, fixes one authoritative merge order, partitions file
> ownership into build waves, aggregates every operator decision, and lists what each item must
> re-verify after P0 merges.
>
> **Status:** plan-only. No source code is changed by this document.
> **Author:** HLD reconciliation agent, 2026-08-11.
> **Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`, branch
> `p1-remediation-2026-08-11` @ `ab9368f` (== `origin/main` at time of writing).

**Sources.** `plan-p1-1-2.md`, `plan-p1-3.md`, `plan-p1-5.md`, `plan-p1-7.md`, `plan-p1-9.md`,
`plan-p1-10.md`, `plan-p1-11.md` and their seven `scope-*.md` twins (this directory);
`/Users/teresadickens/Documents/Claude/Projects/ftf-p0-remediation/docs/plans/audit-p0-remediation/`
(`plan-p0-1`, `-2`, `-3`, `-5`, `-6`, `-7`, `-8-9`, `hld.md`) read read-only; root `CLAUDE.md`,
`docs/CLAUDE.md`.

## Contents

- [Preconditions](#preconditions)
- [A. Collision map](#a-collision-map)
- [B. File ownership table](#b-file-ownership-table)
- [C. Merge order](#c-merge-order)
- [D. Wave plan](#d-wave-plan)
- [E. Consolidated operator decision list](#e-consolidated-operator-decision-list)
- [F. Risk register](#f-risk-register)
- [G. Re-verification checklist](#g-re-verification-checklist)
- [H. Corrections found by the LLD wave](#h-corrections-found-by-the-lld-wave)

---

## H. Corrections found by the LLD wave

> Added 2026-08-11, after this HLD was written, by the orchestrating session. The six LLD/PRD
> agents each re-read the code and found errors in **this document**. Where a correction below
> contradicts the body of this HLD, **the correction wins**. Ordered by consequence.

### H-1 — The T1 verification step names an endpoint that does not exist *(§C step 1, and the prose at "T1's gate")*

This HLD says the taxonomy commit is verified with `GET /api/analytics/health`. **That route does
not exist.** The real endpoint is **`GET /api/admin/analytics/health`**, gated on `X-Cron-Secret`
(`backend/server.py:6977`, `:6991`). `plan-p1-10.md`, `scope-p1-10.md` and this HLD all carried the
wrong path.

Worse, it is a weaker signal than this HLD implies: the counters it reports are **in-process and
reset on deploy**, so a "counters stayed flat" reading is per-worker and proves little immediately
after the T1 deploy. **The load-bearing verification is the hand-rolled `POST /api/events` probe:
`dropped == 0` *and* every property echoed back at the destination.** Name-survival and
prop-survival are distinct failures — an event name can register while its props are silently
stripped, which is exactly the `trade_card_shared.landing` bug already in the tree.

*Found by `LLD-p1-10.md`.* Applies to §C step 1, §B, and every item's re-verification row that
cites the health endpoint.

### H-2 — P0-5 does **not** restructure `_provider_auth_response` *(§A P1-3 row, §B `server.py` row, §E AN-6, §G.30)*

This HLD repeatedly states that P0-5 restructures `backend/server.py:_provider_auth_response`
(`:18005-18075`), and uses that as an argument for deferring P1-3's analytics event.
**P0-5's own LLD lists `backend/server.py` under *must not touch*, and P0's HLD calls that path
unmodified.**

The deferral recommendation (§E AN-6) still stands on its other grounds — import-time assert blast
radius, the intent-by-default DAU decision, a sixth taxonomy claimant. It simply loses this
argument. The **real** contention on that file is P0's whole-file hold on `server.py`, which
affects *sequencing* of P1-3's probe commit rather than creating a merge conflict.

*Found by `LLD-p1-3.md`.*

### H-3 — Every P1-11 row is void; Wave C is empty

Per [`DECISIONS-p1.md`](DECISIONS-p1.md) **D-P1-01**, P1-11 is dropped — "Acquire" stays. All §A
collision rows, §B ownership rows, and §D wave assignments naming P1-11 are moot, **including
Wave C, which no longer contains anything.** P1-3 is now the only item that rebases after Wave B.

Two observations from the voided P1-11 analysis remain true and are worth keeping for P0's sake:
P0-7's conflict-matrix rows for `TabNav.tsx` ("none found") and `LeagueScreen.tsx` are stale, and
`screens/manifest.json:55` under-reports capture staleness.

### H-4 — §E's decision list is incomplete: the LLD wave raised new gates

§E aggregated 46 decisions from the plan wave. The LLD wave added more, and they are **not** in
that count:

| New gate | Item | What it decides | Blocks |
|---|---|---|---|
| **OG-1** | P1-1/2 | Eager vs lazy share-link mint — the plan's Design §3 and its own Maestro block 1 contradict each other, and it is a rate-limit-semantics question | The share flow's shape and its Maestro assertions |
| **OG-12** | P1-5 | The Matches empty state has **no scroll container**, so the promoted CTA lands in an already-clipped region: `assertVisible` cannot detect it and `invite_cta_shown{matches_empty}` degrades to a mount counter | Half of P1-5's surface |
| **OG-13** | P1-5 | The invite card's `primary` lands above `league.action.find`, also primary — competing primaries, unexamined | League Home hierarchy |
| **P-1 … P-8** | P1-9 | Notification bucket, gate strength, and the eight tunable defaults | **P-1 is build-blocking** — it changes the file list, the sim tier, and whether the permission primer needs a fourth consent bullet |

### H-5 — §F R-6 is answered

The open web-parity question for P1-9 resolved during the LLD wave: **web degrades safely, no web
edit needed.** Close the risk row.

---

## Preconditions

### P-1 — The P0 merge is a **gate with a verification step**, not a background fact

Branch `p0-remediation-2026-08-10` (P0-1, -2, -3, -5, -6, -7, -8, and P0-9 test-prep) merges to
`main` **before any P1 build agent writes a line**. Every P1 plan was authored against `ab9368f`,
which contains none of it. The verification step is mechanical and non-negotiable:

```
git fetch origin
git log origin/main --oneline | grep -i "p0-"          # P0 commits present
git rev-parse origin/main                              # record the sha in the scope blocks
git -C <p1-worktree> rebase origin/main                # rebase, do not merge
```

Then, per item, run its row in [§G](#g-re-verification-checklist) before the first edit.
A P1 agent that starts from `ab9368f` line numbers is building against fiction — `backend/server.py`
is 20k+ lines and P0 inserts into six of its functions, and `mobile/src/screens/TradesScreen.tsx`
takes ~24 edits from P0-2 + P0-8/9 alone (`hld.md:350`, `:469`).

### P-2 — Which P1 designs depend on post-P0 code

| Item | Depends on post-P0 code? | What specifically |
|---|---|---|
| **P1-1/2** | **YES — hard** | `backend/analytics_taxonomy.py` (P0-3 B4 + P0-7 both edit the two frozensets); `mobile/src/utils/deepLinks.ts` (P0-3 M4/M5 move `:344-354`); `mobile/src/screens/TradesScreen.tsx` M11/M12 (P0-2 + P0-8/9 rewrite the file); DECISIONS/GOTCHAS next-IDs (P0-3 also claims `D-011`/`G-013`). |
| **P1-3** | **Conditional** | Zero file overlap in the recommended (defer-`email_captured`) lane. If Gate 4 = Option B, it edits `backend/analytics_taxonomy.py` *and* `server.py:_provider_auth_response` (`:18039-18075`), which is the exact function **P0-5 restructures** — then it becomes a hard dependency. |
| **P1-5** | **YES — hardest of the set** | `buildInviteUrl` in `InviteLeaguematesBanner.tsx:27-31` is **rewritten by P0-3 M1**; `invite_shared`'s `CLIENT_EVENT_PROPS` row is **created by P0-3 B4** and P1-5 must *extend* it, not re-add it; `LeagueScreen.tsx` receives P0-7's `league_view` mount effect. Plan states it outright: "Do not start the P1-5 build until `git log origin/main` contains P0-3's merge" (`plan-p1-5.md:230`). |
| **P1-7** | **YES — and P0-1 *widens the bug* on merge** | P0-1 edits `save_anchor_route` (`server.py:7479`), comments the unlock ladder (`:6155-6175`) that P1-7 rewrites, and imports at `:148`. P0-1 pins every wizard user to `ranking_method='anchor'` at first save — which today means permanently locked (`plan-p1-7.md:712-718`). The locked cohort grows every day between the P0 merge and P1-7's. P1-7's Maestro flow also depends on `testID="rank.unlocked-banner"`, which **P0-1 introduces** at `RankScreen.tsx:686` (`plan-p1-7.md:565-573`). |
| **P1-9** | **YES — soft** | `mobile/src/utils/deepLinks.ts` (P0-3 moved the region); `backend/tests/fixtures/seed_ui_test_db.py` (P0-1 rewrites `_validate_quickset` `:314-366`); reads but must not edit `server.py:6218-6255`, the first-unlock fan-out **P0-1 owns**. OC-5 explicitly sequences it "merge after P0-1". |
| **P1-10** | **YES** | `mobile/src/components/SendInSleeperButton.tsx:114` — P0-6 **rewrites this component's render path** and P0-7 inserts `track()` into `onPress`/`catch`; P0-7's own matrix hands the file to P0-6 (`plan-p0-7.md:590`). Line `:114` **will** have moved. Also `RootNav.tsx` (P0-5 edits `:398`, `:410`). Taxonomy per P-3 below. |
| **P1-11** | **YES** | `RankScreen.tsx:686` vs `:693-694` (P0-1) and `TabNav.tsx:650-656` vs `:659-682` (P0-7) — both **real, verified collisions**, see [§A](#a-collision-map). Also `MatchesScreen.tsx` (P0-6 at `:616-623`) and `RootNav.tsx:71` (P0-5 at `:398`/`:410`). |

**No P1 item is independent of the P0 merge.** The closest is P1-3 in its recommended lane
(docs + `config/features.json:58` + `web/privacy.html` + tests), and even that shares
`config/features.json` and `backend/feature_flags.py` with P1-9 and P1-11.

### P-3 — Verified facts this HLD rests on

Checked in this worktree at `ab9368f`, not inherited from any plan:

| Claim | Evidence |
|---|---|
| `growth.share_landing` is **ON** | `config/features.json:125` → `"growth.share_landing": true` |
| `auth.email_capture` is **OFF** | `config/features.json:58` → `"auth.email_capture": false` |
| `trade_card_shared` is registered but its `landing` prop is **stripped** | `analytics_taxonomy.py:74` (name present); `:222` → `frozenset({"trade_id", "channel"})` — no `landing`, no `surface` |
| `calc_trade_shared`, `tier_board_shared`, `share_package_created`, `invite_shared` are **absent** from `ALLOWED_CLIENT_EVENTS` | grep over `analytics_taxonomy.py` returns no hits — they are counted-and-dropped behind a 200 |
| `push_opened` **is** registered with `dedup_key` already in its prop row | `analytics_taxonomy.py:68`, props at `:213` → `frozenset({"kind", "dedup_key"})` |
| Taxonomy structures and their guards | `ALLOWED_CLIENT_EVENTS:38`, `SERVER_FIRED_EVENTS:105`, `FUNNEL_CRITICAL:142`, `CLIENT_EVENT_PROPS:165`, `_assert_namespaces_disjoint:298` (invoked `:322`), missing-prop `ValueError` guard `:327`; `NON_INTENT_EVENTS` at `analytics_queries.py:60`, `INTENT_EVENTS` deny-list at `:65` |
| **TabNav collision is real** | `TabNav.tsx:647` `<Tab.Screen name="Trades">`; comment `:650-652`; `options` block with `tabBarLabel: 'Acquire'` at `:655` and `tabBarAccessibilityLabel: 'Acquire'` at `:656`; `listeners={...}` with the `tabPress` handler at `:659-682`. P1-11 edits `:650-656`; P0-7 inserts `track()` into `:659-682`. **One JSX element, adjacent props.** |
| **RankScreen collision is real** | `RankScreen.tsx:685` `{isUnlockedEverywhere && (`, `:686` `<View style={styles.unlockedBanner}>` (P0-1 adds `testID` here), `:693` `'Your board now prices your trades — see the Acquire tab'`, `:694` `'Trade Finder unlocked — check the Acquire tab'` (P1-11 edits 4–5). **Seven lines apart, one diff hunk.** |

### P-4 — Adjudications made by this HLD (not by the individual plans)

1. **One shared P1 taxonomy commit — adopted and widened.** See [§C, commit T1](#c-merge-order).
2. **P0-7's conflict matrix is corrected** on two rows. See [§A.1](#a1-corrections-to-p0-7s-conflict-matrix).
3. **One consolidated screen re-capture pass** at end of the P1 round. See [§C, step R1](#c-merge-order).
4. **`living-memory` ID allocation is ordered by merge position**, not claimed in advance. See [§A.6](#a6-the-decisionsmd-id-collision-nine-claimants).
5. **The "flag-gated" framing in the briefing is corrected** — four P1 items ship live on merge, not one. See [§F, R-1](#f-risk-register).

---

## A. Collision map

Every file claimed by more than one item, P1 or P0, at line granularity where the plans provide it.
"Owner" is the single agent permitted to write the file in that wave; all other claimants supply
their diff as a spec to the owner, or wait for a later wave.

### A.1 Corrections to P0-7's conflict matrix

`plan-p0-7.md:588-597` carries a conflict matrix that was correct **within the P0 round** and is
now **stale across the P0+P1 program**. Two rows must be corrected in the record:

| Row in `plan-p0-7.md:595` | Says | Correction |
|---|---|---|
| **`mobile/src/navigation/TabNav.tsx`** — "edited \| **none found** \| Clean. P0-5 touches `RootNav.tsx:398`, not `TabNav`." | No other claimant | **FALSE across the program.** `plan-p1-11.md:201-202` edits `TabNav.tsx:655` and `:656` (`tabBarLabel` / `tabBarAccessibilityLabel`), and `plan-p1-11.md:222` rewrites the comment at `:650-652`. P0-7 step 7 adds `track('tab_selected', …)` to the Trades tab's `tabPress` inside `listeners` at `:659-682`. **Same `<Tab.Screen name="Trades">` element (`:647-683`), adjacent props, one diff hunk.** P1-11 itself flags this at `plan-p1-11.md:494`: "That matrix predates P1-11. P1-11 is a new entrant on `TabNav.tsx` — flag to the P0-7 owner." **This HLD is that flag.** |
| **`mobile/src/screens/LeagueScreen.tsx`** — "P0-1 *reads* `:328-334` \| Verify before build; expected clean." | Only P0-1, read-only | **Incomplete twice over.** (a) P0's own HLD already corrected it for P0-3 M3 (`hld.md:491-493` removes M3, resolving it in P0-7's favour). (b) It is now also claimed by **P1-5**, which adds a card mount at `:474`, an `onInvite` suppression at `:700`, an `inviteLeaguemates` rewrite at `:371-382`, an `invite_cta_shown` mount effect, and an optional overlay button at `:803` (`plan-p1-5.md:258-262`). P0-7 step 8 adds a `league_view` mount effect to the same screen. **Two mount effects on one screen.** |

A third row — `backend/analytics_taxonomy.py` "edited \| **none** \| Clean — no other P0 touches
analytics" — was already corrected inside the P0 round (`hld.md:543`, P0-3 B4 also edits it).
It is now wrong by a further **three** claimants: P1-1/2, P1-5, P1-10.

### A.2 `backend/analytics_taxonomy.py` — **five claimants**, default-deny and silent

The single most contended file in the program. The failure mode is not a merge conflict — it is a
**clean merge that drops a name set**. `analytics_ingest.py:379-383` `_health_bump("dropped_unknown_type")`s
and returns **200** for any `event_type` not in `ALLOWED_CLIENT_EVENTS`; `:384-389` silently strips
any prop not in that name's `CLIENT_EVENT_PROPS` row. There is no error on either side.

| Claimant | Structure | Names / rows | Verified state at `ab9368f` |
|---|---|---|---|
| **P0-3 B4** (`plan-p0-3.md:288`) | `ALLOWED_CLIENT_EVENTS` (`:38-99`) + prop rows | `invite_shared`, `invite_link_opened`, `invite_league_pinned`, `invite_pin_failed` | all absent |
| **P0-7 §3.1** (`plan-p0-7.md:246-302`) | `ALLOWED_CLIENT_EVENTS`, `SERVER_FIRED_EVENTS` (`:105-136`), `CLIENT_EVENT_PROPS` (`:165-255`) | 8 client + 1 server (`sleeper_send_succeeded`) + 8 prop rows | all absent |
| **P1-5 A1/A2** (`plan-p1-5.md:242-243`) | `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS` | **new:** `invite_cta_shown`, `invite_cta_tapped`. **MODIFIES:** `invite_shared`'s row → `{league_id, surface, not_joined, total_mates, platform}` | depends on P0-3 B4 landing first |
| **P1-10 1.1/1.2** (`plan-p1-10.md:319-320`) | `ALLOWED_CLIENT_EVENTS` (insert after `:98`) + `CLIENT_EVENT_PROPS` (insert after `:254`) | `sleeper_connect_opened/_failed/_captured/_abandoned` + 4 prop rows | all absent |
| **P1-1/2 B1/B2** (`plan-p1-1-2.md:292-293`) | `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS` (`:222`) | **new:** `calc_trade_shared`, `tier_board_shared`, `share_package_created`. **MODIFIES:** `trade_card_shared`'s row → `{trade_id, channel, landing, surface}` | 3 absent; `trade_card_shared` present at `:74` with `{trade_id, channel}` at `:222` |
| *(conditional)* **P1-3 Gate 4 Opt. B** (`plan-p1-3.md:209`) | `SERVER_FIRED_EVENTS` (`:105-136`) | `email_captured` | absent; **recommended deferred** |

**Two of the five claimants MODIFY an existing row rather than appending.** That is the dangerous
class: a three-way merge that takes "theirs" on the `invite_shared` line silently discards P1-5's
four props, and every invite row lands propless with no error anywhere. `plan-p1-5.md:226` (D3)
names this exactly; `plan-p1-5.md:415` rates it **High**.

#### Adjudication — P1-10's shared-commit recommendation is **ADOPTED, and widened**

`plan-p1-10.md:604` and its Checkpoint D (`:673-677`) recommend "land ONE shared *P1 taxonomy
registration* commit containing both items' names, before either item's client wiring", naming
P1-10 and P1-5. **Adopted — and extended to P1-1/2**, because P1-1/2 is the third writer to the
same two structures and, like P1-5, performs a **row modification** (`trade_card_shared`), which is
the operation the shared commit exists to protect. Three competing single-item registration commits
is strictly worse than two, and P1-1/2's plan already concedes the merge point
(`plan-p1-1-2.md:292`: "**Merge point with P0-3's B4 — same block**").

**Commit T1 — "P1 taxonomy registration"**, one commit, one owner, first P1 commit after the P0
merge, merged **and deployed to Render** before any P1 client `track()` exists.

**T1 contents (exhaustive):**

| # | File | Change |
|---|---|---|
| T1.1 | `backend/analytics_taxonomy.py` `ALLOWED_CLIENT_EVENTS` | Append **9** names in three commented blocks: `sleeper_connect_opened`, `sleeper_connect_failed`, `sleeper_connect_captured`, `sleeper_connect_abandoned` (P1-10 1.1, with its four required comment clauses); `invite_cta_shown`, `invite_cta_tapped` (P1-5 A1); `calc_trade_shared`, `tier_board_shared`, `share_package_created` (P1-1/2 B1, with the comment recording that `calc_trade_shared` has been fired-and-dropped since it shipped). |
| T1.2 | `backend/analytics_taxonomy.py` `CLIENT_EVENT_PROPS` | **9 new rows** (P1-10 1.2's four verbatim frozensets; P1-5's two; P1-1/2's three) **plus 2 modified rows**: `invite_shared` extended to `{league_id, surface, not_joined, total_mates, platform}` (P1-5 A2 — the `platform` comment must state *league* platform, not device); `trade_card_shared` widened from the verified `{trade_id, channel}` at `:222` to `{trade_id, channel, landing, surface}` (P1-1/2 B2). |
| T1.3 | `backend/analytics_queries.py` `NON_INTENT_EVENTS` (`:60-63`) | `+= "invite_cta_shown"` — **mandatory, not optional** (P1-5 A3). `INTENT_EVENTS` is a deny-list (`:65`); an impression event left INTENT step-changes DAU/WAU on ship day and breaks every retention series at the seam. P1-10 adds nothing here **by decision, recorded** (`plan-p1-10.md:321`). P1-1/2's three share events' INTENT/NON_INTENT membership is **unspecified in its plan** — see [§E, AN-4](#e-consolidated-operator-decision-list). |
| T1.4 | `backend/tests/test_events_api.py` | All three acceptance tests in one file, one commit: P1-10's `test_sleeper_connect_events_accepted` (`plan-p1-10.md:323`), P1-5's `test_p1_5_invite_events_accepted` (`plan-p1-5.md:246`). Each must assert `dropped == 0` **and prop survival**, not merely acceptance. |
| T1.5 | `backend/tests/test_share_package.py` | P1-1/2 B3 — the four share names survive `POST /api/events` with full prop sets (`plan-p1-1-2.md:294`). |
| T1.6 | `backend/tests/test_analytics_p0.py` | **ONE** extension of `test_live_taxonomy_is_disjoint`'s membership assertion covering all 9 names. Three separate edits to one assertion is a guaranteed conflict; P1-5 A6, P1-10 1.6 and P0-7 step 5 all target it. |
| T1.7 | `docs/business/analytics/2026-07-17-tracking-plan-v2.md` | **One** appended section, "Addendum 2026-08-11 — P1 round", after the ESPN addendum at `:156`, enumerating all 9 events + the 2 modified rows, and linking out to per-item standalone addendum files where an item wants one. **Rationale:** P1-10 1.4 specifies an in-file addendum (mirroring the ESPN Connect precedent); P1-5 A4 specifies a standalone file `2026-08-11-p1-5-addendum.md`; P1-1/2 specifies "an addendum". Both conventions already coexist (`plan-p1-10.md:322`). Keeping the *append point* single removes the only textual conflict; the standalone files cannot conflict because they are new. |
| T1.8 | `docs/business/analytics/2026-08-11-p1-5-addendum.md` (new) | P1-5 A4's five required contents (a)–(e), unchanged. New file, no conflict. |

**T1's gate.** After merge, Render deploy, then: `GET /api/analytics/health` plus a hand-rolled
`POST /api/events` carrying one envelope per new name with its full prop set. **`dropped == 0` and
every prop echoed, or no P1 client wave starts** (`plan-p1-5.md:249`, `plan-p1-10.md:311-313`).

**If Gate 4 (P1-3) returns Option B**, `email_captured` lands **in T1**, in `SERVER_FIRED_EVENTS`,
not in a later standalone commit — otherwise it becomes a sixth competing edit. The recommendation
across three independent plans is to defer (`plan-p1-3.md:369`, `plan-p1-10.md`, `plan-p1-5.md`).

### A.3 Mobile file collisions — line level

| File | Claimants | Lines | Verdict / owner |
|---|---|---|---|
| **`mobile/src/navigation/TabNav.tsx`** | **P0-7** step 7 · **P1-11** edits 1–2, 7–11 | P0-7: `track()` into `tabPress` at `:659-682` (and 5 other handlers `:623, :636, :689, :709, :729`). P1-11: `:655`, `:656`, comment `:650-652`, plus comments `:396, :488, :580, :685` | **REAL COLLISION, verified.** Same `<Tab.Screen name="Trades">` (`:647-683`). Git may auto-merge `options` vs `listeners`; **do not rely on it** — P1-11's comment rewrite at `:650-652` sits immediately above P0-7's element body and pulls both into one hunk context. **Owner: P1-11, in Wave C, after P0-7 has merged with P0.** Re-locate by content. |
| **`mobile/src/screens/RankScreen.tsx`** | **P0-1** edit #14 · **P1-11** edits 4–5 | P0-1: `testID="rank.unlocked-banner"` on the `View` at `:686`. P1-11: the two copy strings at `:693` and `:694` | **REAL COLLISION, verified.** Both inside `{isUnlockedEverywhere && (…)}` at `:685-696`. **Owner: P1-11, Wave C.** P0-1's Maestro flow is safe by design — it asserts the testID, not the text (`plan-p1-11.md:491`). P0-1's *plan prose* quoting the old string (`plan-p0-1.md:80-82`) goes stale; cosmetic, note at ship. |
| **`mobile/src/screens/LeagueScreen.tsx`** | **P0-7** step 8 · **P1-5** B4–B8 · *(P0-3 M3 removed by `hld.md:491-493`)* · P0-1 *reads* `:328-334` | P0-7: `league_view` mount effect at `summaryQuery :167` + OPTIONAL-A on ~11 handlers (`:366-367, :511, :518, :540, :548, :564, :568, :598, :744`). P1-5: card mount at `:474`, `onInvite` at `:700`, `inviteLeaguemates` body `:371-382`, comment `:369-370`, `invite_cta_shown` effect, overlay `:803-815` | **REAL OVERLAP — two mount effects on one screen.** **Owner: P1-5, Wave B** (P0-7 has already merged as part of P0). Semantic rule carried forward from `plan-p1-5.md:404`: **if P0-7's OPTIONAL-A shipped, its `action` enum must NOT gain an `invite` value** — `invite_cta_tapped` owns that tap; two events for one tap double-counts the product's most important growth action. |
| **`mobile/src/screens/MatchesScreen.tsx`** | **P0-6** item 5 · **P1-5** B9–B11 · **P1-11** edit 3 | P0-6: `leagueName={item.league_name}` at `:616-623`. P1-5: `emptyModule` memo `:387-397`, empty-state block `:548-552`, mount effect. P1-11: copy at `:660` | **Three writers, three disjoint regions.** Serialize: P0-6 (in P0) → P1-5 (Wave B) → P1-11 (Wave C). Auto-merges, but re-grep rather than trusting line numbers. |
| **`mobile/src/screens/TradesScreen.tsx`** | **P0-2** (~18 edits) · **P0-8/9** (`:2456-2459, :2547, :3133-3139, :3153`) · **P0-6** (`:4713`) · **P0-7** (`:4713`) · **P1-1/2** M11/M12 (`:2735-2751`, `:2760-2766`) | — | P0's HLD gives the file exclusively to `W2-TS` inside the P0 round (`hld.md:534`). **For P1: owner is P1-1/2, Wave A**, and only if [OC-2](#e-consolidated-operator-decision-list) is answered "include". P1-11 explicitly does **not** touch it (`plan-p1-11.md:495` — `:3969` is Group-2 "acquire as direction", out of scope). The file is 6,158 lines and will have moved substantially; **re-grep, never edit by line**. |
| **`mobile/src/utils/deepLinks.ts`** | **P0-3** M4/M5 · **P1-1/2** M3 · **P1-9** #13 | P0-3: `V2_SCREENS` `:95-178`, `?league=` capture `:344-354`. P1-1/2: third branch in `rewriteUniversalPath` `:189-199`. P1-9: `V2_TRADE_KINDS` `:262` | **Three-way, all disjoint regions** (`plan-p1-9.md:605`). Serialize **P0-3 (in P0) → P1-1/2 (Wave A) → P1-9 (Wave B)**. Line numbers *will* have moved twice; re-grep for `rewriteUniversalPath` and `V2_TRADE_KINDS`. P1-11 does not touch the file (`plan-p1-11.md:271`). |
| **`mobile/src/screens/SettingsScreen.tsx`** | **P0-5** item 9 · **P1-10** 2.4/2.5 · **P1-9** #18 · P1-3 *reads* `:354-361`/`:1331` · P0-1 *reads* `:229-238` | P0-5: inline Sleeper form → `LinkSleeperSheet` at `:423-472`, `:1210-1236`. P1-10: `:488` (step-up), `:1261` (verify row). P1-9: notification bucket rows `:986-1026`, `Row` helper `:1450-1459` | **Disjoint regions, but P0-5's extraction moves everything below `:472`.** P1-10 and P1-9 must **not** run concurrently on this file. Serialize **P1-10 (Wave A) → P1-9 (Wave B)**. |
| **`mobile/src/components/SendInSleeperButton.tsx`** | **P0-6** item 3 (owner in P0) · **P0-7** step 10 · **P1-10** 2.3 | P0-6 rewrites the gate (`:59-66`) and render tail (`:273`+); P0-7 inserts into `onPress` `:231` and the `:143` catch; P1-10 changes `goConnect`'s navigate at `:114` | **P1-10 owns one line, in Wave A, after both P0 edits.** `:114` **will** have moved — P0-7's own matrix hands the file to P0-6 (`plan-p0-7.md:590`), and P0-6 restructures the render path. Re-grep for `goConnect`. |
| **`mobile/src/navigation/RootNav.tsx`** | **P0-5** items 1–2 (`:297-301`, `:410`) · **P0-3** M8/M12 (`:397-421`, `:341`) · **P1-10** 2.1/2.2 (`:58`, `:437`) · **P1-11** edit 12 (`:71`, comment) | — | Four writers, all disjoint. P0's two land inside P0. **P1-10 (Wave A) → P1-11 (Wave C).** Low risk; re-grep `SleeperConnect`. |
| **`mobile/src/components/InLeagueCalculator.tsx`** | **P0-6** item 5 (`:771`) · **P0-7** step 12 (`:771`) · **P1-1/2** M8 (`:781-798`) | — | Both P0 edits land inside P0 at the same line. **P1-1/2 owns `:781-798` in Wave A.** Adjacent to a line P0 edited twice — re-read the merged mount before editing. |
| **`mobile/src/components/Toast.tsx`** | **P0-2** (`topOffset` prop, `:99-102`, `:143-151`) · **P1-1/2** M15 (`testID` passthrough on the action button, `:111-124`) | — | Disjoint props on one component. P0-2 lands in P0. **P1-1/2 owns it in Wave A.** |
| `mobile/src/screens/TiersScreen.tsx`, `TradeCalculatorScreen.tsx`, `ShareTradeImage.tsx`, `mobile/src/api/calc.ts`, `mobile/src/utils/shareLinks.ts` | **P1-1/2** only | — | **Clean — sole owner.** |
| `mobile/src/screens/SleeperConnectScreen.tsx` | **P1-10** only | — | **Clean — sole owner** (`plan-p1-10.md:610`). |
| `mobile/src/components/TopBar.tsx`, `mobile/src/hooks/usePushNotifications.ts` | **P1-9** only | — | **Clean — sole owner** (`plan-p1-9.md:604`, `:607`). |
| `mobile/src/utils/anchorRows.ts`, `PickAnchorScreen.tsx`, `AnchorSheet.tsx`, `testid-lint-allow.txt` | **P1-7** only | — | **Clean — sole owner.** |
| `mobile/src/utils/leagueUnlocks.ts`, `inviteShare.ts` (new), `InviteLeaguematesCard.tsx` (new) | **P1-5** only | — | **Clean.** |
| `mobile/src/components/InviteLeaguematesBanner.tsx` | **P0-3** M1/M2 (owner in P0) · **P1-5** B12 | P0-3 rewrites `buildInviteUrl` `:27-31` + the comment block `:9-18, 34-37`; P1-5 replaces only `handleInvite`'s body `:39-52` | **P0-3 first, always** (`plan-p1-5.md:405`). **P1-5 never touches `buildInviteUrl`** — it imports it (D1/D2, `plan-p1-5.md:224-225`). |
| `mobile/src/screens/TradeFinderHubScreen.tsx`, `testRouteEntry.ts`, `PickAssignmentScreen.tsx`, `DraftRoomScreen.tsx` | **P1-11** only *(P0-3 M12 also touches `testRouteEntry.ts`)* | P1-11: `TradeFinderHubScreen:487`, `testRouteEntry:11, :74`, `PickAssignmentScreen:873`, `DraftRoomScreen:158` | P0-3 M12 adds harness support to `testRouteEntry.ts`; P1-11 edits comments at `:11`/`:74`. Disjoint. **P1-11, Wave C.** |

### A.4 Backend file collisions — line level

| File | Claimants | Verdict / owner |
|---|---|---|
| **`backend/analytics_taxonomy.py`** + **`backend/analytics_queries.py`** | P0-3, P0-7 (in P0) · **P1-1/2, P1-5, P1-10** | **Resolved by commit T1** — see [§A.2](#a2-backendanalytics_taxonomypy--five-claimants-default-deny-and-silent). **No other P1 commit may touch either file.** P1-9's OC-6 (`push_opened` → NON_INTENT), if elected, is a one-line edit routed **into T1**, not done in P1-9's own commit (`plan-p1-9.md:611`). |
| **`backend/server.py`** — unlock ladder `:6163-6175`, progress payload `:6274-6283`, `/api/ranking-method` docstring `:6289-6298` | **P0-1** (comments `:6155-6175`, `save_anchor_route :7479`, import `:148`) · **P1-7** changes 3–5 · *(excluded **P1-8** would edit the same ladder)* | **P1-7 owns the ladder in Wave A**, after P0-1. `plan-p1-7.md:747-750` (R6): "Re-diff `server.py` immediately before editing; do not trust the line numbers in this plan after P0-1 merges." **See [SQ-1](#e-consolidated-operator-decision-list) for the P1-8 exclusion.** |
| **`backend/server.py`** — `_send_typed_push :15393`, `_NOTIF_FREQ_CAPS :15212`, `_NOTIF_DEDUP_CAPS :15230`, `_inject_likes_you_cards_impl :2813-2936`, `cron_daily_tick :16060+` | **P1-9** #5–#12 only | **Clean — no other P0/P1 claimant** (`plan-p1-9.md:600-602`). But `server.py` takes edits from P0-1, P0-3, P0-5 and P0-7 elsewhere: **P1-7 (Wave A) and P1-9 (Wave B) must not both hold `server.py` open.** Serialized by the wave plan. |
| **`backend/server.py`** — `_provider_auth_response` / `_mint_account_only_session` `:18005-18075` | **P0-5** (restructures) · **P1-3 only if Gate 4 = Option B** | In the recommended lane P1-3 touches **zero** `server.py` lines (`plan-p1-3.md:312`). Option B puts it inside the function P0-5 restructured — an additional argument for deferring. |
| **`backend/feature_flags.py`** | **P0-3** B5 (`growth.invite_join_link`, in P0) · **P1-9** #1 (`notif.trade_found`, `notif.*` block `:267-271`) · **P1-3** #4 (comment `:138-141`) · **P1-11** #17–18 (comments `:532`, `:536`) | **Four writers on one file, three regions.** Mechanical textual conflicts in one Python list are expected (`plan-p1-9.md:609`). Serialize: **P1-9 (Wave B) → P1-11 (Wave C) → P1-3 (independent lane, rebases last)**. Keep each addition inside its existing block so the diffs stay locally anchored. |
| **`config/features.json`** | **P0-3** B6 (in P0) · **P1-9** #2 (`notif.trade_found: false` at ~`:123`) · **P1-3** #3 (`auth.email_capture` `:58` false→**true**) · **P1-11** CP-4 (`_comment_draft_tab` prose at `:170`, values byte-identical) | Three P1 writers, three regions. Same serialization as `feature_flags.py`. **Note:** P1-3's is the round's only *value* flip on an existing key; P1-11's is comment prose only. |
| **`backend/tests/fixtures/flags/release.json`** | **P0-3** B6 (in P0) · **P1-3** #6 (`:59` → true) · **P1-9** (release fixture must carry `notif.trade_found: false`) | Serialize with the above. |
| **`backend/tests/fixtures/seed_ui_test_db.py`** | **P0-1** (`_validate_quickset :314-366`) · **P1-7** #16 (`app_user.anchors` handler) · **P1-9** #20 (`matches_seed.likes_you` + `notifications_seed`, ~`:1137-1163`) · P1-5 *reads* `:563-593` | **Three writers, three regions, plus new profile files that cannot collide.** Serialize **P0-1 (in P0) → P1-7 (Wave A) → P1-9 (Wave B)**, and **re-run the seeder end to end** after each rather than trusting a clean merge (`plan-p1-9.md:608`). |
| **`backend/tests/fixtures/profiles/`** | P0-1 (`quickset-done.json`) · P0-6 (`espn.json`) · **P1-7** (`anchors-done.json`, new) · **P1-9** (`likes-you-waiting.json`, new) | New files cannot collide. Clean. |
| **`backend/trade_service.py`** | **P1-9** #3 (`_DEFAULT_CFG` `:40`, after the F10 block `:369-373`) · **P1-7** touches `:1892` (pick-anchor logic) | Disjoint — config table vs engine code (`plan-p1-9.md:610`). Clean, but serialize by wave anyway. |
| **`backend/ranking_service.py`** | **P1-7** only (`:194`, `:1471`) | **Clean.** |
| `backend/database.py` `NOTIF_KIND_TO_BUCKET` `:9830-9851` | **P1-9** #4 only | **Clean.** P0-1 edits `database.py` elsewhere (`~:3358`, `:1968-1971`, `:181`) — different regions, but P0 lands first. |
| `web/privacy.html` | **P1-3** only | **Clean.** Public legal text — see [§E, privacy group](#e-consolidated-operator-decision-list). |
| `web/js/app.js` | **nobody edits it this round.** P1-1/2 explicitly leaves the dead builders at `:5285-5301` (OC-9); P1-9 flags the notification-list renderer as a **build-time verification item**, not an edit | See [§F, R-6](#f-risk-register) — the web notification renderer is a silent-failure surface. |

### A.5 Docs, Maestro and screen-capture collisions

| Artifact | Claimants | Resolution |
|---|---|---|
| `docs/api-reference.md` | P0-1, P0-3 (in P0) · **P1-1/2** (rows `:544`, `:546`) · **P1-7** (`GET /api/rankings/progress`) · **P1-9** (`POST /api/cron/daily-tick` response key) · P1-3 n/a · P1-10 n/a · P1-11 n/a | Four writers, four different rows. Append in merge order; rebase, do not merge blind. |
| `docs/cross-client-invariants.md` | P0-7 (`:268`, in P0) · **P1-1/2** (share-URL shapes) · **P1-5** C1 (`:268-271`) · **P1-7** (`:329-339`, `:358` — its load-bearing row) · **P1-9** (two new cross-client enum values) · **P1-10** 3.2 (`:268`) | **Five P1 writers, and three of them target `:268` §"Client analytics event contract".** Highest doc-conflict risk in the round. Mitigation: the three analytics writers (P1-1/2, P1-5, P1-10) fold their `:268` bullets into **T1** as a single edit; P1-7 and P1-9 append their own distinct sections later. |
| `docs/config-reference.md` | **P1-1/2** (`growth.share_landing` `:251`) · **P1-3** (`auth.email_capture` `:155`) · **P1-9** (`notif.trade_found` + 8 `model_config` rows) · **P1-7** (only if C2 makes `ANCHOR_UNLOCK_MIN` a `model_config` key) | Distinct rows. Serialize by wave. |
| `docs/glossary.md` | **P1-1/2** (share package, share link ladder) · **P1-7** (`:26` tier band, pick anchor) · **P1-11** #23 (`:120` Acquire tab → Trades tab) | Distinct entries. P1-11 last. |
| `docs/runbook.md` | **P1-1/2** (share-mint failures) · **P1-3** (`:355` + App Store label checklist) | Distinct sections. |
| `living-memory/LLD.md` | **P1-1/2** (AASA↔alias rule) · **P1-7** (two convention shifts) | Distinct entries. |
| `mobile/.maestro/capture/onboarding-tour@fresh.yaml` | **P0-8/9** (S8.1 header comment) · **P1-11** (`:131`, comment) | Near-miss, same file, both comment-only, different hunks (`plan-p1-11.md:496`). Trivial. |
| `mobile/.maestro/capture/trades.yaml` | **P0-2** (mandatory — its error leg asserts the bug) · **P1-11** (`trades@fresh.yaml:19`, `trades@single-format.yaml:43, 49` — comments) | Different files within the capture set except where noted; P0-2's is the substantive one and lands in P0. |
| `mobile/.maestro/capture/anchors.yaml` | **P1-7** only (header comment; three captures re-taken) | Clean. |
| `mobile/scripts/testid-lint-allow.txt`, per-folder `CLAUDE.md` registries | **P1-7** (`anchors.rung*`, `screens/CLAUDE.md`) · **P1-9** #19 (`components/CLAUDE.md`) · **P1-1/2** (3 testIDs) · **P1-11** #19–22 (4 registry edits across `navigation/`, `screens/`, `components/CLAUDE.md`) · P0-1, P0-5, P0-6 also register testIDs | Many small writers on the same three registry files. Serialize by wave; P1-11 last. |

#### Screen re-capture — the consolidated plan (**one pass, R1**)

Six sources invalidate captures. Individually they would trigger five separate capture runs at
4–7 min per screen. **Consolidate into one pass at the end of the P1 round.**

| Invalidator | Screens invalidated | Evidence |
|---|---|---|
| **P0-2** (in P0) | `trades` — `error.png` **plus every trades frame carrying a toast** (the offset moves) | `plan-p0-2.md:478-483` |
| **P1-11** | `matches` (9), `trios` (10), `quick-rank` (2), `draft-room` (4), `sheets-rank-menu` (2) = **5 screens / 27 captures flagged** — **and it under-reports**: only 2 of 32 screens declare `TabNav.tsx` as a source, so `trades` (7), `league` (11), `portfolio` (2), `tiers` (7), `quick-set` (1) will silently keep stale "Acquire" PNGs | `plan-p1-11.md:420-445`, CP-8 |
| **P1-1/2** | `calc`, `tiers`, and `trades` if M11/M12 taken | `plan-p1-1-2.md:414-417` |
| **P1-5** | `league` (all 6 variants) + `matches` — mandatory and eyeballed (R10, fold risk) | `plan-p1-5.md:423` |
| **P1-7** | `anchors` — 3 captures (`error`, `loading`, `question`); `screens/manifest.json:55` lists `anchorRows.ts` as a freshness source | `plan-p1-7.md:555-563` |
| **P1-9** | `topbar`/`settings` frames if the glyph + testIDs land | `plan-p1-9.md:339-342` |

**R1 — one consolidated re-capture**, after Wave C, before the P1 branch merges:

1. Run `mobile/scripts/screen-freshness.sh` and record what it flags.
2. Re-capture **every flagged screen** *plus* **every tab-stack screen whose frames include the
   bottom bar** — the manifest gap means freshness under-reports (P1-11 CP-8). Explicitly:
   `trades`, `league`, `portfolio`, `tiers`, `quick-set`, `matches`, `trios`, `quick-rank`,
   `draft-room`, `sheets-rank-menu`, `calc`, `anchors`, `settings`.
3. **Eyeball every shot** (`mobile/.maestro/README.md` law 23). P1-5 R10 (fold regression on
   League Home) and P1-1/2 manual test 10 (PNG footer legibility at 360px) are *decided from the
   screenshots*, not asserted by a flow.
4. Preserve pre-fix PNGs where a plan asks (`screens/CLAUDE.md` artifact-of-record rule).

**Cost note, stated honestly:** P0 runs its own captures on its own branch as part of its tier-1
ship gates. R1 does not eliminate that; it eliminates the *four extra* P1 passes. `trades` gets
captured twice across the program (once per branch), not five times.

**Follow-up filed, not fixed:** every tab-stack screen should declare
`mobile/src/navigation/TabNav.tsx` in its `screens/manifest.json` `source` list. Left unfixed it
mis-reports on the next nav change too (P1-11 CP-8b).

### A.6 The `DECISIONS.md` ID collision — **nine claimants**

`D-011` is claimed by, at minimum: P0-3, P0-7, P1-1/2 (`plan-p1-1-2.md:438`), P1-3
(`plan-p1-3.md:207` as `D-0NN`), P1-5 (C3), P1-7 (`plan-p1-7.md:478`, hedged as "D-012, or the
next free id"), P1-9 (#25, `D-0NN`), P1-10 (3.3, explicitly "re-check at build time — P0-7 also
claims `D-011`"), P1-11 (#24). `G-013` has at least two claimants (P0-3, P1-1/2).

**Rule:** no agent uses the ID printed in its plan. IDs are allocated **at write time, in merge
order**, by re-reading `living-memory/DECISIONS.md` (and `GOTCHAS.md`, `MISTAKES.md`,
`OPEN_QUESTIONS.md`) immediately before writing. Allocation order within P1 = the merge order in
[§C](#c-merge-order): T1 (none) → P1-7 → P1-10 → P1-1/2 → P1-5 → P1-9 → P1-11 → P1-3.

---

## B. File ownership table

One owner per file per wave. **No file has two simultaneous owners.** Where that is impossible,
the row says so and the items are serialized into different waves instead.

### Wave T (serial, single agent)

| Owner | Files |
|---|---|
| **T1 taxonomy agent** | `backend/analytics_taxonomy.py` · `backend/analytics_queries.py` · `backend/tests/test_events_api.py` · `backend/tests/test_share_package.py` · `backend/tests/test_analytics_p0.py` · `docs/business/analytics/2026-07-17-tracking-plan-v2.md` · `docs/business/analytics/2026-08-11-p1-5-addendum.md` (new) · the §"Client analytics event contract" block of `docs/cross-client-invariants.md` (`:268-271`) |

**After T1 merges, `analytics_taxonomy.py` and `analytics_queries.py` are frozen for the rest of
the round.** Any later need routes back through a T1 amendment commit with the same gate.

### Wave A (three agents, concurrent)

| Owner | Files (exclusive) |
|---|---|
| **A1 — P1-7** | `backend/ranking_service.py` · `backend/server.py` *(§ unlock ladder `:6163-6175`, progress payload `:6274-6283`, `/api/ranking-method` docstring `:6289-6298` — **exclusive hold on `server.py` for this wave**)* · `mobile/src/utils/anchorRows.ts` · `mobile/src/screens/PickAnchorScreen.tsx` · `mobile/src/components/AnchorSheet.tsx` · `mobile/scripts/testid-lint-allow.txt` · `backend/tests/test_anchor_unlock.py` (new) · `backend/tests/test_pick_anchor.py` · `mobile/tests/check-anchor-labels.js` (new) · `backend/tests/fixtures/profiles/anchors-done.json` (new) · `backend/tests/fixtures/seed_ui_test_db.py` *(**exclusive hold for this wave**)* · `mobile/.maestro/capture/anchors.yaml` · `mobile/.maestro/flows/p1-7-anchor-unlock.yaml` (new, C6) |
| **A2 — P1-10** | `mobile/src/screens/SleeperConnectScreen.tsx` · `mobile/src/navigation/RootNav.tsx` *(**exclusive for this wave**)* · `mobile/src/components/SendInSleeperButton.tsx` *(**exclusive**)* · `mobile/src/screens/SettingsScreen.tsx` *(**exclusive for this wave**)* · `docs/integrations/sleeper.md` |
| **A3 — P1-1/2** | `mobile/src/api/calc.ts` · `mobile/src/utils/shareLinks.ts` (new) · `mobile/src/utils/deepLinks.ts` *(**exclusive for this wave**)* · `mobile/src/components/ShareTradeImage.tsx` · `mobile/src/components/Toast.tsx` · `mobile/src/components/InLeagueCalculator.tsx` · `mobile/src/screens/TradeCalculatorScreen.tsx` · `mobile/src/screens/TiersScreen.tsx` · `mobile/src/screens/TradesScreen.tsx` *(**exclusive**, and only if OC-2 = include)* · `backend/tests/test_universal_links.py` · `mobile/.maestro/flows/growth/share-links.yaml` (new) |

**Wave A disjointness proof.** A1 ∩ A2 = ∅. A1 ∩ A3 = ∅. A2 ∩ A3 = ∅ — the near-misses are
`RootNav.tsx` (A2 only; A3 does not touch it) and `SendInSleeperButton.tsx` (A2 only). `server.py`
is held by A1 alone; A2 and A3 make no backend edits beyond tests in files nobody else holds.

### Wave B (two agents, concurrent)

| Owner | Files (exclusive) |
|---|---|
| **B1 — P1-5** | `mobile/src/screens/LeagueScreen.tsx` *(**exclusive**)* · `mobile/src/screens/MatchesScreen.tsx` *(**exclusive for this wave**)* · `mobile/src/components/InviteLeaguematesBanner.tsx` · `mobile/src/components/InviteLeaguematesCard.tsx` (new) · `mobile/src/utils/inviteShare.ts` (new) · `mobile/src/utils/leagueUnlocks.ts` · `mobile/.maestro/flows/growth/invite-promotion.yaml` (new) · `docs/design/components.md` |
| **B2 — P1-9** | `backend/server.py` *(**exclusive for this wave** — push dispatcher, cap maps, `_inject_likes_you_cards_impl`, `cron_daily_tick`)* · `backend/trade_service.py` · `backend/database.py` · `backend/feature_flags.py` *(**exclusive for this wave**)* · `config/features.json` *(**exclusive for this wave**)* · `backend/tests/fixtures/flags/release.json` *(**exclusive for this wave**)* · `backend/tests/fixtures/seed_ui_test_db.py` *(**exclusive for this wave**)* · `backend/tests/fixtures/profiles/likes-you-waiting.json` (new) · `backend/tests/test_trade_found.py` (new) · `mobile/src/hooks/usePushNotifications.ts` · `mobile/src/components/TopBar.tsx` · `mobile/src/screens/SettingsScreen.tsx` *(**exclusive for this wave**)* · `mobile/src/utils/deepLinks.ts` *(**exclusive for this wave**)* · `mobile/.maestro/flows/p1-9-trade-found-inbox.yaml` (new) |

**Wave B disjointness proof.** B1 ∩ B2 = ∅. The files B2 holds that A-wave agents also touched
(`server.py`, `deepLinks.ts`, `SettingsScreen.tsx`, `seed_ui_test_db.py`) are all released by
Wave A before Wave B starts — that is the reason P1-9 is in Wave B and not Wave A.

### Wave C (one agent, serial by necessity)

| Owner | Files |
|---|---|
| **C1 — P1-11** | `mobile/src/navigation/TabNav.tsx` · `mobile/src/screens/RankScreen.tsx` · `mobile/src/screens/MatchesScreen.tsx` · `mobile/src/screens/TradeFinderHubScreen.tsx` · `mobile/src/navigation/RootNav.tsx` · `mobile/src/utils/testRouteEntry.ts` · `mobile/src/screens/PickAssignmentScreen.tsx` · `mobile/src/screens/DraftRoomScreen.tsx` · `backend/feature_flags.py` · `config/features.json` (comment prose only, CP-4) · `mobile/src/navigation/CLAUDE.md` · `mobile/src/screens/CLAUDE.md` · `mobile/src/components/CLAUDE.md` · `docs/glossary.md` · 12 `mobile/.maestro/capture/*.yaml` header comments · `mobile/.maestro/04-tabs-navigation.yaml` |

**Why P1-11 cannot be parallelised.** It is the *last* writer on `TabNav.tsx` (after P0-7),
`RankScreen.tsx` (after P0-1) and `MatchesScreen.tsx` (after P0-6 and P1-5), and it edits three
per-folder `CLAUDE.md` registries that four other items also write. It is five words of user-visible
change with the widest file footprint in the round. **Serialize it last** (its own recommendation,
`plan-p1-11.md:504`).

### Independent lane (unschedulable until its gates clear)

| Owner | Files |
|---|---|
| **L1 — P1-3** | `web/privacy.html` · `config/features.json:58` · `backend/feature_flags.py:138-141` · `backend/tests/test_email_capture.py` · `backend/tests/fixtures/flags/release.json:59` · `docs/config-reference.md:155` · `docs/data-dictionary.md:814-817` · `docs/business/product/2026-07-17-email-capture-spec.md` · `docs/runbook.md:355` |

**Not a wave — a lane.** P1-3 is blocked on legal/governance decisions with an unbounded timeline
(Gate 2 asks whether a lawyer reads the diff). It shares `config/features.json`,
`backend/feature_flags.py` and `release.json` with B2 and C1. **It rebases and lands last**,
whenever its gates clear — possibly after the rest of the round has shipped.

### Where single ownership is impossible

Two cases. Both are resolved by **serialization, not partition**:

1. **`backend/analytics_taxonomy.py`** — three P1 items must each write to two frozensets, and two
   of them must *modify existing rows*. Partition is impossible (it is one dict and one frozenset).
   Resolved by commit **T1**: one owner, all three items' content, before any client wiring.
2. **`mobile/src/screens/MatchesScreen.tsx`** and **`backend/feature_flags.py` / `config/features.json`**
   — three writers each, disjoint regions, but concurrent edits to one file are exactly how a clean
   merge silently drops a hunk. Resolved by wave separation (B1 → C1, and B2 → C1 → L1).

`plan-p0-6.md:622-655` proposed a line-range split of `SendInSleeperButton.tsx` between two agents;
P0's own HLD **rejected** it as S-23 in favour of a sequential handoff (`hld.md:972`). **This HLD
adopts the same posture: no file is ever split by line range between concurrent agents.**

---

## C. Merge order

One authoritative sequence. Each step has a precondition and a verification step. Deviation is an
operator decision, recorded in the affected scope block.

| # | Step | Precondition | Verification |
|---|---|---|---|
| **0** | **P0 merges to `main`** — `p0-remediation-2026-08-10` (P0-1, -2, -3, -5, -6, -7, -8, P0-9 test-prep), in its own HLD's internal order (`hld.md`: W0-TAX → W1-BE/P05/P06 → W2-P07/TS/P03) | P0's own ship gates green | `git fetch origin && git log origin/main` shows the P0 commits; record the sha. **This is a gate, not an assumption** (P-1). |
| **0.5** | **Rebase the P1 branch onto post-P0 `origin/main`; run [§G](#g-re-verification-checklist) per item** | Step 0 | Every §G row answered in writing in that item's scope block. Any row that comes back "the plan's premise no longer holds" **stops that item's build** and returns to planning. |
| **1** | **T1 — P1 taxonomy registration** (contents in [§A.2](#a2-backendanalytics_taxonomypy--five-claimants-default-deny-and-silent)) | Step 0.5. **No P1 client `track()` exists yet.** | Merge → **Render deploys** → `GET /api/analytics/health`, then one hand-rolled `POST /api/events` per new name with its **full** prop set. **`dropped == 0` and every prop echoed back.** Failing that, no client wave starts (`plan-p1-5.md:249`, `plan-p1-10.md:311-313`). |
| **2** | **Wave A** — A1 (P1-7), A2 (P1-10), A3 (P1-1/2) concurrent; three commits | Step 1 verified. Wave-A operator decisions answered ([§E](#e-consolidated-operator-decision-list)). | Per commit: `pytest backend/tests/` green · `npx tsc --noEmit` clean · `mobile/scripts/testid-lint.sh` exit 0 · the item's new Maestro flow green. **A1 additionally:** the `test_anchor_unlock.py` matrix, and the anchor unlock proven on-device (or its waiver written, C6). **A3 additionally:** rung-B degradation asserted (block 2 of `share-links.yaml`) — the assertion that proves the artifact is never link-free. |
| **3** | **Wave B** — B1 (P1-5), B2 (P1-9) concurrent; two commits | Step 2 merged. **B1 additionally requires T1's `invite_shared` prop-row extension verified live** (a `POST /api/events` carrying `surface` + `not_joined` that echoes both). **B2 additionally requires OC-1..OC-4, OC-7 answered.** | Per commit as above. **B1:** Maestro block 2 asserts `league.progress-invite` **absent** in the card state (the only assertion protecting the no-duplicate-CTA principle). **B2:** flag OFF + `trade_found_dry_run=1` confirmed in `config/features.json`; `cron_daily_tick` response byte-identical with the flag off. |
| **4** | **Wave C** — C1 (P1-11); one commit | Step 3 merged. CP-1 and CP-2 answered (both blocking). | `grep -rn "Acquire" mobile/.maestro/ \| grep -v "#"` → 0 hits (it already is; prove it stayed). `04-tabs-navigation.yaml` green. Full smoke (11 flows) or CP-7's tier-2 subset, per the operator's call. |
| **5** | **R1 — one consolidated screen re-capture** ([§A.5](#screen-re-capture--the-consolidated-plan-one-pass-r1)) | Step 4 merged. | `screen-freshness.sh` clean afterwards; **every shot eyeballed** (law 23); pre-fix PNGs preserved where a plan asks. `qa/sim-runs/last-sim-run.json` written; `TEST_LEDGER.md` logged. |
| **6** | **P1 branch merges to `main`** | Steps 1–5. `githooks/pre-push` satisfied. | Render auto-deploys; EAS → TestFlight per the normal release path. |
| **L** | **P1-3 lands whenever its gates clear** — before, between or after any of steps 2–6, but always rebasing onto whatever is on `main` | Gates 0, 1, 2 signed off (`plan-p1-3.md:323`: "Nothing in this plan may proceed past gate 1 without sign-off"). Legal review per Gate 2. | Its `test_release_flag_and_privacy_policy_ship_together` is the durable guard — flag ON with either retired sentence surviving in `web/privacy.html` must be a **red build**. Tier-4 gate logged in `TEST_LEDGER.md`. |

### Reconciling the three conflicting proposed orders

The individual plans proposed three orders that differ in **emphasis, not substance** — all three
are satisfied by the sequence above, because everything they sequence *against* lives inside P0,
which merges as a unit at step 0.

| Plan | Proposed | Satisfied by |
|---|---|---|
| **P1-1/2** (`plan-p1-1-2.md:514`) | `P0-2 → P0-3 → P1-1/2` | Step 0 (both are P0 commits) then step 2/A3. |
| **P1-5** (`plan-p1-5.md:402`, OC-11) | serialize `P0-3 → P0-7 → P1-5` | Step 0 (P0's own HLD already orders P0-3 B4 into W0-TAX and P0-7 into W2) then step 3/B1. |
| **P1-7** (`plan-p1-7.md:712-718`, R1) | P0-1 **widens the anchor bug on merge**, so sequencing is load-bearing — P1-7 must follow *closely* | **This is the constraint that fixes Wave A's membership.** P1-7 is placed in the **first** P1 build wave, immediately after T1. It is the only P1 item whose delay actively grows a defect cohort. If P1-7 slips past step 2, **say so to the operator explicitly** rather than letting the gap widen quietly. |
| **P1-11** (`plan-p1-11.md:504`) | `P0-1 → P0-7 → (P0-2, P0-6, P0-8/9) → P1-11 → one re-capture` | Step 0 then steps 4 and 5. |
| **P1-9** (`plan-p1-9.md:687`, OC-5) | merge after P0-1, flag ON + dry-run 1 | Step 3/B2. |
| **P1-10** (`plan-p1-10.md:604`, Ckpt D) | one shared P1 taxonomy commit first | **Step 1 — T1.** Adopted and widened. |

**Where T1 lands, stated plainly:** T1 is the **first** P1 commit — after the whole P0 merge,
before Wave A. It is the P1 mirror of P0's own W0-TAX commit (`hld.md:340`), for the same reason,
and it carries the same non-negotiable deploy-and-verify gate before any client wiring.

---

## D. Wave plan

| Wave | Items | Concurrency | Why |
|---|---|---|---|
| **T** | T1 taxonomy | **Serial, 1 agent** | Three items' names in two frozensets, two of them modifying existing rows. Cannot be partitioned; must be verified live before any client fires. |
| **A** | **P1-7**, **P1-10**, **P1-1/2** | **3 concurrent** | Disjoint file sets ([§B](#b-file-ownership-table)). All three are *mechanical* once their decisions are in: a backend predicate + label derivation (P1-7), five `track()` insertions and four navigate args (P1-10), a URL ladder and two share affordances (P1-1/2). **P1-7 must be here**, not later — P0-1 grows its locked cohort daily. |
| **B** | **P1-5**, **P1-9** | **2 concurrent** | Disjoint from each other; both blocked on files Wave A holds (`deepLinks.ts`, `SettingsScreen.tsx`, `seed_ui_test_db.py`, `server.py`). P1-5 additionally needs T1's `invite_shared` prop-row extension **verified live**, which is a stronger precondition than "T1 merged". |
| **C** | **P1-11** | **1, serial** | Last writer on `TabNav.tsx`, `RankScreen.tsx`, `MatchesScreen.tsx` and three `CLAUDE.md` registries. Cheapest change, widest footprint. |
| **R** | R1 re-capture | **1, serial** | One pass covering six items' invalidations. |
| **L** | **P1-3** | **independent lane** | Governance-gated with an unbounded timeline. |

### Why P1-3 and P1-9 are not in Wave A, despite looking small

The briefing is right that these two carry a different kind of load, and it changes the schedule:

- **P1-3 is governance-gated, not engineering-gated.** Its change list is nine files and no mobile
  diff, and its sim-gate tier is **4** (`plan-p1-3.md:243`). But `plan-p1-3.md:323` states:
  "Nothing in this plan may proceed past gate 1 without sign-off," and Gate 2 asks *whether a
  lawyer reads the privacy-policy diff* — a question whose answer is not on any engineering
  timeline. It crosses **four bright lines** (data-classification, flag surface, public legal text,
  conditionally analytics) and **cannot be run express-lane** (`plan-p1-3.md:225`, `:382`). Its
  Gate 0 is a *measurement* — ship one log line, watch repeat Apple sign-ins for ~a day — that may
  dissolve the item's entire urgency framing. **Putting it in a build wave would force the legal
  question to resolve on a sprint clock. It is a lane, not a wave.**
- **P1-9 is parameter-gated.** Eight `model_config` defaults (`plan-p1-9.md:326`, OC-3), plus OC-1
  (which preference bucket — the consequential one, because it determines whether the Settings row
  `sub` copy and the `PushPrimingModal` consent bullets must change), OC-2 (gate strength), OC-4
  (how much the push copy reveals about a leaguemate), and OC-7 (does the inbox row ship when the
  push is suppressed — the answer to which determines whether the feature is testable on a
  simulator at all). **None of these is an engineering question**, and OC-1's answer changes the
  file list. Building before they are answered means building the wrong thing twice.

Both are therefore **decision-throughput-bound, not build-bound**. Wave A is reserved for items
whose remaining work is mechanical.

---

## E. Consolidated operator decision list

**53 checkpoints across seven plans, deduplicated to 46 distinct decisions**, grouped four ways.
Two cross-item items in the source plans (P1-5 OC-11 and P1-10 Ckpt D, both "how do we sequence the
taxonomy commit?") are **adjudicated in this HLD** ([§A.2](#a2-backendanalytics_taxonomypy--five-claimants-default-deny-and-silent))
and removed from the operator's queue. Three pairs are merged as duplicates, noted inline.

**BUILD-BLOCKING = 27.** **RELEASE-BLOCKING only = 19.**

### E.1 Product (18)

| ID | Owning item | Decision | Recommendation | Blocks | Blocked until answered |
|---|---|---|---|---|---|
| **PR-1** | P1-11 CP-1 | Reverse #245 ("Acquire" → "Trades")? It was an explicit operator ask on 2026-08-05; #246 removed the two-channel hub that justified it, and the app now contradicts itself ("Acquire tab" above a "Go to Trades" button) | **Yes, revert** | **BUILD** | All of Wave C. Edit 1 cannot start. |
| **PR-2** | P1-11 CP-2 | Confirm the scope line: rename "Acquire" only where it names the **tab** (6 sites), leave it where it means the trade **direction** (9 user-visible sites, mobile + web) | **Hold the line as drawn** | **BUILD** | Wave C's change list. Widening it pulls in `web/` and `docs/design/components.md:69`. |
| **PR-3** | P1-11 CP-3 | `TradeFinderHubScreen.tsx:487` dead page title — change the word, or let A-27 delete the file at P2? | **Change it anyway (~0 cost)** | release | One edit in Wave C. |
| **PR-4** | P1-11 CP-5 | A/B the tab name, or just ship? Audit labels A-20 an "A/B candidate"; 16 production users vs a ~400-per-arm floor | **Ship, no flag, no split.** Compare pre/post on P0-7's `tab_selected` | **BUILD** (if the harness is wanted) | Whether Wave C adds a flag at all. |
| **PR-5** | P1-5 OC-1 | Social-proof copy framing: (a) factual/self-interested, (b) altruistic, (c) named leaguemates | **(a)** — the only framing that stays literally true if the mechanic changes, and the only one that renders identically on both screens from the aggregate alone | **BUILD** | B1's copy table and `inviteSocialProof()`'s implementation. |
| **PR-6** | P1-5 OC-2 | Matches empty-state button hierarchy: invite primary (the audit's literal ask), or "Find a trade" primary with invite secondary | **(b)** — "Find a trade" converts today with zero dependencies; invite pays off in days and depends on someone else acting | **BUILD** | B1's render ladder. |
| **PR-7** | P1-5 OC-4 | ESPN / non-Sleeper gate: withhold the promoted card on non-Sleeper leagues, show everywhere, or show with different copy | **(a) gate to Sleeper** — the invite link cannot resolve for a non-Sleeper league id (P0-3 D4); promoting it scales a known-broken journey and burns the one social ask a user gets | **BUILD** | B1's render ladder **and** Maestro block 4. |
| **PR-8** | P1-5 OC-5 | Suppress the inline link when the card renders? | **(a) suppress** — two invites on one screen is the same disease in a better coat | **BUILD** | B1's `onInvite` conditional at `LeagueScreen.tsx:700`. |
| **PR-9** | P1-5 OC-7 | OPTIONAL-M: invite button in the members overlay (~8 lines, one testID, one `surface` enum value) | **In** | **BUILD** | Whether `members_overlay` exists in the closed `surface` enum — **which is a T1 decision**, since the enum is documented in the prop-row comment. Answer before T1. |
| **PR-10** | P1-5 OC-8 | Zero-not-joined state: card absent, or an affirmation | **(a) absent** | **BUILD** | B1's render ladder. |
| **PR-11** | P1-1/2 OC-2 | Include the liked-but-unmatched trade share (M11/M12, `TradesScreen.tsx:2735-2766`)? The audit scoped P1-2 to the calculator, but the same stale comment lives there and the audit's own §7 calls it "the more common case" | **Include** (~20 lines, kills the second false comment) | **BUILD** | Whether A3 holds `TradesScreen.tsx` at all, and whether `trades` joins the R1 capture list. |
| **PR-12** | P1-1/2 OC-4 | Should a tier share link land on the shared position? `TiersScreen` reads no route params, so `/s/tiers/wr/matt` opens at QB | **(a) ship v1 without it** — the alias prevents the error toast, which is the actual bug | **BUILD** | ~15 lines in A3. |
| **PR-13** | P1-1/2 OC-5 | Should the Quick Set walk's completion also offer a share? | **(a) leave it** — it is a native `Alert`, untestable by Maestro, already carrying a next-step | release | Whether `quick-set` joins the R1 capture list. |
| **PR-14** | P1-1/2 OC-6 | Draft picks render `"Unknown player"` on the package landing (`og_image.py:646-650`) | **(b) fall back to rung B when any id is a `pick_id`** — zero backend work; keeps today's `?ref=` link rather than producing an embarrassing landing | **BUILD** | A3's ladder logic in `shareLinks.ts`. |
| **PR-15** | P1-1/2 OC-7 | The landing's fairness bar (`og_image._compute_fairness`, a cosmetic `search_rank` heuristic) can contradict the app's verdict in the PNG the user just shared | **(b) as a fast-follow, not this plan** — storing the sharer's verdict is a **schema change**, its own bright line | release | Nothing in this round; file it. |
| **PR-16** | P1-9 OC-2 | Gate strength: counterparty intent only, + a dual-board lane, or + a score threshold | **A for v1, B specced and deferred, C never.** C is "a product judgement disguised as a parameter" — it is how "three mediocre pushes a day" happens | **BUILD** | B2's entire gate design (`_trade_found_candidate`). |
| **PR-17** | P1-9 OC-4 | Push copy — name the leaguemate and player (A), name the player only (B), or neutral (C). Also: does the bell row get the `match` glyph or its own? | **A** (concrete-inventory rule; already disclosed in-app at `TradeCard.tsx:344-347`). **C fails the F10 guardrail outright.** Choose **B** if lock-screen privacy outweighs clarity | **BUILD** | B2's copy + `TopBar.tsx` `ROW_GLYPHS`. Interacts with **PV-4**. |
| **PR-18** | P1-9 OC-7 | Does the inbox row ship even when the push is suppressed? | **Yes** — it is the only artifact independent of push permission, prefs, quiet hours and the OS, and **the only thing a simulator can assert.** Say no and the feature becomes untestable and invisible to everyone who declined the primer | **BUILD** | Whether B2 has any Maestro coverage at all. |

### E.2 Privacy and legal (7)

| ID | Owning item | Decision | Recommendation | Blocks | Blocked until answered |
|---|---|---|---|---|---|
| **PV-1** | P1-3 Gate 0 | **Measure the urgency claim before acting on it.** The audit says Apple shares the address on first authorisation only. **The code contradicts the premise** — FTF reads `email` from the verified identity-token JWT (`server.py:18025`), not the first-auth-only native credential property, and `accounts.py:325-333` has a repeat-auth backfill with a test pinning it | **Probe first (Option A)** — one log line, ~a day. It determines whether the legal review is a rush job or a considered one. The audit was already wrong once on this item | **BUILD** | All of P1-3. |
| **PV-2** | P1-3 Gate 1 | Flip `auth.email_capture` → `true`: in `config/features.json` in the same commit as the policy (A), via Render's `FTF_FLAGS` env var (B), or don't flip (C) | **A, sequenced after Gate 0.** Explicitly **forbid B** for this flag and record the prohibition in `DECISIONS.md` — it is the only mechanism that can decouple capture from the policy | **BUILD** | All of P1-3. Nothing proceeds past this gate without sign-off. |
| **PV-3** | P1-3 Gate 2 | **Who writes the privacy-policy rewrite, and does a lawyer read it?** `web/privacy.html:1-8` carries a standing operator TODO that the document has never had legal review. This is the first change that *expands* a collection claim | **A if a lawyer is reachable in the launch window; otherwise C (in-repo `/legal-privacy` skill) plus a dated header note recording that review did not happen.** In no case does a build agent write final policy text unreviewed and merge it — **this plan deliberately does not draft that text** | **BUILD** | All of P1-3. |
| **PV-4** | P1-9 R4 *(surfaced by OC-4)* | A lock-screen banner naming a leaguemate and a player exposes their trade interest to anyone glancing at the phone | Bundled into **PR-17**; the non-naming fallback is option B | **BUILD** | B2's copy. |
| **PV-5** | P1-1/2 OC-3 | **Tier-share privacy posture.** `/s/tiers` + `/og/tiers` publish a named user's board with **no flag and no opt-in**, while `/u/*` is dark behind `profiles.public_pages` **and** `profiles.user_toggle` — and #221 just *hid* the public-profile row | **(b) gate the affordance on `growth.share_landing`** (already ON, no new flag), leave the route unchanged. **Separately:** none of the options stops direct enumeration of `/og/tiers/qb/<any-username>.png` today. If that is unacceptable it is a **P0-class finding of its own** and should be filed separately | **BUILD** | A3's suppression conditions on `TiersScreen`. |
| **PV-6** | P1-3 Gate 3 | What does the policy promise about removal? There is **no** way for a user to remove their address short of deleting the account; `email_unsubscribed_at` has no writer | **(a) disclose exactly the current state.** Do **not** write an unsubscribe promise the code cannot keep | release | P1-3's policy text. |
| **PV-7** | P1-3 Gate 5 | App Store privacy label — a **Contact Info → Email Address** declaration (linked to user) at the next submission | **A: flip now, update the label at the next submission**, with the runbook checklist entry treated as **mandatory** — "wrong privacy label = rejection" is a recorded in-repo risk | release *(submission gate)* | Nothing in this round; blocks the next submission. |

### E.3 Analytics (8)

| ID | Owning item | Decision | Recommendation | Blocks | Blocked until answered |
|---|---|---|---|---|---|
| **AN-1** | P1-10 Ckpt A | The fourth Sleeper-Connect event: `sleeper_connect_failed` or `sleeper_connect_otp_step` (the literal wording of the resolutions doc) | **`sleeper_connect_failed`.** Option 2 needs a MutationObserver against an **unverified** Sleeper DOM and would most likely ship a **permanently-zero event indistinguishable from a real zero**. This deviates from the resolutions doc's wording, and deviates *toward* a verified signal | **BUILD — and before T1** | **T1's name list.** A wrong answer here means re-opening the frozen file. |
| **AN-2** | P1-10 Ckpt B | Does `sleeper_connect_captured` fire on link success (a clean connect-success rate, mutually exclusive partition) or on token arrival (the literal ESPN mirror, double-counts on retry) | **Link success**, with the deviation stated in the addendum so the two platforms' curves are never naively compared | **BUILD** | A2's client wiring; T1's prop-row comment. |
| **AN-3** | P1-5 OC-3 | Event name `invite_shared` (what the client already fires, what P0-3 registers) vs `invite_sent` (tracking plan v2 §S3). **Nothing in code reserves `invite_sent`** — it is a prose-only reservation | **`invite_shared`**, and amend the tracking plan to match runtime. Adopting `invite_sent` instead must then be done in **both P0-3 and P1-5, consistently, in the same wave** | **BUILD — and before P0 merges if the answer is `invite_sent`** | T1, and retroactively P0-3 B4. |
| **AN-4** | *this HLD* (gap found in P1-1/2) | **INTENT vs NON_INTENT for the three new share events.** `plan-p1-1-2.md` specifies `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS` but **is silent on `NON_INTENT_EVENTS`.** `INTENT_EVENTS` is a **deny-list** (`analytics_queries.py:65`) — silence means all three land INTENT by default | `calc_trade_shared` and `tier_board_shared` are genuine user actions ⇒ INTENT. **`share_package_created` is a system outcome, not a user intent** ⇒ recommend **NON_INTENT**. This is the same class of error P1-5 A3 was written to prevent | **BUILD — and before T1** | **T1.3.** Getting this wrong step-changes DAU/WAU on ship day, silently and permanently. |
| **AN-5** | P1-5 OC-6 | Ship `invite_cta_tapped`, or only shown + shared? The gap between them is the OS-share-sheet abandon rate, today entirely invisible | **In** — one registry row, one prop row, one call | **BUILD — before T1** | T1's name list. |
| **AN-6** | P1-3 Gate 4 | Ship the `email_captured` analytics event? | **Defer to the capture-UI build.** In this lane capture is a server-side side effect of signing in, not a user action, and it is already exactly countable from the `accounts` table. Option B costs an import-time-assert blast radius, an intent-by-default DAU decision, an edit inside the function **P0-5 restructures**, and a **sixth** claimant on `analytics_taxonomy.py`. **If elected anyway, it lands in T1**, not in a later commit | **BUILD** *(of P1-3 only)* | P1-3's change list; **and T1's contents if the answer is B**. |
| **AN-7** | P1-9 OC-6 | Is `push_opened` INTENT or NON_INTENT? It is absent from `NON_INTENT_EVENTS`, so it lands INTENT by the deny-list default and enters DAU/WAU/retention **on its first emission ever** | **Leave INTENT** — a push open is a real return, and the incremental effect is ~nil. If the operator prefers NON_INTENT, that is a one-line edit to a P0-7-owned file and **routes into T1**, not into P1-9's commit | release *(but routes into T1 if changed)* | T1.3 if the answer is NON_INTENT. Either way the emission date is a seam and belongs in the CHANGELOG. |
| **AN-8** | P1-5 OC-10 | Defer the invite copy A/B? It cannot be read honestly today — `experiment_exposed` is in `FUNNEL_CRITICAL` and the mobile SDK mirror but **not** in `ALLOWED_CLIENT_EVENTS`, so exposure is unmeasurable and any read is arm-correlated-diluted | **Ship one variant now, register the events, queue the A/B behind P0-7 F1.** Shipping a promoted invite that is measurable beats shipping an experiment that isn't. Wanting the A/B in this wave makes F1 a hard prerequisite and moves P1-5 from M to L | release | Nothing; changes P1-5's effort estimate if answered "now". |

### E.4 Release, rollout and test scope (13)

| ID | Owning item | Decision | Recommendation | Blocks | Blocked until answered |
|---|---|---|---|---|---|
| **RL-1** | P1-1/2 OC-1 | **P1-1/2 ships live on merge.** `growth.share_landing` is `true` at `config/features.json:125` (verified) — every change is user-visible the moment it merges. Accept, or add `growth.share_v2` default OFF? | **Accept.** The finding is that these paths convert zero; a dark flag preserves exactly that. Adding a flag is itself a bright-line surface change, to be decided **before** build, not during | **BUILD** | Whether A3 adds a flag surface at all. **See [§F, R-1](#f-risk-register) — this is not the only live-on-merge item.** |
| **RL-2** | P1-7 C2 + P1-9 OC-3 *(merged: both are "confirm the numbers")* | **P1-7:** `ANCHOR_UNLOCK_MIN = 40` — confirm, and should it be a `model_config` key rather than a Python constant? **P1-9:** all **eight** `trade_found_*` defaults (cooldown 7d, quiet 5d, max age 7d, active 21d, grace 48h, min like age 30m, max per tick 50, dry run 1) | **P1-7: 40, as a constant** (equals the trio bar, so the product explains one number); the `model_config` lever flips one docs row to YES if wanted. **P1-9: take the eight defaults as recommended** — all are `PUT /api/admin/config`-changeable without a deploy | **BUILD** | A1's constant and docs table; **all of B2**. |
| **RL-3** | P1-9 OC-1 | **Which preference bucket does `trade_found` live in?** (a) `trade_matches` — default ON for anyone who granted push, maximum reach, **but requires the Settings row `sub` copy edit AND a `PushPrimingModal` consent-bullet edit**; (b) `reengagement` — default OFF, safest, ~nobody ever receives it; (c) unmapped — **do not do this** | **(a), conditional on the gate staying counterparty-intent-only.** **Bucket strength and gate strength are one decision, not two** — if the gate ever widens to model-scored candidates (PR-16), the kind must move to `reengagement` in the same change. Write that coupling into `DECISIONS.md` | **BUILD** | B2's file list — (a) adds `SettingsScreen.tsx` copy **and** `PushPrimingModal` to the diff; (b) does not. |
| **RL-4** | P1-9 OC-5 | Rollout sequence and graduation criterion | Merge after P0-1 with the flag **ON** and `trade_found_dry_run = 1`; read `daily-tick` counters for **14 days**; graduate only if `dry_run_would_push` ≤ 1/user/week **and** the `blocked_*` mix is legible; then the operator's device allowlist; then general. **`candidates == 0` for the window ⇒ ship it OFF and revisit after invite/density work. Do not loosen the gate to make the counter move** | release | Nothing in the build; governs the post-merge window. |
| **RL-5** | P1-7 C1 *(merged with P0-1 Q5)* | **Suppress the first-unlock push fan-out for the anchor cohort?** Crossing 40 takes the `was_first` branch: `ranking_complete_first_time` fires and `league_member_unlocked_trades` pushes to **every joined leaguemate** (`server.py:6228-6265`). P0-1 raises the identical question for the Quick Set cohort as its Q5 | **Match P0-1's answer, whatever it is.** **The two deploys must not stack unnoticed** — otherwise one release window produces two separate bursts of "@user just unlocked Trade Finder" | release *(blocking on merge only if the answer is "suppress")* | A1's merge, conditionally. |
| **RL-6** | P1-7 C3 | Confirm the label direction: `ANCHOR_ROWS` conforms to `TIER_LABEL`. Evidence: ~11 code/doc locations across four clients versus one | **Conform `ANCHOR_ROWS`.** Cost: three buttons lose their "1 " prefix, the top button gains a "+". The alternative touches mobile, web ×3, the extension, OG rendering, the style guide, the FAQ and the glossary | **BUILD** | A1's entire label design. |
| **RL-7** | P1-7 C4 | `no_value`: display "FA", or keep "No value" as a ninth vocabulary item? | **A ("FA") now, B logged as a separate backlog item.** Note the semantic hazard (R7): the backend pins below the band and returns `tier: null`; `ANCHOR_TIER['no_value'] = null` keeps the distinction in the type system even while the *display* borrows the `waivers` label | **BUILD** | A1. |
| **RL-8** | P1-7 C5 | Ship the visible progress hint (`anchor_count` / `anchor_required` + wizard copy)? | **Yes** — "an unlock bar the user cannot see is the exact shape of P0-1's failure." **Cleanly severable**: decline it and the correctness fix ships with **no API shape change at all** | **BUILD** | Whether A1 changes an API response shape, and therefore whether `docs/api-reference.md` gets that row. |
| **RL-9** | P1-7 C6 | Build the `anchors-done` seed profile so the unlock is provable on-device? `app_user.anchors` is already reserved in every profile JSON and implemented by nothing | **Yes** — "the audit found this class of bug precisely because no fixture reproduced it." Declining means the unlock is proved by pytest + a manual pass, and the Maestro waiver goes in the scope block | **BUILD** | A1's test scope and its Maestro waiver. |
| **RL-10** | P1-10 Ckpt C | Ship the optional Sleeper-Connect Maestro flow? It would close half of A-31, but costs 4 testIDs **and** a custom `headerLeft` — a header-chrome change that moves the sim gate from **tier 2 to tier 1** | **Out for this item; spin the flow off as its own ticket under A-31.** Bundling a header change into an instrumentation fix is the drive-by the coding guidelines forbid, and it triples the ship cost of an Effort-S item | **BUILD** | A2's sim-gate tier and testID set. |
| **RL-11** | P1-10 Ckpt E | Also rename `sleeperconnect.done` → `sleeper-connect.done`? Referenced by **zero** flows, so the rename is free | **Only if RL-10 is taken**, so the screen's ids land in one convention at once | release | A2. |
| **RL-12** | P1-11 CP-7 | Tier 1 or Tier 2 sim gate for P1-11? `TabNav.tsx` is navigation ⇒ Tier 1 by the matrix, but **no navigation behaviour changes** — two string literals in an `options` block | **Tier 2**, recorded as a deviation in the scope block per the matrix's own "deviations are decisions" rule. **Absent a call, the plan executes Tier 1** | release | Wave C's gate cost. |
| **RL-13** | P1-11 CP-8 *(merged with P1-1/2 capture delta and P1-5 R10)* | **How wide is the re-capture?** `screen-freshness.sh` flags 5 screens / 27 captures and **under-reports** — only 2 of 32 screens declare `TabNav.tsx` as a source, yet the tab bar renders in every tab-stack frame | **(a) Re-capture all tab-stack screens once, in the single R1 pass** ([§A.5](#screen-re-capture--the-consolidated-plan-one-pass-r1)); **(b) file the manifest gap as its own follow-up** — it will silently mis-report on the next nav change too | release | Step 5 (R1) scope. This is the round's largest single cost item. |

### E.5 Scope questions raised by reconciliation (not present in any single plan)

| ID | Question | Consequences of each option | Recommendation |
|---|---|---|---|
| **SQ-1** | **P1-7 collides with P1-8, which the operator EXCLUDED from this round.** Both edit the same unlock ladder at `backend/server.py:6163-6175`: P1-7 adds the `anchor` branch, P1-8 (A-17) would add an evidence requirement to the `manual` branch. `plan-p1-7.md:739-745` calls it "same function, adjacent lines, near-certain merge conflict" and P1-7 explicitly does **not** touch `manual`. **Does P1-7 absorb the ladder work, or does the round knowingly ship it half-done?** | **(a) P1-7 absorbs A-17.** One coherent pass over the ladder; `_tiers_rule` (P1-7 change 3) is already the shared seam P1-8 would want; branch order settles as `manual → tiers/quickset → anchor → else`. Cost: P1-7 grows past Effort S, needs A-17's own evidence-rule design (which is *not* specced in any plan here), and pulls an operator-excluded item back into scope. **(b) Ship P1-7 alone, knowingly half-done.** The anchor cohort unlocks; the manual cohort stays structurally locked. **The cross-item fact neither plan could see:** P0-1 adds `_note_ranking_method(sess, "manual")` to `reorder_rankings` (`plan-p0-1.md`, `server.py:7800` after `:7822`), so **after the P0 merge, a user whose first method-write is a manual reorder is pinned to `'manual'` and falls through to the trio rule — the exact structural lock P1-7 exists to remove for anchors.** P0-1 grows the anchor-locked cohort *and* creates a manual-locked one; excluding P1-8 fixes half of what P0-1 widens. **(c) Ship P1-7 and re-open P1-8 as an immediate fast-follow** on the seam P1-7 leaves. | **Not agent-decidable — operator call.** This HLD's obligation is to make the consequence visible: **option (b) means shipping P0-1 + P1-7 together while knowingly leaving a second cohort permanently locked by the same mechanism, in the same file, seven lines away.** If (b) is chosen, it should be recorded in `DECISIONS.md` as a knowing deferral with the `_tiers_rule` seam named, and A-17 raised to the top of `NEXT.md` — not left as an unremarked gap. |
| **SQ-2** | **P1-11's `_comment_draft_tab` edit (CP-4) touches the one string shared with A-20's excluded draft-tab half**, and A-33 (a separate P1) reconciles `_comment_draft_extensions` in the *same* `config/features.json` (`plan-p1-11.md:501`) | If both A-33 and P1-11 run this round, they edit adjacent comment keys in one file | Coordinate at build time, or defer CP-4 to whoever runs the draft-tab half. **Non-blocking.** |

---

## F. Risk register

Cross-item risks that no single plan could see. Silent-failure modes are marked **[SILENT]** —
these produce **no error, no log, and a 200 response**, which is what makes them the round's
defining hazard.

| ID | Risk | Severity | Why no single plan could see it | Mitigation / owner |
|---|---|---|---|---|
| **R-1** | **The "flag-gated" framing is wrong. FOUR P1 items ship user-visible change live on merge, not one.** Verified: **P1-1/2** (`growth.share_landing: true`, `config/features.json:125` — new share affordances, a new deep-link alias, a URL in every shared PNG); **P1-5** ("Feature flags: **None added**", `plan-p1-5.md:285` — a new card on League Home and a new action block on Matches, live); **P1-7** ("None added; none re-defaulted", `plan-p1-7.md:491` — an API **value domain** flips `unlocked: false→true` for a cohort, **and the push fan-out fires**); **P1-11** (presentation-only, but live). **P1-9 is the only item in the round with a real kill switch** (`notif.trade_found`, default OFF + `trade_found_dry_run=1`). **P1-3's flip *is* the deliverable.** **P1-10 is invisible** (analytics only) | **High** | Each plan correctly answered "do I add a flag?" — none asked "how many of us are shipping unguarded at once?" | Surface as a **release-plan fact**, not a per-item footnote. The round's rollback story is **`git revert`, not a flag flip**, for four of seven items. RL-1 is the only checkpoint that asks the operator to accept it, and it only covers P1-1/2. **Recommend the operator answer RL-1 for the whole round, not just for P1-1/2.** |
| **R-2** | **[SILENT] Taxonomy name-set drop.** Three P1 items write nine names and **modify two existing prop rows** in two frozensets. A three-way merge that resolves cleanly the wrong way keeps one name set and drops another. `analytics_ingest.py:379-383` returns **200** and `_health_bump("dropped_unknown_type")`s; `:384-389` strips unlisted props silently. **The repo has already done exactly this to `invite_shared`** — verified absent from `ALLOWED_CLIENT_EVENTS` at `ab9368f` while `InviteLeaguematesBanner.tsx:47` has been firing it since it shipped | **High** | Each item saw at most two of the five claimants | **Commit T1** ([§A.2](#a2-backendanalytics_taxonomypy--five-claimants-default-deny-and-silent)) — one commit, one owner, all nine names. Plus T1.6's **single exact-set** disjointness assertion, which fails loudly on a bad merge. |
| **R-3** | **[SILENT] Stripped props on a modified row.** Distinct from R-2 and subtler: the *name* survives, the *props* vanish. Two rows are modified — `invite_shared` (+4 props) and `trade_card_shared` (+`landing`, +`surface`). A merge that takes the pre-existing row keeps the event working and delivers **every row propless.** For P1-5 that means `surface` — the entire comparison the item exists to enable — is **permanently absent with no error** | **High** | Only P1-5 saw its own half (D3, `plan-p1-5.md:226`); nobody saw that P1-1/2 does the same thing to a second row | T1.2 makes both modifications explicit and adjacent. **Every acceptance test must assert prop survival, not merely acceptance** (T1.4, T1.5). `plan-p1-5.md:246` names this as "the assertion that would have caught D3". |
| **R-4** | **[SILENT] Dead deep-link alias.** AASA claims `/s/*` **wholesale** (`server.py:8094-8107`), so **every** `/s/…` shape needs a matching `rewriteUniversalPath` alias or it opens the app onto the fallback toast. P1-1/2 M3 adds the alias for `/s/tiers/…`. If that hunk is lost in a `deepLinks.ts` rebase — a file with **three** sequential writers (P0-3 → P1-1/2 → P1-9) — every tier share link opens the app to an error toast, and nothing fails in CI | **Medium-High** | Only P1-1/2 knew the AASA-claims-everything rule; only P1-9's collision table saw the three-way write | Manual test 13 (`plan-p1-1-2.md:477`) is the only check. Record the rule as a **convention** in `living-memory/LLD.md` (P1-1/2 docs table) so it binds every future `/s/…` route. **Re-grep, never edit `deepLinks.ts` by line.** |
| **R-5** | **[SILENT] Permanently-zero event.** P1-10 Ckpt A's Option 2 (`sleeper_connect_otp_step`) needs a MutationObserver against an **unverified** Sleeper DOM. It would ship an event that reads zero forever and is **indistinguishable from a real zero** without a live OTP-gated TestFlight session. Same class: P1-9's `dry_run_would_push` staying 0 because the gate genuinely never fires (R1 in `plan-p1-9.md:585`) | **High if built** | — | **AN-1** — recommend Option 1. And record the decision in `DECISIONS.md` so a later reader comparing to the ESPN twin does not "fix" it. For P1-9, the dry-run counters are designed so emptiness is **attributable** (`candidates == 0` vs `blocked_*`) rather than ambiguous. **Do not respond to a zero counter by weakening the gate.** |
| **R-6** | **[SILENT] Dead notification tap on web.** P1-9 adds a `trade_found` `notifications.type` read by three clients. Mobile has a `DEFAULT_ROW_GLYPH` fallback (`TopBar.tsx:73-76`); `web/js/app.js`'s notification-list renderer **is not verified to have one**, and **no item in this round edits `web/js/app.js`**. If the web branch switches on `type`, the row renders wrong or the tap does nothing — no error, no log | **Medium** | P1-9 flagged it as a build-time verification item; no other plan looks at web | Make it an explicit **blocking** build-time check in B2, not a note. Record the silent-failure mode in `docs/cross-client-invariants.md`. |
| **R-7** | **[SILENT] Two mount effects, one screen, double-counted taps.** P0-7 adds a `league_view` mount effect to `LeagueScreen.tsx`; P1-5 adds an `invite_cta_shown` mount effect to the same screen, which has `placeholderData: (prev) => prev` and multiple parallel queries and re-renders often. Separately, **if P0-7's OPTIONAL-A shipped and its `action` enum gained an `invite` value, one invite tap fires two events** and double-counts the product's most important growth action | **Medium** | P1-5 saw half (`plan-p1-5.md:404`, `:420`); P0-7 recorded `LeagueScreen.tsx` as "expected clean" | Single owner for the file in Wave B (**B1**). `firedRef` guard, fire only once the summary has settled **and** the card actually rendered. **Semantic rule carried into [§A.3](#a3-mobile-file-collisions--line-level): P0-7's `action` enum must not gain `invite`.** Verified by counting rows for one visit. |
| **R-8** | **Two unlock cohorts, one release window, one push fan-out each.** P0-1 unlocks the Quick Set cohort; P1-7 unlocks the anchor cohort. **Both** cross the `was_first` branch, so `ranking_complete_first_time` fires and `league_member_unlocked_trades` pushes to every joined leaguemate (`server.py:6228-6265`). Each plan raised it independently (P0-1 R2/Q5, P1-7 R2/C1) — **neither could see that they stack** | **Medium** | — | **RL-5.** Whatever is decided for P0-1 applies to P1-7. The two deploys must not stack unnoticed. |
| **R-9** | **DAU/WAU step-change at the seam.** Three distinct routes to it: `invite_cta_shown` landing INTENT (P1-5 R3, **High**); the three share events' unspecified membership (**AN-4**); `push_opened` firing for the first time ever (P1-9 R8). `INTENT_EVENTS` is a **deny-list** — silence means INTENT | **High** (for the impression event) | Each item reasoned about its own events | T1.3 makes `invite_cta_shown` NON_INTENT **mandatory**. AN-4 forces the P1-1/2 question before T1 freezes. Every seam date goes in the CHANGELOG and the addenda, so a later analyst sees the discontinuity rather than discovering it in a chart. |
| **R-10** | **No baseline for the invite funnel.** `invite_shared` has never landed a row (verified absent from the allowlist), so "promotion worked" has nothing to compare against. Any post-ship read is absolute, not a lift | **Medium** | — | State it plainly in the T1.8 addendum. **Do not let a dashboard imply a before/after that does not exist.** AN-8's A/B is the honest route to a comparison, and it is itself gated on `experiment_exposed` (P0-7 F1). |
| **R-11** | **Half a ladder.** See **SQ-1**. P0-1 pins manual-reorder users to `ranking_method='manual'`, which falls through to the trio rule; P1-8 (which would fix it) is excluded; P1-7 explicitly does not touch that branch. **The round may ship a fix for one structurally-locked cohort while creating and leaving a second, in the same function** | **Medium-High** | P1-7 saw P1-8's exclusion; it did not connect it to P0-1's `manual` write | Operator decision (**SQ-1**). If deferred, record it as a knowing deferral naming the `_tiers_rule` seam, and raise A-17 in `NEXT.md`. |
| **R-12** | **Nine claimants on `D-011`.** Every plan hard-codes or hedges a `living-memory` ID. Two agents writing `D-011` produces a duplicate-ID `DECISIONS.md` that the `living-memory-format-check` skill will flag *after* the fact | **Low, certain** | Each plan checked the file at authoring time | [§A.6](#a6-the-decisionsmd-id-collision-nine-claimants) — allocate at write time in merge order; **no agent uses the ID printed in its plan.** |
| **R-13** | **Stale plan prose becomes the next reader's truth (the A-33 class).** P0-1's plan quotes the RankScreen banner copy verbatim (`plan-p0-1.md:80-82`) — P1-11 edits that exact string. P0-7's conflict matrix says TabNav is uncontended — P1-11 contests it. P0-8/9 cites TabNav launch routing in prose. **Every one of these is a document that will be read as evidence later** | **Low, cumulative** | Structural to parallel planning | This document is the correction of record for the two P0-7 rows ([§A.1](#a1-corrections-to-p0-7s-conflict-matrix)). Where a P0 plan's *prose* goes stale (P0-1's quote, P0-8/9's citation), leave a one-line note at P1 ship rather than editing another branch's plan. |
| **R-14** | **Capture cost dominates a five-word change.** P1-11 is two string literals plus comments; its capture obligation is ~13 screens at 4–7 min each, because the tab bar renders in every tab-stack frame and `screens/manifest.json` **under-declares** `TabNav.tsx` as a source (2 of 32 screens) | **Medium (cost), Low (correctness)** | P1-11 found the manifest gap; the consolidation opportunity across six invalidators is only visible here | **R1** — one pass ([§A.5](#screen-re-capture--the-consolidated-plan-one-pass-r1)). File the manifest gap as its own follow-up (**RL-13b**) — left unfixed it mis-reports on the next nav change too. |
| **R-15** | **Concurrent sibling sessions mutate this worktree's premises.** Root `CLAUDE.md` warns multiple sessions run in this repo; the branch triage doc records 91 stale worktrees once breaking an EAS upload. `plan-p1-7.md:759` raises it for `tierBands.ts`; `plan-p1-9.md:600` raises it for `server.py` (20k+ lines) | **Medium** | Structural | Every wave **re-diffs before editing** ([§G](#g-re-verification-checklist)). Always branch from freshly-fetched `origin/main`. Any branch or worktree deletion goes through `docs/recovery/` **capture-then-delete**, verified by content against `origin/main` (this repo squash-merges, so ahead-counts are not evidence). |

---

## G. Re-verification checklist

**Run per item, immediately after the P0 merge and the rebase, before that item's first edit.**
Each row is a claim the plan asserts that P0 may have invalidated. Answer in writing in the item's
scope block. **A row that comes back "the premise no longer holds" stops that item's build and
returns it to planning** — it does not get patched around at the keyboard.

### G.0 — Applies to every item

1. `git fetch origin && git rev-parse origin/main` — record the sha in the scope block.
2. Confirm the P0 commits are present (P0-1, -2, -3, -5, -6, -7, -8/9).
3. Rebase the P1 branch; resolve nothing blind.
4. **Re-read `living-memory/DECISIONS.md`, `GOTCHAS.md`, `MISTAKES.md`, `OPEN_QUESTIONS.md` for the
   next free IDs.** Do **not** use the ID printed in your plan (R-12).
5. **Re-grep every file:line your plan cites.** `backend/server.py` and
   `mobile/src/screens/TradesScreen.tsx` in particular have moved.
6. Confirm `mobile/node_modules` is still symlinked. **Never run `npm install`.**

### G.1 — T1 (taxonomy)

- [ ] `ALLOWED_CLIENT_EVENTS` now contains P0-3 B4's four invite names **and** P0-7's eight client names. If any is missing, **the P0 merge dropped a name set** — stop and report (this is R-2 having already happened).
- [ ] `CLIENT_EVENT_PROPS` contains an `invite_shared` row. **P1-5 extends it; it must not be re-added.** Record the row's current contents verbatim before editing.
- [ ] `trade_card_shared`'s row is still `frozenset({"trade_id", "channel"})` (verified at `:222` at `ab9368f`). If P0 widened it, reconcile with P1-1/2 B2 rather than overwriting.
- [ ] `_assert_namespaces_disjoint` (`:298`, invoked `:322`) still passes; none of the nine new names appears in `SERVER_FIRED_EVENTS` (`:105-136`), `database._EVENT_TO_USER_COL`, or `_RANK_STREAK_EVENTS`.
- [ ] `NON_INTENT_EVENTS` (`analytics_queries.py:60-63`) — record its post-P0 contents (P0-7 adds `tab_selected`, `league_view`) before adding `invite_cta_shown`.
- [ ] **AN-1, AN-3, AN-4, AN-5 and PR-9 are answered** — they all determine T1's name list or a prop-row comment, and T1 freezes the file afterwards.
- [ ] `test_live_taxonomy_is_disjoint` — read P0-7's and P0-3's extensions before writing T1.6's single combined edit.

### G.2 — P1-7 (Wave A)

- [ ] `backend/server.py` unlock ladder — **re-locate it.** P0-1 comments `:6155-6175` and edits `save_anchor_route :7479`; the ladder is no longer at the line numbers in `plan-p1-7.md:401`.
- [ ] Confirm the `("tiers","quickset")` branch still has the shape `_tiers_rule` is being extracted from, and that P0-1's comment did not restructure it.
- [ ] Confirm `RankScreen.tsx:686` now carries `testID="rank.unlocked-banner"` (P0-1 edit #14) — the `p1-7-anchor-unlock.yaml` flow has a **hard dependency** on it (`plan-p1-7.md:571`).
- [ ] `backend/tests/fixtures/seed_ui_test_db.py` — P0-1 rewrote `_validate_quickset` (`:314-366`). Re-locate the `matches_seed` region and confirm the `app_user.anchors` key is still unhandled.
- [ ] `backend/experiments.py:59` — `ranking_method` is a live targeting attribute and **P0-1 changed which users hold which value.** P1-7 changes what `'anchor'` *means* at the gate. Confirm no experiment is mid-flight on that attribute.
- [ ] **Re-check the `manual` branch's post-P0 state** — P0-1 now writes `ranking_method='manual'` from `reorder_rankings`. This is the evidence for **SQ-1**; report what you find.

### G.3 — P1-10 (Wave A)

- [ ] `mobile/src/components/SendInSleeperButton.tsx` — **`goConnect` is not at `:114` any more.** P0-6 rewrote the gate (`:59-66`) and render tail (`:273`+); P0-7 inserted into `onPress` (`:231`) and the `:143` catch. Re-grep `goConnect`, then edit.
- [ ] `mobile/src/navigation/RootNav.tsx` — P0-5 edits `:297-301`, `:410`; P0-3 edits `:397-421`, `:341`. Re-locate the `SleeperConnect` param-list entry (`:58`) and the `navigate('SleeperConnect')` call (`:437`).
- [ ] `mobile/src/screens/SettingsScreen.tsx` — **P0-5 extracted the inline Sleeper form into `LinkSleeperSheet` (`:423-472`, `:1210-1236`)**, so `:488` and `:1261` have both moved. Re-grep `navigateFromSettings`.
- [ ] `mobile/src/screens/SleeperConnectScreen.tsx` — confirm still untouched by P0 (expected: sole owner). Re-confirm the `catch {` at `:96-97` is still bare (the plan requires it to take the error binding).
- [ ] Confirm the four names are in `ALLOWED_CLIENT_EVENTS` on `main` **and** that T1's live `POST /api/events` probe returned `dropped == 0`. **No `track()` before that.**

### G.4 — P1-1/2 (Wave A)

- [ ] `mobile/src/utils/deepLinks.ts` — P0-3 added `LeagueJoin` to `V2_SCREENS` (`:95-178`) and the `?league=` capture at `:344-354`. **Re-grep `rewriteUniversalPath`**; confirm the existing `/s/p/` and second branch still have the shape M3's third branch mirrors.
- [ ] `backend/server.py:8094-8107` — confirm AASA **still claims `/s/*` wholesale** after P0-3 B1 added `/app/league/join/*`. If P0-3 narrowed the claim, R-4 changes shape and M3's justification must be rewritten.
- [ ] `mobile/src/screens/TradesScreen.tsx` — if **PR-11** = include, re-locate `:2735-2751` and `:2760-2766`. P0-2 made ~18 edits and P0-8/9 four more; the file has moved substantially.
- [ ] `mobile/src/components/Toast.tsx` — P0-2 added `topOffset` (`:99-102`, `:143-151`). Confirm the action button at `:111-124` is still where M15's `testID` passthrough goes.
- [ ] `mobile/src/components/InLeagueCalculator.tsx:771` — P0-6 **and** P0-7 both edited this line. Read the merged mount before adding M8's props at `:781-798`.
- [ ] Confirm `growth.share_landing` is **still `true`** in `config/features.json` and in `backend/tests/fixtures/flags/release.json`. **RL-1's whole premise is that this ships live.**
- [ ] Confirm `docs/api-reference.md` rows `:544` / `:546` still exist at those lines — P0-1 and P0-3 both edited that file.

### G.5 — P1-5 (Wave B)

- [ ] **The load-bearing one.** `grep -n "buildInviteUrl" -A 8 mobile/src/components/InviteLeaguematesBanner.tsx` — confirm P0-3 M1's flag-resolved format is present **before writing a line** (`plan-p1-5.md:230`). Promoting a CTA that emits the old format would *scale the broken link* — the single worst outcome available in this item.
- [ ] Confirm `hld.md:491-493` held: **P0-3 M3 was removed**, so `LeagueScreen.tsx:373` was not touched by P0-3 and `buildInviteUrl` reads the flag imperatively.
- [ ] `mobile/src/screens/LeagueScreen.tsx` — record where P0-7's `league_view` mount effect landed. P1-5's `invite_cta_shown` effect goes **beside** it, not instead of it.
- [ ] **If P0-7's OPTIONAL-A shipped**, read its `action` enum. **It must not contain `invite`** (R-7). If it does, that is a double-count and must be resolved before B1 builds.
- [ ] Re-read `invite_shared`'s `CLIENT_EVENT_PROPS` row on `main` and confirm T1's extension landed — then prove it live: a `POST /api/events` carrying `surface` and `not_joined` that **echoes both back**.
- [ ] `mobile/src/screens/MatchesScreen.tsx` — P0-6 edited `:616-623`. Re-locate `:387-397` and `:548-552`.
- [ ] Confirm `growth.invite_join_link`'s current state. **Either state is safe** (D5, `plan-p1-5.md:228`) — but record which one, because it determines which URL format the promoted CTAs actually emit on ship day.

### G.6 — P1-9 (Wave B)

- [ ] `backend/server.py` — re-locate `_send_typed_push` (`:15393`), `_NOTIF_FREQ_CAPS` (`:15212`), `_NOTIF_DEDUP_CAPS` (`:15230`), `_inject_likes_you_cards_impl` (`:2813-2936`), `cron_daily_tick` (`:16060+`). P0 edited six other functions in this file, **and P1-7 edited the unlock ladder in Wave A.**
- [ ] Confirm `server.py:6218-6255` (the first-unlock fan-out) is **P0-1's and P1-7's**, and that P1-9 adds nothing to it (`plan-p1-9.md:603`).
- [ ] `mobile/src/utils/deepLinks.ts` — **two** writers have moved this file (P0-3, then P1-1/2 in Wave A). Re-grep `V2_TRADE_KINDS`; do not edit `:262` by line.
- [ ] `mobile/src/screens/SettingsScreen.tsx` — **three** writers have moved it (P0-5's extraction, then P1-10 in Wave A). Re-grep the notification bucket rows and the `Row` helper.
- [ ] `backend/tests/fixtures/seed_ui_test_db.py` — P0-1 and P1-7 both edited it. **Re-run the seeder end to end** rather than trusting a clean merge (`plan-p1-9.md:608`).
- [ ] `backend/feature_flags.py` `notif.*` block and `config/features.json` `notif.*` keys — confirm positions after P0-3 B5/B6 added `growth.invite_join_link`.
- [ ] Confirm `push_opened` is still registered at `analytics_taxonomy.py:68` with `dedup_key` in its prop row (`:213`) — **verified true at `ab9368f`**, so change #12's payload addition needs no taxonomy edit. If P0-7 changed the row, re-check.
- [ ] **Verify `web/js/app.js`'s notification-list renderer** — does it switch on `type`, and does it have a fallback? This is R-6 and it is a **blocking** build-time check, not a note.

### G.7 — P1-11 (Wave C)

- [ ] `mobile/src/navigation/TabNav.tsx` — read the merged `<Tab.Screen name="Trades">` element **in full** before editing. At `ab9368f` it spans `:647-683` with the comment at `:650-652`, `options` at `:653-658` and `listeners` at `:659-682`. **P0-7 inserted `track('tab_selected', …)` into that `tabPress`.** Re-locate `tabBarLabel` and `tabBarAccessibilityLabel` by content.
- [ ] `mobile/src/screens/RankScreen.tsx` — read `:685-696` merged. **P0-1 added `testID="rank.unlocked-banner"` at `:686`**, seven lines above the two copy strings at `:693-694`. One hunk. Re-locate by content.
- [ ] `mobile/src/screens/MatchesScreen.tsx:660` — **two** writers moved it (P0-6 at `:616-623`, P1-5 in Wave B). Re-grep the copy string.
- [ ] Re-run the headline grep and confirm it still holds: `grep -rn "Acquire" mobile/.maestro/ | grep -v "#"` → **0 hits**. If P0 added a text assertion on the label, the "no flow breaks" claim is void.
- [ ] `mobile/src/navigation/RootNav.tsx:71`, `testRouteEntry.ts:11/:74` — P0-3 M12 and P0-5 both touched these files. Re-locate the comments.
- [ ] `backend/feature_flags.py:532/:536` — P1-9 (Wave B) added a key to this file. Re-locate.
- [ ] Confirm `TradeFinderHubScreen.tsx` still exists and is still unrouted (CP-3 / A-27).
- [ ] Re-check the three per-folder `CLAUDE.md` registries — P0-1, P0-5, P0-6, P1-7, P1-9 and P1-1/2 all register testIDs in them.

### G.8 — P1-3 (independent lane)

- [ ] **Gate 0's probe result is recorded**, or the operator has knowingly chosen Option B.
- [ ] `config/features.json:58` — confirm `auth.email_capture` is still `false` and still at that key. **P1-9 (Wave B) and P1-11 (Wave C) both edited this file**; re-locate.
- [ ] `backend/feature_flags.py:138-141` — re-locate the comment block; three other items edited this file.
- [ ] `web/privacy.html` — confirm `:90-99`, `:172`, `:198-208`, `:210-226` still carry the sentences the change list retires, and that the header TODO at `:1-8` is unchanged.
- [ ] **If Gate 4 = Option B:** `backend/server.py:18005-18075` — **P0-5 restructured `_provider_auth_response` / `_mint_account_only_session`.** Re-read the whole function; the event must fire **after** the users row exists, and `record_event` writes denorm columns on `users`. And the `email_captured` registration **must go into T1**, which by then is merged — meaning a **T1 amendment commit with the same deploy-and-verify gate**, not a drive-by edit.
- [ ] Confirm `fleaflicker.link` is still `false` — turning it on makes `web/privacy.html:172` false a *second* way via `PlatformLinkSheet.tsx:147-157`. Fix both in the same §2 rewrite while the file is open.

---

## Appendix — what this document deliberately does not do

- **It does not resolve any product, privacy, or copy question.** Every such call is in
  [§E](#e-consolidated-operator-decision-list) with the owning item, the plan's recommendation, and
  what is blocked. Where two plans genuinely disagree on design, both are presented
  (**SQ-1**, and **AN-3**'s `invite_shared` vs `invite_sent` fork).
- **It does not invent new design.** The only additions to the seven plans' content are: the
  composition of commit T1 (assembled from three plans' change lists, not authored), the wave
  partition, and **AN-4** — a *gap* in P1-1/2 (unspecified INTENT membership for three new events),
  surfaced as a question rather than answered.
- **It does not edit any source file.** Plan-only, per the standing instruction.
- **It does not re-litigate P1-3's or P1-9's recommendations.** They are aggregated into
  [§E](#e-consolidated-operator-decision-list) as their authors wrote them, with the build-blocking
  ones named.
