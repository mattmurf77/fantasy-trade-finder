#!/usr/bin/env node
// `espn.signin` — structural guard (client half; the server half registers
// the flag in config/features.json and 404s the ESPN entry route).
//
// The flag lets the operator turn off ONLY the ESPN chip on the sign-in
// screen's platform picker, while MFL sign-in and ESPN league linking in
// Settings stay on. Each claim below protects a specific failure mode:
//
//   1. SignIn reads `espn.signin`, and the ESPN chip is included only behind
//      BOTH `espn.link` AND `espn.signin`. Dropping either gate either
//      removes the new off switch or revives the old one's blind spot.
//   2. The MFL chip does not depend on `espn.signin` — turning ESPN sign-in
//      off must not take MFL sign-in with it.
//   3. A selected ESPN chip falls back to Sleeper when EITHER flag goes off.
//      Flag revalidation can withdraw the chip mid-session; without this the
//      user is stranded on the ESPN panel with no chip, and its button opens
//      an entry sheet whose route now 404s.
//   4. `espn.signin` is consumed in exactly those places (declaration, chip
//      list, fallback, effect deps) and nowhere else in mobile/src. A second
//      consumer would widen "hides only the chip" — e.g. Settings → link
//      ESPN league, LeaguePicker's auto-open, or PlatformLinkSheet (MFL).
//   5. The only sessionless (entry-mode) EspnLinkSheet mount is SignIn's, and
//      the button that opens it renders only for a selected ESPN chip. A new
//      entry mount elsewhere would bypass the gate above.
//   6. The flag is NOT in useFeatureFlags' LAUNCHED_FLAG_DEFAULTS. That map
//      fails open from first paint; this flag is the operator's off switch
//      and a server `false` must never paint the chip, even on a first boot.
//
// Run: node tests/check-espn-signin-flag.js
//   (or: npm run test:espn-signin-flag)

'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const SRC = path.join(__dirname, '..', 'src');
function read(rel) {
  return fs.readFileSync(path.join(SRC, rel), 'utf8');
}
function walk(dir, out = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(p, out);
    else if (/\.(tsx?|jsx?)$/.test(ent.name)) out.push(p);
  }
  return out;
}

const signIn = read('screens/SignInScreen.tsx');

// ── 1. the ESPN chip is behind BOTH flags ────────────────────────────────
assert(
  /const espnSignInOn = useFlag\('espn\.signin'\);/.test(signIn),
  '1. SignIn reads espn.signin',
);
const chipList = signIn.match(
  /const platformChips: Array<[^\n]*> = \[([\s\S]{0,300}?)\n  \];/,
);
assert(!!chipList, '1. platformChips list is parseable');
const chipLines = chipList ? chipList[1].split('\n') : [];
const espnChipLine = chipLines.find((l) => /'espn'/.test(l)) || '';
const mflChipLine = chipLines.find((l) => /'mfl'/.test(l)) || '';
assert(
  /\.\.\.\(espnLinkOn && espnSignInOn \? \(\['espn'\] as const\) : \[\]\)/.test(espnChipLine),
  '1. the ESPN chip is included only when espn.link AND espn.signin are on',
  espnChipLine.trim(),
);

// ── 2. the MFL chip does not depend on espn.signin ───────────────────────
assert(
  /\.\.\.\(mflLinkOn \? \(\['mfl'\] as const\) : \[\]\)/.test(mflChipLine) &&
    !/espn/i.test(mflChipLine),
  '2. the MFL chip depends on mfl.link alone',
  mflChipLine.trim(),
);

