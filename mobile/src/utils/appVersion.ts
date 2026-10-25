// appVersion — the B8 minimum-version gate's pure half (head-eng ruling 35).
//
// The server serves `app_min_version` on GET /api/feature-flags as one int:
// major*10000 + minor*100 + patch (1.22.0 = 12200), 0 = off. This file turns
// the app's own version string into the same int and decides whether to
// block. The encoding is a cross-client invariant
// (docs/cross-client-invariants.md § App version int).
//
// FAILS OPEN on every uncertainty: an unparseable version, a missing or
// malformed min, or 0 never blocks. Whether a fetch resolved at all is the
// flag store's half (`appMinVersion` stays 0 until one does).
//
// Zero runtime imports on purpose: mobile/tests/check-update-gate.js
// transpiles this file and EXECUTES every function under plain node.

/** "1.22.0" → 12200. Anything that is not exactly three dot-separated
 *  integers with minor and patch below 100 (the encoding's field width) →
 *  null. Pre-release / build suffixes ("1.22.0-beta") are unparseable too. */
export function versionInt(version: unknown): number | null {
  if (typeof version !== 'string') return null;
  const m = /^(\d{1,4})\.(\d{1,2})\.(\d{1,2})$/.exec(version.trim());
  if (!m) return null;
  return Number(m[1]) * 10000 + Number(m[2]) * 100 + Number(m[3]);
}

/** A served `app_min_version` as a usable min, or 0 (off) when it is
 *  missing, not a number, not a safe integer, or not positive. */
export function minVersionOrOff(raw: unknown): number {
  return typeof raw === 'number' && Number.isSafeInteger(raw) && raw > 0 ? raw : 0;
}

/** Block only when the min is a positive integer, the app's own int is
 *  known, and the app is strictly older. Equal or newer never blocks. */
export function shouldBlockForUpdate(minVersion: unknown, appVersionInt: unknown): boolean {
  const min = minVersionOrOff(minVersion);
  if (min === 0) return false;
  if (typeof appVersionInt !== 'number' || !Number.isSafeInteger(appVersionInt)) return false;
  return appVersionInt < min;
}

/** Where the gate's Update button goes. The same binary serves TestFlight
 *  testers before the App Store release and App Store users after it, and
 *  the app has no dependency that can tell the two installs apart. So the
 *  button switches on the date: true from LOCAL midnight of `liveFromYmd`
 *  ('YYYY-MM-DD') onward. An unparseable date reads as live, because the
 *  App Store is the permanent target. */
export function appStoreLive(liveFromYmd: string, now: Date): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(liveFromYmd);
  if (!m) return true;
  const liveFrom = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return now.getTime() >= liveFrom.getTime();
}
