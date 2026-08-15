"""Nightly derive passes for the relevance engine (D12).

One module per pass. Each exposes a `run_pass(ctx)` matching
`registry.PassSpec.fn` and is importable without Flask — the host app only
supplies the `PassSpec` wiring.
"""

__all__: list[str] = []