// ── 3. de-flag fallback covers either ESPN flag, and leaves MFL alone ────
const fallback = signIn.match(
  /useEffect\(\(\) => \{\s*\n\s*if \(\s*\n([\s\S]{0,400}?)\)\s*\{\s*\n\s*setEntryPlatform\('sleeper'\);\s*\n\s*\}\s*\n\s*\}, \[([^\]]*)\]\);/,
);
assert(!!fallback, '3. the de-flag fallback effect is parseable');
assert(
  !!fallback &&
    /\(entryPlatform === 'espn' && !\(espnLinkOn && espnSignInOn\)\)/.test(fallback[1]),
  '3. a selected ESPN chip falls back to Sleeper when espn.link OR espn.signin goes off',
);
assert(
  !!fallback && /\(entryPlatform === 'mfl' && !mflLinkOn\)/.test(fallback[1]),
  '3. a selected MFL chip falls back on mfl.link alone',
);
assert(
  !!fallback && /\bespnSignInOn\b/.test(fallback[2]),
  '3. espnSignInOn is an effect dependency (a revalidation re-runs the fallback)',
  fallback ? fallback[2] : '',
);

// ── 4. espn.signin is consumed only by the chip + fallback ───────────────
// Strip the four allowed uses from SignIn, then nothing may remain.
const stripped = signIn
  .replace(/const espnSignInOn = useFlag\('espn\.signin'\);/, '')
  .replace(/\.\.\.\(espnLinkOn && espnSignInOn \? /, '')
  .replace(/!\(espnLinkOn && espnSignInOn\)/, '')
  .replace(/\[entryPlatform, espnLinkOn, espnSignInOn, mflLinkOn\]/, '');
assert(
  !/espnSignInOn/.test(stripped),
  '4. espnSignInOn has no use in SignIn beyond the chip list and the fallback',
);
const flagUsers = walk(SRC)
  .filter((f) => /espn\.signin/.test(fs.readFileSync(f, 'utf8')))
  .map((f) => path.relative(SRC, f))
  .sort();
assert(
  flagUsers.length === 1 && flagUsers[0] === path.join('screens', 'SignInScreen.tsx'),
  "4. 'espn.signin' appears in mobile/src only in SignInScreen (Settings, LeaguePicker, PlatformLinkSheet, EspnLinkSheet and RootNav are not gated on it)",
  flagUsers.join(', '),
);

// ── 5. the sessionless ESPN entry mount is SignIn's, behind the chip ─────
const entryMounts = walk(SRC)
  .filter((f) => /<EspnLinkSheet\s+entry\b/.test(fs.readFileSync(f, 'utf8')))
  .map((f) => path.relative(SRC, f))
  .sort();
assert(
  entryMounts.length === 1 && entryMounts[0] === path.join('screens', 'SignInScreen.tsx'),
  '5. <EspnLinkSheet entry> is mounted only by SignInScreen',
  entryMounts.join(', '),
);
assert(
  /setEntrySheet\(entryPlatform === 'espn' \? 'espn' : 'mfl'\)/.test(signIn) &&
    /const nonSleeperEntry = platformPickerShown && entryPlatform !== 'sleeper';/.test(signIn),
  '5. the entry sheet opens only from the platform panel, which needs a selected non-Sleeper chip',
);

// ── 6. espn.signin is NOT a launched default (fail-safe) ─────────────────
// LAUNCHED_FLAG_DEFAULTS fails OPEN from first paint. This flag must not: a
// server `false` (the ESPN entry route failing its review) must never paint
// the chip, not even for one frame on a first boot. Absent ⇒ `!!undefined` ⇒
// hidden until a successful fetch says true. (landing.platform_options is
// absent from the map too, so the whole chip row is hidden on a first boot
// anyway — omitting this key adds no pop-in.)
const flagsSrc = read('state/useFeatureFlags.ts');
const defaultsBlock = flagsSrc.match(
  /const LAUNCHED_FLAG_DEFAULTS: FlagMap = \{([\s\S]*?)\n\};/,
);
assert(!!defaultsBlock, '6. LAUNCHED_FLAG_DEFAULTS is parseable');
assert(
  !!defaultsBlock && /'espn\.link': true/.test(defaultsBlock[1]),
  '6. (sanity) the parsed block is the real defaults map — espn.link is in it',
);
assert(
  !!defaultsBlock && !/espn\.signin/.test(defaultsBlock[1]),
  "6. LAUNCHED_FLAG_DEFAULTS has no 'espn.signin' key (fail-safe, not fail-open)",
);

if (failures) {
  console.error(`\n${failures} failure(s)`);
  process.exit(1);
}
console.log('\nOK');
