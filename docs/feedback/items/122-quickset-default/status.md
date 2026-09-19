# #122 — Quick set should be the default ranking method

**Status:** built (branch `trade-engine-v2`), pending QA
**Type:** UX default change (mobile-only routing; no data migration)
**Date:** 2026-07-17

## Change

`mobile/src/navigation/TabNav.tsx` (`RankStackNav`): the Rank stack's initial
route for a user with **no stored `rankingMethodPref`** is now
`QuickSetTiers` unconditionally:

- Before: null pref → `RankHome` chooser (or `QuickSetTiers` only when
  onboarding flag `onboarding.rank_routing` was on — it is OFF in prod, and
  gated behind the also-off `onboarding.v2` master).
- After: `(pref && PREF_ROUTE[pref]) || 'QuickSetTiers'`. The
  "More ways to rank" header link on QuickSetTiers (testID `rank.more-ways`,
  → `RankHome`) is now always rendered, not flag-gated — it is the only path
  to the chooser (the Rank action sheet doesn't list RankHome), so the
  chooser stays one tap away.

`onboarding.rank_routing` remains a live flag for its OTHER surface
(TradesScreen deck-exhausted trio entry); TabNav no longer reads it.

## Existing users unaffected

- A stored pref always wins: `PREF_ROUTE[pref]` short-circuits the fallback.
  No pref value is written, migrated, or overwritten anywhere in this change —
  landing on Quick Set by default does NOT set `rankingMethodPref`, so a user
  who later picks a method from the chooser/Settings gets exactly the old
  behavior.
- Backend: `POST /api/ranking-method` already whitelists `'quickset'` (#119)
  and there is **no server-side default for unset** (routing is entirely
  client-side; `get_ranking_method` returning None is handled per-call-site) —
  no backend change needed, backend untouched.

## Files

- `mobile/src/navigation/TabNav.tsx` — fallback + always-on header link
- `mobile/src/screens/RankHomeScreen.tsx` — header comment only (no longer first-run default)
- `mobile/src/navigation/CLAUDE.md`, `mobile/src/screens/CLAUDE.md` — routing rows updated

## Verification

- `cd mobile && npx tsc --noEmit` — clean
- Existing testIDs unchanged (`rank.more-ways`, `rank-home.card.*`,
  `rankmenu.*`); smoke flows that navigate via the Rank menu are unaffected.
  Any flow asserting the chooser as the null-pref landing screen needs the
  same update QA already planned for `onboarding.rank_routing`.
