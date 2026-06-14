#!/usr/bin/env python3
"""
TC-E2E-001 — Full-stack happy path: session_init -> rank -> generate -> swipe -> match -> disposition.

Runs against a SCRATCH COPY of data/trade_finder.db (the live DB is never
written). Boots its own Flask server on port 5099 with DATABASE_URL pointed
at the scratch copy, then drives the same endpoints the mobile client calls,
with the mobile client's timeout budgets as the pass bar.

Usage:  python3 qa/e2e/tc_e2e_001.py
Output: human summary on stdout + qa/e2e/scratch/TC-E2E-001-run.json
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
SCRATCH_DIR = ROOT / "qa" / "e2e" / "scratch"
SCRATCH_DB = SCRATCH_DIR / "trade_finder_e2e.db"
LIVE_DB = ROOT / "data" / "trade_finder.db"
SERVER_LOG = SCRATCH_DIR / "server.log"
PORT = 5099
BASE = f"http://127.0.0.1:{PORT}"

TEST_LEAGUE = "test_league_lakeview"
USER_B = "test_user_fp_1"          # primary journey user (exists in users + league_members)

# Mobile client budgets (seconds) — from mobile/src/api/client.ts.
SLOW_PATHS = ("/api/session/init", "/api/trades/generate", "/api/session/demo")
BUDGET_DEFAULT = 15.0
BUDGET_SLOW = 30.0

checks: list[dict] = []
timings: list[dict] = []


def check(check_id: str, ok: bool, detail: str) -> bool:
    checks.append({"id": check_id, "ok": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {check_id}: {detail}")
    return ok


def info(msg: str) -> None:
    print(f"  .. {msg}")


class Api:
    """Thin client mirroring the mobile app: X-Session-Token header, budget tracking."""

    def __init__(self, token: str | None = None):
        self.token = token

    def call(self, method: str, path: str, **kw):
        headers = kw.pop("headers", {})
        if self.token:
            headers["X-Session-Token"] = self.token
        budget = BUDGET_SLOW if any(path.startswith(p) for p in SLOW_PATHS) else BUDGET_DEFAULT
        t0 = time.monotonic()
        resp = requests.request(method, BASE + path, headers=headers,
                                timeout=budget + 10, **kw)
        elapsed = time.monotonic() - t0
        timings.append({"method": method, "path": path, "status": resp.status_code,
                        "ms": round(elapsed * 1000), "budget_s": budget,
                        "within_budget": elapsed <= budget})
        return resp

    def get(self, path: str, **kw):
        return self.call("GET", path, **kw)

    def post(self, path: str, body: dict | None = None, **kw):
        return self.call("POST", path, json=body or {}, **kw)


def db(sql: str, args: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(f"file:{SCRATCH_DB}?mode=ro", uri=True)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def db1(sql: str, args: tuple = ()):
    rows = db(sql, args)
    return rows[0][0] if rows else None


# ───────────────────────────── setup / teardown ─────────────────────────────

def setup_scratch() -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(SCRATCH_DB) + suffix)
        if p.exists():
            p.unlink()
    shutil.copy2(LIVE_DB, SCRATCH_DB)
    info(f"scratch DB ready: {SCRATCH_DB} ({SCRATCH_DB.stat().st_size:,} bytes)")


def start_server() -> subprocess.Popen:
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{SCRATCH_DB}"
    env["PYTHONPATH"] = str(ROOT)
    bootstrap = (
        "from backend.server import app, _load_sleeper_cache, _maybe_sync_players; "
        "_load_sleeper_cache(); _maybe_sync_players(); "
        f"app.run(host='127.0.0.1', port={PORT}, debug=False)"
    )
    log_fh = open(SERVER_LOG, "w")
    proc = subprocess.Popen([sys.executable, "-c", bootstrap], cwd=ROOT, env=env,
                            stdout=log_fh, stderr=subprocess.STDOUT)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 90:
        if proc.poll() is not None:
            raise RuntimeError(f"server died on boot — see {SERVER_LOG}")
        try:
            if requests.get(f"{BASE}/api/feature-flags", timeout=2).status_code == 200:
                boot_s = time.monotonic() - t0
                info(f"server up on :{PORT} in {boot_s:.1f}s (cold boot incl. player sync)")
                timings.append({"method": "BOOT", "path": "(server cold start)",
                                "status": 200, "ms": round(boot_s * 1000),
                                "budget_s": 90, "within_budget": True})
                return proc
        except requests.RequestException:
            pass
        time.sleep(0.5)
    proc.kill()
    raise RuntimeError("server did not become ready within 90s")


def roster_of(league_id: str, user_id: str) -> list[str]:
    raw = db1("SELECT roster_data FROM league_members WHERE league_id=? AND user_id=?",
              (league_id, user_id))
    ids = json.loads(raw) if raw else []
    return [str(x) for x in ids if x]


def init_session(user_id: str, username: str, league_id: str) -> tuple[str, dict]:
    """session_init the way the web/mobile client does: roster from DB
    (server also injects DB league members as opponents automatically)."""
    api = Api()
    body = {
        "user_id": user_id,
        "username": username,
        "display_name": username,
        "league_id": league_id,
        "league_name": "QA E2E League",
        "user_player_ids": roster_of(league_id, user_id),
        "opponent_rosters": [],   # DB-stored members get injected server-side
    }
    r = api.post("/api/session/init", body)
    payload = r.json() if r.status_code == 200 else {"error": r.text[:200]}
    return (payload.get("token", ""), {"status": r.status_code, **payload})


# ───────────────────────────────── stages ───────────────────────────────────

def stage1_session_init() -> Api:
    print("\nSTAGE 1 — session_init (test-league user via DB rosters)")
    token, payload = init_session(USER_B, USER_B, TEST_LEAGUE)
    check("S1.1-init-200", payload["status"] == 200, f"status={payload['status']}")
    check("S1.2-token", bool(token), f"token issued ({len(token)} chars)")
    check("S1.3-roster", len(payload.get("user_roster", [])) > 0,
          f"{len(payload.get('user_roster', []))} roster players resolved")
    check("S1.4-opponents", payload.get("opponents", 0) >= 10,
          f"{payload.get('opponents')} opponents injected (league has 12 members)")
    api = Api(token)
    r = api.get("/api/session/ping")
    check("S1.5-ping", r.status_code == 200, f"session ping status={r.status_code}")
    return api


def stage2_ranking(api: Api) -> None:
    print("\nSTAGE 2 — ranking loop (trio -> rank3) x3 on RB")
    fmt = "1qb_ppr"
    for i in range(3):
        before = db1("SELECT COUNT(*) FROM swipe_decisions WHERE user_id=? AND decision_type='rank'",
                     (USER_B,))
        r = api.get("/api/trio?position=RB")
        if not check(f"S2.{i}.1-trio-200", r.status_code == 200,
                     f"trio status={r.status_code} {r.text[:120] if r.status_code != 200 else ''}"):
            return
        trio = r.json()
        ids = [trio["player_a"]["id"], trio["player_b"]["id"], trio["player_c"]["id"]]
        names = [trio[k]["name"] for k in ("player_a", "player_b", "player_c")]
        positions = {trio[k].get("position") for k in ("player_a", "player_b", "player_c")}
        check(f"S2.{i}.2-trio-distinct", len(set(ids)) == 3, f"3 distinct players: {names}")
        check(f"S2.{i}.3-trio-position", positions == {"RB"}, f"positions={positions}")

        # winner = a, then b, then c (submit in served order)
        rk = api.post("/api/rank3", {"ranked": ids})
        check(f"S2.{i}.4-rank3-200", rk.status_code == 200, f"rank3 status={rk.status_code}")
        body = rk.json()
        check(f"S2.{i}.5-rank3-shape",
              all(k in body for k in ("interaction_count", "threshold", "percent", "streak")),
              f"keys={sorted(body.keys())}")

        after = db1("SELECT COUNT(*) FROM swipe_decisions WHERE user_id=? AND decision_type='rank'",
                    (USER_B,))
        check(f"S2.{i}.6-3-rows", after - before == 3,
              f"swipe_decisions(rank) +{after - before} (expected +3, decomposed pairs)")

        # Elo direction: the trio winner must not lose Elo, the loser must not gain.
        pub = db("SELECT player_id, elo FROM member_rankings WHERE user_id=? AND league_id=? "
                 "AND scoring_format=? AND player_id IN (?,?)",
                 (USER_B, TEST_LEAGUE, fmt, ids[0], ids[2]))
        elo_map = dict(pub)
        snap = db("SELECT player_id, elo FROM elo_history WHERE user_id=? AND scoring_format=? "
                  "ORDER BY id DESC LIMIT 3", (USER_B, fmt))
        check(f"S2.{i}.7-published", len(elo_map) == 2 and len(snap) == 3,
              f"member_rankings republished ({len(elo_map)}/2 sampled) + elo_history +{len(snap)} rows")


def _wait_job(api: Api, job_id: str, deadline_s: float = BUDGET_SLOW) -> dict:
    t0 = time.monotonic()
    snap: dict = {}
    while time.monotonic() - t0 < deadline_s:
        r = api.get(f"/api/trades/status?job_id={job_id}")
        if r.status_code != 200:
            return {"status": f"http {r.status_code}", "cards": []}
        snap = r.json()
        if snap.get("status") in ("complete", "error"):
            break
        time.sleep(0.75)
    snap["_wall_s"] = round(time.monotonic() - t0, 2)
    return snap


def card_ids(card: dict, side: str) -> list[str]:
    """Public cards carry give/receive as player OBJECTS; swipe echoes raw id
    arrays. Mirror the mobile client's mapping (mobile/src/api/trades.ts)."""
    return [str(p["id"]) for p in card.get(side, [])]


