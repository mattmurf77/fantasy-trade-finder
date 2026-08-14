# OI-9 — Should `expo-updates` come before the device-credentials programme?

> **Gate:** C — blocks S3. **Date:** 2026-08-13. **Owner of the question:** operator (Plan §1).
> **Question asked:** PRD OQ-4 / LLD OI-9 — `expo-updates` is said to address R1–R6 as a class while
> this programme addresses R1–R2, and the PRD ordered it "evaluated **first**." Adopt before,
> instead of, after, or not at all?
> **Answer: do not adopt.** Not before S3, not as part of release 1. The decision is *made*, not
> deferred — Gate C's OI-9 checkbox is discharged by this memo. A named re-open trigger is in §8.
>
> **Independence disclosure, up front — read §9 before weighing this memo against Plan §10.**

---

## 1. The stack, pinned

| Fact | Source |
|---|---|
| `expo-updates` **absent** — zero occurrences | `mobile/package.json`; `mobile/node_modules/expo-updates` does not exist |
| Expo SDK `~54.0.33`, React Native `0.81.5`, Hermes | `mobile/package.json:51,66`; `mobile/app.json:10` |
| No `updates` key, no `runtimeVersion` policy | `mobile/app.json` |
| **No `channel` on any build profile** (`development`, `preview`, `production`) | `mobile/eas.json` |
| `EXUpdatesEnabled` = **`false`** in the committed native project | `mobile/ios/DTFDynastyTradeFinder/Supporting/Expo.plist` |
| The iOS project is **committed, not generated on demand** — 24 tracked files incl. `AppDelegate.swift` | `git ls-files mobile/ios` |
| Shipping version `1.13.3`; **TestFlight-only, never publicly released** | `mobile/app.json:5`; `living-memory/NEXT.md:127`, `DECISIONS.md:343` |
| Population: operator + ~2 testers | PRD §5 |

**A finding that has to come first, because the question is phrased on top of it: the `R1`–`R8`
enumeration does not exist anywhere in the tree.** `git grep -nE '\bR[1-8]\b'` across the PRD, LLD,
analytics spec and `living-memory/` returns nothing. `R7` and `R8` survive only as prose references
(Cloudflare TLS fingerprinting; credential expiry), and "R1–R6" appears solely in the three places
that *assert* the claim under evaluation — HLD-decisions §Still open, LLD OI-9, Plan §10. The list
lived in the superseded `design/device-side-platform-auth` HLD, which is not in the repo.

So **the sentence that gives OI-9 its "upstream of the whole programme" status cannot be checked
against its own source.** I did not treat it as authoritative. I reconstructed the risk classes from
context (HLD-decisions:121 — R8 "is not an upstream *shape* change, which is why it fell out" — pins
R1–R7 as predominantly upstream-shape risks) and evaluated those instead. §5 does that.

## 2. Recommendation

**Don't adopt.** Three reasons, in weight order:

1. **Adopting deletes a requirement the PRD marks non-negotiable.** PRD §8: the host allowlist is
   "**compiled into the binary, never read from a server response**." The guard, the compiled op set,
   the caps fingerprint and the credential-vault access all live in the same JS bundle
   (LLD §1.1). `expo-updates` replaces that bundle wholesale. There is no way to adopt OTA and keep
   PRD §8 as written — adoption is a PRD amendment, not a build-config change, and it should be
   priced that way.
2. **The benefit it is credited with mostly does not exist at this fleet size, and the part that
   does exist is unreachable.** OTA cannot reach a single binary already in the field (§5), and the
   fix cycle it shortens — TestFlight internal distribution, which skips Beta App Review — is
   already hours for a three-person fleet, not the App-Store-release cycle the constraint is written
   against.
3. **It does not touch the decisive risk.** R7 is a TLS/HTTP-2 handshake signature emitted by
   NSURLSession. It is fixed before one line of JavaScript runs. No bundle swap alters it (§6).

**This is not a close call on cost, either.** The programme's *own* architecture already buys G6
("fix upstream shape changes without an App Store release") for the change-prone surface, by a
different mechanism: the server builds every request, so headers, path, variables and body shape are
hotfixable from Render (PRD §8, HLD "settled by both lenses"). The residue OTA would additionally
make hotfixable is precisely the set of things deliberately made *non*-hotfixable because that is
what makes them controls.

## 3. What adoption would concretely entail here — it is not `expo install`

