"""DEC-2 (a) / ADR-025 C1: packed evidence for the unseen cards of one served deck.

Format accepted by models-lead with conditions (models-lead-launch.md
§Reviews-2 R2.2): (a) the checksum covers everything a reader can act on,
(c) version discipline. Pure bytes <-> dicts: no table, no writer, no DB I/O.
trades-eng's evidence writer calls pack_run and stores the PackedRun's fields
verbatim as one deck_evidence_packs row; backend.eval.data.load_decks reads
the row back through unpack_run. The row contract lives in
docs/plans/trade-time-to-suggestion/eng-evidence-contract.md §6.

One packed record per served run. PackedRun's fields are the row's pack
columns, field for field:

  pack_version  PACK_VERSION at write time (the header carries it too).
  header_json   written once per run: pack_version, the caller's run metadata
                (`run`, returned verbatim by unpack_run: the values snapshot
                id, built_at, the config reference, and `deliveries`),
                card_count, the per-run fields hoisted off the cards
                (`shared`), the per-run dictionaries, the taste_attrs
                vocabulary, and the layout needed to slice the blob.
                run["deliveries"] (R4.2 U1) is required: the delivered page
                boundaries [[last_card_index, delivered_at], ...] with
                last_card_index strictly increasing in [0, card_count).
                Pages are delivered from card 0, so the cards delivered are
                0..the last boundary (check_deliveries).
  cards_blob    zlib(raw), raw = per-card columns in card_index order.
  checksum      sha256 hex of ONE canonical JSON document holding the parsed
                header and the unpacked cards:
                  json.dumps({"header": header, "cards": cards},
                             sort_keys=True, separators=(",", ":"))
                The header holds the run metadata, the shared fields, the
                dictionaries and the layout, so a change to any of them, or
                to any card, fails the checksum: it covers everything a
                reader can act on.
  card_count    the served deck's card count, ghosts excluded. The deck's
                full rows and its packed cards together hold card_index
                0..card_count-1; the reader flags a gap as incomplete_deck.

Input cards are what eval sees today, backend.eval.data.card_dict (the frozen
features_json merged with the logged columns), plus the deck_impressions
attribution columns. Only CONTRACT_KEYS survive packing: what the registered
scorers and replay read (value_model.extract_features and ValueModel._inject,
taste_service.attrs_from_features, eval/scorers.py, eval/replay.py), plus the
attribution fields. impression_id is not stored; the reader synthesizes it.

Exactness: an absent key stays absent and None stays distinct from a value.
Every float is float8 (an int stays an int, as int64 in the same slot).
Position lists are dictionary-coded as whole lists, so the multiplicity
attrs_from_features divides by (len(give_pos) counts duplicates), their order
and any '?' entries survive; a set or bitmask encoding would not. shape and
shape_bucket, lane and archetype are kept separately, because extract_features
falls back from one to the other. pack_run decodes its own output and refuses
to return a pack that does not round-trip.

VERSION DISCIPLINE (R2.2 (c)). Any change to the layout, an encoding or the
checksum bumps PACK_VERSION and registers a new decoder in DECODERS. Packs live
as long as their decks, so the reader decodes every version from 1 to
PACK_VERSION forever: an old decoder is never deleted or edited while packs of
its version exist. unpack_run refuses a version with no decoder.

Candidate-set packing (pack_candidates / unpack_candidates, ruling 25) is a
separate codec at the end of this module, with its own CAND_PACK_VERSION.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import dataclass

PACK_VERSION = 1

# Constant across one call of server._log_deck_signal_impressions: the job's
# user/league/job id, one served_at, one candidate-set row, and one
# load_board_state read (ranked_player_count, last_board_update_at, and
# user_value_basis derived from it). policy_version is NOT here: the bake-off,
# value-core and owner paths stamp it per card.
RUN_FIELDS = (
    "user_id", "league_id", "deck_job_id", "served_at",
    "candidate_set_id", "candidate_set_size",
    "ranked_player_count", "user_value_basis", "last_board_update_at",
)

# Per-card dictionary codes (0, 1 or 2 bytes, by dictionary size). Keys that
# co-vary share one code; an entry holds one slot per key: [] = absent,
# [value] = present (value may be None).
CODED_GROUPS = (
    ("shape", "shape_bucket"),
    ("lane", "archetype"),
    ("basis",),
    ("likes_you", "relaxed", "involves_pick"),
    ("give_positions",),
    ("receive_positions",),
    ("partner_user_id",),
    ("centerpiece_id",),
    ("model_arm", "policy_version", "fairness_threshold"),
    ("group_key", "lane_slot"),
)
FLOAT_FIELDS = (
    "propensity", "base_score", "final_score",
    "give_value", "receive_value", "surplus_margin", "fairness_score",
    "taste_pref_long", "taste_pref_short",
)
INT_FIELDS = ("arm_rank", "group_rank")
CONTRACT_KEYS = frozenset(
    RUN_FIELDS + FLOAT_FIELDS + INT_FIELDS
    + tuple(k for group in CODED_GROUPS for k in group)
    + ("card_index", "trade_hash", "taste_attrs"))

# Per-card value states, 2 bits each (omitted when uniform across the run).
_ABSENT, _NULL, _VALUE, _INT = 0, 1, 2, 3
_HEX = frozenset("0123456789abcdef")


class PackIntegrityError(ValueError):
    """The pack is unreadable, has an unknown pack_version, fails its
    checksum, or its row fields disagree with its header. Replay excludes
    the deck; it never sinks it (C7 iv)."""


@dataclass(frozen=True)
class PackedRun:
    """One deck_evidence_packs row's pack columns; the writer stores each
    field verbatim in the column of the same name."""
    pack_version: int
    header_json: str
    cards_blob: bytes
    checksum: str
    card_count: int


def pack_run(run: dict, cards: list[dict], *, card_count: int) -> PackedRun:
    """Pack one served run. `run` is the caller's run metadata (e.g. the values
    snapshot id, built_at, the config reference, and the required
    `deliveries`, see check_deliveries), JSON-serializable; `cards`
    are the packed card dicts in card_index order; `card_count` is the served
    deck's card count, ghosts excluded (full rows and packed cards together).
    Raises ValueError for anything it cannot pack exactly."""
    projected = [_project(c) for c in cards]
    sections, layout = _encode_sections(projected)
    idx = [c["card_index"] for c in projected]
    if (type(card_count) is not int or card_count < 0
            or (idx and (idx[0] < 0 or idx[-1] >= card_count))):
        raise ValueError(f"card_count {card_count!r} must be an int with every "
                         "packed card_index in [0, card_count)")
    check_deliveries(run, card_count)
    header_json = json.dumps(
        {"pack_version": PACK_VERSION, "run": run, "card_count": card_count, **layout},
        sort_keys=True, separators=(",", ":"))
    head = json.loads(header_json)      # exactly what a reader parses
    raw = b"".join(data for _label, data in sections)
    packed = PackedRun(PACK_VERSION, header_json, zlib.compress(raw, 9),
                       _checksum_v1(head, projected), card_count)
    try:
        DECODERS[PACK_VERSION](head, packed.cards_blob, packed.checksum)
    except PackIntegrityError:
        raise ValueError("pack does not round-trip exactly; refusing to write it") from None
    return packed


def check_deliveries(run, card_count: int) -> int:
    """R4.2 U1: validate run["deliveries"] and return the last delivered
    card_index (-1 when nothing was delivered). Raises PackIntegrityError
    (a ValueError) when it is missing or malformed."""
    deliveries = run.get("deliveries") if isinstance(run, dict) else None
    if not isinstance(deliveries, (list, tuple)):
        raise PackIntegrityError("run['deliveries'] must be a list of "
                                 "[last_card_index, delivered_at] pairs")
    last = -1
    for d in deliveries:
        if (not isinstance(d, (list, tuple)) or len(d) != 2 or type(d[0]) is not int
                or not isinstance(d[1], str) or not last < d[0] < card_count):
            raise PackIntegrityError(
                f"deliveries entry {d!r}: needs [last_card_index, delivered_at] with "
                f"last_card_index increasing in [0, {card_count})")
        last = d[0]
    return last


def unpack_run(packed: PackedRun) -> tuple[dict, list[dict]]:
    """Return (run metadata, cards in card_index order). Raises
    PackIntegrityError on an unreadable header, a pack_version with no
    decoder, an undecodable pack, a checksum mismatch, or a pack_version or
    card_count field that disagrees with the (checksummed) header."""
    try:
        head = json.loads(packed.header_json)
    except (TypeError, ValueError) as e:
        raise PackIntegrityError(f"unreadable header: {e}") from None
    version = head.get("pack_version") if isinstance(head, dict) else None
    decode = DECODERS.get(version) if type(version) is int else None
    if decode is None:
        raise PackIntegrityError(f"unknown pack_version {version!r}")
    if packed.pack_version != version:
        raise PackIntegrityError(
            f"pack_version {packed.pack_version!r} disagrees with the header's {version!r}")
    try:
        cards = decode(head, packed.cards_blob, packed.checksum)
        run, header_count = head["run"], head["card_count"]
    except PackIntegrityError:
        raise
    except Exception as e:
        raise PackIntegrityError(f"undecodable pack: {e!r}") from None
    if packed.card_count != header_count:
        raise PackIntegrityError(
            f"card_count {packed.card_count!r} disagrees with the header's {header_count!r}")
    return run, cards


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def _project(card: dict) -> dict:
    if card.get("is_ghost"):
        raise ValueError("ghost rows are never packed (C5)")
    return {k: v for k, v in card.items() if k in CONTRACT_KEYS}


def _encode_sections(cards: list[dict]) -> tuple[list[tuple[str, bytes]], dict]:
    """(labelled raw sections in blob order, header layout). The labels exist
    so the byte budget can be measured per field."""
    n = len(cards)
    sections: list[tuple[str, bytes]] = []
    layout: dict = {"n_cards": n, "states": {}, "dicts": {}, "int_widths": {}}

    def add_states(name, states):
        if len(set(states)) <= 1:
            layout["states"][name] = states[0] if states else _ABSENT
        else:
            layout["states"][name] = None
            out = bytearray((n + 3) // 4)
            for i, s in enumerate(states):
                out[i >> 2] |= s << ((i & 3) * 2)
            sections.append((f"{name}.state", bytes(out)))

    idx = [c.get("card_index") for c in cards]
    if any(type(i) is not int for i in idx) or any(b <= a for a, b in zip(idx, idx[1:])):
        raise ValueError("cards need int card_index values in strictly increasing order")
    if n and idx == list(range(idx[0], idx[0] + n)):
        layout["card_index_start"] = idx[0]
    else:
        layout["card_index_start"] = None
        sections.append(("card_index", struct.pack(f"<{n}i", *idx)))

    shared = {}
    for k in RUN_FIELDS:
        slots = {_canon([c[k]] if k in c else []) for c in cards}
        if len(slots) > 1:
            raise ValueError(f"{k} is not constant across the run")
        if cards and k in cards[0]:
            shared[k] = cards[0][k]
    layout["shared"] = shared

    for group in CODED_GROUPS:
        name = "+".join(group)
        entries, index, codes = [], {}, []
        for c in cards:
            entry = [[c[k]] if k in c else [] for k in group]
            key = _canon(entry)
            if key not in index:
                index[key] = len(entries)
                entries.append(entry)
            codes.append(index[key])
        layout["dicts"][name] = entries
        width = _code_width(len(entries))
        if width:
            sections.append((name, b"".join(code.to_bytes(width, "little") for code in codes)))

    for k in FLOAT_FIELDS:
        states, values = [], []
        for c in cards:
            v = c.get(k)
            if k not in c:
                states.append(_ABSENT)
            elif v is None:
                states.append(_NULL)
            elif type(v) is float:
                states.append(_VALUE)
                values.append(struct.pack("<d", v))
            elif type(v) is int:
                states.append(_INT)
                values.append(struct.pack("<q", v))
            else:
                raise ValueError(f"{k}: cannot pack {type(v).__name__} exactly")
        add_states(k, states)
        sections.append((k, b"".join(values)))

    for k in INT_FIELDS:
        states, values = [], []
        for c in cards:
            v = c.get(k)
            if k not in c:
                states.append(_ABSENT)
            elif v is None:
                states.append(_NULL)
            elif type(v) is int:
                states.append(_INT)
                values.append(v)
            else:
                raise ValueError(f"{k}: cannot pack {type(v).__name__} exactly")
        width = 2 if all(-32768 <= v <= 32767 for v in values) else 4
        layout["int_widths"][k] = width
        add_states(k, states)
        sections.append((k, struct.pack(f"<{len(values)}{'h' if width == 2 else 'i'}", *values)))

    states, hashes = [], []
    for c in cards:
        v = c.get("trade_hash")
        if "trade_hash" not in c:
            states.append(_ABSENT)
        elif v is None:
            states.append(_NULL)
        elif isinstance(v, str) and len(v) == 16 and set(v) <= _HEX:
            states.append(_VALUE)
            hashes.append(bytes.fromhex(v))
        else:
            raise ValueError(f"trade_hash {v!r} is not 16 lowercase hex characters")
    add_states("trade_hash", states)
    sections.append(("trade_hash", b"".join(hashes)))

    states, lists = [], []
    for c in cards:
        v = c.get("taste_attrs")
        if "taste_attrs" not in c:
            states.append(_ABSENT)
        elif v is None:
            states.append(_NULL)
        elif (isinstance(v, list) and all(isinstance(a, str) for a in v)
              and v == sorted(set(v))):
            states.append(_VALUE)
            lists.append(v)
        else:
            raise ValueError("taste_attrs must be a sorted list of unique strings "
                             "(a bitset cannot keep anything else)")
    vocab = sorted({a for attrs in lists for a in attrs})
    layout["taste_vocab"] = vocab
    bit = {a: i for i, a in enumerate(vocab)}
    width = (len(vocab) + 7) // 8
    add_states("taste_attrs", states)
    sections.append(("taste_attrs", b"".join(
        sum(1 << bit[a] for a in attrs).to_bytes(width, "little") for attrs in lists)))
    return sections, layout


def _code_width(n_entries: int) -> int:
    if n_entries <= 1:
        return 0
    if n_entries <= 1 << 8:
        return 1
    if n_entries <= 1 << 16:
        return 2
    raise ValueError(f"{n_entries} dictionary entries exceed 2-byte codes")


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _checksum_v1(head: dict, cards: list[dict]) -> str:
    """The parsed header (run metadata, card_count, shared fields,
    dictionaries, layout) and the unpacked cards, as one canonical JSON
    document."""
    doc = json.dumps({"header": head, "cards": cards}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(doc.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Decoding (v1 mirrors _encode_sections, section by section)
# ---------------------------------------------------------------------------

class _Reader:
    def __init__(self, raw: bytes):
        self.raw, self.pos = raw, 0

    def take(self, k: int) -> bytes:
        if self.pos + k > len(self.raw):
            raise PackIntegrityError("truncated pack")
        out = self.raw[self.pos:self.pos + k]
        self.pos += k
        return out


def _copy(v):
    return list(v) if isinstance(v, list) else v


def _decode(head: dict, raw: bytes) -> list[dict]:
    r = _Reader(raw)
    n = head["n_cards"]

    def states(name):
        uniform = head["states"][name]
        if uniform is not None:
            return [uniform] * n
        packed = r.take((n + 3) // 4)
        return [(packed[i >> 2] >> ((i & 3) * 2)) & 3 for i in range(n)]

    start = head["card_index_start"]
    idx = (range(start, start + n) if start is not None
           else struct.unpack(f"<{n}i", r.take(4 * n)))
    cards = [{"card_index": i} for i in idx]
    for c in cards:
        for k, v in head["shared"].items():
            c[k] = _copy(v)

    for group in CODED_GROUPS:
        entries = head["dicts"]["+".join(group)]
        width = _code_width(len(entries))
        for c in cards:
            entry = entries[int.from_bytes(r.take(width), "little") if width else 0]
            for k, slot in zip(group, entry):
                if slot:
                    c[k] = _copy(slot[0])

    for k in FLOAT_FIELDS:
        for c, s in zip(cards, states(k)):
            if s == _NULL:
                c[k] = None
            elif s == _VALUE:
                c[k] = struct.unpack("<d", r.take(8))[0]
            elif s == _INT:
                c[k] = struct.unpack("<q", r.take(8))[0]

    for k in INT_FIELDS:
        width = head["int_widths"][k]
        fmt = "<h" if width == 2 else "<i"
        for c, s in zip(cards, states(k)):
            if s == _NULL:
                c[k] = None
            elif s == _INT:
                c[k] = struct.unpack(fmt, r.take(width))[0]

    for c, s in zip(cards, states("trade_hash")):
        if s == _NULL:
            c["trade_hash"] = None
        elif s == _VALUE:
            c["trade_hash"] = r.take(8).hex()

    vocab = head["taste_vocab"]
    width = (len(vocab) + 7) // 8
    for c, s in zip(cards, states("taste_attrs")):
        if s == _NULL:
            c["taste_attrs"] = None
        elif s == _VALUE:
            bits = int.from_bytes(r.take(width), "little")
            c["taste_attrs"] = [a for i, a in enumerate(vocab) if bits >> i & 1]

    if r.pos != len(raw):
        raise PackIntegrityError("trailing bytes after the last section")
    return cards


def _decode_v1(head: dict, cards_blob: bytes, checksum: str) -> list[dict]:
    cards = _decode(head, zlib.decompress(cards_blob))
    if _checksum_v1(head, cards) != checksum:
        raise PackIntegrityError("checksum mismatch")
    return cards


# Every pack_version ever written -> its decoder. Never delete or edit an entry
# while packs of that version exist (VERSION DISCIPLINE, module docstring).
DECODERS = {1: _decode_v1}


# ===========================================================================
# Candidate-set packing (head-eng ruling 25): deck_candidate_sets.candidates_packed
#
# Separate from the deck pack above (its layout is frozen and untouched): its
# own CAND_PACK_VERSION and CAND_DECODERS, under the same version discipline.
# One candidate set = the members server._log_deck_signal_impressions writes,
# each {trade_hash, partner, give, receive, base_score, in_deck} in that key
# order. The packed form is ONE bytes value (the column):
#
#   zlib( uvarint(len(header)) + header + raw )
#
#   header  canonical JSON: cand_pack_version, the caller's `run`, n, set_hash,
#           the per-field state layout, the per-run partner dictionary, the
#           per-run asset-id dictionary, and `checksum`: sha256 of canonical
#           JSON {"header": <header without checksum>, "members": <members>},
#           so the run, the dictionaries, set_hash and every member are covered.
#   raw     per field, in member order: a 2-bit state section (absent / null /
#           value / int) unless the state is uniform; trade_hash as 8 raw
#           bytes; partner as a uvarint dictionary code; give and receive each
#           as uvarint length + uvarint asset codes (exact order and
#           duplicates kept); base_score as float8 (an int as int64); in_deck
#           as one bit.
#
# set_hash is computed exactly as the writer computes it (candidate_set_hash)
# and verified on unpack. pack_candidates refuses anything whose unpacked
# json.dumps differs from the input's by a byte (key order, types, values).
# ===========================================================================

CAND_PACK_VERSION = 1
CAND_FIELDS = ("trade_hash", "partner", "give", "receive", "base_score", "in_deck")


@dataclass(frozen=True)
class PackedCandidates:
    """deck_candidate_sets' two packed columns, stored verbatim."""
    cand_pack_version: int
    candidates_packed: bytes


