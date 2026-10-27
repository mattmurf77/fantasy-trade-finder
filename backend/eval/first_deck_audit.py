"""The operator's blind audit sheet for MOD-M1's first-deck gate (task 3).

models-lead-launch.md §MOD-M1-schedule, "What the operator gets". The gate's
verdict is the D-055 insult rule's (backend/eval/insult_rule.py, run by
scripts/deck_eval.py); this sheet audits the rule itself.

  sheet  From a deck_eval run's JSON, pick N (60) of its first-5 cards,
         PER_CELL (5) per format cell (1QB/SF x TEP x team count) where the
         cells allow. Half are cards the rule passed that sit nearest its
         thresholds (net negative with |Δ| in DELTA_BAND, or a haircut in
         HAIRCUT_BAND), where a rule miss is likeliest; the rest are random
         (all of them random when there aren't enough near cards). Shuffled
         together, they go into a CSV the operator marks (insulting? Y or N,
         and one tag when Y), with an instructions page and a private key
         (sheet card -> its source and the rule's verdict).
         The sheet is blind: it shows what the app would show (the league
         format, each side's players and picks with position, age and FTF
         value, the side totals) and never the rule's verdict, the cell, the
         engine or arm, Δ, or league or team names.
  score  Read the marked CSV against the key: the operator's Y cards, and
         those the rule passed. HOLD_AT (3) or more of those means the rule
         under-counts for this engine, so the result is HOLD for models-lead
         to review with the operator (exit 1); otherwise the rule stands
         (exit 0). An unmarked or invalid row refuses to score (exit 2).

The sheet and key hold league members' rosters, so they're written mode 0600
and only to a directory git ignores (default feedback-workspace/deck-eval/).

    python3 -m backend.eval.first_deck_audit sheet --run <deck_eval_<ts>.json>
    python3 -m backend.eval.first_deck_audit score --sheet <audit_sheet_<ts>.csv> \\
        --key <audit_key_<ts>.json>
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import random
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from backend.eval.insult_rule import LOWBALL_HAIRCUT, MATERIALITY

N_CARDS = 60
PER_CELL = 5
# models-lead's audit bands around the rule's thresholds (MATERIALITY 500,
# LOWBALL_HAIRCUT 20%), as stated: |Δ| 300..700 inclusive, a haircut from 12%
# up to (not including) 20%. Literal, so 12% is exactly in the band.
DELTA_BAND = (300, 700)
HAIRCUT_BAND = (0.12, 0.20)
HOLD_AT = 3
TAGS = ("lowball", "filler", "wrong position", "other")
COLUMNS = ("card", "format", "you_give", "give_total", "you_get", "get_total",
           "insulting (Y/N)", "tag (if Y)")
_REPO = Path(__file__).resolve().parents[2]
OUT_DIR = _REPO / "feedback-workspace" / "deck-eval"

RUBRIC = (
    "You're the owner of this team, and this is the first trade the app ever shows you. "
    "Mark **Y** if you'd feel lowballed or mocked: you give up clearly more than you get, or "
    "you'd hand over a star for filler, or the offer makes no sense for your team. Otherwise "
    "mark **N**. If Y, add one tag (lowball / filler / wrong position / other). Don't overthink "
    "it: first impression, about 30 seconds.")


def cell_of(fmt: dict) -> str:
    """The format cell, as deck_eval's summary names it."""
    return f"{fmt['qb']} / {'TEP' if fmt['tep'] else 'no TEP'} / {fmt['teams']} teams"


def nearness(card: dict) -> float | None:
    """How near a rule-passed card sits to the rule's thresholds (0 = on
    one): the nearer of |Δ| to MATERIALITY across DELTA_BAND and the haircut
    to LOWBALL_HAIRCUT across HAIRCUT_BAND, each scaled to its band. None
    when the rule flagged the card or it's in neither band."""
    if card["insult"] or card["delta"] >= 0:
        return None
    loss, haircut = -card["delta"], card["haircut"]
    near = []
    if DELTA_BAND[0] <= loss <= DELTA_BAND[1]:
        near.append(abs(loss - MATERIALITY) / (DELTA_BAND[1] - MATERIALITY))
    if HAIRCUT_BAND[0] <= haircut < HAIRCUT_BAND[1]:
        near.append((LOWBALL_HAIRCUT - haircut) / (HAIRCUT_BAND[1] - HAIRCUT_BAND[0]))
    return min(near) if near else None


