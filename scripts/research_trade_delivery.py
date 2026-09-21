#!/usr/bin/env python3
"""Isolated delivery protocol experiment; never imported by the application.

This does NOT evaluate fantasy trades. The caller supplies the final ordered
inventory and per-card validation/evidence assertions. SQLite here exercises
commit, retry and publication semantics, not production database performance.
All CLI timings are deterministic simulations, never measured phone latency.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Callable
import uuid


def encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@dataclass(frozen=True)
class CheckedCard:
    """Detached public payload plus an opaque reference to exact private proof."""

    public_json: str
    proof_ref: str
    checks_passed: bool = True

    @classmethod
    def from_public(cls, payload: dict, proof_ref: str, checks_passed: bool = True):
        return cls(encoded(payload).decode(), proof_ref, checks_passed)

    @property
    def public(self) -> dict:
        return json.loads(self.public_json)


class DeliveryInventory:
    """A final ranked inventory, published in atomic contiguous batches.

    ranking_complete is an explicit experimental precondition, not a computed
    certificate. No early generation-order prefix can claim final-order parity.
    The in-memory connection must remain open when simulating process recovery;
    a production implementation needs a persistent, shared store and job leases.
    """

    def __init__(self, db: sqlite3.Connection, inventory_id: str, scope: str,
                 cards: list[CheckedCard], *, ranking_complete: bool):
        if not ranking_complete:
            raise ValueError("global_order_not_final")
        if not inventory_id or ":" in inventory_id or not scope:
            raise ValueError("invalid_inventory_scope")
        ids = [card.public.get("trade_id") for card in cards]
        if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
            raise ValueError("non_unique_action_identity")
        self.db, self.inventory_id, self.scope = db, inventory_id, scope
        self.cards, self.error = tuple(cards), None
        db.execute("CREATE TABLE IF NOT EXISTS manifests (id TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS offers (
            inventory TEXT NOT NULL, ordinal INTEGER NOT NULL, payload TEXT NOT NULL,
            proof_ref TEXT NOT NULL, PRIMARY KEY (inventory, ordinal))""")
        manifest = encoded([scope, [[c.public_json, c.proof_ref, c.checks_passed] for c in cards]]).decode()
        with db:
            prior = db.execute("SELECT value FROM manifests WHERE id=?", (inventory_id,)).fetchone()
            if prior and prior[0] != manifest:
                raise ValueError("inventory_reused_with_different_terms_or_order")
            db.execute("INSERT OR IGNORE INTO manifests VALUES (?, ?)", (inventory_id, manifest))

    @property
    def ready_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM offers WHERE inventory=?", (self.inventory_id,)).fetchone()[0]

    @property
    def status(self) -> str:
        return "error" if self.error else "complete" if self.ready_count == len(self.cards) else "running"

    def publish_next(self, count: int = 30, *, fail_after: int | None = None,
                     crash_after_commit: bool = False) -> None:
        if count < 1:
            raise ValueError("batch_must_be_positive")
        start = self.ready_count
        try:
            with self.db:
                for ordinal in range(start, min(start + count, len(self.cards))):
                    card = self.cards[ordinal]
                    if not card.checks_passed or not card.proof_ref:
                        raise ValueError("required_checks_or_evidence_missing")
                    public = card.public
                    if not all(public.get(k) for k in ("opponent_user_id", "give_player_ids", "receive_player_ids")):
                        raise ValueError("incomplete_exact_terms")
                    identity = encoded([self.scope, self.inventory_id, public, card.proof_ref]).decode()
                    public["impression_id"] = uuid.uuid5(uuid.NAMESPACE_URL, identity).hex
                    public["preserve_server_order"] = True
                    self.db.execute("INSERT INTO offers VALUES (?, ?, ?, ?)",
                                    (self.inventory_id, ordinal, encoded(public).decode(), card.proof_ref))
                    if fail_after == ordinal - start + 1:
                        raise RuntimeError("injected_evidence_write_failure")
            self.error = None
        except Exception as exc:
            self.error = str(exc)
            raise
        if crash_after_commit:
            # No second in-memory publish list: committed rows ARE availability.
            raise RuntimeError("injected_crash_after_commit")

    def _authorize(self, scope: str) -> None:
        if scope != self.scope:
            raise PermissionError("foreign_inventory")

    def _ready(self) -> list[dict]:
        return [json.loads(row[0]) for row in self.db.execute(
            "SELECT payload FROM offers WHERE inventory=? ORDER BY ordinal", (self.inventory_id,))]

    def page(self, scope: str, *, cursor: str | None = None, limit: int = 30,
             eligible: Callable[[dict], bool] = lambda card: True) -> dict:
        """Cursor counts scanned inventory positions, including revoked cards.

        This eligibility hook models a fail-closed current serve-time check;
        production must invoke its real authority/disposition/ownership checks.
        It must not move an actioned card's exact terms to another identity.
        """
        self._authorize(scope)
        if not 1 <= limit <= 30:
            raise ValueError("invalid_page_size")
        version, offset_text = (cursor or f"{self.inventory_id}:0").rsplit(":", 1)
        offset, ready = int(offset_text), self._ready()
        if version != self.inventory_id or not 0 <= offset <= len(ready):
            raise ValueError("stale_or_invalid_cursor")
        result = []
        while offset < len(ready) and len(result) < limit:
            card = ready[offset]
            offset += 1
            if eligible(card):
                result.append(card)
        return {"inventory_id": self.inventory_id, "status": self.status,
                "revision": len(ready), "ready_count": len(ready),
                "total_count": len(self.cards), "cards": result,
                "next_cursor": f"{self.inventory_id}:{offset}",
                "has_more_ready": offset < len(ready),
                "inventory_complete": self.status == "complete",
                "done": self.status == "complete" and offset == len(self.cards),
                "error": self.error}

    def legacy_snapshot(self, scope: str, *,
                        eligible: Callable[[dict], bool] = lambda card: True) -> dict:
        self._authorize(scope)
        # Unnegotiated clients receive cumulative snapshots, never a page cap.
        return {"job_id": self.inventory_id, "status": self.status,
                "opponents_done": 0, "opponents_total": 0,
                "cards": [card for card in self._ready() if eligible(card)], "error": self.error}

    def action(self, scope: str, impression_id: str, exact_public: dict, *,
               eligible: Callable[[dict], bool] = lambda card: True) -> bool:
        """Read-only identity validation; deliberately performs no like/send."""
        self._authorize(scope)
        for card in self._ready():
            if card["impression_id"] == impression_id:
                keys = ("trade_id", "opponent_user_id", "give_player_ids", "receive_player_ids")
                return all(card.get(k) == exact_public.get(k) for k in keys) and eligible(card)
        return False


