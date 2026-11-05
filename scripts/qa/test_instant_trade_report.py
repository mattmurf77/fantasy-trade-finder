"""Offline acceptance-reporter regressions; synthetic input is never a release pass.

Run: python3 -m unittest discover -s scripts/qa -p 'test_instant_trade_report.py' -v
The optional PG case uses only an explicitly supplied scratch database/schema.
"""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("instant_report", Path(__file__).with_name("instant_trade_report.py"))
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


def cohort(**overrides):
    row = dict(platform="mobile", entry_point="calculator", search_type="organic",
               network_type="wifi", launch_state="first_tap", scenario="warm", devices=2,
               histogram=[dict(result="shown", ms=100, count=80)])
    row.update(overrides)
    return row


def payload(rows=None):
    return dict(schema=1, evidence_kind="measured", finalized=True, untraced_taps=0,
                cohorts=rows if rows is not None else [cohort()])


def complete(profile="all-entry"):
    rows = {}
    for _, selectors, expected in R.requirements(profile):
        row = cohort(**selectors)
        if row["scenario"].startswith("after_"):
            row.update(input_age_ms_min=80, input_age_ms_max=80)
        if expected != "latency":
            row.update(devices=0 if expected in R.GATES else 2, devices_all=2,
                       histogram=[dict(result=expected, ms=50, count=80)])
        rows[tuple(row[d] for d in R.DIMENSIONS)] = row
    return payload(list(rows.values()))


