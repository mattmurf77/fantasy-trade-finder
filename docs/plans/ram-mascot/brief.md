# Brief — The Ram replaces The Analyst (mascot + guide avatar)

**Date:** 2026-08-22 · **Status:** BRIEF — awaiting operator go on §1 · **Owner:** operator (decisions), one Opus build session per part
**Asked by the operator:** *"replace the analyst with the logo avatar (the ram)… that avatar makes more sense to keep the branding together… Expectation that the ram has all poses that the analyst has… I would like to explore a version that matches the design of the logo rather than the branding guide. We already have Higgsfield."*

This brief covers the three parts in order. Each part has a decision, a deliverable, an acceptance test, and what it must not touch. Nothing here starts until #384's W6-B has landed — the guide bubble is the one file both touch.

---

## 0. What exists today (verified)

| Thing | Where | Fact |
|---|---|---|
| The Analyst | `mobile/src/components/analyst/` | Six `react-native-svg` poses — `neutral · point · celebrate · computing · thinking · oops` — each a 1:1 translation of an operator-approved SVG in `mockups/avatar-lab/analyst-poses.html`, plus a shared part-kit (`parts.tsx`). ViewBoxes 150–170 × 150. |
| The switcher | `analyst/index.tsx` | `AnalystAvatar({ pose, size, flip })` — the **only** API the rest of the app uses. `BUBBLE_ANCHOR = {x:.5, y:0}` (top-centre). `size` is the rendered width (96 in the guide bubble, 44 / 38 on Team Review). |
| Call sites | 3 | `AnalystGuide.tsx:295` (the bubble), `TeamReviewScreen.tsx:351`, `TeamReviewEntryCard.tsx:118`. Nothing else imports a pose. |
| Name in copy | 6 strings | Settings toggle title + description (two Settings variants), the bubble's "who" label, the opening line *"I'm The Analyst. I model dynasty trades — you bring the roster."*, one a11y hint. |
| Analytics | `guide_step_shown{pose}` | The six pose names are values on a registered prop. Keeping the pose vocabulary keeps the analytics unchanged. |
| The ram | `mobile/assets/icon.png` (+ splash, Android `splashscreen_logo`) | A **painted 1024 px raster**: brown pebbled football head, ice (`#56D9EC`-family) horns, grey ears, pink glowing eyes and grin, on ink-0. **No vector source in the repo** (icon masters live in a gitignored folder that may be absent). |
| The rules that bite | `mobile/assets/CLAUDE.md`, `docs/design/brand.md` | "In-app icons are vector; mascot art is `react-native-svg`. Do not add raster UI assets." · "No gradient, no glow." · Mascot is "an **illustration asset, not UI chrome**: allowed in empty states, celebration moments, and the auth page." |
| The stale decision | `brand.md:44`, `living-memory/BRAND.md §Mascot`, **Q-009** (open since 2026-05-21) | Both docs still say the mascot is a *fumbling running back* ("Tommy Tumble vs Ricky Rumble"). The shipped icon is the ram. The docs and the product already disagree. |
| Approval path | `analyst/CLAUDE.md` "Rule: mockup first" | Art changes go to the avatar lab HTML first, get approved there, then are re-translated. |

**Two consequences worth stating before any work starts.** (1) A logo-match ram is painted art — gradients, glow, soft shading. It will not vectorise into clean `react-native-svg` paths; the honest medium for it is a **raster sprite per pose**, which today's assets rule forbids. Part 1 therefore has to *decide* that rule, not work around it. (2) The guide bubble attaches at the top-centre of the avatar box — which on a ram is **between the horns**. The pose sheet must leave that anchor clear, or the anchor moves.

---

## 1. Decision — the ram is the mascot (closes Q-009)

**Decision to record (proposed D-154):**
- The **ram** — the shipped app-icon character — is Fleeced's mascot **and** its guide avatar. The fumbling-RB concept is retired; Q-009 closes as "neither — the ram".
- The guide persona keeps its **role name** for now: it still introduces itself as *The Analyst* (the role is "I model trades"; the ram is who plays it). A character name is a separate, later call — the brief does not need it. *(If the operator wants a name now, it goes in the same decision.)*
- **Medium rule, amended:** the mascot may ship as **raster pose sprites** (`@2x/@3x` PNG with alpha) *when* the approved art is painted; vector remains the rule for everything else. The "no gradient, no glow" rule applies to UI chrome and stays; the mascot is an illustration asset (brand.md already says so) and is exempt **inside its own box only** — no glow bleeding onto surfaces, no gradient backgrounds behind it.
- **Where it may appear is unchanged:** the guide bubble, Team Review, empty states, celebration moments, the auth page. Never inline with data.

