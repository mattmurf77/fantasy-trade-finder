#!/usr/bin/env node
// Settings IA — the testID inventory (settings-ia-hub, 2026-08-18).
//
// WHY THIS EXISTS. Plan §8: "Every existing settings.* testID moves with its
// row unchanged." testIDs are the app's only stable handles on individual
// controls — they are what a QA note, a bug report, and `testid-lint.sh`
// point at. A refactor that renames or drops one does not fail `tsc`, does
// not fail testid-lint (which polices FORM, not INVENTORY: it cannot know a
// row used to exist), and does not fail at runtime. It just quietly breaks
// every reference to that control.
//
// The 1,712-line SettingsScreen fanned out into twelve section modules, so
// this walks all of src/ rather than one file: a testID is "still shipped"
// if it resolves anywhere under mobile/src, wherever the split put it.
//
// Three inventories:
//   1. SHIPPED — present in 1.13.2, must survive the split unchanged.
//   2. NEW — added by this plan (the version row, the hub rows). Asserting
//      these means the hub cannot ship half-built.
//   3. DELETED — `settings.close-btn` was the modal's header ✕ (#130). The
//      modal is gone (plan §5), so the testID must be gone from src AND from
//      mobile/.maestro, whose flows tap it. A .maestro flow referencing a
//      dead id is a flow that can only fail; D-056 keeps those files as
//      historical artifacts, and history should not name a control that
//      never existed in the shipped build.
//
// Matching is on real `testID=` attributes parsed out of source, not raw
// substring search, so an id mentioned in a comment cannot count as shipped.
//
// Run: node tests/check-settings-testids.js   (or: npm run test:settings-testids)

'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
const ok   = (n) => console.log(`PASS  ${n}`);
const fail = (n, why) => { failures += 1; console.error(`FAIL  ${n}\n      ${why}`); };

const MOBILE = path.join(__dirname, '..');
const SRC = path.join(MOBILE, 'src');
const MAESTRO = path.join(MOBILE, '.maestro');

// ── Inventories (plan §8) ─────────────────────────────────────────────────

// Shipped in 1.13.2. Each must still resolve somewhere under src/.
const SHIPPED = [
  'settings.link-espn',
  'settings.link-platform',
  'settings.sleeper-disconnect',
  'settings.espn-disconnect',
  'settings.mfl-disconnect',
  'settings.export-data',
  'settings.help-faq',
  'settings.test-stages',
  'settings.guided-tour-toggle',
  'settings.link-apple-btn',
  'settings.notif-denied-banner',
];

// Template-generated ids: one per segmented-control option, so the check is
// on the PREFIX (`settings.stud-tax.${o.key}`), not on a fixed string.
//
// `settings.pick-pricing.` left this list on 2026-08-21 (D-144) — see
// DELETED_PREFIXES below. It is not "temporarily missing": the operator ruled
// pick pricing is "not an opt-in or even an option to flip", so the control
// it handled no longer exists in any build.
const SHIPPED_PREFIXES = [
  'settings.stud-tax.',
];

// Added by this plan. `file` pins where it must live when that matters.
const NEW = [
  { id: 'settings.version',              file: null,                     why: 'F7 — the version + build row on About' },
  { id: 'settings.hub.identity',         file: 'SettingsHubScreen.tsx',  why: 'hub identity block' },
  { id: 'settings.hub.leagues',          file: 'SettingsHubScreen.tsx',  why: 'hub group row' },
  { id: 'settings.hub.ranking',          file: 'SettingsHubScreen.tsx',  why: 'hub group row' },
  { id: 'settings.hub.trade-values',     file: 'SettingsHubScreen.tsx',  why: 'hub group row' },
  { id: 'settings.hub.notifications',    file: 'SettingsHubScreen.tsx',  why: 'hub group row' },
  { id: 'settings.hub.account',          file: 'SettingsHubScreen.tsx',  why: 'hub group row' },
  { id: 'settings.hub.about',            file: 'SettingsHubScreen.tsx',  why: 'hub group row' },
];

// The Testing hub row is the seventh group row but is gated
// (`__DEV__ || testing.stage_users`), so it is listed apart from the six
// that every release build renders.
const NEW_GATED = [
  { id: 'settings.hub.testing', file: 'SettingsHubScreen.tsx', why: 'hub group row, dev/tester builds only' },
];

// Dies with the modal presentation (plan §5, §8).
const DELETED = 'settings.close-btn';

