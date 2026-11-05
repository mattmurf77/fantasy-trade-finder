# Screen-state standard

> **Proposed for `docs/design/components.md` (owned by `design-lead`); until housed there,
> this file is the review standard.** It reaches `design-lead` through `head-product`;
> `ux-lead` does not send it directly. It specifies what each state must say and do, not
> how it looks — visuals stay with `design-lead` and Chalkline.
>
> Line numbers verified on `origin/main` at `678834ab` (2026-10-15). Re-open each at the
> reviewed sha before citing it. Paths are relative to `mobile/src/` unless they start
> with `mobile/`, `docs/`, `backend/` or `living-memory/`.

## The honest-state principle

Every state answers the same three questions truthfully:

1. **Name the real reason.** Say why the screen looks the way it does, using a value the
   app actually holds.
2. **Never fabricate.** No invented diagnosis, no padded list, no number you can't stand
   behind, no cause you can't prove.
3. **Offer the real lever, and only a real one.** If the user can change the outcome,
   give that action. If they can't, don't offer a button that implies they can.

The exemplar is `components/presentation/HonestEmptyState.tsx:7-30`. Its header explains
why: when no trade clears the bar for both sides, the screen shows nothing rather than a
weaker suggestion, because a confidently wrong trade is the most damaging error in a
league that sees every offer. The approved lab named a blocking player that no API
response carries, so the shipped state shows only levers read from real values. Its copy
builder renders the suppression note only when there is a real count
(`utils/tradePresentation.ts:337-366`, the null branch at :358-362).

`HonestEmptyState` is the exemplar of the principle, **not a component to reuse**. It is
the Trades "nothing qualifies" pivot behind `trades.presentation_v2`, used only by
`screens/TodaysTradeScreen.tsx:200`, and its props are trade-specific.

The counterpart for "no lever exists": `screens/LeagueSummaryScreen.tsx:3190-3200` — a
non-Sleeper league gets one row explaining why season outlook is missing, with no retry,
because there is nothing the user can do and a retry would imply there is.

## Copy rules — every state

- Chalkline voice: plain, dry, a peer rather than a tutor. No exclamation marks, no hype,
  no emoji (`docs/design/design-system.md:15`; `docs/design/brand.md:58`, `:62`; the voice
  charter in `living-memory/BRAND.md`). This standard checks that copy is true and
  actionable, not its wording.
- Say what happened, then what to do. One primary action, labelled with its verb; add
  more levers only when each is real (`HonestEmptyState` offers up to three; the fairness one only when it applies).
- Numbers only when real (`utils/tradePresentation.ts:358-362`).
- Don't claim a cause you can't prove. #420 replaced a misleading timeout explanation
  with one neutral line, now `TIMEOUT_MESSAGE` (`api/client.ts:292`).
- An honest message needs an honest data path. #164: Trends told users to keep ranking
  while most ranking flows never wrote the history it read. Review the query behind a
  state, not just its copy.

## First-run

- **When:** the user hasn't yet done what the screen depends on — no real league (the
  `no_league` sentinel, `navigation/RootNav.tsx:439-457`), no swipe yet
  (`firstSwipeDone`, `state/useOnboardingState.ts:18`), an unranked board.
- **Must show:** the next step toward first value and the one action that takes it;
  progress when the unlock has several steps.
- **Must not:** show a zero-state that reads as broken; stack interrupts (rubric I5); add
  a step before first value without `onboarding-pm`.
