"""Split the backend pytest suite across CI runners by test file.

Pytest plugin, loaded in CI with:

    FTF_TEST_SHARD=3/8 PYTHONPATH=.github/scripts python -m pytest backend/tests -q -p ci_shard

Pytest collects everything as usual; this plugin then keeps only the items whose test
file is assigned to shard i and deselects the rest. Assignment is a pure function
file -> exactly one shard, applied to pytest's own collection, so every collected
test runs in exactly one shard. Durations (.github/backend-test-durations.json) only
balance the shards: a stale or missing entry can unbalance them, never drop or
duplicate a test. With FTF_TEST_SHARD unset or empty the plugin does nothing.

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


def assign_shards(files, durations, n, default=DEFAULT_WEIGHT):
    """Map each file to a shard in 1..n by greedy longest-processing-time packing.

    Files are taken heaviest first (ties by path) and each goes into the currently
    lightest shard (ties by lowest index). Deterministic for given inputs.
    """
    weights = {f: durations.get(f, default) for f in set(files)}
    loads = [0.0] * n
    assignment = {}
    for f in sorted(weights, key=lambda f: (-weights[f], f)):
        k = min(range(n), key=lambda k: (loads[k], k))
        assignment[f] = k + 1
        loads[k] += weights[f]
    return assignment


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
    assignment = assign_shards(files, load_durations(config.rootpath), n)
    keep = [it for it, f in zip(items, files) if assignment[f] == i]
    drop = [it for it, f in zip(items, files) if assignment[f] != i]
    total, total_files = len(items), len(assignment)
    kept_files = sum(1 for s in assignment.values() if s == i)
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
