"""Independent, small graph resource controls; no SQL or provider access."""
from copy import deepcopy
import hashlib

import pytest

from backend import prepared_trade_payload_v2 as codec
from backend.deck_diagnostics import dumps, REFERENCE_KEY
from backend.tests.test_prepared_trade_payload import isolated_config


def _diagnostic_chain(length, *, repeated=False):
    """Small genuine scoped hashes; root size is modest in these unit controls."""
    values, expanded, prior = {}, "leaf", None
    for _ in range(length):
        if prior is None:
            body = expanded
        elif repeated:
            body = [{REFERENCE_KEY: prior}, {REFERENCE_KEY: prior}]
            expanded = [expanded, expanded]
        else:
            body = {"nested": {REFERENCE_KEY: prior}}
            expanded = {"nested": expanded}
        sid = hashlib.sha256((dumps(("viewer", "prepared-job")) + "\n" + dumps(expanded)).encode()).hexdigest()
        values[sid] = {"snapshot_id": sid, "user_id": "viewer", "deck_job_id": "prepared-job",
                       "created_at": "2026-09-22T12:00:00+00:00", "payload_json": dumps(body)}
        prior = sid
    return values, prior


class DiagnosticReader:
    def __init__(self, nodes):
        self.nodes = nodes

    def get_nodes(self, snapshot_ids):
        return {sid: deepcopy(self.nodes[sid]) for sid in snapshot_ids if sid in self.nodes}


def test_diagnostic_depth_cannot_depend_on_prior_cache_warming():
    nodes, root = _diagnostic_chain(100)
    cold = codec.DiagnosticResolver(DiagnosticReader(nodes), user_id="viewer", job_id="prepared-job")
    with pytest.raises(ValueError, match="depth"):
        cold.validate_node(root)
    warmed = codec.DiagnosticResolver(DiagnosticReader(nodes), user_id="viewer", job_id="prepared-job")
    # Validating prior nodes cannot certify a root rejected from a cold cache.
    with pytest.raises(ValueError, match="depth"):
        for sid in nodes:
            warmed.validate_node(sid)


def test_amplified_diagnostic_is_rejected_before_materialization(monkeypatch):
    nodes, root = _diagnostic_chain(12, repeated=True)
    monkeypatch.setattr(codec, "MAX_EXPANDED_BYTES", 1024)
    resolver = codec.DiagnosticResolver(DiagnosticReader(nodes), user_id="viewer", job_id="prepared-job")
    monkeypatch.setattr(resolver, "_materialize", lambda *a: pytest.fail("allocated rejected expanded graph"))
    with pytest.raises(ValueError, match="amplification"):
        resolver.expand({REFERENCE_KEY: root})

