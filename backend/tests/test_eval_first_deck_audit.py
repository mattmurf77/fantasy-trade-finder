"""backend.eval.first_deck_audit, MOD-M1 task 3: the operator's blind audit
sheet. The selection (half near the rule's thresholds, half random, 5 per
format cell where cells allow), its blindness, the near-threshold bands'
edges, scoring (HOLD at 3 operator Ys the rule passed), and the CLI's private,
never-committable output."""
import csv
import json
import os
import stat
from collections import Counter

import pytest

from backend.eval import first_deck_audit as fa
from backend.eval.insult_rule import insult_verdict

QB = ("1QB", "SF")


def _card(i, give, receive):
    """A first-5 card as deck_eval's card_record writes it, from values."""
    v = insult_verdict(give, receive)
    side = lambda tag, vals: [{"id": f"{tag}{i}-{k}", "name": f"Player {tag}{i}-{k}",
                               "position": "WR", "age": 25, "value": x}
                              for k, x in enumerate(vals)]
    return {"deck_position": i % 5 + 1, "trade_hash": f"h{i}", "model_arm": "owner",
            "give": side("g", give), "receive": side("r", receive), **v, "unpriced": []}


def _run(cells=12, cards_per_cell=10, near_per_cell=4):
    """`cells` format cells, one league each; per cell `near_per_cell` cards
    the rule passed near its thresholds, then clean ones, plus one insult."""
    leagues = []
    for c in range(cells):
        fmt = {"qb": QB[c % 2], "tep": bool(c // 2 % 2), "teams": (10, 12, 14)[c // 4 % 3],
               "te_bonus": 0, "scoring_format": "sf_tep"}
        cards = []
        for i in range(cards_per_cell):
            n = c * 100 + i
            if i < near_per_cell:
                cards.append(_card(n, [3000], [3000 - 450 - 10 * i]))     # |Δ| 450.. near 500
            elif i == cards_per_cell - 1:
                cards.append(_card(n, [3000], [1000]))                     # an insult
            else:
                cards.append(_card(n, [2000], [2100]))                     # clean, Δ > 0
        leagues.append({"league_id": f"L{c}", "name": f"Secret League {c}", "format": fmt,
                        "seats": [{"user_id": f"u{c}", "username": f"owner{c}",
                                   "cards": cards}]})
    return {"json_artifact": "feedback-workspace/deck-eval/x.json", "commit": "abc",
            "leagues": leagues}


def test_sixty_cards_five_per_cell_half_near_the_thresholds():
    rows, key = fa.build(_run(), seed=1)
    cards = key["cards"]
    assert len(rows) == 60 and list(cards) == [f"S{i:02d}" for i in range(1, 61)]
    assert set(Counter(v["cell"] for v in cards.values()).values()) == {5}
    picked = Counter(v["selection"] for v in cards.values())
    assert picked == {"near_threshold": 30, "random": 30}
    near = [v for v in cards.values() if v["selection"] == "near_threshold"]
    assert all(not v["insult"] and v["delta"] < 0 for v in near)
    # the nearest to |Δ| 500 first: per cell 480 and 470, then 460 in half the cells
    assert Counter(-v["delta"] for v in near) == {480: 12, 470: 12, 460: 6}


def test_the_sheet_is_blind():
    rows, key = fa.build(_run(), seed=1)
    assert all(tuple(r) == fa.COLUMNS for r in rows)
    text = json.dumps([list(r.values()) for r in rows])          # what the operator reads
    for hidden in ("Secret League", "owner", "owner0", "insult", "delta", "haircut",
                   "near_threshold", "random", "teams", "model_arm", "h1"):
        assert hidden not in text, hidden
    assert {r["format"] for r in rows} == {"1QB, no TEP", "SF, no TEP", "1QB, TEP", "SF, TEP"}
    first = next(r for r in rows if r["card"] == "S01")
    assert "(WR, age 25, " in first["you_give"] and first["give_total"].replace(",", "").isdigit()
    assert first["insulting (Y/N)"] == "" and first["tag (if Y)"] == ""


def test_random_cards_fill_in_when_near_cards_are_scarce_and_cells_are_small():
    """No near cards at all: every card is random. Cells too small for 5
    each: the cap relaxes so the sheet still reaches n where it can."""
    _rows, key = fa.build(_run(near_per_cell=0), seed=2)
    assert Counter(v["selection"] for v in key["cards"].values()) == {"random": 60}
    _rows, key = fa.build(_run(cells=4, cards_per_cell=20), seed=2)
    assert len(key["cards"]) == 60
    _rows, key = fa.build(_run(cells=2, cards_per_cell=10), seed=2)
    assert len(key["cards"]) == 20                       # everything there is


def test_the_selection_is_seeded():
    assert fa.build(_run(), seed=3) == fa.build(_run(), seed=3)
    assert fa.build(_run(), seed=3)[1] != fa.build(_run(), seed=4)[1]


@pytest.mark.parametrize("give, receive, near", [
    ([3000], [2700], 1.0),          # |Δ| 300, the band's low edge (inclusive); haircut 10%
    ([3000], [2300], 1.0),          # |Δ| 700, the high edge, haircut 23.3%: an insult, None
    ([10000], [8800], 1.0),         # |Δ| 1200, haircut 12% (inclusive edge)
    ([10000], [8100], 0.125),       # haircut 19%: near 20%
    ([3000], [2710], None),         # |Δ| 290, haircut 9.7%: in neither band
    ([3000], [3100], None),         # Δ > 0
])
def test_nearness_bands(give, receive, near):
    card = _card(0, give, receive)
    if card["insult"]:
        assert fa.nearness(card) is None
        return
    assert fa.nearness(card) == (None if near is None else pytest.approx(near))


def _marked(rows, marks: dict):
    return [{**r, "insulting (Y/N)": marks.get(r["card"], ("N", ""))[0],
             "tag (if Y)": marks.get(r["card"], ("N", ""))[1]} for r in rows]


def test_three_operator_ys_the_rule_passed_hold_the_result():
    rows, key = fa.build(_run(), seed=1)
    passed = [c for c, v in key["cards"].items() if not v["insult"]]
    flagged = [c for c, v in key["cards"].items() if v["insult"]]
    two = fa.score(_marked(rows, {c: ("Y", "lowball") for c in passed[:2]}), key)
    assert (two["yes_the_rule_passed"], two["result"]) == (2, "RULE_STANDS")
    three = fa.score(_marked(rows, {**{c: ("Y", "filler") for c in passed[:3]},
                                    **{c: ("y", "") for c in flagged[:1]}}), key)
    assert (three["operator_yes"], three["yes_the_rule_passed"], three["result"]) == (4, 3, "HOLD")
    assert [r["card"] for r in three["review"]] == sorted(passed[:3])
    assert three["tags"] == {"filler": 3, "untagged": 1}
    assert three["rule_flagged_operator_no"] == sorted(flagged[1:])


@pytest.mark.parametrize("change", [
    lambda rows: rows[0].update({"insulting (Y/N)": ""}),            # unmarked
    lambda rows: rows[0].update({"insulting (Y/N)": "maybe"}),
    lambda rows: rows[0].update({"insulting (Y/N)": "Y", "tag (if Y)": "rude"}),
    lambda rows: rows.pop(),                                          # a row missing
    lambda rows: rows[0].update({"card": "S99"}),                     # unknown card
])
def test_an_unmarked_or_invalid_sheet_is_refused(change):
    rows, key = fa.build(_run(), seed=1)
    rows = _marked(rows, {})
    change(rows)
    with pytest.raises(ValueError):
        fa.score(rows, key)


def test_the_cli_writes_private_files_and_scores_them(tmp_path, capsys):
    run = tmp_path / "run.json"
    run.write_text(json.dumps(_run()))
    out = tmp_path / "out"
    assert fa.main(["sheet", "--run", str(run), "--out-dir", str(out)]) == 0
    made = json.loads(capsys.readouterr().out)
    assert made["cards"] == 60 and made["by_selection"] == {"near_threshold": 30, "random": 30}
    sheet, key = map(lambda k: __import__("pathlib").Path(made[k]), ("sheet", "key"))
    for path in (sheet, key, __import__("pathlib").Path(made["instructions"])):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o700
    assert "first trade the app ever shows you" in open(made["instructions"]).read()
    with sheet.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    passed = [c for c, v in json.loads(key.read_text())["cards"].items() if not v["insult"]]
    marked = tmp_path / "marked.csv"
    with marked.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fa.COLUMNS)
        writer.writeheader()
        writer.writerows(_marked(rows, {c: ("Y", "other") for c in passed[:3]}))
    assert fa.main(["score", "--sheet", str(marked), "--key", str(key)]) == 1      # HOLD
    capsys.readouterr()
    with marked.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fa.COLUMNS)
        writer.writeheader()
        writer.writerows(_marked(rows, {}))
    assert fa.main(["score", "--sheet", str(marked), "--key", str(key)]) == 0      # stands
    capsys.readouterr()
    rows[0]["insulting (Y/N)"] = ""
    with marked.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fa.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    assert fa.main(["score", "--sheet", str(marked), "--key", str(key)]) == 2      # unmarked


def test_the_cli_never_writes_a_committable_path():
    target = fa._REPO / "docs" / "first-deck-audit-probe"     # tracked tree, not ignored
    try:
        with pytest.raises(SystemExit, match="not gitignored"):
            fa.private_dir(target)
        assert not target.exists()
    finally:
        if target.exists():                                   # only under a sabotage
            target.rmdir()
    assert fa.OUT_DIR == fa._REPO / "feedback-workspace" / "deck-eval"
    fa.private_dir(fa.OUT_DIR)                                # gitignored: accepted


def test_the_audit_bands_bracket_the_rules_thresholds():
    from backend.eval.insult_rule import LOWBALL_HAIRCUT, MATERIALITY
    assert fa.DELTA_BAND == (300, 700) and fa.HAIRCUT_BAND == (0.12, 0.20)
    assert fa.DELTA_BAND[0] < MATERIALITY < fa.DELTA_BAND[1]
    assert fa.HAIRCUT_BAND[1] == LOWBALL_HAIRCUT