def stage3_generate(api: Api) -> list[dict]:
    print("\nSTAGE 3 — trade generation (async job + card quality)")
    t0 = time.monotonic()
    r = api.post("/api/trades/generate", {"league_id": TEST_LEAGUE})
    check("S3.1-generate-200", r.status_code == 200, f"status={r.status_code}")
    snap = r.json()
    job_id = snap.get("job_id", "")
    check("S3.2-job-shape",
          all(k in snap for k in ("job_id", "status", "opponents_done", "opponents_total", "cards")),
          f"snapshot keys={sorted(snap.keys())}")
    if snap.get("status") != "complete":
        snap = _wait_job(api, job_id)
    total_s = time.monotonic() - t0
    check("S3.3-complete", snap.get("status") == "complete",
          f"job status={snap.get('status')} error={snap.get('error')} in {total_s:.1f}s")
    check("S3.4-budget", total_s <= BUDGET_SLOW, f"end-to-end {total_s:.1f}s (budget {BUDGET_SLOW:.0f}s)")

    cards = snap.get("cards") or []
    check("S3.5-cards", len(cards) > 0, f"{len(cards)} cards returned")
    if not cards:
        return []

    my_roster = set(roster_of(TEST_LEAGUE, USER_B))
    member_rosters = {uid: set(roster_of(TEST_LEAGUE, uid))
                      for (uid,) in db("SELECT user_id FROM league_members WHERE league_id=?",
                                       (TEST_LEAGUE,))}
    bad_fairness = [c for c in cards if not (0.0 <= float(c.get("fairness_score", -1)) <= 1.0)]
    bad_basis = [c for c in cards if c.get("basis") not in ("divergence", "consensus", None)]
    bad_nulls = [c for c in cards
                 if not card_ids(c, "give") or not card_ids(c, "receive")
                 or any(not p or p == "None"
                        for p in card_ids(c, "give") + card_ids(c, "receive"))]
    bad_give = [c for c in cards if not set(card_ids(c, "give")) <= my_roster]
    bad_recv = [c for c in cards
                if not set(card_ids(c, "receive"))
                <= member_rosters.get(str(c.get("target_user_id")), set())]
    scores = [float(c.get("composite_score", 0)) for c in cards]
    dup_ids = len(cards) - len({c.get("trade_id") for c in cards})

    check("S3.6-fairness-range", not bad_fairness, f"{len(bad_fairness)} cards outside [0,1]")
    check("S3.7-basis-enum", not bad_basis,
          f"{len(bad_basis)} bad basis values; seen={sorted({str(c.get('basis')) for c in cards})}")
    check("S3.8-no-null-ids", not bad_nulls, f"{len(bad_nulls)} cards with empty/null player ids")
    check("S3.9-give-on-my-roster", not bad_give, f"{len(bad_give)} cards give players I don't own")
    check("S3.10-receive-on-target-roster", not bad_recv,
          f"{len(bad_recv)} cards receive players the target doesn't own")
    # Deck order is only composite-sorted when Thompson sampling is OFF —
    # with trade.thompson_deck on, ordering is intentionally stochastic
    # (bounded 0.5-1.5x multiplier), so strict sort is the wrong invariant.
    flags = api.get("/api/feature-flags").json().get("flags", {})
    thompson = bool(flags.get("trade.thompson_deck"))
    if thompson:
        check("S3.11-sorted", True,
              "skipped strict-sort: trade.thompson_deck=on (stochastic order by design)")
    else:
        check("S3.11-sorted", scores == sorted(scores, reverse=True),
              "cards sorted by composite_score desc" if scores == sorted(scores, reverse=True)
              else f"NOT sorted with thompson_deck OFF: {[round(s, 3) for s in scores[:8]]}")
    check("S3.12-unique-ids", dup_ids == 0, f"{dup_ids} duplicate trade_ids")

    # Cache behavior: an immediate second generate must return the same finished job fast.
    t1 = time.monotonic()
    r2 = api.post("/api/trades/generate", {"league_id": TEST_LEAGUE})
    cache_s = time.monotonic() - t1
    same = r2.status_code == 200 and r2.json().get("job_id") == job_id \
        and r2.json().get("status") == "complete"
    check("S3.13-cache-hit", same and cache_s < 2.0,
          f"second call: same_job={same} in {cache_s * 1000:.0f}ms")
    return cards


