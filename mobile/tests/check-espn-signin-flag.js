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
//   7. The smart-start "That's an ESPN league URL — choose ESPN above" hint
//      follows the chip: with the picker up but no ESPN chip it falls to the
//      screen's existing no-chip copy, and no new copy is introduced.
//   8. Web mirrors the rule (chip and selectEntryPlatform need espn.link AND
//      espn.signin; MFL untouched) while `_entryPost` keeps its unconditional
//      throw — the web never mints an ESPN/MFL entry session.
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

// ── 7. the smart-start "choose ESPN above" hint needs the chip ───────────
// Pasting an ESPN league URL used to say "choose ESPN above" whenever the
// picker was up. With espn.signin off the picker can still be up (Sleeper ·
// MFL) with no ESPN chip, so the hint points at a control that is not there.
// It must follow the chip: `platformChips` is the single source of truth for
// which chips render. When the chip is missing the screen falls to its
// EXISTING no-chip branch ("<P> leagues link after sign-in …", Settings path)
// — and no copy is invented: the setError ternary holds exactly the three
// strings that were already there.
const hintBlock = signIn.match(
  /setError\(\s*\n\s*pname && platformPickerShown[\s\S]{0,900}?\n          \);/,
);
assert(!!hintBlock, '7. the smart-start platform-hint setError is parseable');
assert(
  !!hintBlock &&
    /pname && platformPickerShown && \(platformChips as string\[\]\)\.includes\(resolved\.platform \?\? ''\)\s*\n\s*\? `That's an \$\{pname\} league URL — choose \$\{pname\} above to link it\.`/.test(
      hintBlock[0],
    ),
  "7. 'choose <P> above' is shown only when that platform's chip is in platformChips",
);
assert(
  !!hintBlock &&
    /\? `\$\{pname\} leagues link after sign-in — enter a Sleeper username here, or sign in with Apple and link your league from Settings\.`/.test(
      hintBlock[0],
    ) &&
    /: "That league URL isn't from a supported platform — paste a Sleeper league URL or your username\."/.test(
      hintBlock[0],
    ),
  '7. the existing no-chip and unsupported-platform strings are still the fallbacks',
);
// (copy only: the empty `''` fallback in the chip test is not a message)
const hintStrings = (hintBlock ? hintBlock[0].match(/`[^`]*`|"[^"]*"|'[^']*'/g) || [] : [])
  .filter((s) => s.length > 2);
assert(
  hintStrings.length === 3,
  '7. no new copy: the hint ternary holds exactly its three existing strings',
  String(hintStrings.length),
);

// ── 8. web: the ESPN chip follows espn.link AND espn.signin ──────────────
// The web never mints an entry session (`_entryPost` throws, below); its
// ESPN/MFL chips only point people to the mobile app. But with espn.signin
// off the ESPN chip would still say "Sign in and verify your ESPN account in
// the Fleeced mobile app". Mirror the mobile rule.
const webApp = fs.readFileSync(
  path.join(__dirname, '..', '..', 'web', 'js', 'app.js'),
  'utf8',
);
const codeOnly = (s) =>
  s.split('\n').filter((l) => !/^\s*\/\//.test(l)).join('\n');
const applyFn = webApp.match(/function _applyPlatformOptionsFlag\(\) \{[\s\S]*?\n    \}\n/);
const selectFnWeb = webApp.match(/function selectEntryPlatform\(p\) \{[\s\S]*?\n    \}\n/);
assert(!!applyFn && !!selectFnWeb, '8. web chip-row and selectEntryPlatform are parseable');
assert(
  !!applyFn &&
    /const espnOn = optionsOn && window\.FTF_FLAG\('espn\.link'\) && window\.FTF_FLAG\('espn\.signin'\);/.test(
      applyFn[0],
    ),
  '8. the web ESPN chip is shown only when espn.link AND espn.signin are on',
);
assert(
  !!applyFn &&
    /const mflOn\s+= optionsOn && window\.FTF_FLAG\('mfl\.link'\);/.test(applyFn[0]),
  '8. the web MFL chip depends on mfl.link alone',
);
assert(
  !!applyFn &&
    /\(_entryPlatformSel === 'espn' && !espnOn\)/.test(applyFn[0]),
  '8. a selected web ESPN chip falls back to Sleeper through the same espnOn',
);
assert(
  !!selectFnWeb &&
    /if \(p === 'espn' && !window\.FTF_FLAG\('espn\.signin'\)\) return;\s*\n\s*_entryPlatformSel = p;/.test(
      selectFnWeb[0],
    ),
  "8. selectEntryPlatform('espn') returns before selecting when espn.signin is off",
);
const webSigninUses = (codeOnly(webApp).match(/espn\.signin/g) || []).length;
assert(
  webSigninUses === 2,
  '8. espn.signin is read in exactly two web code sites (chip row, selectEntryPlatform)',
  String(webSigninUses),
);
assert(
  /window\.FTF_FLAG\s*=\s*function \(key\) \{ return !!\(window\.FTF_FLAGS && window\.FTF_FLAGS\[key\]\); \};/.test(
    webApp,
  ),
  '8. (documents) FTF_FLAG reads a missing key as false — an unsent espn.signin hides the chip',
);
const entryPostWeb = webApp.match(/async function _entryPost\(body\) \{([\s\S]*?)\n    \}\n/);
assert(!!entryPostWeb, '8. web _entryPost is parseable');
assert(
  !!entryPostWeb &&
    /^throw new Error\('[^']*'\);$/.test(codeOnly(entryPostWeb[1]).trim()),
  '8. web _entryPost still throws unconditionally — no web ESPN/MFL sign-in (legal)',
);

if (failures) {
  console.error(`\n${failures} failure(s)`);
  process.exit(1);
}
console.log('\nOK');
