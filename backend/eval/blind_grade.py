"""Blind-grade sheet export and import for trade card sets.

Implements docs/plans/value-core-engine/lld.md section 8.4. The operator grades
shuffled cards 1-5 ("would I send this?") with optional reason tags, without
seeing which engine variant produced each card: the sheet carries neutral ids
(c01, c02, ...) and no variant name anywhere; the private key maps ids back.

CardSet JSON: {"variant": str, "source": "value_core_bench" | "served",
               "cards": [{"league": str, "seat": str, "partner": str,
                          "give": [{"id","name","position","market"}],
                          "receive": [{"id","name","position","market"}],
                          "reasons": [str]}],
               "skipped_no_row": int,      # served sets only
               "leagues_without_deck": [str],   # served: no gradeable Trades deck in the lookback
               "leagues_with_no_cards": [str],  # served: a deck found, 0 gradeable cards
               "skipped_decks_by_reason": {str: int}}  # served: ungradeable decks seen

``served_card_set`` is the only production touch: a read-only read of the
incumbent's served decks, asserting ``transaction_read_only = on`` first.
It reads them through eval's loader (backend.eval.data.load_decks), so it sees
each deck as eval does (models-lead B5): Trades decks only (a deck the loader
marks CALIBRATION_REFRESH, by CALIBRATION_REFRESH_SOURCE, is skipped, as is
one whose evidence contradicts itself),
never-delivered withdrawn cards removed, not-yet-paged first30 rows kept, and
the top N taken by displayed position.
Every file written is 0600 inside a fresh directory (or O_EXCL), never overwritten.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

TAGS = ("same_guy_again", "too_small", "never_accept", "wrong_my_window",
        "wrong_their_window", "junk_filler", "overpay")
SHEET_COLUMNS = ("card_id", "league", "you_give", "you_get", "give_value", "get_value",
                 "reasons", "grade", "tags", "note")
TARGET_MEAN = 4.0   # PRD section 6
_GRADE = re.compile(r"[1-5]")
# How far back served_card_set looks for a league's latest Trades deck.
SERVED_LOOKBACK = timedelta(days=30)


def _side_text(assets: Sequence[Mapping]) -> str:
    return " · ".join(f"{a['name']} ({a['position']})" for a in assets)


def _side_value(assets: Sequence[Mapping]) -> str:
    markets = [a.get("market") for a in assets]
    if not markets or any(m is None for m in markets):
        return ""
    return str(int(round(sum(float(m) for m in markets))))


def _trade_key(card: Mapping) -> tuple:
    return (card["league"], card["seat"], card["partner"],
            tuple(sorted(a["id"] for a in card["give"])),
            tuple(sorted(a["id"] for a in card["receive"])))


def export(card_sets: Sequence[Mapping], *, per_variant: int = 40, seed: int = 7,
           output_dir: Path, show_reasons: bool = False) -> dict:
    """Sample `per_variant` cards per set, merge identical trades across variants, shuffle,
    and write grade-sheet.csv plus key.private.json into a NEW directory (files 0600)."""
    from backend.eval.value_core_bench import fresh_dir, write_private_json, write_private_text

    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists; export never overwrites")
    rng = random.Random(seed)
    merged: dict[tuple, dict] = {}
    per_variant_counts: dict[str, int] = {}
    for card_set in card_sets:
        variant = str(card_set["variant"])
        cards = list(card_set["cards"])
        picked = cards if len(cards) <= per_variant else rng.sample(cards, per_variant)
        per_variant_counts[variant] = per_variant_counts.get(variant, 0) + len(picked)
        for card in picked:
            row = merged.setdefault(_trade_key(card), {"card": card, "variants": set()})
            row["variants"].add(variant)
    order = list(merged)
    rng.shuffle(order)

    width = max(2, len(str(len(order))))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(SHEET_COLUMNS)
    key: dict[str, dict] = {}
    for i, trade_key in enumerate(order, 1):
        card_id = f"c{i:0{width}d}"
        card = merged[trade_key]["card"]
        writer.writerow([card_id, card["league"], _side_text(card["give"]),
                         _side_text(card["receive"]), _side_value(card["give"]),
                         _side_value(card["receive"]),
                         "; ".join(card.get("reasons") or []) if show_reasons else "",
                         "", "", ""])
        key[card_id] = {"variants": sorted(merged[trade_key]["variants"]),
                        "seat": card["seat"], "league": card["league"]}
    fresh_dir(output_dir)
    write_private_text(output_dir / "grade-sheet.csv", buffer.getvalue())
    write_private_json(output_dir / "key.private.json", key)
    return {"rows": len(order), "per_variant": per_variant_counts}


def _score(graded: Sequence[tuple[int, list[str]]]) -> dict:
    n = len(graded)
    tags = Counter(t for _, row_tags in graded for t in row_tags)
    return {"n": n,
            "mean": round(sum(g for g, _ in graded) / n, 4) if n else None,
            "share_ge_4": round(sum(1 for g, _ in graded if g >= 4) / n, 4) if n else None,
            "tag_counts": dict(sorted(tags.items()))}


def import_grades(sheet: Path, key: Path) -> dict:
    """Validate and score a graded sheet against its private key. Blank grade = ungraded.
    Returns {"variants": {name: {n, mean, share_ge_4, tag_counts}}, "overall", "target_mean"}
    and writes summary.json next to the sheet (0600, never overwritten)."""
    from backend.eval.value_core_bench import write_private_json

    sheet, key = Path(sheet), Path(key)
    mapping = json.loads(key.read_text())
    per_variant: dict[str, list[tuple[int, list[str]]]] = {}
    overall: list[tuple[int, list[str]]] = []
    with sheet.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            card_id = (row.get("card_id") or "").strip()
            if card_id not in mapping:
                raise ValueError(f"card {card_id!r} is not in the key")
            tags = [t.strip() for t in (row.get("tags") or "").split(";") if t.strip()]
            for tag in tags:
                if tag not in TAGS:
                    raise ValueError(f"card {card_id}: unknown tag {tag!r} "
                                     f"(allowed: {', '.join(TAGS)})")
            grade = (row.get("grade") or "").strip()
            if not grade:
                continue
            if not _GRADE.fullmatch(grade):
                raise ValueError(f"card {card_id}: grade {grade!r} is not an integer 1-5")
            graded = (int(grade), tags)
            overall.append(graded)
            for variant in mapping[card_id]["variants"]:
                per_variant.setdefault(variant, []).append(graded)
    summary = {"variants": {v: _score(g) for v, g in sorted(per_variant.items())},
               "overall": _score(overall), "target_mean": TARGET_MEAN}
    write_private_json(sheet.parent / "summary.json", summary)
    return summary


def _valuation_markets(valuation: dict) -> dict:
    """asset id -> market from a served valuation_json, in either shape it is
    written in: the value core's evidence (assets: [{id, market}]) or the
    personal-market snapshot (assets: {give: [...], receive: [...]}, each row
    {id, market_value}). {} when it records no per-asset market."""
    assets = (valuation or {}).get("assets")
    if isinstance(assets, dict):          # the personal-market snapshot
        rows, key = [*(assets.get("give") or []), *(assets.get("receive") or [])], "market_value"
    elif isinstance(assets, list):        # the value core's evidence
        rows, key = assets, "market"
    else:
        return {}
    return {str(r["id"]): r.get(key) for r in rows if isinstance(r, dict) and "id" in r}


def served_card_set(*, secrets: Path, league_ids: Sequence[str], user_id: str,
                    top: int = 30, variant: str = "incumbent") -> dict:
    """The incumbent's latest served Trades deck per league as a CardSet (prod, read-only).

    Per league (models-lead B5): eval's loader (backend.eval.data.load_decks)
    reads the user's decks served within SERVED_LOOKBACK, and the latest by
    served_at whose exclusion is not CALIBRATION_REFRESH, PACK_INTEGRITY or
    WITHDRAWAL_CONFLICT is taken (Calibration's refresh decks are never shown
    in Trades; the other two contradict their own evidence and keep their
    withdrawn cards; any other exclusion, in_flight above all, still counts:
    the latest Trades deck is usually live). The
    loader has already removed its never-delivered withdrawn cards
    (deck_card_withdrawals.served_before = 0: I-1 drops and disposition cuts)
    and kept its first30 rows whether delivered yet or not. The `top` kept
    non-ghost cards by displayed position (LoggedCard.position) are chosen,
    then assets_json, valuation_json and features_json are read for exactly
    those impression_ids. A chosen card without a full row (a packed-only
    card, or a row without assets_json) is skipped and counted in
    "skipped_no_row", never replaced by a later card. A league with no such
    deck is named in "leagues_without_deck", and one whose deck yields no
    gradeable card (every chosen card skipped, or none to choose) in
    "leagues_with_no_cards": neither is a silent 0 cards.

    Every read runs on the engine prod_analytics._connect_readonly returns,
    whose connections all open with default_transaction_read_only=on; the
    SHOW check below confirms it before the first read."""
    from sqlalchemy import bindparam, text

    from backend.eval import data as eval_data
    # Never graded: Calibration's refresh (not a Trades deck), and a deck whose
    # evidence contradicts itself (pack_integrity, withdrawal_conflict). The
    # loader stops before removing such a deck's never-delivered withdrawals,
    # so its top N could hold cards nobody saw.
    ungradeable = {eval_data.CALIBRATION_REFRESH, eval_data.PACK_INTEGRITY,
                   eval_data.WITHDRAWAL_CONFLICT}
    from backend.tools import prod_analytics

    # load_decks drops an empty user or league filter: never read beyond the seat.
    if not str(user_id) or not all(str(league_id) for league_id in league_ids):
        raise ValueError("a user id and non-empty league ids are required")
    prod_analytics.SECRETS = Path(secrets)
    engine = prod_analytics._connect_readonly(prod_analytics._load_prod_url(), 15000)
    since = (datetime.now(timezone.utc) - SERVED_LOOKBACK).isoformat()
    cards: list[dict] = []
    skipped = 0
    without_deck: list[str] = []
    no_cards: list[str] = []
    # models-lead C5: every ungradeable deck in the lookback is counted by reason,
    # so a skip is never silent (pack_integrity / withdrawal_conflict are also
    # G1 / G8 signals).
    skipped_decks = dict.fromkeys(sorted(ungradeable), 0)
    try:
        with engine.connect() as conn:
            if conn.execute(text("SHOW transaction_read_only")).scalar() != "on":
                raise ValueError("read-only connection required: transaction_read_only is not on")
            for league_id in league_ids:
                loaded = eval_data.load_decks(engine=engine, since=since,
                                              user_id=str(user_id), league_id=str(league_id))
                for d in loaded:
                    if d.exclusion in ungradeable:
                        skipped_decks[d.exclusion] += 1
                decks = [d for d in loaded if d.exclusion not in ungradeable]
                if not decks:     # named, never a silent 0 cards (runbook §Blind grade)
                    without_deck.append(str(league_id))
                    continue
                deck = max(decks, key=lambda d: (d.served_at, d.deck_job_id))
                chosen = sorted((c for c in deck.cards if not c.is_ghost),
                                key=lambda c: c.position)[:top]
                impression_ids = [c.impression_id for c in chosen]
                full = {}
                for i in range(0, len(impression_ids), 500):   # chunked like the loader's IN()
                    sql = text("SELECT impression_id, assets_json, features_json, valuation_json "
                               "FROM deck_impressions WHERE impression_id IN :ids"
                               ).bindparams(bindparam("ids", expanding=True))
                    full.update((r["impression_id"], r) for r in
                                conn.execute(sql, {"ids": impression_ids[i:i + 500]}).mappings())
                name = conn.execute(text("SELECT name FROM leagues WHERE sleeper_league_id = :lid"),
                                    {"lid": league_id}).scalar() or str(league_id)
                parsed = []
                for impression_id in impression_ids:
                    r = full.get(impression_id)
                    if r is None or not r["assets_json"]:
                        skipped += 1
                        continue
                    assets = json.loads(r["assets_json"])
                    valuation = json.loads(r["valuation_json"]) if r["valuation_json"] else {}
                    markets = _valuation_markets(valuation)
                    features = json.loads(r["features_json"]) if r["features_json"] else {}
                    parsed.append(([str(i) for i in assets.get("give") or []],
                                   [str(i) for i in assets.get("receive") or []],
                                   features.get("partner_user_id"), markets))
                if not parsed:    # a deck, but nothing to grade: named too
                    no_cards.append(str(league_id))
                ids = sorted({a for give, receive, _, _ in parsed for a in give + receive})
                players = {}
                if ids:
                    sql = text("SELECT player_id, full_name, position FROM players "
                               "WHERE player_id IN :ids").bindparams(bindparam("ids", expanding=True))
                    players = {str(r["player_id"]): r
                               for r in conn.execute(sql, {"ids": ids}).mappings()}

                def side(asset_ids, markets):
                    return [{"id": a,
                             "name": (players.get(a) or {}).get("full_name") or a,
                             "position": (players.get(a) or {}).get("position") or "PICK",
                             "market": markets.get(a)} for a in asset_ids]
                cards.extend({"league": name, "seat": str(user_id), "partner": str(partner or ""),
                              "give": side(give, markets), "receive": side(receive, markets),
                              "reasons": []}
                             for give, receive, partner, markets in parsed)
    finally:
        engine.dispose()
    return {"variant": variant, "source": "served", "cards": cards, "skipped_no_row": skipped,
            "leagues_without_deck": without_deck, "leagues_with_no_cards": no_cards,
            "skipped_decks_by_reason": skipped_decks}


def main(argv: Sequence[str] | None = None) -> int:
    from backend.eval.value_core_bench import write_private_json

    parser = argparse.ArgumentParser(prog="python -m backend.eval.blind_grade",
                                     description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_served = sub.add_parser("served", help="incumbent served cards from prod (read-only)")
    p_served.add_argument("--secrets", type=Path, required=True)
    p_served.add_argument("--user", required=True)
    p_served.add_argument("--league", action="append", required=True)
    p_served.add_argument("--output", type=Path, required=True)
    p_served.add_argument("--top", type=int, default=30)
    p_served.add_argument("--variant", default="incumbent")
    p_export = sub.add_parser("export", help="write a blind grade sheet")
    p_export.add_argument("--cards", type=Path, action="append", required=True)
    p_export.add_argument("--per-variant", type=int, default=40)
    p_export.add_argument("--seed", type=int, default=7)
    p_export.add_argument("--output", type=Path, required=True)
    p_export.add_argument("--show-reasons", action="store_true")
    p_import = sub.add_parser("import", help="score a graded sheet")
    p_import.add_argument("--sheet", type=Path, required=True)
    p_import.add_argument("--key", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "served":
        if args.output.exists():
            raise SystemExit(f"{args.output} already exists; served never overwrites")
        try:
            card_set = served_card_set(secrets=args.secrets, league_ids=args.league,
                                       user_id=args.user, top=args.top, variant=args.variant)
        except ValueError as exc:
            raise SystemExit(f"served failed: {exc}") from None
        except Exception as exc:     # a driver error can echo query parameters: name the type only
            raise SystemExit(f"served failed: {type(exc).__name__}") from None
        write_private_json(args.output, card_set)
        print(json.dumps({"cards": len(card_set["cards"]), "leagues": len(args.league),
                          "skipped_no_row": card_set["skipped_no_row"],
                          "leagues_without_deck": card_set["leagues_without_deck"],
                          "leagues_with_no_cards": card_set["leagues_with_no_cards"],
                          "skipped_decks_by_reason": card_set["skipped_decks_by_reason"]}))
    elif args.command == "export":
        card_sets = [json.loads(path.read_text()) for path in args.cards]
        print(json.dumps(export(card_sets, per_variant=args.per_variant, seed=args.seed,
                                output_dir=args.output, show_reasons=args.show_reasons),
                         sort_keys=True))
    else:
        print(json.dumps(import_grades(args.sheet, args.key), sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
