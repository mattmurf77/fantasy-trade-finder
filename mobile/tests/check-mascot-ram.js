#!/usr/bin/env node
// D-155 / D-156 — Fleeced the ram as the guide avatar, behind
// `onboarding.mascot_ram`.
//
// What this guards, and why each one is here rather than assumed:
//
//   1. The swap is FLAG-GATED and the gate is real. Sabotage check: if the
//      flag read is removed or short-circuited (`|| true`), this fails. Flag
//      OFF must stay byte-identical to The Analyst — that is the whole
//      rollback story.
//   2. The switch lives in ONE place. All three call sites go through
//      `AnalystAvatar`; none may import a ram pose directly, or the flag
//      stops being a single lever.
//   3. All six poses exist as sprites at @1x/@2x/@3x and are under the
//      60 KB/file budget that D-155's scoped raster exception sets.
//   4. The 70% ink inset holds. This is the one that will actually catch a
//      regression: sprites re-exported trimmed-to-bbox render ~40% oversized
//      beside the Analyst, and nothing else in CI would notice.
//   5. `point` honours `flip` — 16 spotlight beats mirror it.
//   6. The pose vocabulary is unchanged, so `guide_step_shown{pose}`
//      analytics mean the same thing in both states.
//
// Run: node tests/check-mascot-ram.js

'use strict';

