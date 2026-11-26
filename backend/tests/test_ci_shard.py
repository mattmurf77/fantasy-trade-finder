"""Guards for the CI test-sharding plugin (.github/scripts/ci_shard.py)."""
import importlib.util
import json
import random
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("ci_shard_under_test", ROOT / ".github/scripts/ci_shard.py")
ci_shard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci_shard)

DURATIONS = {"a.py": 50.0, "b.py": 30.0, "c.py": 30.0, "d.py": 5.0, "e.py": 0.1}
FILES = list(DURATIONS) + ["new_1.py", "new_2.py", "new_3.py"]  # last three not in durations
TESTS = [(f"{f}::test_{j}", f) for f in FILES for j in range(5)]
SPLIT = {"a.py": 2, "b.py": 3, "not_collected.py": 2}


@pytest.mark.parametrize("n", [1, 2, 3, 8, 20])
def test_assignment_is_a_partition_of_node_ids(n):
    assignment = ci_shard.assign_tests(TESTS, DURATIONS, n, split_files=SPLIT)
    assert set(assignment) == {nodeid for nodeid, _ in TESTS}
    assert all(1 <= s <= n for s in assignment.values())
    if n == 1:
        assert set(assignment.values()) == {1}


def test_assignment_is_deterministic_and_order_independent():
    expected = ci_shard.assign_tests(TESTS, DURATIONS, 8, split_files=SPLIT)
    shuffled = TESTS[:]
    random.Random(0).shuffle(shuffled)
    assert ci_shard.assign_tests(shuffled, DURATIONS, 8, split_files=SPLIT) == expected
    # An unsplit file stays whole; a split file's chunks spread out (sorted round-robin).
    assert len({expected[f"c.py::test_{j}"] for j in range(5)}) == 1
    assert expected["a.py::test_0"] == expected["a.py::test_2"] != expected["a.py::test_1"]
    assert len({expected[f"b.py::test_{j}"] for j in range(5)}) == 3


def test_committed_split_file_halves_land_on_different_shards():
    durations = json.loads((ROOT / ci_shard.DURATIONS_RELPATH).read_text())
    tests = [(f"{f}::t", f) for f in durations]
    tests += [(f"{f}::t{j}", f) for f in ci_shard.SPLIT_FILES for j in range(4)]
    assignment = ci_shard.assign_tests(tests, durations, 8)
    for f, k in ci_shard.SPLIT_FILES.items():
        assert len({s for nodeid, s in assignment.items() if nodeid.startswith(f + "::")}) == k


@pytest.mark.parametrize("value, expected", [
    (None, None), ("", None), ("  ", None), ("1/1", (1, 1)), ("3/8", (3, 8)), ("8/8", (8, 8)),
])
def test_parse_shard_accepts(value, expected):
    assert ci_shard.parse_shard(value) == expected


@pytest.mark.parametrize("value", ["0/8", "9/8", "x", "3", "1/0", "-1/8", "3/8/2", "a/b"])
def test_parse_shard_rejects(value):
    with pytest.raises(ValueError):
        ci_shard.parse_shard(value)


def test_ci_matrix_matches_shard_count():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    n = int(re.search(r"FTF_TEST_SHARD: \$\{\{ matrix\.shard \}\}/(\d+)", ci).group(1))
    shards = re.search(r"^\s*shard: \[([\d, ]+)\]", ci, re.M).group(1)
    assert [int(s) for s in shards.split(",")] == list(range(1, n + 1))
    assert f"name: backend-suite (${{{{ matrix.shard }}}}/{n})" in ci
