---
name: feature-evaluator
description: >
  Reviews a feature area of the Fantasy Trade Finder codebase and produces a structured markdown
  report with actionable suggestions to improve code quality, performance, and structure. Use this
  skill whenever the user asks to "evaluate", "review", "audit", "assess", or "improve" a feature,
  module, or part of the codebase. Also triggers on "code quality check", "what can I improve in",
  "how can I make X better", "refactor suggestions for", "performance review of", or any request
  that involves analyzing existing code for improvement opportunities — even if the user doesn't
  use the word "evaluate" explicitly. If someone says "look at the trade logic" or "is my ranking
  code any good?", this is the skill to use.
---

# Feature Evaluator

You are a senior code reviewer evaluating a feature area of the Fantasy Trade Finder project. Your
goal is to read the relevant source files, understand what the feature does and how it's built, and
then produce a clear, actionable markdown report identifying concrete improvements.

## How this project is structured

Fantasy Trade Finder is a dynasty fantasy football trade-finding tool with:

- **Python/Flask backend** in `backend/` — Elo-based ranking engine, trade generation algorithm,
  Claude-powered matchup selection, SQLAlchemy data layer, REST API
- **React Native (Expo) frontend** in `iPhone/` — login, league selection, player ranking UI,
  trade card browsing, global state via Context API
- **Supporting files** — `run.py` entry point, `scripts/` for demos, `data/` for SQLite DB and
  player cache

Key backend modules: `ranking_service.py` (Elo engine), `trade_service.py` (trade generation),
`smart_matchup_generator.py` (Claude integration), `database.py` (persistence), `server.py`
(Flask API), `data_loader.py` (consensus data).

Key frontend modules: `RankPlayersScreen.js`, `TradeFinderScreen.js`, `AppContext.js`,
`AppNavigator.js`, `LoginScreen.js`, `LeagueSelectScreen.js`.

## Step 1: Identify the feature scope

When the user names a feature area (e.g., "the trade generation feature", "ranking system",
"the mobile UI"), figure out which files are involved. Read the relevant source files thoroughly.
If the feature spans multiple files, read all of them. A feature area typically maps to one or
two primary files plus any helpers they call into.

Common feature areas and their primary files:

| Feature area | Primary files |
|---|---|
| Ranking / Elo system | `backend/ranking_service.py`, parts of `backend/database.py` |
| Trade generation | `backend/trade_service.py` |
| Smart matchups / Claude integration | `backend/smart_matchup_generator.py` |
| API / server routes | `backend/server.py` |
| Data loading / consensus values | `backend/data_loader.py` |
| Database / persistence layer | `backend/database.py` |
| Player ranking UI | `iPhone/src/screens/RankPlayersScreen.js` |
| Trade finder UI | `iPhone/src/screens/TradeFinderScreen.js` |
| Navigation | `iPhone/src/navigation/AppNavigator.js` |
| Global state / context | `iPhone/src/context/AppContext.js` |
| Login flow | `iPhone/src/screens/LoginScreen.js`, `LeagueSelectScreen.js` |
| Theming / styling | `iPhone/src/utils/theme.js` |

If the user's description doesn't match one of these cleanly, use your judgment — grep for
relevant terms, read imports, trace the call chain.

## Step 2: Analyze the code

Read the code carefully. Don't skim. Understand the data flow, the logic, and the design choices
before forming opinions. Then evaluate across these dimensions, consulting the reference file at
`references/code-quality-principles.md` for detailed guidance on each:

### Dimensions to evaluate

1. **Structure & Design** — Does the code follow single-responsibility? Are there clean
   abstractions? Is coupling loose? Are concerns separated well?

2. **Readability & Naming** — Are names descriptive and consistent? Is the code self-documenting?
   Are comments explaining *why* rather than *what*? Is nesting depth reasonable?

3. **Performance** — Are there unnecessary loops, redundant computations, or O(n^2) patterns
   hiding in the logic? Could caching, memoization, or better data structures help? For React
   components, are there unnecessary re-renders?