def select(run: dict, *, n: int = N_CARDS, per_cell: int = PER_CELL, seed: int = 0) -> list:
    """[(entry, why)] for the sheet: near-threshold cards first (n // 2,
    nearest first, round-robin over the cells), then random ones to n, each
    capped at `per_cell` per cell; when the cells can't fill n under the cap,
    the rest are random from any cell. An entry is {"league_id", "user_id",
    "cell", "format", "card"}."""
    rng = random.Random(seed)
    cells: dict[str, list] = {}
    for league in run.get("leagues") or []:
        if not league.get("format"):
            continue
        for seat in league.get("seats") or []:
            for card in seat.get("cards") or []:
                cells.setdefault(cell_of(league["format"]), []).append(
                    {"league_id": league["league_id"], "user_id": seat["user_id"],
                     "cell": cell_of(league["format"]), "format": league["format"],
                     "card": card})
    names = sorted(cells)
    taken: list = []
    used: set[int] = set()
    count: Counter = Counter()

    def fill(pools: dict, quota: int, why: str, cap: int | None) -> None:
        while len(taken) < quota:
            progressed = False
            for name in names:
                if len(taken) >= quota:
                    return
                if cap is not None and count[name] >= cap:
                    continue
                pool = pools[name]
                while pool and id(pool[0]) in used:
                    pool.pop(0)
                if pool:
                    entry = pool.pop(0)
                    used.add(id(entry))
                    count[name] += 1
                    taken.append((entry, why))
                    progressed = True
            if not progressed:
                return

    near = {name: sorted((e for e in cells[name] if nearness(e["card"]) is not None),
                         key=lambda e: nearness(e["card"])) for name in names}
    fill(near, n // 2, "near_threshold", per_cell)
    shuffled = {name: rng.sample(cells[name], len(cells[name])) for name in names}
    fill(shuffled, n, "random", per_cell)
    fill(shuffled, n, "random", None)
    rng.shuffle(taken)
    return taken


def _asset(a: dict) -> str:
    bits = [a.get("position") or "?"]
    if a.get("age") is not None:
        bits.append(f"age {a['age']}")
    bits.append(f"{a['value']:,}")
    return f"{a.get('name') or a['id']} ({', '.join(bits)})"


def _format_label(fmt: dict) -> str:
    return f"{fmt['qb']}, {'TEP' if fmt['tep'] else 'no TEP'}"


def build(run: dict, *, n: int = N_CARDS, per_cell: int = PER_CELL,
          seed: int = 0) -> tuple[list[dict], dict]:
    """(sheet rows, key): the blind rows and the private key for them."""
    rows, key = [], {"generated_from": run.get("json_artifact"), "commit": run.get("commit"),
                     "seed": seed, "hold_at": HOLD_AT, "cards": {}}
    for i, (entry, why) in enumerate(select(run, n=n, per_cell=per_cell, seed=seed), 1):
        card, label = entry["card"], f"S{i:02d}"
        rows.append({
            "card": label,
            "format": _format_label(entry["format"]),
            "you_give": "; ".join(_asset(a) for a in card["give"]),
            "give_total": f"{sum(a['value'] for a in card['give']):,}",
            "you_get": "; ".join(_asset(a) for a in card["receive"]),
            "get_total": f"{sum(a['value'] for a in card['receive']):,}",
            "insulting (Y/N)": "",
            "tag (if Y)": "",
        })
        key["cards"][label] = {
            "selection": why, "cell": entry["cell"], "league_id": entry["league_id"],
            "user_id": entry["user_id"], "deck_position": card.get("deck_position"),
            "trade_hash": card.get("trade_hash"), "model_arm": card.get("model_arm"),
            "insult": card["insult"], "i1": card["i1"], "i2": card["i2"],
            "delta": card["delta"], "haircut": card["haircut"],
            "unpriced": card.get("unpriced") or [],
        }
    return rows, key


def instructions(n_cards: int) -> str:
    return "\n".join([
        "# First-deck audit sheet (MOD-M1)",
        "",
        f"{n_cards} trade cards, each the first, second, ... or fifth card a brand-new user "
        "would see. About 30 seconds a card.",
        "",
        "**The question:** " + RUBRIC,
        "",
        "**How to mark it:** open the CSV, put **Y** or **N** in `insulting (Y/N)` on every "
        "row, and for each Y one tag in `tag (if Y)`: " + " / ".join(TAGS) + ". Leave the "
        "other columns as they are, and send the file back as it is.",
        "",
        "Values are FTF consensus values, as the app shows them; each side's total is the "
        "sum of its assets. The sheet is private (it holds league members' rosters): don't "
        "share it beyond the person who returns it.",
    ]) + "\n"


def score(rows: list[dict], key: dict) -> dict:
    """The audit's result (module doc). Raises ValueError on an unmarked or
    invalid row, or a card the key doesn't know."""
    bad, marks = [], {}
    for row in rows:
        label = (row.get("card") or "").strip()
        mark = (row.get("insulting (Y/N)") or "").strip().upper()
        tag = (row.get("tag (if Y)") or "").strip().lower()
        if label not in key["cards"] or mark not in ("Y", "N") or (mark == "Y" and tag
                                                                   and tag not in TAGS):
            bad.append(label or "?")
            continue
        marks[label] = (mark, tag or None)
    missing = sorted(set(key["cards"]) - set(marks) - set(bad))
    if bad or missing:
        raise ValueError(f"unmarked, invalid or unknown rows: {sorted(bad) + missing}")
    yes = sorted(c for c, (m, _) in marks.items() if m == "Y")
    missed = [c for c in yes if not key["cards"][c]["insult"]]
    disagreed = sorted(c for c, (m, _) in marks.items()
                       if m == "N" and key["cards"][c]["insult"])
    result = "HOLD" if len(missed) >= key.get("hold_at", HOLD_AT) else "RULE_STANDS"
    return {
        "cards": len(marks), "operator_yes": len(yes),
        "yes_the_rule_passed": len(missed), "hold_at": key.get("hold_at", HOLD_AT),
        "result": result,
        "review": [{"card": c, **key["cards"][c], "tag": marks[c][1]} for c in missed],
        "rule_flagged_operator_no": disagreed,
        "tags": dict(sorted(Counter(marks[c][1] or "untagged" for c in yes).items())),
        "yes_by_selection": dict(sorted(Counter(key["cards"][c]["selection"] for c in yes).items())),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def private_dir(path: Path) -> Path:
    """`path`, created 0700, refused when it's inside the repo but not
    gitignored (the sheet must never be committable)."""
    path = path.resolve()
    if path == _REPO or _REPO in path.parents:
        probe = path / "probe.csv"
        ignored = subprocess.run(["git", "check-ignore", "-q", str(probe)], cwd=_REPO,
                                 capture_output=True).returncode == 0
        if not ignored:
            raise SystemExit(f"refusing {path}: inside the repo and not gitignored")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _write_private(path: Path, text: str) -> None:
    """Create `path` 0600; refuses an existing one."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
        stream.write(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m backend.eval.first_deck_audit",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sh = sub.add_parser("sheet", help="build the blind sheet, its instructions and the key")
    sh.add_argument("--run", type=Path, required=True, help="a deck_eval run's JSON")
    sh.add_argument("--n", type=int, default=N_CARDS)
    sh.add_argument("--per-cell", type=int, default=PER_CELL)
    sh.add_argument("--seed", type=int, default=0)
    sh.add_argument("--out-dir", type=Path, default=OUT_DIR)
    sc = sub.add_parser("score", help="score a marked sheet against its key")
    sc.add_argument("--sheet", type=Path, required=True)
    sc.add_argument("--key", type=Path, required=True)
    args = ap.parse_args(argv)

    if args.command == "sheet":
        rows, key = build(json.loads(args.run.read_text()), n=args.n,
                          per_cell=args.per_cell, seed=args.seed)
        out = private_dir(args.out_dir)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        paths = {name: out / f"audit_{name}_{ts}.{ext}"
                 for name, ext in (("sheet", "csv"), ("instructions", "md"), ("key", "json"))}
        _write_private(paths["sheet"], buffer.getvalue())
        _write_private(paths["instructions"], instructions(len(rows)))
        _write_private(paths["key"], json.dumps(key, sort_keys=True, indent=1))
        picked = Counter(v["selection"] for v in key["cards"].values())
        print(json.dumps({"cards": len(rows), "by_selection": dict(sorted(picked.items())),
                          "by_cell": dict(sorted(Counter(v["cell"] for v in key["cards"].values())
                                                 .items())),
                          **{k: str(v) for k, v in paths.items()}}, indent=1))
        return 0

    with args.sheet.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    try:
        result = score(rows, json.loads(args.key.read_text()))
    except ValueError as err:
        print(f"first_deck_audit: {err}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1))
    return 1 if result["result"] == "HOLD" else 0


if __name__ == "__main__":
    sys.exit(main())
