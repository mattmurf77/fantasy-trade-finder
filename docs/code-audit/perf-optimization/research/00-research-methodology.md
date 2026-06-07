# Research Methodology — Performance Deep-Dive

This doc governs the **research** phase (external best-practices). It is the
counterpart to `../templates/` which governs the **audit** phase (this
codebase). Research agents follow this framework so the five research docs
read as one coherent body.

## Goal

Produce an authoritative, FTF-relevant reference on how high-performing mobile
apps make data fetching + rendering feel fast — so the codebase audit and the
final plan can cite established practice instead of opinion.

## Scope guardrails

- **Mobile-first, React Native / Expo–relevant.** FTF mobile is RN 0.81 +
  Expo SDK 54, new architecture on, Hermes, Reanimated 4, TanStack Query,
  Zustand, talking to a Python/Flask backend on Render free tier (cold
  starts), SQLite dev / Postgres prod.
- Prefer techniques that apply to **this** stack. Note when a technique needs
  a library/infra FTF doesn't have yet (flag it as a prerequisite).
- Cite sources (docs, talks, benchmarks, RFCs). Prefer primary sources.

## Required structure for each research `.md`

```
# <NN> — <Topic>

## TL;DR
<5–8 bullet executive summary of the highest-leverage tactics.>

## Why it matters for FTF
<Tie the topic to FTF's known pain: slow player + trade fetch, Render cold
starts, 4.8 MB player payloads, etc.>

## Tactics
For each tactic:
### <Tactic name>
- **What it is** — concise definition.
- **When to use it** — and when NOT to.
- **Expected impact** — rough latency/UX gain, with any benchmark cited.
- **RN/Flask applicability** — how it maps to FTF's stack; library needed?
- **Cost / risk** — complexity, failure modes, maintenance.
- **Source(s)** — links.

## Anti-patterns to flag in the audit
<Bullet list of concrete code smells the audit agents should grep for, so
research directly seeds the audit. e.g. "request waterfalls: sequential
awaits where Promise.all would do".>

## Recommended defaults for FTF
<Opinionated, specific defaults: e.g. TanStack staleTime/gcTime values,
gzip threshold, FlatList windowSize, image cache policy.>

## Open questions / needs measurement
<Things that can't be settled without profiling FTF directly.>
```

## Scoring / framing alignment

Research docs don't carry RICE-P (that's for observations), but when you
recommend a default or tactic, label its expected impact using the **same
Impact ladder** as `../templates/scoring-criteria.md` (Massive / High /
Medium / Low / Minimal) so the audit can inherit your framing.

## Output location

Write exactly one file to `../research/` with the filename given in your
agent brief (e.g. `01-mobile-data-fetching.md`). Do not write anywhere else.
No code changes. Web research + synthesis only.
