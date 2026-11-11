#!/usr/bin/env node
// The playoff forecast's outlook suggestion in the outlook selector
// (TradeDnaSheet, opened by Home's "Review outlook" through TradesScreen).
//
// WHY THIS EXISTS. The sheet autosaves every tap. A suggestion that reached a
// draft setter, an effect or the save queue would change a user's saved
// outlook because a forecast moved, with no tap from them. The contract is:
// the suggestion MARKS one card and nothing else; the saved selection stays
// selected; the only write is the user's own tap on a card. With no
// suggestion the sheet renders as it always has. Under D-056 there is no
// simulator, so these are claims about code shape.
//
//   1  TradeDnaSheet: `suggestedOutlook` reaches exactly one expression
//   2  TradeDnaSheet: that expression only feeds the tag and the a11y label
//   3  TradeDnaSheet: selection, seeding and the save path are untouched
//   4  TradesScreen: the route param is validated, held, passed and cleared
//
// Dependency-free: text assertions over comment-stripped source.
// Run: node tests/check-outlook-suggestion.js  (npm run test:outlook-suggestion)
'use strict';

const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'src');
let failures = 0;
const assert = (cond, name, why) => {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`);
  }
};
const strip = (s) =>
  s
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
const read = (rel) => strip(fs.readFileSync(path.join(SRC, rel), 'utf8'));
const count = (hay, needle) => hay.split(needle).length - 1;
const words = (hay, word) => (hay.match(new RegExp(`\\b${word}\\b`, 'g')) || []).length;

const sheet = read('components/TradeDnaSheet.tsx');
const trades = read('screens/TradesScreen.tsx');

// ── 1. the prop reaches exactly one expression ─────────────────────────────
{
  assert(/suggestedOutlook\?: 'jets' \| 'rebuilder' \| 'contender' \| 'championship' \| null;/.test(sheet),
    '1a. suggestedOutlook is an optional prop over the four recommendable outlooks');
  assert(words(sheet, 'suggestedOutlook') === 3
    && sheet.includes('export default function TradeDnaSheet({ visible, onClose, full, openSource, suggestedOutlook }: Props) {')
    && count(sheet, 'const suggested = suggestedOutlook === o.key;') === 1,
    '1b. suggestedOutlook is read once: `const suggested = suggestedOutlook === o.key;`',
    `found ${words(sheet, 'suggestedOutlook')} references (expected the prop type, the destructure and one comparison). ` +
    'A second read is how a suggestion reaches a setter, an effect or a save.');
}

// ── 2. `suggested` only marks ──────────────────────────────────────────────
{
  assert(words(sheet, 'suggested') === 5
    && sheet.includes('suggested ? `${o.title}, suggested from your playoff chance` : o.title')
    && /\{suggested \? \(\s*<View testID="trade-dna\.outlook\.suggested" style=\{styles\.outCardSuggested\}>\s*<Badge label="Suggested" color=\{flare\.base\} colorText \/>\s*<\/View>\s*\) : null\}/.test(sheet),
    '2a. `suggested` feeds the accessibility label and the flare "Suggested" tag, and nothing else',
    `found ${words(sheet, 'suggested')} uses of \`suggested\` (expected the declaration, the label condition and its text, the tag condition and its testID)`);
  assert(count(sheet, 'trade-dna.outlook.suggested') === 1 && count(sheet, 'label="Suggested"') === 1,
    '2b. one tag, on the outlook card');
}

// ── 3. selection, seeding and saving are what they were ────────────────────
{
  assert(count(sheet, 'const sel = draftOutlook === o.key;') === 1
    && sheet.includes('accessibilityState={{ selected: sel, checked: sel }}')
    && sheet.includes('sel && styles.outCardSel'),
    '3a. the selected card is still the draft outlook alone');
  const seed = (/useEffect\(\(\) => \{\s*if \(visible && dnaTouched\.current\) return;[\s\S]*?\}, \[prefs, visible\]\);/.exec(sheet) || [''])[0];
  assert(/setDraftOutlook\(\s*\(prefs\?\.team_outlook as NonNullable<Outlook>\) \?\?\s*\(prefs\?\.inferred_outlook as NonNullable<Outlook>\) \?\?\s*null,\s*\);/.test(seed),
    '3b. the draft is seeded from the saved prefs only (no auto-select of a suggestion)');
  assert(count(sheet, 'setDraftOutlook(') === 3,
    '3c. setDraftOutlook has its three call sites: the prefs seed, the failed-save reset and the tap',
    `found ${count(sheet, 'setDraftOutlook(')}`);
  assert(count(sheet, 'pickOutlook(') === 1 && sheet.includes('onPress={() => pickOutlook(o.key)}'),
    '3d. pickOutlook runs only from a press on an outlook card');
  assert(count(sheet, 'saveLeaguePreferences(') === 1,
    '3e. the sheet still has one preferences write');
  const effects = sheet.match(/useEffect\(\(\) => \{[\s\S]*?\n  \}, \[[^\]]*\]\);/g) || [];
  const writers = effects.filter((e) => /queueDnaSave\(|flushDnaSave\(|saveOutlook\.mutate|saveLeaguePreferences\(|pickOutlook\(/.test(e));
  assert(effects.length > 0 && writers.length === 0,
    '3f. no effect saves a preference (nothing is written on open)',
    `${writers.length} effect(s) reach the save path`);
}

// ── 4. TradesScreen carries the suggestion from the route to the sheet ─────
{
  const effect = (/useEffect\(\(\) => \{\s*if \(route\?\.params\?\.editDna\) \{[\s\S]*?\}, \[route\?\.params\?\.editDna\]\);/.exec(trades) || [''])[0];
  assert(effect.includes('const suggest = route?.params?.suggestOutlook;')
    && effect.includes("suggest === 'jets' || suggest === 'rebuilder' || suggest === 'contender' || suggest === 'championship'")
    && effect.includes('? { leagueId, outlook: suggest }')
    && effect.includes(': null,'),
    '4a. the editDna effect reads suggestOutlook and keeps only one of the four outlooks');
  assert(effect.includes('navigation?.setParams?.({ editDna: undefined, suggestOutlook: undefined });'),
    '4b. the param is cleared with editDna');
  assert(count(trades, 'route?.params?.suggestOutlook') === 1,
    '4c. the route param is read in that effect only');
  const close = (/function handleEditSheetClose\(\) \{[\s\S]*?\n  \}/.exec(trades) || [''])[0];
  assert(close.includes('setDnaSuggestion(null);'), '4d. closing the sheet clears the suggestion');
  assert(count(trades, 'setDnaSuggestion(') === 2,
    '4e. the suggestion is set from the route param and cleared on close, nowhere else',
    `found ${count(trades, 'setDnaSuggestion(')} setter calls`);
  assert(count(trades, 'suggestedOutlook={dnaSuggestion && dnaSuggestion.leagueId === leagueId ? dnaSuggestion.outlook : null}') === 1
    && words(trades, 'dnaSuggestion') === 4,
    '4f. the suggestion is read only to mark the sheet, and only for the league it was made for',
    `found ${words(trades, 'dnaSuggestion')} reads of dnaSuggestion (expected the state and the one prop expression)`);
}

{
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
  assert(pkg.scripts['test:outlook-suggestion'] === 'node tests/check-outlook-suggestion.js',
    'npm run test:outlook-suggestion runs this suite');
}

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log('\noutlook-suggestion: all checks passed');
