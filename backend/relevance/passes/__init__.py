"""Nightly pass bodies that live in the relevance package (LLD §4.1).

A pass here is a plain `fn(ctx) -> dict` registered with
`relevance.registry.PassSpec` by the host app. Same D12 rule as the rest of
the package: **zero Flask imports** — a pass takes what it needs from its
`PassContext` and reads the database directly, so it is unit-testable with a
tmp SQLite engine and no app.
"""

__all__: list[str] = []
