#!/usr/bin/env node
// Static test: the app-level privacy manifest ships and declares the
// required-reason APIs the app and its pods use (N4, 2026-10-23). A missing
// declaration draws ITMS-91053 on upload.
//
// The floor below comes from a 2026-10-23 scan of every native pod source in
// node_modules (101 podspecs). The categories used are FileTimestamp,
// SystemBootTime, DiskSpace and UserDefaults. ActiveKeyboards isn't used.
// Several pods ship no manifest of their own (@react-native-cookies/cookies,
// expo-document-picker, RN Settings, CoreModules and jsi), so the app-level
// file must cover their categories. React Native's pod-install aggregation
// (Podfile `privacy_file_aggregation_enabled`) merges pods' manifests into this
// file at build time, so the aggregation switch is pinned on too.
//
// Pins:
// - The file exists and is in the app target's Resources build phase.
// - Each category carries at least the reasons below (a floor, not an exact set).
// - NSPrivacyTracking is false.
// - Podfile.properties.json doesn't turn aggregation off.
// - NSPrivacyCollectedDataTypes equals legal-lead's R3-FINAL App Privacy label
//   set EXACTLY (2026-10-23, docs/plans/org-bringup/leads/legal-lead.md §R3/R5):
//   the same types, each linked and not tracking, with the same purposes. The
//   labels in App Store Connect and this manifest must agree, so any R3 change
//   updates COLLECTED below in the same commit. Purchase History was added by
//   legal-lead's R28.2 when the paywall entered the launch binary (2026-10-25).
//
// Run: node tests/check-privacy-manifest.js

'use strict';

const fs = require('fs');
const path = require('path');

const IOS = path.join(__dirname, '..', 'ios');
const MANIFEST = path.join(IOS, 'DTFDynastyTradeFinder', 'PrivacyInfo.xcprivacy');
const PBXPROJ = path.join(IOS, 'DTFDynastyTradeFinder.xcodeproj', 'project.pbxproj');
const PODFILE_PROPS = path.join(IOS, 'Podfile.properties.json');

const REQUIRED = {
  NSPrivacyAccessedAPICategoryFileTimestamp: ['C617.1', '3B52.1'], // app container; user-picked files (document picker)
  NSPrivacyAccessedAPICategoryUserDefaults: ['CA92.1'], // app-only defaults (RN Settings, cookies, expo-constants)
  NSPrivacyAccessedAPICategorySystemBootTime: ['35F9.1'], // elapsed-time measurement (RN, expo-device)
  NSPrivacyAccessedAPICategoryDiskSpace: ['E174.1'], // free-space checks before writes (expo-file-system)
};

// R3-FINAL: collected data type → purposes (all linked, none tracking).
const COLLECTED = {
  Name: ['AppFunctionality'],
  EmailAddress: ['AppFunctionality'],
  CoarseLocation: ['Analytics', 'AppFunctionality'],
  CustomerSupport: ['AppFunctionality'],
  OtherUserContent: ['AppFunctionality', 'ProductPersonalization'],
  UserID: ['AppFunctionality', 'Analytics'],
  DeviceID: ['AppFunctionality', 'Analytics'],
  ProductInteraction: ['Analytics', 'ProductPersonalization', 'AppFunctionality'],
  CrashData: ['AppFunctionality', 'Analytics'],
  PerformanceData: ['AppFunctionality', 'Analytics'],
  OtherDiagnosticData: ['AppFunctionality', 'Analytics'],
  // R28.2 (2026-10-25): the paywall ships (operator approved R1), so purchases
  // are collected. Analytics too, because subscription events feed K0–K3.
  PurchaseHistory: ['AppFunctionality', 'Analytics'],
  OtherDataTypes: ['AppFunctionality'],
};

let failures = 0;
function fail(msg) { failures += 1; console.error(`FAIL  ${msg}`); }

for (const f of [MANIFEST, PBXPROJ]) {
  if (!fs.existsSync(f)) {
    console.error(`no ${path.relative(IOS, f)} — the privacy manifest or the project moved`);
    process.exit(2);
  }
}

