"""Deterministic protocol tests, not production engine or phone performance."""
import json
import sqlite3
import unittest

from scripts.research_trade_delivery import (
    CheckedCard, DeliveryInventory, depletion_wait, poll_delivery, polling_phase_sweep, response_bytes,
)


def cards(count):
    return [CheckedCard.from_public({"trade_id": f"trade-{i}", "opponent_user_id": f"partner-{i % 11}",
        "give_player_ids": [f"give-{i}"], "receive_player_ids": [f"receive-{i}"],
        "match_score": count - i, "rationale": "Synthetic public card"}, f"proof-{i}") for i in range(count)]


class DeliveryProtocolTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)

    def inventory(self, count=75, **kwargs):
        return DeliveryInventory(self.db, "inventory-v1", "account-league-format", cards(count),
                                 ranking_complete=kwargs.pop("ranking_complete", True), **kwargs)

    def test_complete_inventory_survives_pages_and_duplicate_responses(self):
        inv = self.inventory(1974)
        expected = [c.public["trade_id"] for c in inv.cards]
        cursor, received, seen = None, [], set()
        for size in [1, 29] + [30] * 65:
            inv.publish_next(size)
            while True:
                page = inv.page(inv.scope, cursor=cursor)
                # A retried request has exactly the same identities and order.
                self.assertEqual(page, inv.page(inv.scope, cursor=cursor))
                for card in page["cards"]:
                    self.assertNotIn(card["trade_id"], seen)
                    seen.add(card["trade_id"])
                    received.append(card["trade_id"])
                cursor = page["next_cursor"]
                if not page["has_more_ready"]:
                    break
        self.assertEqual(received, expected)
        self.assertTrue(page["done"])
        self.assertEqual(inv.ready_count, 1974)

    def test_running_batch_is_actionable_but_uncommitted_cards_are_not(self):
        inv = self.inventory()
        self.assertEqual(inv.page(inv.scope)["cards"], [])
        inv.publish_next(1)
        page = inv.page(inv.scope)
        self.assertEqual(page["status"], "running")
        self.assertFalse(page["done"])
        card = page["cards"][0]
        self.assertTrue(inv.action(inv.scope, card["impression_id"], card))
        self.assertFalse(inv.action(inv.scope, "unknown", card))
        self.assertFalse(inv.action(inv.scope, card["impression_id"], {**card, "give_player_ids": ["changed"]}))
        self.assertFalse(inv.action(inv.scope, card["impression_id"], card, eligible=lambda _: False))

    def test_failed_batch_atomicity_preserves_previous_cards_and_retry_identity(self):
        inv = self.inventory()
        inv.publish_next(30)
        before = inv.legacy_snapshot(inv.scope)["cards"]
        with self.assertRaisesRegex(RuntimeError, "evidence_write"):
            inv.publish_next(30, fail_after=12)
        self.assertEqual(inv.ready_count, 30)
        self.assertEqual(inv.status, "error")
        self.assertEqual(inv.legacy_snapshot(inv.scope)["cards"], before)
        inv.publish_next(30)
        self.assertEqual(inv.status, "running")
        self.assertEqual(inv.legacy_snapshot(inv.scope)["cards"][:30], before)
        inv.publish_next(30)
        self.assertEqual(inv.status, "complete")

    def test_recovery_after_commit_keeps_same_action_identity_and_continues(self):
        inv = self.inventory()
        with self.assertRaisesRegex(RuntimeError, "crash_after_commit"):
            inv.publish_next(30, crash_after_commit=True)
        committed = inv.page(inv.scope)
        recovered = self.inventory()
        self.assertEqual(recovered.page(inv.scope), committed)
        recovered.publish_next(30)
        self.assertEqual(recovered.ready_count, 60)
        self.assertEqual(recovered.page(inv.scope)["cards"], committed["cards"])

    def test_legacy_client_never_gets_a_silent_30_card_cap(self):
        inv = self.inventory()
        inv.publish_next(30)
        self.assertEqual(inv.legacy_snapshot(inv.scope)["status"], "running")
        inv.publish_next(60)
        legacy = inv.legacy_snapshot(inv.scope)
        self.assertEqual(len(legacy["cards"]), 75)
        self.assertEqual(legacy["status"], "complete")
        self.assertEqual(len(inv.page(inv.scope)["cards"]), 30)
        self.assertFalse(inv.page(inv.scope)["done"])

    def test_no_silent_order_or_terms_change_in_existing_inventory(self):
        inv = self.inventory()
        inv.publish_next()
        for changed in (list(reversed(inv.cards)), cards(76)):
            with self.assertRaisesRegex(ValueError, "different_terms_or_order"):
                DeliveryInventory(self.db, inv.inventory_id, inv.scope, changed, ranking_complete=True)
        with self.assertRaisesRegex(ValueError, "global_order_not_final"):
            self.inventory(ranking_complete=False)

    def test_missing_proof_and_failed_checks_never_publish(self):
        for index, bad in enumerate((CheckedCard.from_public(cards(1)[0].public, ""),
                                     CheckedCard.from_public(cards(1)[0].public, "proof", False))):
            inv = DeliveryInventory(self.db, f"bad-{index}", "scope", [bad], ranking_complete=True)
            with self.assertRaisesRegex(ValueError, "checks_or_evidence"):
                inv.publish_next()
            self.assertEqual(inv.ready_count, 0)

    def test_empty_short_and_exact_page_multiple_finish_honestly(self):
        for count in (0, 1, 19, 30, 60):
            inv = DeliveryInventory(self.db, f"size-{count}", "scope", cards(count), ranking_complete=True)
            inv.publish_next(60)
            page = inv.page(inv.scope)
            if count > 30:
                self.assertFalse(page["done"])
                page = inv.page(inv.scope, cursor=page["next_cursor"])
            self.assertTrue(page["done"])

    def test_disposition_filter_advances_scanned_cursor_without_dropping_others(self):
        inv = self.inventory(60)
        inv.publish_next(60)
        keep = lambda c: int(c["trade_id"].split("-")[1]) % 4 != 0
        first = inv.page(inv.scope, eligible=keep)
        second = inv.page(inv.scope, cursor=first["next_cursor"], eligible=keep)
        actual = [c["trade_id"] for c in first["cards"] + second["cards"]]
        self.assertEqual(actual, [f"trade-{i}" for i in range(60) if i % 4])
        self.assertEqual(actual, [c["trade_id"] for c in inv.legacy_snapshot(inv.scope, eligible=keep)["cards"]])
        self.assertTrue(second["done"])

    def test_failed_serve_time_checks_do_not_fall_back_to_unchecked_cards(self):
        inv = self.inventory()
        inv.publish_next()
        def unavailable(_):
            raise RuntimeError("eligibility_database_unavailable")
        for read in (inv.page, inv.legacy_snapshot):
            with self.assertRaisesRegex(RuntimeError, "database_unavailable"):
                read(inv.scope, eligible=unavailable)

    def test_cursor_and_account_scope_reject_cross_inventory_requests(self):
        inv = self.inventory()
        inv.publish_next()
        for cursor in ("other:0", "inventory-v1:31", "inventory-v1:-1"):
            with self.assertRaises(ValueError):
                inv.page(inv.scope, cursor=cursor)
        with self.assertRaises(PermissionError):
            inv.page("other-account")
        with self.assertRaises(PermissionError):
            inv.legacy_snapshot("other-account")

    def test_returned_payload_mutation_cannot_change_durable_identity(self):
        inv = self.inventory()
        inv.publish_next()
        first = inv.page(inv.scope)["cards"][0]
        first["give_player_ids"].append("evil")
        self.assertNotEqual(inv.page(inv.scope)["cards"][0], first)


