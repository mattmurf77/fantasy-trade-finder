import { Clipboard } from 'react-native';

// The app's ONE clipboard write (audit P0-6). RN core's Clipboard is
// deprecated — react-native/index.js exports it behind a getter that calls
// warnOnce('clipboard-moved', "Clipboard has been extracted from react-native
// core…") on first access, once per JS session: visible in Metro dev logs,
// invisible in release. The implementation
// (Libraries/Components/Clipboard/Clipboard.js) and the iOS native module
// (React/CoreModules/RCTClipboard.mm) both still ship in react-native@0.81.5,
// and Clipboard.d.ts exports ClipboardStatic, so this typechecks with no cast.
//
// Why not expo-clipboard: it is a NATIVE module — npm install + expo prebuild
// + a fresh EAS/simulator build — and mobile/node_modules is a symlink in this
// worktree, so npm install is unavailable to this build. Migrating is a
// ONE-FILE edit at the next scheduled native rebuild: swap the import and the
// call below; no call site changes.
//
// Return type is `void` deliberately: RN core's setString is synchronous and
// returns nothing, so there is no success signal to await and no failure to
// catch — the caller's "Copied" flip acknowledges the TAP, not the write. When
// this seam moves to expo-clipboard (setStringAsync → Promise<boolean>) the
// signature may become Promise<boolean> and the caller gains a real success
// gate; that is a considered change, not a silent one. Separate file from
// tradeText.ts because that module must stay import-free for its unit test.
export function copyText(s: string): void {
  Clipboard.setString(s);
}