| Step | Note specific to this repo |
|---|---|
| `expo install expo-updates` + `updates.url` = `https://u.expo.dev/68beb3f2-c99e-408b-b03c-1c326a64b4ec` | `projectId` already exists (`app.json` `extra.eas`) |
| **Native diff to a committed Xcode project** — `EXUpdatesEnabled` → `true`, updates URL + runtime version into `Expo.plist`, new pod, `AppDelegate.swift` controller wiring | `mobile/ios/` is tracked (§1). Either a `prebuild` regeneration reviewed as a real diff, or hand-edits. Not a JS-only change. |
| `runtimeVersion` policy — `appVersion` vs `fingerprint` | New standing invariant: an update published across a native change is either silently withheld or, mispolicied, shipped to a binary that cannot run it. `appVersion` is a poor fit — this app bumps marketing version frequently and independently of native deps. |
| `channel` on each `eas.json` profile + branch↔channel mapping | Three profiles exist today with **none** |
| **Update code signing** — `expo-updates codesigning:generate`, cert embedded in the binary, manifests signed at publish | **Off by default.** Skipping it is the common path and is the insecure one (§4). |
| `living-memory/DEPENDENCIES.md`, `docs/config-reference.md` | Repo convention |

**Sequencing consequence, independent of the merits:** `expo-updates` is a *native* module, so its
benefit begins only in a build that carries it — S6 at the earliest. Adopting "first" therefore
de-risks nothing before S6, and the work has **zero coupling to S3, S4 or S5**. Even an operator who
rejects §2 should not hold Gate C for it; it is a Gate D build-config question.

## 4. The security carve-out — can `mobile/src/transport/` be excluded, and is signing enough?

**No, and no.**

**Exclusion is not implementable.** `expo-updates`' unit of replacement is the entire JS bundle plus
assets. There is no subtree exclusion, no per-module pinning, no "everything but this directory."
`gqlGuard.ts`, `platformTransport.ts`, `credentialVault.ts`, `DEVICE_OPS` and the compiled caps
constant all compile into one Hermes bundle and are replaced together or not at all. Note also that
`app.json`'s `extra` block is **not** a hiding place: under `expo-updates` the manifest is served
remotely too, so `extra` is exactly as swappable as the bundle.

**The only real carve-out is relocation to native.** `expo-updates` never replaces native code — that
is what `runtimeVersion` exists to enforce. So the allowlist, the endpoint set and the op set *could*
be made genuinely uncompromisable by moving them into `Info.plist` behind a small native module. That
is a new design, not a carve-out: it puts a security control into Swift in a codebase whose
`mobile/src` contains none, and it breaks the LLD's testing strategy outright — §6.1's harness
transpiles the real TS and runs it under node (`check-espn-nav-policy.js:14-35`), and §6.1(b)'s
differential oracle and §6.1(c)'s 10k-case fuzz both depend on the control being plain TS. Trading
that away to enable OTA is a strictly worse deal than not having OTA.

**Signing is necessary, insufficient, and its key sits in the wrong place to help.** Two precise
points, because the loose version of this argument is wrong:

- **The loose version — "OTA moves the update channel into the TCB of a design whose stated threat is
  a compromised backend" — overstates it.** The programme's adversary is *Render*. The update channel
  is Expo/EAS, a different trust domain. A Render compromise does not yield the ability to publish an
  OTA update. OTA does not hand the guard to the stated adversary.
- **The accurate version is still disqualifying.** Adoption adds a *second* remote-code path whose
  compromise yields arbitrary code execution inside the app **with vault access** — and the credential
  that guards it is the operator's Expo/EAS token, held on the same laptop as everything else. Today
  the same credential already permits pushing a malicious *build*, but that path is slow, Apple-
  processed, versioned and requires the user to install it. OTA makes it instant, silent and
  invisible in the version string. That is a real delta against the status quo. Code signing narrows
  forgery from "whoever can serve the CDN" to "whoever holds the private key" — but the key holder is
  the operator's machine, i.e. **the same principal**, so the two compromises are correlated to near
  unity, and signing does nothing about a signed *rollback* to an older, still-valid bundle.

## 5. What OTA buys that the programme does not — measured against n=3

Reconstructing the "cannot fix old binaries" residual by class (§1's caveat applies — the numbered
list is unrecoverable):

