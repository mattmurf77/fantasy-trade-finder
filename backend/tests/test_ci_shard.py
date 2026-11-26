"""Guards for the CI test-sharding plugin (.github/scripts/ci_shard.py)."""
import importlib.util
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


@pytest.mark.parametrize("n", [1, 2, 3, 8, 20])
def test_assignment_is_a_partition(n):
    assignment = ci_shard.assign_shards(FILES, DURATIONS, n)
    assert set(assignment) == set(FILES)
    assert all(1 <= s <= n for s in assignment.values())
    if n == 1:
        assert set(assignment.values()) == {1}


def test_assignment_is_deterministic_and_order_independent():
    expected = ci_shard.assign_shards(FILES, DURATIONS, 8)
    shuffled = FILES[:]
    random.Random(0).shuffle(shuffled)
    assert ci_shard.assign_shards(shuffled, DURATIONS, 8) == expected
    # Longest-processing-time: the three heaviest files land on separate shards.
    assert len({expected["a.py"], expected["b.py"], expected["c.py"]}) == 3


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