class TransportModelTest(unittest.TestCase):
    def test_current_quiet_owner_schedule_and_responsive_first_window(self):
        self.assertEqual(poll_delivery(2100, "legacy"), (3800, 3))
        self.assertEqual(poll_delivery(2100, "responsive"), (2250, 9))
        self.assertEqual(poll_delivery(3000, "legacy"), (3800, 3))
        self.assertEqual(poll_delivery(3000, "responsive"), (3000, 12))

    def test_response_time_and_jitter_are_not_claimed_as_free(self):
        with_rtt, _ = poll_delivery(2100, "responsive", response_ms=200)
        self.assertGreater(with_rtt, 2100)
        late, _ = poll_delivery(66316, "legacy", jitter=.1)
        self.assertGreaterEqual(late, 66316)
        self.assertLess(late - 66316, 4400)

    def test_batch_is_not_enough_to_hide_arbitrarily_long_tail(self):
        self.assertEqual(depletion_wait(3000, 66000, 30, .5), 3000)
        self.assertEqual(depletion_wait(3000, 66000, 30, 1), 33000)
        self.assertEqual(depletion_wait(3000, 66000, 30, 2), 48000)
        self.assertEqual(depletion_wait(3000, 10000, 30, 2), 0)

    def test_uniform_phase_simulation_keeps_sampling_distinct_from_real_p95(self):
        legacy, responsive = polling_phase_sweep("legacy"), polling_phase_sweep("responsive")
        self.assertEqual(legacy["grid_points"], 6001)
        self.assertEqual(legacy["max_delay_ms"], 3990)
        self.assertEqual(responsive["max_delay_ms"], 990)

    def test_bytes_are_exact_serialized_aggregates_without_fixture_contents(self):
        payload = {"cards": [c.public for c in cards(1974)], "status": "complete"}
        report = response_bytes(payload)
        self.assertEqual(report["cards"], 1974)
        self.assertEqual(report["first_page_cards"], 30)
        self.assertGreater(report["full_json_utf8"], report["first_page_json_utf8"])
        self.assertNotIn("trade-1", json.dumps(report))
        self.assertEqual(report, response_bytes(payload))


if __name__ == "__main__":
    unittest.main()
