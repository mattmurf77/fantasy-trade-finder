# Tier Naming Proposal — memorable names for the 8-tier pick-value ladder

*2026-07-12 · Status: **PROPOSAL — nothing adopted, no code changed.** Display-layer only: tier keys, colors, and Elo bands are untouched in every scheme below.*

The 8-tier ladder (feedback #117/#118) currently labels tiers with pure pick math: `4+ 1sts / 3 1sts / 2 1sts / 1st / 2nd / 3rd / 4th / Waivers`. That precision is the ladder's whole point — but it has no personality. The operator's friend's calculator (TI-CALC) shows the alternative: evocative tier names *with the pick math kept beside them*. This doc proposes three naming schemes in that spirit.

**Hard requirement carried through every scheme:** the pick equivalence stays visible. A name never replaces the pick math — it headlines it. Canonical rendering: name prominent, pick math as sublabel:

> `CORNERSTONE · 3 1sts`

---

## 1. The inspiration: TI-CALC's scheme, verbatim

Source: https://fantasy-trade-calculator.vercel.app (live site is JS-rendered; names extracted from source at https://github.com/onrits/fantasy-trade-calculator). Author: the operator's friend, who is winding the app down to help FTF — see the full teardown at [`docs/competitor-teardown-ti-calc.md`](../competitor-teardown-ti-calc.md). His tier tables are duplicated across files and have drifted, so there are actually **three** naming variants in his codebase:

**Variant 1 — the tier headers on the drag-drop rankings board (`components/EditableRankings.js`, `tierNames`). This is the canonical inspiration — name + pick anchor + tier number fused into one header string:**

```js
const tierNames = {
    1: "Prometheus - 4+ 1sts - Tier 1",
    2: "Franchise Altering - 3+ 1sts - Tier 2",
    3: "Cornerstones - 2-3 1sts - Tier 3",
    4: "Portfolio Pillars - 2+ 1sts - Tier 4",
    5: "Hopeful Elites - 1-2 1sts - Tier 5",
    6: "Kind of Exciting - 1st+ - Tier 6",
    7: "Solid Pieces - Late 1st - Tier 7",
    8: "Bridge Players - Early 2nd - Tier 8",
    9: "Rentals - Mid 2nd - Tier 9",
    10: "Bench Fodder - Mid 3rd - Tier 10",
    11: "Roster Cloggers - Mid 4th - Tier 11",
    12: "Insurance - Tier 12",
    13: "Cut Plz - Tier 13",
};
```

**Variant 2 — the read-only rankings table (`components/RankingsTable.js`, `tierNames`)**: "League Breakers", "The Elite", "Franchise Cornerstones", "Stars", "High-end Starters", "Above Average Starters", "Starters", "Low-end Starters", "Fringe Starters", "Contributors", "Bench Pieces", "Insurance", "Roster Cloggers".

**Variant 3 — the legend (`components/Legend.js`)** uses plain "Tier 1"–"Tier 11+" names but leads each description with a role phrase: "League Breaking. Untouchables.", "True elites.", "Cornerstones.", "Strong starters.", "Solid producers.", "Serviceable starters.", "Fringe starters.", "Insurance plays.", "Bench fillers.", "Waiver-level players.", "Below replacement. Roster Cloggers."

What to take from it: the names are **roster-construction nouns with attitude** (Cornerstones, Bridge Players, Bench Fodder, Roster Cloggers), the pick anchor is **always co-present** in the header, and the bottom tiers are allowed to be a little mean. What not to take: the drift (three variants of the same taxonomy), the mythology one-off ("Prometheus" doesn't rhyme with anything else in the set), and hedge names ("Kind of Exciting", "Hopeful Elites") that are charming but read as indecision at badge size.

---

## 2. Constraints (apply to every scheme)

1. **≤ 12 characters** — must fit the Tiers screen header, the QuickSet step header, and the TierBadge without truncation.
2. **Pick math stays visible** — name headlines, pick equivalence sublabels. Non-negotiable; the #117 ladder's value is that a tier *states what a player is worth*.
3. **Distinct at a glance** — no two names that skim alike; ordering should be guessable without the sublabel.
4. **No trademarked fantasy-industry terms** (KeepTradeCut, FantasyCalc, Dynasty Daddy, etc.) and no third-party marks (rules out the friend's "Prometheus"-adjacent "Konami Code" framing too).
5. **No emoji** (Chalkline prohibition #1) and **format-agnostic** — a name can't imply QB-ness or any position; the same 8 names serve `1qb_ppr` and `sf_tep`.
6. **"Waivers" may stay literal** — it is already a name, not math; all three schemes keep it.
7. **Avoid words already load-bearing elsewhere in FTF** (collision risk):
   - *Elite, Starter, Solid, Depth* — the retired 2026-07-11 ladder, still alive in `web/css/styles.css`'s separate `.tier-elite/.tier-high/.tier-mid/.tier-depth` dynasty-value badge set.
   - *Untouchable* — `asset_preferences.list_type='untouchable'` ("never offer from my roster").
   - *Anchor* — the Pick Anchor wizard.
   - *Target, Sweetener* — trade-engine domain terms.

Tone target (Chalkline, ADR-004/005): chalk-on-slate coaching room. Terse, declarative, a little dry. Headers render UPPERCASE in Barlow Condensed; badges in Archivo 600 UPPER. Words a coach or a GM would actually say beat words a copywriter would say.

---

## 3. Scheme A — "Framework" (structural nouns; the homage)

The truest descendant of the friend's scheme: his best names are architecture (**Cornerstones**, **Portfolio Pillars**, **Bridge Players**), and FTF's own copy already says "Build your board." One coherent structural metaphor, top of the arch to the scrap pile.

| Tier key | Pick label | Name | Chars | Reading |
|---|---|---|---|---|
| `firsts_4plus` | 4+ 1sts | KEYSTONE | 8 | the piece the whole arch depends on |
| `firsts_3` | 3 1sts | CORNERSTONE | 11 | direct homage — his Tier 3, one rung up |
| `firsts_2` | 2 1sts | PILLAR | 6 | homage to "Portfolio Pillars" |
| `first_1` | 1st | FIXTURE | 7 | a fixture in the lineup; installed, reliable |
| `second` | 2nd | BRIDGE | 6 | homage to "Bridge Players"; gets you to the next window |
| `third` | 3rd | STOPGAP | 7 | patches a hole this week |
| `fourth` | 4th | SPARE | 5 | spare part |
| `waivers` | Waivers | WAIVERS | 7 | literal |

- **Rationale:** one metaphor, monotone descent, three of eight names are deliberate tributes to the calculator being retired to help FTF — the naming *is* the acknowledgment.
- **Tone fit vs Chalkline:** good. Concrete nouns, zero whimsy, reads like a depth-chart wall. Slight risk: the metaphor is *builder* language, not *coach* language, so it sits a half-step off the chalk-talk voice.
- **Watch:** STOPGAP/SPARE share an initial S (minor skim risk at badge size).

Mock render: `KEYSTONE · 4+ 1sts` · `BRIDGE · 2nd` · `SPARE · 4th`

---## 4. Scheme B — "Trade Desk" (asset-market language; the on-brand one)

FTF is a *trade* app: name the tiers the way the market talks about the assets. The names reinforce the pick sublabel instead of decorating it — `TRADE CHIP · 2nd` reads as one thought. Bonus: the top tier reuses vocabulary FTF already owns (the crown-asset premium and the `crown` icon in the Chalkline set).

| Tier key | Pick label | Name | Chars | Reading |
|---|---|---|---|---|
| `firsts_4plus` | 4+ 1sts | CROWN | 5 | the crown of the league; pairs with the existing `crown` icon |
| `firsts_3` | 3 1sts | HEADLINER | 9 | the name the trade is about |
| `firsts_2` | 2 1sts | PREMIUM | 7 | costs real capital |
| `first_1` | 1st | MAINSTAY | 8 | the reliable core holding |
| `second` | 2nd | TRADE CHIP | 10 | the classic 2nd-round-value piece deals get built from |
| `third` | 3rd | DART THROW | 10 | dynasty-native slang for a cheap speculative add |
| `fourth` | 4th | FLIER | 5 | "take a flier" |
| `waivers` | Waivers | WAIVERS | 7 | literal |

- **Rationale:** every name is trade-value language, so name and pick math say the same thing at two zoom levels — the strongest conceptual fit with the #117 ladder's "a tier states what a player is worth."
- **Tone fit vs Chalkline:** strong. Terse GM-speak; DART THROW and FLIER are words actual dynasty players use, no explanation cost; nothing cute.
- **Watch:** (a) CROWN deliberately overlaps the *crown asset* engine term — mostly aligned (a Crown-tier player is exactly who the crown-asset premium fires on), but "crown asset" means *best asset in a package* regardless of tier, so the overlap is imperfect; APEX (Scheme C) is the drop-in swap if that bothers anyone. (b) PREMIUM could collide with a future paid "Premium" plan — flagged as an open question; STUD is the alternate. (c) BLUE CHIP was considered for `firsts_3` and rejected: "BLUE CHIP" vs "TRADE CHIP" fails distinct-at-a-glance.

Mock render: `CROWN · 4+ 1sts` · `TRADE CHIP · 2nd` · `DART THROW · 3rd`

---

## 5. Scheme C — "Chalk" (terse rank adjectives; the minimal one)

The shortest possible names — pure intensity ladder, no metaphor to maintain, maximum badge legibility. If the names are flavor and the pick math is the meaning, spend as few pixels on flavor as possible.

| Tier key | Pick label | Name | Chars | Reading |
|---|---|---|---|---|
| `firsts_4plus` | 4+ 1sts | APEX | 4 | top of the board |
| `firsts_3` | 3 1sts | MARQUEE | 7 | the big name |
| `firsts_2` | 2 1sts | PRIME | 5 | peak value |
| `first_1` | 1st | CORE | 4 | what you build around |
| `second` | 2nd | STEADY | 6 | dependable, not headline |
| `third` | 3rd | ROTATION | 8 | in the mix, replaceable |
| `fourth` | 4th | FRINGE | 6 | roster bubble |
| `waivers` | Waivers | WAIVERS | 7 | literal |

- **Rationale:** unambiguous descent (APEX > MARQUEE > PRIME > CORE > STEADY > ROTATION > FRINGE > WAIVERS), every name ≤ 8 chars, so all render sizes — including the extension badge — fit name + sublabel comfortably.
- **Tone fit vs Chalkline:** best raw fit — these ARE chalk words, terse and dry. The cost is memorability: nothing here has the personality of "Bench Fodder"; it's the least "in the spirit of the friend's site" of the three.
- **Watch:** deliberately avoids the retired Elite/Starter/Solid/Depth words despite them being the obvious picks in this register — that's why STEADY and not SOLID, FRINGE and not DEPTH.

Mock render: `APEX · 4+ 1sts` · `CORE · 1st` · `FRINGE · 4th`

---

## 6. Recommendation: Scheme B ("Trade Desk"), Scheme A as runner-up

**Scheme B** is the pick, for three reasons:

1. **It's the only scheme where the names and the pick math argue for each other.** "TRADE CHIP · 2nd" is one idea said twice; "BRIDGE · 2nd" and "STEADY · 2nd" are a metaphor plus a number. In a trade-finding app, tier names that speak trade value are load-bearing, not decorative — the same property that made the friend's anchor "load-bearing in the UX."
2. **It borrows equity FTF already has**: the crown icon and crown-asset concept give CROWN instant internal meaning, and DART THROW/FLIER are the community's own words — memorable at zero teaching cost.
3. **It keeps the friend's spirit without his drift**: personality concentrated where he put it (evocative middle, dismissive bottom), but one canonical set, no mythology one-offs, no hedge names.

**Scheme A** is the runner-up and the right choice if the operator wants the naming itself to honor the friend's calculator — CORNERSTONE, PILLAR, and BRIDGE are a visible tribute. **Scheme C** is the fallback if any doubt remains about badge width or tone: it cannot be wrong, only forgettable. Schemes are also mixable (e.g. Scheme B with APEX for CROWN, or STUD for PREMIUM) since each name was checked against the constraints independently.

---

## 7. Implementation notes (for whoever builds the winner)

**Scope: labels only.** Tier keys (`firsts_4plus`…`waivers`), canonical hexes, rgba tint bases, and Elo bands in `backend/tier_config.json` are all untouched. This is a display-layer change to label maps plus docs — no API contract, no saved-board migration (boards store raw Elo).

Label map locations (the same list as `docs/cross-client-invariants.md` § "Tier keys, labels & color tokens"):

- **Mobile:** `mobile/src/utils/tierBands.ts` (`TIER_LABEL`, line ~38), `mobile/src/components/TierBadge.tsx` and `mobile/src/components/chalkline/Badge.tsx` (`TierChalkBadge`) label maps. QuickSet (`QuickSetTiersScreen`) and the Tiers screen headers consume these.
- **Web:** `web/positional-tiers.html` (`TIERS` / `TIER_LABELS_SHORT`, line ~2936), `web/profile.html` (`TIER_ORDER` / `TIER_LABELS`), `web/js/app.js` (`_eloToTierLabel`), `web/style-guide.html` badge swatches.
- **Extension:** `extension/content.js` (`TIER_LABELS`, line ~33) — note the Sleeper-page badge is the tightest surface; verify the two 10-char names (TRADE CHIP, DART THROW) at real size before committing to Scheme B there.
- **Backend (display-only):** `backend/og_image.py` (`TIER_ORDER` / `TIER_LABELS`) — share images will carry the names; good brand exposure, but confirm layout fits name + pick sublabel.
- **Docs:** add a **Name** column to the canonical table in `docs/cross-client-invariants.md` (keep the existing Label column as the pick sublabel), update the *Tier band* entry in `docs/glossary.md`, and note the change in `docs/design/components.md` wherever TierBadge/tier headers are specced.

Rendering spec (per the hard requirement): name in the header/badge's existing label style (UPPER), pick math as sublabel in `data`/`body-sm` chalk-dim — e.g. `CORNERSTONE · 3 1sts`. The accessibility invariant "tier color is never the only encoding — always paired with the text label" now pairs color with *name + pick math*; the pick sublabel must not be dropped on any surface, or the ladder's anchor semantics silently vanish there.

History note: #103's display-only pick sublabel (`Elite 1st+`) was retired when #117 made labels *be* pick terms. This proposal re-introduces a two-part label from the opposite direction (name over pick math). That's intentional, but it deserves a line in the invariants doc so a future session doesn't "simplify" the sublabel away again.

---

## 8. Open questions for the operator

1. **Replace or accompany, per surface?** Headers and QuickSet steps have room for `NAME · pick math`. The extension badge and dense mobile rows may only fit one — if so, which wins there: name or pick math? (Recommendation: pick math wins wherever only one fits; the names are flavor, the anchor is the product.)
2. **QuickSet step framing:** the walk currently asks, in effect, "who's worth 4+ 1sts?" Should steps lead with the name ("CROWN — who's worth 4+ 1sts?") or keep the question purely pick-denominated with the name as a chip?
3. **PREMIUM vs monetization:** if a paid plan will ever be called Premium, swap the `firsts_2` name (STUD is the vetted alternate) before shipping Scheme B.
4. **CROWN vs crown asset:** comfortable with the deliberate overlap, or swap in APEX?
5. **Does "Waivers" stay literal everywhere?** All three schemes assume yes.
6. **Should the friend get a visible credit** (e.g. a line in the tier legend), given Scheme A/B knowingly echo his scheme? He's winding his app down to help FTF, so this may be welcome — operator's call.
