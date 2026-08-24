# `mascot_ram_rollout` — allowlist-targeted rollout of Fleeced

**Date:** 2026-08-23 · **Decisions:** [D-155](../../../living-memory/DECISIONS.md), [D-156](../../../living-memory/DECISIONS.md) · **Flag:** `onboarding.mascot_ram`
**Status:** **RUNNING on production since 2026-08-24** as `mascot_ram_rollout` **v2**, verified reaching the operator's device only (§7).

---

## 1. What this is, and what it is not

The operator asked for the ram "hidden behind an A/B test only enabled for me". This is the mechanism: an
**allowlist-targeted rollout**, not a powered experiment. It exists so the operator's device receives Fleeced in
production while every other unit keeps The Analyst, and no baseline is disturbed.

It is modelled directly on the shipped precedent
[`onboarding_v2_rollout`](../../business/analytics/2026-07-18-onboarding-v2-rollout-experiment.md), and on the pattern
`docs/api-reference.md` records for `testing.stage_users`: *"ships per-device via the experiment overlay, so the global
flag stays dark and other testers never see the surface."*

**No readout will be drawn from this.** A mascot swap has no hypothesis in the metric catalogue, and n=1.

## 2. How the gate actually works

Three independent things must all be true before a device renders Fleeced:

1. `onboarding.v2` is true (the master — `useOnboardingFeature` ANDs it in).
2. `onboarding.mascot_ram` is true **for that unit**. It is `false` in `config/features.json` and stays there; the
   treatment variant's `client_config.flags` overlays it per-unit, server-resolved, in `GET /api/feature-flags`.
   `mobile/src/api/flags.ts` merges overlays over the base map — overlay wins.
3. The unit is in `experiments.load_tester_allowlist()` — the union of `FTF_TESTER_ALLOWLIST` (env) and
   [`config/tester_allowlist.json`](../../../config/tester_allowlist.json), which already contains the operator's
   device id and account id.

Miss any one and the client sees the flag absent, which is indistinguishable from off: The Analyst renders, byte-identical.

**The fourth condition is not a flag at all — it is the build.** See §5.

## 3. The spec

| Field | Value | Why |
|---|---|---|
| key / version | `mascot_ram_rollout` **v2** | v1 was drafted on `onboarding` and rejected at launch; `/revise` minted v2 on `growth` |
| layer | ~~`onboarding`~~ → **`growth`** | **Deviation from this spec, forced at launch.** `onboarding` is fully occupied by `onboarding_v2_rollout` v3 — *running*, `targeting: null` (all users), device units, buckets `[0,10000)`. Layers enforce in-layer bucket exclusivity, so there was no room, and stopping a live all-users experiment to make room is not a call to make in passing. `growth` and `engine` were the only free layers; `growth` is the better fit for a brand rollout. **This rollout measures nothing, so it cannot confound a growth test** — but it does hold the growth layer's full range until stopped. See §8 |
| unit_type | `device` | Mandated for the onboarding layer (FR-34) — pre-auth, stable across sign-in |
| buckets | `[0, 10000)` | Full layer. **Targeting narrows, never bucketing** — an allowlisted device must not miss on a bucket roll |
| targeting | `{"is_tester_allowlist": true}` | Missing attr = excluded, so a non-listed unit can never be captured |
| variants | `control` 0 bp · `treatment` 10000 bp | Weights must sum to 10000 with ≥2 variants; a 0-weight control makes treatment certain for captured units |
| treatment `client_config` | `{"flags": {"onboarding.mascot_ram": true}}` | The only overlay. Deliberately one key — nothing else about onboarding changes |
| control `client_config` | *(none)* | Control is the shipped Analyst, i.e. today |
| primary_metric | `activation_rate` | A required field from `METRIC_CATALOG`. **Carried, not claimed** — this rollout is not designed to move it and no verdict will be read |
| exposure_surface | `guide_bubble` | First and primary treated surface (`AnalystGuide`) |
| guardrails | the 5 PFO guardrails | Auto-attached, non-omittable |
| launch | `override_underpowered: true` | Rationale: *"n=1 allowlist rollout for operator validation, not a powered test."* The engine records the override permanently |

## 4. Creating it — a production write, held for confirmation

Two `X-Cron-Secret`-authenticated calls against **production**. `CRON_SECRET` is in the gitignored
`secrets.local.env`. These are **not** run as part of shipping this branch:

