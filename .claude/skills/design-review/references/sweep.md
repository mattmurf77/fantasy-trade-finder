# Mechanical sweep — one pattern per prohibition

Copy-paste commands for the macOS default shell (zsh) and `/usr/bin/perl`. Every
pattern runs in perl, so BSD vs GNU `grep` flavours never change a result. The only
`git` features used are `git diff`, `git grep -n -e ''` (a plain line dump, no PCRE)
and `git show`. Rule text: `docs/design/design-system.md` §Prohibitions 1–9, §Typography,
§Accessibility floors; `docs/design/brand.md` §Color philosophy.

A hit is a **candidate**, not a verdict. Each rule says whether a hit is a finding by
default (**F**) or needs a judgment call (**J**). Triage every hit in the verdict, then
check it against [exceptions.md](exceptions.md) before you call it.

## 0. Setup

Run from the repo root of a checkout of the branch under review (your own worktree;
`git switch --detach <branch>` there is fine). Output lands in `/tmp/design-review/`.

**Concurrent reviews:** several leads run reviews in parallel, and one shared directory
would let them overwrite each other's files. Each concurrent review runs in its own
worktree and uses its own directory, `/tmp/design-review-<slug>/`, in place of
`/tmp/design-review/` in every command below.

```sh
git fetch origin
mkdir -p /tmp/design-review
```

The scan scope is the same twelve pathspecs everywhere below:
`mobile/App.tsx`, `mobile/src/*.ts(x)`, `web/*.{html,css,js}`, `extension/*.{html,css,js}`,
`mockups/*.{html,css,js}` (git pathspec `*` crosses directories).

**Whole-tree dump** (always; S11 reads it, and it is the audit input):

```sh
git grep -n -I -e '' -- 'mobile/App.tsx' 'mobile/src/*.ts' 'mobile/src/*.tsx' 'web/*.html' 'web/*.css' 'web/*.js' 'extension/*.html' 'extension/*.css' 'extension/*.js' 'mockups/*.html' 'mockups/*.css' 'mockups/*.js' > /tmp/design-review/all.raw
```

## 1. Pick the input — added lines (review) or whole files (audit)

**Review a committed branch** (the default). Emits `path:line:content` for every added
line, with the line number in the new file:

```sh
git diff -U0 --no-color --src-prefix=a/ --dst-prefix=b/ origin/main...HEAD -- 'mobile/App.tsx' 'mobile/src/*.ts' 'mobile/src/*.tsx' 'web/*.html' 'web/*.css' 'web/*.js' 'extension/*.html' 'extension/*.css' 'extension/*.js' 'mockups/*.html' 'mockups/*.css' 'mockups/*.js' | perl -ne '
  if (/^diff --git /) { $h = 1; next }
  if ($h) { $f = $1 if m{^\+\+\+ b/(.+)$}; if (/^@@ -\S+ \+(\d+)/) { $n = $1; $h = 0 } next }
  if (/^@@ -\S+ \+(\d+)/) { $n = $1; next }
  if (s/^\+//) { print "$f:$n:$_"; $n++ }' > /tmp/design-review/lines.raw
```

**Review uncommitted work** — same parser, diffed against the merge base so the
working tree counts. Run `git add -N <path>` on new files first, or they are invisible:

```sh
git diff -U0 --no-color --src-prefix=a/ --dst-prefix=b/ "$(git merge-base origin/main HEAD)" -- 'mobile/App.tsx' 'mobile/src/*.ts' 'mobile/src/*.tsx' 'web/*.html' 'web/*.css' 'web/*.js' 'extension/*.html' 'extension/*.css' 'extension/*.js' 'mockups/*.html' 'mockups/*.css' 'mockups/*.js' | perl -ne '
  if (/^diff --git /) { $h = 1; next }
  if ($h) { $f = $1 if m{^\+\+\+ b/(.+)$}; if (/^@@ -\S+ \+(\d+)/) { $n = $1; $h = 0 } next }
  if (/^@@ -\S+ \+(\d+)/) { $n = $1; next }
  if (s/^\+//) { print "$f:$n:$_"; $n++ }' > /tmp/design-review/lines.raw
```

