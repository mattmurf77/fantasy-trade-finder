"""Operator label review for the win-now season signal (validation.md §4, lld.md §8).

Two commands:

    python -m backend.eval.season_label_review write --fixture
    python -m backend.eval.season_label_review write --rows <league rows.json> --league-key league-a
    python -m backend.eval.season_label_review score <marks.json> [<marks.json> ...]

`write` turns one league's label table into a self-contained HTML review page plus its rows
sidecar (`<key>.html`, `<key>.rows.json`) under `data/season-label-review/`, inside the
repository's git-ignored `/data/` folder; it refuses any folder outside it. One row per
rostered player (picks are labelled by rule and not graded): name, position, age, projected
points per game, the league's starter line at his position, dynasty value, future value,
startable, label; grouped by label. Per row the operator marks Agree or the label it should
be; a second list asks whether each of the viewer's players "starts for you". Marks persist in
the browser and are exported as `<key>.marks.json`. Public NFL names only: nothing about a
league's managers or team names is put on the page.

`--rows` reads a league's rows in the sidecar's own shape (`season-label-review-1`, below); the
admin route of WI-5 (`GET /api/admin/season-signal/labels`) is to return or be mapped to it.
`--fixture` builds them from the committed fixture league and its projection capture.

`score` reads exported marks with their sidecars and prints aggregates only: agreement overall,
by label, the top 24 by value in each league, a confusion table, "starts for you", and the bar
(>= 85% agreement over >= 120 graded labelled players in >= 2 leagues). Unmarked players are
not graded. Exit 0 when the bar passes, 1 otherwise. Label stability (<= 10% of labels change
on the next weekly forecast) needs two forecasts and is not measured here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import html
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
IGNORED_ROOT = REPO / "data"                     # `/data/` in .gitignore
DEFAULT_DIR = IGNORED_ROOT / "season-label-review"
SCHEMA, MARKS_SCHEMA = "season-label-review-1", "season-label-review-marks-1"
LABELS = ("win_now", "cornerstone", "rebuild", "depth")
SHOWN = {"win_now": "Win-now piece", "cornerstone": "Cornerstone", "rebuild": "Rebuild piece",
         "depth": "Depth", None: "No label (borderline or unprojected)"}
AGREEMENT_BAR, MIN_GRADED, MIN_LEAGUES, TOP, STARTS_BAR = .85, 120, 2, 24, .9


# ── rows ──────────────────────────────────────────────────────────────────────

def fixture_rows(league_key="fixture-league-12"):
    """The fixture league's label table, read from revision 5's own search (viewer = first team)."""
    from .. import trade_gen_bilateral_season as r5
    from .season_replay import fixture_evidence, fixture_world
    search = r5._Search(**fixture_world("championship"), season_evidence=fixture_evidence())
    profile, ppg = search._profile, search._season_ppg
    viewer = search.teams[search.user_id]
    players = []
    for team in search.teams.values():
        for pid in sorted(team["roster"]):
            pos = search._position(pid)
            if pos == "PICK":
                continue
            info = profile["players"].get(pid) or {}
            player = search.players[pid]
            players.append({"id": pid, "name": player.name, "position": pos, "age": player.age,
                            "ppg": ppg.get(pid), "line": profile["line"].get(pos),
                            "value": round(search.market.get(pid, 0.0), 1), "future": info.get("future"),
                            "startable": info.get("startable"), "label": info.get("label")})
    own = [{"id": pid, "name": search.players[pid].name, "position": search._position(pid), "ppg": ppg.get(pid),
            "starts_for_you": search.starts_for(viewer, pid)}
           for pid in sorted(viewer["roster"]) if search._position(pid) != "PICK" and pid in ppg]
    return {"schema": SCHEMA, "league_key": league_key, "label_rules_version": r5.LABEL_RULES_VERSION,
            "line": profile["line"], "players": players, "own": own}


# ── the page ──────────────────────────────────────────────────────────────────

def _inside_ignored(path):
    root = IGNORED_ROOT.resolve()
    target = Path(path).resolve()
    return target == root or root in target.parents


def _num(x, digits=1):
    return "" if x is None else f"{x:.{digits}f}" if isinstance(x, float) else str(x)


def _options():
    return "".join(f'<option value="{k}">{html.escape(SHOWN[k])}</option>' for k in (*LABELS, "none")
                   if k != "none") + '<option value="none">No label</option>'


def render(rows):
    """The self-contained HTML page for one league's rows."""
    key = html.escape(rows["league_key"])
    groups = []
    for label in (*LABELS, None):
        members = sorted((p for p in rows["players"] if p["label"] == label), key=lambda p: -(p["value"] or 0))
        if not members:
            continue
        body = "".join(
            f'<tr data-id="{html.escape(str(p["id"]))}" data-label="{p["label"] or "none"}">'
            f'<td>{html.escape(str(p["name"]))}</td><td>{html.escape(str(p["position"]))}</td>'
            f'<td class="n">{_num(p["age"])}</td><td class="n">{_num(p["ppg"], 2)}</td>'
            f'<td class="n">{_num(p["line"], 2)}</td><td class="n">{_num(p["value"], 0)}</td>'
            f'<td class="n">{_num(p["future"], 0)}</td>'
            f'<td>{"" if p["startable"] is None else "yes" if p["startable"] else "no"}</td>'
            f'<td><button class="btn agree" type="button">Agree</button> '
            f'<select class="should" aria-label="Should be"><option value="">Should be&hellip;</option>{_options()}'
            f'</select></td></tr>' for p in members)
        groups.append(f'<section class="card"><h2>{html.escape(SHOWN[label])} <span class="cnum">{len(members)}'
                      f'</span></h2><table><thead><tr><th>Player</th><th>Pos</th><th class="n">Age</th>'
                      f'<th class="n">Pts/game</th><th class="n">Starter line</th><th class="n">Value</th>'
                      f'<th class="n">Future</th><th>Startable</th><th>Your call</th></tr></thead>'
                      f'<tbody>{body}</tbody></table></section>')
    own = "".join(
        f'<tr data-start="{html.escape(str(p["id"]))}"><td>{html.escape(str(p["name"]))}</td>'
        f'<td>{html.escape(str(p["position"]))}</td><td class="n">{_num(p["ppg"], 2)}</td>'
        f'<td>{"starts" if p["starts_for_you"] else "does not start"}</td>'
        f'<td><button class="btn right" type="button">Right</button> '
        f'<button class="btn wrong" type="button">Wrong</button></td></tr>' for p in rows.get("own", ()))
    line = " &middot; ".join(f"{pos} {_num(v, 2)}" for pos, v in (rows.get("line") or {}).items())
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Label review &mdash; {key}</title>
<style>
:root {{ --ground:#0C0E11; --panel:#13161B; --line:#262C35; --text:#ECEFF4; --dim:#97A1AE;
  --ice:#56D9EC; --ice-on:#071013; --flare:#F0508C;
  --display:'Barlow Condensed','Avenir Next Condensed','Arial Narrow',sans-serif;
  --body:'Archivo','Avenir Next','Helvetica Neue',Arial,sans-serif;
  --mono:'IBM Plex Mono','SF Mono',Menlo,Consolas,monospace; }}
