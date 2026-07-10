#!/usr/bin/env python3
"""
Push the synthetic "Lakeview League (Test)" SCAFFOLDING from the local DB to prod
so the disposition seed has a league + members to attach to.

Copies (INSERT-only, idempotent — skips rows that already exist):
  • leagues row  test_league_lakeview
  • league_members (all 12)
  • users          test_user_fp_1 / test_user_fp_2  ONLY

NEVER writes the mattmurf77 user row (his real prod profile is left untouched);
players are global and already in prod.

Usage (from repo root, with DATABASE_URL_PROD in secrets.local.env):
  set -a && . ./secrets.local.env && set +a
  DATABASE_URL_PROD="$DATABASE_URL_PROD" python3 qa/push_lakeview_to_prod.py            # dry-run (default)
  DATABASE_URL_PROD="$DATABASE_URL_PROD" python3 qa/push_lakeview_to_prod.py --execute  # write
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from database import metadata  # noqa: E402  (table definitions only)
from sqlalchemy import create_engine, select, insert, func  # noqa: E402

EXECUTE = "--execute" in sys.argv
LEAGUE = "test_league_lakeview"
MATT = "313560442465169408"
TEST_USERS = ["test_user_fp_1", "test_user_fp_2"]

L = metadata.tables["leagues"]
LM = metadata.tables["league_members"]
U = metadata.tables["users"]

def main():
    prod_url = os.environ.get("DATABASE_URL_PROD", "").replace("postgres://", "postgresql://", 1)
    if not prod_url:
        print("DATABASE_URL_PROD not set"); sys.exit(2)
    local_url = "sqlite:///" + os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data", "trade_finder.db"))
    le = create_engine(local_url, future=True)
    pe = create_engine(prod_url, future=True)
    mode = "EXECUTE (writing)" if EXECUTE else "DRY-RUN (no writes)"
    print(f"mode: {mode}\nlocal: {local_url}\nprod : ...{prod_url[-40:]}\n")

    def cols(tbl, row):
        return {c.name: row._mapping[c.name] for c in tbl.columns if c.name in row._mapping}

    with le.connect() as lc, pe.begin() as pc:
        # ---- leagues row -------------------------------------------------
        lrow = lc.execute(select(L).where(L.c.sleeper_league_id == LEAGUE)).first()
        if not lrow:
            print("✗ local league row not found — abort"); sys.exit(1)
        exists = pc.execute(select(func.count()).select_from(L)
                            .where(L.c.sleeper_league_id == LEAGUE)).scalar()
        if exists:
            print("• league row: already in prod (skip)")
        else:
            print("• league row: WILL CREATE" if not EXECUTE else "• league row: creating")
            if EXECUTE:
                pc.execute(insert(L).values(**cols(L, lrow)))

        # ---- league_members ---------------------------------------------
        members = lc.execute(select(LM).where(LM.c.league_id == LEAGUE)).all()
        m_new = 0
        for m in members:
            here = pc.execute(select(func.count()).select_from(LM)
                              .where((LM.c.league_id == LEAGUE) & (LM.c.user_id == m._mapping["user_id"]))).scalar()
            if here:
                continue
            m_new += 1
            if EXECUTE:
                vals = cols(LM, m); vals.pop("id", None)  # let prod autoincrement
                pc.execute(insert(LM).values(**vals))
        print(f"• league_members: {len(members)} local, {m_new} {'created' if EXECUTE else 'to create'}, {len(members)-m_new} already present")

        # ---- test users only (NEVER mattmurf77) -------------------------
        u_new = 0
        for uid in TEST_USERS:
            urow = lc.execute(select(U).where(U.c.sleeper_user_id == uid)).first()
            if not urow:
                print(f"  - {uid}: not in local (skip)"); continue
            here = pc.execute(select(func.count()).select_from(U)
                              .where(U.c.sleeper_user_id == uid)).scalar()
            if here:
                print(f"  - {uid}: already in prod (skip)"); continue
            u_new += 1
            print(f"  - {uid}: {'CREATE' if not EXECUTE else 'creating'}")
            if EXECUTE:
                pc.execute(insert(U).values(**cols(U, urow)))
        print(f"• test users: {u_new} {'created' if EXECUTE else 'to create'} (mattmurf77 deliberately untouched)")

        if not EXECUTE:
            print("\nDRY-RUN only — nothing written. Re-run with --execute to push.")
        else:
            print("\n✅ scaffolding pushed. Next: run the disposition seed against prod.")

if __name__ == "__main__":
    main()
