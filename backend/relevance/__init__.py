"""Trade relevance engine (LLD §2.1 / D12).

Deliberately empty at import time: importing `backend.relevance` must not pull
in the database engines, the experiment cache, or anything else expensive.
Callers import the submodule they need:

    from backend.relevance.batch import batch_write
    from backend.relevance.config import resolve, valve

**ZERO Flask imports anywhere in this package** (D12 testability rationale):
every module here must be unit-testable without a Flask app or request context.
A module that needs request state takes it as an argument.
"""

__all__: list[str] = []
