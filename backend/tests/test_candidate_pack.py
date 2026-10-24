"""Candidate-set packing (head-eng ruling 25): evidence_pack.pack_candidates /
unpack_candidates, and scorecard_evidence reading packed deck_candidate_sets
rows. The deck pack (PACK_VERSION 1, frozen) is untouched.

Sets: real trade jobs with suggestion.telemetry on (harness), the real writer's
set for a 1,200-card deck with 300 over-generated members, and a large
synthetic set with duplicate and unsorted asset ids, int ids, null partners and
int scores. The bar: unpacked members equal the stored JSON exactly, in order
(json.dumps byte for byte), and set_hash is identical.
"""

import json
import random
import zlib
from dataclasses import replace
from hashlib import sha256

import pytest
from sqlalchemy import Column, Integer, LargeBinary, MetaData, create_engine, insert

from backend.database import deck_candidate_sets_table, deck_impressions_table
from backend.eval import evidence_pack as ep
from backend.eval import scorecard_evidence as se
from backend.tests.support import evidence_pack_decks as D

RUN = {"candidate_set_id": "cs-1", "deck_job_id": "job-1"}


def _synthetic_members(n, seed=7):
    rng = random.Random(seed)
    assets = [f"p{i}" for i in range(400)] + [f"20{y}_{r}_pick" for y in (27, 28)
                                              for r in (1, 2, 3)] + [1234, 98765]
    partners = [f"opp{i}" for i in range(12)] + [None, 7]
    scores = (lambda i: rng.random(), lambda i: -0.0, lambda i: 1e-300, lambda i: float(i),
              lambda i: i % 5, lambda i: round(rng.random(), 3))
    return [{"trade_hash": sha256(f"m{i}".encode()).hexdigest()[:16],
             "partner": rng.choice(partners),
             "give": rng.choices(assets, k=rng.choice([1, 2, 3, 4])),
             "receive": rng.choices(assets, k=rng.choice([0, 1, 2, 3])),
             "base_score": rng.choice(scores)(i),
             "in_deck": rng.random() < 0.2} for i in range(n)]


@pytest.fixture(scope="module")
def real_sets():
    return D.harness_candidate_sets() + [D.writer_candidate_set(1200, pool=300, seed=5)]


def _round_trip(members, run=RUN):
    out_run, back = ep.unpack_candidates(ep.pack_candidates(run, members))
    assert out_run == run
    return back


# ---------------------------------------------------------------------------
# Golden
# ---------------------------------------------------------------------------

def test_real_candidate_sets_round_trip_exactly(real_sets):
    assert len(real_sets) >= 3
    writer = real_sets[-1]
    for row in real_sets:
        members = json.loads(row["candidates_json"])
        back = _round_trip(members, {"candidate_set_id": row["candidate_set_id"]})
        assert json.dumps(back) == row["candidates_json"]          # exact, in order
        assert ep.candidate_set_hash(back) == row["set_hash"]
        assert len(back) == row["size"]
    members = json.loads(writer["candidates_json"])
    assert len(members) == 1500 and sum(not m["in_deck"] for m in members) == 300


def test_a_large_synthetic_set_round_trips_exactly():
    members = _synthetic_members(5000)
    assert any(len(m["give"]) != len(set(m["give"])) for m in members)      # duplicates
    assert any(m["give"] != sorted(m["give"], key=str) for m in members)    # unsorted
    assert any(m["partner"] is None for m in members)
    assert any(type(a) is int for m in members for a in m["give"])
    assert any(type(m["base_score"]) is int for m in members)
    back = _round_trip(members)
    assert json.dumps(back) == json.dumps(members)
    assert ep.candidate_set_hash(back) == ep.candidate_set_hash(members)


def test_absent_and_null_fields_round_trip():
    members = [{"trade_hash": "00ff00ff00ff00ff", "partner": None, "give": [], "receive": None,
                "base_score": None, "in_deck": None},
               {"trade_hash": "0123456789abcdef", "give": ["a", "a"], "in_deck": False},
               {"trade_hash": "fedcba9876543210", "partner": "x", "give": ["b"],
                "receive": ["a"], "base_score": 2.5, "in_deck": True}]
    assert json.dumps(_round_trip(members)) == json.dumps(members)
    assert _round_trip([]) == []