const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const SRC = path.join(ROOT, 'src');
const SPRITES = path.join(ROOT, 'assets', 'mascot', 'ram');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}`); if (detail) console.log(`      ${detail}`); }
}
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');

const POSES = ['neutral', 'point', 'celebrate', 'computing', 'thinking', 'oops'];
const BUDGET_KB = 60;
const INSET_TARGET = 0.70;   // ink width / box width (D-156)
const INSET_TOL = 0.06;      // resampling + antialias slack

console.log('check-mascot-ram:');

// ── 1. the flag gate ────────────────────────────────────────────────────
const idx = read('components/analyst/index.tsx');
assert(/useOnboardingFeature\(\s*['"]onboarding\.mascot_ram['"]\s*\)/.test(idx),
  'AnalystAvatar gates on onboarding.mascot_ram via useOnboardingFeature',
  'onboarding.* keys must AND in the onboarding.v2 master — mobile/src/CLAUDE.md');
assert(!/\buseFlag\(\s*['"]onboarding\./.test(idx),
  'no bare useFlag() on an onboarding.* key',
  'a bare read skips the onboarding.v2 master kill-switch');
assert(!/onboarding\.mascot_ram['"]\s*\)\s*\|\|\s*true/.test(idx)
    && !/\|\|\s*true/.test(idx),
  'the gate is not short-circuited (no `|| true`)',
  'a forced-on gate defeats the rollback lever');
assert(/RamAvatar/.test(idx) && /POSE_COMPONENTS\[pose\]/.test(idx),
  'both branches survive — ram when on, Analyst when off',
  'flag OFF must still render the Analyst pose components');

// ── 2. one switch, not three ────────────────────────────────────────────
const CALLERS = [
  'components/AnalystGuide.tsx',
  'components/TeamReviewEntryCard.tsx',
  'screens/TeamReviewScreen.tsx',
];
for (const f of CALLERS) {
  const t = read(f);
  assert(/AnalystAvatar/.test(t) && !/mascot\/ram/.test(t),
    `${f} goes through AnalystAvatar and does not import a ram pose directly`);
}

// ── 3. sprites exist, at every scale, inside budget ─────────────────────
assert(fs.existsSync(SPRITES), 'assets/mascot/ram/ exists');
let worst = 0;
for (const p of POSES) {
  for (const suf of ['', '@2x', '@3x']) {
    const f = path.join(SPRITES, `${p}${suf}.png`);
    const ok = fs.existsSync(f);
    if (!ok) { assert(false, `sprite ${p}${suf}.png present`); continue; }
    const kb = fs.statSync(f).size / 1024;
    worst = Math.max(worst, kb);
    if (kb > BUDGET_KB) assert(false, `${p}${suf}.png within ${BUDGET_KB} KB`, `${kb.toFixed(1)} KB`);
  }
}
assert(worst > 0 && worst <= BUDGET_KB,
  `all 18 sprites within the ${BUDGET_KB} KB budget (worst ${worst.toFixed(1)} KB)`);

// ── 4. the 70% ink inset (D-156) ────────────────────────────────────────
// Minimal PNG reader: IHDR for dimensions, then scan the alpha channel of a
// decompressed RGBA8 image for the ink bounding box. Only @1x is checked —
// the three scales are exported from one source, so one is representative.
function inkFraction(file) {
  const buf = fs.readFileSync(file);
  if (buf.readUInt32BE(0) !== 0x89504e47) return null;
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  const bitDepth = buf[24], colorType = buf[25];
  // Collect IDAT (+ tRNS, which is where a palette PNG keeps its alpha)
  let off = 8, idat = [], trns = null;
  while (off < buf.length) {
    const len = buf.readUInt32BE(off);
    const type = buf.toString('ascii', off + 4, off + 8);
    if (type === 'IDAT') idat.push(buf.subarray(off + 8, off + 8 + len));
    if (type === 'tRNS') trns = buf.subarray(off + 8, off + 8 + len);
    if (type === 'IEND') break;
    off += 12 + len;
  }
  if (!idat.length) return null;
  let raw;
  try { raw = require('zlib').inflateSync(Buffer.concat(idat)); }
  catch { return null; }
  // Only handle 8-bit RGBA (6) and 8-bit palette (3) with tRNS — the two the
  // exporter produces. Anything else: skip rather than assert wrongly.
  if (bitDepth !== 8) return null;
  // RGBA8 (6) → alpha is byte 3 of each pixel. Palette8 (3) → the byte is a
  // palette index and alpha comes from tRNS (indices past its end are opaque).
  const bpp = colorType === 6 ? 4 : colorType === 3 ? 1 : 0;
  if (!bpp) return null;
  if (colorType === 3 && !trns) return null;   // fully opaque palette: no ink box
  const alphaAt = colorType === 6
    ? (line, x) => line[x * 4 + 3]
    : (line, x) => { const i = line[x]; return i < trns.length ? trns[i] : 255; };

  let minX = w, maxX = -1;
  const stride = w * bpp + 1;
  let prev = Buffer.alloc(w * bpp);
  for (let y = 0; y < h; y++) {
    const filt = raw[y * stride];
    const line = Buffer.from(raw.subarray(y * stride + 1, y * stride + 1 + w * bpp));
    // undo PNG filters (0 none, 1 sub, 2 up, 3 avg, 4 paeth)
    for (let i = 0; i < line.length; i++) {
      const a = i >= bpp ? line[i - bpp] : 0, b = prev[i], c = i >= bpp ? prev[i - bpp] : 0;
      if (filt === 1) line[i] = (line[i] + a) & 255;
      else if (filt === 2) line[i] = (line[i] + b) & 255;
      else if (filt === 3) line[i] = (line[i] + ((a + b) >> 1)) & 255;
      else if (filt === 4) {
        const pp = a + b - c, pa = Math.abs(pp - a), pb = Math.abs(pp - b), pc = Math.abs(pp - c);
        line[i] = (line[i] + (pa <= pb && pa <= pc ? a : pb <= pc ? b : c)) & 255;
      }
    }
    for (let x = 0; x < w; x++) {
      if (alphaAt(line, x) > 8) { if (x < minX) minX = x; if (x > maxX) maxX = x; }
    }
    prev = line;
  }
  if (maxX < 0) return null;
  return (maxX - minX + 1) / w;
}

let insetChecked = 0;
for (const p of POSES) {
  const frac = inkFraction(path.join(SPRITES, `${p}.png`));
  if (frac === null) continue;
  insetChecked++;
  assert(Math.abs(frac - INSET_TARGET) <= INSET_TOL,
    `${p} ink inset ≈ ${(INSET_TARGET * 100) | 0}% of box width (got ${(frac * 100).toFixed(1)}%)`,
    'trimmed-to-bbox sprites render oversized beside the Analyst — see D-156');
}
assert(insetChecked > 0,
  'inset measurable on at least one sprite',
  'if this trips, the exporter changed PNG format and the guard went blind');

// ── 4b. the copy swap is flag-gated too (D-155) ─────────────────────────
// The name follows the artwork or the two disagree — a ram introducing itself
// as "The Analyst", or worse, "Fleeced" printed over the Analyst's face.
const guide = read('components/AnalystGuide.tsx');
const script = read('components/analystScript.ts');
const copy = read('utils/mascotCopy.ts');

assert(/useOnboardingFeature\(\s*['"]onboarding\.mascot_ram['"]\s*\)/.test(guide),
  'AnalystGuide gates its copy on the same flag as the artwork',
  'name and face must never disagree');
assert(!/>\s*The Analyst\s*</.test(guide),
  'AnalystGuide has no hardcoded "The Analyst" in rendered copy',
  'the who-label must come from mascotName()');
assert(/mascotName\(/.test(guide), 'AnalystGuide names the speaker via mascotName()');
assert(/lineRam/.test(guide) && /lineRam/.test(script),
  'the ram opening line lives in the script and is read by the guide',
  'copy belongs in analystScript.ts, not inlined in the host');
assert(/MASCOT_NAME_ANALYST\s*=\s*'The Analyst'/.test(copy),
  'flag-off name is still exactly "The Analyst"',
  'flag off must be byte-identical, copy included');
assert(/MASCOT_NAME_RAM\s*=\s*'Fleeced'/.test(copy), 'flag-on name is "Fleeced"');
for (const f of ['screens/SettingsScreen.tsx', 'screens/settings/sections/GuideSection.tsx']) {
  const t = read(f);
  assert(!/title="The Analyst"/.test(t),
    `${f} does not hardcode the mascot name on the guided-tour toggle`);
  assert(/guideToggleTitle\(/.test(t),
    `${f} takes its toggle title from mascotCopy`);
}

// ── 5. flip survives ────────────────────────────────────────────────────
const ram = read('components/mascot/ram/index.tsx');
assert(/flip/.test(ram) && /scaleX:\s*-1/.test(ram),
  'RamAvatar honours `flip` via scaleX(-1)',
  '16 spotlight beats mirror the point pose');

// ── 6. pose vocabulary unchanged ────────────────────────────────────────
for (const p of POSES) {
  assert(new RegExp(`\\b${p}\\s*:`).test(ram), `ram sprite map covers "${p}"`);
}
assert(/AnalystPose/.test(ram),
  'RamAvatar types its pose against AnalystPose',
  'a divergent union would let the two mascots drift apart');

console.log(failures === 0
  ? '  all checks passed'
  : `  ${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
