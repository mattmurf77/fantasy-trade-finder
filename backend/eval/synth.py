"""F8 — synthetic logged-data generator (demo + CLI end-to-end check).

Builds a standalone SQLite file containing deck_impressions/deck_outcomes
rows shaped like real F1 output: decks of N cards ordered by final_score,
a position-decaying view curve, and like/propose probabilities that rise
with card quality (so the production ordering is genuinely better than
random — the property the harness must detect).

    python3 -m backend.eval.synth --db /tmp/eval_demo.db --decks 60 --seed 7

Writes ONLY to the given path; refuses to run against an existing file
unless --force. Never points at the product DB.
"""

from __future__ import annotations

import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, insert

from backend.database import deck_impressions_table, deck_outcomes_table, metadata

SHAPES = ("1x1", "2x1", "1x2", "2x2", "3x2")
LANES = ("window", "value", None)


def build_synthetic_db(
    db_url: str,
    n_decks: int = 60,
    cards_per_deck: int = 8,
    seed: int = 7,
    days_span: int = 21,
    thompson_noise: bool = True,
) -> dict:
    """Create the two F1 tables at db_url and fill them. Returns counts."""
    rng = random.Random(seed)
    eng = create_engine(db_url, future=True,
                        connect_args={"check_same_thread": False}
                        if db_url.startswith("sqlite") else {})
    metadata.create_all(eng, tables=[deck_impressions_table, deck_outcomes_table])

    now = datetime.now(timezone.utc)
    imp_rows, out_rows = [], []
    for d in range(n_decks):
        job_id = f"synthjob{d:04d}"
        user = f"user{d % 6}"
        league = "league_synth"
        served = (now - timedelta(days=days_span * (1 - d / max(n_decks, 1)))).isoformat()
        # Quality descends with position (production ordering is real signal).
        for pos in range(cards_per_deck):
            quality = 1.0 - pos / cards_per_deck + rng.uniform(-0.05, 0.05)
            base = 0.5 + quality
            prop = (0.5 + rng.random()) if thompson_noise else 1.0
            features = {
                "shape": rng.choice(SHAPES),
                "basis": "divergence",
                "likes_you": False,
                "lane": rng.choice(LANES),
                "give_positions": ["RB"], "receive_positions": ["WR"],
                "give_value": 1000 + 500 * quality,
                "receive_value": 1050 + 500 * quality,
                "give_value_band": "1000-1500", "receive_value_band": "1000-1500",
                "involves_pick": rng.random() < 0.2,
                "partner_user_id": f"opp{rng.randrange(4)}",
                "surplus_margin": 80 * quality,
                "fairness_score": 0.8 + 0.15 * quality,
                "ranked_player_count": 40, "last_board_update_at": served,
                "user_value_basis": "personal",
            }
            imp_id = uuid.uuid4().hex
            imp_rows.append({
                "impression_id": imp_id, "user_id": user, "league_id": league,
                "deck_job_id": job_id, "card_index": pos,
                "trade_hash": uuid.uuid4().hex[:16],
                "features_json": json.dumps(features),
                "propensity": prop, "base_score": base,
                "final_score": base * prop, "archetype": features["lane"],
                "shape_bucket": features["shape"], "served_at": served,
            })
            # View curve decays with position; labels only for viewed cards.
            p_view = max(0.95 - 0.11 * pos, 0.1)
            if rng.random() < p_view:
                out_rows.append({"impression_id": imp_id, "action": "viewed",
                                 "dwell_ms": rng.randrange(600, 9000),
                                 "acted_at": served})
                p_like = 0.03 + 0.22 * max(quality, 0.0)
                if rng.random() < p_like:
                    out_rows.append({"impression_id": imp_id, "action": "like",
                                     "dwell_ms": rng.randrange(1500, 20000),
                                     "acted_at": served})
                    if rng.random() < 0.25:
                        out_rows.append({"impression_id": imp_id,
                                         "action": "propose", "dwell_ms": None,
                                         "acted_at": served})
                else:
                    out_rows.append({"impression_id": imp_id, "action": "pass",
                                     "dwell_ms": rng.randrange(400, 6000),
                                     "acted_at": served})

    with eng.begin() as conn:
        conn.execute(insert(deck_impressions_table), imp_rows)
        if out_rows:
            conn.execute(insert(deck_outcomes_table), out_rows)
    eng.dispose()
    return {"decks": n_decks, "impressions": len(imp_rows), "outcomes": len(out_rows)}


def main(argv=None) -> int:
    import os
    ap = argparse.ArgumentParser(prog="python3 -m backend.eval.synth")
    ap.add_argument("--db", required=True, help="SQLite file path to create")
    ap.add_argument("--decks", type=int, default=60)
    ap.add_argument("--cards", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--deterministic", action="store_true",
                    help="propensity 1.0 everywhere (no Thompson noise)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    if os.path.exists(args.db) and not args.force:
        ap.error(f"{args.db} exists — pass --force to overwrite")
    if os.path.exists(args.db):
        os.remove(args.db)
    counts = build_synthetic_db(
        f"sqlite:///{args.db}", n_decks=args.decks, cards_per_deck=args.cards,
        seed=args.seed, thompson_noise=not args.deterministic)
    print(f"Wrote {counts['impressions']} impressions / {counts['outcomes']} "
          f"outcomes across {counts['decks']} decks to {args.db}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