**Audit whole files** (no diff; debt inventory, never a verdict on a change):

```sh
cp /tmp/design-review/all.raw /tmp/design-review/lines.raw
```

**Drop comment-only lines** from both inputs, so prose like "no gradients" never fires.
Block-comment interiors are dropped when the block opens at the start of a line; a
`qa:allow-*` pragma line is kept so S1 can honour it:

```sh
perl -ne '
  my ($p, $n, $c) = /^([^:]+):(\d+):(.*)$/s or next;
  $in = 0 if $p ne $lp || $n != $ln + 1; ($lp, $ln) = ($p, $n);
  if ($in) { $in = 0 if $c =~ /\*\/|-->/; next }
  if ($c =~ /^\s*(?:\{?\/\*|<!--)/ && $c !~ /qa:allow-/) { $in = 1 unless $c =~ /\*\/|-->/; next }
  next if $c =~ /^\s*(?:\/\/|\*(?:\/|\s*$|\s(?!.*\{\s*$)))/ && $c !~ /qa:allow-/;
  print' /tmp/design-review/lines.raw > /tmp/design-review/lines.txt
perl -ne '
  my ($p, $n, $c) = /^([^:]+):(\d+):(.*)$/s or next;
  $in = 0 if $p ne $lp || $n != $ln + 1; ($lp, $ln) = ($p, $n);
  if ($in) { $in = 0 if $c =~ /\*\/|-->/; next }
  if ($c =~ /^\s*(?:\{?\/\*|<!--)/ && $c !~ /qa:allow-/) { $in = 1 unless $c =~ /\*\/|-->/; next }
  next if $c =~ /^\s*(?:\/\/|\*(?:\/|\s*$|\s(?!.*\{\s*$)))/ && $c !~ /qa:allow-/;
  print' /tmp/design-review/all.raw > /tmp/design-review/all.txt
```

**Colour allowlist** (S6), read from `origin/main` so a diff cannot whitelist its own new
hue. Code token files give every hex and `rgb()` base; the two docs give 6-digit hexes
only (their 3-digit `#NNN` strings are issue numbers):

```sh
git show origin/main:web/css/tokens.css origin/main:mobile/src/theme/chalkline.ts origin/main:mobile/src/theme/colors.ts | perl -ne '
  next if /^\s*(?:\/\/|\/?\*)/;
  while (/#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![\w-])/g) { my $h = lc $1; $h =~ s/(.)/$1$1/g if length $h == 3; print "$h\n" }
  while (/rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/g) { printf "%02x%02x%02x\n", $1, $2, $3 }' > /tmp/design-review/allow.txt
git show origin/main:docs/design/design-system.md origin/main:docs/cross-client-invariants.md | perl -ne 'while (/#([0-9a-fA-F]{6})(?![\w-])/g) { print lc($1), "\n" }' >> /tmp/design-review/allow.txt
sort -u -o /tmp/design-review/allow.txt /tmp/design-review/allow.txt
```

## 2. The rules

Each command prints its hits and saves them to `/tmp/design-review/S<n>.txt`.

