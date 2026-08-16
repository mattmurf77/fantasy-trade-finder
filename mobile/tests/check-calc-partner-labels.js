#!/usr/bin/env node
// #306 (D-306-1/D-306-2) — partner-chip pick-equivalent labels on the
// in-league calculator.
//
// WHY THIS EXISTS. The graduated server now sends `value_label` per
// position and `picks.value_label` per team, and the chip must render the
// LABEL with the raw numeric ONLY as an old-server fallback — plus speak
// the same thing to VoiceOver. Every failure mode here is silent: a
// numeric-first precedence swap renders numbers forever and looks exactly
// like an old server; a sighted-only relabel leaves VoiceOver reading raw
// values under a correct-looking screen. The component therefore routes
// BOTH surfaces through one pair of helpers (segmentText/segmentSpoken)
// whose label-first precedence is what this file pins. Each assertion
// names the sabotage it detects.
//
// Run: node tests/check-calc-partner-labels.js

'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const ROOT = path.join(__dirname, '..');
function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), 'utf8');
}
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
}

const src = stripComments(read('src/components/InLeagueCalculator.tsx'));

// ── Sabotage "numeric-first": swapping precedence so the number renders
// even when the label is present. The visible helper must read `.label`
// FIRST with the numeric strictly behind `??`.
assert(
  /segmentText\s*=\s*\(s: SummarySegment\): string =>\s*s\.label \?\? Math\.round\(s\.value\)\.toLocaleString\(\)/.test(src),
  'segmentText renders the label first, numeric only as ?? fallback',
);
// Same for the spoken form ("≈3 firsts" → "about 3 firsts").
assert(
  /segmentSpoken\s*=\s*\(s: SummarySegment\): string =>\s*s\.label \? s\.label\.replace\('≈', 'about '\) : String\(Math\.round\(s\.value\)\)/.test(src),
  'segmentSpoken speaks the label first, numeric only as fallback',
);

// ── Sabotage "sighted-only fix": relabel the visible line but leave the
// a11y string on raw numbers. Both surfaces must draw from the SAME
// helpers — and no raw Math.round(summary…) bypass may exist anywhere.
assert(
  src.includes('segmentSpoken(summary.pos[pos])'),
  'a11ySummary positions speak through segmentSpoken',
);
assert(
  src.includes('segmentSpoken(summary.picks)'),
  'a11ySummary picks segment speaks through segmentSpoken',
);
assert(
  src.includes('segmentText(summary.pos[pos])'),
  'visible summary positions render through segmentText',
);
assert(
  src.includes('segmentText(summary.picks)'),
  'visible summary picks segment renders through segmentText',
);
assert(
  !/Math\.round\(summary/.test(src),
  'no raw Math.round(summary…) bypass outside the helpers',
);

// ── partnerSummaries must actually CAPTURE the server labels (dropping
// them at the memo renders the fallback forever — indistinguishable from
// an old server).
for (const pos of ['QB', 'RB', 'WR', 'TE']) {
  assert(
    src.includes(`t.positions?.${pos}?.value_label`),
    `partnerSummaries captures ${pos} value_label`,
  );
}
assert(
  src.includes('t.picks.value_label'),
  'partnerSummaries captures picks.value_label (D-306-2 — the literal-count label, never a client conversion of picks.value)',
);

// ── Labels are longer than the numbers they replace: the summary line must
// allow two lines so tail segments (TE, Picks) survive ellipsis.
const lineIdx = src.indexOf('calc.partner-summary.');
const lineRegion = src.slice(Math.max(0, lineIdx - 400), lineIdx + 400);
assert(lineIdx !== -1, 'partner summary line testID present');
assert(
  /numberOfLines=\{2\}/.test(lineRegion),
  'summary line allows numberOfLines={2}',
);

process.exit(failures ? 1 : 0);
