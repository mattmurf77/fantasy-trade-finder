"""Nightly derive passes for the relevance engine (LLD §4.1, D12).

One module per pass. Each exposes a callable matching `registry.PassSpec.fn`
(`fn(ctx) -> dict`); the host app supplies the `PassSpec` wiring.

Same D12 rule as the rest of the package: **zero Flask imports** — a pass
takes what it needs from its `PassContext` and reads the database directly,
so it is unit-testable against a tmp SQLite engine with no app context.
"""

__all__: list[str] = []
