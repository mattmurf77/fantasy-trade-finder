# OI-12 — Runtime primitives on Hermes: `TextDecoder`, base64, and (unexpectedly) `URL`

> **Gate:** C — blocks S3. **Date:** 2026-08-13.
> **Question asked:** does the app's JS runtime provide `TextDecoder` (with `fatal: true`) and base64, which [LLD](device-side-platform-auth-lld-2026-08-13.md) §4.2.1 flags as unnamed dependencies of the import-free GraphQL guard?
> **Answer:** almost certainly **no** for both — with strong, specific evidence short of the device check. And the spike surfaced a **third primitive nobody was looking at, `URL`, which is a bigger problem than either.**

---

## 1. The stack, pinned

| Fact | Source |
|---|---|
| Expo SDK `~54.0.33`, React Native `0.81.5` | `mobile/package.json:51,66` |
| New architecture on; no `jsEngine` override ⇒ **Hermes** (the RN 0.81 default) | `mobile/app.json:10` |
| `expo-updates` **absent** | `mobile/package.json` — zero occurrences |

## 2. `TextDecoder` / `TextEncoder` — absent, with reasons rather than a guess

**RN core does not polyfill them.** The RN 0.81.5 startup chain installs its globals in `src/private/setup/setUpDefaultReactNativeEnvironment.js:22-43`, and the complete polyfill set in `Libraries/Core/setUpXHR.js:21-35` is:

`XMLHttpRequest` · `FormData` · `fetch` · `Headers` · `Request` · `Response` · `WebSocket` · `Blob` · `File` · `FileReader` · **`URL`**

`setUpGlobals.js` adds only `window`, `self`, and `process.env`. **No `TextDecoder`, no `TextEncoder`, no `atob`, no `btoa` anywhere in the chain.**

