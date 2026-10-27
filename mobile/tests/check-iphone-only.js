#!/usr/bin/env node
// Static test: the app ships iPhone-only (SB-1, operator 2026-10-23: "Sb1 iphone
// only: Yes").
//
// The setting that ships is the native one. This is a bare-workflow project, so
// EAS builds from ios/ and app.json's iOS block is ignored (G-013). An iPad
// device family (TARGETED_DEVICE_FAMILY containing 2) makes App Store Connect
// require 13" iPad screenshots and puts the app in front of iPad reviewers.
// app.json's supportsTablet is pinned too, so a future `expo prebuild` can't
// regenerate "1,2".
//
// Run: node tests/check-iphone-only.js

'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const APP_JSON = path.join(MOBILE, 'app.json');
const PBXPROJ = path.join(MOBILE, 'ios', 'DTFDynastyTradeFinder.xcodeproj', 'project.pbxproj');
const INFO_PLIST = path.join(MOBILE, 'ios', 'DTFDynastyTradeFinder', 'Info.plist');

let failures = 0;
function fail(msg) { failures += 1; console.error(`FAIL  ${msg}`); }

for (const f of [APP_JSON, PBXPROJ, INFO_PLIST]) {
  if (!fs.existsSync(f)) {
    console.error(`no ${path.relative(MOBILE, f)} — nothing to check (did the project move?)`);
    process.exit(2);
  }
}

const supportsTablet = JSON.parse(fs.readFileSync(APP_JSON, 'utf8')).expo?.ios?.supportsTablet;
if (supportsTablet !== false) {
  fail(`app.json expo.ios.supportsTablet is ${JSON.stringify(supportsTablet)}, expected false`);
}

const families = [...fs.readFileSync(PBXPROJ, 'utf8').matchAll(/TARGETED_DEVICE_FAMILY = ("?)([^";]*)\1;/g)]
  .map((m) => m[2].trim());
if (families.length === 0) {
  fail('project.pbxproj sets no TARGETED_DEVICE_FAMILY (Xcode would default to iPhone, but the pin is gone)');
}
families.forEach((v, i) => {
  if (v !== '1') fail(`project.pbxproj TARGETED_DEVICE_FAMILY #${i + 1} is "${v}", expected 1 (iPhone only)`);
});

// An explicit UIDeviceFamily in Info.plist would override the build setting.
const plist = fs.readFileSync(INFO_PLIST, 'utf8');
const deviceFamily = /<key>UIDeviceFamily<\/key>\s*<array>([\s\S]*?)<\/array>/.exec(plist);
if (deviceFamily && /<integer>\s*2\s*<\/integer>/.test(deviceFamily[1])) {
  fail('Info.plist UIDeviceFamily lists 2 (iPad)');
}

if (failures) {
  console.error(`\n${failures} iPhone-only pin(s) broken.`);
  process.exit(1);
}
console.log(`ok    iPhone-only: supportsTablet false, ${families.length} TARGETED_DEVICE_FAMILY = 1, no iPad UIDeviceFamily`);
