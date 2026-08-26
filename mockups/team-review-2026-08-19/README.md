# Team Review — design lab

**Opened:** 2026-08-19 · **Rev 2:** 2026-08-19 (odds lit, D-094) · **Items:** #357 / #358 / #359 · **Status:** in flight
**Binding docs:** [`docs/feedback/items/357-team-review/`](../../docs/feedback/items/357-team-review/status.md)

Open [`index.html`](index.html) — single self-contained page, works over `file://`.

## The question this lab answers

What does "analyst-guided" concretely mean for a team read, and where does the
entry point live inside the find-a-trade experience?

## Verdicts

| Question | Answer | Beaten alternatives |
|---|---|---|
| Form | **Stepped beats** — one finding, one plain read, one action per screen | Narrated scroll (a dashboard with prose; nowhere to put a decision, so the preference-setting job never happens). Q&A (canned questions are a worse menu; open input needs an LLM, which contradicts "reuse what exists" and breaks the deterministic-copy precedent in `trade_narrative.py`). |
| Persona | **Reuse the Analyst** mascot + voice; **do not** reuse the `AnalystGuide` spotlight overlay | The overlay teaches a *control* by cutting a hole over it. Team Review presents *data* — a cutout over a chart is theatre. It also mounts in `RootNav` above the nav tree, whereas a data surface needs a routed screen with real back behavior. |
| Entry point | **A card at the top of `TradesHome`** (where #359 was filed), collapsing to a one-line row rather than vanishing; plus the deck's empty state | A seventh mode chip — rejected on the source's own measurement (`TradeFinderModeBar.tsx:50–58`: five chips already ≈402pt against ≈361pt usable, so the strip is scrolled and an appended chip is never seen). |
| Odds | **A playoff band chip on beat `standing`** (rev 2) | The lab originally recommended shipping odds-free with `standing` as a future seam. **The operator overruled that on 2026-08-19** (*"Outlook odds should be visible"*) and `outlook.odds` is now lit — D-094. Because the seam was designed in, this cost one chip, not a redesign. Still refused, on evidence rather than preference: **championship odds** (`title_pct` has no demonstrated skill) and **any bare percentage**. |
| #357's "+6 PPG" | **Cut; replaced by `starter_impact` slot movement** | No forward projection source exists that is both license-clean and ready-made. |

## Capture provenance

Three **real** captures are embedded (`../../screens/mobile/…`):
`trades/populated.png`, `trades/empty.png`, `league-summary/populated.png` —
all 2026-08-10/11, manifest sha `106c8e38…`.

Every other frame is a **labelled reconstruction**, drawn from source. This
follows the interim posture in [`mockups/CLAUDE.md`](../CLAUDE.md): the embed
rule and the D-056 capture freeze are in unresolved conflict, so the rule is
"embed where a capture exists, label reconstructions, never silently skip the
current pane".

`mobile/src/screens/TradesScreen.tsx` has moved **11 times** since the capture
(`586dbba` → `045c020`); the guided-first landing and the chip strip are not in
it, and there is no way to refresh it. The lab's §0 lists every commit.