def poll_delivery(ready_ms: int, policy: str, *, response_ms: int = 0,
                  jitter: float = 0.0) -> tuple[float, int]:
    """Simulate first response carrying a ready card after POST returns at t=0.

    legacy models quiet-owner exponential backoff. responsive uses 250ms for
    the first 3s, 500ms to 10s, and 1s thereafter while the ready deck is low.
    A response has symmetric transit; server checks at its midpoint. This is
    a toy transport assumption, not a network measurement. No overlap occurs.
    """
    if policy not in ("legacy", "responsive") or not -.1 <= jitter <= .1:
        raise ValueError("invalid_policy_or_jitter")
    now, interval, requests = 0.0, 800.0 if policy == "legacy" else 250.0, 0
    while True:
        # Current app's first 800ms timer has no jitter.
        now += interval * (1 + jitter if requests else 1)
        requests += 1
        ready = now + response_ms / 2 >= ready_ms
        now += response_ms
        if ready:
            return now, requests
        interval = (min(round(interval * 1.5), 4000) if policy == "legacy"
                    else 250 if now < 3000 else 500 if now < 10000 else 1000)


def depletion_wait(first_ready_ms: int, next_ready_ms: int, initial: int, cards_per_second: float) -> float:
    if initial < 0 or cards_per_second <= 0 or next_ready_ms < first_ready_ms:
        raise ValueError("invalid_depletion_scenario")
    return max(0.0, next_ready_ms - first_ready_ms - 1000 * initial / cards_per_second)


def polling_phase_sweep(policy: str) -> dict:
    """Equal-weight readiness phases, explicitly not a production distribution."""
    lags = sorted(poll_delivery(ready, policy)[0] - ready for ready in range(10000, 70001, 10))
    return {"readiness_range_ms": [10000, 70000], "grid_step_ms": 10,
            "grid_points": len(lags), "median_delay_ms": lags[len(lags) // 2],
            "p95_delay_ms": lags[int((len(lags) - 1) * .95)], "max_delay_ms": max(lags)}


def response_bytes(response: dict, limit: int = 30) -> dict:
    """Pure serialization comparison. gzip bytes do not establish wire behavior."""
    full = encoded(response)
    page = encoded({**response, "cards": response.get("cards", [])[:limit]})
    return {"cards": len(response.get("cards", [])), "first_page_cards": min(limit, len(response.get("cards", []))),
            "full_json_utf8": len(full), "first_page_json_utf8": len(page),
            "full_gzip_level6": len(gzip.compress(full, compresslevel=6, mtime=0)),
            "first_page_gzip_level6": len(gzip.compress(page, compresslevel=6, mtime=0)),
            "payload_sha256": hashlib.sha256(full).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-response", type=Path, help="Optional private captured public JSON; outputs aggregates only")
    args = parser.parse_args()
    scenarios = []
    for ready in (1000, 2100, 3000, 13932, 66316):
        row = {"server_ready_ms": ready}
        for policy in ("legacy", "responsive"):
            delivered, count = poll_delivery(ready, policy)
            row[policy] = {"response_ms": delivered, "detection_delay_ms": delivered - ready, "requests": count}
        scenarios.append(row)
    output = {"evidence_kind": "deterministic simulation, zero RTT/jitter; excludes POST and render",
              "poll_scenarios": scenarios,
              "equal_weight_readiness_phase_sweep": {p: polling_phase_sweep(p) for p in ("legacy", "responsive")},
              "depletion_30_cards_first_at_3s_next_at_66s": {
                  str(rate): depletion_wait(3000, 66000, 30, rate) for rate in (.5, 1, 2)}}
    if args.public_response:
        with args.public_response.open("rb") as source:
            raw = source.read()
        output["supplied_public_response_bytes"] = {
            "source_file_bytes": len(raw),
            "source_file_gzip_level6": len(gzip.compress(raw, compresslevel=6, mtime=0)),
            "source_file_sha256": hashlib.sha256(raw).hexdigest(),
            "comparison_encoding": "compact sorted JSON, ensure_ascii=False",
            **response_bytes(json.loads(raw)),
        }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
