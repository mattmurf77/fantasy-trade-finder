# Plan — #384 the manual calculator becomes the merged trade surface

**Status:** draft for operator review. Nothing built. **Four decisions (§5) gate the build.**
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

## 4. Proposed sequencing

| Wave | Content | Why here |
|---|---|---|
| **W1** | Layout only: two columns, outlook collapsible + league/team dropdowns beneath, the four-button row, remove/add buttons, utility row and subnav hidden | Independently shippable and visually verifiable; no tour dependency |
| **W2** | ✕ → decline-reason **overlay**; platform-aware single send button; end-of-deck "back to calculator" + "find a trade without <player> pinned" | Behavior, each piece separately testable |
| **W3** | The interstitial suppression gate | Prerequisite for W4; touches many surfaces, wants its own scope block |
| **W4** | The tour itself, compressed to budget, with receipts | Depends on every control above existing and on W3 |

## 5. Four decisions before a build agent starts

1. **Does the ✕ overlay change apply only to this page, or everywhere `decline_reasons` renders?**
   Ruling 1 is written against the calculator. The shipped inline-tile form is live on the deck. Two
   presentations of one mechanism is a real cost; one presentation is a change to a surface this
   round was scoped to leave alone.
2. **What does "Include Players" toggle *mean* against the engine?** The report says a trade can be
   found with no players selected. Is the toggle "may my roster players be used as outbound
   assets", or "restrict the search to the assets on the canvas"? These produce different requests.
3. **Which of the three calculator modes gets this?** `live` (no league), `demo`, `league`. League
   and team dropdowns and a platform-aware send button only mean something in `league`. #310 is
   explicit that the manual calculator must not be locked behind a league — so what does the page
   look like in `live` mode?
4. **Is the tour for first visit only, or re-runnable?** The report says "first visit (including
   current testers)". Current testers already have guide state; re-showing needs either a version
   bump or a deliberate reset, and FR-E9's v1-upgrader release cap interacts with it.

## 6. Not addressed by this plan

The report's closing expectation — *"when the user makes a decision, the find a trade feature works
as is, the next trade card comes up automatically"* — conflicts with ruling 8, which adds an
end-of-deck state with a back-to-calculator button. Both are true at different moments (auto-advance
between cards; a summary when the deck is exhausted), but the tour copy has to be honest about
which the user is about to see.