// Templated ids that must NO LONGER be generated anywhere under src/.
// `settings.pick-pricing.*` — the Pick pricing segmented control, removed
// 2026-08-21 (D-144) when the operator ruled market pricing unconditional.
// Asserted as an absence, not merely dropped from SHIPPED_PREFIXES, so a
// well-meaning revert that re-adds the control fails here loudly instead of
// quietly restoring a setting the operator deleted.
const DELETED_PREFIXES = [
  { prefix: 'settings.pick-pricing.',
    why: 'the Pick pricing control was removed 2026-08-21 (D-144) — pick '
       + 'pricing is unconditional and is no longer a setting' },
];

// ── Collect every testID= attribute value under src/ ──────────────────────
const walk = (dir, out = []) => {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(p);
  }
  return out;
};

// testID="x" | testID={'x'} | testID={"x"} | testID={`x${...}`}
const TESTID_RE =
  /testID\s*=\s*(?:"([^"]*)"|'([^']*)'|\{\s*"([^"]*)"\s*\}|\{\s*'([^']*)'\s*\}|\{\s*`([^`]*)`\s*\})/g;

const files = walk(SRC);
const idsToFiles = new Map();   // testID value → Set(relative file)
for (const f of files) {
  const text = fs.readFileSync(f, 'utf8');
  const rel = path.relative(MOBILE, f);
  for (const m of text.matchAll(TESTID_RE)) {
    const v = m[1] ?? m[2] ?? m[3] ?? m[4] ?? m[5];
    if (!v) continue;
    if (!idsToFiles.has(v)) idsToFiles.set(v, new Set());
    idsToFiles.get(v).add(rel);
  }
}
const allIds = [...idsToFiles.keys()];
const settingsIds = allIds.filter((i) => i.startsWith('settings.')).sort();

console.log(`Scanned ${files.length} source files under mobile/src — `
  + `${allIds.length} testIDs total, ${settingsIds.length} in the settings.* namespace.\n`);

const where = (id) => [...(idsToFiles.get(id) || [])].join(', ');

// ── 1. Shipped ids survived the split ─────────────────────────────────────
// "Resolves under src/" is not enough on its own while Phase 4 is pending:
// the legacy flat `src/screens/SettingsScreen.tsx` still carries every one
// of these ids and would satisfy a whole-tree search all by itself, so a row
// that never made it into the new subtree would pass unnoticed. (Verified:
// renaming settings.espn-disconnect in PlatformDisconnectSection.tsx passes
// a whole-tree search and fails this one.) So each shipped id must resolve
// inside `src/screens/settings/` — the tree that actually renders once the
// hub is on. This assertion also survives Phase 4 deleting the legacy file.
const NEW_TREE = path.join('src', 'screens', 'settings') + path.sep;
const inNewTree = (id) => [...(idsToFiles.get(id) || [])].some((f) => f.startsWith(NEW_TREE));
{
  const missing  = SHIPPED.filter((id) => !idsToFiles.has(id));
  const stranded = SHIPPED.filter((id) => idsToFiles.has(id) && !inNewTree(id));
  if (missing.length === 0 && stranded.length === 0) {
    ok(`all ${SHIPPED.length} shipped settings.* testIDs still resolve, and all of them `
       + 'inside src/screens/settings/ (not only in the legacy flat screen)');
    for (const id of SHIPPED) console.log(`      ${id.padEnd(32)} ${where(id)}`);
  }
  if (missing.length > 0) {
    fail('all shipped settings.* testIDs still resolve',
         `gone from the tree — the control was renamed or dropped in the split: ${missing.join(', ')}`);
  }
  if (stranded.length > 0) {
    fail('shipped settings.* testIDs live in the new settings subtree',
         stranded.map((id) => `${id} only in ${where(id)}`).join('; ')
           + ' — present in the legacy screen but missing from the page that now renders');
  }

  const prefixHit = (p) => allIds.filter((id) => id.startsWith(p));
  const badPrefix = SHIPPED_PREFIXES.filter((p) => {
    const hits = prefixHit(p);
    return hits.length === 0 || !hits.some(inNewTree);
  });
  if (badPrefix.length === 0) {
    for (const p of SHIPPED_PREFIXES) {
      console.log(`      ${(p + '*').padEnd(32)} ${prefixHit(p).map(where).join(', ')}`);
    }
    ok(`all ${SHIPPED_PREFIXES.length} templated testID prefix(es) still generate ids `
       + `in the new subtree (${SHIPPED_PREFIXES.join(', ')})`);
  } else {
    fail('templated testID prefixes still generate ids in the new subtree',
         badPrefix.map((p) => `${p}* → ${prefixHit(p).map(where).join(', ') || 'nothing'}`).join('; ')
           + ' — the segmented control lost its handles');
  }

  // Retired prefixes: the inverse assertion. A generated id under one of
  // these means a removed control came back.
  for (const { prefix, why } of DELETED_PREFIXES) {
    const hits = prefixHit(prefix);
    if (hits.length === 0) {
      ok(`${prefix}* generates no testIDs — ${why}`);
    } else {
      fail(`${prefix}* generates no testIDs`,
           `still generated at ${hits.map(where).join(', ')} — ${why}`);
    }
  }
}