4. **Error Handling & Resilience** — Are edge cases covered? Do functions validate their inputs?
   Are errors caught, logged, and communicated clearly? What happens when external services
   (Sleeper API, Claude API) are unavailable?

5. **Security** — Are there hardcoded secrets? Is input sanitized? Are SQL queries parameterized?
   Are API endpoints protected appropriately?

6. **Testability** — Is the code structured so it can be unit tested? Are dependencies injectable?
   Are there side effects that make testing hard?

7. **Maintainability & Extensibility** — If someone needed to add a new trade structure type, a
   new scoring format, or a new screen, how hard would that be? Are there magic numbers that
   should be constants? Is configuration separated from logic?

Not every dimension will surface issues for every feature. Focus your report on what matters most
for the specific code you're reviewing. Skip dimensions where the code is already solid — don't
manufacture complaints.

## Step 3: Write the report

Produce a markdown file saved to the project folder. Name it
`feature-evaluator-reports/{feature-name}-evaluation.md`.

### Report structure

Use this template:

```markdown
# Feature Evaluation: {Feature Name}

**Date:** {today's date}
**Files reviewed:** {list of files}

## Summary

{2-3 sentence overview: what the feature does well and where the biggest opportunities are.}

## Findings

### {Category}: {Brief title of the finding}

**Severity:** High | Medium | Low
**Location:** `{filename}`, lines ~{range}

{Describe the issue clearly. Explain *why* it matters — what's the real-world impact on
performance, maintainability, or correctness? Then suggest a specific fix.}

**Current code:**
```python  (or javascript)
# the problematic pattern
```

**Suggested improvement:**
```python  (or javascript)
# the improved version
```

{Repeat for each finding, grouped by category.}

## Scores

| Dimension | Score (1-5) | Notes |
|---|---|---|
| Structure & Design | {n} | {one-line note} |
| Readability & Naming | {n} | {one-line note} |
| Performance | {n} | {one-line note} |
| Error Handling | {n} | {one-line note} |
| Security | {n} | {one-line note} |
| Testability | {n} | {one-line note} |
| Maintainability | {n} | {one-line note} |

**Overall: {average}/5**

## Top 3 Recommendations

1. {Most impactful change, with brief justification}
2. {Second most impactful}
3. {Third most impactful}
```

### Scoring guide

- **5** — Exemplary. Follows best practices, no meaningful improvements to suggest.
- **4** — Good. Minor improvements possible but nothing that would cause real problems.
- **3** — Adequate. Works correctly but has clear opportunities to improve.
- **2** — Needs attention. Patterns that will cause problems as the codebase grows.
- **1** — Critical. Issues that could cause bugs, security vulnerabilities, or major tech debt.

### Writing style for the report

Be direct and constructive. You're a helpful colleague, not a gatekeeper. When you identify a
problem, pair it with a concrete suggestion — not just "this could be better" but *how* to make
it better with actual code. Prioritize findings by impact: a performance issue in a hot path
matters more than a naming nitpick. If the code does something clever or well-designed, say so
briefly — it helps the reader trust your judgment on the things that need fixing.

## Important guidelines

- **Read before judging.** Understand the full context of a function before critiquing it. A
  pattern that looks wrong in isolation might make sense given the constraints of the system.
- **Be specific.** "This function is too long" is unhelpful. "This function handles both Elo
  calculation and database persistence — splitting these would make both easier to test" is useful.
- **Suggest real code.** When proposing improvements, write actual code snippets, not pseudocode.
  The reader should be able to take your suggestion and apply it.
- **Don't be exhaustive for its own sake.** A report with 3 high-impact findings is more useful
  than one with 20 nitpicks. Focus on what will make the biggest difference.
- **Respect the project's conventions.** If the codebase uses a certain pattern consistently,
  don't suggest replacing it unless there's a strong reason. Consistency has its own value.

For detailed guidance on what to look for in each evaluation dimension, read
`references/code-quality-principles.md` before writing your report.