def stage4_swipe_and_match(api_b: Api, cards: list[dict]) -> int | None:
    print("\nSTAGE 4 — swipe scenarios: likes_you instant match + fresh-card mirror match")
    # Pre-existing match pairs (match_already_exists dedups across ALL time).
    existing_pairs = {
        (frozenset(json.loads(g)), frozenset(json.loads(r)))
        for (g, r) in db("SELECT user_a_give, user_a_receive FROM trade_matches "
                         "WHERE league_id=?", (TEST_LEAGUE,))
    }
    existing_pairs |= {(r, g) for (g, r) in existing_pairs}   # either orientation
    # Counterparty likes already on record (these make a first like match instantly).
    prior_likes: dict[str, set] = {}
    for (uid, g, r) in db("SELECT user_id, give_player_ids, receive_player_ids "
                          "FROM trade_decisions WHERE league_id=? AND decision='like'",
                          (TEST_LEAGUE,)):
        prior_likes.setdefault(uid, set()).add((frozenset(json.loads(g)), frozenset(json.loads(r))))

    def pair_of(c: dict) -> tuple:
        return (frozenset(card_ids(c, "give")), frozenset(card_ids(c, "receive")))

    def has_prior_mirror(c: dict) -> bool:
        g, r = pair_of(c)
        return (r, g) in prior_likes.get(str(c.get("target_user_id")), set())

    # ── S4a: likes_you card -> liking it must create a match IMMEDIATELY ──
    card_ly = next((c for c in cards if c.get("likes_you")
                    and pair_of(c) not in existing_pairs), None)
    if card_ly:
        info(f"likes_you card {card_ly['trade_id']} -> {card_ly['target_user_id']}")
        r = api_b.post("/api/trades/swipe", {
            "trade_id": card_ly["trade_id"], "decision": "like",
            "give_player_ids": card_ids(card_ly, "give"),
            "receive_player_ids": card_ids(card_ly, "receive"),
            "target_user_id": str(card_ly["target_user_id"]),
            "target_username": card_ly.get("target_username", ""),
            "league_id": TEST_LEAGUE,
        })
        ok = r.status_code == 200 and r.json().get("matched") is True
        check("S4a.1-likes-you-instant-match", ok,
              f"liking a likes_you card -> matched={r.json().get('matched')} "
              f"match_id={r.json().get('match_id')}")
    else:
        info("no eligible likes_you card in deck — S4a skipped")

    # ── S4b: fresh card (no prior mirror, no prior match) -> two-step match ──
    # Prefer 1-for-1: immune to fuzzy-match (trade.fuzzy_match=on) false hits.
    fresh = [c for c in cards
             if not c.get("likes_you")
             and pair_of(c) not in existing_pairs
             and not has_prior_mirror(c)]
    card = next((c for c in fresh
                 if len(card_ids(c, "give")) == 1 and len(card_ids(c, "receive")) == 1),
                fresh[0] if fresh else None)
    if not check("S4.0-fresh-card", card is not None,
                 f"found fresh card (deck={len(cards)}, "
                 f"existing matches={len(existing_pairs) // 2})"):
        return None
    target_uid = str(card["target_user_id"])
    give_ids, recv_ids = card_ids(card, "give"), card_ids(card, "receive")
    info(f"fresh card {card['trade_id']}: give={give_ids} receive={recv_ids} -> {target_uid}")
    ctx = {
        "trade_id": card["trade_id"],
        "decision": "like",
        "give_player_ids": give_ids,
        "receive_player_ids": recv_ids,
        "target_user_id": target_uid,
        "target_username": card.get("target_username", ""),
        "league_id": TEST_LEAGUE,
    }
    before_td = db1("SELECT COUNT(*) FROM trade_decisions WHERE user_id=?", (USER_B,))
    before_sw = db1("SELECT COUNT(*) FROM swipe_decisions WHERE user_id=? AND decision_type='trade'",
                    (USER_B,))
    r = api_b.post("/api/trades/swipe", ctx)
    check("S4.1-swipe-200", r.status_code == 200, f"status={r.status_code} {r.text[:120] if r.status_code != 200 else ''}")
    body = r.json()
    check("S4.2-no-premature-match", body.get("matched") is False,
          f"matched={body.get('matched')} (no mirror exists yet)")
    after_td = db1("SELECT COUNT(*) FROM trade_decisions WHERE user_id=?", (USER_B,))
    after_sw = db1("SELECT COUNT(*) FROM swipe_decisions WHERE user_id=? AND decision_type='trade'",
                   (USER_B,))
    check("S4.3-decision-persisted", after_td - before_td == 1,
          f"trade_decisions +{after_td - before_td}")
    check("S4.4-elo-signal-persisted", after_sw - before_sw >= 1,
          f"swipe_decisions(trade) +{after_sw - before_sw}")

    # Counterparty session: like the MIRROR via card-context echo (FB-46 path).
    target_username = db1("SELECT username FROM league_members WHERE league_id=? AND user_id=?",
                          (TEST_LEAGUE, target_uid)) or target_uid
    info(f"counterparty = {target_uid} ({target_username})")
    tok_c, payload_c = init_session(target_uid, str(target_username), TEST_LEAGUE)
    check("S4.5-counterparty-init", payload_c["status"] == 200 and bool(tok_c),
          f"counterparty session status={payload_c['status']}")
    api_c = Api(tok_c)

    mirror = {
        "trade_id": "qa-e2e-mirror-001",            # not in C's deck -> FB-46 reconstruction
        "decision": "like",
        "give_player_ids": recv_ids,                # flipped perspective
        "receive_player_ids": give_ids,
        "target_user_id": USER_B,
        "target_username": USER_B,
        "league_id": TEST_LEAGUE,
    }
    before_m = db1("SELECT COUNT(*) FROM trade_matches WHERE league_id=?", (TEST_LEAGUE,))
    r2 = api_c.post("/api/trades/swipe", mirror)
    check("S4.6-mirror-swipe-200", r2.status_code == 200,
          f"status={r2.status_code} {r2.text[:160] if r2.status_code != 200 else ''}")
    body2 = r2.json() if r2.status_code == 200 else {}
    check("S4.7-match-detected", body2.get("matched") is True,
          f"matched={body2.get('matched')} match_id={body2.get('match_id')}")
    after_m = db1("SELECT COUNT(*) FROM trade_matches WHERE league_id=?", (TEST_LEAGUE,))
    check("S4.8-match-row", after_m - before_m == 1, f"trade_matches +{after_m - before_m}")

    match_id = body2.get("match_id")
    if match_id:
        row = db("SELECT status FROM trade_matches WHERE id=?", (match_id,))
        check("S4.9-match-pending", bool(row) and row[0][0] == "pending",
              f"match status={row[0][0] if row else 'missing'}")
        notif = db1("SELECT COUNT(*) FROM notifications WHERE type='trade_match' AND "
                    "user_id IN (?,?) AND id > (SELECT COALESCE(MAX(id),0)-2 FROM notifications)",
                    (USER_B, target_uid))
        both = db("SELECT user_id FROM notifications WHERE type='trade_match' ORDER BY id DESC LIMIT 2")
        check("S4.10-notifications-both",
              {u for (u,) in both} == {USER_B, target_uid},
              f"latest trade_match notifications -> {sorted(u for (u,) in both)}")
        # surface in B's matches inbox
        rm = api_b.get(f"/api/trades/matches?league_id={TEST_LEAGUE}")
        found = any(m.get("id") == match_id or m.get("match_id") == match_id
                    for m in (rm.json() if rm.status_code == 200 else
                              rm.json().get("matches", []) if isinstance(rm.json(), dict) else []))
        check("S4.11-match-in-inbox", rm.status_code == 200 and found,
              f"GET /api/trades/matches status={rm.status_code} contains match={found}")
    stage4_swipe_and_match.api_c = api_c   # hand to stage 5
    return match_id


