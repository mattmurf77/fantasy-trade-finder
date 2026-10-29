"""backend.eval.redaction: the deletion scrub's hook for the value-model
store (models-lead E-b3, legal R28.22). In every record's partner_rates, a
key whose viewer is a deleted user is deleted and a key whose partner is one
takes that user's token; rates and other keys are kept, and so are
unparseable lines that can't hold a deleted id. The rewrite is atomic and
idempotent, keeps the store's mode, and the serve-time cache reloads it."""

import json
import os
import stat

import pytest

from backend import value_model as vm
from backend.eval import redaction
from backend.eval.contract import REDACTED_PARTNER_PREFIX

TOKEN = f"{REDACTED_PARTNER_PREFIX}9f0c"


def _model(rates):
    return vm.ValueModel(
        like_head=vm.LogisticHead(weights={"bias": -0.4}), propose_head=None,
        propose_constant=0.2, partner_rates=rates, global_like_rate=0.3, position_mean=0.4,
        trained_at="t", train_date="2026-10-27")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("VALUE_MODEL_DIR", str(tmp_path))
    vm.append_model(_model({"gone|p1": 0.7, "u1|gone": 0.4, "u1|p2": 0.5}))
    with open(vm.models_path(), "a", encoding="utf-8") as fh:
        fh.write("{torn\n")
    vm.append_model(_model({"u2|gone": 0.6, "u2|p3": 0.2}))
    return vm.models_path()


def _rates(path):
    out = []
    for line in open(path, encoding="utf-8").read().splitlines():
        try:
            out.append(json.loads(line)["model"]["partner_rates"])
        except json.JSONDecodeError:
            out.append(line)
    return out


def test_the_deleted_user_s_own_keys_go_and_their_partner_keys_take_the_token(store):
    """R28.22 (f, c3 #14): "gone|p1" is the deleted user's own rate, deleted;
    "u1|gone" and "u2|gone" are other viewers' rates with them, re-keyed."""
    assert redaction.redact_model_store({"gone": TOKEN}) == 3
    assert _rates(store) == [
        {f"u1|{TOKEN}": 0.4, "u1|p2": 0.5},
        "{torn",
        {f"u2|{TOKEN}": 0.6, "u2|p3": 0.2},
    ]
    assert "gone" not in open(store, encoding="utf-8").read()


def test_a_pair_already_under_the_token_keeps_its_rate():
    """#529 QA P3: re-keying "u1|gone" onto an existing "u1|<token>" keeps
    the token's rate, whichever order the keys come in."""
    for rates in ({"u1|gone": 0.4, f"u1|{TOKEN}": 0.9}, {f"u1|{TOKEN}": 0.9, "u1|gone": 0.4}):
        assert redaction.redact_partner_rates(rates, {"gone": TOKEN}) == ({f"u1|{TOKEN}": 0.9}, 1)


def test_the_rewrite_keeps_the_store_s_mode(store):
    """#529 QA P3: mkstemp's 0600 isn't the store's mode."""
    os.chmod(store, 0o644)
    redaction.redact_model_store({"gone": TOKEN})
    assert stat.S_IMODE(os.stat(store).st_mode) == 0o644


def test_a_re_run_changes_nothing_and_no_temp_file_is_left(store):
    redaction.redact_model_store({"gone": TOKEN})
    before = open(store, encoding="utf-8").read()
    assert redaction.redact_model_store({"gone": TOKEN}) == 0
    assert open(store, encoding="utf-8").read() == before
    assert [f for f in os.listdir(os.path.dirname(store)) if f.endswith(".redact")] == []


def test_the_serve_cache_reloads_the_redacted_model(store):
    assert vm.load_latest_model().partner_rates == {"u2|gone": 0.6, "u2|p3": 0.2}
    redaction.redact_model_store({"gone": TOKEN})
    assert vm.load_latest_model().partner_rates == {f"u2|{TOKEN}": 0.6, "u2|p3": 0.2}


