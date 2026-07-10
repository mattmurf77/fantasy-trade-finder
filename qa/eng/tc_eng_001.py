#!/usr/bin/env python3
"""
TC-ENG-001 — Trade-engine kill-switch regression (legacy / v2 / v3).

Boots three server instances pinned to each engine via FTF_FLAGS (no repo
flag-file mutation), generates a deck for the same user+league on each, and
checks the safety + stability invariants:

  - SAFETY (all 3 engines): every engine yields a non-empty, VALID deck —
    fairness in [0,1], basis enum, no null ids, give-players on my roster,
    receive-players on the target's roster, unique ids. The kill-switch must
    never degrade to an empty/broken deck.
  - ROUTING: /api/feature-flags reports the intended engine per instance, and
    the engines actually produce different decks (proves the flag routes code).
  - STABILITY (v2 -> v3): v3 must not drop v2's single best trade and should
    keep most of v2's top-N (documented "v3 beats v2 on lower cards, not the
    top"). Reported as an overlap metric; low overlap is flagged, not crashed.

Deterministic-ordering flags (thompson_deck, deck_diversity) are pinned OFF so
decks are comparable. v2/v3 use consensus opponent valuations (comparable);
legacy injects random opponent Elo by design, so it is validity-checked only.

Usage:  python3 qa/eng/tc_eng_001.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import harness as H  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch"
USER = "test_user_fp_1"
LEAGUE = "test_league_lakeview"

# Ordering flags off everywhere so decks are comparable run-to-run.
_BASE_FLAGS = {"trade.thompson_deck": False, "trade.deck_diversity": False}
ENGINES = {
    "legacy": {**_BASE_FLAGS, "trade_engine.v2": False, "trade_engine.v3": False},
    "v2":     {**_BASE_FLAGS, "trade_engine.v2": True,  "trade_engine.v3": False},
    "v3":     {**_BASE_FLAGS, "trade_engine.v2": True,  "trade_engine.v3": True},
}
PORTS = {"legacy": 5111, "v2": 5112, "v3": 5113}

rec = H.CheckRecorder()


def roster_of(db_path: Path, league_id: str, user_id: str) -> list[str]:
    raw = H.db_scalar(db_path, "SELECT roster_data FROM league_members "
                      "WHERE league_id=? AND user_id=?", (league_id, user_id))
    return [str(x) for x in (json.loads(raw) if raw else []) if x]


def card_ids(card: dict, side: str) -> list[str]:
    return [str(p["id"]) for p in card.get(side, [])]


def pair_key(card: dict) -> tuple:
    return (tuple(sorted(card_ids(card, "give"))), tuple(sorted(card_ids(card, "receive"))))


def session_and_generate(base: str, db_path: Path) -> list[dict]:
    api = H.Api(base)
    body = {
        "user_id": USER, "username": USER, "display_name": USER,
        "league_id": LEAGUE, "league_name": "QA ENG League",
        "user_player_ids": roster_of(db_path, LEAGUE, USER),
        "opponent_rosters": [],
    }
    r = api.post("/api/session/init", body)
    if r.status_code != 200:
        return []
    token = r.json().get("token", "")
    api = H.Api(base, token=token)
    r = api.post("/api/trades/generate", {"league_id": LEAGUE})
    snap = r.json()
    job_id = snap.get("job_id", "")
    t0 = time.monotonic()
    while snap.get("status") not in ("complete", "error") and time.monotonic() - t0 < 40:
        time.sleep(0.6)
        rr = api.get(f"/api/trades/status?job_id={job_id}")
        if rr.status_code != 200:
            break
        snap = rr.json()
    return snap.get("cards") or []


def validity_battery(name: str, cards: list[dict], db_path: Path) -> None:
    rec.check(f"{name}:non-empty", len(cards) > 0, f"{len(cards)} cards")
    if not cards:
        return
    my_roster = set(roster_of(db_path, LEAGUE, USER))
    member_rosters = {uid: set(roster_of(db_path, LEAGUE, uid))
                      for (uid,) in H.db_query(db_path,
                      "SELECT user_id FROM league_members WHERE league_id=?", (LEAGUE,))}
    bad_fair = [c for c in cards if not 0.0 <= float(c.get("fairness_score", -1)) <= 1.0]
    bad_basis = [c for c in cards if c.get("basis") not in ("divergence", "consensus", None)]
    bad_null = [c for c in cards if not card_ids(c, "give") or not card_ids(c, "receive")
                or any(not p or p == "None" for p in card_ids(c, "give") + card_ids(c, "receive"))]
    bad_give = [c for c in cards if not set(card_ids(c, "give")) <= my_roster]
    bad_recv = [c for c in cards if not set(card_ids(c, "receive"))
                <= member_rosters.get(str(c.get("target_user_id")), set())]
    dups = len(cards) - len({c.get("trade_id") for c in cards})
    rec.check(f"{name}:fairness-range", not bad_fair, f"{len(bad_fair)} outside [0,1]")
    rec.check(f"{name}:basis-enum", not bad_basis, f"{len(bad_basis)} bad basis")
    rec.check(f"{name}:no-null-ids", not bad_null, f"{len(bad_null)} null/empty id cards")
    rec.check(f"{name}:give-on-roster", not bad_give, f"{len(bad_give)} give players not owned")
    rec.check(f"{name}:recv-on-target", not bad_recv, f"{len(bad_recv)} recv players target lacks")
    rec.check(f"{name}:unique-ids", dups == 0, f"{dups} duplicate ids")


def run_engine(name: str, db_path: Path) -> list[dict]:
    print(f"\nENGINE {name.upper()} — flags {ENGINES[name]}")
    proc, base = H.boot_server(db_path, PORTS[name], SCRATCH / f"server_{name}.log",
                               env_overrides={"FTF_FLAGS": json.dumps(ENGINES[name]),
                                              "CRON_SECRET": None})
    try:
        flags = H.Api(base).get("/api/feature-flags").json().get("flags", {})
        rec.check(f"{name}:flag-v2", flags.get("trade_engine.v2") == ENGINES[name]["trade_engine.v2"],
                  f"trade_engine.v2={flags.get('trade_engine.v2')}")
        rec.check(f"{name}:flag-v3", flags.get("trade_engine.v3") == ENGINES[name]["trade_engine.v3"],
                  f"trade_engine.v3={flags.get('trade_engine.v3')}")
        cards = session_and_generate(base, db_path)
        validity_battery(name, cards, db_path)
        return cards
    finally:
        H.stop_server(proc)


def main() -> int:
    print("TC-ENG-001 — trade-engine kill-switch regression")
    db_path = H.make_scratch_db(SCRATCH, "qa_eng.db")
    decks = {name: run_engine(name, db_path) for name in ("legacy", "v2", "v3")}

    print("\nCROSS-ENGINE — routing + v2/v3 stability")
    # Routing: legacy deck must differ from v2 deck (different valuation model
    # + scoring path). Identical decks would mean the flag didn't route.
    legacy_keys = {pair_key(c) for c in decks["legacy"]}
    v2_keys = [pair_key(c) for c in decks["v2"]]
    v3_keys = [pair_key(c) for c in decks["v3"]]
    if decks["legacy"] and decks["v2"]:
        rec.check("routing:legacy!=v2", set(v2_keys) != legacy_keys,
                  f"legacy {len(legacy_keys)} pairs vs v2 {len(set(v2_keys))} pairs differ")

    # Stability v2 -> v3.
    if decks["v2"] and decks["v3"]:
        v2_top = v2_keys[:10]
        v3_set = set(v3_keys)
        overlap = sum(1 for k in v2_top if k in v3_set)
        rec.info(f"v2 top-10 pairs surviving into v3 deck: {overlap}/{len(v2_top)}")
        rec.check("stability:v3-keeps-v2-best", v2_keys[0] in v3_set,
                  f"v2's #1 trade {'present' if v2_keys[0] in v3_set else 'MISSING'} in v3 deck")
        rec.check("stability:top10-overlap", overlap >= max(1, len(v2_top) // 2),
                  f"{overlap}/{len(v2_top)} of v2 top-10 survive into v3 "
                  f"(threshold {max(1, len(v2_top) // 2)})")

    return rec.summary(SCRATCH / "TC-ENG-001-run.json",
                       meta={"test_case": "TC-ENG-001",
                             "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             "deck_sizes": {k: len(v) for k, v in decks.items()}})


if __name__ == "__main__":
    sys.exit(main())
