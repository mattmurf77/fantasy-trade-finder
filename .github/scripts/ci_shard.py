"""Split the backend pytest suite across CI runners by test file.

Pytest plugin, loaded in CI with:

    FTF_TEST_SHARD=3/8 PYTHONPATH=.github/scripts python -m pytest backend/tests -q -p ci_shard

Pytest collects everything as usual; this plugin then keeps only the items assigned to
shard i and deselects the rest. Assignment is a pure function node id -> exactly one
shard (by file, or by chunk for the files in SPLIT_FILES), applied to pytest's own
collection, so every collected test runs in exactly one shard. Durations
(.github/backend-test-durations.json) only balance the shards: a stale or missing
entry can unbalance them, never drop or duplicate a test. With FTF_TEST_SHARD unset or empty the plugin does nothing.

Regenerate the durations file from a junit XML of a full serial run:

    python -m pytest backend/tests -q --junitxml=serial.xml
    python .github/scripts/ci_shard.py --from-junit serial.xml
"""
import json
import os
import re
import sys
from pathlib import Path

import pytest

ENV_VAR = "FTF_TEST_SHARD"
DURATIONS_RELPATH = ".github/backend-test-durations.json"
DEFAULT_WEIGHT = 1.0  # seconds, for test files not in the durations file

# Files split into k chunks instead of running as one unit. Explicit and opt-in: a
# file goes here only after someone has checked its tests pass in separate processes.
# test_rules_first_deck.py alone is heavier than an even shard's share; its
# module-level caches (_CACHE, _SEASON_WORLDS) fill lazily, so each chunk just
# rebuilds what it needs. A listed file that is not collected is ignored.
SPLIT_FILES = {"backend/tests/test_rules_first_deck.py": 2}


def parse_shard(value):
    """'i/N' -> (i, N), 1-based. Empty/None -> None. Anything else raises ValueError."""
    if value is None or not value.strip():
        return None
    m = re.fullmatch(r"(\d+)/(\d+)", value.strip())
    if not m:
        raise ValueError(f"{ENV_VAR}={value!r}: expected 'i/N', e.g. '3/8'")
    i, n = int(m.group(1)), int(m.group(2))
    if not 1 <= i <= n:
        raise ValueError(f"{ENV_VAR}={value!r}: need 1 <= i <= N")
    return i, n


def pack(weights, n):
    """Map each unit in `weights` to a shard in 1..n by greedy longest-processing-time
    packing: heaviest first (ties by key), each into the currently lightest shard
    (ties by lowest index). Deterministic for given inputs.
    """
    loads = [0.0] * n
    assignment = {}
    for u in sorted(weights, key=lambda u: (-weights[u], u)):
        k = min(range(n), key=lambda k: (loads[k], k))
        assignment[u] = k + 1
        loads[k] += weights[u]
    return assignment


def assign_tests(tests, durations, n, split_files=SPLIT_FILES, default=DEFAULT_WEIGHT):
    """Map each node id to a shard in 1..n. `tests` is an iterable of (nodeid, file).

    Each file is one packing unit, except a file in `split_files` with k chunks: its
    node ids, in sorted order, go round-robin into k units 'file#j/k', each weighing
    file weight / k. Sorting makes the chunks depend only on the set of node ids.
    """
    by_file = {}
    for nodeid, f in tests:
        by_file.setdefault(f, set()).add(nodeid)
    unit_of, weights = {}, {}
    for f, nodeids in by_file.items():
        k = split_files.get(f, 1)
        w = durations.get(f, default)
        for idx, nodeid in enumerate(sorted(nodeids)):
            unit = f if k == 1 else f"{f}#{idx % k + 1}/{k}"
            unit_of[nodeid] = unit
            weights[unit] = w / k
    shard_of_unit = pack(weights, n)
    return {nodeid: shard_of_unit[u] for nodeid, u in unit_of.items()}


def load_durations(root):
    path = Path(root) / DURATIONS_RELPATH
    if not path.exists():
        return {}
    return json.loads(path.read_text())


# ── pytest hooks ────────────────────────────────────────────────────────────

def pytest_configure(config):
    try:
        config._ci_shard = parse_shard(os.environ.get(ENV_VAR))
    except ValueError as e:
        raise pytest.UsageError(str(e))


def _item_file(item, root):
    return Path(item.path).resolve().relative_to(Path(root).resolve()).as_posix()


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(session, config, items):
    shard = getattr(config, "_ci_shard", None)
    if shard is None:
        return
    i, n = shard
    files = [_item_file(it, config.rootpath) for it in items]
    shard_of = assign_tests(zip((it.nodeid for it in items), files),
                            load_durations(config.rootpath), n)
    keep = [it for it in items if shard_of[it.nodeid] == i]
    drop = [it for it in items if shard_of[it.nodeid] != i]
    total, total_files = len(items), len(set(files))
    kept_files = len({f for it, f in zip(items, files) if shard_of[it.nodeid] == i})
    if drop:
        config.hook.pytest_deselected(items=drop)
    items[:] = keep
    line = (f"ci_shard: shard {i}/{n} runs {len(keep)} of {total} collected tests "
            f"({kept_files} of {total_files} files)")
    tr = config.pluginmanager.get_plugin("terminalreporter")
    if tr is not None:
        tr.ensure_newline()
        tr.write_line(line)
    else:
        print(line)



# ── durations regeneration ──────────────────────────────────────────────────

def _classname_to_file(classname, root):
    """'backend.tests.test_foo[.Class...]' -> 'backend/tests/test_foo.py' (longest
    dotted prefix that is an existing .py file under root), else None."""
    parts = classname.split(".")
    for end in range(len(parts), 0, -1):
        rel = "/".join(parts[:end]) + ".py"
        if (root / rel).is_file():
            return rel
    return None


def durations_from_junit(xml_path, root):
    import xml.etree.ElementTree as ET

    totals, unmapped = {}, set()
    for tc in ET.parse(xml_path).getroot().iter("testcase"):
        f = _classname_to_file(tc.get("classname", ""), root)
        if f is None:
            unmapped.add(tc.get("classname", ""))
            continue
        totals[f] = totals.get(f, 0.0) + float(tc.get("time") or 0)
    for c in sorted(unmapped):
        print(f"warning: no test file for classname {c!r}", file=sys.stderr)
    return {f: round(t, 2) for f, t in sorted(totals.items())}


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--from-junit":
        sys.exit("usage: python .github/scripts/ci_shard.py --from-junit path.xml")
    repo_root = Path(__file__).resolve().parents[2]
    data = durations_from_junit(sys.argv[2], repo_root)
    out = repo_root / DURATIONS_RELPATH
    out.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    print(f"wrote {out} ({len(data)} files, {sum(data.values()):.0f}s total)")
