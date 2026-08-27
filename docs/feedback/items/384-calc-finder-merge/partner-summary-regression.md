# #384 regression — the partner team-shape summary, restored to the merged layout

**Date:** 2026-08-27
**Entry point:** direct ask, off the [2026-08-27 calc-vs-guided-finder parity audit](../../../reviews/2026-08-27-calc-vs-guided-finder-audit.md) — §3 "The five `partial` rows", row 24
**Builder:** claude/calc-merged-partner-summary
**Operator sign-off on waivers:** not needed (no waivers)

---

## 0. What broke, and the proof that it was a regression and not a ruling

The In-league calculator's partner list has carried a per-partner **team-shape line**
— colour-coded QB / RB / WR / TE values plus the owned-pick pool, in pick-equivalent
labels ("≈3 firsts") — since the DTF teardown landed it in `fbd55611`
(2026-07-27), refined by #306 in `780c035c` (2026-08-12) to render the server's
`value_label` instead of raw numerics.

**#384 W1 (`dfcd5321`) replaced the partner chip row with a Team dropdown + sheet**
(#333) and did not carry the line across. Its own commit message describes the new
sheet as "listing leaguemates with their R/R*/NR rank state" — handle and badge, no
shape. `calc.merged_layout` is `true` in `config/features.json` and has been live for
all users since v1.16.0, so **every user has been seeing the reduced list**.

Checked against the #384 record before touching anything:

| Source | Says |
|---|---|
| [`status.md`](status.md) § Operator rulings 1–10 | Nothing about the partner list. Rulings **6** and **7** remove the *utility row* and the *three-tab subnav* — different surfaces |
| [`status.md`](status.md) § Round-2 rulings 1–4 | Decline overlay, include-players, replace the manual tab / delete the demo calc, tour re-entry. Nothing about the partner list |
| [`plan.md`](plan.md) §26, §80, §141 | The W1 layout spec says "League and Team — their own dropdowns … This is #333". It specifies where the control moves. It never rules that the shape line is dropped |
| `plan.md` §15 | Lists `calc.partner-summary.<id>` in the page's **existing controls** inventory — the control #384 inherited, not one it retired |

Verdict: an omission during a control-shape change, not a ruling. Restored.

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** the change adds no interaction. The
  shape line is inert text inside a row whose only gesture (`onPress` → `setOpponentId`)
  is unchanged. No event fires on the stacked page's copy of this line today either, so
  there is nothing to keep at parity.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. The data is already on the wire —
  `partnerSummaries` is built from the existing `getPowerRankings(leagueId, 'consensus')`
  query (`InLeagueCalculator.tsx:341-345`), which is unconditional and already feeds
  `needsByTeam` in the merged layout. **No new request.**
- New/changed feature flags: **none**. The fix lands inside the existing
  `calc.merged_layout` branch; flag-off behaviour is unchanged.
- New env vars / `model_config` keys: **none**.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-calc-merged-layout.js` **extended** with
      section 22 (a–h). New file not warranted — this guard already owns the
      "the merged branch silently dropped something the stacked page shows" failure class
      (assertions 13/14 are the scoring-format chips and the #191 conversion note, the
      exact same shape of defect). `npm run test:calc-merged-layout` unchanged.

      Pins: one shared implementation (22a/22b) · the merged sheet mounts it (22c/22d) ·
      fed from the same memo (22e) · the sheet row *speaks* the shape (22f) ·
      the row can shrink so the badge is never pushed off (22g) ·
      the flag-off stacked page keeps it (22h).

- [x] **Unit tests:** none. Backend untouched — no route, no query, no serializer changed.
- [x] **Code-walk proof:** §A below.
- [x] **Manual TestFlight checklist:** §B below. Runtime proof matters here: the whole
      defect is "a line does not appear", and the fix reflows a sheet row from one line to
      two — layout truth the structural guard cannot assert.
- `testID`s added/renamed: **none**. `calc.partner-summary.<id>` is reused verbatim; the
  two mounts are in mutually-exclusive flag branches so at most one is ever on screen.
  `bash mobile/scripts/testid-lint.sh` → `testid-lint OK`.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added, renamed, removed, or contract-changed |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifted |
| `docs/architecture.md` | n/a | no module wiring or data-flow change; same component, same query |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | position hexes are read through `posColor()` from `theme/colors.ts`, unchanged and unrestyled — this change consumes the encoding, it does not define it |
| `docs/glossary.md` | n/a | no new domain term |
| ADR / `DECISIONS.md` | n/a | restoring shipped behaviour to the state its own plan inventoried is not a new design choice |
| `mobile/src/components/CLAUDE.md` | **updated** | `InLeagueCalculator` row — the merged-layout sentence now names the shape line alongside the format chips it already listed |

## 5. Ship gate declaration

- **CI green (run locally on this branch):**
  - `npx tsc --noEmit` → exit 0
  - all 84 `mobile/tests/check-*.js` guards → 0 failures
  - `bash mobile/scripts/testid-lint.sh` → `testid-lint OK`
  - `pytest backend/tests` — **not run, backend untouched** (`git diff --stat` is two mobile files)
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-08-27 entry.
- **TestFlight verification:** §B, owed by the operator on the next build.
- Express lane declared by the operator? **No** — full gates.

---

## A · Code-walk proof

All cites are `mobile/src/components/InLeagueCalculator.tsx` on branch
`claude/calc-merged-partner-summary` unless stated.

### A1 — the data was already there; only the render was missing

1. `:341-345` — `powerQ` fetches `getPowerRankings(leagueId, 'consensus')`. **Not gated on
   `merged`**: one `useQuery` at component scope, no `enabled`.
2. `:352-369` — `partnerSummaries` maps `powerQ.data.teams` into
   `Record<string, PartnerSummary>`, capturing `t.positions?.<POS>?.value_label` and
   `t.picks.value_label` per team.
3. `:376` — `needsByTeam` reads the **same** `powerQ.data` and is consumed by the
   merged layout's evener/balance rows. So on the merged page the summaries were computed
   every render and thrown away. Restoring the line costs zero requests.

### A2 — where the line went missing

4. `:943` (`:895` on `origin/main`) — the stacked layout opens with `{!merged ? (`.
5. `:978-1002` — inside it, the partner chip row: handle + `Badge` + the shape line.
6. `:1338` — the merged pickers open with `{merged ? (`.
7. `:1379-1412` (`:1349-1380` on `origin/main`) — the merged team sheet's row rendered exactly
   `<Text>@{o.username}</Text>` + `<Badge label={state} />`. No `partnerSummaries` read
   anywhere between `testID="calc.team-sheet"` and its `</Modal>`. That absence is the
   defect, and `git show origin/main:…` confirms it on the shipped tree.

### A3 — the fix

8. `:164-167` — `PartnerSummary` type extracted, and `partnerSummaries`' inline record type
   at `:352` replaced with it. Same shape; `tsc --noEmit` is the check that it is.
9. `:177-180` — `partnerSummarySpoken(summary)` — the a11y string, lifted verbatim from the
   chip's old inline `a11ySummary` expression, still routed through `segmentSpoken`.
10. `:182-214` — `PartnerSummaryLine({userId, summary})` — the visible line, lifted verbatim:
    same `testID={\`calc.partner-summary.${userId}\`}`, same `styles.summaryLine`, same
    `numberOfLines={2}` + `ellipsizeMode="tail"`, same `posColor(pos)` per position label,
    same `segmentText` per segment, same `' · Picks '` tail.
11. `:979` — the chip's a11y string is now `summary ? partnerSummarySpoken(summary) : ''`.
12. `:1000-1002` — the chip's inline JSX is now `<PartnerSummaryLine userId={o.user_id} …/>`.
    Rendered output is byte-identical: same element tree, same props, same style objects.
13. `:1378` — the merged sheet row reads `partnerSummaries[o.user_id]`.
14. `:1385-1387` — its `accessibilityLabel` appends `partnerSummarySpoken(summary)`, exactly
    as the chip does, so VoiceOver hears the shape on both layouts.
15. `:1398-1405` — handle + line wrapped in `<View style={styles.teamRowMain}>`; the `Badge`
    stays the row's second child, unmoved.
16. `:1888-1891` — `teamRowMain: { flex: 1, flexBasis: 0, minWidth: 0, gap: 2, paddingVertical: space.xs }`.
    `minWidth: 0` is what lets the shape line ellipsize *inside* the row rather than widening
    it and pushing the badge off the sheet — the same reason `column` at `:1838` carries it.
    `teamRow` itself (`:1878-1887`) is untouched: `minHeight: 44` still holds, and the
    stacked content (18pt handle + 2 + 14pt line + 2×`space.xs`) sits under it, so no row
    grows and the sheet's `maxHeight: '60%'` + `ScrollView` absorb the rest.

### A4 — Chalkline compliance

- No new colour, radius, font or accent. `styles.summaryLine` (`:1912-1917`) is reused as-is:
  `fonts.data` at the 11px floor, `chalk.dim`.
- Position hexes come from `posColor()` (`theme/colors.ts`, imported `:41`) and are always
  paired with the text label — the data-encoding contract in
  `docs/cross-client-invariants.md`, consumed unchanged.
- `teamRowMain` introduces only flex/gap/padding tokens (`space.xs`). No emoji, no gradient,
  no radius.
- Guard assertion 8 (no `#384` font size below 11) and 11 (no emoji) still pass.

### A5 — the guard is falsifiable

Each sabotage was applied to the working tree, the guard run, and the tree restored:

| Sabotage | Guard result |
|---|---|
| Run against `origin/main`'s component verbatim — **the shipped regression** | 6 FAILED (22b, 22d, 22e, 22f, 22g, 22h) |
| Delete the `<PartnerSummaryLine>` mount from the merged sheet only | 1 FAILED — 22d |
| Sighted-only restore: strip `partnerSummarySpoken` from the sheet row's a11y label | 1 FAILED — 22f |
| Hand-copy an inline block into the sheet instead of using the shared helper | 2 FAILED — 22a, 22d |

The first row is the one that matters: **the guard fails on the build that shipped the bug.**

---

## B · Manual TestFlight checklist (operator)

Prerequisite: a league with ≥3 leaguemates whose rosters differ noticeably by position, and
where at least one member owns draft picks. `calc.merged_layout` is on by default — no
setup needed. Where a step says "shape line", it means a line like
`QB ≈1 first · RB ≈2 firsts · WR ≈3 firsts · TE ≈0.5 firsts · Picks ≈2 firsts`.

1. Open **Acquire → Calc** (the In-league calculator). Tap the **Team** dropdown.
   → *Expect:* the sheet lists every leaguemate. **Each row shows the handle on line 1 and a
   shape line on line 2**, with QB/RB/WR/TE in their position colours. The R / R\* / NR badge
   is still on the right of each row, fully visible, not clipped or wrapped.
   → *This step alone is the regression.* Before the fix, line 2 was absent.
2. Read three different rows' shape lines.
   → *Expect:* the numbers **differ between teams** and are plausible against those rosters
   (a QB-heavy team's QB segment leads). All-identical or all-zero means `powerQ` is failing,
   not this fix — report it.
3. Find a member who owns no future picks (or the ESPN case, where picks are unavailable).
   → *Expect:* their line ends at **TE**, with no trailing `· Picks` and no empty separator.
4. Find a member who owns picks.
   → *Expect:* a `· Picks ≈N firsts` tail, in the same pick-equivalent wording as the rest of
   the line. **No raw numbers like `4,200`** anywhere on the line — a numeric means the
   server dropped `value_label`; note which member and which segment.
5. Rotate to landscape, or set **Settings → Display → Larger Text** two steps up, and reopen
   the sheet.
   → *Expect:* the shape line wraps to **at most two lines** and ellipsizes with "…" rather
   than a third line; the badge stays on screen; rows stay tappable.
6. Tap a member.
   → *Expect:* the sheet closes, the Team dropdown shows that handle, and the calculator
   re-prices for them exactly as before. (Selection behaviour is unchanged by this fix — this
   step is here to confirm the reflow did not break the tap target.)
7. Turn VoiceOver on. Reopen the sheet and swipe through the rows.
   → *Expect:* each row is announced as one element:
   *"@handle, ranked, QB about 1 first, RB about 2 firsts, WR about 3 firsts, TE about
   0.5 firsts, picks about 2 firsts, button"*. The shape must be **spoken**, not just drawn.
   A row read as only "@handle, ranked, button" is the sighted-only failure — report it.
8. Scroll the sheet with more than ~8 leaguemates.
   → *Expect:* it scrolls; the sheet does not grow past ~60% of the screen; nothing under the
   home indicator is unreachable.

Log the outcome in `living-memory/TEST_LEDGER.md` under the 2026-08-27 entry.
