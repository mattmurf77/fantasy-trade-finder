#!/usr/bin/env node
// Static test: the root .easignore repeats every secret, credential, database
// and env-file pattern from every tracked .gitignore (2026-10-15).
//
// Once .easignore exists, eas-cli stops reading .gitignore files and copies the
// working tree into the archive it uploads to EAS ("if .easignore exists,
// .gitignore files are not used" — eas-cli vcs/local.js). `eas build:inspect
// --stage archive` showed secrets.local.env, data/*.db, .env files, signing
// files and the qa scratch DBs all landing in that archive. This check stops a
// new sensitive .gitignore line from silently reopening the hole.
//
// Run: node tests/check-easignore.js

'use strict';

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.join(__dirname, '..', '..');

// A .gitignore line is sensitive if it names a secret, credential, database or
// env file, or a local data / QA-scratch directory that holds DB copies.
const SENSITIVE =
  /secret|\.env|\.db$|\.p8$|\.p12$|\.pem$|\.key$|\.jks$|\.mobileprovision$|^\/?data\/$|^\/?qa\//;

let failures = 0;
function fail(msg) { failures += 1; console.error(`FAIL  ${msg}`); }

function patterns(file) {
  return fs
    .readFileSync(file, 'utf8')
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#') && !l.startsWith('!'));
}

const easignorePath = path.join(ROOT, '.easignore');
if (!fs.existsSync(easignorePath)) {
  console.error('no .easignore at the repo root — nothing to check (was it removed?)');
  process.exit(2);
}
const eas = new Set(patterns(easignorePath));

// Anchored directory entries (`/mockups/`) drop whole trees, so a .gitignore
// inside one of them can't leak anything.
const droppedDirs = [...eas]
  .filter((p) => p.startsWith('/') && p.endsWith('/'))
  .map((p) => p.slice(1, -1));

// gitignore semantics: a slash at the start or middle anchors a pattern to its
// .gitignore's directory; without one it matches at any depth below it.
function covered(p, dir) {
  const bare = p.replace(/^\//, '');
  const prefix = dir ? `${dir}/` : '';
  const anchored = p.replace(/\/$/, '').includes('/');
  // An unanchored line needs an unanchored twin: `/x` would only cover the root.
  const accept = anchored ? [`${prefix}${bare}`, `/${prefix}${bare}`] : [p];
  if (accept.some((a) => eas.has(a))) return true;
  // A literal file name is covered by an unanchored extension glob (Thumbs.db ← *.db).
  const ext = /^[^*/]+(\.[A-Za-z0-9]+)$/.exec(bare);
  return Boolean(ext && eas.has(`*${ext[1]}`));
}

const gitignores = execFileSync('git', ['ls-files', '-z', '--', '.gitignore', '*/.gitignore'], {
  cwd: ROOT,
  encoding: 'utf8',
})
  .split('\0')
  .filter(Boolean);

let checked = 0;
for (const rel of gitignores) {
  const dir = path.posix.dirname(rel) === '.' ? '' : path.posix.dirname(rel);
  if (droppedDirs.some((d) => dir === d || dir.startsWith(`${d}/`))) continue;
  for (const p of patterns(path.join(ROOT, rel))) {
    if (!SENSITIVE.test(p)) continue;
    checked += 1;
    if (!covered(p, dir)) {
      fail(`${rel}: "${p}" is gitignored but not in .easignore, so EAS would upload it`);
    }
  }
}

if (checked === 0) {
  console.error('no sensitive .gitignore lines found — check the regex or the git ls-files call');
  process.exit(2);
}

if (failures) {
  console.error(`\n${failures} of ${checked} sensitive .gitignore pattern(s) missing from .easignore.`);
  process.exit(1);
}
console.log(`ok    all ${checked} sensitive .gitignore pattern(s) are repeated in .easignore`);
