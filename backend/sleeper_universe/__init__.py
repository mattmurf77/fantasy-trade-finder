"""Sleeper trade universe: a research crawler for completed Sleeper trades.

Research tooling, not app code. The Flask app never imports this package and
it never touches the app database. It reads Sleeper's public REST v1 API
through ONE throttled client (``client.py``), strips identity with an
allow-list before anything reaches disk (``identity.py``), and keeps a local
store in ``data/sleeper-universe/`` (``store.py``).

Pipeline: ``discover`` (seeds -> leagues, breadth-first, lineage) -> ``pull``
(one checkpoint per league-season) -> ``derive`` (trades, assets, standings,
outcomes, roster reconstruction, pick resolution, cleaning flags) ->
``report`` (aggregates + leak scan). Entry point: ``scripts/sleeper_universe.py``.
Plan: ``docs/plans/sleeper-trade-universe/`` (research-plan on its own branch;
scope.md here). Usage: ``backend/sleeper_universe/README.md``.
"""

VERSION = "1.0.0"