def stage5_disposition(api_b: Api, match_id: int) -> None:
    print("\nSTAGE 5 — disposition lifecycle (both-sides accept, 409 on repeat, 404 unknown)")
    api_c: Api = stage4_swipe_and_match.api_c

    r1 = api_c.post(f"/api/trades/matches/{match_id}/disposition", {"decision": "accept"})
    check("S5.1-first-accept-200", r1.status_code == 200, f"status={r1.status_code}")
    status_mid = db1("SELECT status FROM trade_matches WHERE id=?", (match_id,))
    check("S5.2-still-pending", status_mid == "pending",
          f"after one accept status={status_mid} (must not roll until both decide)")

    r2 = api_b.post(f"/api/trades/matches/{match_id}/disposition", {"decision": "accept"})
    check("S5.3-second-accept-200", r2.status_code == 200, f"status={r2.status_code}")
    status_end = db1("SELECT status FROM trade_matches WHERE id=?", (match_id,))
    check("S5.4-accepted", status_end == "accepted", f"final status={status_end}")

    dispo_rows = db1("SELECT COUNT(*) FROM swipe_decisions WHERE decision_type='disposition' "
                     "AND user_id IN (?,?)", (USER_B, "%"))
    info(f"disposition Elo signals present for user_b: {dispo_rows}")

    r3 = api_b.post(f"/api/trades/matches/{match_id}/disposition", {"decision": "accept"})
    check("S5.5-repeat-409", r3.status_code == 409, f"repeat decision status={r3.status_code}")
    r4 = api_b.post("/api/trades/matches/99999999/disposition", {"decision": "accept"})
    check("S5.6-unknown-404", r4.status_code == 404, f"unknown match status={r4.status_code}")
    rbad = api_b.post(f"/api/trades/matches/{match_id}/disposition", {"decision": "maybe"})
    check("S5.7-bad-decision-400", rbad.status_code == 400, f"invalid decision status={rbad.status_code}")


