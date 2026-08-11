# LLD — P0-8 (guided-tour sign-off gate) + P0-9 (first-session test prep)

> **Binding parents:** [`hld.md`](hld.md) (authority — §2 S-39…S-46, §3 commit 11, §4 W2-TS,
> §6 rows 6 and 11, §7, §8 R6/R17, §9 LLD-7, §10.1). Where this document and
> [`plan-p0-8-9.md`](plan-p0-8-9.md) disagree, the HLD wins and the divergence is recorded in
> [§9 Deviations](#9-deviations-from-the-plan-and-the-hld).
>
> **Executed by:** build agent **`W2-TS`** — the single exclusive owner of
> `mobile/src/screens/TradesScreen.tsx` for wave 2. `W2-TS` also owns P0-2's edits to the same
> file; `lld-p0-2.md` did not exist when this document was written, so the composition contract in
> §1 is derived from [`plan-p0-2.md`](plan-p0-2.md) §Design + §Exact change list. If `lld-p0-2.md`
> exists at build time, read it first — §1's *disjointness claim* is the thing to re-check, not the
> edits themselves.
>
> **Worktree:** `ftf-p0-remediation`, branch `p0-remediation-2026-08-10`, from `origin/main @ ab9368f`.
> **`mobile/node_modules` is a symlink — never run `npm install`.**
>
> **HLD corrections already absorbed (do not re-litigate):** `screen_viewed` is *already* emitted at
> `RootNav.tsx:352` and `:376` (HLD §10.1) — plan §3.4's "missing" claim and open question **Q5**
> are **dropped**; living-memory ids are **D-026+ / G-029+**, not `D-011` / `G-013`; `s8.1` is gated
> on **beat identity** (`guideSeen['s2.2']`), never a step count (S-39); `err.burst` is **deleted**
> (S-40); **D1 is IN SCOPE** (S-42); **D2 is a client rename, no taxonomy alias** (S-41); **D3 is
> proven by a flag-pinned run during validation** (S-43); **no flag default changes anywhere**
> (S-44); `tester_allowlist` device-id currency is an **operator checklist item** (S-45).

## Contents

- [1. Composition contract with LLD-2 inside `W2-TS`](#1-composition-contract-with-lld-2-inside-w2-ts)
- [2. §P0-8 — the `s8.1` beat gate](#2-p0-8--the-s81-beat-gate)
- [3. §D1-fix — the like-first swallow](#3-d1-fix--the-like-first-swallow)
- [4. §D2-rename — `celebration_fired` → `celebration_shown`](#4-d2-rename--celebration_fired--celebration_shown)
- [5. §P0-9-validation — the procedure `W3-QA` executes](#5-p0-9-validation--the-procedure-w3-qa-executes)
- [6. §Test-mechanism — the zero-code operator recipe](#6-test-mechanism--the-zero-code-operator-recipe)
- [7. §Flows — Maestro delta](#7-flows--maestro-delta)
- [8. Gates, and the rows this LLD supplies to `W3-DOCS`](#8-gates-and-the-rows-this-lld-supplies-to-w3-docs)
- [9. Deviations from the plan and the HLD](#9-deviations-from-the-plan-and-the-hld)

---

## 1. Composition contract with LLD-2 inside `W2-TS`

`W2-TS` lands **one commit** (HLD §3 commit 11) containing P0-2, P0-8, P0-9's two client defects,
and the two one-liners inherited from P0-6/P0-7 at the `SendInSleeperButton` mount. This section
exists so the agent can stage the four sets as separate hunks without a three-way merge inside its
own head.

### 1.1 Anchors, not line numbers (HLD §8 R1)

`TradesScreen.tsx` is 6 158 lines and mutates under concurrent sessions. **Every edit in this
document is addressed by a `grep` anchor string.** No line number in this document is an
instruction; the numbers appear only as *"as of `ab9368f`"* provenance.

| # | Anchor (unique substring, verify with `grep -n`) | Owner | Region |
|---|---|---|---|
| A1 | `// s6.1 seen → S8 sign-off (tour complete)` | **P0-8** | chain effect, `s8.1` branch (`:2456`) |
| A2 | `track('celebration_fired', { beat: 'first_quickset_save' }, 'Trades');` | **D2** | `useFocusEffect` Quick-Set handoff (`:2547`) |
| A3 | `const firstLike = !getOnboardingState().celebrationsShown.first_like;` | **D1 + D2** | `decide()` like branch (`:3128-3144`) |
| A4 | `track('celebration_fired', { beat: 'first_like' }, 'Trades');` | **D2** | **two** occurrences — see §4.1 for the ordering rule |
| A5 | `<SendInSleeperButton` (deck mount, `:4713`) | inherited P0-6/P0-7 | not specced here — see `plan-p0-6.md` / `plan-p0-7.md` |

### 1.2 Disjointness from P0-2

P0-2's fifteen `TradesScreen.tsx` edits (`plan-p0-2.md` §Exact change list items 4-18) touch:
module-scope copy constants; the `useState` block beside `const [job, …]`; `handleFindTrades`;
`generateMutation.onSuccess` / `.onError`; the poll-failure branch; a new effect after the poll
effect; the league-switch reset; `handleToggleFairness`; ladder row 4 and a new row 7b; the
`deckErrorTitle` style; the mode-bar `onLayout` + `<Toast topOffset>`.

**None of those regions is A1-A4.** The nearest approach is P0-2 item 12's *"new effect after the
poll effect"*, which lands ~1 100 lines above the chain effect. The two sets are textually and
semantically disjoint; there is no ordering constraint between them inside the commit.

**One shared consequence, stated so neither half is surprised:** P0-2 deletes nothing from the
guide path, and P0-8 deletes `err_burst` — the mascot line that would otherwise have competed with
P0-2's new `trades.deck-error` card for the same failure moment (HLD §1.4, S-40). After this
commit the Trades failure moment has exactly one surface, and it is P0-2's.

### 1.3 Suggested internal order

`(1) analystScript.ts err_burst deletion` → `(2) A1 gate` → `(3) A3 D1 restructure` →
`(4) A2 + the remaining A4 rename` → `(5) P0-2's hunks` → `(6) the inherited mount props`.

Step 3 before step 4 is **load-bearing**: the D1 restructure rewrites one of A4's two occurrences,
which is what makes the second one unambiguous for a literal string replace (§4.1).

---

## 2. §P0-8 — the `s8.1` beat gate

### 2.1 The chain effect today (verbatim, `TradesScreen.tsx:2456-2461` @ `ab9368f`)

```ts
    // s6.1 seen → S8 sign-off (tour complete)
    if (ob.guideSeen['s6.1'] && !ob.guideSeen['s8.1'] && !ob.guideTourCompleted) {
      requestGuideStep(GUIDE.s8_1());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guideActive, guidedS3Pending, guidedS55Done, topCard]);
```

`ob` is bound at the top of the same effect (`const ob = getOnboardingState();`, `:2418`), after the
`if (guideActive || !guidedAvatarActive()) return;` guard at `:2417`. The `s8.1` branch is the
effect's **last** branch and the only one with no `return` after it.

The mechanism of the bug, re-verified in this worktree: under release flags `firstRun` is false
(`onboarding.trades_first` is `false`), so `s2.1` never fires, so `s2.2`/`s2.3` never fire. The
user's first like fires `s6.1` (`advance:'auto'`, `autoMs:2200`, `once:true`). Its auto-advance
writes `guideSeen['s6.1']` and sets `active: null`; `guideActive` flips, the effect re-runs, and
the `s8.1` branch is the **only satisfiable branch in the file**. Sign-off ~2.2 s after one like.

### 2.2 The edit

Replace the two lines above the `requestGuideStep(GUIDE.s8_1());` call. **Exact new condition:**

```ts
    // s2.2 (swipe coaching, ACTED ON) + s6.1 seen → S8 sign-off.
    // s2.2 is the precondition, not decoration: it is the tour's only
    // advance:'action' teaching beat, it is chained on s2.1 (⇒ firstRun ⇒
    // onboarding.trades_first), and guideSeen is durable. Without it a user
    // who saw nothing but the first-like celebration was told the tour was
    // over, having been taught one line — the P0-8 finding. The gate reads
    // product state, never a flag, so it is correct under both flag sets.
    if (
      ob.guideSeen['s2.2'] &&
      ob.guideSeen['s6.1'] &&
      !ob.guideSeen['s8.1'] &&
      !ob.guideTourCompleted
    ) {
      requestGuideStep(GUIDE.s8_1());
    }
```

**The condition, on one line, for grep/diff review:**
`ob.guideSeen['s2.2'] && ob.guideSeen['s6.1'] && !ob.guideSeen['s8.1'] && !ob.guideTourCompleted`

Nothing else in the effect changes: no new dependency (`guideSeen` is read imperatively through
`getOnboardingState()`, exactly as the three branches above it do), no `return` added, no reorder.

**`useGuide.ts` is not edited.** `stepsSeenCount` stays — it is the `steps_seen` property of
`guide_tour_completed` (`analytics_taxonomy.py:233`), which remains registered and correct.

### 2.3 Consumer audit for "`guideTourCompleted` never becomes true on the release path"

Re-grepped in this worktree. `guideTourCompleted` is read at exactly three places:
`useGuide.completeTour` (writes it), the two `TradesScreen` sites being edited here
(`:2457` chain gate, `:2466` the completion effect), and `resetGuideProgress()`
(`useOnboardingState.ts:151-153`, clears it). `SettingsScreen` reads **`guideDismissed`**, not
`guideTourCompleted`; `guidedAvatarActive()` reads `guideDismissed`. **Nothing else reads it.**

The one observable change on the release path is that `guide_tour_completed` stops firing — which
is the correct signal, because no tour is delivered there. **W3-QA must expect the release-path
`guide_tour_completed` row count to be zero**, and must not read that as a regression.

### 2.4 Behaviour matrix, as testable assertions

`R` = today's `config/features.json` release defaults. `V2` = the `onboarding-v2` flag set
(`backend/tests/fixtures/flags/onboarding-v2.json`, or the §6 experiment overlay — the two are the
same map by construction). Each row is a **binary assertion with a named verifier**; a row with no
verifier is not an assertion and does not appear.

| id | Flags | Given / When | Then (assert) | Verified by |
|---|---|---|---|---|
| **P08-A1** | R | fresh install, sign in, one league, first disposition is a **like** | `guide.avatar.*celebrate` becomes visible (s6.1 still fires — the fix must not over-gate) | `guide-no-false-signoff@release.yaml` step 5 |
| **P08-A2** | R | continuing A1, ≥ 8 s after the like | `guide.bubble` is **not visible** and no bubble replaced s6.1 | same flow, steps 6-7 (`extendedWaitUntil notVisible`, then `assertNotVisible`) |
| **P08-A3** | R | continuing A1, whole session | **zero** `guide_tour_completed` rows in `user_events` for the session | `sqlite3` on the run's seeded DB (§5.4) |
| **P08-A4** | R | continuing A1, whole session | **zero** `guide_step_shown` rows with `step='s8.1'` | same |
| **P08-A5** | R | fresh install, exhausts the deck **without** liking | no `s6.1`, no `s8.1`; `s7.1` (deck-exhausted beat) is unaffected | tier-1 smoke `06-trades-deck` stays green; no new assertion (unchanged path) |
| **P08-A6** | R | like, **then** exhaust the deck | `s7.1` still renders; still no `s8.1` | manual leg of the tier-1 run, recorded in the ledger |
| **P08-A7** | R, 2+ leagues | `s1.1` shows on the picker, then a like | still no `s8.1` (`s1.1` is not a teaching beat) | logically implied by A4; no separate flow — `s1.1` writes `guideSeen['s1.1']`, never `['s2.2']` |
| **P08-A8** | **V2** | the normal walk `pass → pass → Fix WR → Quick Set → s5.x → s5.5 "Later" → like` | `s8.1` **fires** and `onboarding__s8-1.png` is still produced | `capture/onboarding-tour@fresh.yaml` re-run after the fix (§5.2) |
| **P08-A9** | V2 | continuing A8 | exactly one `guide_tour_completed` row, `steps_seen ≥ 7` | `sqlite3` (§5.4) |
| **P08-A10** | V2 | user's **first** disposition is a like (the D1 path) | after the D1 fix, `s6.1` fires on the next like that finds a free slot, and `s8.1` follows | §3.4 assertions D1-A1…D1-A3 |
| **P08-A11** | either | user taps **"Skip tour"** at any beat | `guideDismissed` ⇒ `guidedAvatarActive()` false ⇒ the chain effect returns at its first line; nothing changes | unchanged path; `guide.dismiss-tour` already exercised by the capture flow |
| **P08-A12** | `onboarding.guided_avatar` off | passive surfaces only | the chain effect returns at its first line; no guide code runs | unchanged path |
| **P08-A13** | V2 | Settings → tour toggle off → on after a completed tour | `resetGuideProgress()` clears `guideSeen` **and** `guideTourCompleted`; the tour replays from its first beat and can sign off again | **manual** (§5.5 manual check 3) — the harness cannot drive it |

**P08-A1 + P08-A2 together are the acceptance criterion**: *a user who sees only the first-like
celebration is never told the tour is complete* — asserted under **R**, and A8/A9 assert the V2
arm did not regress. The criterion is therefore proven under **both** flag sets, which is what
S-39's "the gate reads product state, not configuration" buys.

### 2.5 `err.burst` deletion

**Entry to delete, verbatim (`mobile/src/components/analystScript.ts:106-109` @ `ab9368f`):**

```ts
  err_burst: (): GuideStep => ({
    id: 'err.burst', screen: 'Trades', pose: 'oops', advance: 'tap',
    line: "Something's broken on my end. Not your fault. Investigating.",
  }),
```

Delete the four lines. The preceding entry (`s8_1`) already ends with `}),`, and `} as const;`
follows — the deletion is a clean excision requiring no comma surgery.

- **Zero call sites**, re-verified: `grep -rn "err\.burst\|err_burst" mobile/src/` returns only the
  definition. Deletion is behaviour-preserving by construction.
- `S` is `as const`; removing a key narrows the literal type. `GUIDE` (the import alias for `S` in
  `TradesScreen.tsx`) has no `err_burst` reference, so `tsc --noEmit` is the complete proof.
- **Post-condition worth asserting once:** after the deletion every remaining entry in `S` has a
  call site (19 of 19). That is what makes the plan's §1.3 inventory table trustworthy going
  forward, and it is the positive reason for the deletion rather than merely the absence of harm.
- The design record is **not** lost: `docs/plans/onboarding-conversion/guided-avatar-script.md:110`
  keeps the reactive-only-mode paragraph that describes this line. `W3-DOCS` annotates it (§8.2).

---

## 3. §D1-fix — the like-first swallow

### 3.1 The defect, quoted at all three points of the sequence

**(a) The first disposition requests `s2.3`, which occupies the bubble slot**
(`TradesScreen.tsx:3007-3015`, inside `decide()`):

```ts
    // Guided tour: the real swipe advances the s2.2 coaching step; s2.3
    // (the provenance-chip beat) follows immediately in the freed slot.
    if (guidedAvatarActive()) {
      advanceGuideIfActive('s2.2');
      const seen = getOnboardingState().guideSeen;
      if (seen['s2.2'] && !seen['s2.3']) {
        requestGuideStep(GUIDE.s2_3());
      }
    }
```

**(b) `requestStep` returns `false` when a bubble is already active**
(`mobile/src/state/useGuide.ts:89-94`):

```ts
  requestStep: (step, handlers) => {
    if (!guidedAvatarActive()) return false;
    const ob = getOnboardingState();
    if (step.once && ob.guideSeen[step.id]) return false;
    // One bubble at a time — an active step is never preempted.
    if (get().active) return false;
```

**(c) …but the celebration is already marked consumed before the request is made**
(`TradesScreen.tsx:3128-3139`, still inside `decide()`, ~115 lines below (a)):

```ts
      const firstLike = !getOnboardingState().celebrationsShown.first_like;
      if (guidedAvatarActive()) {
        // Guided arm: s6.1 celebrate replaces the toast; the honest Apple
        // setup line (s6.2) precedes the system sheet, which opens after
        // the auto-step clears (never two overlapping surfaces).
        if (firstLike) {
          patchOnboardingState({ celebrationsShown: { first_like: true } });
          track('celebration_fired', { beat: 'first_like' }, 'Trades');
          requestGuideStep(GUIDE.s6_1());
        } else {
          setToast({ msg: 'Liked', tone: 'success' });
        }
```

**The failure:** on a user whose *first* disposition is a like, (a) runs first and puts `s2.3` in the
slot; (c) then marks `celebrationsShown.first_like = true`, fires the (currently dropped) event, and
calls `requestGuideStep(GUIDE.s6_1())` — which hits (b)'s third guard and returns `false`. The beat
is **lost permanently**: `firstLike` is false forever, so `s6.1` is never requested again,
`guideSeen['s6.1']` is never written, and — with or without P0-8's gate — `s8.1` can never fire.
The V2 tour has no ending. Note the user also gets **no feedback at all** on that like: no
celebration (swallowed) and no toast (the `else` branch was not taken).

**Scope:** V2-only. Under release flags `s2.3` is unreachable (it is chained on
`guideSeen['s2.2']`), so the slot is always free and `s6.1` always shows.

### 3.2 Mechanism chosen

Two mechanisms were available in the code:

| | Mechanism | Cost | Guarantee |
|---|---|---|---|
| **M-a** | **Do not consume the beat unless the slot was free** — call `requestGuideStep` first, and key the `celebrationsShown` write + the event off its **return value** | one boolean, no new state, no new effect dependency | `s6.1` re-arms and fires on the **next** like |
| M-b | Arm a `guidedS61Pending` state at the like site and let the chain effect request it in the freed slot, mirroring `guidedS3Pending` | new state + new effect dep + a new branch ordered *above* the `s8.1` branch | `s6.1` fires as soon as the slot frees, without a second like |

**S-42 settles this: "One condition." → M-a.** `plan-p0-8-9.md` §3.3 reaches the same conclusion
independently ("prefer the one-condition version — the chain effect is already crowded"). M-b's
residual advantage and the cost of not taking it are recorded honestly in §3.5.

`requestStep` reads only `guideSeen[step.id]` and `get().active` — never `celebrationsShown` — so
**reordering the call above the state write is safe** and changes nothing on the non-swallowed path.

### 3.3 The edit

Replace the `if (firstLike) { … } else { … }` block quoted in §3.1(c) with:

```ts
      const firstLike = !getOnboardingState().celebrationsShown.first_like;
      if (guidedAvatarActive()) {
        // Guided arm: s6.1 celebrate replaces the toast; the honest Apple
        // setup line (s6.2) precedes the system sheet, which opens after
        // the auto-step clears (never two overlapping surfaces).
        //
        // REQUEST FIRST, CONSUME ON SUCCESS (P0-9 D1). When the like is the
        // user's FIRST disposition, s2.3 was requested ~115 lines above and
        // owns the bubble slot, so requestStep refuses (useGuide.ts:93-94).
        // Marking the celebration spent before knowing that lost the beat
        // permanently: firstLike went false, s6.1 was never requested again,
        // guideSeen['s6.1'] was never written, and the tour had no ending.
        // The && short-circuits, so a non-first like still never requests.
        const shown = firstLike && requestGuideStep(GUIDE.s6_1());
        if (shown) {
          patchOnboardingState({ celebrationsShown: { first_like: true } });
          track('celebration_shown', { beat: 'first_like' }, 'Trades');
        } else {
          setToast({ msg: 'Liked', tone: 'success' });
        }
        if (!getOnboardingState().guideSeen['s6.2'] && appleAskEligible('like')) {
          setTimeout(() => {
            requestGuideStep(GUIDE.s6_2());
            setTimeout(() => maybeAskApple('like'), 2800);
          }, shown ? 2400 : 0);
        } else {
          maybeAskApple('like');
        }
```

Three substantive changes, and nothing else in the block moves:

1. `const shown = firstLike && requestGuideStep(GUIDE.s6_1());` — the request happens first; `shown`
   is `true` only when the bubble actually became active.
2. The `patchOnboardingState` + `track` pair moves **inside** `if (shown)`. The swallowed case now
   falls to the existing `'Liked'` toast, so the user always gets exactly one acknowledgement.
3. `}, firstLike ? 2400 : 0);` → `}, shown ? 2400 : 0);`. The 2400 ms exists **only** to let
   `s6.1`'s 2200 ms auto-advance clear the slot before `s6.2` is requested. After change 1,
   `firstLike` no longer means "a celebration is on screen" — it means "the celebration has not been
   consumed yet" — so leaving `firstLike` there would be a latent misreading. `shown` is the same
   condition, reused. (Recorded as a deliberate micro-extension of S-42 in §9.)

The unguided arm (the `else` of `guidedAvatarActive()`) is **untouched** except for its D2 rename;
it has no `requestGuideStep` call and therefore no swallow.

`shown`'s type is `boolean` (`boolean && boolean`); no `tsc` friction.

### 3.4 Assertions

| id | Flags | Given / When | Then | Verified by |
|---|---|---|---|---|
| **D1-A1** | V2 | user's **first** disposition is a **like** | a `'Liked'` toast appears (the user is acknowledged), `s2.3`'s bubble is unaffected, and **`celebrationsShown.first_like` stays false** | manual sim walk (§5.5 manual check 4) + absence of a `celebration_shown` row |
| **D1-A2** | V2 | continuing D1-A1, user dismisses `s2.3` and likes a second card | `s6.1` renders (`guide.avatar.*celebrate`) and a `celebration_shown {beat:'first_like'}` row lands | same walk; `sqlite3` (§5.4) |
| **D1-A3** | V2 | continuing D1-A2 | `s8.1` follows once `s6.1` auto-advances, and `guide_tour_completed` fires once | same walk |
| **D1-A4** | V2 | the **normal** walk (like is *not* the first disposition — the path `onboarding-tour@fresh.yaml` already takes) | byte-identical behaviour to today: one `s6.1`, one `celebration_shown`, one `s8.1` | `capture/onboarding-tour@fresh.yaml` re-run (P08-A8) |
| **D1-A5** | R | any like | unchanged — slot is always free, so `shown === firstLike` | `guide-no-false-signoff@release.yaml` step 5 |

### 3.5 Residual, stated rather than buried

Under **M-a**, a V2 user whose first disposition is a like and who then **never likes again** still
never sees `s6.1` and therefore never reaches `s8.1`. The beat is *re-armed*, not *rescheduled*.

This is strictly better than today (today it is lost permanently and the user gets no
acknowledgement either), it satisfies the PRD's acceptance wording ("still reaches the sign-off
eventually"), and it is the version S-42 adjudicated. **It is not a complete fix**, and the
complete fix is M-b. Recorded as a candidate `NEXT.md` row in §8.2 rather than silently absorbed —
`W3-QA` should report the swallow-then-never-like case in the validation findings so the operator
can decide whether M-b is worth a follow-up.

---

## 4. §D2-rename — `celebration_fired` → `celebration_shown`

`celebration_fired` is **not** in `ALLOWED_CLIENT_EVENTS`. Ingest is default-deny —
*"unknown types are counted + dropped, never 4xx'd"* (`analytics_taxonomy.py:10`) — so all three
call sites have been discarded since they shipped. The target name is already registered
(`analytics_taxonomy.py:76`) with a superset prop row (`:225`,
`frozenset({"beat_key", "beat"})`), so `{ beat }` survives the prop allowlist unchanged.

**No taxonomy edit. No alias (S-41). No schema change. `W0-TAX` does nothing for D2.**

### 4.1 The three call sites, before → after

**Site 1 — `useFocusEffect`, first Quick Set save (`:2541-2548`).** Unique literal; replace directly.

```ts
        patchOnboardingState({ celebrationsShown: { first_quickset_save: true } });
        track('celebration_fired', { beat: 'first_quickset_save' }, 'Trades');
```
→
```ts
        patchOnboardingState({ celebrationsShown: { first_quickset_save: true } });
        track('celebration_shown', { beat: 'first_quickset_save' }, 'Trades');
```

**Site 2 — `decide()`, guided arm (`:3135`).** **Do not edit this line on its own.** It is rewritten
wholesale by the D1 restructure in §3.3, which already emits `celebration_shown`. Landing D1 first
is what makes site 3 an unambiguous single-occurrence replace.

```ts
          track('celebration_fired', { beat: 'first_like' }, 'Trades');   // inside `if (firstLike)`
```
→ (see §3.3) `track('celebration_shown', { beat: 'first_like' }, 'Trades');` inside `if (shown)`.

**Site 3 — `decide()`, unguided arm (`:3149-3155`).** After D1 lands, the only remaining
`celebration_fired` literal in the tree.

```ts
        let likeToast = 'Liked';
        if (guidedOn && firstLike) {
          likeToast = 'First target logged. Your front office is open for business.';
          patchOnboardingState({ celebrationsShown: { first_like: true } });
          track('celebration_fired', { beat: 'first_like' }, 'Trades');
        }
```
→
```ts
        let likeToast = 'Liked';
        if (guidedOn && firstLike) {
          likeToast = 'First target logged. Your front office is open for business.';
          patchOnboardingState({ celebrationsShown: { first_like: true } });
          track('celebration_shown', { beat: 'first_like' }, 'Trades');
        }
```

### 4.2 Post-condition

`grep -rn "celebration_fired" mobile/ backend/ docs/plans/onboarding-conversion/` → **empty**
(matches in `docs/plans/audit-p0-remediation/*` and `docs/business/product/2026-08-09-mobile-ux-audit/*`
are historical prose and stay).

### 4.3 A finding this rename surfaced — 33 client event names are being dropped, not one

D2 is not the second or third occurrence of G-031; it is one of **thirty-three**. Sweeping every
`track('<name>'` literal in `mobile/src` against `ALLOWED_CLIENT_EVENTS`:

> 73 distinct client event names are emitted. **33 are absent from `analytics_taxonomy.py` and are
> counted-and-dropped:** `apple_banner_dismissed`, `calc_clear_undone`, `calc_trade_shared`,
> `celebration_fired`, `deck_regenerated`, `deck_summary_viewed`, `demo_bridge_tapped`,
> `guide_tour_reenabled`, `help_opened`, `help_read_more_tapped`, `invite_shared`,
> `match_dismiss_undone`, `notif_denied_settings_shown`, `notif_denied_settings_tapped`,
> `pick_pricing_mode_changed`, `player_menu_opened`, `prompt_deferred`, `prompt_shown`,
> `push_primer_accepted`, `push_primer_dismissed`, `push_primer_shown`, `rating_prompt_requested`,
> `stud_tax_mode_changed`, `suppression_undo_tapped`, `trade_asset_removed`,
> `trade_edit_in_calculator_tapped`, `trade_keep_side_tapped`, `trade_pin_cleared`,
> `trade_swap_suggest_opened`, `trade_swap_suggestion_picked`, `trio_entry_tapped`,
> `trio_session_started`, `untouchable_toggled`.

Commit 1 fixes `invite_shared` (S-18); this commit fixes `celebration_fired`. **31 remain.**

Two of the 31 are inside P0-9's own reading surface, and **both plan §3.4 and scope §1 assert they
are registered — they are not**:

- **`deck_regenerated`** (`TradesScreen.tsx:2563`, carries `{position, new_trades}`) — the S5 reveal
  counter. Plan §3.4 lists it under *"already registered and sufficient, no work"* and scope §1
  cites it as the signal that *"distinguishes `s5.1` from `s5.0`"*. It is dropped. **§5.3's D3 proof
  is therefore designed not to depend on it.**
- **`guide_tour_reenabled`** (`useGuide.ts:134`) — the Settings replay signal behind manual check 3.

**Neither is fixed here.** Adding names is a taxonomy change owned exclusively by `W0-TAX`, and
HLD §4 Wave 0 enumerates commit 1's names *"in full"*. Registering `deck_regenerated` would be a
one-row addition to a commit that is already a taxonomy commit and would make the S5 reveal
readable — **recommended, not assumed**; it needs the orchestrator's yes (see §9, Deviation D-4).
The full list goes to `NEXT.md` and reinforces `G-031` (§8.2).

---

## 5. §P0-9-validation — the procedure `W3-QA` executes

> **Nothing in this section changes a flag default.** It pins flags per-run through the existing
> fixture mechanism (`# flags: onboarding-v2` → `screen-capture.sh:113` →
> `sim-run.sh --flags backend/tests/fixtures/flags/onboarding-v2.json`, merged over the profile map
> at `sim-run.sh:56-68` and round-tripped through `/api/feature-flags` as a handshake at `:118-119`).

### 5.1 The flows that walk the reachable beats — reuse, do not duplicate

**Three existing capture flows, all already tagged `# flags: onboarding-v2`, cover every beat the
harness can reach.** Authoring a fourth is rejected (HLD §6 lists no such file; plan §6.2 records
that a duplicate would clone ~300 lines of hard-won timing knowledge from three documented failed
runs tuning the S2.wait window).

| Flow | Profile | Beats it walks | Command |
|---|---|---|---|
| `capture/onboarding-signin@fresh.yaml` | `fresh` | `s0.1`, `s0.2`, `s0.err-notfound`, `s0.err-down` | `mobile/scripts/screen-capture.sh --flow capture/onboarding-signin@fresh.yaml` |
| `capture/onboarding-leaguepicker@two-leagues.yaml` | `two-leagues` | `s1.1` (needs ≥2 cached leagues — `LeaguePickerScreen.tsx:116`) | same, that flow |
| `capture/onboarding-tour@fresh.yaml` | `fresh` | `s2.wait`, `s2.1`, `s2.2`, `s2.3`, `s3.1`, `s3.2`, `s4.1`, `s5.1`\|`s5.0`, `s5.5`, `s6.1`, `s6.2`, `s8.1` | same, that flow |

`s7.1` is walked by neither: it needs a deck exhausted to a nondeterministic length (the capture
matrix's ruling D wants a `/__test__/pin/deck_size` pin first). It is **not** a P0-9 blocker —
record it as un-walked, do not author a pin for it in this batch.

### 5.2 Per-beat pass/fail criteria

For every beat, four checks — **(a) reachable, (b) renders, (c) advances, (d) analytics land**:

- **(a) reachable** — the flow arrives at the beat inside its declared timeout without a
  conditional-branch miss. A `runFlow: when:` block that silently did not fire is a **fail**, not a
  skip: check the flow's screenshot manifest for the frame, not just the exit code.
- **(b) renders** — the bubble is present (`guide.bubble`), the pose matches the script table
  (`guide.avatar.<pose>`), and where the step declares a `target`, the spotlight resolves —
  i.e. the ring is drawn, which happens only when `frame` is non-null (`AnalystGuide.tsx:79-86`).
  A beat whose target failed to register renders with **no scrim at all**; that is visible in the
  screenshot and is a **fail**.
- **(c) advances** — by its declared mechanism (`tap` / `action` / `cta` / `auto`) with no dead end:
  `guide.step-x` present on every bubble, `guide.dismiss-tour` present. **A beat that cannot be
  left is a fail regardless of how well it renders** (script §1: never trap).
- **(d) analytics land** — a `guide_step_shown` row with the right `step` **and** a
  `guide_step_advanced` (or `_skipped`) row for it. All three names are registered
  (`analytics_taxonomy.py:78`), so absence means the beat did not fire, not that the event was
  dropped.

**Per-beat expectations (V2 arm):**

| Beat | Specific check | Known status entering validation |
|---|---|---|
| `s0.1`, `s0.2` | `s0.2` advances on the **real submit** (`SignInScreen.tsx:215`), not on a tap | captured ✓ |
| `s0.err-notfound`, `s0.err-down` | both branches at `SignInScreen.tsx:312` reachable; neither traps | captured ✓ |
| `s1.1` | needs ≥2 leagues; **confirm a single-league user is not left waiting on a beat that cannot fire** | captured under `two-leagues` ✓ |
| `s2.wait` | the `running`/`isPending` window is real, **not only harness-injected latency** — the flow injects 3 s on `/api/trades/generate` + 8 s on `/api/trades/status*` to buy the window | captured ✓ — **report the caveat**, do not fix (plan R3) |
| `s2.1` | fires the moment the deck lands | captured ✓ |
| `s2.2` | spotlight resolves to `trades.card-body`; advances on a **real disposition** | captured ✓ (button path — see manual check 1) |
| `s2.3` | fires immediately in the freed slot; spotlight resolves to `trades.provenance-chip`; **the chip is actually rendered** (needs `tradesFirstOn`) | captured ✓ |
| `s3.1` | trigger arithmetic: first **pass** at ≥2 swipes, else ≥3 | captured ✓ |
| `s3.2` | **both** CTAs: `Fix <pos> →` routes with `onboardingReturn:true`; **`Not now` snoozes and does not trap** | accept path captured ✓; **dismiss path is manual check 2** |
| `s4.1` | fires on the onboarding-mode Quick Set mount | captured ✓ |
| **`s5.1`** | **the payoff beat — see §5.3. This is the gate.** | **never observed in this repo** |
| `s5.0` | the honest-null branch | captured ✓ |
| `s5.5` | leverage order from `nextUnrankedPosition`; `Rank <next> →` routes; **`Later` does not trap** | captured ✓ (dismiss path is walked by the flow) |
| `s6.1` | fires on first like; **plus the swallow case** | captured ✓ on the normal walk; swallow case = D1-A1…A3 |
| **`s6.2`** | Apple setup line + the 2400/2800 ms handoff to the system sheet | **frame missing** — the conditional block did not fire; determine **why** (a verified/account-only fixture user skips the scene entirely) and record it as *not applicable* or as a defect, never as "flaky" |
| `s7.1` | un-walked (see §5.1) | out of scope for this pass |
| `s8.1` | fires **only after `s2.2`** post-fix; `completeTour()` follows | P08-A8/A9 |

### 5.3 The `s5.1` proof (D3) — what makes `fresh > 0`

**The computation, verbatim.** The snapshot is taken on the Quick-Set→Trades focus
(`TradesScreen.tsx:2532-2535`):

```ts
      pendingRegenRef.current = {
        position: pos,
        prevIds: new Set(deck.map((c) => c.trade_id)),
      };
```

and the count + branch happen when the forced job completes (`:2557-2575`):

```ts
    const pending = pendingRegenRef.current;
    if (!pending || job?.status !== 'complete') return;
    pendingRegenRef.current = null;
    const fresh = deck.filter((c) => !pending.prevIds.has(c.trade_id)).length;
    track(
      'deck_regenerated',
      { position: pending.position, new_trades: fresh },
      'Trades',
    );
    if (guidedAvatarActive()) {
      requestGuideStep(
        fresh > 0 ? GUIDE.s5_1(fresh, pending.position) : GUIDE.s5_0(pending.position),
      );
      setGuidedS55Done(pending.position);
      return;
    }
```

`fresh` = **cards in the regenerated deck whose `trade_id` was not in the deck at Quick-Set-entry
time.** The branch is a single ternary at a single call site: **there is no path on which
`fresh > 0` and `s5.0` renders.** That fact is what makes the proof design below sound.

**Why it has never rendered.** `capture/onboarding-tour@fresh.yaml` walks the eight tier rungs with
**empty** saves — the loop taps `quick-set.save-btn` ten times with zero chips selected, and with
zero selected the primary composes as a Skip (`QuickSetTiersScreen.tsx:626-660`). The board is
unchanged, the forced regen re-prices with identical numbers, `fresh === 0`, and the flow lands on
`s5.0` every time. `s5-1.png` is absent from `screens/mobile/onboarding/` for that reason.

**Seeded state that makes `fresh > 0`.** The `fresh` profile seeds `qa_standard` with
`"rankings": null, "tiers": null, "anchors": null` — **zero** user board — in a 10-team 1QB PPR
league with two generated-roster opponents. So the *pre*-walk deck is priced entirely on consensus.
Assigning **any** real chips creates a user board where none existed, which is the largest board
delta available on this fixture. The lever is therefore: **select chips instead of skipping.**

**Deterministic selection IS possible.** `QuickSetTiersScreen.tsx:409` renders
`` testID={`quick-set.chip.${item.id}`} `` — player-id templated, so the ids themselves are not
selectors. But Maestro matches ids as regexes and supports positional `index:`, and
`capture/quick-rank.yaml:100-107` already uses exactly this pattern on the sibling screen for the
same reason:

```yaml
- tapOn:
    id: "quick-set.chip.*"
    index: 0
- tapOn:
    id: "quick-set.chip.*"
    index: 1
- tapOn:
    id: "quick-set.chip.*"
    index: 2
```

Tapping the bare regex three times without `index` would toggle the **same** first chip on/off/on —
that is the trap `quick-rank.yaml`'s comment records, and the reason `index` is mandatory here.

`testid-lint.sh` passes without an allowlist entry: the linter reduces `quick-set.chip.*` to the
base `quick-set.chip` and greps `` testID={`?["'`]*quick-set.chip `` over `mobile/src`, which the
template literal at `:409` matches. **Do not add a `testid-lint-allow.txt` line** — that file is
not in `W2-TS`'s ownership and no entry is needed.

**The variant walk (amendment to `capture/onboarding-tour@fresh.yaml`, §7.2).** In the rung loop,
select the first three chips *before* each save. Rung 1 is Tier 1, so this promotes three players
into the top tier on a board that previously had none — a maximal, not marginal, delta.

**The proof, and its falsification — designed without `deck_regenerated`** (which is dropped, §4.3):

| Observed | Conclusion | Action |
|---|---|---|
| `guide.avatar.*celebrate` at the S5 slot **and** a `guide_step_shown {step:'s5.1'}` row **and** `onboarding__s5-1.png` shows a bubble reading *"There it is. **N** new trades…"* with N ≥ 1 | **s5.1 is proven.** D3 closed. | file the frame; record N in the ledger |
| `guide.avatar.*oops` (`s5.0`) | **Inconclusive, NOT a defect.** `s5.0` renders *iff* `fresh === 0`, so this says the walk failed to move the board — not that `s5.1` is broken. | re-run selecting more chips per rung (index 0-5) or on more rungs; if it still lands on `s5.0`, escalate to the manual fallback below |
| **Neither** pose appears and no `guide_step_shown` row for `s5.0` or `s5.1` inside the flow's 180 s wait | **The S5 reveal is broken** — the slot was occupied, `pendingRegenRef` was cleared, or the forced job never reached `complete`. | **this is the most important defect in the set** — surface to the operator immediately (HLD R17) |
| `celebrate` pose but **no** `s5.1` row, or a bubble with a wrong/absent number | **`s5.1` is broken.** | fix, per §5.6 |

**Manual fallback, if the flag-pinned variant still cannot produce `fresh > 0`.** Do **not** fake it
(HLD §9 LLD-7). Use the harness's existing interactive mode, which stops the flow before a named
shutter and leaves the simulator sitting in that state:

```
mobile/scripts/screen-capture.sh --flow capture/onboarding-tour@fresh.yaml --interactive --state s4-1
```

That lands on the onboarding-mode Quick Set with the `onboarding-v2` flags pinned and the `fresh`
profile seeded. Hand-select real players across several rungs, save, and photograph the S5 bubble
on the return to Trades. File the screenshot as `s5-1.png` with a ledger note stating it was
hand-walked and why.

### 5.4 Reading the analytics during the run

The sim run seeds a dedicated SQLite file and exports it to Flask
(`seed_ui_test_db.py:1698`, `DEFAULT_OUT_DIR = "data/ui-test"`), so every `user_events` row the run
produces is queryable locally with no server access and no prod data:

```
sqlite3 data/ui-test/fresh.db \
  "SELECT event_type, properties FROM user_events
    WHERE event_type IN ('guide_step_shown','guide_step_advanced','guide_step_skipped',
                         'guide_tour_completed','guide_tour_dismissed','celebration_shown')
    ORDER BY id;"
```

(Confirm the column names against `docs/data-dictionary.md` § `user_events` before running; the
table exists and is documented — this LLD does not change its shape.)

That query is the verifier for **P08-A3, P08-A4, P08-A9, D1-A2** and for check (d) on every beat.
For the release-flag flow the profile file is the same `fresh.db`.

### 5.5 Manual checks the harness cannot make

Four, all recorded verbatim in `TEST_LEDGER.md` with a pass/fail verdict:

1. **A real finger swipe advances `s2.2`.** The deck's PanResponder rejects Maestro's synthetic
   directional swipe (documented in the capture flow's own comment), so the harness always
   exercises the button path. `decide()` is shared by both (`TradesScreen.tsx:3006-3015`), so this
   is a harness limit, not a product risk — but it is asserted once by hand.
2. **`s3.2` "Not now" and `s5.5` "Later" do not trap.** The capture flow walks accept on `s3.2`.
3. **Settings → tour toggle off → on replays from the first beat** (`resetGuideProgress`,
   full-replay semantics, `useGuide.ts:66-70`) — **P08-A13**. Note `guide_tour_reenabled` is
   dropped (§4.3), so this check is visual only.
4. **The D1 swallow path** — first disposition is a like (D1-A1…A3). No flow drives it: the capture
   flow's first two dispositions are passes by construction, and authoring a fourth tour flow is
   rejected (§5.1). Walk it by hand from `--interactive --state s2-2`.

### 5.6 Fix policy — what gets fixed here, what gets deferred

| Finding class | Disposition |
|---|---|
| A beat that **traps** the user (no `guide.step-x`, no `guide.dismiss-tour`, no advance path) | **Fix in this commit.** Script §1's binding principle; a trap is a P0 by definition. |
| **`s5.1` broken** (celebrate fires with no `s5.1` row, or a wrong/absent count) | **Fix in this commit** (HLD R17 / S-43) — it is the payoff beat and nothing else in the tour is worth testing if it is broken. |
| **`s5` reveal broken entirely** (neither branch fires) | **Stop and surface to the operator before any further validation.** Then fix. |
| **`s6.2` never fires** | **Diagnose, then classify.** If the fixture user is verified/account-only the scene is correctly skipped ⇒ record *not applicable*. Anything else ⇒ defect; fix only if it is a trap, else `NEXT.md`. |
| **`s2.wait` only renders under injected latency** | **Do not fix.** Record in the findings: "13 beats" overstates the real-world tour by one for a user on a warm pre-gen (plan R3). |
| **`s7.1` un-walked** | Defer — needs a `/__test__` deck-size pin (capture-matrix ruling D). `NEXT.md`. |
| **Copy, ordering, or pacing opinions** | Out of scope. P0-9 is validation, not a redesign. |
| **`deck_regenerated` / `guide_tour_reenabled` / the other 29 dropped names** | **Not fixed here** — taxonomy is `W0-TAX`'s exclusive file. `NEXT.md` + `G-031`. |
| **FeedbackFAB overlap (audit A-34), swipe-vs-button harness limit, Quick Set payoff copy** | Explicitly out of scope (plan §3.3). |

---

## 6. §Test-mechanism — the zero-code operator recipe

> **Zero code. Zero deploys. Zero flag-default changes.** The overlay path already exists and is the
> `onboarding_v2_rollout` precedent. Every claim below was re-verified against
> `backend/experiments.py`, `backend/server.py` and `mobile/src/api/flags.ts` in this worktree.
>
> **`CRON_SECRET` lives in `secrets.local.env`** (project root, gitignored). Read it from there.
> Never paste it into chat, a doc, or a commit.

### 6.0 How it works, in four verified sentences

`GET /api/feature-flags` (`server.py:17269-17332`) returns `{flags, experiments, configs}`, where
`flags` is the **global** `flags_dict()` — an experiment never mutates it. Per-unit values ride in
`configs`, populated by `experiments.resolve_for_unit` from the matched variant's `client_config`
verbatim (`experiments.py:320-342`; `create_experiment` stores
`variants_json=json.dumps(spec["variants"])` at `:509` and `validate_spec` never inspects
`client_config`). The client merges every `configs[*].flags` **over** the global map
(`mobile/src/api/flags.ts:44-51`) and caches the **merged** result, so the treatment survives
offline boots and reconciles on the next fetch. The server resolves the device unit from the
`X-Device-Id` header the client already sends (`server.py:17293`, `flags.ts:28`), **so the overlay
reaches a signed-out device** — which matters, because `onboarding.landing` is a pre-auth surface.

### 6.1 Step 0 — the branch that decides everything else

```bash
curl -s "https://fantasy-trade-finder.onrender.com/api/admin/experiments" \
  -H "X-Cron-Secret: $CRON_SECRET"
```

Look for any **`onboarding`-layer** experiment with status `running` or `paused` — in practice
`onboarding_v2_rollout`.

| Branch | Condition | Do this |
|---|---|---|
| **A** | No onboarding-layer experiment is running or paused | §6.2 as written. |
| **B** | `onboarding_v2_rollout` is running **and** `GET /api/admin/experiments/onboarding_v2_rollout` shows a treatment `client_config.flags` that already matches §6.3's map | **Create nothing.** Confirm the device id (§6.5) and verify with §6.4. Zero writes. |
| **C** | An onboarding-layer experiment is running with a different or partial overlay | **Read the warning below**, capture its full spec, `stop` it, then §6.2. |

> ⚠ **`stopped` is a one-way door.** `_LEGAL_EDGES` (`experiments.py:76-81`) has **no
> `stopped → running` edge**. Restarting a stopped experiment means
> `POST /api/admin/experiments/<key>/revise` (a new draft version — `experiments.py:585-589`)
> followed by a `transition` to `running`, **and its metrics reset**. Before stopping anything,
> save its full row: `GET /api/admin/experiments/onboarding_v2_rollout` returns `variants_json`,
> `targeting_json`, buckets and metric — that response **is** the restore spec.
>
> **Why stopping is unavoidable in branch C:** `validate_spec(for_launch=True)` rejects a launch
> whose buckets overlap any *running or paused* experiment in the same layer
> (`experiments.py:473-484`), and the onboarding layer's incumbent occupies `[0, 10000)`. Pausing
> does **not** help — `_running_and_paused` counts paused rows. Revising the incumbent instead is
> also wrong: `_running_and_paused` excludes only by **key**, so v1 and v2 of the same key would
> both be `running`, and `resolve_for_unit` would write both into `configs[key]` with last-one-wins.

### 6.2 Create (branch A or C)

```bash
curl -s -X POST https://fantasy-trade-finder.onrender.com/api/admin/experiments \
  -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
  -d '{
    "key": "trades_first_operator_test",
    "layer": "onboarding",
    "unit_type": "device",
    "bucket_start": 0,
    "bucket_end": 10000,
    "targeting": {"is_tester_allowlist": true},
    "hypothesis": "Operator-only walkthrough of the built trades-first onboarding (P0-9). n=1, not a powered test.",
    "exposure_surface": "onboarding",
    "primary_metric": "activation_rate",
    "variants": [
      {"name": "control", "weight_bp": 0},
      {"name": "treatment", "weight_bp": 10000, "client_config": {"flags": {
        "onboarding.v2": true,
        "onboarding.guided_avatar": true,
        "onboarding.landing": true,
        "onboarding.trades_first": true,
        "onboarding.quickset_prompt": true,
        "onboarding.apple_save_moment": true,
        "onboarding.league_autoskip": false,
        "landing.try_before_sync": true
      }}}
    ]
  }'
```

Every field is validated; each choice below is forced by `validate_spec` (`experiments.py:421-486`)
and was checked against the code, not assumed:

| Field | Value | Why it must be this |
|---|---|---|
| `layer` | `"onboarding"` | must be in `RESERVED_LAYERS` (`:74`) |
| `unit_type` | `"device"` | `layer == "onboarding"` **requires** `device` — `onboarding_layer_requires_device_unit` (`:470-472`). It is also the only unit that exists pre-sign-in, which the landing surface needs. |
| `bucket_start` / `bucket_end` | `0` / `10000` | `0 <= start < end <= 10000` (`:432`). Full range + allowlist targeting = "the allowlisted device is always in". |
| `targeting` | `{"is_tester_allowlist": true}` | the only `_CONFIG`-source attribute, registered for **both** unit types (`ATTR_REGISTRY:53`). Every `_USERS` attribute would fail `attr_unit_incompatible` on a device unit (`:465-467`). |
| `variants` | `control` `0` bp, `treatment` `10000` bp | ≥2 variants, unique names, weights summing to exactly 10000 (`:435-441`). 0/10000 ⇒ a targeted unit is **always** treatment — the `onboarding_v2_rollout` / `aggregate_tier_labels` shape. |
| `primary_metric` | `"activation_rate"` | must be in `METRIC_CATALOG` (`:65-69`, `:457-459`). `activation_rate` is the honest choice for an onboarding walkthrough — and the five `PFO_GUARDRAILS` are auto-attached either way (`:489-491`). |
| `exposure_surface` | `"onboarding"` | required and non-empty (`:468-469`). |
| `client_config` | the flag map | passes through **verbatim** — `validate_spec` inspects `model_overlay` only. |

**The overlay map, key by key.** It mirrors `backend/tests/fixtures/flags/onboarding-v2.json`, so
the operator's device gets byte-identically the configuration every capture flow was validated
against:

| Key | Value | Note |
|---|---|---|
| `onboarding.v2` | `true` | master kill-switch; already `true` globally. Listed so the spec is self-documenting. |
| `onboarding.guided_avatar` | `true` | already `true` globally. Same reason. |
| `onboarding.landing` | `true` | sole trigger for S0 (`SignInScreen.tsx:110`). |
| `onboarding.trades_first` | `true` | **the point of the test.** Latches `firstRun`; gates the entire S2 block, the ProvenanceChip, and the first-run auto-generate. |
| `onboarding.quickset_prompt` | `true` | sole trigger for S3 (`TradesScreen.tsx:2476`). |
| `onboarding.apple_save_moment` | `true` | sole trigger for S6.2 (`:2682`). |
| `onboarding.league_autoskip` | **`false`** | **deliberately off.** With it on, a single-league user skips the picker and `s1.1` becomes unreachable. |
| `landing.try_before_sync` | `true` | **not an `onboarding.*` key, and `false` globally — and it is required.** It is the launch pairing `config/features.json`'s `_comment_onboarding` records: without it `/api/session/demo` 404s and the landing's demo link is a dead end. |

Keys deliberately **absent**: `onboarding.share_sheet`, `onboarding.rank_routing`,
`onboarding.demo_bridge`, `onboarding.guided_layer`, `onboarding.keep_warm` — all `false` in the
validated fixture, and `guided_layer` in particular is *superseded* by `guided_avatar` (the passive
surfaces are the non-guided arm).

### 6.3 Launch

```bash
curl -s -X POST https://fantasy-trade-finder.onrender.com/api/admin/experiments/trades_first_operator_test/transition \
  -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
  -d '{"to": "running", "version": 1, "override_underpowered": true,
       "reason": "n=1 operator-only rollout, not a powered test"}'
```

`draft → running` is a legal edge (`:77`) and re-runs `validate_spec(for_launch=True)`, which is
where a layer overlap would surface as a 400 with `layer_overlap: buckets [0,10000) collide with
<key> v<n>` — i.e. branch C was missed at step 0. `override_underpowered` is accepted by the route
signature (`server.py:7150-7155`) but **is not consulted by `transition()`** in this build — the
underpowered gate is not implemented on this path. It is harmless and documents intent; keep it.

### 6.4 Verify before touching the phone (do not skip)

```bash
curl -s "https://fantasy-trade-finder.onrender.com/api/feature-flags" \
  -H "X-Device-Id: <the device pseudo-id, WITHOUT the 'device:' prefix>"
```

**Expect** `experiments` to contain `"trades_first_operator_test": "treatment"` and `configs` to
contain the overlay map. This one unauthenticated call proves, in a single shot, that: the
allowlist matched, the layer has a salt (`_evaluate` returns `None` when
`_load_cache()["layers"]` has no row for the layer — `experiments.py:303-305` — and a
salt-less layer is the one silent failure mode with no error anywhere), the bucket resolved, the
targeting passed, and the variant carries the config.

If `experiments` is empty: the device id is wrong or not on the allowlist (§6.5), or the layer has
no salt — the CRON-gated `POST /api/admin/experiments/reseed-layers` (`server.py:21046-21054`)
re-derives the reserved-layer salts, and **refuses once any experiment has assigned a unit**, so run
it *before* launching, never after.

Then **force-quit and reopen the app** on the allowlisted device. The flag store fetches at boot and
on the ≥30-min foreground refetch; a warm app keeps the cached merged map until then.

### 6.5 Operator checklist (S-45 — checklist items, not build tasks)

- [ ] **Device-id currency.** `config/tester_allowlist.json` currently holds
      `["device:dev_loc-mrpy6qog-2t72t6", "313560442465169408"]`. Device pseudo-ids are minted by
      `getDeviceId()` (`mobile/src/api/client.ts:119-145`) and stored in **SecureStore**, so a
      reinstall that clears the keychain rotates the id. **Confirm the current id and add it if it
      changed** — one line in a git-deployed JSON file (Render does **not** apply `render.yaml`
      envVars to a dashboard-created service, observed 2026-07-19, which is why the file exists).
      Entries are `device:<id>`; the header in §6.4 takes the id **without** the prefix.
      *If in doubt, §6.4 is the test: it returns empty until the id is right.*
- [ ] **No onboarding-layer collision** — §6.1 step 0 run and its branch chosen.
- [ ] **If branch C:** the incumbent's full spec saved before stopping it (one-way door).
- [ ] **Layer salt present** — proven by §6.4, not assumed.
- [ ] **`experiments.engine` is on** — `true` in `config/features.json`; a global flag, not part of
      the overlay.
- [ ] `CRON_SECRET` read from `secrets.local.env`, never pasted into chat.
- [ ] **AASA-independent — no dependency on P0-3.** This test needs no deep link, no universal
      link, and no `growth.invite_join_link` flip. Entry is a normal cold app launch on the
      allowlisted device. Nothing in §6 waits on CDN propagation (HLD R2), and P0-3 can ship,
      slip, or roll back without touching this recipe.
- [ ] **The build must be on the device first.** The overlay turns on flags the *client* reads; the
      P0-8/D1/D2 fixes must be in the installed build or the walk validates the old code.

### 6.6 Rollback and widening

**Rollback — one call, no deploy, no build, no App Store round trip:**

```bash
curl -s -X POST https://fantasy-trade-finder.onrender.com/api/admin/experiments/trades_first_operator_test/transition \
  -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
  -d '{"to": "stopped", "version": 1, "reason": "operator test complete"}'
```

Every non-allowlisted user is byte-identical throughout, because the global `flags_dict()` never
changed. The allowlisted device keeps its cached merged map until the next `/api/feature-flags`
fetch (boot or ≥30-min foreground refetch) — force-quit to reconcile immediately. If branch C was
taken, restore the incumbent now: `revise` with the saved spec, then `transition` to `running`.

**Widening later** (not part of P0-9): `POST .../revise` with `is_tester_allowlist` dropped from
`targeting` and the weights rebalanced — the documented `onboarding_v2_rollout` graduation path,
requiring no client or server code change. Widening beyond the operator's own device is a
**bright-line decision** and needs an explicit operator yes.

---

## 7. §Flows — Maestro delta

Two files. Both conform to `mobile/.maestro/README.md`'s flow-authoring laws 1-23; the laws each
one turns on are named inline.

### 7.1 NEW — `mobile/.maestro/flows/guide-no-false-signoff@release.yaml`

The batch's **only true regression test**: it fails on the unfixed tree and passes on the fixed one
(HLD §6 row 6).

```
appId: com.fantasytradefinder.app
# tc: TC-GUIDE-NO-FALSE-SIGNOFF
# profile: fresh
# flags: release
tags: [smoke, onboarding, guide]
```

> The `@release` suffix names the **flag fixture**, not a profile — unlike the `capture/` naming
> convention (`<screen>[@profile].yaml`). This file lives under `flows/`, whose runner reads the
> `# profile:` and `# flags:` headers explicitly, so there is no ambiguity; the filename is fixed by
> HLD §6. Add a one-line header comment saying so, because the next reader will assume otherwise.

**Legs:**

1. `launchApp: {clearState: true, clearKeychain: true, stopApp: true}` — **law 6**: the react-query
   cache is persisted, and this flow depends on a genuinely first-run `ftf_onboarding_state`
   (`guideSeen` empty, `celebrationsShown.first_like` false).
2. `extendedWaitUntil visible: signin.username-input` → `tapOn` → `inputText: "qa_standard"` →
   **assert the typed username before submitting** (**law 10**) → `tapOn: signin.continue-btn`.
   Under `release`, `onboarding.landing` is off, so **no S0 bubble appears** and no tap-catcher
   preamble is needed here.
3. `extendedWaitUntil visible: leagues.row.*` → `tapOn: leagues.row.*`. The `fresh` profile has
   exactly one league, so `s1.1` (which needs `cached.length >= 2`) does **not** fire.
4. Settle before the tab tap (**law 8** — tab taps race #244 launch routing): wait on the Rank
   surface's own header control, then `tapOn: tab.trades`. Then the conditional first-visit
   outlook-sheet dismissal (`runFlow when visible: outlook.save-btn`), copied from
   `flows/smoke/06-trades-deck.yaml`, plus a bounded conditional `guide.tap-catcher` probe
   (**law 9**).
5. `extendedWaitUntil visible: trades.find-btn` → `tapOn: trades.find-btn` →
   `extendedWaitUntil visible: trades.card-top` (60 s — the poll backoff is 800→4000 ms). Under
   `release`, `firstRun` is false, so there is **no** first-run auto-generate; the deck must be
   asked for. `trades.find-btn` is not unlock-gated (`TradesScreen.tsx:4235-4241`).
6. `scrollUntilVisible {element: {id: trades.like-btn}, direction: DOWN}` → `tapOn: trades.like-btn`.
   **Law 2**: the disposition row sits below the card, so the scroll is mandatory, not cosmetic.
7. **`extendedWaitUntil visible: guide.avatar.*celebrate` (30 s)** — asserts `s6.1` **still fires**.
   This is the guard against over-gating and it is why P08-A1 exists as a separate assertion.
8. **`extendedWaitUntil notVisible: {id: "guide.bubble"} timeout: 8000`** — **the regression
   assertion.** `s6.1` is `advance:'auto', autoMs:2200`, and `AnalystGuide` returns `null` when no
   step is active (`AnalystGuide.tsx:71`), so `guide.bubble` disappears when the slot empties. Under
   the bug, `s8.1` (`advance:'tap'`, no auto) takes the slot ~2.2 s after the like and its bubble
   **persists indefinitely** — this wait times out and the flow fails. Under the fix nothing
   replaces `s6.1` and the wait returns.
9. `assertNotVisible: {id: "guide.bubble"}` — belt and braces after the wait.
10. `takeScreenshot` for the run record (**law 23**: a green run is not a good capture — eyeball it).

**Why the assertion is precise rather than lucky:** under `release`, after a first like, `s6.1` is
the *only* beat that can be showing — `s6.2` needs `onboarding.apple_save_moment` (off), `s7.1`
needs an exhausted deck, `s2.*`/`s3.*`/`s5.*` need `trades_first`/`quickset_prompt` (off), and
`s1.1` needs two leagues. So "no bubble after `s6.1`" is exactly "no false sign-off".

**No `testID`s are added or renamed** by this flow. Every selector already exists:
`signin.username-input`, `signin.continue-btn`, `leagues.row.*`, `tab.trades`, `outlook.save-btn`,
`trades.find-btn`, `trades.card-top`, `trades.like-btn`, `guide.avatar.*`, `guide.bubble`,
`guide.tap-catcher`. `testid-lint.sh` passes unchanged (`guide.avatar.*` and `leagues.row.*` are
already in `testid-lint-allow.txt`).

**Banned patterns avoided:** no fixed `sleep`, no coordinate tap, no `tapOn: text:` — the three the
linter enforces.

### 7.2 MODIFIED — `mobile/.maestro/capture/onboarding-tour@fresh.yaml`

Two amendments; **nothing else in the file moves** (it carries timing knowledge from three
documented failed runs and every change to it is a regression risk).

**(1) S8.1 precondition comment.** At the S8.1 block, whose comment today reads *"the chain effect
(:2455-2459) then requests S8.1"*, record that `s8.1` now **additionally requires
`guideSeen['s2.2']`** — so this flow's own S2.2 step is a **precondition** of its S8.1 step, not an
ordering coincidence, and removing or reordering the S2.2 leg would break the S8.1 leg for a reason
that has nothing to do with S8.1. Comment only; no command changes.

**(2) The D3 populated-walk variant** (S-43). In the rung loop, select three chips before each save:

```yaml
- repeat:
    times: 10
    commands:
      - runFlow:
          when:
            visible:
              id: "quick-set.save-btn"
          commands:
            # D3 (P0-9): REAL selections, not empty saves. With zero chips the
            # primary composes as a Skip (QuickSetTiersScreen.tsx:626-660), the
            # board never moves, fresh === 0 and S5 always lands on s5.0 — which
            # is why s5-1.png has never existed. Chip ids are player-id
            # templated, so they are selected POSITIONALLY off the shared regex;
            # tapping the bare regex three times would toggle the SAME chip
            # on/off/on (the trap capture/quick-rank.yaml:88-97 records).
            - tapOn:
                id: "quick-set.chip.*"
                index: 0
            - tapOn:
                id: "quick-set.chip.*"
                index: 1
            - tapOn:
                id: "quick-set.chip.*"
                index: 2
            - tapOn:
                id: "quick-set.save-btn"
            - waitForAnimationToEnd
```

Notes the build agent must not lose:

- The taps are **inside** the existing `runFlow: when: visible: quick-set.save-btn` guard, so once
  the walk finishes and the screen navigates back to Trades the remaining iterations are no-ops —
  the loop still self-terminates and still cannot hang the cell.
- A rung with fewer than three chips makes the extra `index` taps **misses, not failures** — the
  same tolerance `quick-rank.yaml` relies on.
- The existing S5 block already screenshots **both** branches conditionally
  (`celebrate → onboarding__s5-1`, `oops → onboarding__s5-0`), so **no change is needed there**:
  after this amendment the celebrate branch is the one expected to fire, and `s5-0.png` simply is
  not re-taken (the existing library frame stays).
- `testid-lint.sh` passes: `quick-set.chip.*` reduces to base `quick-set.chip`, which the linter
  finds at `QuickSetTiersScreen.tsx:409`. **Do not add an allowlist entry.**
- This makes the flow's `s5.5` leg **more** reliable, not less: `setGuidedS55Done(pending.position)`
  runs on both branches, so the S5.5 CTA still arms.

**Rejected:** a permanent second cell `onboarding-tour@fresh--populated.yaml`. It is not in HLD §6's
inventory, it would duplicate ~300 lines of timing knowledge, and the amendment above obtains the
missing frame inside the flow that already owns the tour.

### 7.3 Files this LLD must NOT touch

`mobile/.maestro/04-tabs-navigation.yaml` and `mobile/.maestro/flows/smoke/09-league.yaml` are P0-7's
must-pass-**unmodified** waiver proof (HLD §6). `capture/leagues@fresh.yaml` is P0-5's control.
`capture/trades.yaml` belongs to P0-2's half of this same commit — `W2-TS` edits it under
`lld-p0-2.md`'s spec, never under this one. `mobile/scripts/testid-lint-allow.txt` needs no entry
and is not owned here.

---

## 8. Gates, and the rows this LLD supplies to `W3-DOCS`

### 8.1 Gates

- `python3 -m pytest backend/tests/ -q` — **no backend file is touched**; run anyway (concurrent
  sessions write to this repo).
- `cd mobile && npx tsc --noEmit` — clean. The `err_burst` deletion narrows `S`'s literal type and
  `tsc` is the complete proof that nothing referenced it. **`mobile/node_modules` is a symlink —
  never run `npm install`.**
- `bash mobile/scripts/testid-lint.sh` — clean. No `testID` added or renamed; no allowlist entry.
- `grep -rn "err_burst\|err\.burst" mobile/src/` → empty; `grep -rn "celebration_fired" mobile/` →
  empty.
- **Simulator gate: tier 1** for the batch (HLD §4 Wave 3), one run covering all seven findings:
  full smoke suite (11 flows) + `guide-no-false-signoff@release.yaml` +
  `capture/onboarding-tour@fresh.yaml` under the `onboarding-v2` fixture + the other six new/changed
  feature flows. **Capture refresh: none required for P0-8/P0-9's release path** — deleting an
  unreferenced script entry and tightening a boolean changes no pixels there; run
  `mobile/scripts/screen-freshness.sh` to confirm nothing else drifted. The V2 captures are re-run
  as **P0-9 validation evidence**, and `s5-1.png` is a **new** library frame.
- **Pre-fix control run required** for `guide-no-false-signoff@release.yaml`: run it on the unfixed
  tree and record that it **fails**. A regression test that never observed the bug proves nothing
  (HLD R5).
- Evidence: `living-memory/TEST_LEDGER.md` + `qa/sim-runs/last-sim-run.json`
  (`githooks/pre-push` enforces; install with `git config core.hooksPath githooks`).

### 8.2 Rows supplied to `W3-DOCS` (wave 3 — **no build agent edits `docs/` or `living-memory/`**)

| Doc | Row |
|---|---|
| `docs/runbook.md` | **New subsection: "Operator-only onboarding test (`trades_first_operator_test`)"** — §6 in full: the step-0 branch and the **one-way `stopped` door**, the create + transition calls, the `/api/feature-flags` pre-flight verification, the eight-key overlay with the two non-obvious values (`landing.try_before_sync` must be present; `onboarding.league_autoskip` must stay `false`), the device-id currency check, the one-call rollback, and the note that the recipe is **AASA-independent**. This knowledge currently exists only inside a feedback status doc for a *different* experiment (`docs/feedback/items/279-aggregate-tier-labels/status.md`). |
| `docs/plans/onboarding-conversion/guided-avatar-script.md` | (a) `err.burst` is **deleted from the implementation** — the reactive-only-mode paragraph at `:110` describes a line that was never wired and no longer exists in `analystScript.ts`; keep the design intent, mark it unbuilt. (b) **S8.1 now requires the S2.2 beat** (`:104-108`) — the sign-off is gated on swipe coaching having been delivered and acted on. |
| `docs/config-reference.md` | **Only if** the operator's device id is added to `config/tester_allowlist.json` — note the addition. **No flag row changes**: no default is flipped, no key added to `FLAG_KEYS`. |
| `living-memory/DECISIONS.md` | **D-032** (id per HLD §7, **not** `D-011`) — beat-identity gate over step-count gate. Record the three reasons the count option fails: `stepsSeenCount` is in-memory zustand and resets on launch; `guideSeen` only records `once:true` steps, so a real tour that ended at `s5.5` records 7 keys while an empty release-flag session with two leagues records 3; any `N` is a magic number that silently changes meaning the next time a beat is added, removed, or has its `once` flag edited. Add **D-033 (candidate)**: "consume the celebration only when the bubble slot was free" (D1's request-first-consume-on-success idiom) — allocate the next free id if `W3-DOCS` finds `D-032` taken. |
| `living-memory/GOTCHAS.md` | **G-031** (id per HLD §7, **not** `G-013`) — a client `track()` name absent from `backend/analytics_taxonomy.py` is counted and dropped in silence. **Strengthen the HLD's "third occurrence" wording: the sweep in §4.3 found 33 dropped names out of 73.** Name `celebration_fired` (fixed here), `invite_shared` (fixed in commit 1), and `deck_regenerated` + `guide_tour_reenabled` (**not** fixed — both are asserted as registered by `plan-p0-8-9.md` §3.4 and `scope-p0-8-9.md` §1 and are not). |
| `living-memory/NEXT.md` | (1) **Register the remaining 31 dropped client event names** (§4.3 list), starting with `deck_regenerated` — until it lands the S5 reveal's `new_trades` count is unreadable in production. (2) **D1 mechanism M-b** — re-arm `s6.1` through the chain effect so a swallowed celebration fires without needing a second like (§3.5). (3) `s7.1` has never been captured — needs a `/__test__/pin/deck_size` pin (capture-matrix ruling D). (4) `s2.wait` may be unreachable for real users on a warm pre-gen — decide whether the beat earns its place. |
| `living-memory/CHANGELOG.md` | At ship, inside the batch's dated H2: the guided tour no longer announces completion after a single first-like celebration; the first-like celebration is no longer lost when the user's first disposition is a like; `celebration_shown` starts landing in `user_events` for the first time. |
| `living-memory/TEST_LEDGER.md` | Owned by `W3-QA`: the tier-1 run, the **pre-fix control** result for `guide-no-false-signoff@release.yaml`, the four manual checks in §5.5 verbatim with verdicts, the D3 outcome (celebrate + N, or the escalation), and whether `s5-1.png` was harness-captured or hand-walked. |
| `docs/api-reference.md`, `living-memory/LLD.md`, `docs/architecture.md`, `living-memory/HLD.md`, `docs/cross-client-invariants.md`, `docs/glossary.md`, `docs/data-dictionary.md`, `living-memory/DEPENDENCIES.md` | **n/a.** No route, no schema, no shared constant, no new domain term, no dependency, no convention shift — one boolean tightened inside an existing effect, one orphaned data entry deleted, one client string renamed to an already-registered name. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a — do not edit.** The audit is a dated artifact. Its P0-8 count ("nine of fifteen unreachable") is superseded by `plan-p0-8-9.md` §1.3 (**16 of 20**); the correction lives in the plan. |

---

## 9. Deviations from the plan and the HLD

| # | Deviation | From | Rationale | Needs a yes? |
|---|---|---|---|---|
| **D-1** | The D1 edit also substitutes `shown` for `firstLike` in the `s6.2` handoff delay (`}, shown ? 2400 : 0);`) | `plan-p0-8-9.md` §3.3 describes D1 as touching only the consume; S-42 says "one condition" | It **is** the same condition, reused. The 2400 ms exists solely to let `s6.1`'s 2200 ms auto-advance clear the slot; after the fix `firstLike` no longer means "a celebration is on screen", so leaving it there encodes a false premise for the next reader. Behaviour on every non-swallowed path is unchanged. | No — micro-extension, recorded here |
| **D-2** | The swallowed-like case now shows the `'Liked'` toast (the `else` branch is reached when `shown === false`) | plan §3.3 says "leave the `else` toast path untouched" | The path is untouched; it is merely now *reachable* in a case where the user previously got **nothing at all** — no celebration and no toast. Silence on a like is a worse defect than the one being fixed. | No |
| **D-3** | Plan §3.4 / scope §1's claim that `deck_regenerated` is registered is **false**, so the D3 proof is redesigned to depend on `guide_step_shown {step}` and the rendered pose instead | plan §3.4, scope §1 line 31 | Verified: `grep -n deck_regenerated backend/analytics_taxonomy.py` → empty. The `fresh > 0` ternary is a single call site, so `s5.0` rendering **proves** `fresh === 0` and cannot be confused with a broken `s5.1`. The redesigned proof is strictly stronger and needs no taxonomy change. | No |
| **D-4** | **Recommendation, not action:** register `deck_regenerated` in commit 1 | HLD §4 Wave 0 enumerates commit 1's names "in full" | One `ALLOWED_CLIENT_EVENTS` row + one `CLIENT_EVENT_PROPS` row (`{position, new_trades}`) on a commit that is already the taxonomy commit; it makes the S5 reveal readable in production, which is the number the trades-first hypothesis turns on. **Not done here** — `analytics_taxonomy.py` is `W0-TAX`'s exclusive file. | **Yes — orchestrator + `W0-TAX`** |
| **D-5** | The operator recipe gains a **step 0** (running-onboarding-experiment branch) and a **§6.4 pre-flight verification** that the plan's §3.2 does not have | plan §3.2 / R6 | R6 names the collision but not that `stopped` is a **one-way door** (`_LEGAL_EDGES` has no `stopped → running`), nor that pausing does not help (`_running_and_paused` counts paused rows), nor that a salt-less layer fails **silently** in `_evaluate`. Branch B may also mean the test needs **zero** writes. All four are load-bearing for an operator running this against prod. | No — additive rigour |
| **D-6** | Q5 (`screen_viewed`) is **dropped**, not answered | plan §9 Q5, scope §1's ⚠ waiver | HLD §10.1: `screen_viewed` is already emitted at `RootNav.tsx:352`/`:376` for every route including tab switches, is in `ALLOWED_CLIENT_EVENTS` **and** in `NON_INTENT_EVENTS`. Time-to-first-value and the picker→Trades drop-off are readable today; P0-9's A6 is satisfiable now. **Tell the operator explicitly** — it removes the dependency the test was said to hang on. | No |
| **D-7** | Living-memory ids are `D-032` / `G-031`, not the plan's `D-011` / `G-013` | plan §7, scope §4 | HLD §10.4: root `CLAUDE.md`'s "next ID" columns are stale; the real last ids are `D-024` and `G-026`. Five plans copied the same wrong numbers. | No |
| **D-8** | `s5-1.png` is a **new screen-library frame**, so the "capture delta: none" line in scope §3 is narrowed to "none **for the release path**" | scope §3 | Deleting an unreferenced entry and tightening a boolean changes no release-path pixels, which is what that line meant. The V2 run legitimately adds one frame the library has never had. | No |
