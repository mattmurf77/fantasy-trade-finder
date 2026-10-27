#!/usr/bin/env python3
"""
deck_eval.py — first-deck quality gate (MOD-M1; bars ratified in D-055)
=======================================================================
Simulates a brand-new user's first deck for every team of each connected
Sleeper league passed in, through the live first-deck path, and reports the
D-055 gate: empty-deck rate (< 5%), the rule-based insult rate over every
first-5 card (< 3%; backend/eval/insult_rule.py) and latency.

The path is the live one (backend/eval/first_deck.py has the detail and the
deliberate differences): POST /api/session/init → the pregen trade job's
worker (_run_trade_job) → POST /api/trades/generate page 1, through the Flask
app in this process. The default engine and roster as configured, owner
presentment, the D-207 deck_quality filters, the first-30 publication and
ghost withholding all run as configured. Pass prod's configuration (MOD-M1
M3) with --overrides, a JSON file {"flags": {...}, "model_config": {...}}.

Isolation: DATABASE_URL is pointed at a new temporary SQLite file before any
backend import, and the run refuses to start unless every backend engine is
that file. The jobs' writes (impressions, evidence, events) land there and
are deleted with it. Nothing reads prod. League data comes only from the
public Sleeper API (read-only), memoized per run.

Usage:
  python3 scripts/deck_eval.py --overrides prod-config.json 1312076055586050048 [more ids...]
  python3 scripts/deck_eval.py --no-overrides <league ids>   # this checkout's config: not a gate run
Options:
  --overrides PATH  prod's flags and model_config (unknown keys are an error)
  --no-overrides    run on config/features.json and the model_config defaults
  --max-teams N     cap teams per league (default: all)
  --seed N          deck RNG seed (default 0); with PYTHONHASHSEED fixed a re-run reproduces
  --report PATH     markdown report (default: next to the JSON)

Outputs (feedback-workspace/deck-eval/, gitignored: they hold league rosters):
  deck_eval_<UTC ts>.json   machine-readable: every first-5 card with each side's
                            assets (position, age, consensus value), totals, Δ,
                            haircut, I1/I2 and the league format
  deck_eval_<UTC ts>.md     readable report
"""

import argparse
import hashlib
import json
import logging
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
OUT_DIR = PROJECT_ROOT / "feedback-workspace" / "deck-eval"


def _isolate(scratch: pathlib.Path, flags: dict | None) -> None:
    """Environment for a scratch-only run. Must precede every backend import."""
    if any(name.startswith("backend") for name in sys.modules):
        raise SystemExit("deck_eval must start in a fresh process (backend already imported)")
    os.environ["DATABASE_URL"] = f"sqlite:///{scratch}"
    os.environ["FTF_DISABLE_CLEANUP_LOOP"] = "1"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    if flags:
        # Import-time readers see prod's flags too (apply_overrides covers the rest).
        os.environ["FTF_FLAGS"] = json.dumps(flags)
    else:
        os.environ.pop("FTF_FLAGS", None)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("league_ids", nargs="+", help="connected Sleeper league ids")
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--overrides", type=pathlib.Path,
                       help='JSON {"flags": {...}, "model_config": {...}} with prod values')
    which.add_argument("--no-overrides", action="store_true",
                       help="this checkout's config (not a gate run)")
    ap.add_argument("--max-teams", type=int, default=0, help="cap teams per league (0 = all)")
    ap.add_argument("--seed", type=int, default=0, help="deck RNG seed")
    ap.add_argument("--report", type=pathlib.Path, help="markdown report path")
    args = ap.parse_args()

    overrides = None
    if args.overrides:
        overrides = json.loads(args.overrides.read_text())
        if not isinstance(overrides, dict):
            raise SystemExit("--overrides must hold a JSON object")
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="deck-eval-"))
    scratch = workdir / "scratch.sqlite3"
    _isolate(scratch, (overrides or {}).get("flags"))

    print(f"Scratch database: {scratch}")
    print("Importing backend.server (warm-process setup: DB, consensus, pools)...")
    try:
        t0 = time.perf_counter()
        from backend.eval import first_deck as fd  # noqa: E402  (imports backend.server)
        import_s = time.perf_counter() - t0
        fd.require_scratch_db(str(scratch))
        # The backend's INFO firehose (every module logger); failures still surface.
        logging.getLogger().setLevel(logging.WARNING)
        logging.getLogger("trade_finder").setLevel(logging.WARNING)

        applied = fd.apply_overrides(overrides) if overrides else None
        if applied is None:
            print("!! --no-overrides: this checkout's config, NOT prod's. Not a gate run.")
        t0 = time.perf_counter()
        if fd.srv._load_sleeper_cache() is None:
            raise SystemExit("data/.sleeper_players_cache.json missing — start the dev "
                             "server once or fetch /api/sleeper/players.")
        fd.srv._ensure_universal_pools()
        pool_build_ms = (time.perf_counter() - t0) * 1000
        if not fd.srv.g_universal_by_format.get("1qb_ppr", {}).get("players"):
            raise SystemExit("Universal pool build failed (DynastyProcess fetch?)")

        ts = datetime.now(timezone.utc)
        leagues = []
        with fd.FirstDeckEval(workdir, seed=args.seed) as evaluation:
            for league_id in dict.fromkeys(args.league_ids):
                print(f"\n=== League {league_id}")
                league = evaluation.run_league(league_id, max_teams=args.max_teams)
                if league["error"]:
                    print(f"  !! {league['error']}")
                for seat in league["seats"]:
                    seat.pop("first_page")        # raw public cards: in memory only
                    print(f"  @{seat['username']:<22} first page={seat['first_page_size']:>3} "
                          f"deck={seat['deck_size']:>4} build={seat['job_ms'] or 0:7.0f}ms "
                          f"insults={sum(c['insult'] for c in seat['cards'])}"
                          + (f"  !! {seat['error']}" if seat["status"] == "error" else ""))
                leagues.append(league)
            pushes = evaluation.pushes

        summary = fd.summarize(leagues)
        summary.update(import_s=round(import_s, 1), pool_build_ms=round(pool_build_ms, 1))
        run = {
            "generated_at": ts.strftime("%Y-%m-%d %H:%M UTC"),
            "commit": _git_head(),
            "overrides_file": str(args.overrides) if args.overrides else None,
            "overrides_sha256": (hashlib.sha256(args.overrides.read_bytes()).hexdigest()
                                 if args.overrides else None),
            "overrides_applied": applied,
            "seed": args.seed,
            "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
            "iso_week": fd.srv._bakeoff.iso_week_of(),
            "first_deck_fairness": fd.FIRST_DECK_FAIRNESS,
            "pushes_suppressed": pushes,
            "effective_flags": fd.ff.flags_dict(),
            "effective_model_config": dict(sorted(fd._trade_service_mod._cfg.items())),
            "summary": summary,
            "leagues": leagues,
        }
    finally:
        if "backend.database" in sys.modules:
            sys.modules["backend.database"].engine.dispose()
        shutil.rmtree(workdir, ignore_errors=True)

    json_path, report_path = output_paths(ts.strftime("%Y%m%dT%H%M%SZ"), args.report)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    run["json_artifact"] = _display(json_path)
    json_path.write_text(json.dumps(run, indent=1))
    write_report(report_path, run)

    s = summary
    print(f"\n== Done: {s['leagues']} leagues, {s['seats']} teams")
    print(f"   empty-deck rate {s['empty_deck_rate_pct']}% (bar < 5%)")
    print(f"   insult rate     {s['insult_rate_pct']}% of {s['first5_cards']} first-5 cards (bar < 3%)")
    print(f"   deck build      {s['latency_ms']['deck_build']}")
    print(f"   JSON:   {json_path}")
    print(f"   Report: {report_path}")


