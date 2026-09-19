# Plan — #384 the manual calculator becomes the merged trade surface

**Status:** **ALL FIVE WAVES BUILT** (see [`status.md`](status.md)). Kept as the plan of record;
§6b's working assumption was built to and still wants a confirming yes/no.
Rulings and scope: [`status.md`](status.md).

---

## 1. What exists today

| Piece | Where | Note |
|---|---|---|
| `TradeCalculatorScreen` | `mobile/src/screens/TradeCalculatorScreen.tsx`, 1,083 lines | Three modes — `live` / `demo` / `league` — behind a mode switch |
| `InLeagueCalculator` | `mobile/src/components/InLeagueCalculator.tsx`, 1,382 lines | Mounted only by the screen above, only in `league` mode |
| Existing controls | `calc.find-a-trade`, `calc.clear-btn`, `calc.verdict`, `calc.partner-change`, `calc.partner-collapsed`, `calc.partner-summary.<id>`, `calc.lineup-impact`, `calc.starter-impact` | **A Find-a-Trade button already exists on this page** |
| The Analyst | `mobile/src/components/AnalystGuide.tsx` + `analystScript.ts`; mounted once in `RootNav` above the nav tree | Guided-onboarding v2 |

**The partner-collapse behavior #380 asks for is partly built already** — `calc.partner-collapsed`
and `calc.partner-change` exist. Confirm what they do before rebuilding them.

## 2. Layout, per the report

Top to bottom, and **the whole trade-calc section must fit in the frame**:

1. **Outlook** — collapsible section; the window pops on hitting **Change**. (`trades.outlook-receipt.change` is the existing analogue.)
2. **League and Team** — their own dropdowns *underneath* the collapsible section, side by side. This is #333.
3. **The two teams as two vertical columns**, side by side — not the stacked rows shipping today. Same select/see-players behavior.
4. **Bottom action row, four controls, in-frame:**

| Position | Width | Control |
|---|---|---|
| Left | 40% | **Find a Trade** |
| Left-middle | 30% | **Include Players** (toggle) |
| Middle | 15% | **Clear** |
| Right | 15% | **✅** (like / queue) |

Plus, per ruling 4: **Remove** and **Add a player** as explicit buttons on the player rows.
Per rulings 6 and 7: **no utility row, no three-tab subnav** on this page.

**The 15% cells are the layout risk.** A 15%-wide cell on a 375pt screen is ~56pt minus padding.
That is at or under the 44pt tap-target floor once inset, and a text label will not fit — hence
"✅" for the like control. Clear is the one to watch: it needs a label or a recognizable glyph, and
the Chalkline rules forbid emoji as icons, so ✅ itself needs to resolve to a real icon.

## 3. The tour — the constraint nobody has priced yet

The report writes fifteen prose beats. They cannot ship as written. `analystScript.ts` is governed
by a **copy budget enforced in CI** by `mobile/tests/check-guide-script.js`:

| `advance` | Budget |
|---|---|
| `auto` | 12 words, and `autoMs ≥ words/4.17×1000 + 800` |
| `action` | 16 words |
| `tap` | 20 words |
| `cta` | 16 words + button labels ≤ 4 words, at most one primary |

And every new `n`-prefixed step must declare **four** things: retirement (`retireAfter`, or
`'never'` with a written reason on the same line), a display cap, an `adoptionEvent`, and a degrade
contract (`degradeLine`, or `degrade:'suppress'`, or a line with no deixis).

**So the real tour work is compression, not writing.** Step 11 alone — acknowledging the Clear
button became the X, explaining that X records the decision to tailor future trades, and that the
check behaves as before — is three beats at ≤20 words each, not one paragraph.

**Retirement receipts are client-side only.** A receipt wired to a server-fired analytics event
never fires, which the script file calls out as *worse than none*. Any new receipt this tour needs
(e.g. "the user hit Find a Trade from the calculator") must be recorded at the real local moment
via `recordGuideReceipt`, in the same change as the step that retires on it.

**Ruling 10 needs a mechanism, and it does not exist yet.** "Mute other interstitials and analyst
prompts during the tour" means a suppression gate that the quick-set prompt card, the outlook
receipt, the Apple session-2 banner, the diff banner, the adaptation moment and the suppression
note all consult. Today each decides independently. This is the single largest hidden cost in the
report and should be its own work item.

## 4. Proposed sequencing — SUPERSEDED by §7 (kept for the reasoning)

| Wave | Content | Why here |
|---|---|---|
| **W1** | Layout only: two columns, outlook collapsible + league/team dropdowns beneath, the four-button row, remove/add buttons, utility row and subnav hidden | Independently shippable and visually verifiable; no tour dependency |
| **W2** | ✕ → decline-reason **overlay**; platform-aware single send button; end-of-deck "back to calculator" + "find a trade without <player> pinned" | Behavior, each piece separately testable |
| **W3** | The interstitial suppression gate | Prerequisite for W4; touches many surfaces, wants its own scope block |
| **W4** | The tour itself, compressed to budget, with receipts | Depends on every control above existing and on W3 |