| Class | OTA-addressable? | Real at n=3? |
|---|---|---|
| Upstream Sleeper request-shape change | **Already solved without OTA** — server builds the body (PRD §8) | n/a |
| Upstream response-shape change | **Already solved** — I1, the device never parses; the server interprets | n/a |
| Defect in our compiled guard/parser (Plan F3) | yes | Detectable in the S7 soak; fix = one TestFlight build |
| Stale/wrong compiled allowlist, op set, or caps fingerprint (§2.1, OI-17) | yes | Failure is **loud** — 426 to everyone, caught on the operator's own device |
| Defect in the five rewritten §4.5 sites / vault / caps emission | yes | Same |
| **R7 — Cloudflare rejects the iOS TLS/HTTP-2 fingerprint** | **no** (§6) | The decisive risk |
| R8 — credential expiry/invalidation | no, and doesn't need to be — server-detected, prompts re-capture | Handled |

**The three OTA-addressable classes are all defects in code that does not exist yet, in an app whose
entire fleet is the operator plus two testers.** For that fleet, "cannot fix without an App Store
release" is factually not the constraint: this app has never been on the App Store, and internal
TestFlight distribution does not go through Beta App Review — the cycle is an EAS build plus
processing, which the Plan itself budgets at "0.5 + 1–3 elapsed" days (§2, S6). OTA would compress
days to minutes for a three-person population that can be told to update in a text message.

**And the class OTA is most credited with, it cannot touch at all.** LLD §4.5's "the old-binary set …
**cannot be fixed**" refers to sites 1/3/4/5 as shipped "in every TestFlight build up to and
including `1.13.2`." Those binaries have no `expo-updates` native module and never will —
`EXUpdatesEnabled` is `false` in the shipped project. **Adopting today makes builds from S6 forward
updatable and leaves every binary already in the field permanently frozen.** OI-4's reinstall hazard
(TestFlight permits installing old builds) is untouched for the same reason.

## 6. Does OTA touch R7? No — and the layer argument is clean