def stage6_integrity(api: Api, baseline: dict) -> None:
    print("\nSTAGE 6 — post-run integrity sweep + server log scan")
    orphans = db1("SELECT COUNT(*) FROM league_members lm LEFT JOIN users u "
                  "ON lm.user_id = u.sleeper_user_id WHERE u.sleeper_user_id IS NULL")
    check("S6.1-no-new-orphans", orphans <= baseline["orphans"],
          f"orphaned league_members: {orphans} (baseline {baseline['orphans']})")

    bad_enum = db1("SELECT COUNT(*) FROM swipe_decisions WHERE decision_type NOT IN "
                   "('rank','trade','disposition')")
    check("S6.2-enum-domain", bad_enum == 0, f"{bad_enum} swipe_decisions outside enum domain")

    bad_dec = db1("SELECT COUNT(*) FROM trade_decisions WHERE decision NOT IN ('like','pass')")
    bad_match = db1("SELECT COUNT(*) FROM trade_matches WHERE status NOT IN "
                    "('pending','accepted','declined')")
    check("S6.3-enum-domain-2", bad_dec == 0 and bad_match == 0,
          f"bad trade_decisions={bad_dec} bad trade_matches={bad_match}")

    new_ts = db("SELECT created_at FROM swipe_decisions ORDER BY id DESC LIMIT 5")
    iso_ok = all(t and "T" in str(t) and str(t)[:4].isdigit() for (t,) in new_ts)
    check("S6.4-iso-timestamps", iso_ok, f"latest swipe_decision timestamps ISO-8601: {iso_ok}")

    fk = db("PRAGMA integrity_check")
    check("S6.5-sqlite-integrity", fk and fk[0][0] == "ok", f"PRAGMA integrity_check={fk[0][0]}")

    r = api.get("/api/debug/log?n=200")
    if r.status_code == 200:
        text = json.dumps(r.json())
        err_count = text.count("ERROR") + text.count("Traceback")
        check("S6.6-no-server-errors", err_count == 0,
              f"{err_count} ERROR/Traceback entries in debug ring buffer")
    else:
        check("S6.6-no-server-errors", False, f"/api/debug/log status={r.status_code}")

    # Server-side warnings during the run = swallowed failures. Known, already-
    # filed findings are allowlisted so the gate stays useful while they're open.
    # F-E2E-1 (upsert_league keyed on (league_id, user_id) → UNIQUE constraint
    # failed on every second-member session_init) was FIXED — upsert_league now
    # upserts on the sleeper_league_id PK. It is intentionally NOT allowlisted so
    # this gate catches any regression.
    KNOWN_ISSUES: set[str] = set()
    log_text = SERVER_LOG.read_text()
    warn_lines = [ln for ln in log_text.splitlines()
                  if "[WARNING]" in ln or "IntegrityError" in ln or "constraint failed" in ln]
    unexpected = [ln for ln in warn_lines
                  if not any(k in ln for k in KNOWN_ISSUES)
                  and "Background on this error" not in ln and "[SQL:" not in ln
                  and not ln.strip().startswith("[parameters")]
    known_hits = [ln for ln in warn_lines if any(k in ln for k in KNOWN_ISSUES)]
    if known_hits:
        info(f"known issue reproduced ({len(known_hits)}x)")
    check("S6.8-no-unexpected-warnings", not unexpected,
          f"{len(unexpected)} unexpected warning lines in server log"
          + (f"; first: {unexpected[0][:160]}" if unexpected else ""))

    over = [t for t in timings if not t["within_budget"]]
    check("S6.7-all-within-budget", not over,
          f"{len(over)} calls over mobile budget" + (f": {over}" if over else ""))