## 5. The four decisions — RULED, 2026-08-22

| # | Question | Ruling |
|---|---|---|
| 1 | ✕-overlay scope | **Just this version of the calculator.** The deck keeps the shipped inline Value/Fit/Neither tiles; the overlay presentation is local to this page |
| 2 | What "Include Players" means | **The search must include the players on the canvas.** ON ⇒ the canvas assets are required in any returned trade. OFF ⇒ the finder is unconstrained by the canvas (the report's "we can find a trade without any players selected") |
| 3 | Which mode | **This replaces the manual calc tab and lives within the league calc. Demo calc is removed** — "it's pointless" |
| 4 | First-visit or re-runnable | **Re-runnable**, via a **"Show me around"** link in the **top right** of the page |

**Added in the same ruling:** the tour **auto-starts the moment the user lands on the manual calc
page** — because its first beat is what carries them to the league version.

## 6. Two findings that change how ruling 3 gets built

### 6a. "Demo" names two unrelated things. Only one is being deleted.

`git grep` finds `demo` across sixteen files, and they are **two separate systems**:

| | What it is | Disposition |
|---|---|---|
| **Demo calculator mode** | `CalcMode = 'demo'`, the seeded mock dual-board league in `data/tradeCalcMock.ts`; `demoEvaluation` / `demoSuggested` / `demoAddOns` in `TradeCalculatorScreen` | **This is what "remove the demo calc" means.** Delete |
| **Demo *session*** | `/api/session/demo`, `useSession.isDemo`, the SignIn "try before you sync" path, flags `landing.try_before_sync` and `onboarding.demo_bridge`, the `trades.demo-bridge` conversion surface | **Do not touch.** This is open-access onboarding |

They share a word and nothing else. A build agent told to "remove the demo calc" without this
distinction can plausibly delete the try-before-signin path. Named here so it cannot happen.
Also in scope for the deletion, and easy to miss: `mobile/tests/check-picker-pick-filter.js`
asserts against demo-mode behavior, and `PlayerPickerModal` / `TradeSide` / `tradeCalcMath.ts` /
`shareLinks.ts` / `api/calc.ts` all carry demo branches.

### 6b. Ruling 3 collides with #310, and with the tour's own first step

> **RULED 2026-08-22 — own tab for now ([D-151](../../../living-memory/DECISIONS.md), closes Q-028).** The working assumption below is the decision: `In league` | `Real values`, two tabs. Kept as written for the reasoning.

`TradesScreen.tsx:4944` states the current architecture's intent outright:

> *"Calculator (manual trade builder, demo data) is always reachable — **it needs no league**."*

That is deliberate, and **#310 is the report that asked for it** — *"we should not lock the manual
calculator behind trades."* Folding the manual calculator into the league calculator locks it
behind having a league, which is the opposite. `mode: 'league'` is only offered when
`hasLeague` is true (`TradeCalculatorScreen.tsx:150-155`).

The tour points the same way: *"the first step brings them to the league version"* — the user
cannot be brought **to** the league version unless they started somewhere that is not it.

**Working assumption, stated so it can be corrected rather than discovered mid-build:** the mode
switcher becomes **two** tabs, `Manual` | `In league`, with `demo` deleted. The rich spec in §2 is
the **In league** surface. `Manual` survives as the league-free entry point that #310 requires and
that the tour's first beat starts from. Everything else in this plan is unaffected by that choice;
only this paragraph is.

## 7. Sequencing, revised

| Wave | Content |
|---|---|
| **W0** | Delete demo calculator mode (per §6a — the mode, never the session) |
| **W1** | Layout: two columns, outlook collapsible + league/team dropdowns beneath, four-button row, remove/add buttons, no utility row, no three-tab subnav, "Show me around" top-right |
| **W2** | ✕ → decline-reason overlay (this page only); platform-aware single send button; end-of-deck "back to calculator" + "find a trade without <player> pinned"; the Include-Players contract from ruling 2 |
| **W3** | The interstitial suppression gate — prerequisite for W4, wants its own scope block |
| **W4** | The tour: compressed to the copy budget, auto-start on landing, re-entry via "Show me around", receipts wired to real local writes |

## 8. Not addressed by this plan

The report's closing expectation — *"when the user makes a decision, the find a trade feature works
as is, the next trade card comes up automatically"* — conflicts with ruling 8, which adds an
end-of-deck state with a back-to-calculator button. Both are true at different moments (auto-advance
between cards; a summary when the deck is exhausted), but the tour copy has to be honest about
which the user is about to see.