R7 is Cloudflare fingerprinting the **TLS ClientHello and HTTP/2 SETTINGS/priority frames** emitted by
iOS's networking stack. That signature is produced by NSURLSession below `fetch`, below Hermes, below
the bundle. A JS bundle swap cannot change cipher-suite ordering, extension ordering, ALPN, or frame
layout. PRD A3 already reaches the same conclusion by a different route ("on a phone you cannot choose
NSURLSession's fingerprint"), and HLD-decisions:110-112 narrows it correctly: the one known lever is a
WKWebView transport — **native**, therefore requiring a binary, therefore outside OTA's reach even
after adoption. R-ROLLBACK remains the only answer, exactly as A3 says.

## 7. How much LLD machinery would adoption actually obsolete?

Concretely, and mostly the answer is "none," for one reason stated once: **a server contract must
still be correct against binaries that never take an update** — binaries predating `expo-updates`,
reinstalled old builds (OI-4), offline devices, and devices between the store install and the first
update fetch.

| LLD machinery | Under adoption |
|---|---|
| §2.5 `GET /api/sleeper/link` union contract + `revoked` | **Unchanged.** Its whole purpose is `1.13.2`, which can never receive an OTA. |
| §4.5's five call sites | **Unchanged as a rewrite; the *risk* of getting it wrong shrinks.** The rewrite is still required, in a binary, before S6. |
| §6.2 vendored `legacy-sendInSleeper-1.13.2.ts` fixture test | **Unchanged.** Same reason. |
| §2.1 caps fingerprint + `TRANSPORT_OP_SETS` | **Strengthened, not obsoleted.** OTA adds a skew axis — two devices on the same `X-App-Version` can now genuinely carry different compiled op sets. That is D3's decisive argument, restated harder. The registry's append-only rule also survives, because un-updated binaries persist. |
| §7.2 S6 "point of no return" / Plan §4 | **Genuinely softened** — for JS defects only. Native surface (Sentry SDK config, keychain entitlements, anything in `Expo.plist`) still needs a build. This is the one real win, and it is a win about *our* future bugs. |
| §6.1 guard corpus / oracle / fuzz | **Unchanged**, and see §4 — moving the guard native to protect it would *destroy* this harness. |
| §5.4 fail-closed inventory, §6.4 rails, §4.7 sweep | **Unchanged** — all server-side or test-side. |

So: one section softens, one strengthens, the rest are untouched. The claim that OTA makes the
programme materially cheaper does not survive contact with which parts exist for old binaries.

## 8. MANDATORY — what evidence would have concluded "adopt first"

Four facts. **Any one of them holding flips this recommendation, and each is checkable rather than a
matter of judgement. If any of the four is wrong, this memo is wrong.**

1. **A working subtree carve-out.** If `expo-updates` could exclude `mobile/src/transport/` from the
   update payload — or if the compiled allowlist and op set already lived in native code — adoption
   would cost PRD §8 nothing, and I would have recommended adopting before S3. It cannot, and they
   do not (§4).
2. **OTA reaching the existing fleet.** If a `1.13.2` binary could take an OTA update, then §2.5's
   union contract, §4.5's five sites and §6.2's vendored fixture test would genuinely go away and the
   programme would get materially cheaper. It cannot: `expo-updates` is a native module and
   `EXUpdatesEnabled` is `false` in every build shipped to date (§5).
3. **A store-release-bound fix cycle.** If this app were publicly released with a fleet that could not
   be moved in hours — App Review plus weeks of user-driven adoption before a guard fix reaches
   everyone — then "cannot fix old binaries" would be an operational cost rather than a three-person
   inconvenience, and OTA would be worth its security price. It is TestFlight-only with n≈3 (§1, §5).
4. **Any OTA purchase on R7.** If the programme's decisive risk had a JS-layer remedy, OTA would be
   buying the one thing nothing else here can buy. It does not: the fingerprint is emitted below the
   JS runtime (§6).

**Named re-open trigger, so this decision does not silently expire:** re-evaluate OI-9 at the **first
public App Store release** (`living-memory/NEXT.md:127`) — fact 3 flips there, and facts 1/2/4 should
be re-checked against the Expo SDK of the day. Until then, `expo-updates` stays a PRD §3 non-goal.

## 9. If the operator overrides this and adopts — what changes

Stated so an "adopt" answer is executable rather than a restart:

- **PRD §8 must be amended.** "Compiled into the binary, never read from a server response" becomes
  "delivered over a code-signed update channel," and the PRD must say who holds the key. Update
  code signing moves from optional to **mandatory** — unsigned OTA on a credential-custody app is not
  a defensible posture. PRD §3's non-goal line is deleted.
- **LLD §1.2** drops `expo-updates` from out-of-scope; **§2.1** gains a rule that the caps fingerprint
  is computed from the *bundle's* `DEVICE_OPS`, not the build's, and that an OTA changing `DEVICE_OPS`
  requires a `TRANSPORT_OP_SETS` registration **before** publish, not after — the ordering is
  reversed relative to a store release and getting it backwards 426s the fleet.
- **LLD §5.4** gains a fail-closed item: an update whose signature does not verify must not launch.
- **Plan §4** re-rates S6 from "NO" to "no for native, yes for JS," and **Plan §2** adds ~1–2 days to
  S5/S6 for the native diff, channels, runtime-version policy and signing setup — not to S3.
- **Gate D** gains: a rollback-to-previous-update drill rehearsed on device, and evidence that a
  tampered manifest is rejected.
- `living-memory/DEPENDENCIES.md`, `docs/config-reference.md`, `docs/runbook.md` (publish + rollback
  procedure) per §7.6's existing list.

## 10. Independence disclosure — read this before checking me against Plan §10

I was instructed not to read Plan §10 so this memo could be an independent check on it. **I did not
open §10. I did, however, see two of its lines incidentally**, in the output of a
`git grep -n "expo-updates"` run to locate the source documents, before I had read any of them:

- **`plan:207`** — the execution lens's trusted-computing-base argument in full.
- **`plan:269`** — a Reconciliation Log row disclosing that "the recommendation leans proceed **with
  the spike holding the veto**," i.e. the orchestrator's leaning was visible to me.

I am reporting this rather than quietly proceeding, because it degrades the independence this memo
was commissioned for and the operator should discount accordingly. Two things partially offset it:

1. **I reach the same verdict by different reasoning, and I explicitly reject the leaked argument's
   framing.** §4 says the TCB formulation as stated at `plan:207` is *overstated* — the update channel
   is Expo/EAS, not Render, so OTA does not put the guard in the stated adversary's hands. My case
   rests instead on the non-implementable carve-out, the unreachable existing fleet, the n≈3 fix
   cycle, and R7's layer.
2. **My load-bearing findings are absent from what I saw** — the missing `R1`–`R8` list (§1), the
   fact that OTA can never reach `1.13.2` so §2.5/§4.5/§6.2 do not shrink (§5, §7), that the caps
   fingerprint is *strengthened* by OTA (§7), and that adoption is a Gate D build-config question
   with zero coupling to S3 (§3).

`plan:269` also records two hygiene rules on this spike — that the prompt exclude §10 and that the
memo name its own disconfirming evidence. The first is compromised as described; the second is §8.
