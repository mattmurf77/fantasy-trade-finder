"""Draft replay harness (rookie-draft M1 — plan §M1, lld §4.1).

Turns the committed cassettes under ``backend/tests/fixtures/draft/`` into a
live-looking draft that a test can step through pick by pick, with zero
network and zero wall-clock waiting.

Two mechanisms, because the two platforms have two different seams:

* **Sleeper** rides the shipped ``FTF_SLEEPER_FIXTURES_DIR`` seam
  (``server._sleeper_fixture_path``). :class:`DraftReplay` copies a corpus into
  a temp dir and mutates *that* copy, so the committed cassettes stay pristine
  and record mode's "refuses a non-empty dir" rule (server.py, [RV-6]) is never
  in play — which is also why the corpora are recorded **one per directory**.
* **MFL** has no env seam; ``mfl_service`` injects ``_opener``
  (mfl_service.py ``_fetch_one``). :func:`mfl_opener` builds a stub opener over
  a committed ``draftResults.json`` snapshot, matching the convention the
  repo's existing MFL tests already use.

Deviation from the LLD, recorded here because the LLD assumed otherwise:
``truncate_picks`` was specced as setting the detail object's ``last_picked``
to "pick k's timestamp". **Sleeper pick objects carry no timestamp** — verified
against the live Lakeview recording, whose pick keys are ``draft_id,
draft_slot, is_keeper, metadata, pick_no, picked_by, player_id, reactions,
roster_id, round``. ``last_picked`` exists only on the draft detail object. The
replayer therefore *synthesises* a strictly-increasing ladder anchored so that
``pick_timestamp(total)`` is byte-identical to the recorded live value — a
truncation to the full length reproduces the real cassette exactly.
"""

from __future__ import annotations

import json
import pathlib
import shutil

# Corpus root — the committed cassettes.
FIXTURES_ROOT = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "draft"

# Sleeper's draft `status` → the board-payload `state` vocabulary of lld §2.1.
# M3 must agree with this table; it lives here so there is exactly one copy.
SLEEPER_STATUS_TO_STATE = {
    "pre_draft": "upcoming",
    "drafting": "live",
    "paused": "live",
    "complete": "complete",
}

# Spacing of the synthesised pick ladder. Arbitrary but fixed: determinism is
# the only property that matters.
PICK_INTERVAL_MS = 60_000


class FakeClock:
    """Monotonic clock stand-in for TTL tests — no ``time.sleep`` anywhere.

    M3 introduces ``draft_board_service._now_monotonic`` as a module-level
    indirection precisely so a test can point it at one of these
    (``monkeypatch.setattr(draft_board_service, "_now_monotonic", clock)``)
    instead of patching the stdlib.
    """

    def __init__(self, start: float = 1_000.0):
        self._t = float(start)

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> float:
        self._t += float(seconds)
        return self._t

    @property
    def now(self) -> float:
        return self._t


