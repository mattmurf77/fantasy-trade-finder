# Code Quality Principles Reference

This document provides detailed guidance for each evaluation dimension. Consult it when
analyzing a feature — it helps calibrate what "good" looks like and what patterns to flag.

## Table of Contents

1. [Structure & Design](#structure--design)
2. [Readability & Naming](#readability--naming)
3. [Performance](#performance)
4. [Error Handling & Resilience](#error-handling--resilience)
5. [Security](#security)
6. [Testability](#testability)
7. [Maintainability & Extensibility](#maintainability--extensibility)
8. [Python-Specific Patterns](#python-specific-patterns)
9. [React Native / JavaScript Patterns](#react-native--javascript-patterns)

---

## Structure & Design

### SOLID Principles

**Single Responsibility:** Each class or function should have one reason to change. A function
that fetches data from an API, transforms it, and writes it to the database is doing three things.
Split it.

**Open/Closed:** Code should be extendable without modifying existing logic. Look for switch
statements or if/else chains that would need editing every time a new variant is added — these
are candidates for polymorphism or strategy patterns.

**Dependency Inversion:** High-level modules should not depend on low-level details. If a
service directly instantiates a database connection, it's tightly coupled. Prefer injecting
dependencies so they can be swapped or mocked.

### What to look for

- Functions longer than ~50 lines (Python) or ~40 lines (JS) — usually doing too much
- Classes with many unrelated methods — consider splitting
- Deep inheritance hierarchies — prefer composition
- God objects that know about everything — break into focused services
- Circular imports or dependencies — sign of tangled architecture
- Business logic mixed with I/O (database calls, API calls, file operations)

---

## Readability & Naming

### Naming conventions

- **Python:** snake_case for functions/variables, PascalCase for classes, UPPER_SNAKE for constants
- **JavaScript/React:** camelCase for functions/variables, PascalCase for components/classes
- Boolean variables should read as questions: `is_active`, `has_completed`, `should_retry`
- Functions should be verbs: `calculate_elo`, `fetch_players`, `generate_trades`
- Avoid abbreviations that aren't universally understood (`usr`, `mgr`, `proc`)

### What to look for

- Inconsistent naming patterns within the same file
- Single-letter variables outside of loop counters or comprehensions
- Misleading names (a function called `get_players` that also modifies state)
- Comments that restate the code instead of explaining *why*
- Deeply nested code (more than 3-4 levels) — use early returns or extract functions
- Magic numbers without named constants (e.g., `if score > 1500` — what's 1500?)

---

## Performance

### Algorithmic complexity

- Nested loops over the same data set → O(n^2) or worse. Can an index, set, or hash map help?
- Repeated database queries in loops (N+1 problem)
- Sorting when only the top-k elements are needed (use a heap)
- String concatenation in loops (use join or StringBuilder patterns)

### Caching and memoization

- Functions called repeatedly with the same arguments — cache results
- Data fetched from external APIs on every request — consider TTL caching
- Expensive computations that could be precomputed at startup or on schedule

### Data structure choices

- Lists used for membership checks → use sets for O(1) lookup
- Scanning a list to find an item by key → use a dictionary
- Repeatedly inserting into / removing from the middle of a list → use a deque or linked list

### React-specific performance

- Components re-rendering when their props haven't changed → use React.memo
- Expensive calculations in render → use useMemo
- Callback functions recreated every render → use useCallback
- Large lists without virtualization → use FlatList (React Native) with proper key extraction
- State updates that trigger unnecessary re-renders in siblings

---

## Error Handling & Resilience

### Input validation

- Functions that accept external data (API requests, user input) should validate before processing
- Type checks, range checks, null/undefined checks at boundaries
- Fail fast with clear error messages rather than propagating bad data

### Exception handling

- Catch specific exceptions, not bare `except:` or `catch(e)` with no filtering
- Don't swallow exceptions silently — at minimum, log them
- Include context in error messages: what was the input? What was expected?
- Distinguish between recoverable errors (retry, fallback) and fatal ones (fail clearly)

### External service resilience

- What happens when the Sleeper API is down? Does the app crash or degrade gracefully?
- What happens when the Claude API times out? Is there a fallback?
- Are there retries with exponential backoff for transient failures?
- Are there timeouts on HTTP requests?

### What to look for

- Bare `try/except: pass` blocks
- Error messages that say "something went wrong" with no detail
- No handling for None/null returns from functions that can fail
- Async operations without error handling
- Missing finally/cleanup blocks for resources (file handles, DB connections)

---

## Security

### Secrets and credentials

- API keys hardcoded in source → should be in environment variables
- Secrets committed to git → should be in .gitignore, use .env files
- Secrets logged to console or files → mask or omit sensitive values

### Input sanitization

- SQL queries built with string interpolation → use parameterized queries (SQLAlchemy handles
  this when used correctly, but raw SQL strings are a risk)
- User input rendered without escaping → XSS risk in web contexts
- File paths constructed from user input → path traversal risk

### API security

- Endpoints that modify data without authentication or authorization checks
- No rate limiting on public endpoints
- Sensitive data returned in API responses that doesn't need to be there
- CORS configured too permissively

### Dependency security

- Known vulnerabilities in pinned dependency versions
- Unpinned dependencies that could pull in breaking or vulnerable versions
- Unnecessary dependencies that increase attack surface

---

## Testability

### What makes code testable

- Functions with clear inputs and outputs (pure functions where possible)
- Dependencies injected rather than instantiated internally
- Side effects isolated to the edges of the system
- Small, focused functions that test one thing

### What to look for

- Global state that tests can't control or reset
- Functions that directly call external APIs with no way to stub them
- Complex setup required just to test a small piece of logic
- Business logic buried inside framework-specific code (Flask route handlers, React components)
- Missing test files entirely — note this but don't penalize heavily if the project is early-stage

---

## Maintainability & Extensibility

### Configuration

- Magic numbers → extract to named constants or config
- Hardcoded values that might change (URLs, thresholds, feature flags) → externalize
- Configuration scattered across files → centralize

### Modularity

- Can you add a new trade structure type without modifying existing code?
- Can you add a new screen without touching navigation in 5 places?
- Are there clear boundaries between modules, or does everything reach into everything else?

### Documentation

- Do complex algorithms have explanatory comments or docstrings?
- Are non-obvious design decisions documented?
- Could a new developer understand the feature by reading the code + comments?

---

## Python-Specific Patterns

### Pythonic code

- Use list/dict/set comprehensions instead of manual loops where they improve clarity
- Use `enumerate()` instead of manual index tracking
- Use `with` statements for resource management (files, connections)
- Use `dataclasses` or `NamedTuple` for structured data instead of plain dicts
- Use `pathlib.Path` instead of string manipulation for file paths

### Common anti-patterns

- Mutable default arguments: `def foo(items=[])` — use `None` and initialize inside
- Using `type()` for type checking instead of `isinstance()`
- Bare `except:` catching everything including KeyboardInterrupt
- Not using context managers for database sessions
- Long chains of `if/elif` that could be a dictionary dispatch

### Flask-specific

- Business logic in route handlers → extract to service functions
- Request parsing mixed with response formatting → separate concerns
- No request validation → use schemas or validation decorators
- Global app state instead of proper dependency injection

---

## React Native / JavaScript Patterns

### Component design

- Components doing too much → split into presentational and container components
- Inline styles repeated across components → extract to shared theme/styles
- Props drilling through many levels → consider Context or state management
- Missing PropTypes or TypeScript types for component props

### State management

- State stored at the wrong level (too high causes unnecessary re-renders, too low forces
  prop drilling)
- Derived state stored separately instead of computed from source state
- Multiple sources of truth for the same data
- useEffect used for synchronization that could be handled by event handlers

### Common anti-patterns

- Anonymous functions in JSX props (creates new reference every render)
- Array index as key in lists (breaks diffing when list changes)
- Missing cleanup in useEffect (memory leaks with subscriptions/timers)
- Fetching data in components without loading/error states
- Hardcoded strings instead of constants or i18n keys