class AcceptanceReportTests(unittest.TestCase):
    def test_empty_is_failure_not_fast_zero(self):
        out = R.report(payload([]))
        self.assertEqual(out["status"], "FAIL")
        self.assertIsNone(out["totals_including_cold_offline_preferences"]["p95_ms"])
        self.assertTrue(all(c["status"] == "FAIL" for c in out["checks"]))

    def test_all_required_measured_cohorts_can_pass(self):
        self.assertEqual(R.report(complete())["status"], "PASS")

    def test_unmeasured_synthetic_cannot_claim_release_pass(self):
        p = complete()
        p["evidence_kind"] = "synthetic"
        self.assertEqual(R.report(p)["status"], "FAIL")

    def test_small_sample_fast_success_is_pass_not_robust(self):
        hist = [(100, 40)]
        self.assertEqual(R.nearest_rank(hist, .95), 100)
        self.assertIsNone(R.quantile_ci(hist)["upper_ms"])
        p = complete("ac-l1")
        for row in p["cohorts"]:
            row["histogram"][0]["count"] = 40
        self.assertEqual(R.report(p, "ac-l1")["status"], "PASS_NOT_ROBUST")

    def test_nearest_rank_with_failures_uses_entire_denominator(self):
        for result in ("empty", "error", "abandoned", "timeout", "missing_outcome"):
            row = cohort(histogram=[dict(result="shown", ms=100, count=94),
                                    dict(result=result, ms=1, count=6)])
            stats = R.summarize([row], 200)
            self.assertEqual(stats["eligible"], 100)
            self.assertEqual(stats["failed_or_missing"], 6)
            self.assertIsNone(stats["p95_ms"], result)

    def test_exact_five_percent_failure_boundary(self):
        self.assertEqual(R.nearest_rank([(100, 95), (None, 5)], .95), 100)
        self.assertIsNone(R.nearest_rank([(100, 94), (None, 6)], .95))

    def test_slow_successes_fail(self):
        p = complete()
        p["cohorts"][0]["histogram"][0]["ms"] = 201
        self.assertEqual(R.report(p)["status"], "FAIL")

    def test_one_slow_tap_cannot_hide_beneath_fast_p95_in_strict_profile(self):
        p = complete()
        p["cohorts"][0]["histogram"].append(dict(result="shown", ms=5000, count=1))
        self.assertEqual(R.summarize(p["cohorts"], 200)["p95_ms"], 100)
        out = R.report(p)
        self.assertEqual(out["status"], "FAIL")
        self.assertEqual(out["totals_including_cold_offline_preferences"]["max_shown_ms"], 5000)
        self.assertEqual(out["totals_including_cold_offline_preferences"]["eligible_above_limit_or_missing"], 1)

    def test_one_timeout_cannot_hide_beneath_fast_p95_in_strict_profile(self):
        p = complete()
        p["cohorts"][0]["histogram"].append(dict(result="timeout", ms=10000, count=1))
        self.assertEqual(R.summarize(p["cohorts"], 200)["p95_ms"], 100)
        self.assertEqual(R.report(p)["status"], "FAIL")

    def test_legacy_profile_keeps_p95_rule(self):
        p = complete("ac-l1")
        p["cohorts"][0]["histogram"].append(dict(result="shown", ms=5000, count=1))
        self.assertNotEqual(R.report(p, "ac-l1")["status"], "FAIL")

    def test_known_no_solution_is_not_a_fast_card_but_unknown_empty_is_a_miss(self):
        row = cohort(scenario="no_eligible_solution",
                     histogram=[dict(result="no_solution", ms=120, count=80)])
        stats = R.summarize([row], 200)
        self.assertEqual(stats["eligible"], 0)
        row["histogram"][0]["result"] = "empty"
        self.assertEqual(R.summarize([row], 200)["eligible_above_limit_or_missing"], 80)

    def test_missing_or_ambiguous_events_fail_even_below_p95_fraction(self):
        for result in ("missing_outcome", "duplicate_outcome", "invalid_outcome"):
            p = complete()
            p["cohorts"][0]["histogram"].append(dict(result=result, ms=None, count=1))
            out = R.report(p)
            self.assertIn("incomplete_or_ambiguous_R1_terminal_join", out["reasons"])

    def test_untraced_taps_never_disappear(self):
        p = complete()
        p["untraced_taps"] = 1
        self.assertIn("taps_without_search_id", R.report(p)["reasons"])
        stats = R.report(p)["totals_including_cold_offline_preferences"]
        self.assertEqual(stats["taps"], stats["correlated_unique_taps"] + 1)

    def test_immediate_scenario_cannot_pass_without_age_evidence(self):
        p = complete()
        for row in p["cohorts"]:
            if row["scenario"] == "after_preferences_change":
                row["input_age_ms_max"] = 5001
        self.assertEqual(R.report(p)["status"], "FAIL")
        for row in p["cohorts"]:
            row.pop("input_age_ms_min", None)
            row.pop("input_age_ms_max", None)
        self.assertEqual(R.report(p)["status"], "FAIL")

    def test_duplicate_r1_is_not_independent_sample(self):
        p = complete()
        p["cohorts"][0]["duplicate_taps"] = 1
        self.assertIn("duplicate_R1_search_ids", R.report(p)["reasons"])

    def test_cold_offline_preferences_and_scoped_are_required_in_strict_profile(self):
        for dimension, value in (("scenario", "after_preferences_change"),
                                 ("scenario", "after_league_switch"), ("scenario", "genuinely_cold"),
                                 ("scenario", "offline_cached"), ("scenario", "targeted_opponent"),
                                 ("scenario", "pinned_receive"), ("launch_state", "cold_launch")):
            p = complete()
            p["cohorts"] = [r for r in p["cohorts"] if r[dimension] != value]
            self.assertEqual(R.report(p)["status"], "FAIL", (dimension, value))

    def test_preferences_are_not_silently_excluded_by_legacy_t7(self):
        row = cohort(entry_point="prefs_changed_strip", scenario="after_preferences_change",
                     histogram=[dict(result="shown", ms=4000, count=80)])
        self.assertEqual(R.summarize([row], 200)["p95_ms"], 4000)
        self.assertEqual(R.summarize([row], 200, legacy=True)["eligible"], 0)

    def test_product_gates_are_reported_but_not_fast_cards(self):
        row = cohort(devices=0, devices_all=2, scenario="preview_exhausted",
                     histogram=[dict(result="paywall", ms=1, count=80)])
        stats = R.summarize([row], 200)
        self.assertEqual(stats["taps"], 80)
        self.assertEqual(stats["eligible"], 0)
        self.assertEqual(stats["outcomes"]["paywall"], 80)

    def test_free_preview_needs_real_cards_not_only_paywall(self):
        p = complete()
        for r in p["cohorts"]:
            if r["scenario"] == "free_preview":
                r.update(devices=0, devices_all=2, histogram=[dict(result="paywall", ms=1, count=80)])
        self.assertEqual(R.report(p)["status"], "FAIL")

    def test_offline_empty_is_separate_negative_control_not_fast_card(self):
        p = complete()
        for r in p["cohorts"]:
            if r["scenario"] == "offline_empty":
                r["histogram"] = [dict(result="shown", ms=50, count=80)]
        self.assertEqual(R.report(p)["status"], "FAIL")

    def test_two_cohorts_on_one_device_do_not_make_two_devices(self):
        p = complete("ac-l1")
        p["cohorts"][0]["devices"] = 1
        other = copy.deepcopy(p["cohorts"][0])
        other["scenario"] = "after_rank_change"
        p["cohorts"].append(other)
        out = R.report(p, "ac-l1")
        self.assertEqual(out["checks"][0]["devices_lower_bound"], 1)
        self.assertEqual(out["status"], "FAIL")

    def test_offline_negative_control_devices_do_not_supply_card_sample_devices(self):
        performance = cohort(devices=1)
        negative = cohort(scenario="offline_empty", devices=2,
                          histogram=[dict(result="offline", ms=1, count=80)])
        stats = R.summarize([performance, negative], 200)
        self.assertEqual(stats["devices_lower_bound"], 1)
        self.assertEqual(stats["devices_all_lower_bound"], 2)

    def test_new_web_source_is_required(self):
        p = complete()
        p["cohorts"] = [r for r in p["cohorts"] if r["platform"] != "web"]
        self.assertEqual(R.report(p)["status"], "FAIL")

    def test_invalid_and_identity_bearing_inputs_are_rejected(self):
        for change in (dict(user_id="must-not-export"), dict(devices=True), dict(devices=999),
                       dict(histogram=[dict(result="shown", ms=None, count=80)]),
                       dict(histogram=[dict(result="shown", ms=-1, count=80)]),
                       dict(histogram=[dict(result="shown", ms=float("nan"), count=80)])):
            with self.assertRaises(ValueError):
                R.validate(payload([cohort(**change)]))
        with self.assertRaises(ValueError):
            R.validate(payload([cohort(), cohort()]))

    def test_unfinalized_window_fails(self):
        p = complete()
        p["finalized"] = False
        self.assertIn("unfinalized_observation_window", R.report(p)["reasons"])

    def test_cli_exit_codes_and_no_database_import_for_offline_or_help(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "aggregate.json"
            path.write_text(json.dumps(complete()))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(R.main(["--input", str(path)]), 0)
                path.write_text(json.dumps(payload([])))
                self.assertEqual(R.main(["--input", str(path)]), 1)
                path.write_text("invalid")
                self.assertEqual(R.main(["--input", str(path)]), 2)
        proc = subprocess.run([sys.executable, "-S", str(Path(R.__file__)), "--help"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_production_query_left_joins_taps_and_returns_aggregates_only(self):
        self.assertIn("FROM taps t LEFT JOIN terminals", R.PRODUCTION_SQL)
        self.assertNotIn("calc_find_a_trade_tapped", R.PRODUCTION_SQL)
        self.assertIn("COUNT(DISTINCT device_id)", R.PRODUCTION_SQL)
        final_projection = R.PRODUCTION_SQL[R.PRODUCTION_SQL.index("SELECT jsonb_build_object('schema'"):]
        self.assertNotIn("user_id", final_projection)
        self.assertNotIn("device_id", final_projection)
        self.assertNotIn("'sid'", final_projection)


@unittest.skipUnless(os.environ.get("FTF_INSTANT_QA_PG_URL"), "optional disposable socket-only PG")
class AggregateSQLTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        self.text = text
        url = make_url(os.environ["FTF_INSTANT_QA_PG_URL"])
        # Never run a writable test on a remote DB, even if an env var is wrong.
        if (url.query.get("host") != "/private/tmp/fleeced-instant-qa-pg/socket"
                or str(url.query.get("port")) != "56439" or url.database != "postgres"):
            self.fail("PG regression requires the dedicated disposable local socket cluster")
        self.engine = create_engine(url)
        self.conn = self.engine.connect()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.conn.execute(text("CREATE TEMP TABLE user_events (user_id text,device_id text,event_type text,"
                               "occurred_at text,props text,source text,platform text,device_type text,app_version text)"))
        self.params = dict(start="2026-11-05T00:00:00Z", end="2026-11-05T00:05:00Z",
                           outcome_end="2026-11-05T00:10:00Z", version="1.22.0", build="172", immediate_ms=5000)

    def add(self, sid, event="find_trades_tapped", user="fake_a", **props):
        body = dict(search_id=sid)
        if event == "find_trades_tapped":
            body.update(source="calculator", client_build="172")
        else:
            body.update(search_type="organic", network_type="wifi", launch_state="first_tap", ms_from_tap=100)
        body.update(props)
        self.conn.execute(self.text("INSERT INTO user_events VALUES (:u,'fake_device',:e,:at,:p,'mobile','ios','iphone','1.22.0')"),
                          dict(u=user, e=event, at="2026-11-05T00:00:01Z" if event == "find_trades_tapped" else "2026-11-05T00:06:00Z",
                               p=json.dumps(body)))

    def query(self):
        return self.conn.execute(self.text(R.PRODUCTION_SQL), self.params).scalar_one()

    def test_build_age_late_terminal_and_tap_denominator(self):
        self.add("a", scenario="after_league_switch", input_age_ms=80)
        self.add("a", "trade_first_card_shown")
        self.add("a", user="fake_b")  # same UUID in another user MUST NOT match A's outcome
        self.add("old", client_build="171")
        self.add("old", "trade_first_card_shown", ms_from_tap=4000)
        self.add("unmatched")
        self.add(None)
        self.add("delayed", scenario="after_preferences_change", input_age_ms=5001)
        self.add("delayed", "trade_first_card_shown")
        self.add("immediate", scenario="after_preferences_change", input_age_ms=5000)
        self.add("immediate", "trade_first_card_failed", reason="timeout", ms_from_tap=10000)
        self.add("companion", "calc_find_a_trade_tapped")  # never a second R1
        p = self.query()
        R.validate(p)
        self.assertEqual(p["untraced_taps"], 1)
        stats = R.summarize(p["cohorts"], 200)
        self.assertEqual(stats["taps"], 5)
        self.assertEqual(stats["outcomes"], dict(shown=2, missing_outcome=2, timeout=1))
        immediate = next(r for r in p["cohorts"] if r["scenario"] == "after_preferences_change")
        self.assertEqual(immediate["input_age_ms_max"], 5000)
        self.assertTrue(any(r["scenario"] == "delayed_or_unknown_input_age" for r in p["cohorts"]))
        self.params["build"] = None
        self.assertEqual(R.summarize(self.query()["cohorts"], 200)["taps"], 6)

    def test_duplicate_terminal_bad_latency_and_gate_are_honest(self):
        self.add("duplicate")
        self.add("duplicate", "trade_first_card_shown")
        self.add("duplicate", "trade_first_card_failed", reason="error")
        self.add("bad")
        self.add("bad", "trade_first_card_shown", ms_from_tap="NaN")
        self.add("gate")
        self.add("gate", "trade_first_card_failed", reason="paywall")
        self.add("repeat_r1")
        self.add("repeat_r1")
        self.add("repeat_r1", "trade_first_card_shown")
        p = self.query()
        out = R.report(p)
        self.assertEqual(out["status"], "FAIL")
        self.assertIn("duplicate_R1_search_ids", out["reasons"])
        stats = out["totals_including_cold_offline_preferences"]
        self.assertEqual(stats["taps"], 4)
        self.assertEqual(stats["eligible"], 3)
        self.assertEqual(stats["outcomes"], dict(duplicate_outcome=1, invalid_outcome=1, paywall=1, shown=1))


if __name__ == "__main__":
    unittest.main()