def test_nothing_to_do_returns_0(store, tmp_path):
    assert redaction.redact_model_store({}) == 0
    assert redaction.redact_model_store({"nobody": TOKEN}) == 0
    assert redaction.redact_model_store({"gone": TOKEN}, path=str(tmp_path / "absent")) == 0


def test_a_store_that_keeps_changing_raises_for_the_scrub_to_retry(store, monkeypatch):
    """An append between the read and the replace (the nightly fit) makes it
    read again; one that never stops raises, and the file is untouched."""
    before = open(store, encoding="utf-8").read()
    ticks = iter(range(100))
    monkeypatch.setattr(redaction, "_signature", lambda path: next(ticks))
    with pytest.raises(RuntimeError, match="kept changing"):
        redaction.redact_model_store({"gone": TOKEN})
    assert open(store, encoding="utf-8").read() == before


@pytest.mark.parametrize("torn, dropped", [
    ('{"model": {"partner_rates": {"gone|p1": 0.7, "u1|p', True),     # a whole deleted id
    ('{"model": {"partner_rates": {"u1|p2": 0.5, "u1|go', True),      # torn inside it
    ('{"model": {"partner_rates": {"u1|p2": 0.5, "u1|p3": 0.', False),  # no deleted id
], ids=["whole_id", "torn_mid_id", "no_id"])
def test_a_torn_line_that_may_hold_a_deleted_id_is_dropped(store, torn, dropped):
    """head-eng's #529 check (a): the loader skips an unparseable line, so
    dropping one costs nothing, and one holding a deleted id, whole or cut
    off mid-id, must not survive. It counts as one change; others are kept."""
    with open(store, "a", encoding="utf-8") as fh:
        fh.write(torn + "\n")
    served = vm.load_latest_model(use_cache=False).partner_rates   # partner-side keys only
    assert redaction.redact_model_store({"gone": TOKEN}) == 3 + dropped
    text = open(store, encoding="utf-8").read()
    assert (torn in text) is not dropped and "{torn" in text
    assert "gone" not in text and "|go\n" not in text
    assert vm.load_latest_model(use_cache=False).partner_rates == {
        k.replace("gone", TOKEN): v for k, v in served.items()}
    assert redaction.redact_model_store({"gone": TOKEN}) == 0


def test_a_store_whose_only_change_is_a_torn_line_is_rewritten(tmp_path):
    path = tmp_path / "models.jsonl"
    path.write_text('{"model": {"partner_rates": {"gone|\n', encoding="utf-8")
    assert redaction.redact_model_store({"gone": TOKEN}, path=str(path)) == 1
    assert path.read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------------------
# #542 QA P3s: the token map, a symlinked store, and QA's four store cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tokens", [
    {"gone": "u70"},                                   # a live id as the "token"
    {"gone": "plain-token"},                           # not a redaction token
    {"gone": TOKEN, TOKEN: f"{REDACTED_PARTNER_PREFIX}x"},   # a token that's also a key
], ids=["live_id", "no_prefix", "token_is_a_key"])
def test_a_mis_built_map_is_refused_and_the_store_untouched(store, tokens):
    before = open(store, encoding="utf-8").read()
    with pytest.raises(ValueError) as err:
        redaction.redact_model_store(tokens)
    assert "gone" not in str(err.value) and "u70" not in str(err.value)
    assert open(store, encoding="utf-8").read() == before
    with pytest.raises(ValueError):
        redaction.redact_partner_rates({"a|gone": 0.4}, tokens)


def test_a_symlinked_store_rewrites_its_target_and_keeps_the_link(store, tmp_path):
    target = tmp_path / "real" / "models.jsonl"
    target.parent.mkdir()
    os.rename(store, target)
    os.symlink(target, store)
    assert redaction.redact_model_store({"gone": TOKEN}) == 3
    assert os.path.islink(store) and "gone" not in target.read_text(encoding="utf-8")


