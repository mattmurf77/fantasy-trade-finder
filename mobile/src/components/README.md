# mobile/src/components/

77 shared components plus three subfolders. The annotated per-component map — what each one is for, its flag gate, its testIDs, its sharp edges — is [CLAUDE.md](CLAUDE.md). Read that before editing any component; this file is orientation only.

## Subfolders

| Folder | What's there | Doc |
|---|---|---|
| `chalkline/` | Design-system primitives: `Text`, `Button`, `Card`, `Badge`, `Meter`, `Icon`, `TickLabel`, plus `StyleGuide` (renders everything; not routed). `index.ts` re-exports them | [chalkline/CLAUDE.md](chalkline/CLAUDE.md) |
| `analyst/` | "The Analyst" mascot: six pose SVGs (`Neutral`, `Point`, `Celebrate`, `Computing`, `Thinking`, `Oops`), the `parts.tsx` shared geometry kit, and the `index.tsx` switcher | [analyst/CLAUDE.md](analyst/CLAUDE.md) |
| `draft/` | Draft Room / Mock Draft pieces: `DraftRows`, `MockChrome`, `MockEntryPanel`, `MockSetupSheet`, `MockTeamSheet` | rows in [CLAUDE.md](CLAUDE.md) |

`analystScript.ts` sits at this level and is **data, not UI** — the mascot's dialogue table, mirroring `docs/plans/onboarding-conversion/guided-avatar-script.md` §3. Copy edits land there without touching engine or screen logic.

## Conventions

- **One component per file, PascalCase, default export**, named after the file. Props go through an `interface Props` immediately above the component.
- **Build from `chalkline/`.** New text uses `chalkline/Text` (it carries the Dynamic Type caps); new buttons use `chalkline/Button`. Never a bare RN `<Text>` with a hand-written `maxFontSizeMultiplier`.
- **Tokens only.** Import from `../theme/chalkline`. Position/tier colors come from `../theme/colors` via `utils/tierBands` — never a local hex.
- **Prop-driven by default.** Ten self-contained widgets own a `useQuery` (`InLeagueCalculator`, `LeaderboardsSection`, `MarketPulseStrip`, `MatchValueSection`, `OutlookBiasReceipt`, `RankChipBadge`, `RookieDraftBoardSheet`, `TopBar`, `TradeDnaSheet`, `draft/MockTeamSheet`); everything else takes data from its screen. Fetching inside a new component is a decision to justify.
- **Flag gating is self-contained where the render is conditional** — e.g. `MemberEnteredMarker` checks its own flag *and* `source === 'user'`, so callers render it unconditionally. Never wrap it in a caller-side ternary.
- **Sheets are `Modal`-based** and follow the Chalkline sheet construction (ink-2 surface, hairline border, sheet shadow, line-strong grabber, solid scrim). iOS will not stack sibling `Modal`s — a sheet needing a second layer nests it inside the same `Modal`.
- **Sheets and modals do NOT mount `FeedbackFAB`** (root `mobile/CLAUDE.md` exception). Screens with a pinned bottom bar call `setPinnedBottomBarHeight`, exported from `FeedbackFAB`.
- **testIDs** follow the grammar in [docs/plans/mobile-testing/lld.md](../../../docs/plans/mobile-testing/lld.md) Appendix A and are checked by `mobile/scripts/testid-lint.sh`, which is still enforced in CI after the Maestro retirement (D-056). Template-literal ids need an entry in `mobile/scripts/testid-lint-allow.txt`.

## Adding a component

1. Does a `chalkline/` primitive already do it? Use that.
2. Create `MyThing.tsx` here; take props, take tokens.
3. Add a row to [CLAUDE.md](CLAUDE.md) — the contract, not the changelog.
4. Give any interactive element a `testID`, then run `bash ../../scripts/testid-lint.sh`.
5. If the behavior is structural and invisible to a value-based test (placement, unconditional render, marker presence), add a `mobile/tests/check-*.js` guard — that is what the existing ones are for, and since D-056 they are the primary automated evidence for mobile.

## What does NOT belong here

Screens (`../screens/`), navigation config (`../navigation/`), data fetching modules (`../api/`), cross-screen state (`../state/`), and pure math (`../utils/`).
