"""DEC-2 (a) PROTOTYPE: packed evidence for the unseen cards of one served deck.

Unmerged; the format is pending models-lead's acceptance
(docs/plans/org-bringup/leads/models-lead-launch.md, §DEC-2 "Confirmation"
§1 and §4). Pure bytes <-> dicts: no table, no writer, no DB I/O.

One packed record per served run:

  header_json  written once per run: pack_version, the caller's run metadata
               (`run`, returned verbatim by unpack_run), the per-run fields
               hoisted off the cards (`shared`), the per-run dictionaries, the
               taste_attrs vocabulary, and the layout needed to slice the blob.
  blob         zlib(raw), raw = per-card columns in card_index order.
  checksum     sha256 hex of the canonical JSONL of the unpacked cards
               (json.dumps(card, sort_keys=True), one line per card).

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
    """The pack is unreadable, has an unknown pack_version, or fails its
    checksum. Replay excludes the deck; it never sinks it (C7 iv)."""


@dataclass(frozen=True)
class PackedRun:
    header_json: str
    blob: bytes
    checksum: str


def pack_run(header: dict, cards: list[dict]) -> PackedRun:
    """Pack one served run. `header` is the caller's run metadata (e.g. the
    values snapshot id and config reference); `cards` are card dicts in
    card_index order. Raises ValueError for anything it cannot pack exactly."""
    projected = [_project(c) for c in cards]
    sections, layout = _encode_sections(projected)
    raw = b"".join(data for _label, data in sections)
    header_json = json.dumps({"pack_version": PACK_VERSION, "run": header, **layout},
                             sort_keys=True, separators=(",", ":"))
    checksum = _checksum(projected)
    if _checksum(_decode(json.loads(header_json), raw)) != checksum:
        raise ValueError("pack does not round-trip exactly; refusing to write it")
    return PackedRun(header_json, zlib.compress(raw, 9), checksum)


def unpack_run(packed: PackedRun) -> tuple[dict, list[dict]]:
    """Return (run metadata, cards in card_index order). Raises
    PackIntegrityError on an unknown pack_version, an undecodable pack, or a
    checksum mismatch."""
    try:
        head = json.loads(packed.header_json)
    except ValueError as e:
        raise PackIntegrityError(f"unreadable header: {e}") from None
    version = head.get("pack_version") if isinstance(head, dict) else None
    if version != PACK_VERSION:
        raise PackIntegrityError(f"unknown pack_version {version!r}")
    try:
        run, cards = head["run"], _decode(head, zlib.decompress(packed.blob))
    except PackIntegrityError:
        raise
    except Exception as e:
        raise PackIntegrityError(f"undecodable pack: {e!r}") from None
    if _checksum(cards) != packed.checksum:
        raise PackIntegrityError("checksum mismatch")
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


def _checksum(cards: list[dict]) -> str:
    jsonl = "".join(json.dumps(c, sort_keys=True) + "\n" for c in cards)
    return hashlib.sha256(jsonl.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Decoding (mirrors _encode_sections, section by section)
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
