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
console.log(`ok    privacy manifest: in Resources, ${Object.keys(REQUIRED).length} required-reason categories declared, tracking off`);
