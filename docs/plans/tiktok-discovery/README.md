# tiktok-discovery — TikTok-style discovery engine for Find-a-Trade

Research → gap analysis → prioritized backlog → PRDs for making the trade deck a first-class
discovery engine, modeled on TikTok's presentment + models layer. Produced 2026-07-26 via the
app-teardown-audit research discipline (paired independent researchers per topic).

## Read order

1. [research/tiktok-presentment.md](research/tiktok-presentment.md) — the app/UX mechanisms (consolidated, sourced)
2. [research/tiktok-models-layer.md](research/tiktok-models-layer.md) — the ranking/learning stack (consolidated, sourced)
3. [current-state.md](current-state.md) — FTF's deck pipeline today, file:line-cited (HEAD 786f63d)
4. [gap-analysis.md](gap-analysis.md) — 16 mechanisms compared, verdicts, dependency spine
5. [backlog.md](backlog.md) — 10 features scored + sequenced + wave plan + standing guardrails
6. `prds/` — one build-ready PRD per backlog item:

| PRD | Feature | Flag |
|---|---|---|
| [F1](prds/F1-signal-foundation.md) | Signal Foundation (impression_id spine) — **build first** | `deck.signal_v2` |
| [F2](prds/F2-thompson-v2.md) | Thompson v2 (bandit hygiene) | `deck.thompson_v2` |
| [F3](prds/F3-fatigue-suppression.md) | Fatigue & durable suppression | `deck.fatigue` |
| [F4](prds/F4-session-rerank.md) | Session re-rank (bends in one session) | `deck.session_rerank` |
| [F5](prds/F5-taste-vectors.md) | Trade-taste vectors | `deck.taste_vectors` |
| [F7](prds/F7-exploration-slots.md) | Exploration slots & archetype audition | `deck.exploration` |
| [F8](prds/F8-offline-eval.md) | Offline eval harness (replay/IPS) | — (operator tooling) |
| [F6](prds/F6-value-model.md) | Learned acceptance heads × V-vector — **build last, gated on F8** | `deck.value_model` |
| [F9](prds/F9-first-session-win.md) | First-session win engineering | `deck.first_session` |
| [F10](prds/F10-deck-replenishment.md) | Deck replenishment ritual | `deck.replenishment` |

F11 (intent knobs on generate) deliberately has **no PRD here** — it defers to the operator's own
#168/#172 looking-for-intents work; F5 is its learned complement.

Raw independent-researcher outputs live in gitignored `feedback-workspace/tiktok-discovery/`
(T1A/T1B presentment, T2A/T2B models, CS current-state).

## The strategy in one line

Keep the one-card forced-verdict format (already right), build the logging spine first (F1 — the
impossible-to-retrofit-later piece), layer correctness fixes then taste-learning on the existing
generator (which becomes the retrieval stage), evaluate offline before live, and reject the
compulsion mechanics — north star is trades proposed/accepted per weekly-active, never minutes.