class DraftReplay:
    """A mutable copy of one Sleeper draft corpus.

    ``corpus_dir`` is a directory under :data:`FIXTURES_ROOT` (or an absolute
    path); ``tmp_dir`` is where the working copy lands — point it at pytest's
    ``tmp_path``. The corpus is copied on construction, so every mutation is
    scoped to the test.
    """

    def __init__(self, corpus_dir: str | pathlib.Path, tmp_dir: str | pathlib.Path):
        src = pathlib.Path(corpus_dir)
        if not src.is_absolute():
            src = FIXTURES_ROOT / src
        if not src.is_dir():
            raise FileNotFoundError(f"no such draft corpus: {src}")

        self.corpus_dir = src
        self.tmp_dir = pathlib.Path(tmp_dir) / src.name
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)
        shutil.copytree(src, self.tmp_dir)

        self.manifest = self._read_json_or(self.tmp_dir / "manifest.json", {})
        self.league_id = self.manifest.get("league_id")
        self.draft_id = self.manifest.get("draft_id")

        if self.draft_id:
            self._detail_path = self.tmp_dir / "draft" / f"{self.draft_id}.json"
            self._picks_path = self.tmp_dir / "draft" / self.draft_id / "picks.json"
            # The pristine pick list — truncation always slices from this, so
            # advance() can go forwards and backwards freely.
            self._all_picks = self._read_json_or(
                src / "draft" / self.draft_id / "picks.json", [])
            self._recorded_last_picked = self._read_json_or(
                src / "draft" / f"{self.draft_id}.json", {}).get("last_picked")
        else:
            self._detail_path = self._picks_path = None
            self._all_picks = []
            self._recorded_last_picked = None

        self._k = len(self._all_picks)

    # ── env / wiring ─────────────────────────────────────────────────────

    @property
    def env(self) -> dict[str, str]:
        """Env for a subprocess, or for ``monkeypatch.setenv`` before import."""
        return {"FTF_SLEEPER_FIXTURES_DIR": str(self.tmp_dir)}

    def install(self, monkeypatch, server_module, test_mode: bool = True) -> None:
        """Point an ALREADY-IMPORTED ``backend.server`` at this corpus.

        ``server.py`` reads ``FTF_SLEEPER_FIXTURES_DIR`` once at import into
        module constants, so setting the env var after import does nothing —
        the constants are what has to move.

        ``test_mode=True`` arms ``test_support.counters`` so a live call would
        be *counted* rather than silently succeed; it does not change the
        fixture seam itself.
        """
        monkeypatch.setattr(server_module, "_SLEEPER_FIXTURES_DIR", str(self.tmp_dir))
        monkeypatch.setattr(server_module, "_SLEEPER_RECORD", False)
        monkeypatch.setattr(server_module, "_TEST_MODE", test_mode)

    # ── state ────────────────────────────────────────────────────────────

    @property
    def total_picks(self) -> int:
        return len(self._all_picks)

    @property
    def picks_made(self) -> int:
        return self._k

    @property
    def status(self) -> str:
        return self.detail.get("status")

    @property
    def state_label(self) -> str:
        """The board `state` this corpus currently represents (lld §2.1)."""
        return SLEEPER_STATUS_TO_STATE.get(self.status, "unavailable")

    @property
    def detail(self) -> dict:
        return self._read_json_or(self._detail_path, {}) if self._detail_path else {}

    @property
    def picks(self) -> list:
        return self._read_json_or(self._picks_path, []) if self._picks_path else []

    @property
    def drafts(self) -> list:
        return self._read_json_or(
            self.tmp_dir / "league" / str(self.league_id) / "drafts.json", [])

    def pick_timestamp(self, k: int) -> int | None:
        """Epoch-ms of the k-th pick (1-based). ``None`` for k <= 0.

        Anchored so ``pick_timestamp(total_picks)`` equals the value the live
        recording carries, making a full-length replay byte-faithful.
        """
        if k <= 0:
            return None
        anchor = self._recorded_last_picked
        if anchor is None:
            # Pre-draft corpus: no live anchor to honour, so pick a fixed base.
            anchor = 1_777_000_000_000 + self.total_picks * PICK_INTERVAL_MS
        return int(anchor) - (self.total_picks - k) * PICK_INTERVAL_MS

    # ── mutation ─────────────────────────────────────────────────────────

    def truncate_picks(self, k: int) -> None:
        """Rewrite ``picks.json`` to the first k picks.

        Also moves the detail object's ``last_picked`` to pick k's synthesised
        timestamp (``None`` at k == 0) and its ``status`` to the state k
        implies, so the poll-detail-then-fetch-picks rule (M3) sees a genuine
        in-progress draft rather than a complete one with fewer rows.
        """
        if self._picks_path is None:
            raise ValueError(f"corpus {self.corpus_dir.name} has no draft to truncate")
        if not 0 <= k <= self.total_picks:
            raise ValueError(f"k must be in [0, {self.total_picks}], got {k}")

        self._k = k
        self._write_json(self._picks_path, self._all_picks[:k])

        if k == 0:
            status = "pre_draft"
        elif k < self.total_picks:
            status = "drafting"
        else:
            status = "complete"
        self._patch_detail(last_picked=self.pick_timestamp(k), status=status)

    def advance(self, n: int = 1) -> None:
        self.truncate_picks(self._k + n)

    def set_status(self, status: str) -> None:
        """Force the draft status, leaving the pick list where it is.

        For the cases where status and pick count legitimately disagree — a
        complete draft with zero picks, a paused live draft.
        """
        if status not in SLEEPER_STATUS_TO_STATE:
            raise ValueError(f"unknown Sleeper draft status: {status!r}")
        self._patch_detail(status=status)

    # ── internals ────────────────────────────────────────────────────────

    def _patch_detail(self, **fields) -> None:
        """Apply ``fields`` to BOTH copies of the draft object.

        Sleeper serves the same draft twice — inside ``/league/<id>/drafts``
        and as ``/draft/<id>`` — and M3 reads the second while M0/#207 read the
        first. Letting them drift would be a fixture that lies.
        """
        detail = self._read_json_or(self._detail_path, {})
        detail.update(fields)
        self._write_json(self._detail_path, detail)

        drafts_path = self.tmp_dir / "league" / str(self.league_id) / "drafts.json"
        drafts = self._read_json_or(drafts_path, None)
        if isinstance(drafts, list):
            for d in drafts:
                if str(d.get("draft_id")) == str(self.draft_id):
                    d.update(fields)
            self._write_json(drafts_path, drafts)

    @staticmethod
    def _read_json_or(path, default):
        if path is None or not pathlib.Path(path).exists():
            return default
        return json.loads(pathlib.Path(path).read_text())

    @staticmethod
    def _write_json(path, obj) -> None:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, indent=1))


# ── MFL ──────────────────────────────────────────────────────────────────

def mfl_corpus(name: str) -> dict:
    """The committed ``draftResults`` snapshot for an ``mfl-*`` corpus."""
    return json.loads((FIXTURES_ROOT / name / "draftResults.json").read_text())


def mfl_manifest(name: str) -> dict:
    return json.loads((FIXTURES_ROOT / name / "manifest.json").read_text())


class _StubResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def mfl_opener(name: str, *, calls: list | None = None):
    """An ``_opener`` for ``mfl_service`` backed by an ``mfl-*`` corpus.

    Serves the corpus for ``TYPE=draftResults`` and raises for anything else,
    so a test that quietly starts needing a second export fails loudly instead
    of falling through to the network.
    """
    payload = json.dumps(mfl_corpus(name)).encode("utf-8")

    def _opener(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if calls is not None:
            calls.append(url)
        if "TYPE=draftResults" not in url:
            raise AssertionError(
                f"mfl_opener({name!r}) only serves draftResults; got {url}")
        return _StubResponse(payload)

    return _opener


def mfl_unit_counts(raw: dict) -> tuple[int, int, int]:
    """``(units, picks_made, picks_total)`` over a ``draftResults`` payload.

    Handles MFL's dict-or-list ``draftUnit`` and ``draftPick`` shapes — the
    same normalisation ``draft_status.mfl_verdict`` does.
    """
    du = (raw.get("draftResults") or {}).get("draftUnit")
    if du is None:
        return 0, 0, 0
    units = du if isinstance(du, list) else [du]
    made = total = 0
    for unit in units:
        picks = unit.get("draftPick", [])
        picks = picks if isinstance(picks, list) else [picks]
        total += len(picks)
        made += sum(1 for p in picks if str(p.get("player", "")).strip())
    return len(units), made, total