@pytest.mark.parametrize("mutate, message", [
    (lambda ms: ms[0].update(trade_hash="ABCDEF0123456789"), "lowercase hex"),
    (lambda ms: ms[0].update(extra=1), "holds only"),
    (lambda ms: ms[0].update(give=("a", "b")), "list of str or int"),
    (lambda ms: ms[0].update(partner=True), "str or int id"),
    (lambda ms: ms[0].update(base_score="0.5"), "packed exactly"),
    (lambda ms: ms[0].update(in_deck=1), "not a bool"),
    (lambda ms: ms[0].pop("trade_hash"), "set_hash"),
    (lambda ms: ms.__setitem__(0, {k: ms[0][k] for k in reversed(list(ms[0]))}), "round-trip"),
])
def test_what_cannot_round_trip_exactly_is_refused(mutate, message):
    members = _synthetic_members(5)
    mutate(members)
    with pytest.raises(ValueError, match=message):
        ep.pack_candidates(RUN, members)


# ---------------------------------------------------------------------------
# Integrity and versions
# ---------------------------------------------------------------------------

def _parts(packed):
    data = zlib.decompress(packed.candidates_packed)
    r = ep._Reader(data)
    head = json.loads(r.take(ep._read_uvarint(r)))
    return head, data[r.pos:]


def _repack(packed, head, raw, **fields):
    header = ep._canon(head).encode()
    return replace(packed, candidates_packed=zlib.compress(
        ep._uvarint(len(header)) + header + raw), **fields)


def _with_header(edit):
    def tamper(packed):
        head, raw = _parts(packed)
        edit(head)
        return _repack(packed, head, raw)
    return tamper