body {{ background:var(--ground); color:var(--text); font-family:var(--body); font-size:14px; margin:0; }}
.topbar {{ position:sticky; top:0; display:flex; gap:16px; align-items:center; padding:12px 24px;
  background:var(--ground); border-bottom:1px solid var(--line); }}
.topbar h1 {{ font-family:var(--display); text-transform:uppercase; font-size:22px; margin:0; flex:1; }}
main {{ padding:0 24px 48px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px 20px; margin:18px 0; }}
h2 {{ font-family:var(--display); text-transform:uppercase; font-size:20px; margin:0 0 10px; }}
.cnum, #progress {{ font-family:var(--mono); font-size:12px; color:var(--dim); }}
table {{ border-collapse:collapse; width:100%; }}
th, td {{ text-align:left; padding:6px 12px 6px 0; border-bottom:1px solid var(--line); }}
th {{ font-size:11px; text-transform:uppercase; color:var(--dim); }}
.n {{ text-align:right; font-family:var(--mono); }}
.btn {{ font-family:var(--body); font-weight:600; font-size:12px; background:transparent; color:var(--dim);
  border:1px solid var(--line); border-radius:4px; padding:4px 10px; cursor:pointer; }}
.btn.on, .btn.primary {{ background:var(--ice); color:var(--ice-on); border-color:var(--ice); }}
select {{ font-size:12px; background:var(--ground); color:var(--text); border:1px solid var(--line); border-radius:4px; }}
tr.disagree td:first-child {{ color:var(--flare); }}
</style></head><body>
<div class="topbar"><h1>Label review &mdash; {key}</h1><span id="progress"></span>
<button class="btn primary" id="exportBtn" type="button">Export marks</button></div>
<main>
<p>Rules {html.escape(str(rows.get("label_rules_version")))}. Starter line (points a game): {line}.
Mark each player Agree, or pick the label he should have. Marks are kept in this browser until exported.</p>
{''.join(groups)}
<section class="card"><h2>Your roster: starts for you? <span class="cnum">{len(rows.get("own", ()))}</span></h2>
<table><thead><tr><th>Player</th><th>Pos</th><th class="n">Pts/game</th><th>Engine says</th><th>Your call</th></tr>
</thead><tbody>{own}</tbody></table></section>
</main>
<script>
(function () {{
  var KEY = 'ftf-season-label-review:{key}';
  var state = {{ marks: {{}}, starts: {{}} }};
  try {{ state = JSON.parse(localStorage.getItem(KEY)) || state; }} catch (e) {{}}
  function save() {{ try {{ localStorage.setItem(KEY, JSON.stringify(state)); }} catch (e) {{}} paint(); }}
  function paint() {{
    var rows = document.querySelectorAll('tr[data-id]'), done = 0;
    rows.forEach(function (tr) {{
      var mark = state.marks[tr.dataset.id];
      tr.querySelector('.agree').classList.toggle('on', mark === 'agree');
      tr.querySelector('.should').value = mark && mark !== 'agree' ? mark : '';
      tr.classList.toggle('disagree', !!mark && mark !== 'agree' && mark !== tr.dataset.label);
      if (mark) done++;
    }});
    document.querySelectorAll('tr[data-start]').forEach(function (tr) {{
      var v = state.starts[tr.dataset.start];
      tr.querySelector('.right').classList.toggle('on', v === 'right');
      tr.querySelector('.wrong').classList.toggle('on', v === 'wrong');
    }});
    document.getElementById('progress').textContent = done + ' of ' + rows.length + ' marked';
  }}
  document.querySelectorAll('tr[data-id]').forEach(function (tr) {{
    tr.querySelector('.agree').addEventListener('click', function () {{
      if (state.marks[tr.dataset.id] === 'agree') delete state.marks[tr.dataset.id];
      else state.marks[tr.dataset.id] = 'agree';
      save();
    }});
    tr.querySelector('.should').addEventListener('change', function (ev) {{
      if (ev.target.value) state.marks[tr.dataset.id] = ev.target.value; else delete state.marks[tr.dataset.id];
      save();
    }});
  }});
  document.querySelectorAll('tr[data-start]').forEach(function (tr) {{
    ['right', 'wrong'].forEach(function (v) {{
      tr.querySelector('.' + v).addEventListener('click', function () {{
        if (state.starts[tr.dataset.start] === v) delete state.starts[tr.dataset.start];
        else state.starts[tr.dataset.start] = v;
        save();
      }});
    }});
  }});
  document.getElementById('exportBtn').addEventListener('click', function () {{
    var out = {{ schema: '{MARKS_SCHEMA}', league_key: '{key}', exported_at: new Date().toISOString(),
                marks: state.marks, starts: state.starts }};
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], {{ type: 'application/json' }}));
    a.download = '{key}.marks.json';
    document.body.appendChild(a); a.click(); a.remove();
  }});
  paint();
}})();
</script></body></html>
"""


def write_review(rows, out_dir=DEFAULT_DIR):
    """Write `<key>.html` and `<key>.rows.json`; only inside the git-ignored data folder."""
    if rows.get("schema") != SCHEMA:
        raise ValueError(f"rows must carry schema {SCHEMA}")
    if not _inside_ignored(out_dir):
        raise ValueError("the review page is written only under the git-ignored data/ folder")
    key = str(rows["league_key"])
    if not key or any(ch in key for ch in "/\\") or key.startswith("."):
        raise ValueError("league_key must be a plain file name")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    page, sidecar = out / f"{key}.html", out / f"{key}.rows.json"
    page.write_text(render(rows))
    sidecar.write_text(json.dumps(rows, indent=1, sort_keys=True))
    return page, sidecar


def label_counts(rows):
    return Counter(p["label"] or "none" for p in rows["players"])


# ── scoring ───────────────────────────────────────────────────────────────────

def score(reviews):
    """Aggregates over [(rows, marks)] pairs: agreement, by label, top 24, confusion, starts, the bar."""
    graded = agreed = 0
    by_label, confusion, top, leagues = Counter(), Counter(), {}, set()
    agree_label = Counter()
    unlabelled_graded = right = starts_graded = 0
    for rows, marks in reviews:
        if marks.get("league_key") != rows["league_key"]:
            raise ValueError("marks belong to another league")
        given = marks.get("marks") or {}
        labelled = [p for p in rows["players"] if p["label"] is not None]
        for p in labelled:
            mark = given.get(str(p["id"]))
            if mark is None:
                continue  # unmarked: not graded
            graded += 1
            leagues.add(rows["league_key"])
            by_label[p["label"]] += 1
            if mark in ("agree", p["label"]):
                agreed += 1
                agree_label[p["label"]] += 1
            else:
                confusion[(p["label"], mark)] += 1
        unlabelled_graded += sum(str(p["id"]) in given for p in rows["players"] if p["label"] is None)
        best = sorted(labelled, key=lambda p: -(p["value"] or 0))[:TOP]
        top[rows["league_key"]] = sum(given.get(str(p["id"])) not in (None, "agree", p["label"]) for p in best)
        for p in rows.get("own", ()):
            verdict = (marks.get("starts") or {}).get(str(p["id"]))
            if verdict in ("right", "wrong"):
                starts_graded += 1
                right += verdict == "right"
    agreement = agreed / graded if graded else None
    passed = (agreement is not None and agreement >= AGREEMENT_BAR and graded >= MIN_GRADED
              and len(leagues) >= MIN_LEAGUES)
    return {"graded": graded, "agreed": agreed, "agreement": agreement, "leagues": len(leagues),
            "by_label": {label: (agree_label[label], by_label[label]) for label in LABELS if by_label[label]},
            "confusion": dict(confusion), "top_disagreements": top, "unlabelled_graded": unlabelled_graded,
            "starts": (right, starts_graded), "passed": passed}


def report(result):
    lines = [f"graded labelled players: {result['graded']} in {result['leagues']} league(s)",
             "agreement: " + ("n/a" if result["agreement"] is None else
                              f"{result['agreed']} of {result['graded']} ({result['agreement']:.1%})")]
    for label, (agree, n) in result["by_label"].items():
        lines.append(f"  {SHOWN[label]}: {agree} of {n} ({agree / n:.0%})")
    if result["confusion"]:
        lines.append("confusion (shown -> expected): " + ", ".join(
            f"{SHOWN[a]} -> {SHOWN.get(b, b) if b != 'none' else 'No label'} {n}"
            for (a, b), n in sorted(result["confusion"].items())))
    for league, n in sorted(result["top_disagreements"].items()):
        lines.append(f"top {TOP} by value, {league}: {n} disagreement(s)" + (" - explain each" if n else ""))
    if result["unlabelled_graded"]:
        lines.append(f"unlabelled players graded (not in the bar): {result['unlabelled_graded']}")
    right, n = result["starts"]
    starts_ok = n >= 10 and right / n >= STARTS_BAR
    lines.append(f"starts for you: {right} of {n} right [{'PASS' if starts_ok else 'FAIL' if n >= 10 else 'INSUFFICIENT'}]"
                 " (bar >= 9 of 10)")
    lines.append(f"[{'PASS' if result['passed'] else 'FAIL'}] agreement >= {AGREEMENT_BAR:.0%} over >= {MIN_GRADED} "
                 f"graded labelled players in >= {MIN_LEAGUES} leagues")
    lines.append("label stability (next weekly forecast): not measured by this tool")
    return "\n".join(lines)


def load_reviews(paths, directory=DEFAULT_DIR):
    reviews = []
    for path in paths:
        marks = json.loads(Path(path).read_text())
        if marks.get("schema") != MARKS_SCHEMA:
            raise ValueError(f"not a marks export: {os.path.basename(path)}")
        rows = json.loads((Path(directory) / f"{marks['league_key']}.rows.json").read_text())
        reviews.append((rows, marks))
    return reviews


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    w = sub.add_parser("write", help="write one league's review page")
    src = w.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixture", action="store_true")
    src.add_argument("--rows", help=f"a league's rows ({SCHEMA})")
    w.add_argument("--league-key", default=None, help="file name for the page (default: the rows' own)")
    w.add_argument("--out-dir", default=str(DEFAULT_DIR))
    s = sub.add_parser("score", help="read exported marks back")
    s.add_argument("marks", nargs="+")
    s.add_argument("--dir", default=str(DEFAULT_DIR))
    args = parser.parse_args(argv)
    if args.command == "write":
        rows = fixture_rows() if args.fixture else json.loads(Path(args.rows).read_text())
        if args.league_key:
            rows["league_key"] = args.league_key
        page, _ = write_review(rows, args.out_dir)
        counts = label_counts(rows)
        print(f"wrote {page}")
        print("players by label: " + ", ".join(f"{k} {counts[k]}" for k in (*LABELS, "none") if counts[k])
              + f"; your roster rows: {len(rows.get('own', ()))}")
        return 0
    result = score(load_reviews(args.marks, args.dir))
    print(report(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
