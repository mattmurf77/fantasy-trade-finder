# P1-11 — "Acquire" → "Trades": presentation-only vocabulary correction

> Audit item **A-20 (partial — the naming half ONLY)**. Type Polish, effort S.
> The draft-tab seasonal toggle that shares A-20's row is **excluded by operator decision**
> and is neither planned nor designed for here. See [Risks and cross-item collisions](#risks-and-cross-item-collisions).

**Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`
**Branch:** `p1-remediation-2026-08-11` @ `ab9368f` (== `origin/main` at plan time)
**Date:** 2026-08-11
**Sources:** `docs/business/product/2026-08-09-mobile-ux-audit/06-resolutions.md` row A-20;
`04-priority-backlog.md`. Root `CLAUDE.md` §Conventions (feature gates, bright lines);
`docs/CLAUDE.md` (doc triggers).

## Contents

- [Verified current state](#verified-current-state)
- [Design](#design)
- [Exact change list](#exact-change-list)
- [Surface changes](#surface-changes)
- [Maestro delta](#maestro-delta)
- [Docs impact table](#docs-impact-table)
- [Test plan](#test-plan)
- [Risks and cross-item collisions](#risks-and-cross-item-collisions)
- [Operator checkpoints](#operator-checkpoints)

---

## Verified current state

Every citation below was re-read in this worktree at `ab9368f`. **The audit's claim holds
and is more precise than the audit stated**: the rename is genuinely presentation-only,
and it is *documented as such in the code that performs it*.

### Provenance — this is a deliberate decision being reversed, not a defect being fixed

"Acquire" is not accidental vocabulary. It shipped as feedback item **#245** on 2026-08-05
(`docs/feedback/items/245-acquire-tab/status.md`), on an explicit operator ask:
*"rebrand the Trades tab as Acquire"*. The stated rationale was that the tab covers **both**
acquisition channels — trades and free agency — because #245 also restructured the hub into
`TRADE` and `FREE AGENCY` sections.

**That rationale has since been undercut by the codebase itself.** Feedback **#246**
(same day) superseded the #245 hub: `TradeFinderHubScreen` is now **unrouted**
(`mobile/src/navigation/TabNav.tsx:36`, `:400`; `mobile/src/screens/CLAUDE.md:18`), the
guided deck is the landing, and Free Agents is a chip in the mode bar plus a row on the
League tab. The two-channel argument that justified "Acquire" no longer has a surface
carrying it. This is material and belongs in front of the operator —
see [Operator checkpoints](#operator-checkpoints) CP-1.

### The label is already internally inconsistent

`mobile/src/screens/MatchesScreen.tsx` contradicts itself inside a single empty state:

| Line | String |
|---|---|
| `:660` | `Swipe more in the Acquire tab.` |
| `:667` | `label="Go to Trades"` (the button directly beneath it) |

And at `:546` the mutual-match empty state's primary button reads `"Find a trade"`.
The web client's main nav already reads **`Find Trades`** (`web/index.html:246`). The
product only says "Acquire" in five places; it says "trade(s)" everywhere else.

### Complete occurrence table

Sweep method: `grep -rni "acquire"` across `mobile/src`, `web/`, `extension/`
(`.tsx .ts .html .js .css`) → **117 raw hits**. `extension/` → **0 hits**, so that client is
out of scope entirely. Every hit is classified below; nothing is omitted.

#### Group 1 — the tab's NAME, user-visible (IN SCOPE — 5 live + 1 dead)

| file:line | current string | user-visible? | proposed |
|---|---|---|---|
| `mobile/src/navigation/TabNav.tsx:655` | `tabBarLabel: 'Acquire',` | **YES** — bottom tab bar | `tabBarLabel: 'Trades',` |
| `mobile/src/navigation/TabNav.tsx:656` | `tabBarAccessibilityLabel: 'Acquire',` | **YES** — VoiceOver | `tabBarAccessibilityLabel: 'Trades',` |
| `mobile/src/screens/MatchesScreen.tsx:660` | `Swipe more in the Acquire tab.` | **YES** — awaiting-them empty state | `Swipe more in the Trades tab.` |
| `mobile/src/screens/RankScreen.tsx:693` | `'Your board now prices your trades — see the Acquire tab'` | **YES** — unlock banner (flag `ux.outlook_inline_default` = true) | `…— see the Trades tab` |
| `mobile/src/screens/RankScreen.tsx:694` | `'Trade Finder unlocked — check the Acquire tab'` | **YES** — unlock banner (flag off arm) | `…— check the Trades tab` |
| `mobile/src/screens/TradeFinderHubScreen.tsx:487` | page title `Acquire` | **NO** — screen is UNROUTED since #246; no navigator registers it | `Trades` (see CP-3) |

That is the **entire** user-visible tab-name surface. There is no sixth live string.

#### Group 2 — "acquire" as a trade DIRECTION, user-visible, DIFFERENT MEANING (OUT OF SCOPE)

These are the antonym of "trade away" in the FB-47 target picker and the positional-preference
sheet. They are not the product's core verb and **must not be renamed** — `Trade away / Trades`
is not a coherent toggle. Listed for completeness so the sweep is provably complete:

| file:line | current string | note |
|---|---|---|
| `mobile/src/screens/TradesScreen.tsx:3969` | `['acquire', 'Acquire'],` | direction-toggle pill label, paired with `['trade_away', 'Trade away']` at `:3968` |
| `mobile/src/screens/TradesScreen.tsx:5174` | `'Target players to acquire'` | picker modal title |
| `mobile/src/screens/TradesScreen.tsx:4020` | `` `Remove ${p.name} from acquire targets` `` | a11y label |
| `mobile/src/components/TradeDnaSheet.tsx:792` | `` `Remove ${p.name} from acquire targets` `` | a11y label |
| `mobile/src/components/OutlookSheet.tsx:131` | `Positions you want to acquire` | section header |
| `mobile/src/components/OutlookSheet.tsx:140` | `` accessibilityLabel={`Acquire ${p}`} `` | a11y label |
| `web/index.html:626` | `>Acquire</button>` | web direction toggle (`setPickerDirection('receive')`) |
| `web/js/app.js:3037` | `'Select players to acquire'` | web picker hint |
| `web/js/app.js:3283` | `` `Pinned ${n} player(s) to acquire` `` | debug log drawer, not chrome |

`docs/design/components.md:69` specs this toggle by name ("two `Trade away` / `Acquire` chips").
Unchanged — see the [Docs impact table](#docs-impact-table).

#### Group 3 — internal identifiers (NEVER TOUCH)

Not user-visible, not renamed. Categories, with representative sites:

| Kind | Count | Examples |
|---|---|---|
| `acquire_positions` / `currentAcquirePositions` API + state keys | ~14 | `mobile/src/api/league.ts`, `web/js/app.js:4403,4419,4443,4544` |
| `'trade_away' \| 'acquire'` union type / discriminant | ~16 | `TradesScreen.tsx:1010,1943,3363,3897,3924,4018,4176,4203,5185`; `TradeDnaSheet.tsx:166,167,793,811` |
| `acquire:` payload field on the DNA save shape | ~10 | `TradeDnaSheet.tsx:362,380,418,431,461`; `TradeFinderHubScreen.tsx:338,357,395,415,445` |
| `data-side="acquire"` DOM attributes | 5 | `web/index.html:975,978,981,984,987` |
| unrelated English (`acquired` mutex flag) | 4 | `mobile/src/state/useSession.ts:315,323,329,333` |

#### Group 4 — code comments naming the TAB (update per the A-33 discipline)

CLAUDE.md's A-33 lesson is explicit: *"when an operator override flips a constant, the comment
above it is part of the change."* Comments that name the tab go stale the moment the label moves.

| file:line | why it names the tab |
|---|---|
| `mobile/src/navigation/TabNav.tsx:396` | "#246 — guided-first Acquire landing" |
| `mobile/src/navigation/TabNav.tsx:488` | "#245/#246's Acquire semantics" |
| `mobile/src/navigation/TabNav.tsx:580` | "#245/#246's Acquire semantics" |
| `mobile/src/navigation/TabNav.tsx:650` | "#245 — presentation-level rename: the tab reads \"Acquire\"" — **the comment that must be rewritten, not deleted** |
| `mobile/src/navigation/TabNav.tsx:685` | "(Rank · Acquire · Draft · Matches · League)" |
| `mobile/src/navigation/RootNav.tsx:71` | "(placement wave) the Acquire" |
| `mobile/src/utils/testRouteEntry.ts:11` | "the Acquire subnav is hidden while `trades.finder_hub`" |
| `mobile/src/utils/testRouteEntry.ts:74` | "// Trades (tab label \"Acquire\") stack" |
| `mobile/src/screens/PickAssignmentScreen.tsx:873` | "the same manager-sheet construction the Acquire…" |
| `mobile/src/screens/DraftRoomScreen.tsx:158` | "the Acquire chip" |
| `mobile/src/screens/TradeFinderHubScreen.tsx:497` | "\"Acquire\" rather than \"Find a Trade\"" |
| `backend/feature_flags.py:532,536` | "(third: Rank · Acquire…)" and "the Acquire mode strip's Draft chip" |
| `mobile/.maestro/capture/*.yaml` — **12 files** | header-comment prose only, listed in [Maestro delta](#maestro-delta) |

**Do NOT rewrite** — these cite a real file path, `mockups/polish-lab-2026-08/acquire-landing-guided-first.html`
(verified present on disk):
`mobile/src/navigation/TabNav.tsx:397`, `mobile/src/components/TradeFinderModeBar.tsx:8`,
`mobile/src/components/TradeDnaSheet.tsx:45`. The mockup file itself is a dated historical
artifact and is not renamed.

#### Group 5 — config-comment prose (informational, 4 JSON files)

`config/features.json:170` and its three test fixtures
(`backend/tests/fixtures/flags/release.json:170`, `onboarding-v2.json:165`, `profiles-on.json:165`)
carry `_comment_draft_tab`, whose prose reads *"(third: Rank / Acquire / Draft / Matches / League)"*.
Purely descriptive; no code parses it. Treated in CP-4.

### Nothing is load-bearing beyond presentation — proof

| Mechanism | Keys off | Evidence |
|---|---|---|
| Route name | `'Trades'` (string literal, unchanged) | `TabNav.tsx:648` `name="Trades"` |
| Deep links | route table `Trades: 'trades'` | `mobile/src/utils/deepLinks.ts:290`, `:152`, `:198` |
| testIDs | `tabBarButtonTestID: 'tab.trades'` | `TabNav.tsx:657` |
| Scroll-to-top bus | `requestScrollToTop('Trades')` | `TabNav.tsx:672` |
| Test-route harness | `TAB_NAMES = new Set(['Rank','Trades',…])` | `mobile/src/utils/testRouteEntry.ts:84` |
| Analytics (`screen_viewed`) | route names | `testRouteEntry.ts:74-78` mapping |
| Analytics (`tab_selected`, incoming from P0-7) | `tab ∈ rank\|trades\|draft\|matches\|league` | P0-7 plan `:164` — route-derived, not label-derived |
| Backend | nothing | `grep -rni acquire backend/*.py` → only two prose comments in `feature_flags.py` |

Every one of these reads a **route name or a testID**, never `tabBarLabel`. The label is a
leaf. **Confirmed: nothing is load-bearing beyond presentation.**

---

## Design

**One decision: what replaces "Acquire".** Recommendation — **`Trades`**.

| Candidate | For | Against |
|---|---|---|
| **`Trades`** ✅ | Matches the route name, the deep-link path (`app/trades/…`), the testID (`tab.trades`), the web nav ("Find Trades"), the Matches button ("Go to Trades"), the domain vocabulary ("Trade Finder", "Trade DNA", "trade card"), competitors, and App Store search. Removes the `Acquire tab` / `Go to Trades` contradiction on one screen. Shorter (6 chars vs 7) → zero tab-bar layout risk. | Loses #245's two-channel framing — already moot post-#246. |
| `Trade` | Verb-ish, marginally shorter | Every sibling tab label is a noun (Rank is the exception and is itself a verb); inconsistent with the plural route |
| `Find` | Emphasises the action | Vague; "find what?"; no search-term value |

**Scope discipline.** Group 2 stays untouched. The direction toggle's "Acquire" is the
antonym of "Trade away" in a two-way control; renaming it produces `Trade away / Trades`,
which is meaningless. **Vocabulary consistency for the tab's *name* is the fix; the
directional verb is a separate, coherent word that happens to share spelling.** This is the
one place the brief's "a partial rename is worse than none" rule must be read as scoped to
Group 1 — and it is called out for the operator at CP-2.

**No flag.** The change is 5 string literals with no behavioural branch. A flag would add a
second code path, a config key, a `FLAG_KEYS` entry and a graduation criterion to guard a
word. Reversal is a one-line revert. The audit labels A-20 an "A/B candidate", but
`06-resolutions.md` itself records that production is 16 users and that **below ~400
completions per arm an A/B is a directional read, not a decision** — so a tab-label split
cannot be powered. Ship the better-reasoned arm; compare pre/post on `tab_selected`
(which P0-7 delivers). Escalated as CP-5 because the audit's own label says otherwise.

---

## Exact change list

Ordered. All paths relative to the worktree root. **This plan writes no code** — the list is
the build agent's instruction set.

### A. The label (2 edits, 1 file)

1. `mobile/src/navigation/TabNav.tsx:655` — `tabBarLabel: 'Acquire'` → `tabBarLabel: 'Trades'`
2. `mobile/src/navigation/TabNav.tsx:656` — `tabBarAccessibilityLabel: 'Acquire'` → `'Trades'`

### B. Copy that names the tab (3 edits, 2 files)

3. `mobile/src/screens/MatchesScreen.tsx:660` — `Swipe more in the Acquire tab.` → `Swipe more in the Trades tab.`
4. `mobile/src/screens/RankScreen.tsx:693` — `…— see the Acquire tab` → `…— see the Trades tab`
5. `mobile/src/screens/RankScreen.tsx:694` — `…— check the Acquire tab` → `…— check the Trades tab`

> **Merge order:** edits 4–5 sit inside the `unlockedBanner` `View` that **P0-1 edit #14**
> also modifies (`RankScreen.tsx:686`). P0 merges first; rebase before touching this hunk.

### C. Dead code (1 edit, 1 file) — see CP-3

6. `mobile/src/screens/TradeFinderHubScreen.tsx:487` — page title `Acquire` → `Trades`; update the
   `:484-485` and `:495-497` comments so they no longer assert a page title that is gone.
   *(Screen is unrouted; A-27 proposes deleting the file entirely at P2. Changing one word now
   costs nothing and prevents exactly the A-33 failure mode — stale text a later reader trusts.)*

### D. Comments that name the tab (11 edits, 7 files)

7. `mobile/src/navigation/TabNav.tsx:650-652` — **rewrite, do not delete.** Must still record that
   the label is presentation-only over route `Trades`, and now also that #245's "Acquire" was
   reverted by P1-11 on 2026-08-11 and why (#246 removed the two-channel hub). The provenance
   is the point.
8. `mobile/src/navigation/TabNav.tsx:396` · 9. `:488` · 10. `:580` · 11. `:685`
12. `mobile/src/navigation/RootNav.tsx:71`
13. `mobile/src/utils/testRouteEntry.ts:11` · 14. `:74`
15. `mobile/src/screens/PickAssignmentScreen.tsx:873`
16. `mobile/src/screens/DraftRoomScreen.tsx:158`
17. `backend/feature_flags.py:532` · 18. `:536`

**Explicitly NOT changed:** `TabNav.tsx:397`, `TradeFinderModeBar.tsx:8`, `TradeDnaSheet.tsx:45`
— real mockup file path.

### E. Per-folder CLAUDE.md registries (4 edits, 3 files)

19. `mobile/src/navigation/CLAUDE.md:6` — tab list `Rank · Acquire · Draft · Matches · League` → `Rank · Trades · …`; the parenthetical "the Acquire tab's route name stays `Trades`" becomes "the tab label and route name are both `Trades`".
20. `mobile/src/navigation/CLAUDE.md:8` — `**Acquire** (route `Trades`)` → `**Trades** (route `Trades`)`
21. `mobile/src/screens/CLAUDE.md:19` — "also the Acquire tab's landing" → "the Trades tab's landing"
22. `mobile/src/components/CLAUDE.md:51` — "Acquire tab's mode chip strip" → "Trades tab's mode chip strip"

### F. Reference docs

23. `docs/glossary.md:120` — retitle the **Acquire tab** entry to **Trades tab**, keep the #245/#246
    history in the body (do not erase it), append the P1-11 reversal + rationale, and keep the
    "route name stays `Trades`" invariant. Re-sort if the file is alphabetical; update any TOC.
24. `living-memory/DECISIONS.md` — new entry (next free ID; **verify at build time**, `D-011` per
    root CLAUDE.md) recording the reversal of #245's naming and the #246 rationale collapse.

### G. Maestro + captures

25. `mobile/.maestro/capture/*.yaml` — header-comment prose only, 12 files (§[Maestro delta](#maestro-delta)).
26. `mobile/.maestro/04-tabs-navigation.yaml` — one added label assertion (§[Maestro delta](#maestro-delta), subject to CP-6).
27. Screen re-capture (§[Test plan](#test-plan)).

**No changes to:** `extension/` (0 hits), `web/` (its nav already reads "Find Trades"; its only
"Acquire" is the Group-2 direction toggle), any backend route, `config/features.json` values,
any `.json` flag fixture.

---

## Surface changes

**Every category is `none`.** Proof per category, not assertion.

| Surface | Change | Proof |
|---|---|---|
| **Routes (navigation)** | **none** | `Tab.Screen name="Trades"` (`TabNav.tsx:648`) is untouched. `TAB_NAMES` (`testRouteEntry.ts:84`) and the `ROUTE_TO_TAB` map (`:74-78`) untouched. |
| **Routes (HTTP/API)** | **none** | No file under `backend/` changes except two prose comments in `feature_flags.py`. `docs/api-reference.md` unaffected. |
| **Deep links** | **none** | `deepLinks.ts` is not in the change list. `Trades: 'trades'` (`:290`), `path: 'trades'` (`:152`), `app/trades` share landing (`:198`) all read the route name. |
| **Schema** | **none** | No `backend/database.py` change; no table, column, or migration. |
| **Feature flags** | **none** | No key added, removed, or default-flipped. `config/features.json` values byte-identical (CP-4 concerns a comment string only). No `FLAG_KEYS` entry. |
| **Analytics events** | **none** | No event name, no property name, no property *value* changes. `screen_viewed` and P0-7's `tab_selected` both derive from route names (P0-7 plan `:164`: `tab ∈ rank\|trades\|draft\|matches\|league`), which are unchanged. No taxonomy allowlist edit. |
| **testIDs** | **none** | `tab.trades` unchanged; no id added or renamed; `testid-lint.sh` surface unchanged. |
| **Env vars / `model_config`** | **none** | Not touched. |
| **Cross-client invariants** | **none** | `grep -i "acquire\|tabBar" docs/cross-client-invariants.md` → 0 hits. Tab labels are not a shared constant. |

**Bright-line statement (root CLAUDE.md §Conventions).** This change touches **no** schema,
**no** API contract, **no** feature-flag surface, and **no** analytics event. It is not on the
bright line, and it is therefore eligible for the express lane **if the operator declares it**.
This agent does not self-select express — full gates are planned by default.

---

## Maestro delta

### Flows asserting the old label: **ZERO**

Verified exhaustively, and this is the headline result:

```
grep -rn "Acquire" mobile/.maestro/            → 12 hits, ALL inside # comments
grep -rn "Acquire" mobile/.maestro/ | grep -v "#" → 0 hits
grep -rn "text:.*[Tt]rade"  mobile/.maestro/   → 1 hit, unrelated
    (capture/trades@single-format.yaml:99 → "Set up SF TEP to trade here")
```

Every tab interaction in the harness uses `tabBarButtonTestID` selectors — `id: "tab.trades"`,
`id: "tab.rank"`, `id: "tab.matches"`, `id: "tab.league"`, `id: "tab.draft"` — across
`01`–`06` smoke, `flows/s1-spike-part-b-tabs.yaml`, and 51 capture flows. The harness moved to
testID selectors on 2026-07-12 (QA F-2, noted in `04-tabs-navigation.yaml:5-6`), which is
precisely why this rename is free.

**Consequence: no flow breaks. No flow requires a fix to stay green.**

### Comment-only edits — 12 capture flows (no assertion touched)

| File | Line | Comment prose |
|---|---|---|
| `mobile/.maestro/capture/trios@near-unlock.yaml` | 36 | quotes the RankScreen banner copy (edit 5) — **must** be updated or it misquotes the fixture |
| `mobile/.maestro/capture/trades@single-format.yaml` | 43, 49 | "never on Acquire" / "`near-unlock`'s Acquire" |
| `mobile/.maestro/capture/trades@fresh.yaml` | 19 | "the resting Acquire landing" |
| `mobile/.maestro/capture/onboarding-tour@fresh.yaml` | 131 | "lands the first run on Acquire" |
| `mobile/.maestro/capture/portfolio.yaml` | 21 | "the Acquire subnav's Portfolio pill" |
| `mobile/.maestro/capture/portfolio@two-leagues.yaml` | 10 | "the Acquire subnav's" |
| `mobile/.maestro/capture/anchors.yaml` | 11 | "(Acquire tab is never visited)" |
| `mobile/.maestro/capture/trios.yaml` | 11 | "that sheet belongs to the Acquire tab" |
| `mobile/.maestro/capture/trends.yaml` | 11 | "(Acquire tab is never visited)" |
| `mobile/.maestro/capture/manual-ranks.yaml` | 11 | "(Acquire tab is never visited)" |
| `mobile/.maestro/capture/quick-set.yaml` | 12 | "(Acquire tab is never visited)" |
| `mobile/.maestro/capture/tiers.yaml` | 11 | "an Acquire-tab" |

`trios@near-unlock.yaml:36` is the one that matters — it reproduces the exact banner string
being changed by edit 5, so leaving it stale reintroduces the A-33 failure mode in the QA layer.

### New coverage — the gate obligation

Root CLAUDE.md requires *"every user-visible mobile change ships a new/extended flow in
`mobile/.maestro/` (or a written waiver)."* Nothing breaks, but nothing **guards** the label
either — a future silent rename would pass the full suite.

**Proposal:** extend `mobile/.maestro/04-tabs-navigation.yaml` (already the tab-bar smoke flow,
already waits on `tab.trades`) with one assertion after its existing
`extendedWaitUntil: visible: id: "tab.trades"` at `:13-17`:

```yaml
# P1-11 — the tab label is presentation-only over route 'Trades'; nothing
# else in the harness asserts it, so a silent rename would pass every flow.
- assertVisible:
    id: "tab.trades"
    text: "Trades"
```

**Honest caveat, escalated as CP-6.** Maestro's combined `id` + `text` matcher must match a
single element; `tabBarButtonTestID` lands on the pressable while the label is a `Text`
descendant, so the combined matcher may not resolve. A bare `text: "Trades"` is **not** an
acceptable fallback — `04`'s frames also contain "Go to Trades" and other trade copy, so it
would pass spuriously and assert nothing. If the combined matcher does not resolve on a real
run, the correct outcome is to **drop the assertion and rely on the screen library** (the tab
bar is in every tab-stack capture frame, so the PNG diff *is* the regression evidence) and
record that as a written waiver in the scope block. Do not ship a matcher that cannot fail.

---

## Docs impact table

Row per `docs/CLAUDE.md` / `docs/templates/feature-scope.md` §4 trigger. Every row answered.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/glossary.md` | **YES** | `:120` — the **Acquire tab** entry is the canonical definition of this exact term. Retitle to **Trades tab**; preserve the #245/#246 history; append the P1-11 reversal; keep the "route name stays `Trades`" invariant. **This is the load-bearing doc edit.** |
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. Zero backend route files touched. |
| `living-memory/LLD.md` | **n/a** | No schema/route/invariant *convention* shifts. The "label is presentation-only over the route name" convention is **reaffirmed**, not changed. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **n/a** | Verified 0 hits for `acquire`/`tabBar`. Tab labels are not a shared cross-client constant (mobile says one thing, web already says "Find Trades"). |
| `docs/config-reference.md` | **n/a** | No env var, no `config/features.json` key, no `model_config` key. (CP-4 concerns a JSON *comment* only.) |
| `docs/data-dictionary.md` | **n/a** | No `backend/database.py` schema change. |
| `docs/design/design-system.md` | **n/a** | No token, color, radius, or type change. |
| `docs/design/components.md` | **n/a** | `:69` documents the Group-2 direction toggle (`Trade away` / `Acquire` chips), which is **out of scope and unchanged**. Verified the file contains no tab-bar label spec. |
| `docs/runbook.md` | **n/a** | No new operational failure mode. |
| ADR | **n/a** | Not architectural — it is a copy decision. |
| `living-memory/DECISIONS.md` | **YES** | New entry (next free ID; **verify at build time**): reverting #245's naming, with the #246 rationale collapse as the reason. Required by root CLAUDE.md — this is a non-obvious choice that reverses a prior operator decision. |
| `living-memory/CHANGELOG.md` | **YES at ship** | Dated H2 on merge. |
| `living-memory/TEST_LEDGER.md` | **YES at ship** | Sim-gate evidence (see [Test plan](#test-plan)). |
| `mobile/src/navigation/CLAUDE.md` | **YES** | `:6`, `:8` — the tab-label registry. |
| `mobile/src/screens/CLAUDE.md` | **YES** | `:19` — `TradesScreen` row. |
| `mobile/src/components/CLAUDE.md` | **YES** | `:51` — `TradeFinderModeBar` row. No testID added or renamed, so the testID registry tranche is unchanged. |
| `docs/feedback/items/245-acquire-tab/status.md` | **NO — deliberately** | Historical record of what shipped on 2026-08-05. Amending it would falsify the archive. The reversal is recorded in DECISIONS.md and the glossary, which are the live surfaces. |

---

## Test plan

### Static

1. `cd mobile && npx tsc --noEmit` — clean. (Expected trivially: only string literals change.)
2. `mobile/scripts/testid-lint.sh` — passes; no testID added, renamed, or removed.
3. Residual sweep, must return **only** Group 2 + Group 3 + the mockup path:
   ```
   grep -rni "acquire" mobile/src web extension --include=*.tsx --include=*.ts \
     --include=*.html --include=*.js --include=*.css
   grep -rn "Acquire tab" . --exclude-dir=node_modules --exclude-dir=.git
   ```
   The second command must return **zero** hits outside `docs/feedback/items/245-acquire-tab/`
   and the DECISIONS/glossary history text. This is the completeness gate.
4. `python -m pytest backend/tests` — unaffected (comment-only backend edits), run for CI parity.

### Simulator — Tier 1

`docs/runbook.md` §Pre-ship simulator gate: *"Mobile screen / navigation / state change"* → **Tier 1**
= full smoke suite (11 flows) + the feature's own flow + `screen-capture.sh --screen <touched>`
for every screen whose visuals changed.

This edits `TabNav.tsx` — navigation — so Tier 1 applies on the letter of the matrix even though
the blast radius is five words. Argued down to Tier 2 at **CP-7**; absent an operator call, plan Tier 1.

5. Full smoke suite: `01`–`06` plus the rest of the 11.
6. `mobile/.maestro/04-tabs-navigation.yaml` with the new assertion (or the CP-6 waiver).
7. Manual: bottom bar reads **Trades** in every state (4-tab and 5-tab with `draft.tab` on — verify
   5 labels still fit without truncation; "Trades" is shorter than "Acquire" so this should be
   strictly better, but confirm).
8. Manual: VoiceOver announces "Trades" on the tab.
9. Manual: Matches → awaiting-them empty state reads "Swipe more in the Trades tab." above a
   "Go to Trades" button — the contradiction is gone.
10. Manual: Rank unlock banner reads "…see the Trades tab" (flag `ux.outlook_inline_default` on)
    and "…check the Trades tab" (off). **Both arms** — they are separate string literals.

### Screen library — capture delta, and a manifest gap

`screens/manifest.json` hashes each screen's **declared** `source` list. Declared dependencies on
the files this change touches:

| Screen | Declares | Captures |
|---|---|---|
| `matches` | `MatchesScreen.tsx` | 9 |
| `trios` | `RankScreen.tsx` | 10 |
| `quick-rank` | `RankScreen.tsx` | 2 |
| `draft-room` | `TabNav.tsx` | 4 |
| `sheets-rank-menu` | `TabNav.tsx` | 2 |

→ `screen-freshness.sh` will flag **5 screens / 27 captures**.

**That under-reports, and the plan must say so.** The tab bar is rendered in every tab-stack
frame, but only 2 of 32 screens declare `TabNav.tsx` as a source. `trades` (7 captures),
`league` (11), `portfolio` (2), `tiers` (7), `quick-set` (1) and others all show the bar and
will silently keep a stale "Acquire" PNG. This is a **pre-existing manifest gap**, not caused by
this change, but this change is the first to expose it.

**Recommendation:** re-capture the 5 flagged screens **plus** every tab-stack screen whose frames
include the bottom bar. See **CP-8** — this is the single largest cost item in an otherwise
trivial change (~4–7 min per screen).

### Ship evidence

11. `living-memory/TEST_LEDGER.md` — flows run, pass/fail, sim device, SHA.
12. `qa/sim-runs/last-sim-run.json` — required by `githooks/pre-push` for any `mobile/src` push.

---

## Risks and cross-item collisions

### R-1 — A-20 is two findings in one row; only half is planned here

A-20 reads *"Draft tab out of season; 'Acquire' naming"* and its resolution covers both the
seasonal `draft.tab` toggle and the label. **The draft-tab half is excluded by operator decision
and is not planned, designed for, or costed in this document.** Note the entanglement:
`config/features.json:170`'s `_comment_draft_tab` prose contains the tab list
"Rank / Acquire / Draft / Matches / League", so the two halves touch one shared string
(see CP-4). No other coupling exists. Anyone closing A-20 must run the draft-tab half separately;
this plan does **not** close A-20.

### R-2 — reverting a deliberate operator decision

"Acquire" was an explicit operator ask (#245). This plan reverses it on the strength of #246
having removed the two-channel hub that justified it. **The operator must confirm** — CP-1.
Mitigation: DECISIONS.md records both directions and the reason, so the record does not
lose the original intent.

### R-3 — partial-rename hazard, deliberately accepted

Group 2's "Acquire" survives. A user could see the tab say "Trades" and a picker pill say
"Acquire" in the same session. Judged correct — they are different words that share spelling —
but it is a conscious acceptance of local inconsistency, surfaced at CP-2.

### R-4 — capture-manifest gap hides stale screenshots

Covered in the [Test plan](#test-plan); actioned at CP-8. Left unaddressed, the design-truth
library keeps showing a label the app no longer has.

### Cross-item collisions — line level

**Sequencing:** P0 (`p0-remediation-2026-08-10`) merges to `main` **before** any P1 build.
This branch rebases onto post-P0 `main` before edit 1.

| Item | Their file:line | My file:line | Verdict |
|---|---|---|---|
| **P0-1** edit #14 | `RankScreen.tsx:686` — add `testID="rank.unlocked-banner"` to the `unlockedBanner` `View` | `RankScreen.tsx:693-694` — the two banner copy strings | **REAL COLLISION.** Same JSX element (`:685-697`), 7 lines apart → one diff hunk in a 3-way merge. Rebase onto P0 first, then re-locate by content, not by line number. |
| **P0-1** prose | `plan-p0-1.md:80-82` quotes `"Your board now prices your trades — see the Acquire tab"` verbatim | edit 4 changes that exact string | Their **plan doc** goes stale. Cosmetic; no code impact. Worth a one-line note when P1 lands. |
| **P0-1** Maestro | new `flows/p0-1-quickset-unlock.yaml` asserts the banner | edits 4–5 change banner text | **SAFE.** P0-1 §3.4 chose `testID="rank.unlocked-banner"` *specifically* to avoid a text regex on flag-dependent copy. Their flow asserts the id. Text-independent by design. |
| **P0-7** edit #7 | `TabNav.tsx` — one `track('tab_selected', …)` per existing `tabPress` (6 handlers, incl. the Trades tab's at `:660-682`) | `TabNav.tsx:655-656` — `options` block of the **same** `Tab.Screen` (`:647-683`) | **REAL COLLISION.** Same JSX element, ~5 lines apart, different props (`options` vs `listeners`). Git may auto-merge; do not rely on it. Rebase and verify by reading the merged element. |
| **P0-7** taxonomy | `tab_selected` prop `tab ∈ rank\|trades\|draft\|matches\|league` (plan `:164`) | tab **label** only | **SAFE and confirms the bright line** — P0-7's values are route names. A label change cannot alter an event value. |
| **P0-7** §595 | its own conflict matrix lists `TabNav.tsx` as "edited, none found" | — | That matrix predates P1-11. **P1-11 is a new entrant on `TabNav.tsx`** — flag to the P0-7 owner. |
| **P0-2** | `TradesScreen.tsx` (18 edits), `Toast.tsx`, `capture/trades.yaml`, `screens/mobile/trades/` | none of these — `TradesScreen.tsx:3969` is Group 2 and stays untouched | **NO FILE OVERLAP.** Only shared consequence: both invalidate `screens/mobile/trades/` captures. Sequence the re-capture **after both** land; do not capture twice. |
| **P0-8/9** | `TradesScreen.tsx`, `analystScript.ts`, `useGuide.ts`, `api/flags.ts`, `useFeatureFlags.ts`, `capture/onboarding-tour@fresh.yaml`, `flows/guide-no-false-signoff@release.yaml` | `capture/onboarding-tour@fresh.yaml:131` — **comment only**, in a different region (they edit the S8.1 header comment) | **NEAR-MISS, same file.** Both comment-only, different hunks. Trivial to resolve; listed so the HLD can order it. |
| **P0-8/9** `:111` | prose: *"Launch routing to the Acquire tab on first run lives in `TabNav.tsx` (audit cite `:208-237`)"* | — | A **read**, not an edit. `TabNav.tsx` is absent from their change list (§4). No conflict; their plan prose goes stale. |
| **P0-6** | `MatchesScreen.tsx:616-623` — add `leagueName` to the `TradeCard` mount | `MatchesScreen.tsx:660` | **SAME FILE, different hunks** (~40 lines apart). Auto-merges. Low risk. |
| **P0-5** | `RootNav.tsx:398` — routing | `RootNav.tsx:71` — comment | **SAME FILE, far apart.** No risk. |
| **A-27** (P2) | proposes deleting `TradeFinderHubScreen.tsx` (unrouted) | edit 6 changes one word in it | If A-27 lands first, **drop edit 6**. If P1-11 lands first, A-27 deletes the file and the edit evaporates. Either order is safe. CP-3. |
| **A-33** (P1) | reconciles `config/features.json` `_comment_draft_extensions` + `mock_draft_service.py:294` | CP-4 concerns `_comment_draft_tab` in the **same file** | **SAME FILE, adjacent comment keys.** Coordinate if both run in this P1 round. |

**Merge order recommendation for the HLD:**
`P0-1` → `P0-7` → (`P0-2`, `P0-6`, `P0-8/9` in any order) → **P1-11** → screen re-capture, once.
P1-11 last among the `RankScreen`/`TabNav` writers minimises rebase cost, and a single
re-capture pass at the end serves P0-2 and P1-11 together.

---

## Operator checkpoints

Each needs a decision before or during build. Recommendations given; none is agent-decidable.

**CP-1 — Reverse #245?** *(blocking)*
"Acquire" was your explicit ask on 2026-08-05. This plan reverses it because #246 (same day)
removed the trade + free-agency hub that justified the two-channel name, and because the app
contradicts itself today ("Acquire tab" above a "Go to Trades" button).
→ **Recommend: yes, revert to "Trades."** Confirm before edit 1.

**CP-2 — Confirm the scope line between the tab name and the direction verb.** *(blocking)*
The plan renames "Acquire" only where it names the tab (6 sites), and leaves it where it means
"get this player, as opposed to trade away" (9 user-visible sites, mobile + web). Renaming the
latter yields "Trade away / Trades."
→ **Recommend: hold the line as drawn.** If you want the direction verb changed too, that is a
separate, larger item (it touches web, and `docs/design/components.md:69` specs it).

**CP-3 — `TradeFinderHubScreen.tsx:487`, the dead page title.** *(non-blocking)*
Unrouted since #246; A-27 proposes deleting the file at P2.
→ **Recommend: change the word anyway** (~0 cost, and stale in-tree text is exactly what caused
the P0-4 false blocker). Alternative: skip it and let A-27 delete the file.

**CP-4 — `_comment_draft_tab` prose in 4 JSON files.** *(non-blocking)*
`config/features.json:170` + 3 test fixtures read "(third: Rank / Acquire / Draft / Matches / League)".
Descriptive only; nothing parses it. But it is the same class of stale comment A-33 exists to fix,
and it is the one string shared with A-20's excluded draft-tab half.
→ **Recommend: update the prose in all four** (values byte-identical, so no flag surface moves).
Alternative: defer to whoever runs the draft-tab half.

**CP-5 — A/B, or just ship?** *(blocking if you want the harness)*
The audit labels A-20 an "A/B candidate." Its own §"Before you read the A/B labels" records
16 production users and a ~400-per-arm floor for a real read.
→ **Recommend: ship it, no flag, no split.** Compare pre/post on P0-7's `tab_selected`.
A flag to guard five string literals costs more than the revert it protects against.

**CP-6 — the new Maestro assertion may not be expressible.** *(non-blocking)*
Combined `id: "tab.trades"` + `text: "Trades"` may not resolve, since the testID is on the
pressable and the label is a descendant `Text`.
→ **Recommend: try it once on the sim.** If it does not resolve, **drop it** and take a written
waiver in the scope block, resting on the screen library as visual evidence. Do **not** fall back
to a bare `text: "Trades"` — `04`'s frames contain other "Trades" copy, so it would pass without
asserting anything.

**CP-7 — Tier 1 or Tier 2 sim gate?** *(blocking)*
`TabNav.tsx` is navigation → Tier 1 by the matrix. But no navigation *behaviour* changes: no
route, no listener, no structure — two string literals in an `options` block.
→ **Recommend: Tier 2** (feature flow + affected smoke subset + `screen-freshness.sh`), recorded
as a deviation in the scope block per the matrix's own "deviations are decisions" rule.
Absent your call, the plan executes **Tier 1**.

**CP-8 — how wide is the re-capture?** *(blocking; biggest cost item)*
`screen-freshness.sh` will flag 5 screens / 27 captures. It **under-reports**: only 2 of 32
screens declare `TabNav.tsx` as a source, yet the tab bar renders in every tab-stack frame, so
`trades`, `league`, `portfolio`, `tiers`, `quick-set` and others will keep stale "Acquire" PNGs.
At 4–7 min per screen, the full sweep is the dominant cost of an otherwise five-word change.
→ **Recommend:** (a) re-capture all tab-stack screens once, **after P0-2 also lands**, so the
`trades` screen is captured a single time; and (b) file the manifest gap — every tab-stack screen
should declare `mobile/src/navigation/TabNav.tsx` in its `source` list — as its own follow-up item,
since it will silently mis-report on the next nav change too.