**Hermes will not supply them either.** `TextDecoder` is the WHATWG *Encoding* API and `atob`/`btoa` are *HTML* APIs — neither is ECMAScript, and Hermes implements ECMAScript. (Hermes's added surface, e.g. `Intl` on Android, is separate and does not include these.) So there is no second source.

**Confidence: high, but this is still desk research.** The 30-second device check below is the confirmation, and it stays a Gate C item.

```ts
// Drop in any screen of a dev build, read once from the Metro log.
console.log('PRIMITIVES', {
  TextDecoder: typeof TextDecoder,   // expect 'undefined'
  TextEncoder: typeof TextEncoder,   // expect 'undefined'
  atob: typeof atob, btoa: typeof btoa,
  URL: typeof URL,                   // expect 'function' (RN's polyfill)
  fatalDecode: (() => {              // only meaningful if TextDecoder exists
    try { new TextDecoder('utf-8', { fatal: true }).decode(new Uint8Array([0xff])); return 'DID NOT THROW'; }
    catch (e) { return e instanceof TypeError ? 'threw (correct)' : 'threw ' + String(e); }
  })(),
});
```

### 2.1 Consequence for S3 — the estimate moves

LLD §4.2.1 already states this branch: the import-free rule means a missing `TextDecoder` forces a **hand-written UTF-8 validating decoder inside `gqlGuard.ts`**, which becomes part of the security control and needs its own corpus rows — overlong encodings, lone surrogates, truncated trailing sequences, and the `0xC0 0x80` NUL trick. The LLD calls that "a sub-project, not a task."

Per Plan §2's note, **S3 is re-estimated at Gate C rather than assumed to fit its 6–9 day ceiling.**

**One design question worth asking before writing that decoder:** the guard needs `fatal: true` decoding because it must refuse malformed UTF-8 rather than silently substituting `U+FFFD`. But the *purpose* is to inspect a document the **server** built and base64'd. An alternative that deletes the primitive entirely is for the lease to carry the query as a plain JSON string and for the device to hand `fetch` that string — RN encodes the body as UTF-8 natively, so no JS-side decoder is needed. That trades away the LLD's "exact bytes, no re-serialization" property (PRD parser rule 4), which was chosen deliberately, so **it is a real trade, not a free win** — but it should be weighed at S3 before committing to hand-rolling a validating decoder into the security control. Flagging, not deciding.

### 2.2 base64 is the easier half

Only `gqlGuard.ts` is import-free (LLD §1.1). `platformTransport.ts` may take a dependency, so a missing `atob` costs a package (`base-64`, or `expo-crypto`'s helpers) plus a `DEPENDENCIES.md` entry — not a second hand-rolled primitive.

---

## 3. The finding nobody was looking for: `URL` is a 198-line regex, and the host allowlist depends on it

**RN polyfills `URL` itself** (`setUpXHR.js:35` → `Libraries/Blob/URL.js`), no WHATWG parser is installed (`react-native-url-polyfill` / `whatwg-url` are absent from `mobile/package.json`), and **`new URL(...)` appears nowhere in `mobile/src` today** — so LLD §4.3 step 3 would be its first use in this app.

That polyfill is **not a URL parser.** It is 198 lines of regex getters, and its one-argument constructor (`URL.js:79-99`) **stores the string without validating it**:

```js
hostname: /^https?:\/\/(?:[^@]+@)?([^:/?#]+)/
password: /https?:\/\/.*:(.*)@/          // note the greedy .*
port:     /:(\d+)(?=[/?#]|$)/
```

Meanwhile `fetch` hands the URL string to **native iOS networking, which parses it properly**. So the guard would decide with one parser and the request would be dispatched by another — the exact parser-differential class the GraphQL guard was designed around, reappearing one layer up, unnoticed through four LLD review rounds.

### 3.1 Measured — 16 adversarial URLs, RN's getters vs WHATWG

| Direction | Count | Meaning |
|---|---|---|
| **Bypass (RN allows, WHATWG refuses)** | **0** | **The allowlist cannot be tricked.** RN is strictly over-strict; this is the safe direction and it is the important result. |
| **False refusal (RN refuses, WHATWG allows)** | **4** | Benign URLs the device would reject — and LLD §4.4 pages the operator for exactly those refusal codes. |

The four false refusals: a backslash in the URL; a `#` appearing before an `@`; a tab inside the host; and — the one that will actually happen — **`https://sleeper.com/a:b@c`, refused as `userinfo`** because the greedy password regex scans across the *path*, not just the authority.

Harmless in release 1: today's only endpoint is `https://sleeper.com/graphql`, which has no `:` and no `@`, and it tested **agree/ALLOW**. It stops being harmless the moment a URL carries a colon and a later at-sign — and the LLD says `_normalize_url` is "defensive today — ESPN's REST surface in release 2 will need it."

### 3.2 Recommendation for S4: do not parse the URL at all in release 1

The LLD's own philosophy — compiled, exact, no clever matching — resolves this cleanly. The server builds the URL and release 1 has **exactly one endpoint**, so the device can compare the whole string:

```ts
const ALLOWED_ENDPOINTS: ReadonlySet<string> = new Set(['https://sleeper.com/graphql']);
if (!ALLOWED_ENDPOINTS.has(lease.request.url)) return refuse('host_not_allowed');
```

Exact string equality against a compiled set is **strictly stronger** than parsing-then-allowlisting, has no parser to diverge from native, and deletes scheme/userinfo/port checks as a class — none of them can be smuggled past an exact match. Release 2's ESPN paths need prefix matching over a hand-written strict splitter (or a real WHATWG polyfill, taken as a dependency with a DEPENDENCIES.md entry) — but that decision belongs to release 2, not to release 1's guard.

Recorded as **OI-21**.

---

## 4. Gate C verdict

- **`TextDecoder`: expect absent** — confirm on device with §2's snippet. If absent, **re-estimate S3** before starting it.
- **base64: expect absent, cheap** — a dependency for `platformTransport.ts`, not a hand-rolled primitive.
- **`URL`: present but unfit.** Do not build the host allowlist on it. Adopt the exact-endpoint match (§3.2) at S4. **No device check needed — this one is settled by reading the source and the measurement above.**
