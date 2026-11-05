# Invariant-colour change — tier and position hexes and labels

Triggered by sweep S12 line 2, by an S6/S13 hit that edits a tier or position value, or
by any PRD that renames a tier. Source of truth: `docs/cross-client-invariants.md`
§"Tier keys, labels & color tokens" and §"Position color tokens".

## 0. Who signs

- These rows are a contract across mobile, web, the style guide, the extension and the
  backend OG-image renderer. A change needs **joint sign-off from head-eng** (it owns
  `cross-client-invariants.md`) and design-lead. A diff without both is a block.
- Decision P14 (2026-10-14) splits tier work: the **words** (tier names, labels) go to
  `marketing-lead`; the **encodings** (hex, tint base, badge construction) go to
  `design-lead`. A label change without marketing-lead's sign-off is a block.
- Tier **keys** (`firsts_4plus` … `waivers`) are wire enums; renaming one is an API
  change for head-eng, not a design call.

## 1. List every location

Start from the Locations lines, then grep, because the lines are stale:

- **Tiers** (`cross-client-invariants.md` §Tier keys, Locations): `mobile/src/theme/colors.ts`
  (`colors.tier`), `mobile/src/components/TierBadge.tsx` and `chalkline/Badge.tsx`
  (`TierChalkBadge`) label maps, `mobile/src/utils/tierBands.ts` (`TIERS` / `TIER_LABEL`),
  `web/positional-tiers.html`, `web/profile.html` (`TIER_ORDER` / `TIER_LABELS`),
  `web/style-guide.html`, `extension/content.css` (`.ftf-badge.ftf-tier-*`, including the
  lighter 300/200-level per-client border and text shades) and `extension/content.js`
  (`TIER_LABELS`), `backend/og_image.py` (`TIER_ORDER` / `TIER_LABELS` / `TIER_TINTS`).
- **Positions** (§Position color tokens, Locations): `mobile/src/theme/colors.ts`
  (`colors.position`), `mobile/src/components/PositionChip.tsx`, `web/profile.html`, and any
  progress-bar component.
- **Not on either line, but holding the values:** `web/css/tokens.css` (`--qb…--te`,
  `--firsts-*`…, `--tier-*`; the single web token source since 2026-08-19, which
  `profile.html` and `style-guide.html` now read through `var()`),
  `docs/design/design-system.md` §Preserved invariants, and the
  `cross-client-invariants.md` tables themselves.
- **Stale on the lines (2026-10-15):** `web/profile.html` no longer has inline `:root`
  hexes; `PositionChip.tsx` no longer holds rgba tint bases. List both as docs owed to
  head-eng.

Find the real set for the value being changed (old hex and its rgb tuple):

```sh
git grep -n -i -E -e 'f472b6' -e '244, ?114, ?182' -- ':!mockups' ':!archive' ':!docs/recovery'
```

Every hit is either changed in the diff or named in the verdict as missed. Labels: grep
the old label string the same way (`'3rd'`, `"FA"`), scoped to the files above.

## 2. Check distance — positions, both accents, and semantics

Tier hues are the bright 400-level family, positions the deeper 500-level family, and no
tier may share a hue with a position colour (`cross-client-invariants.md`). The same care
applies to ice and flare, which no doc spells out. Measure the candidate against all
eight references:

```sh
perl -MList::Util=max,min -e '
sub hue { my @c = map { hex($_) / 255 } unpack "A2A2A2", $_[0]; my ($R, $G, $B) = @c; my ($x, $n) = (max(@c), min(@c)); my $d = $x - $n or return 0;
  my $h = $x == $R ? ($G - $B) / $d : $x == $G ? ($B - $R) / $d + 2 : ($R - $G) / $d + 4; ($h * 60 + 360) % 360 }
sub lab { my ($R, $G, $B) = map { my $v = hex($_) / 255; $v <= 0.04045 ? $v / 12.92 : (($v + 0.055) / 1.055) ** 2.4 } unpack "A2A2A2", $_[0];
  my @f = map { $_ > 0.008856 ? $_ ** (1 / 3) : 7.787 * $_ + 16 / 116 } (($R * .4124 + $G * .3576 + $B * .1805) / .95047, $R * .2126 + $G * .7152 + $B * .0722, ($R * .0193 + $G * .1192 + $B * .9505) / 1.08883);
  (116 * $f[1] - 16, 500 * ($f[0] - $f[1]), 200 * ($f[1] - $f[2])) }
my %ref = (QB => "f97316", RB => "22c55e", WR => "3b82f6", TE => "a855f7", ice => "56d9ec", flare => "f0508c", neg => "ef4444", warn => "f59e0b");
(my $c = lc shift) =~ s/^#//; my @a = lab($c);
for (sort { $a cmp $b } keys %ref) { my @b = lab($ref{$_}); my $dh = abs(hue($c) - hue($ref{$_})); $dh = 360 - $dh if $dh > 180;
  printf "%-6s #%s  hue %3d deg apart  dE76 %5.1f\n", $_, $ref{$_}, $dh, sqrt(($a[0]-$b[0])**2 + ($a[1]-$b[1])**2 + ($a[2]-$b[2])**2) }' '#f472b6'
```

Today's closest pairs (hue degrees apart / CIE76 ΔE), measured 2026-10-15:

| Tier | Nearest reference | Hue apart | ΔE | Documented? |
|---|---|---|---|---|
| `firsts_2` gold `#fbbf24` | `--warn` `#F59E0B` | 6° | 16.8 | yes: bright vs deep (design-system.md §Semantic) |
| `third` pink `#f472b6` | **flare** `#F0508C` | 9° | 17.4 | **no** — not in `cross-client-invariants.md` or `design-system.md` |
| `firsts_4plus` red `#f87171` | `--neg` `#EF4444` | 0° | 21.0 | yes: bright vs deep |
| `first_1` teal `#2dd4bf` | **ice** `#56D9EC` | 15° | 24.5 | **no** |
| `second` sky `#38bdf8` | **ice** `#56D9EC` | 11° | 25.2 | **no** |
| `firsts_3` fuchsia `#e879f9` | TE `#A855F7` | 21° | 26.3 | yes: bright vs deep |

Reviewer heuristic, not a design-system rule: a change that moves any tier closer to a
position colour, ice or flare than it is today, or that creates a new pair under ΔE 30,
is a finding until `cross-client-invariants.md` carries a written separation rationale
and the joint sign-off. The `third`/flare, `first_1`/ice and `second`/ice proximities are
existing undocumented debt; list them as docs owed (head-eng, with design-lead) whenever a
diff touches tier colours.

## 3. Keep the label-pairing floor

Position and tier colour is never the only encoding (design-system.md §Accessibility
floors): every rail, dot, badge, meter segment and chart fill sits next to its text
label (`QB`/`RB`/`WR`/`TE`, the tier name) or carries it in the accessibility label. A
hex change that ships anywhere the label is missing is a block, even if the old hex was
equally unlabelled there.

## 4. What the verdict records

- Every location from section 1, each marked changed or missed.
- The distance table for the new value.
- Sign-offs present: head-eng, design-lead, and marketing-lead for any label.
- Docs owed: the `cross-client-invariants.md` row, `design-system.md` §Preserved
  invariants, the style-guide swatch, and any stale Locations entry.