def _flip_raw(packed):
    head, raw = _parts(packed)
    raw = bytearray(raw)
    raw[len(raw) // 2] ^= 0x01
    return _repack(packed, head, bytes(raw))


@pytest.mark.parametrize("tamper", [
    _with_header(lambda h: h["run"].update(deck_job_id="job-2")),
    _with_header(lambda h: h["partners"].reverse()),
    _with_header(lambda h: h["assets"].__setitem__(0, "zzz")),
    _with_header(lambda h: h.update(set_hash="0" * 16)),
    _with_header(lambda h: h.update(checksum="0" * 64)),
    _flip_raw,
], ids=["run", "partner_dictionary", "asset_dictionary", "set_hash", "checksum", "member"])
def test_tampering_is_refused(tamper):
    packed = ep.pack_candidates(RUN, _synthetic_members(300))
    with pytest.raises(ep.PackIntegrityError):
        ep.unpack_candidates(tamper(packed))


def test_a_set_hash_that_disagrees_with_the_members_is_refused():
    """Forged with a consistent checksum: only the set_hash check catches it."""
    members = _synthetic_members(20)
    packed = ep.pack_candidates(RUN, members)
    head, raw = _parts(packed)
    head["set_hash"] = "f" * 16
    head["checksum"] = ep._cand_checksum_v1(head, members)
    with pytest.raises(ep.PackIntegrityError, match="set_hash mismatch"):
        ep.unpack_candidates(_repack(packed, head, raw))


def test_versions():
    packed = ep.pack_candidates(RUN, _synthetic_members(10))
    assert packed.cand_pack_version == ep.CAND_PACK_VERSION
    for version in range(1, ep.CAND_PACK_VERSION + 1):
        assert callable(ep.CAND_DECODERS.get(version)), version
    head, raw = _parts(packed)
    for version in (0, ep.CAND_PACK_VERSION + 1, "1", True, None):
        bad = _repack(packed, {**head, "cand_pack_version": version}, raw,
                      cand_pack_version=version)
        with pytest.raises(ep.PackIntegrityError, match="unknown cand_pack_version"):
            ep.unpack_candidates(bad)
    with pytest.raises(ep.PackIntegrityError, match="disagrees"):
        ep.unpack_candidates(replace(packed, cand_pack_version=2))
    with pytest.raises(ep.PackIntegrityError, match="unreadable"):
        ep.unpack_candidates(replace(packed, candidates_packed=b"not zlib"))


# ---------------------------------------------------------------------------
# scorecard_evidence reads packed rows as the JSON rows they replace
# ---------------------------------------------------------------------------

def _snapshot(path, sets, *, form):
    """A local SQLite snapshot. form: "json" (today's rows), "packed" (the
    new writer's rows: candidates_json stays NOT NULL and holds ''),
    "legacy" (no packed columns)."""
    md = MetaData()
    cands = deck_candidate_sets_table.to_metadata(md)
    if form != "legacy":
        cands.append_column(Column("candidates_packed", LargeBinary))
        cands.append_column(Column("cand_pack_version", Integer))
    assert not cands.c.candidates_json.nullable
    imps = deck_impressions_table.to_metadata(md)
    eng = create_engine(f"sqlite:///{path}")
    md.create_all(eng)
    with eng.begin() as conn:
        for row in sets:
            if form == "packed":
                packed = ep.pack_candidates({"candidate_set_id": row["candidate_set_id"]},
                                            json.loads(row["candidates_json"]))
                row = {**row, "candidates_json": "",
                       "candidates_packed": packed.candidates_packed,
                       "cand_pack_version": packed.cand_pack_version}
            conn.execute(insert(cands).values(**row))
        conn.execute(insert(imps).values(
            impression_id="i1", user_id="u", league_id="lg", deck_job_id="job-1",
            card_index=0, propensity=1.0, served_at="2026-10-24T00:00:00+00:00",
            candidate_set_id=sets[0]["candidate_set_id"]))
    eng.dispose()
    return path


def test_scorecard_outputs_are_identical_from_packed_and_json_rows(real_sets, tmp_path):
    synthetic = {"candidate_set_id": "cs-synthetic", "deck_job_id": "job-s", "user_id": "u",
                 "league_id": "lg", "size": 2000, "created_at": "2026-10-24T00:00:00+00:00"}
    members = _synthetic_members(2000)
    synthetic.update(set_hash=ep.candidate_set_hash(members), candidates_json=json.dumps(members))
    sets = real_sets + [synthetic]
    audits = {form: se.audit_rows(se.load_sqlite_snapshot(
                  _snapshot(tmp_path / f"{form}.db", sets, form=form)), include_records=True)
              for form in ("json", "packed", "legacy")}
    assert audits["packed"] == audits["json"] == audits["legacy"]
    assert audits["packed"]["tables"]["deck_candidate_sets"]["rows"] == len(sets)


def test_scorecard_flags_an_unreadable_pack(real_sets, tmp_path):
    rows = se.load_sqlite_snapshot(_snapshot(tmp_path / "p.db", real_sets, form="packed"))
    rows["deck_candidate_sets"][0].update(candidates_json=None)
    bad = {**rows, "deck_candidate_sets": [
        {**rows["deck_candidate_sets"][0], "candidates_packed": b"junk", "cand_pack_version": 1},
        *rows["deck_candidate_sets"][1:]]}
    manifest = se.audit_rows(bad, include_records=True)
    assert manifest["counts"]["candidate_set_pack_unreadable"] == 1
    first = manifest["private_records"]["source_tables"]["deck_candidate_sets"][0]
    assert first["candidates_json"] is None and "candidates_pack_error" in first


# head-eng's schema ruling: candidates_json stays NOT NULL; a packed row stores
# '' there, and candidates_packed IS NOT NULL is authoritative.

def _set_row(members, cid="cs-x"):
    return {"candidate_set_id": cid, "deck_job_id": "job-1", "user_id": "u", "league_id": "lg",
            "size": len(members), "set_hash": ep.candidate_set_hash(members),
            "candidates_json": json.dumps(members), "created_at": "2026-10-24T00:00:00+00:00"}


def _packed_row(members, **override):
    packed = ep.pack_candidates({"candidate_set_id": "cs-x"}, members)
    return {**_set_row(members), "candidates_json": "",
            "candidates_packed": packed.candidates_packed,
            "cand_pack_version": packed.cand_pack_version, **override}


def test_a_packed_row_with_empty_candidates_json_reads_exactly_like_the_json_row():
    members = _synthetic_members(50)
    packed = se._select_rows({"deck_candidate_sets": [_packed_row(members)]})
    legacy = se._select_rows({"deck_candidate_sets": [_set_row(members)]})
    assert packed == legacy
    assert se.audit_rows({"deck_candidate_sets": [_packed_row(members)]}, include_records=True) \
        == se.audit_rows({"deck_candidate_sets": [_set_row(members)]}, include_records=True)


def test_a_row_without_a_pack_reads_its_legacy_json_unchanged():
    row = _set_row(_synthetic_members(10))
    no_pack = {**row, "candidates_packed": None, "cand_pack_version": None}
    assert se._select_rows({"deck_candidate_sets": [no_pack]})["deck_candidate_sets"] == [row]


@pytest.mark.parametrize("json_column", ["", "legacy JSON"])
def test_a_corrupt_pack_is_flagged_and_candidates_json_is_never_read(json_column):
    """The pack is authoritative: a corrupt one is flagged, and the reader
    never falls back to candidates_json, whether it holds '' or valid JSON."""
    members = _synthetic_members(10)
    corrupt = _flip_raw(ep.pack_candidates({"candidate_set_id": "cs-x"}, members))
    row = _packed_row(members, candidates_packed=corrupt.candidates_packed,
                      candidates_json=json.dumps(members) if json_column else "")
    manifest = se.audit_rows({"deck_candidate_sets": [row]}, include_records=True)
    [out] = manifest["private_records"]["source_tables"]["deck_candidate_sets"]
    assert out["candidates_json"] is None and out["candidates_pack_error"]
    assert manifest["counts"]["candidate_set_pack_unreadable"] == 1