// In the target's Resources build phase: the PBXBuildFile id for the manifest
// must be listed inside a PBXResourcesBuildPhase section.
const pbx = fs.readFileSync(PBXPROJ, 'utf8');
const buildFile = /(\w+) \/\* PrivacyInfo\.xcprivacy in Resources \*\/ = \{isa = PBXBuildFile;/.exec(pbx);
const resources = /\/\* Begin PBXResourcesBuildPhase section \*\/([\s\S]*?)\/\* End PBXResourcesBuildPhase section \*\//.exec(pbx);
if (!buildFile) fail('project.pbxproj has no "PrivacyInfo.xcprivacy in Resources" build file');
else if (!resources || !resources[1].includes(buildFile[1])) {
  fail('PrivacyInfo.xcprivacy is not in the target\'s Resources build phase, so it would not ship');
}

const plist = fs.readFileSync(MANIFEST, 'utf8');
const declared = {};
for (const m of plist.matchAll(/<key>NSPrivacyAccessedAPIType<\/key>\s*<string>([^<]+)<\/string>\s*<key>NSPrivacyAccessedAPITypeReasons<\/key>\s*<array>([\s\S]*?)<\/array>/g)) {
  declared[m[1]] = [...m[2].matchAll(/<string>([^<]+)<\/string>/g)].map((r) => r[1]);
}
for (const [cat, reasons] of Object.entries(REQUIRED)) {
  if (!declared[cat]) { fail(`manifest does not declare ${cat}`); continue; }
  for (const r of reasons) if (!declared[cat].includes(r)) fail(`${cat} is missing reason ${r}`);
}
if (!/<key>NSPrivacyTracking<\/key>\s*<false\/>/.test(plist)) fail('NSPrivacyTracking must be false (the app does no ATT tracking)');

// NSPrivacyCollectedDataTypes: find the array, matching nested <array> tags.
function collectedBlock(src) {
  const start = src.indexOf('<key>NSPrivacyCollectedDataTypes</key>');
  if (start < 0) return null;
  const rest = src.slice(start);
  const open = /<array\/>|<array>/.exec(rest);
  if (!open) return null;
  if (open[0] === '<array/>') return '';
  let depth = 0;
  const tag = /<array>|<\/array>/g;
  tag.lastIndex = open.index;
  let m;
  while ((m = tag.exec(rest)) !== null) {
    depth += m[0] === '<array>' ? 1 : -1;
    if (depth === 0) return rest.slice(open.index + 7, m.index);
  }
  return null;
}
const block = collectedBlock(plist);
if (block === null) {
  fail('manifest has no NSPrivacyCollectedDataTypes array');
} else {
  const seen = {};
  for (const d of block.matchAll(/<dict>([\s\S]*?)<\/dict>/g)) {
    const body = d[1];
    const type = (/<key>NSPrivacyCollectedDataType<\/key>\s*<string>NSPrivacyCollectedDataType(\w+)<\/string>/.exec(body) || [])[1];
    if (!type) { fail('a collected-data entry has no NSPrivacyCollectedDataType'); continue; }
    if (seen[type]) fail(`collected data type ${type} is listed twice`);
    const linked = (/<key>NSPrivacyCollectedDataTypeLinked<\/key>\s*<(true|false)\/>/.exec(body) || [])[1];
    const tracking = (/<key>NSPrivacyCollectedDataTypeTracking<\/key>\s*<(true|false)\/>/.exec(body) || [])[1];
    const purposesBlock = (/<key>NSPrivacyCollectedDataTypePurposes<\/key>\s*<array>([\s\S]*?)<\/array>/.exec(body) || [])[1] || '';
    seen[type] = {
      linked, tracking,
      purposes: [...purposesBlock.matchAll(/<string>NSPrivacyCollectedDataTypePurpose(\w+)<\/string>/g)].map((p) => p[1]),
    };
  }
  for (const [type, purposes] of Object.entries(COLLECTED)) {
    const got = seen[type];
    if (!got) { fail(`R3-FINAL type ${type} is missing from NSPrivacyCollectedDataTypes`); continue; }
    if (got.linked !== 'true') fail(`${type}: NSPrivacyCollectedDataTypeLinked must be true (R3: linked to you)`);
    if (got.tracking !== 'false') fail(`${type}: NSPrivacyCollectedDataTypeTracking must be false (R3: not used to track)`);
    const want = [...purposes].sort().join(',');
    const have = [...got.purposes].sort().join(',');
    if (want !== have) fail(`${type}: purposes are [${have}], R3-FINAL says [${want}]`);
  }
  for (const type of Object.keys(seen)) {
    if (!COLLECTED[type]) fail(`${type} is declared but isn't in R3-FINAL; update the labels (legal-lead) first`);
  }
}

if (fs.existsSync(PODFILE_PROPS)) {
  const props = JSON.parse(fs.readFileSync(PODFILE_PROPS, 'utf8'));
  if (String(props['apple.privacyManifestAggregationEnabled']) === 'false') {
    fail('Podfile.properties.json disables apple.privacyManifestAggregationEnabled, so pod manifests would not be merged');
  }
}

if (failures) {
  console.error(`\n${failures} privacy-manifest pin(s) broken.`);
  process.exit(1);
}
console.log(`ok    privacy manifest: in Resources, ${Object.keys(REQUIRED).length} required-reason categories, ${Object.keys(COLLECTED).length} collected types = the App Privacy labels, tracking off`);