def test_prefix_sharing_ids_are_left_alone(tmp_path, monkeypatch):
    """Deleting u7 or acct_1 never touches u70, u700 or acct_12 (whole ids only)."""
    monkeypatch.setenv("VALUE_MODEL_DIR", str(tmp_path))
    rates = {"u7|x": 0.1, "x|u7": 0.2, "u70|x": 0.3, "x|u70": 0.4, "u700|u7": 0.5,
             "acct_1|acct_12": 0.6, "acct_12|acct_1": 0.7}
    vm.append_model(_model(rates))
    tokens = {"u7": TOKEN, "acct_1": f"{REDACTED_PARTNER_PREFIX}a1"}
    assert redaction.redact_model_store(tokens) == 5
    assert _rates(vm.models_path()) == [{
        f"x|{TOKEN}": 0.2, "u70|x": 0.3, "x|u70": 0.4, f"u700|{TOKEN}": 0.5,
        f"acct_12|{REDACTED_PARTNER_PREFIX}a1": 0.7}]


@pytest.mark.parametrize("mode", [0o600, 0o640, 0o664])
def test_any_store_mode_is_kept(store, mode):
    os.chmod(store, mode)
    redaction.redact_model_store({"gone": TOKEN})
    assert stat.S_IMODE(os.stat(store).st_mode) == mode


@pytest.mark.parametrize("where", ["replace_oserror", "replace_interrupt", "fsync", "fchmod",
                                   "mkstemp"])
def test_a_failure_leaves_the_store_untouched_and_no_temp_file(store, monkeypatch, where):
    """...and no file descriptor open (QA P3-5: fchmod failing leaked one)."""
    os.chmod(store, 0o644)
    raw, st = open(store, "rb").read(), os.stat(store)
    fds = len(os.listdir("/dev/fd"))

    def boom(*_a, **_k):
        raise KeyboardInterrupt() if where == "replace_interrupt" else OSError("boom")

    if where.startswith("replace"):
        monkeypatch.setattr(redaction.os, "replace", boom)
    elif where == "fchmod":
        monkeypatch.setattr(redaction.os, "fchmod", boom)
    elif where == "mkstemp":
        monkeypatch.setattr(redaction.tempfile, "mkstemp", boom)
    else:
        monkeypatch.setattr(redaction.os, "fsync", boom)     # after the write, before replace
    with pytest.raises((OSError, KeyboardInterrupt)) as err:
        redaction.redact_model_store({"gone": TOKEN})
    assert "gone" not in str(err.value)
    assert open(store, "rb").read() == raw
    st2 = os.stat(store)
    assert (st2.st_ino, st2.st_mtime_ns, stat.S_IMODE(st2.st_mode)) == (
        st.st_ino, st.st_mtime_ns, 0o644)
    assert os.listdir(os.path.dirname(store)) == ["models.jsonl"]
    assert len(os.listdir("/dev/fd")) == fds


def test_a_concurrent_reader_only_ever_sees_a_whole_store(tmp_path, monkeypatch):
    """Atomicity: a reader beside the rewrites sees only whole states (every
    line complete, a line count some whole state had); each rewrite is a new
    inode, never an in-place write."""
    import threading
    monkeypatch.setenv("VALUE_MODEL_DIR", str(tmp_path))
    ids = [f"p{i}" for i in range(8)]
    for r in range(20):
        vm.append_model(_model({f"{a}|{b}": 0.1 for a in ids for b in ids if a != b}))
    path = vm.models_path()
    states, inode = {open(path, "rb").read().count(b"\n")}, os.stat(path).st_ino
    seen, stop = [], threading.Event()

    def reader():
        while not stop.is_set():
            raw = open(path, "rb").read()
            seen.append((raw.count(b"\n"), raw.endswith(b"\n")))

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        for i, pid in enumerate(ids):
            assert redaction.redact_model_store({pid: f"{REDACTED_PARTNER_PREFIX}{i}"}) > 0
            states.add(open(path, "rb").read().count(b"\n"))
    finally:
        stop.set()
        thread.join()
    assert seen and all(n in states and whole for n, whole in seen)
    assert os.stat(path).st_ino != inode