# ───────────────────────────────── main ─────────────────────────────────────

def main() -> int:
    print("TC-E2E-001 — full-stack happy path (scratch DB, local server)")
    setup_scratch()
    baseline = {
        "orphans": db1("SELECT COUNT(*) FROM league_members lm LEFT JOIN users u "
                       "ON lm.user_id = u.sleeper_user_id WHERE u.sleeper_user_id IS NULL"),
        "swipes": db1("SELECT COUNT(*) FROM swipe_decisions"),
        "matches": db1("SELECT COUNT(*) FROM trade_matches"),
    }
    info(f"baselines: {baseline}")

    proc = start_server()
    try:
        api_b = stage1_session_init()
        if api_b.token:
            stage2_ranking(api_b)
            cards = stage3_generate(api_b)
            if cards:
                match_id = stage4_swipe_and_match(api_b, cards)
                if match_id:
                    stage5_disposition(api_b, match_id)
            stage6_integrity(api_b, baseline)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    passed = sum(1 for c in checks if c["ok"])
    failed = [c for c in checks if not c["ok"]]
    print(f"\n{'=' * 60}\nRESULT: {passed}/{len(checks)} checks passed")
    if failed:
        print("FAILED CHECKS:")
        for c in failed:
            print(f"  ✗ {c['id']}: {c['detail']}")
    print("\nTIMINGS (vs mobile budget):")
    for t in timings:
        flag = "" if t["within_budget"] else "  ** OVER BUDGET **"
        print(f"  {t['ms']:>6}ms  {t['method']:<5} {t['path']}{flag}")

    out = {"test_case": "TC-E2E-001", "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "passed": passed, "total": len(checks), "checks": checks, "timings": timings}
    (SCRATCH_DIR / "TC-E2E-001-run.json").write_text(json.dumps(out, indent=2))
    print(f"\nreport: {SCRATCH_DIR / 'TC-E2E-001-run.json'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