**Docs this decision touches:** `docs/design/brand.md` §Mascot · `living-memory/BRAND.md` §Mascot & Visual Branding · `mobile/assets/CLAUDE.md` (the raster exception, scoped) · `docs/design/components.md` (the two "mascot illustration" mentions — no change in placement rules) · `living-memory/OPEN_QUESTIONS.md` Q-009 → CLOSED · `living-memory/DECISIONS.md` D-154.

**Acceptance:** the four docs agree with the icon; Q-009 is closed; no code changes in this part.

---

## 2. Art — six ram poses, two explorations, via Higgsfield

### 2.1 What "all the poses" means

Each Analyst pose carries a *meaning* the script relies on. The ram must carry the same meaning, not copy the gesture — a ram has no glasses, tie, or foam finger.

| Pose | Used for (script) | Analyst gesture | Ram equivalent (brief to the generator) | Must hold |
|---|---|---|---|---|
| `neutral` | most bubbles (12 beats) | upright, glasses, slight smile | head-on, calm grin, horns symmetric | the default read at 38 pt |
| `point` | spotlight beats (16) — **`flip` mirrors it toward the target** | foam finger pointing right | head turned ~30° **right**, one horn forward, eyes toward the target; a clear directional read that survives `scaleX(-1)` | **points right by default; no text/asymmetric marking that breaks when flipped**; margin on the pointing side |
| `celebrate` | re-rank reveal, first like, sign-off (7) | arms up | head thrown back, grin wide, eyes bright, horns up | reads as joy at 38 pt |
| `computing` | "give me a second" — pre-deck, regen (1) | laptop, smaller body | eyes narrowed/down as if reading, a faint ice scan-line or cursor glint in the eyes — **no laptop prop** | distinguishable from `thinking` |
| `thinking` | "hmm" beats (3) | hand on chin | head tilted, one eyebrow-ridge raised, eyes up-left | distinguishable from `computing` |
| `oops` | error/recovery beats (3) | crooked glasses | wince, one horn slightly askew, eyes squeezed | reads as "my bad", not angry |

Shared constraints for every pose: **same character** (one approved hero image is the reference for the other five); square-ish framing at ~150×150 logical units; **clear top-centre strip between the horns** for the bubble anchor (or we move `BUBBLE_ANCHOR` — decide in the lab); transparent background; no text, no watermark, no frame; readable at 38 pt and 96 pt on `#0C0E11`.

### 2.2 The two explorations