- **Exemplars:** `components/SkeletonTradeCard.tsx:5-9` and its status line at :17 (the
  first-run deck placeholder that replaced the manual "Hit 'Find a Trade' to start" empty
  state);
  `navigation/TabNav.tsx:728-739` (a first-run user lands on Trades, where the guide is
  scripted); `components/LeagueProgressModule.tsx:9-16` (one card owns every unlock —
  #229/#230/#234).
- **Review check:** name the first-run condition in code (flag plus state field). Every
  TestFlight step for it says "fresh install" or "already onboarded".

## Empty — typed by reason

Four reasons, four different messages. Find out which one applies before judging copy.

| Reason | Say | Lever | Exemplar |
|---|---|---|---|
| **Nothing yet** — the user hasn't acted | What will appear, and what fills it | The action that fills it | `components/LeagueProgressModule.tsx` (#229); #159's "No players for this tier" save label |
| **Filtered to nothing** | That the filter hid everything, naming the filter | Change or clear the filter | `screens/UsageTrendsScreen.tsx:478-486` (copy per ownership filter) |
| **Nothing qualifies** — the system checked and refused | That it checked, and that nothing cleared the bar | The real levers, plus keeping things as they are | `HonestEmptyState` with `emptyStateCopy`. #189: relaxed results are allowed only when labelled as relaxed |
| **Not applicable** — offseason, unsupported league, data that doesn't exist | The condition, and when it changes if it does | None, if none exists | `screens/UsageTrendsScreen.tsx:430-436` (in-season only); `screens/LeagueSummaryScreen.tsx:3190-3200`; #422 names the unsupported slots instead of "Unsupported roster slots" (`backend/win_now_service.py:53`) |

- **Must not:** call a loading list empty. `components/PlayerPickerModal.tsx:332-346`
  shows a spinner while the fetch runs because "No players match." would be false then.
- **Must not:** render nothing where a section is expected, without a reason —
  absence reads as a bug (`screens/LeagueSummaryScreen.tsx:3190-3192`). A spec may choose
  "renders nothing" on purpose: `EvenerRows` with no candidates
  (`docs/design/components.md:99`), `LeagueProgressModule` for one-team leagues (:103).
- **Visual spec:** the `EmptyState` row in `docs/design/components.md:121` (heading,
  dim body, one button). No shared mobile component implements it (Gaps).

## Loading

- **When:** a request or job is running and there is nothing to show yet. With cached
  data, show it and refetch quietly (`state/queryClient.ts:10-17`).
- **Must show:** a skeleton where the layout is known (cards, lists); a spinner for a
  short wait of unknown shape; for a long job, a line saying what is happening —
  `SkeletonTradeCard`'s status line, or `screens/WinNowScreen.tsx:192`, where the
  refresh button itself reads "Loading season projections…".
- **Must end.** Every loading branch reaches success, empty or error. #420 made Win Now
  one bounded attempt: loading ends on any terminal failure, Back stays usable, and an
  explicit Refresh starts a new attempt (`docs/feedback/items/420-win-now-loading/prd.md`
  R-1, R-4).
- **Must not:** spin forever; block Back; shimmer (static by design,
  `components/SkeletonTradeCard.tsx:7-9`); explain a delay with a cause you can't prove.
- **Exemplars:** `screens/UsageTrendsScreen.tsx:420`;
  `components/PlayerPickerModal.tsx:341-346` (spinner plus "Loading players…").
- **Guard:** `mobile/tests/check-win-now-recovery.js` runs the bounded recovery on fake
  time.
- **Visual spec:** the `Spinner` row, `docs/design/components.md:106`.

## Error

Decide first: recoverable (network, timeout, 5xx) or not (a refusal, an unsupported
case, a permission).

- **Recoverable must show:** what failed in plain words and a retry that re-runs the same
  request — `components/home/HomeHub.tsx:287-304`, `screens/UsageTrendsScreen.tsx:421-429`.
- **Not recoverable must show:** the reason and the real next step, or no action at all.
- **Seam errors surface where the user is, with their fix:**
  - `verification_required` (403) → `ApiError.isVerificationRequired`
    (`api/client.ts:187-197`) → one central listener (:219-229, :637-646) →
    `VerifyAccountBanner` (`navigation/RootNav.tsx:624-626`) → Sleeper verification.
    Screens don't map this error themselves.
  - `espn_auth_required` (403) → `isEspnAuthRequired` (`api/client.ts:198-209`) → ESPN
    sign-in again.
  - An expired session → `setOnSessionExpired` (`api/client.ts:231-240`) routes
    account-only users to sign-in instead of stranding them on failing screens.
  - Platform link sheets: "Couldn't reach <platform> — try again shortly."
    (`components/PlatformLinkSheet.tsx:239`).
  - An unroutable link → `Main` plus a toast, never a silent no-op
    (`utils/deepLinks.ts:448`).
- **Must not:** swallow a failure; show raw codes; offer retry on a refusal; lose what the
  user typed (`mobile/tests/check-feedback-capture.js`: a draft was cleared before its
  save was confirmed); leave a control dead after a failed write
  (`mobile/tests/check-swipe-failure-recovery.js`).
- **Guards:** the two above, `check-win-now-recovery.js`, `check-espn-wrong-account.js`.

## Offline

- **What exists:** NetInfo drives TanStack Query's online state (`mobile/App.tsx:232-245`),
  so active queries refetch on reconnect (`state/queryClient.ts:19-21`, :28). Two
  offline write queues exist, analytics and live draft picks; a third must copy their
  contract (`api/README.md:27`).
- **What doesn't:** an app-wide offline indicator (Gaps). Offline reaches the user as each
  screen's error or loading branch.
- **Must show:** for reads, the error state with a connection hint and a retry
  (`components/home/HomeHub.tsx:291-293`); for writes, either a queue built on the shared
  contract or a visible failure that keeps the input.
- **Must not:** report success for a write that didn't land.
- **Review check:** trace which branch the screen renders while a query waits for the
  network. If it is a loading branch with no end until reconnect, that is a finding under
  "Loading must end". Without a TestFlight result, label it a hypothesis and add the step
  (airplane mode, open the screen, expect the error state).

## Flag-off

- **When:** any change behind a flag.
- **Must:** keep the flag-off path byte-identical to today's app. Routes register
  unconditionally and the flag gates the entry (`navigation/CLAUDE.md:19`); a stale link
  to a flag-off route lands on an honest unavailable state
  (`screens/RookieRanksScreen.tsx:84-86`; Usage Trends, `utils/deepLinks.ts:127-129`). A
  tab is decided once at mount from an imperative read, so a mid-session flag change can't
  move the bar (`navigation/TabNav.tsx:718-724`).
- **Precedents:** `navigation/RootNav.tsx:263-275` (`SettingsRoute` mounts one component
  or the other; flag off mounts exactly today's); `state/useInterruptCoordinator.ts:53-55`
  (flag off is a passthrough); `mobile/tests/check-avoid-positions.js:22-23`;
  `mobile/tests/check-inline-home.js` and `mobile/tests/check-presentation-v2.js` (headers
  explain why byte-identity is the whole safety claim).
- **Must not:** render an entry and no-op it (the first risk in the
  `check-presentation-v2.js` header); read a tab flag with a hook that revalidates.
- **Review check:** name the guard that pins byte-identity, or write the code-walk showing
  the off branch untouched.

## Gaps (as of `678834ab`)

- **No shared state primitive.** `components/chalkline/` exports Badge, Button, Card,
  Icon, Meter, Text and TickLabel. No generic empty, loading, error, skeleton or offline
  component exists under `components/` (checked with `git grep`); each screen builds its
  own. `HonestEmptyState` is trade-specific; `SkeletonTradeCard` is the deck's;
  `RookieScopeEmpty` (`components/RookieScopeControl.tsx:126-131`) is shared, but only
  across rookie-scoped surfaces.
- **`docs/design/components.md` has no states section.** The nearest material: the
  `EmptyState` row (:121) under Feedback & status (:114); the `Spinner` row (:106) under
  Meters & progress (:87); the input error style (:110); honest-empty notes inside other
  rows (:72, :99, :103). Those say how a piece looks. Nothing says when a screen-level
  first-run, loading, error or offline state applies, or what it must say.
- **No app-wide offline indicator.**

These go to `design-lead` (the spec) and `head-eng` (a shared primitive, if wanted)
through `head-product`. This standard proposes no component.

## Per-screen check (rubric section 3)

One row per screen × state in the verdict or the spec:

| Screen | State | Trigger in code | What it says | Action | Evidence (guard, file:line or TestFlight step) |
|---|---|---|---|---|---|
| | First-run | | | | |
| | Empty (reason) | | | | |
| | Loading | | | | |
| | Error (recoverable / not) | | | | |
| | Offline | | | | |
| | Flag-off | | | | |

A state that can't occur gets "n/a" with the reason (for example, no flag).
