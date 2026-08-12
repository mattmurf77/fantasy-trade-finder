# Sleeper iOS Reachability — Probe Result (2026-08-12)

> Answers the blocking unknown in [ADR-011](../adr/adr-011-device-side-platform-auth.md) / [device-side-platform-auth-hld-2026-08-12.md](device-side-platform-auth-hld-2026-08-12.md): **does Sleeper's Cloudflare edge accept a request originating inside an iOS app at all?**
>
> **Answer: yes, in every configuration tested — and the Chrome spoof is unnecessary.**

---

## Result

Run from a real iPhone, TestFlight build 107 (v1.13.1, commit `4a0101f`), via the temporary in-app probe. Sleeper's own no-op query (`{ __typename }`) — reads nothing, writes nothing. Four runs, self-reported through `sleeper_probe_result` analytics rather than transcribed:

| Headers | Network | Verdict | HTTP |
|---|---|---|---|
| Chrome-spoofed (mirrors `sleeper_write._BROWSER_HEADERS`) | Wi-Fi | **PASS** | 200 |
| Honest iOS (no UA override) | Wi-Fi | **PASS** | 200 |
| Chrome-spoofed | Cellular | **PASS** | 200 |
| Honest iOS | Cellular | **PASS** | 200 |

## What this settles

**1. The Sleeper half of the device-side migration is technically viable.** This was the one unknown capable of invalidating it outright — `backend/sleeper_write.py:43-59` records Cloudflare error 1010 against automation-looking signatures, and nobody had checked what a native iOS network stack looks like to that edge. It looks fine.

**2. Do NOT port the Chrome spoof to the device.** Honest iOS headers passed identically. The pre-probe worry was that spoofing desktop Chrome over an iOS TLS stack could fare *worse* than not spoofing, because a UA-versus-fingerprint mismatch is itself a bot signal. Neither was penalised here — but the spoof is still the wrong choice on the device:

- The server spoofs because a datacenter IP needs cover. A user's phone making the user's own request needs none.
- FTF has explicit permission from Sleeper. Disguising authorised traffic is both unnecessary and harder to defend if it is ever examined.
- A mismatch that is tolerated today is a latent failure: Cloudflare tightening its fingerprint checks would break a spoofing client and leave an honest one working.

**Design consequence:** the device adapter sends `content-type` + `authorization` and lets iOS supply its own User-Agent. `_BROWSER_HEADERS` stays server-side, where it is still needed.

**3. Neither network type is disadvantaged.** Wi-Fi and cellular both passed, so there is no carrier-IP-reputation cliff to design around.

## What this does NOT settle

- **Volume behaviour.** Four requests prove the edge accepts the *shape* of an iOS request. They say nothing about how Cloudflare treats sustained per-device traffic, and nothing about Sleeper's own application-level rate limits.
- **Durability.** A single point in time against a defence that is tuned continuously. Re-run if a device-side call starts failing in the field.
- **Token-rejection path.** All four runs carried a valid token, so the `AUTH-REJECTED` branch (edge passes, Sleeper refuses the token) is untested — it is the classifier's inference, not an observation.
- **ESPN and MFL.** Untested, and not implied by this. ESPN's anti-bot posture is separate; MFL is not moving its calls at all.

## Method note, for whoever runs the next one

Three earlier attempts to capture a live request by injecting a `fetch`/XHR interceptor into a page **all failed the same way** — the platform performs a full page load around the action, which destroys the injected hook. `sessionStorage` preserves captured *data* across that reload but cannot preserve the *hook*.

What worked was inverting it: rather than intercepting a request the app makes, **make the request deliberately and report the outcome as an analytics event**. That is durable, needs no transcription, and captured the network type automatically — removing the one detail most likely to be misremembered.

## Cleanup owed

The probe is temporary. Delete `mobile/src/screens/SleeperProbeScreen.tsx`, its `SleeperProbe` route in `RootNav`, the Settings row, the `debug.sleeper_probe` flag (plus its three mirror fixtures), and the `sleeper_probe_result` taxonomy + NON_INTENT entries.

**Known defect if it is ever re-run before deletion:** the Settings row calls `navigationRef.navigate` directly instead of the `navigateFromSettings` helper every other row uses. Settings is a modal, so the pushed screen lands *behind* it and the tap appears to do nothing. Fixed in a worktree but not shipped, since the probe had already answered the question.
