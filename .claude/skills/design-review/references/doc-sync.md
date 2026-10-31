# Design-doc sync — what a UI change owes the docs

The reviewer lists every item below that applies as **docs owed** in the verdict. The
reviewer does not write them; the doc's named owner does:

| Doc / file | Owner |
|---|---|
| `docs/design/design-system.md`, `components.md`, `brand.md`, `web/style-guide.html`, `mockups/` | design-lead |
| `docs/cross-client-invariants.md` | head-eng (contract-doc owner); colour and label rows jointly with design-lead |
| Token mirror code (`web/css/tokens.css`, `mobile/src/theme/chalkline.ts`, `colors.ts`, `spacing.ts`) and shared components (`mobile/src/components/chalkline/*`) | head-eng writes, design-lead reviews |

Docs owed do not block a diff on their own. A token change whose mirrors disagree does
(see section 3).

## 1. New or changed component

A new construction, or a change to an existing row's anatomy, owes a `components.md` row
in the section it belongs to:

- **Name** (bold) and the issue / decision that introduced it.
- **Spec**: surfaces, borders, radius, type tokens, accent use, states (pressed,
  selected, disabled, loading, empty, error), hit target.
- **testID(s)** the build registered (`mobile/src/components/CLAUDE.md` holds the
  registry; `mobile/scripts/testid-lint.sh` lints it in CI).
- **Source component**: the file path (the table's last column).

A new component the diff adds without a row is a **proposal**: the verdict says so and
asks design-lead to accept it into `components.md` or fold it into an existing row. A
new component that duplicates an existing one ("don't invent parallel variants",
`components.md` header) is a block finding, not a docs item.

## 2. Style-guide render

`web/style-guide.html` renders tokens, type, buttons, badges, player and trade cards.
Owe a render when the change adds or alters a token, a badge or chip, a button variant,
or a card construction that exists on web. Mobile's mirror is
`mobile/src/components/chalkline/StyleGuide.tsx`; owe an update there when a Chalkline
primitive (`TickLabel`, `Button`, `Badge`, `Card`, `Meter`, `Icon`, `Text`) changes.

## 3. Token mirrors in lockstep

A token change must land in every mirror in the same change. Mismatched mirrors are a
**block** finding.

| design-system.md | web `tokens.css` | mobile `chalkline.ts` / `colors.ts` |
|---|---|---|
| `--ink-0…3`, `--line` | same names | `ink.ink0…ink3`, `ink.line` |
| `--line-strong` `#59647A` | `--line-strong` | `ink.lineStrongA11y` (legacy `ink.lineStrong` `#3D4654` until `visual.chalkline_cleanup` cleanup) |
| `--chalk`, `--chalk-dim`, `--chalk-faint` | same | `chalk.base`, `chalk.dim`, `chalk.faint` |
| `--ice`, `--ice-press`, `--on-ice` | same, plus alias `--accent` | `ice.base`, `ice.press`, `ice.on` |
| `--flare`, `--flare-press`, `--on-flare` | same | `flare.base`, `flare.press`, `flare.on` |
| `--pos`, `--neg`, `--warn` | same | `semantic.pos/neg/warn` |
| Medal `gold` / `silver` / `bronze` | `--gold` aliases `--warn` | `colors.gold/silver/bronze` |
| Positions, tiers | `--qb…--te`, `--firsts-*`…, `--tier-*` | `colors.position`, `colors.tier` (re-exported as `position`, `tier`) |
| Radii `--r-xs/sm/md/pill` | same | `radii.xs/sm/md/pill` |
| Spacing scale | — | `space` (has `xxxl` 48); `spacing.ts` is legacy |
| Type table | `--font-ui/display/data` | `fonts.*`, `type.*`, `maxFontScale` |
| Motion `--t-fast/base/sheet` | same | `duration.fast/base/sheet` |
| `--shadow-sheet`, scrim | `--shadow-sheet` | `shadowSheet`, `scrim` |

When tokens change, also run:

- `cd mobile && npm run test:contrast`. It is **not** in CI (`.github/workflows/ci.yml`
  runs `mobile/tests/check-*.js`; the contrast script lives in `mobile/scripts/`), so a
  token PR that skips it has no contrast evidence. Note the result in the verdict.
- `python3 qa/web/check_web_structure.py` (in CI) for any web change; it fails if a
  second file defines the token block.

## 4. Exceptions

A valid exception from [exceptions.md](exceptions.md) that `design-system.md` does not
record owes a copy there: the rule, the scope, the decision ID. Put it next to the rule
it bends (the ice ration lives in `brand.md` §Color philosophy and the Ice table; the
touch floor in §Accessibility floors).

## 5. Known drift (2026-10-15)

Existing docs-owed items. List the ones a diff touches; do not re-raise the rest on
every review.

1. `design-system.md` records none of exceptions E1–E6 or E8.
2. `design-system.md` §Iconography still describes the `They're interested` migration as
   pending; it shipped 2026-07-02.
3. `design-system.md` §Color tokens says web tokens are defined in `web/css/styles.css`;
   since 2026-08-19 they live only in `web/css/tokens.css`.
4. `design-system.md` §Spacing says the scale is unchanged from `spacing.ts`; that file
   lacks `xxxl` 48, which `chalkline.ts` `space` has.
5. `components.md` §Sheets gives the scrim as `rgba(9,10,8,0.78)`; `design-system.md`
   §Depth and `chalkline.ts` `scrim` say `rgba(7,9,12,0.78)`.
6. `components.md` Position tile row cites D-202 for the D-204 ice exception; the Hero
   entry tile row cites G-425, not D-192.
7. `brand.md` §Color philosophy lists tier colours as "gold/green/blue/purple/gray";
   the 8-tier ladder is red, fuchsia, gold, teal, sky, pink, lime, gray.
8. `mobile/src/components/chalkline/CLAUDE.md` says screens still use the legacy
   components; `chalkline.ts` says the migration is complete.
9. `docs/cross-client-invariants.md` Locations lines are stale (see
   [invariant-colors.md](invariant-colors.md) §1).
