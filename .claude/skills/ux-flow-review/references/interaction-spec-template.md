# Interaction spec — <feature>

<!--
Template for ux-flow-review Mode B. Copy it to docs/plans/<slug>/interaction-spec.md
(feedback item: docs/feedback/items/<id>-<slug>/interaction-spec.md). The area PM folds
the filled spec into the PRD; ux-lead does not edit the PRD.

RULE: every section is answered or waived with a reason in the Waivers table.
Silence is not a waiver. States follow references/state-standard.md; the checks
behind each section are in references/rubric.md.
-->

**Feature / PRD:** <path> · **Area PM:** <key> · **Date:** YYYY-MM-DD · **Author:** ux-lead
**Flags:** <key — default today> · **P16 triggers:** (a) entry · (b) tab/IA · (c) deep link · (d) interrupt · (e) new screen states

## 1. Problem and evidence

- What the user is trying to do, and where it fails today.
- Evidence, each labelled **observed** (verified in code or on TestFlight), **reported**
  (feedback ID) or **hypothesis**, with N stated:
  - …

## 2. Flow

```
Entry: <where the user is> → <control>
1. <Screen> — user does <X>
   decision: <condition A> → 2 · <condition B> → 4
2. …
Exit: <terminal action> → lands on <Screen>; Back from there → <Screen>
Failure paths:
- network or timeout at step <n> → <state>
- server refusal (<error code>) → <state>
- signed out / no league / flag off → <state>
```

## 3. Entries and deep links

| Entry | Screen and position | Shown when | Flag |
|---|---|---|---|
| | | | |

| Deep link | `V2_SCREENS` key and path | Signed out | No league | Flag off |
|---|---|---|---|---|
| | | | | |

Push or inbox kinds that land here (`resolveNotificationTarget`): <kinds, or none>.
Screen role (verified in `RootNav.tsx` / `TabNav.tsx`): tab root · tab-stack push · root-stack push · modal.

## 4. States

| Screen | State | Trigger (code or condition) | What it says | Action | Exemplar |
|---|---|---|---|---|---|
| | First-run | | | | |
| | Empty — nothing yet / filtered / nothing qualifies / not applicable | | | | |
| | Loading (and how it ends) | | | | |
| | Error — recoverable | | | | |
| | Error — not recoverable | | | | |
| | Offline | | | | |
| | Flag-off | | | | |

## 5. Interrupts

| Surface | `InterruptSurface` id and priority | Trigger | Defers to | During the tour hold | Events |
|---|---|---|---|---|---|
| | | | | | |

Or: none — this feature adds no surface, banner, modal, coach mark or guide step.

## 6. Placement

| Control | Next to | Reachable without scrolling? | Sibling precedent | Label (verb) |
|---|---|---|---|---|
| | | | | |

## 7. Seams

| Seam | Other side (area, files) | Errors the other side raises | How they surface here |
|---|---|---|---|
| | | | |

## 8. Flag-off behaviour

- Flag(s) and default:
- What a user with the flag off sees (must be today's app):
- How byte-identity is pinned (guard name, or the code-walk to write):

## 9. FeedbackFAB (#188)

Root-stack push (mounts one, `aboveTabBar={false}`) · tab-stack screen (mounts none) ·
modal, sheet or onboarding (exempt). Pinned bottom bar: calls `setPinnedBottomBarHeight` — yes / no / n/a.

## 10. TestFlight checklist steps

One line each: `N. [flag <key> on|off] [first-run | onboarded] <Tab> → <Screen> → <action>. Expect <exact result>. Fail if <the regression>.`

1. …

## 11. Reviews needed

- `design-lead` — visuals change? yes / no
- `onboarding-pm` — anything before first value, or tour content? yes / no
- `analytics-lead` — new events or event values? yes / no
- `models-lead` (through `head-bizops`) — a state that explains model output? yes / no
- The PM on the other side of each seam: <keys, or none>

## Waivers

| Section | Waived because |
|---|---|
| | |
