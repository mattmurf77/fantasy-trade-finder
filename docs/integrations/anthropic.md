# Anthropic — Claude-powered matchup selection

> Optional AI assist that picks the most informative next player comparison for the ranking swipe interface. Off by default in the sense that it silently no-ops without an API key; on by default (via `smart_matchup_enabled=1`) once a key is present. Fail-soft everywhere — a Claude outage degrades to the algorithmic selector, never a user-visible error.

## Table of Contents

- [What it is](#what-it-is)
- [Model / endpoint](#model--endpoint)
- [When it triggers](#when-it-triggers)
- [Request shape](#request-shape)
- [Response consumption](#response-consumption)
- [Error / fallback behavior](#error--fallback-behavior)
- [Cost and frequency](#cost-and-frequency)
- [Instrumentation guidance](#instrumentation-guidance)
- [Source](#source)

## What it is

`backend/smart_matchup_generator.py` (`SmartMatchupGenerator`) uses the Anthropic Python SDK to ask Claude which of ~10 candidate player pairs/trios is the most "dynasty-informative" next comparison to show a user in the swipe-ranking UI — i.e., which comparison will most reduce uncertainty in that user's personal Elo ranking. Candidate generation and Elo math are pure local computation; Claude is used only to pick among already-computed candidates, not to generate values or run the ranking math itself.

## Model / endpoint

- **Model:** `claude-sonnet-4-6` (`SmartMatchupGenerator.MODEL`)
- **SDK call:** `anthropic.Anthropic(api_key=...).messages.create(model=MODEL, max_tokens=300, messages=[{"role": "user", "content": prompt}])` — a single-turn, non-streaming Messages API call. No tool use, no system prompt, no conversation history carried across calls.
- **`max_tokens`:** 300 for both the pair-matchup and the trio-matchup calls.

## When it triggers

Gated by three conditions, all must hold:

1. **`ANTHROPIC_API_KEY` env var is set** at process boot (`backend/server.py`). If unset, `matchup_gen` stays `None` and the app logs `ℹ️  No ANTHROPIC_API_KEY — using algorithmic matchup selection` — no import of `anthropic`, no client constructed, zero possibility of a call.
2. **`smart_matchup_enabled` model_config flag == 1.0** (default: `1.0`, i.e. on once a key exists — `backend/database.py` `_MODEL_CONFIG_DEFAULTS`, `backend/ranking_service.py`).
3. **The trio-selection "variety" lane resolves to `tightest`.** `RankingService._pick_trio_variety` first rolls a weighted choice among `boundary` / `within_tier` / `cross_pos` / `tightest` trio-generation strategies (weights `trio_boundary_rate` / `trio_within_tier_rate` / `trio_cross_pos_rate`, see `docs/config-reference.md`). Only the `tightest` lane — and only when that lane's non-AI strategies produce nothing — reaches the Claude call in `RankingService._next_trio` (`backend/ranking_service.py`, `self._generator.generate_next_trio(...)`). At default weights (`boundary` 0.4, `within_tier` 0.35) this is roughly a quarter of trio-serve requests, not all of them.

`SmartMatchupGenerator` also exposes a pair-based `generate_next_matchup()`/`_ask_claude()` path (used historically for 2-player swipes); the currently-wired production caller is the 3-player trio path (`generate_next_trio()`/`_ask_claude` inside it).

## Request shape

**What's sent to Claude, per call:** a text prompt listing ~10 candidate matchups (pairs or trios), each rendered as: player name, position, team, age, years of NFL experience, that player's **locally-computed Elo rating** (derived purely from this user's own swipe history, seeded from DynastyProcess/KeepTradeCut consensus — see `docs/integrations/dynastyprocess.md`), and win/loss counts from prior swipes. Plus: total swipe count so far, and the active position filter (or "All positions"). Example line from the trio prompt:

```
1. Ja'Marr Chase (WR, CIN, age 26) [Elo 1823]  |  Justin Jefferson (WR, MIN, age 27) [Elo 1811]  |
   Puka Nacua (WR, LAR, age 24) [Elo 1798]  (spread 25, 1/3 pairs already compared)
```

**Privacy considerations:** no user-identifying data leaves the process — no username, user id, session token, league id, or Sleeper/ESPN/MFL identifiers appear in the prompt. The only "personal" signal is derivational: the Elo numbers reflect that particular user's private swipe preferences, but they're sent as bare numbers attached to public NFL player names — not attributable to a person without already having their session. Player bio data (name/team/age/experience) is public information available from any fantasy football source. No request/response content is currently persisted to disk or a database — it exists only for the duration of the API call.

## Response consumption

Claude is instructed to respond with JSON only: `{"selected_index": <1-based int>, "reasoning": "<1-2 sentences>"}`. The code:
1. Strips markdown code fences if present (`raw.split("```")`).
2. `json.loads()`s the remainder.
3. Clamps `selected_index` into range (`max(0, min(idx, len(candidates) - 1))`) — a malformed or out-of-range index degrades to a valid candidate rather than raising.
4. Returns the chosen candidate players plus Claude's `reasoning` string. The reasoning text is not currently surfaced to end users or logged anywhere — it's returned by the function but the wiring in `ranking_service.py` discards it (only the player selection is used).

A JSON parse failure (bad fences, non-JSON content, missing `selected_index` key) raises inside `_ask_claude`/`generate_next_trio`, which is caught by the caller (see below) — it does not propagate to the user.

## Error / fallback behavior

- **No API key:** `matchup_gen = None` at boot; the `tightest` lane in `_next_trio` never attempts a Claude call (`self._generator is not None` gate fails) and falls straight to `_algorithmic_trio` — the local Elo-adjacency heuristic with no external call.
- **Key present but `smart_matchup_enabled` flag off:** same — falls to `_algorithmic_trio`.
- **Any exception during the Claude call** (network failure, timeout, rate limit, malformed JSON response, SDK error) — caught by a bare `except Exception: trio = None` in `RankingService._next_trio` (`backend/ranking_service.py`), which then falls through to `_algorithmic_trio`. **No retry, no backoff, no circuit breaker** — every eligible trio request independently re-attempts the Claude call; a sustained Anthropic outage means a sustained per-request latency/cost hit (see below) with silent fallback, not a cached "Claude is down, stop trying" state.
- **User-visible impact of any failure:** none. The trio is served either way; only the *selection strategy* changes (Claude-informed vs. purely-algorithmic "tightest" ordering). No error surfaces to the client.
- **SDK import failure at boot** (e.g. `anthropic` package missing): caught at construction (`try: from .smart_matchup_generator import SmartMatchupGenerator; matchup_gen = SmartMatchupGenerator(api_key=api_key) except Exception as e: print(f"⚠️  Claude generator unavailable ({e}), using algorithmic fallback")`) — same fail-soft outcome.

## Cost and frequency

- **Frequency:** at most one API call per served trio, only for requests that land in the `tightest` variety lane (see "When it triggers" above — roughly a quarter of trio requests at default weights) AND only when that lane's earlier non-AI strategies didn't already produce a trio. No batching — one HTTP round-trip per eligible request.
- **Token volume:** small and bounded — prompt is ~10 candidate lines of short text (a few hundred tokens) plus a fixed instruction block; `max_tokens=300` caps the response. No conversation history, no system prompt, no large context.
- **No caching** of Claude's selection — every eligible request is a fresh call, even for an unchanged candidate set (this is intentional: swipe history changes between requests, which changes the Elo ratings and thus the candidate ranking).
- **No usage/cost tracking today** — the SDK call's token usage (`message.usage.input_tokens` / `output_tokens`, available on the `Message` response) is not read or logged anywhere in the current code.

## Instrumentation guidance

**Must redact:** the `ANTHROPIC_API_KEY` value itself (never log it — it isn't logged today), and **full prompt contents** — the candidate-matchup listing and Claude's `reasoning` string should not be logged verbatim in production telemetry (they're low-sensitivity but unbounded free text; log shape, not content).

**Safe / recommended to log** (structured, per call):
- **Status:** success / fallback-triggered / exception (and which fallback path was hit — no-key, flag-off, or exception-in-call).
- **Latency:** wall-clock time of the `messages.create()` call.
- **Token counts:** `message.usage.input_tokens` / `output_tokens` from the SDK response — currently unread; capturing them is the main gap for cost visibility, since there is no cost tracking today.
- **Fallback-used flag:** boolean, `True` whenever `_algorithmic_trio` is reached instead of a Claude-selected trio, plus the reason enum (no_key / flag_off / boundary_or_within_lane_handled_it / exception).
- **Prompt CLASS/size only:** e.g. `candidate_count=10, position_filter="WR", swipe_count=47` — never the rendered prompt string or the `reasoning` text itself.

No existing log lines cover this path today (`_ask_claude`/`generate_next_trio` have no logging at all; the only related log lines are the boot-time `✅ Claude matchup generator enabled` / `ℹ️  No ANTHROPIC_API_KEY — using algorithmic matchup selection` / `⚠️  Claude generator unavailable (...)` in `backend/server.py`). Adding call-level logging per the fields above is a genuine gap, not a refactor of existing instrumentation.

## Source

- `backend/smart_matchup_generator.py` — `SmartMatchupGenerator`, `_ask_claude`, `generate_next_trio`
- `backend/server.py` — boot-time wiring (`api_key = os.environ.get("ANTHROPIC_API_KEY")`)
- `backend/ranking_service.py` — `_next_trio`, the `tightest`-lane gate, `_c("smart_matchup_enabled")`, `_algorithmic_trio` fallback
- `backend/database.py` — `_MODEL_CONFIG_DEFAULTS` entry for `smart_matchup_enabled`
- `docs/config-reference.md` — `ANTHROPIC_API_KEY`, `smart_matchup_enabled`, `trio_boundary_rate`, `trio_within_tier_rate`
- `docs/architecture.md` — data-flow diagram (External → `AN[Anthropic Claude API]`)