| | **A — Logo-match** (the operator's stated preference to explore) | **B — Chalkline-flat** (the branding-guide version, for comparison) |
|---|---|---|
| Look | The icon's painted style: pebbled brown football skin, glossy ice horns with specular highlights, pink glowing eyes/grin, soft rim light | Flat fills, 2–3 tones per material, no gradients, no glow; ice and flare as accents only; the Analyst's stroke weight and simplicity |
| Medium | **Raster sprites** (`@2x/@3x` PNG, alpha) — requires the §1 rule amendment | `react-native-svg` via the avatar-lab "mockup first" path, like the Analyst |
| Risk | Reads as an app icon pasted into the UI at 38 pt; glow halo against ink-1 cards; heavier assets | Loses the exact logo likeness; a second hand-vectorisation job (1–2 days) |
| Why do both | The operator wants to *see* A; B is the control that shows what the brand rules would have produced, so the choice is made on evidence, not a rule |

### 2.3 Generation plan (Higgsfield, `character-sheet` workflow)

The MCP's `character-sheet` workflow is loaded first (it dictates slot order and the negative tail). Steps, in order — **no generation is run until the operator says "generate"** (workflow Mode B), and `use_unlim` is passed only if the operator asks to spend the free-trial allowance:

1. **Reference upload.** `media_upload` → `mobile/assets/icon.png` as the *style and identity* reference (it is our own IP, so the workflow's IP rule is satisfied; the prompt still describes the character explicitly so it does not depend on the reference).
2. **Model pick.** `models_explore(action:'recommend')` with the goal "stylised character expression sheet, consistent identity across six poses, transparent background" — one model for A (painted/3D-stylised) and, if different, one for B (flat 2D).
3. **Hero + consistency sheet (one call per exploration).** Composition = the workflow's **expression sheet** variant, adapted: *"Character expression sheet, six head-and-shoulders views of the identical original character in a row, evenly spaced: neutral, pointing right, celebrating, reading/computing, thinking, wincing,"* then the identity slot (the ram described once: "anthropomorphic football ram head — pebbled brown leather skin with white laces down the centre, two large curled horns in glossy ice-blue (#56D9EC family), small grey ears, almond eyes and grin glowing hot pink"), the render module (A: *"painted 3D-stylised render, soft rim light, glossy specular horns, subtle subsurface glow on eyes"*; B: *"flat vector illustration, cel-shaded with at most three tones per material, crisp even linework, no gradients, no glow"*), lighting, quality tail, and the negative tail (*no text, no watermark, no logos, no frame borders, no background props, single character, no duplicate figures, transparent or pure #0C0E11 background*). Aspect **16:9** for the row.
4. **Operator picks the hero.** The single best `neutral` from the sheet becomes the **identity reference** for step 5 (workflow Principle 4: every established detail carries forward unchanged).
5. **Per-pose singles at 1:1.** Six calls per exploration, each with the hero as reference and the pose clause changed, square aspect, background `#0C0E11` (so the halo is judged on the real ground) **and** a transparent variant for the sprite. `remove_background` on the approved frames if the model cannot output alpha; `upscale_image` to 2K for the sprite masters.
6. **One fix round per pose** ("tighten the point direction", "less glow", "horns symmetric") — the workflow budgets exactly one.
7. **The lab.** New page `mockups/avatar-lab/ram-poses.html`: A and B side by side with the Analyst row, each pose at **38 / 44 / 96 pt on ink-0 and ink-1**, with the bubble drawn at the top-centre anchor so the horn clash is visible, and the `point` pose shown flipped. The operator picks A, B, or a blend — **the lab is the decision artefact**, per the mockup-first rule.
8. **Medium step.** A: export `@2x/@3x` PNG sprites, alpha, trimmed to the pose box, target ≤ 60 KB each. B: hand-translate the six SVGs to `react-native-svg` exactly as the Analyst was (shared part-kit for horns/ears/eyes).

**Acceptance for Part 2:** six poses per chosen exploration in the lab; identity consistent across all six (same horn curl, same eye shape, same lace count); `point` reads correctly both unflipped and flipped; anchor strip clear or a new anchor agreed; every pose legible at 38 pt on ink-1; operator sign-off written into the lab page header.

**Budget:** ~2 sheet calls + ~12 single calls + ≤ 12 fix calls per exploration; one review session with the operator; B adds 1–2 days of vector translation if chosen.

---

## 3. Engineering — the swap

**Scope:** the guide avatar renderer, the three call sites (unchanged), the name strings, a flag, a guard, docs, checklist. No change to the tour script, the pose enum, spotlight anchoring logic, or analytics.

1. **Renderer behind a flag.** `onboarding.mascot_ram` (default `false`; allow-listed in `feature_flags.py`, `config/features.json`, `release.json`; `docs/config-reference.md`). `AnalystAvatar` keeps its signature and becomes the switch: flag on → `components/mascot/ram/` (six pose components — `<Image>`-backed sprites for A, or SVG for B); flag off → today's Analyst, byte-identical. `BUBBLE_ANCHOR` becomes per-mascot if the lab moved it. The flag is the rollback lever and a clean A/B.
2. **Name strings.** The six "The Analyst" strings stay unless §1 names the character; if it does, one `MASCOT_NAME` constant, six call sites.
3. **Guard** `mobile/tests/check-mascot-ram.js`: six pose components exist and are wired in the switch; the flag gates the switch (sabotage: `|| true`); the three call sites still go through `AnalystAvatar` (no direct pose imports); sprite files (A) exist at `@2x/@3x` and are under the size budget; the `point` component honours `flip`; `assets/CLAUDE.md`'s raster exception names exactly the sprite folder.
4. **Docs:** `components/analyst/CLAUDE.md` (or a new `components/mascot/CLAUDE.md`), `brand.md`, `assets/CLAUDE.md`, `glossary.md` ("Mascot"), `screens/CLAUDE.md` mentions, `scope.md` for the feature (full gates — it is user-visible; analytics row: *none new, pose values unchanged* is the explicit waiver).
5. **TestFlight checklist** (the only runtime evidence): flag off byte-identical; flag on — every pose at 96 pt in the bubble across a full tour (`Show me around` on the calculator is the fastest way to see all six), `point` flipped toward a left-side target, Team Review at 44/38 pt, glow/halo on ink-1 cards, dark and light status-bar contexts, VoiceOver unchanged.

**Estimate:** half a day to a day of engineering once the art is approved; plus the §2.3 step 8 medium work.

---

## 4. Sequencing and the three decision points

| Step | Who | Gate |
|---|---|---|
| 0 | lead | W6-B (#384) lands — shared file `AnalystGuide.tsx` |
| **D1** | operator | §1: ram = mascot; name now or later; raster exception — **yes/no** |
| 1 | lead + Higgsfield | §2.3 steps 1–3, both explorations → lab page |
| **D2** | operator | pick A / B / blend in the lab; anchor decision |
| 2 | lead + Higgsfield | §2.3 steps 4–8 for the chosen one |
| 3 | one Opus build session | §3, full gates, dark behind `onboarding.mascot_ram` |
| **D3** | operator | TestFlight pass → flip |

**Not in this brief:** renaming the product's guide role, any change to tour copy or beats, a web or extension mascot, the notification icon (it is `icon.png` and already the ram).