def candidate_set_hash(members: list[dict]) -> str:
    """deck_candidate_sets.set_hash exactly as the writer computes it: sha256
    of the members' trade_hashes, sorted and joined by '|', first 16 hex."""
    return hashlib.sha256(
        "|".join(sorted(m["trade_hash"] for m in members)).encode()).hexdigest()[:16]


def pack_candidates(run: dict, members: list[dict]) -> PackedCandidates:
    """Pack one candidate set. `run` is the caller's JSON-serializable
    metadata (e.g. candidate_set_id, deck_job_id), returned verbatim by
    unpack_candidates. Raises ValueError for anything it can't round-trip
    byte for byte; the writer then keeps candidates_json for that row."""
    raw, layout = _encode_candidates(members)
    try:
        set_hash = candidate_set_hash(members)
    except (KeyError, TypeError) as e:
        raise ValueError(f"set_hash can't be computed as the writer does: {e!r}") from None
    head = json.loads(_canon({"cand_pack_version": CAND_PACK_VERSION, "run": run,
                              "n": len(members), "set_hash": set_hash, **layout}))
    head["checksum"] = _cand_checksum_v1(head, members)
    header = _canon(head).encode("utf-8")
    packed = PackedCandidates(CAND_PACK_VERSION,
                              zlib.compress(_uvarint(len(header)) + header + raw, 9))
    try:
        _run, back = unpack_candidates(packed)
    except PackIntegrityError as e:
        raise ValueError(f"candidate set does not round-trip: {e}") from None
    if json.dumps(back) != json.dumps(members):
        raise ValueError("candidate set does not round-trip exactly (key order, types "
                         "or values); refusing to pack it")
    return packed