```bash
# 1. create the draft
curl -sS -X POST "$FTF_PROD/api/admin/experiments" \
  -H "X-Cron-Secret: $CRON_SECRET" -H 'Content-Type: application/json' \
  -d '{
    "key": "mascot_ram_rollout",
    "layer": "onboarding",
    "unit_type": "device",
    "bucket_start": 0,
    "bucket_end": 10000,
    "targeting": { "is_tester_allowlist": true },
    "variants": [
      { "name": "control",   "weight_bp": 0 },
      { "name": "treatment", "weight_bp": 10000,
        "client_config": { "flags": { "onboarding.mascot_ram": true } } }
    ],
    "primary_metric": "activation_rate",
    "exposure_surface": "guide_bubble",
    "hypothesis": "No hypothesis under test. Allowlist-targeted rollout so the operator sees Fleeced in production while every other unit keeps The Analyst."
  }'

# 2. launch it (expect the underpowered gate — override deliberately)
curl -sS -X POST "$FTF_PROD/api/admin/experiments/mascot_ram_rollout/transition" \
  -H "X-Cron-Secret: $CRON_SECRET" -H 'Content-Type: application/json' \
  -d '{ "version": 1, "to": "running",
        "reason": "n=1 allowlist rollout for operator validation, not a powered test",
        "override_underpowered": true }'
```

**Rollback:** `/transition` to `stopped`. The overlay disappears on the next flag fetch and The Analyst returns with no
deploy. The global flag was never on, so there is nothing to un-flip.

## 5. The constraint that decides when this can work

**The sprites are bundled assets and there is no EAS Update channel** — `mobile/app.json` has `updates: null` and no
`runtimeVersion`. So:

- Flipping the flag on a build that **does not contain** `assets/mascot/ram/` does nothing: `require()` is resolved at
  bundle time, and the flag can only choose between components that shipped.
- Fleeced therefore reaches a device **only via a new build** — `eas build --profile production --platform ios`, then
  `eas submit`, then TestFlight.
- Creating the experiment before that build exists is harmless but inert.

**Order that works:** merge → EAS build → TestFlight install → create + launch the experiment → the operator's device
picks up the overlay on its next flag fetch (boot, or the ≥30-min foreground refetch).

## 6. Verifying it landed

1. `GET /api/feature-flags` with `X-Device-Id: <operator device>` → `experiments` contains
   `mascot_ram_rollout: treatment`, and `configs.mascot_ram_rollout.flags["onboarding.mascot_ram"]` is `true`.
2. The same call **without** that header (or with any other device id) → the key is absent from both.
3. On device: run the calculator tour (`Show me around`). All six poses render as the ram, **and the bubble header now
   reads “Fleeced”**. On the SignIn beat the introduction reads *“I'm Fleeced, the ram. Good to see another sheep here for me to take advantage of.”*.
   If the face is a ram but the name still says “The Analyst”, the copy gate and the art gate have diverged.
4. `guide_step_shown` events still carry the same six `pose` values. If they changed, something other than the renderer
   was touched.

## 7. Verified after launch (2026-08-24)

`GET /api/feature-flags` against production, three ways:

| Request | `experiments` | `configs.mascot_ram_rollout.flags` | base `flags["onboarding.mascot_ram"]` |
|---|---|---|---|
| `X-Device-Id: dev_loc-mrpy6qog-2t72t6` (allowlisted) | `mascot_ram_rollout: treatment` | `{onboarding.mascot_ram: true}` | `false` |
| no device header | `{}` | absent | `false` |
| `X-Device-Id: dev_not-on-the-list-99999` | `{}` | absent | `false` |

The base map staying `false` for the allowlisted device is **correct, not a bug**: the overlay lives in `configs`, and
`mobile/src/api/flags.ts` merges it over the base map with overlay-wins. Only that device resolves `true` on-device.

## 8. The layer debt this created, and how to clear it

`mascot_ram_rollout` v2 holds **the whole `growth` layer** (`[0,10000)`). Any future growth experiment will collide
with it exactly as this one collided with `onboarding_v2_rollout`.

**Clear it by stopping this rollout once the TestFlight pass is done** — that is the intended end state anyway; the
flag graduates or reverts, and either way this delivery mechanism stops being needed:

```bash
curl -sS -X POST "$FTF_PROD/api/admin/experiments/mascot_ram_rollout/transition" \
  -H "X-Cron-Secret: $CRON_SECRET" -H 'Content-Type: application/json' \
  -d '{ "version": 2, "to": "stopped", "reason": "TestFlight pass complete" }'
```

**The cleaner long-term fix is an operator call, not mine:** `onboarding_v2_rollout` v3 is untargeted and full-range on
the layer this rollout actually belongs to. Post-Phase-A, the onboarding flags it was built to overlay are the release
default (see the comment in `test_onboarding_v2_flags_are_release_plus_the_onboarding_surface`), so v3 may now be
overlaying nothing. **If it is vestigial, stopping it frees the onboarding layer** and this rollout could be re-filed
where it belongs. That was not verified, so it was not assumed.
