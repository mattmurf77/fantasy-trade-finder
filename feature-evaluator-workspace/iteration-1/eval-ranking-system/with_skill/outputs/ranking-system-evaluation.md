# Feature Evaluation: Ranking System (Elo Engine)

**Date:** 2026-04-12
**Files reviewed:** `backend/ranking_service.py`, `backend/database.py`, `backend/server.py` (integration points)

## Summary

The ranking system is a well-architected Elo engine that intelligently decomposes 3-player interactions into pairwise comparisons for efficiency. The code demonstrates solid design fundamentals: clean separation of concerns, thoughtful data models, and a principled approach to configuration management. However, there are concrete opportunities in three areas: (1) defensive programming—edge cases in replay logic and division by zero risks; (2) performance—unnecessary recomputation and collection size assumptions; (3) maintainability—scattered business logic and floating-point precision. These are not blockers but will matter as the codebase scales.

## Findings

### Error Handling & Resilience: Silent failure in get_next_trio fallback

**Severity:** Medium
**Location:** `ranking_service.py`, lines ~270–283

The `get_next_trio()` method falls back to the algorithmic trio selection if the smart matchup generator raises *any* exception. While defensive, this silently swallows real errors (database connectivity, Claude API failures, etc.) that operators should know about. The current code makes debugging difficult.

**Current code:**
```python
if self._generator is not None:
    try:
        from .smart_matchup_generator import SwipeDecision as SD
        history = [SD(winner_id=s.winner_id, loser_id=s.loser_id) for s in self._swipes]
        trio = self._generator.generate_next_trio(
            players=pool,
            swipe_history=history,
            position_filter=position,
        )
        return trio
    except Exception:
        pass

return self._algorithmic_trio(pool)
```

**Suggested improvement:**
```python
if self._generator is not None:
    try:
        from .smart_matchup_generator import SwipeDecision as SD
        history = [SD(winner_id=s.winner_id, loser_id=s.loser_id) for s in self._swipes]
        trio = self._generator.generate_next_trio(
            players=pool,
            swipe_history=history,
            position_filter=position,
        )
        return trio
    except Exception as e:
        # Log the error but allow fallback for graceful degradation
        import logging
        logging.warning(f"Smart matchup generator failed, using algorithmic fallback: {e}")

return self._algorithmic_trio(pool)
```

---

### Performance: Unnecessary recomputation in _algorithmic_trio

**Severity:** Medium
**Location:** `ranking_service.py`, lines ~448–479

The `_algorithmic_trio()` method calls `_compute_elo()` and `_compute_stats()` every time it's invoked, even though these have just been computed by the caller in `get_rankings()`. Since ranking pools can contain 50–200 players, this duplicates O(n × m) work where m is the number of swipes (which can grow unbounded).

**Current code:**
```python
def _algorithmic_trio(self, pool: list[Player]) -> MatchupTrio:
    """Pick 3 adjacent players in Elo order that haven't all been compared."""
    elo          = self._compute_elo(pool)       # Recomputes
    sorted_p     = sorted(pool, key=lambda p: elo[p.id], reverse=True)
    stats        = self._compute_stats(pool)     # Recomputes
    # ...
```

**Suggested improvement:**
```python
def _algorithmic_trio(self, pool: list[Player], 
                      elo: dict[str, float] = None,
                      stats: dict[str, dict] = None) -> MatchupTrio:
    """Pick 3 adjacent players in Elo order that haven't all been compared."""
    if elo is None:
        elo = self._compute_elo(pool)
    if stats is None:
        stats = self._compute_stats(pool)
    
    sorted_p = sorted(pool, key=lambda p: elo[p.id], reverse=True)
    # ... rest of method
```

Then update `get_next_trio()`:
```python
def get_next_trio(self, position: Optional[str] = None) -> MatchupTrio:
    pool = self._pool(position)
    if len(pool) < 3:
        raise ValueError(f"Need at least 3 players for position={position\!r}")

    if self._generator is not None:
        # ... smart generator logic ...

    # Precompute once, pass to fallback
    elo = self._compute_elo(pool)
    stats = self._compute_stats(pool)
    return self._algorithmic_trio(pool, elo=elo, stats=stats)
```

---

### Maintainability & Extensibility: Magic numbers in _algorithmic_trio window size

**Severity:** Low
**Location:** `ranking_service.py`, lines ~456–458

The nested loops that search for candidate trios use hardcoded window sizes (5) with no explanation. These thresholds shape which matchups are surfaced—they're business logic, not implementation details.

**Current code:**
```python
for i in range(len(sorted_p) - 2):
    for j in range(i + 1, min(i + 5, len(sorted_p) - 1)):
        for k in range(j + 1, min(j + 5, len(sorted_p))):
```

**Suggested improvement:**
```python
# At class level
TRIO_SEARCH_WINDOW = 5  # Search window size for candidate trio selection

def _algorithmic_trio(self, pool: list[Player]) -> MatchupTrio:
    # ...
    for i in range(len(sorted_p) - 2):
        for j in range(i + 1, min(i + self.TRIO_SEARCH_WINDOW, len(sorted_p) - 1)):
            for k in range(j + 1, min(j + self.TRIO_SEARCH_WINDOW, len(sorted_p))):
```

And document the reasoning in a docstring or comment explaining why 5 was chosen (e.g., "empirically found to balance freshness vs. search cost").

---

### Structure & Design: Division-by-zero risk in replay_from_db

**Severity:** Medium
**Location:** `ranking_service.py`, lines ~369–372