def output_paths(stamp: str, report: pathlib.Path | None = None) -> tuple[pathlib.Path, pathlib.Path]:
    """(JSON, markdown) paths. Both default into the gitignored OUT_DIR: the
    report holds league rosters and never belongs in a tracked doc."""
    return OUT_DIR / f"deck_eval_{stamp}.json", report or OUT_DIR / f"deck_eval_{stamp}.md"


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return None


def _display(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def fmt_side(side: list[dict]) -> str:
    return " + ".join(f"{a['name']} ({a['position']}, {a['value']})" for a in side)


def _pct(x) -> str:
    return "—" if x is None else f"{x}%"


def write_report(path: pathlib.Path, run: dict) -> None:
    s = run["summary"]
    lines = []
    a = lines.append
    a("# First-deck quality gate — deck_eval")
    a("")
    a(f"*Generated {run['generated_at']} by `scripts/deck_eval.py` at `{(run['commit'] or '?')[:8]}`, "
      f"ISO week {run['iso_week']}, seed {run['seed']}.*")
    a("")
    if run["overrides_applied"] is None:
        a("> **Not a gate run:** `--no-overrides` — this checkout's config, not prod's.")
    else:
        o = run["overrides_applied"]
        a(f"Config: prod overrides from `{run['overrides_file']}` (sha256 "
          f"`{run['overrides_sha256'][:12]}`): {len(o['flags'])} flags, "
          f"{len(o['model_config'])} model_config keys.")
    a("")
    a("Each team below is simulated as a **brand-new user** opening the app: consensus board, "
      "no swipes or preferences, league-mates on consensus too (no prod reads). The deck is the "
      "live first-deck path: `/api/session/init` → the pregen job → `/api/trades/generate` "
      "page 1 (fairness 0.5, the default for an unset preference).")
    a("")
    a("## The gate (D-055)")
    a("")
    verdict = {True: "PASS", False: "FAIL"}
    a("| Metric | Bar | This run |")
    a("|---|---|---|")
    a(f"| Empty-deck rate | **< 5%** | {_pct(s['empty_deck_rate_pct'])} "
      f"({s['empty_decks']}/{s['seats']}) — {verdict[s['pass']['empty_deck']]} |")
    a(f"| Insult rate, every first-5 card | **< 3%** | {_pct(s['insult_rate_pct'])} "
      f"({s['insult_cards']}/{s['first5_cards']}; I1 {s['i1_cards']}, I2 {s['i2_cards']}) — "
      f"{verdict[s['pass']['insult']]} |")
    lat = s["latency_ms"]["deck_build"]
    if lat.get("n"):
        a(f"| Deck build (pregen job) | informs the 60 s budget | mean {lat['mean']} ms · "
          f"p95 {lat['p95']} ms · max {lat['max']} ms |")
    a("")
    a("**The insult rule** (`backend/eval/insult_rule.py`, from the 2026-08-15 report's "
      "statement): a card is an insult when the owner's side is net negative in consensus value "
      "by |Δ| ≥ 500 **and** either I1, a haircut of 20% or more on the package the owner gives, "
      "or I2, the return holds an asset worth ≤ 350 while the give side holds one worth ≥ 2,500. "
      "Δ = receive − give. Values are consensus (`elo_to_value` of the seed Elo).")
    a("")
    a("## Summary")
    a("")
    a(f"- Leagues: **{s['leagues']}** ({s['leagues_failed']} failed) · teams: **{s['seats']}** "
      f"({s['seat_errors']} errored, counted as empty)")
    a(f"- First page size: min {s['first_page_size']['min']} · mean {s['first_page_size']['mean']} "
      f"· max {s['first_page_size']['max']}")
    for label, key in (("Session init", "session_init"), ("Deck build", "deck_build"),
                       ("First page (generate)", "first_page")):
        x = s["latency_ms"][key]
        if x.get("n"):
            a(f"- {label}: mean {x['mean']} ms · p50 {x['p50']} ms · p95 {x['p95']} ms · max {x['max']} ms")
    a(f"- Warm-process setup: import {s['import_s']} s, universal pools {s['pool_build_ms']} ms "
      "(local machine; Render differs, cold start most)")
    if s["regenerated_seats"]:
        a(f"- **{s['regenerated_seats']} teams' first page did not join the pregen job** "
          "(a second job ran): check before trusting latency.")
    a("")
    a("### Format cells")
    a("")
    a("| Cell | Leagues | Teams | Empty | First-5 cards | Insults |")
    a("|---|---|---|---|---|---|")
    for cell, c in s["cells"].items():
        a(f"| {cell} | {c['leagues']} | {c['seats']} | {c['empty_decks']} | "
          f"{c['first5_cards']} | {c['insult_cards']} |")
    insults = [(lg, seat, c) for lg in run["leagues"] for seat in lg["seats"]
               for c in seat["cards"] if c["insult"]]
    if insults:
        a("")
        a("### Insult cards")
        a("")
        for lg, seat, c in insults:
            tags = "+".join(t for t in ("I1", "I2") if c[t.lower()])
            a(f"- {lg['name']} / @{seat['username']} #{c['deck_position']} ({tags}): "
              f"{fmt_side(c['give'])} → {fmt_side(c['receive'])} "
              f"(Δ {c['delta']:+d}, haircut {round(c['haircut'] * 100)}%)")
    a("")
    a("---")
    for lg in run["leagues"]:
        a("")
        f = lg["format"] or {}
        a(f"## {lg['name']} (`{lg['league_id']}`)")
        a("")
        if lg["error"]:
            a(f"**Not evaluated:** {lg['error']}")
            continue
        a(f"{f.get('qb')} · {'TEP ' + str(f.get('te_bonus')) if f.get('tep') else 'no TEP'} · "
          f"{f.get('teams')} teams · `{f.get('scoring_format')}` · "
          f"{len(lg['seats'])} evaluated, {lg['teams_skipped']} skipped (no owner or empty roster)")
        for seat in lg["seats"]:
            a("")
            a(f"### @{seat['username']} — first page {seat['first_page_size']} of {seat['deck_size']} "
              f"· build {seat['job_ms']} ms · outlook `{seat['outlook']}`")
            if seat["status"] == "error":
                a("")
                a(f"**ERROR** — {seat['error']}")
                continue
            if not seat["cards"]:
                a("")
                a("**EMPTY DECK** — this user sees no trades"
                  + (f" ({seat['error']})." if seat["error"] else "."))
                continue
            a("")
            a("| # | Trade (give → receive) | Δ | Haircut | Insult |")
            a("|---|---|---|---|---|")
            for c in seat["cards"]:
                tags = "+".join(t for t in ("I1", "I2") if c[t.lower()]) or "—"
                a(f"| {c['deck_position']} | {fmt_side(c['give'])} → **{fmt_side(c['receive'])}** "
                  f"(w/ {c['partner']}) | {c['delta']:+d} | {round(c['haircut'] * 100)}% | {tags} |")
    a("")
    a("---")
    a("")
    a("## Method notes")
    a("")
    a("- `backend/eval/first_deck.py` lists the deliberate differences from a live first open: "
      "the session-init daemon runs once per league (the league is already connected) and every "
      "team starts from that snapshot; league-mates have no personal boards; the deck RNG seed is "
      "fixed; Sleeper reads are memoized; pushes are no-ops.")
    a("- Latency is this machine's, warm process; Render will differ.")
    a(f"- Effective flags and model_config: the JSON artifact (`{run['json_artifact']}`).")
    a("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