| ID | Prohibition (source) | Default |
|---|---|---|
| S1 | Emoji in UI (#1) | F |
| S1b | Dingbat glyphs: check marks, crosses (#1, Iconography map) | J |
| S2 | Gradients (#2) | F |
| S3 | Blur, glass, translucent white surface (#3) | F |
| S3b | Any translucent `rgba()` background (#3 "surfaces are solid ink steps") | J |
| S4 | Inter, Roboto, system stack, non-Chalkline family (#4) | F |
| S5 | Radius > 8 that is not 999 (#5) | F |
| S5b | Pill radius (999) in use (#5 "specced pills only") | J |
| S6 | Hex or `rgb()` not in the token files or invariants (#9) | F |
| S6b | Named CSS colours (`white`, `red`, ...) (#9) | F |
| S7 | Shadow / elevation (#8) | J |
| S8 | `translateY` / scale / hover transforms (#7, Motion) | J |
| S9 | Text below 11px (Typography type floor) | F |
| S10 | Flare on an actionable control (#6, ADR-005) | J; S10b F |
| S11 | Ice in more than ~3 places on a screen (brand.md ration) | J |
| S12 | Token, invariant, component files touched | trigger |
| S13 | Position / tier colour in use (Accessibility floors: label pairing) | J |

**S1 — emoji** (U+1F000–1FAFF, U+2600–26FF, U+2B00–2BFF, VS16, ZWJ, plus `\u`
escapes and numeric entities). Honours `qa:allow-emoji` on a line and the line after it,
like `qa/web/check_web_structure.py`:

```sh
perl -CSD -ne '
  if (/qa:allow-emoji/) { $skip = 1; next } if ($skip) { $skip = 0; next }
  print if /[\x{1F000}-\x{1FAFF}\x{2600}-\x{26FF}\x{2B00}-\x{2BFF}\x{FE0F}\x{200D}]|\\u\{?(?:1F[0-9A-Fa-f]{3}|26[0-9A-Fa-f]{2}|2B[0-9A-Fa-f]{2}|FE0F)|&#x(?:1F[0-9A-Fa-f]{3}|26[0-9A-Fa-f]{2}|2B[0-9A-Fa-f]{2});|&#(?:12[6-9][0-9]{3}|9(?:72[89]|7[3-9][0-9]|[89][0-9]{2}));/' /tmp/design-review/lines.txt | tee /tmp/design-review/S1.txt
```

**S1b — dingbats** (U+2700–27BF). A finding when the glyph stands in for an icon
(design-system.md maps the check mark U+2713 to `check` and the cross U+274C to `x`);
typographic use is fine. The web CI
guard deliberately does not flag this range, so nothing else will:

```sh
perl -CSD -ne 'print if /[\x{2700}-\x{27BF}]|\\u27[0-9A-Fa-f]{2}|&#x27[0-9A-Fa-f]{2};|&#(?:99[89][0-9]|10[01][0-9]{2});/' /tmp/design-review/lines.txt | tee /tmp/design-review/S1b.txt
```

**S2 — gradients** (CSS `*-gradient`, `LinearGradient`, `expo-linear-gradient`, SVG
`<linearGradient>`). The only exemption is mascot art inside its own box (E3), which
ships as raster sprites under `mobile/assets/mascot/ram/`, outside these paths; any hit
here is a finding unless it sits inside mascot artwork:

```sh
perl -ne 'print if /gradient/i' /tmp/design-review/lines.txt | tee /tmp/design-review/S2.txt
```

**S3 — blur, glass, translucent white:**

```sh
perl -ne 'print if /(?i:backdrop-?filter|BlurView|expo-blur|blurRadius|rgba\(\s*255\s*,\s*255\s*,\s*255\s*,|#f{6}[0-9a-f]{2}(?![\w-])|#f{3}[0-9a-e](?![\w-]))|(?<![\w.])blur\(/' /tmp/design-review/lines.txt | tee /tmp/design-review/S3.txt
```

**S3b — translucent backgrounds.** Legitimate only for the solid scrim
(`rgba(7,9,12,0.78)`) and the invariant tier tints (`docs/cross-client-invariants.md`
rgba tint bases, extension badges). Anything else is a translucent surface:

```sh
perl -ne 'print if /(?:background(?:-color)?|backgroundColor)\s*:\s*["\x27]?rgba\(/i' /tmp/design-review/lines.txt | tee /tmp/design-review/S3b.txt
```

**S4 — fonts.** Inter, Roboto, `system-ui`, `-apple-system`, `BlinkMacSystemFont`
anywhere, plus any `font-family` / `fontFamily` / `font:` value that names no Chalkline
family and no token (`var(--…)`, `fonts.*`, `type.*`, `inherit`):

```sh
perl -ne 'print if /\b(?:Inter|Roboto)\b|system-ui|-apple-system|BlinkMacSystemFont|(?:font-family|fontFamily|(?<![\w-])font)\s*[:=]\s*(?!.*(?:var\(--|fonts\.|type\.|Barlow|Archivo|IBM Plex Mono|IBMPlexMono|inherit))/' /tmp/design-review/lines.txt | tee /tmp/design-review/S4.txt
```

**S5 — radius > 8, not 999.** CSS `border-*radius`, RN `border*Radius`, SVG `<rect rx>`;
numbers 9–998, any `%` (circles), rem/em above 0.5, and the `size / 2` circle idiom. A
circle is a finding unless the register covers it (`qa/web/check_web_structure.py`
skips `%`, so CI will not catch it on web):

```sh
perl -ne 'print if /(?:border(?:-(?:top|bottom)-(?:left|right))?-radius|[bB]order(?:Top|Bottom)?(?:Left|Right|Start|End)?Radius|<[Rr]ect\b[^>]*?\br[xy])\s*[:=]\s*[^;,}]*?(?:(?<![\d.\w#-])(?:9|[1-9][0-9]|[1-8][0-9]{2}|9[0-8][0-9]|99[0-8])(?:\.[0-9]+)?(?![\d.])|(?<![\d.])(?:0?\.(?:5[1-9]|[6-9])[0-9]*|[1-9][0-9]*(?:\.[0-9]+)?)r?em\b|\/\s*2(?![\d.]))/' /tmp/design-review/lines.txt | tee /tmp/design-review/S5.txt
```

**S5b — pills in use.** Each hit must be a pill `components.md` specs as one (CountBadge,
LikesYouPill, TradeFinderModeBar pills, the League rankings position filter):

```sh
perl -ne 'print if /(?:border-radius|[bB]orderRadius)\s*:\s*[^;,}]*(?:999|radii\.pill|--r-pill)/' /tmp/design-review/lines.txt | tee /tmp/design-review/S5b.txt
```

**S6 — off-token colour.** Every `#hex` (3/4/6/8 digits, alpha ignored) and `rgb()` /
`rgba()` base checked against `allow.txt`. The stale `#3D4654` (legacy `ink.lineStrong`)
is treated as off-token. All-digit `#NNN` counts only in colour position (after a quote,
`:`, `=` or a border style), so issue numbers stay out. Hits under
`mobile/src/components/analyst/` are illustration art: route them to the mascot check in
SKILL.md, not rule 9:

```sh
perl -ne '
  if ($ARGV =~ /allow\.txt$/) { chomp; $ok{$_} = 1; next }
  delete $ok{"3d4654"};
  my $l = $_; $l =~ s{^[^:]+:\d+:}{}; $l =~ s{/\*.*?\*/}{}g; $l =~ s{(^|\s)//.*$}{$1};
  my @bad;
  while ($l =~ /#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])/g) {
    my ($raw, $pre) = ($1, substr($l, 0, $-[0]));
    next if $raw =~ /^\d{3,4}$/ && $pre !~ /(?:["\x27]|[:=]\s*|(?:solid|dashed|dotted|double)\s+)$/;
    my $h = lc $raw; $h = join "", map { $_ x 2 } split //, substr($h, 0, 3) if length $h <= 4;
    push @bad, "#$raw" unless $ok{substr($h, 0, 6)} }
  while ($l =~ /rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/g) {
    push @bad, "rgb($1,$2,$3)" unless $ok{sprintf "%02x%02x%02x", $1, $2, $3} }
  print "[@bad] $_" if @bad' /tmp/design-review/allow.txt /tmp/design-review/lines.txt | tee /tmp/design-review/S6.txt
```

**S6b — named colours:**

```sh
perl -ne 'print if /(?:[cC]olor|[bB]ackground|border(?:-color)?|[bB]orderColor|fill|stroke|tintColor)\s*[:=]\s*\{?\s*["\x27]?(?:white|black|red|green|blue|gr[ae]y|purple|orange|yellow|pink|silver|gold|navy|teal|cyan|magenta)\b/' /tmp/design-review/lines.txt | tee /tmp/design-review/S6b.txt
```

**S7 — shadow / elevation.** Allowed only as `--shadow-sheet` / `...shadowSheet` on a
sheet, menu or toast. Every other hit is a finding, including `shadowSheet` spread on a
non-sheet (FAB, strip, header) and a hand-rolled shadow block. A focus ring drawn with
`box-shadow` is acceptable only if it renders the 2px ice ring:

```sh
perl -ne 'print if /box-shadow|boxShadow|text-shadow|textShadow|drop-shadow|shadow(?:Color|Opacity|Radius|Offset)\b|(?<![\w-])elevation\s*:|\.\.\.shadowSheet|--shadow-sheet/' /tmp/design-review/lines.txt | tee /tmp/design-review/S7.txt
```

**S8 — lift and press transforms.** A finding when the transform sits in a `:hover`,
`:focus` or pressed state (cards and buttons change border and fill, never position or
scale). Sanctioned uses: sheet and toast slides, and the one on-load entry stagger
(fade + 8px rise, 40ms apart, max 6 items, reduced-motion respected):

```sh
perl -ne 'print if /translateY|translate3d|(?<![\w-])scale\s*[:(]|:hover[^{]*\{[^}]*transform/' /tmp/design-review/lines.txt | tee /tmp/design-review/S8.txt
```

**S9 — text below 11px** (`font-size` / `fontSize` 0–10.x, rem/em below 0.6875, `font:`
shorthand). Barlow Condensed below 16px is a judgment check in SKILL.md:

```sh
perl -ne 'print if /(?:font-size|fontSize)\s*[:=]\s*\{?\s*["\x27]?(?:(?<![\d.])(?:[0-9]|10)(?:\.[0-9]+)?(?:px)?(?![\d.])|0?\.(?:[0-5][0-9]*|6[0-7][0-9]*)r?em)|(?<![\w-])font\s*:\s*[^;]*?(?<![\d.\/])(?:[0-9]|10)(?:\.[0-9]+)?px/' /tmp/design-review/lines.txt | tee /tmp/design-review/S9.txt
```

**S10 — flare.** S10a lists every flare use for the judgment pass; S10b is the
high-confidence case, flare on the same line as a press handler, button or link. The
sanctioned interactive case is `flare.press` on a flare-bordered informational chip
(design-system.md); flare as a control's primary fill, label or border is a finding:

```sh
perl -ne 'print if /flare\.(?:base|press|on)\b|var\(--(?:flare|flare-press|on-flare)\)|#(?:F0508C|D8437B|170610)\b/i' /tmp/design-review/lines.txt | tee /tmp/design-review/S10a.txt
perl -ne 'print if /flare\.(?:base|press|on)\b|var\(--(?:flare|flare-press|on-flare)\)|#(?:F0508C|D8437B|170610)\b/i && /onPress|Pressable|\bTouchable|(?i:<button|\bbtn\b|-btn\b|Btn\b|\bcta\b|cursor\s*:\s*pointer|href=)/' /tmp/design-review/lines.txt | tee /tmp/design-review/S10b.txt
```

**S11 — ice count.** Per touched file: ice references added (`add`) and in the whole file
(`file`), counting fills, borders and text (`ice.base`, `var(--ice)`, `var(--accent)`,
`#56D9EC`) but not the pressed or on-ice halves of the same element. References are a
proxy: a file over 3, or a screen composed of several touched files, gets a code-walk
count of rendered ice on the screen. More than 3 is a finding unless the register
covers it (D-204 Home position tiles):

```sh
perl -ne '
  my ($f) = /^([^:]+):/; my $k = () = /ice\.base\b|var\(--(?:ice|accent)\)|#56D9EC\b/gi;
  if ($ARGV =~ /lines\.txt$/) { $t{$f} = 1; $add{$f} += $k; next }
  $all{$f} += $k if $t{$f};
  END { printf "%4s %4s  %s\n", "add", "file", "path"; for (sort keys %t) { printf "%4d %4d  %s\n", $add{$_}, $all{$_}, $_ if $add{$_} || $all{$_} > 3 } }' /tmp/design-review/lines.txt /tmp/design-review/all.txt | tee /tmp/design-review/S11.txt
```

**S12 — surface triggers.** Line 1: token or design-doc files touched → [doc-sync.md](doc-sync.md).
Line 2: a tier or position Locations file touched (`docs/cross-client-invariants.md`) →
[invariant-colors.md](invariant-colors.md). Line 3: a new file under `components/`,
`screens/` or `web/` → a new component or screen (judgment pass, item 1). For uncommitted
work, swap `origin/main...HEAD` for `"$(git merge-base origin/main HEAD)"`:

```sh
git diff --name-status origin/main...HEAD -- web/css/tokens.css mobile/src/theme docs/design web/style-guide.html mobile/src/components/chalkline | tee /tmp/design-review/S12.txt
git diff --name-status origin/main...HEAD -- docs/cross-client-invariants.md mobile/src/theme/colors.ts mobile/src/components/TierBadge.tsx mobile/src/components/chalkline/Badge.tsx mobile/src/components/PositionChip.tsx mobile/src/utils/tierBands.ts web/positional-tiers.html web/profile.html web/style-guide.html extension/content.css extension/content.js backend/og_image.py | tee -a /tmp/design-review/S12.txt
git diff --name-status --diff-filter=A origin/main...HEAD -- 'mobile/src/components/*' 'mobile/src/screens/*' 'web/*.html' | tee -a /tmp/design-review/S12.txt
```

**S13 — data colours in use.** Every position or tier colour must sit next to its text
label (QB/RB/WR/TE, tier name) and stay a data encoding, never chrome:

```sh
perl -ne 'print if /colors\.(?:position|tier)\b|\b(?:position|tier)\[|posColor\(|tierColor\(|var\(--(?:qb|rb|wr|te|picks|waivers|firsts-4plus|firsts-3|firsts-2|first-1|second|third|fourth|tier-[\w-]+)\)|#(?:F97316|3B82F6|A855F7|f87171|e879f9|fbbf24|2dd4bf|38bdf8|f472b6|a3e635|7a7f96)\b/i' /tmp/design-review/lines.txt | tee /tmp/design-review/S13.txt
```

**Summary for the verdict's Evidence section:**

```sh
wc -l /tmp/design-review/S*.txt
```

## 3. Re-proving the patterns

After editing any pattern, plant one violation per rule in an uncommitted scratch file
under `mobile/src/`, `git add -N` it, run section 1's uncommitted mode and every rule,
confirm each rule fires on its planted line (and the comment-only header line fires
nothing), then `git reset -- <file>` and delete it. Leave `git status` clean.

## 4. What the sweep cannot see

Rendered ice count across composed components, hit-target size after `hitSlop`,
contrast of a new token pair, label pairing across lines, motion count per screen, and
whether a new construction duplicates an existing component. Those are SKILL.md's
judgment pass, proved by a file:line code-walk.

There is no CI guard for these rules on mobile today. A `mobile/tests/check-chalkline.js`
structural guard is being proposed to `head-eng`; until it exists, this sweep is run by
hand on every UI diff. On web, `qa/web/check_web_structure.py` (CI) already enforces
emoji, system fonts, radius in px, gradients and `backdrop-filter` on shipped pages, and
excludes `color-lab*.html`, `style-guide.html` and `admin/`.