// ── 2. New ids exist (and, where pinned, in the right module) ─────────────
{
  const check = (list, label) => {
    const problems = [];
    for (const spec of list) {
      if (!idsToFiles.has(spec.id)) {
        problems.push(`${spec.id} missing (${spec.why})`);
        continue;
      }
      if (spec.file) {
        const homes = [...idsToFiles.get(spec.id)];
        if (!homes.some((h) => h.endsWith(spec.file))) {
          problems.push(`${spec.id} lives in ${homes.join(', ')}, expected ${spec.file}`);
        }
      }
    }
    if (problems.length === 0) {
      ok(`${label}: all ${list.length} present`);
      for (const spec of list) console.log(`      ${spec.id.padEnd(32)} ${where(spec.id)}`);
    } else {
      fail(label, problems.join('; '));
    }
  };

  check(NEW, 'new testIDs (version row + identity block + the six release hub rows)');
  check(NEW_GATED, 'new gated testID (Testing hub row)');
}

// ── 3. settings.close-btn is gone, everywhere ─────────────────────────────
{
  // 3a. src/ — as a testID attribute, and as a raw mention on a code line
  // (a stale onPress handler or const naming it is just as dead).
  const asAttr = idsToFiles.has(DELETED) ? where(DELETED) : null;
  const rawHits = [];
  for (const f of files) {
    const lines = fs.readFileSync(f, 'utf8').split('\n');
    lines.forEach((l, i) => {
      const t = l.trim();
      if (t.startsWith('//') || t.startsWith('*') || t.startsWith('/*')) return;
      if (l.includes(DELETED)) rawHits.push(`${path.relative(MOBILE, f)}:${i + 1}`);
    });
  }
  if (!asAttr && rawHits.length === 0) {
    ok(`${DELETED} is gone from mobile/src — it died with the modal presentation (#130's ✕)`);
  } else {
    fail(`${DELETED} is gone from mobile/src`,
         `still referenced at ${(asAttr ? [asAttr] : []).concat(rawHits).join(', ')} — `
           + 'plan §5 removes the header close control along with the page-sheet');
  }

  // 3b. mobile/.maestro — flows are frozen artifacts under D-056, but a flow
  // that taps a control the build no longer has is a lie in the record.
  if (!fs.existsSync(MAESTRO)) {
    ok('mobile/.maestro absent — nothing to check');
  } else {
    const yamls = [];
    const walkY = (dir) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, e.name);
        if (e.isDirectory()) walkY(p);
        else if (/\.ya?ml$/.test(e.name)) yamls.push(p);
      }
    };
    walkY(MAESTRO);
    const hits = [];
    for (const f of yamls) {
      fs.readFileSync(f, 'utf8').split('\n').forEach((l, i) => {
        if (l.trim().startsWith('#')) return;   // YAML comment
        if (l.includes(DELETED)) hits.push(`${path.relative(MOBILE, f)}:${i + 1}`);
      });
    }
    if (hits.length === 0) {
      ok(`${DELETED} is gone from mobile/.maestro (${yamls.length} flow files scanned)`);
    } else {
      fail(`${DELETED} is gone from mobile/.maestro`,
           `still tapped at ${hits.join(', ')} — the control no longer exists in the build`);
    }
  }
}

// ── 4. Audit trail: the whole settings.* namespace as it stands ───────────
console.log('\nsettings.* namespace after the split:');
for (const id of settingsIds) console.log(`  ${id.padEnd(36)} ${where(id)}`);

console.log(failures === 0
  ? `\nAll settings testID inventory checks passed `
    + `(${SHIPPED.length} shipped + ${SHIPPED_PREFIXES.length} templated kept, `
    + `${NEW.length + NEW_GATED.length} added, 1 deleted).`
  : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