def unpack_candidates(packed: PackedCandidates) -> tuple[dict, list[dict]]:
    """(run, members in stored order). Raises PackIntegrityError on an
    unreadable pack, an unknown cand_pack_version or one that disagrees
    with its column, a checksum mismatch, or a set_hash mismatch."""
    try:
        data = zlib.decompress(packed.candidates_packed)
        r = _Reader(data)
        head = json.loads(r.take(_read_uvarint(r)))
        raw = data[r.pos:]
    except PackIntegrityError:
        raise
    except Exception as e:
        raise PackIntegrityError(f"unreadable candidate pack: {e!r}") from None
    version = head.get("cand_pack_version") if isinstance(head, dict) else None
    decode = CAND_DECODERS.get(version) if type(version) is int else None
    if decode is None:
        raise PackIntegrityError(f"unknown cand_pack_version {version!r}")
    if packed.cand_pack_version != version:
        raise PackIntegrityError(f"cand_pack_version {packed.cand_pack_version!r} "
                                 f"disagrees with the pack's {version!r}")
    try:
        members = decode(head, raw)
    except PackIntegrityError:
        raise
    except Exception as e:
        raise PackIntegrityError(f"undecodable candidate pack: {e!r}") from None
    return head["run"], members


def _uvarint(n: int) -> bytes:
    out = bytearray()
    while True:
        low, n = n & 0x7F, n >> 7
        out.append(low | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _read_uvarint(r: "_Reader") -> int:
    n = shift = 0
    while True:
        byte = r.take(1)[0]
        n |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return n
        shift += 7


def _cand_checksum_v1(head: dict, members: list[dict]) -> str:
    body = {k: v for k, v in head.items() if k != "checksum"}
    doc = json.dumps({"header": body, "members": members}, sort_keys=True,
                     separators=(",", ":"))
    return hashlib.sha256(doc.encode("utf-8")).hexdigest()


def _is_id(v) -> bool:
    return type(v) in (str, int)


def _encode_candidates(members: list[dict]) -> tuple[bytes, dict]:
    n = len(members)
    layout: dict = {"states": {}, "partners": [], "assets": []}
    index: dict = {"partners": {}, "assets": {}}

    def code(table: str, value) -> bytes:
        key = _canon(value)
        if key not in index[table]:
            index[table][key] = len(layout[table])
            layout[table].append(value)
        return _uvarint(index[table][key])

    states = {f: [] for f in CAND_FIELDS}
    out = {f: bytearray() for f in CAND_FIELDS}
    bits: list[bool] = []
    for m in members:
        if type(m) is not dict or set(m) - set(CAND_FIELDS):
            raise ValueError(f"a candidate member holds only {CAND_FIELDS}")
        for f in CAND_FIELDS:
            if f not in m:
                states[f].append(_ABSENT)
                continue
            v = m[f]
            if v is None:
                states[f].append(_NULL)
                continue
            state = _VALUE
            if f == "trade_hash":
                if not (type(v) is str and len(v) == 16 and set(v) <= _HEX):
                    raise ValueError(f"trade_hash {v!r} is not 16 lowercase hex characters")
                out[f] += bytes.fromhex(v)
            elif f == "partner":
                if not _is_id(v):
                    raise ValueError(f"partner {v!r} is not a str or int id")
                out[f] += code("partners", v)
            elif f in ("give", "receive"):
                if type(v) is not list or not all(_is_id(a) for a in v):
                    raise ValueError(f"{f} must be a list of str or int asset ids")
                out[f] += _uvarint(len(v)) + b"".join(code("assets", a) for a in v)
            elif f == "base_score":
                if type(v) is float:
                    out[f] += struct.pack("<d", v)
                elif type(v) is int and -2**63 <= v < 2**63:
                    out[f] += struct.pack("<q", v)
                    state = _INT
                else:
                    raise ValueError(f"base_score {v!r} can't be packed exactly")
            elif type(v) is bool:                          # in_deck
                bits.append(v)
            else:
                raise ValueError(f"in_deck {v!r} is not a bool")
            states[f].append(state)

    sections = []
    for f in CAND_FIELDS:
        if len(set(states[f])) <= 1:
            layout["states"][f] = states[f][0] if n else _ABSENT
        else:
            layout["states"][f] = None
            packed = bytearray((n + 3) // 4)
            for i, s in enumerate(states[f]):
                packed[i >> 2] |= s << ((i & 3) * 2)
            sections.append(bytes(packed))
    flags = bytearray((len(bits) + 7) // 8)
    for i, b in enumerate(bits):
        flags[i >> 3] |= b << (i & 7)
    sections += [bytes(out[f]) for f in CAND_FIELDS[:-1]] + [bytes(flags)]
    return b"".join(sections), layout


def _decode_candidates_v1(head: dict, raw: bytes) -> list[dict]:
    r = _Reader(raw)
    n = head["n"]
    states = {}
    for f in CAND_FIELDS:
        uniform = head["states"][f]
        if uniform is not None:
            states[f] = [uniform] * n
        else:
            packed = r.take((n + 3) // 4)
            states[f] = [(packed[i >> 2] >> ((i & 3) * 2)) & 3 for i in range(n)]
    partners, assets = head["partners"], head["assets"]
    members: list[dict] = [{} for _ in range(n)]
    for f in CAND_FIELDS[:-1]:
        for m, s in zip(members, states[f]):
            if s == _ABSENT:
                continue
            if s == _NULL:
                m[f] = None
            elif f == "trade_hash":
                m[f] = r.take(8).hex()
            elif f == "partner":
                m[f] = partners[_read_uvarint(r)]
            elif f in ("give", "receive"):
                m[f] = [assets[_read_uvarint(r)] for _ in range(_read_uvarint(r))]
            else:                                          # base_score
                m[f] = struct.unpack("<q" if s == _INT else "<d", r.take(8))[0]
    k = sum(s == _VALUE for s in states["in_deck"])
    flags, i = r.take((k + 7) // 8), 0
    for m, s in zip(members, states["in_deck"]):
        if s == _NULL:
            m["in_deck"] = None
        elif s == _VALUE:
            m["in_deck"] = bool(flags[i >> 3] >> (i & 7) & 1)
            i += 1
    if r.pos != len(raw):
        raise PackIntegrityError("trailing bytes after the last candidate section")
    if _cand_checksum_v1(head, members) != head.get("checksum"):
        raise PackIntegrityError("checksum mismatch")
    if candidate_set_hash(members) != head["set_hash"]:
        raise PackIntegrityError("set_hash mismatch")
    return members


# Every cand_pack_version ever written -> its decoder (same discipline as DECODERS).
CAND_DECODERS = {1: _decode_candidates_v1}