The replay logic reconstructs interaction counts by dividing swipe counts by 3 (to convert pairwise swipes back to 3-player interactions). However, if the swipe history is corrupted or contains orphaned rank swipes, the math breaks down silently.

**Current code:**
```python
self._interactions = {
    pos: cnt // 3
    for pos, cnt in pos_swipe_counts.items()
}
```

**Suggested improvement:**
```python
self._interactions = {}
for pos, cnt in pos_swipe_counts.items():
    # Sanity check: rank swipes should always be in multiples of 3
    if cnt % 3 \!= 0:
        logging.warning(
            f"Rank swipe count for {pos} is {cnt} (not divisible by 3); "
            f"possible data corruption. Using integer division."
        )
    self._interactions[pos] = cnt // 3
```

---

### Error Handling & Resilience: Missing input validation in record_ranking

**Severity:** Low
**Location:** `ranking_service.py`, lines ~180–184

The method validates that player IDs exist but doesn't check for duplicates in `ordered_ids`. If a user submits the same player twice (a client-side bug or injection), the decomposition creates self-comparison rows (A > A), which are logically nonsensical.

**Current code:**
```python
if len(ordered_ids) < 2:
    raise ValueError("Need at least 2 player IDs")
for pid in ordered_ids:
    if pid not in self._players:
        raise ValueError(f"Unknown player id: {pid\!r}")
```

**Suggested improvement:**
```python
if len(ordered_ids) < 2:
    raise ValueError("Need at least 2 player IDs")
if len(ordered_ids) \!= len(set(ordered_ids)):
    raise ValueError("Duplicate player IDs in ranking")
for pid in ordered_ids:
    if pid not in self._players:
        raise ValueError(f"Unknown player id: {pid\!r}")
```

---

### Readability & Naming: Config accessor function naming

**Severity:** Low
**Location:** `ranking_service.py`, lines ~48–49

The `_c()` function is a 1-character name that shadows Python's built-in semantics. While short names are acceptable for true hot-path accessors, this makes searching and linting harder.

**Current code:**
```python
def _c(key: str) -> float:
    return _cfg.get(key, _DEFAULT_CFG[key])
```

**Suggested improvement:**
```python
def _get_config(key: str) -> float:
    """Get a runtime config value with fallback to default."""
    return _cfg.get(key, _DEFAULT_CFG[key])

# Then update all callsites: _c("elo_k") → _get_config("elo_k")
```

Alternatively, if brevity is preferred for readability in tight loops:
```python
def _c(key: str) -> float:  # Get config value (see reload_config)
    """Retrieve a runtime ELO K-factor or fallback to default."""
    return _cfg.get(key, _DEFAULT_CFG[key])
```

---

### Testability: Hard-to-mock generator dependency

**Severity:** Low
**Location:** `ranking_service.py`, lines ~150–162

The `matchup_generator` is injected as a positional argument but only used in one method. This makes the dependency unclear to new readers and complicates testing (you must pass a mock or None every time you instantiate `RankingService`). A setter or lazy loading would be clearer.

**Current code:**
```python
def __init__(
    self,
    players: list[Player],
    matchup_generator=None,
    seed_ratings: Optional[dict[str, float]] = None,
):
```

**Suggested improvement:**
```python
def __init__(
    self,
    players: list[Player],
    seed_ratings: Optional[dict[str, float]] = None,
):
    # ...
    self._generator = None  # Injected via set_matchup_generator if needed

def set_matchup_generator(self, generator) -> None:
    """Optionally inject a smart matchup generator for A/B testing."""
    self._generator = generator
```

Then update `get_next_trio()` to use `self._generator` as before. This makes the optional dependency more explicit and easier to test.

---

## Scores

| Dimension | Score (1-5) | Notes |
|---|---|---|
| Structure & Design | 4 | Clean separation of Elo math, stats, and trio selection. Config reloading is well-thought-out. Minor: generator dependency could be clearer. |
| Readability & Naming | 4 | Well-named methods and data classes. `_c()` is cryptic but brief; fine for a utility. Good docstrings overall. |
| Performance | 3 | Elo computation is O(n × m) per call (necessary). Main inefficiency: trio selection recomputes Elo/stats unnecessarily. Passable for league sizes ≤500. |
| Error Handling | 3 | Validates inputs and handles missing players. Silent fallback in generator is problematic; replay logic lacks corruption detection. |
| Security | 4 | No hardcoded secrets. DB queries use parameterized inserts. No SQL injection risk visible. |
| Testability | 3 | Pure functions (compute_elo, compute_stats) are testable. Generator injection makes mocking awkward. No unit tests in repo. |
| Maintainability | 4 | Config management is centralized and runtime-tunable. Magic numbers in trio search could be constants. Codebase is compact and readable. |

**Overall: 3.6/5**

---

## Top 3 Recommendations

1. **Precompute Elo and stats before trio selection** (Medium impact, low effort). Cache the results of `_compute_elo()` and `_compute_stats()` during `get_rankings()` and pass them to `_algorithmic_trio()` to avoid O(n × m) recomputation. This is the highest-impact perf win and costs minimal refactoring.

2. **Log generator failures instead of silently swallowing them** (Medium impact, trivial effort). Replace the bare `except Exception: pass` in `get_next_trio()` with `logging.warning()` to help operators diagnose smart matchup outages without guessing.

3. **Add data corruption detection in replay_from_db** (Low impact, low effort). Check that rank swipe counts are divisible by 3 before dividing; log a warning if not. Protects against silent state corruption from database bugs or manual edits.

**Bonus:** Extract `TRIO_SEARCH_WINDOW = 5` as a named constant with a comment explaining the choice. This clarifies intent and makes it easy to tune later.
