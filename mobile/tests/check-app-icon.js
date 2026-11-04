#!/usr/bin/env node
// Static test: the shipped app icon is design-lead's square master (N12,
// 2026-10-23). Square means full-bleed with no baked corners: iOS applies the
// corner mask itself.
//
// Pins:
// - The Expo icon (app.json `icon`) and the native AppIcon set (what a
//   bare-workflow build ships, G-013) are the same bytes, so neither drifts alone.
// - 1024×1024, 8-bit RGB, no alpha channel and no tRNS chunk. App Store
//   Connect rejects an icon with transparency (ITMS-90717).
// - None of the four corner pixels is near-white. The old icon had white
//   rounded corners baked in.
//
// Dependency-free: decodes the PNG with node's zlib.
// Run: node tests/check-app-icon.js

'use strict';

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const MOBILE = path.join(__dirname, '..');
const APP_JSON = path.join(MOBILE, 'app.json');
const NATIVE = path.join(MOBILE, 'ios', 'DTFDynastyTradeFinder', 'Images.xcassets', 'AppIcon.appiconset',
  'App-Icon-1024x1024@1x.png');

let failures = 0;
function fail(msg) { failures += 1; console.error(`FAIL  ${msg}`); }

const iconRel = JSON.parse(fs.readFileSync(APP_JSON, 'utf8')).expo?.icon;
if (!iconRel) {
  console.error('app.json has no expo.icon — nothing to check');
  process.exit(2);
}
const EXPO = path.join(MOBILE, iconRel);
for (const f of [EXPO, NATIVE]) {
  if (!fs.existsSync(f)) {
    console.error(`no ${path.relative(MOBILE, f)} — nothing to check (did the icon move?)`);
    process.exit(2);
  }
}

const expoBytes = fs.readFileSync(EXPO);
const nativeBytes = fs.readFileSync(NATIVE);
if (!expoBytes.equals(nativeBytes)) {
  fail(`${iconRel} and the native App-Icon-1024x1024@1x.png differ; swap both or neither`);
}

// Minimal PNG decode: chunks → IHDR, tRNS, concatenated IDAT → unfiltered rows.
function decode(buf) {
  if (!buf.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) throw new Error('not a PNG');
  let off = 8; let ihdr = null; let hasTrns = false; const idat = [];
  while (off < buf.length) {
    const len = buf.readUInt32BE(off); const type = buf.toString('latin1', off + 4, off + 8);
    const data = buf.subarray(off + 8, off + 8 + len);
    if (type === 'IHDR') {
      ihdr = { w: data.readUInt32BE(0), h: data.readUInt32BE(4), depth: data[8], color: data[9], interlace: data[12] };
    } else if (type === 'tRNS') hasTrns = true;
    else if (type === 'IDAT') idat.push(data);
    off += 12 + len;
  }
  return { ihdr, hasTrns, raw: zlib.inflateSync(Buffer.concat(idat)) };
}

function unfilter({ w, h }, raw, bpp) {
  const stride = w * bpp; const out = Buffer.alloc(stride * h); let prev = Buffer.alloc(stride);
  for (let y = 0; y < h; y++) {
    const ft = raw[y * (stride + 1)]; const line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    const cur = out.subarray(y * stride, (y + 1) * stride);
    for (let i = 0; i < stride; i++) {
      const a = i >= bpp ? cur[i - bpp] : 0; const b = prev[i]; const c = i >= bpp ? prev[i - bpp] : 0;
      let p;
      if (ft === 0) p = 0;
      else if (ft === 1) p = a;
      else if (ft === 2) p = b;
      else if (ft === 3) p = (a + b) >> 1;
      else {
        const pa = Math.abs(b - c); const pb = Math.abs(a - c); const pc = Math.abs(a + b - 2 * c);
        p = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      }
      cur[i] = (line[i] + p) & 0xff;
    }
    prev = cur;
  }
  return out;
}

const { ihdr, hasTrns, raw } = decode(nativeBytes);
if (ihdr.w !== 1024 || ihdr.h !== 1024) fail(`icon is ${ihdr.w}×${ihdr.h}, expected 1024×1024`);
if (ihdr.color !== 2 || ihdr.depth !== 8) {
  fail(`icon colour type ${ihdr.color} / depth ${ihdr.depth}; expected 8-bit RGB (type 2) with no alpha`);
}
if (hasTrns) fail('icon has a tRNS (transparency) chunk');
if (ihdr.interlace !== 0) fail('icon is interlaced; this check expects a non-interlaced PNG');

if (!failures) {
  const px = unfilter(ihdr, raw, 3);
  const at = (x, y) => { const i = (y * ihdr.w + x) * 3; return [px[i], px[i + 1], px[i + 2]]; };
  const corners = { 'top-left': at(0, 0), 'top-right': at(ihdr.w - 1, 0),
    'bottom-left': at(0, ihdr.h - 1), 'bottom-right': at(ihdr.w - 1, ihdr.h - 1) };
  for (const [name, rgb] of Object.entries(corners)) {
    if (rgb.every((v) => v > 200)) fail(`${name} corner pixel is near-white (${rgb.join(',')}): baked rounded corners?`);
  }
}

if (failures) {
  console.error(`\n${failures} app-icon pin(s) broken.`);
  process.exit(1);
}
console.log('ok    app icon: Expo and native identical, 1024×1024 RGB with no alpha, no white corners');
