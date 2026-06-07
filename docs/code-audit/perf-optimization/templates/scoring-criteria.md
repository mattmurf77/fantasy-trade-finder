# Scoring Criteria — RICE-P (RICE adapted for Performance)

Every observation MUST carry a RICE-P score so findings across all six audit
areas can be ranked on one comparable scale. Use these exact definitions and
scales — do not invent your own. If you are unsure of a value, pick the
conservative (lower-priority) option and say so in the Confidence note.

---

## The four inputs

### Reach (R) — how often the slow path is hit
How many user **sessions or interactions** are affected over a typical week.
Score on a 1–10 scale anchored to FTF's actual usage surfaces:

| Score | Meaning | FTF example |
|------:|---------|-------------|
| 10 | Every app launch / every session | App boot, session bootstrap, flag fetch |
| 8 | Every time a core tab is opened | Trades deck load, Tiers open, league pick |
| 6 | Common action several times per session | Trio fetch, tier save, swipe |
| 4 | Occasional per session | League switch, profile view |
| 2 | Rare / power-user only | Cross-league portfolio, contrarian view |
| 1 | Edge path | Demo bootstrap, deep-link cold entry |

### Impact (I) — magnitude of improvement per affected interaction
How much faster/smoother the interaction gets **per occurrence**. Use the
fixed multiplier ladder (RICE convention) and tie it to an estimated time
delta where you can:

| Score | Label | Rough latency delta guide |
|------:|-------|---------------------------|
| 3 | Massive | >2 s saved, or removes a hard block / cold-start stall |
| 2 | High | ~1–2 s saved, or eliminates a visible spinner |
| 1 | Medium | ~300 ms–1 s, or removes a jank/dropped-frame burst |
| 0.5 | Low | ~100–300 ms, or a minor smoothness gain |
| 0.25 | Minimal | <100 ms, perception-threshold or below |

### Confidence (C) — how sure the finding + fix are real
Percentage that the slowness is real AND the proposed fix will deliver the
estimated Impact. Be honest; speculative findings should score low.

| Score | Meaning |
|------:|---------|
| 100% | Measured (profiler, timed curl, network trace, render count) |
| 80% | Strong static evidence (clear code path, known anti-pattern, file:line) |
| 50% | Reasoned hypothesis, not yet measured |
| 20% | Speculative — flag for a spike before committing effort |

### Effort (E) — person-days to implement + test + ship
Decimal person-days for one engineer, including verification. Don't forget
test + review + the cross-client invariant checks FTF requires.

| Score | Meaning |
|------:|---------|
| 0.5 | Trivial: one-line / config change |
| 1 | Small: single file, low risk |
| 2 | Medium: a few files or one new endpoint |
| 3 | Large: spans client + backend, needs coordination |
| 5 | Major: new subsystem / migration / schema change |
| 8 | Epic: multi-week, should be decomposed |

---

## The score

```
RICE-P = (Reach × Impact × Confidence) / Effort
```

Confidence is expressed as a decimal (80% → 0.8) in the formula.

Report the computed number to one decimal. Higher = do sooner. Example:
Reach 8, Impact 2, Confidence 0.8, Effort 1 → (8 × 2 × 0.8) / 1 = **12.8**.

---

## Severity (orthogonal to RICE-P)

RICE-P answers "what order do we do this in." Severity answers "how bad is it
right now." Tag every observation with one:

| Tag | Meaning |
|-----|---------|
| **P0 — Critical** | Severely degrades a core flow on most sessions; user-reported pain |
| **P1 — High** | Clear, noticeable delay on a common flow |
| **P2 — Medium** | Measurable but secondary; affects fewer flows |
| **P3 — Low** | Minor / polish / nice-to-have |

A finding can be P0 severity but low RICE-P (e.g. huge impact but enormous
effort) — that's fine and useful signal for the plan phase.

---

## Estimated latency delta (required, separate from Impact score)

Always state a concrete estimate even if rough, with the assumption behind it.
Prefer ranges and name the scenario (cold vs warm, wifi vs cellular). Example:
"−1.2 s on a warm league pick (wifi); on a cold Render dyno the warm-cache
download was 30–60 s and is fully removed from the critical path."

If you genuinely cannot estimate without measurement, say
"needs measurement — spike required" and set Confidence ≤ 50%.
