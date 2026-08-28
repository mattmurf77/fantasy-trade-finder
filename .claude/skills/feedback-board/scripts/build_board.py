#!/usr/bin/env python3
"""Build the open-feedback board HTML from the live admin API.

  python3 .claude/skills/feedback-board/scripts/build_board.py            # write board.html
  python3 .claude/skills/feedback-board/scripts/build_board.py --check    # only report missing descriptions

Joins the live feedback list against descriptions.json (the plain-language
layer). Any open item with no description is reported on stderr and rendered
with its raw text so the board is never silently incomplete.

Styling follows the Chalkline design system (docs/design/design-system.md):
dark-only ink surfaces, Barlow Condensed / Archivo / IBM Plex Mono, ice for
actions, flare for informational highlights. No gradients, no emoji, no
radius above 8px, no shadows.
"""
import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR.parent / "feedback" / "scripts"))
from fetch_feedback import PROD_BASE, OPEN_STATUSES, fetch_all  # noqa: E402

# Board section order. Anything with an unrecognised area lands in "Other".
AREA_ORDER = [
    "Trade finder", "Team review", "Calculator", "Player info",
    "League home", "League rankings", "Rank", "Mock draft",
    "Navigation", "Settings", "Design", "Other",
]

STATE_LABEL = {
    "open": "Open",
    "dark": "Built, switched off",
    "partial": "Partly done",
    "discuss": "Needs a decision",
}
SEV_LABEL = {"bug": "Bug", "polish": "Polish", "idea": "Idea"}


def load_descriptions() -> dict:
    path = SKILL_DIR / "descriptions.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def render(items: list, desc: dict, missing: list) -> str:
    by_area: dict[str, list] = {}
    for it in items:
        d = desc.get(str(it["id"]), {})
        area = d.get("area") or "Other"
        by_area.setdefault(area, []).append(it)

    counts = {
        "total": len(items),
        "dark": sum(1 for i in items if desc.get(str(i["id"]), {}).get("state") == "dark"),
        "bug": sum(1 for i in items if i.get("severity") == "bug"),
        "idea": sum(1 for i in items if i.get("severity") == "idea"),
        "polish": sum(1 for i in items if i.get("severity") == "polish"),
    }
    reporters: dict[str, int] = {}
    for i in items:
        reporters[i.get("username") or "unknown"] = reporters.get(i.get("username") or "unknown", 0) + 1

    stamp = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    out = []
    A = out.append

    A('<title>Fleeced Feedback Board</title>')
    A('<link rel="preconnect" href="https://fonts.googleapis.com">')
    A('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    A('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Barlow+Condensed:wght@600;700&family=Archivo:wght@400;500;600;700'
      '&family=IBM+Plex+Mono:wght@500;600&display=swap">')
    A(f"<style>{CSS}</style>")

    A('<div class="wrap">')
    A('<header class="head">')
    A('<p class="eyebrow"><span class="tick"></span>Fleeced · Dynasty Trade Finder</p>')
    A('<h1>Open tester feedback</h1>')
    A(f'<p class="sub">Every open item from the in-app feedback queue, in plain language. '
      f'Generated {esc(stamp)}.</p>')
    A('</header>')

    # Summary strip
    A('<section class="stats" aria-label="Summary">')
    for label, val, cls in (
        ("Open items", counts["total"], ""),
        ("Bugs", counts["bug"], "sev-bug"),
        ("Polish", counts["polish"], "sev-polish"),
        ("Ideas", counts["idea"], "sev-idea"),
        ("Built but off", counts["dark"], "hot"),
    ):
        A('<div class="stat">')
        A(f'<span class="stat-num {cls}">{val}</span>')
        A(f'<span class="stat-label">{esc(label)}</span>')
        A('</div>')
    A('</section>')

    who = " · ".join(f"{esc(k)} {v}" for k, v in sorted(reporters.items(), key=lambda x: -x[1]))
    A(f'<p class="reporters">Reported by {who}</p>')

    if counts["dark"]:
        A('<aside class="callout">')
        A('<p class="callout-title">Cheapest value on the board</p>')
        A(f'<p>{counts["dark"]} of these are already built and merged — they sit behind '
          'feature flags that are switched off. A tester still sees exactly what they '
          'reported, so they read as open, but the work is done. Check each one\'s flag '
          'note before flipping: one of them is not in any shipped app build yet.</p>')
        A('</aside>')

    if missing:
        A('<aside class="callout warn">')
        A('<p class="callout-title">Awaiting a plain-language summary</p>')
        A('<p>These arrived since the board was last written and show their raw text: '
          + ", ".join(f"#{esc(m)}" for m in missing) + '.</p>')
        A('</aside>')

    for area in AREA_ORDER:
        rows = by_area.get(area)
        if not rows:
            continue
        rows.sort(key=lambda i: -i["id"])
        A('<section class="area">')
        A(f'<h2>{esc(area)}<span class="area-count">{len(rows)}</span></h2>')
        A('<ul class="items">')
        for it in rows:
            d = desc.get(str(it["id"]), {})
            state = d.get("state", "open")
            plain = d.get("plain") or it.get("text", "").strip()
            note = d.get("note", "")
            sev = it.get("severity") or "bug"
            A(f'<li class="item state-{esc(state)}">')
            A('<div class="item-top">')
            A(f'<span class="id">#{it["id"]}</span>')
            A(f'<span class="chip sev-{esc(sev)}">{esc(SEV_LABEL.get(sev, sev))}</span>')
            if state != "open":
                A(f'<span class="chip st-{esc(state)}">{esc(STATE_LABEL.get(state, state))}</span>')
            A('</div>')
            A(f'<p class="plain">{esc(plain)}</p>')
            meta = f'{esc(it.get("username"))} · v{esc(it.get("app_version"))} · ' \
                   f'{esc((it.get("created_at") or "")[:10])} · {esc(it.get("screen"))}'
            A(f'<p class="meta">{meta}' + (f'<span class="note">{esc(note)}</span>' if note else '') + '</p>')
            A('</li>')
        A('</ul>')
        A('</section>')

    A('<footer class="foot"><p>Generated from the live feedback admin API. '
      'States are verified against the code on <code>origin/main</code>, not just the '
      'stored status field.</p></footer>')
    A('</div>')
    return "\n".join(out)


CSS = """
:root{
  --ink-0:#0C0E11; --ink-1:#13161B; --ink-2:#1A1E25; --ink-3:#232833;
  --line:#262C35; --line-strong:#59647A;
  --chalk:#ECEFF4; --chalk-dim:#97A1AE; --chalk-faint:#626C79;
  --ice:#56D9EC; --flare:#F0508C; --warn:#F59E0B; --pos:#22C55E; --neg:#EF4444;
  --r-xs:2px; --r-sm:4px; --r-md:8px;
}
*{box-sizing:border-box;}
body{
  margin:0; background:var(--ink-0); color:var(--chalk);
  font-family:Archivo,'Helvetica Neue',Arial,sans-serif; font-size:14px; line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:820px; margin:0 auto; padding:48px 24px 64px; display:flex; flex-direction:column; gap:32px;}
.head{display:flex; flex-direction:column; gap:8px;}
.eyebrow{
  margin:0; font-size:11px; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
  color:var(--chalk-dim); display:flex; align-items:center; gap:8px;
}
.tick{display:inline-block; width:3px; height:12px; background:var(--ice); border-radius:var(--r-xs);}
h1{
  margin:0; font-family:'Barlow Condensed',Arial,sans-serif; font-weight:700;
  font-size:44px; line-height:1.05; letter-spacing:.02em; text-transform:uppercase;
  text-wrap:balance;
}
.sub{margin:0; color:var(--chalk-dim); max-width:62ch;}
.reporters{
  margin:-16px 0 0; font-family:'IBM Plex Mono',monospace; font-size:12px;
  color:var(--chalk-faint); font-variant-numeric:tabular-nums;
}
.stats{display:flex; flex-wrap:wrap; gap:1px; background:var(--line); border:1px solid var(--line); border-radius:var(--r-md); overflow:hidden;}
.stat{flex:1 1 120px; background:var(--ink-1); padding:16px; display:flex; flex-direction:column; gap:4px;}
.stat-num{
  font-family:'IBM Plex Mono',monospace; font-weight:600; font-size:26px; line-height:1;
  font-variant-numeric:tabular-nums; color:var(--chalk);
}
.stat-num.hot{color:var(--flare);}
.stat-num.sev-bug{color:var(--neg);} .stat-num.sev-polish{color:var(--ice);} .stat-num.sev-idea{color:var(--warn);}
.stat-label{font-size:11px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--chalk-dim);}
.callout{
  border:1px solid var(--flare); border-left-width:3px; border-radius:var(--r-md);
  background:var(--ink-1); padding:16px; display:flex; flex-direction:column; gap:6px;
}
.callout.warn{border-color:var(--warn);}
.callout p{margin:0; color:var(--chalk-dim);}
.callout .callout-title{
  font-size:11px; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
  color:var(--flare);
}
.callout.warn .callout-title{color:var(--warn);}
.area{display:flex; flex-direction:column; gap:12px;}
h2{
  margin:0; font-family:'Barlow Condensed',Arial,sans-serif; font-weight:600; font-size:22px;
  line-height:1.2; letter-spacing:.03em; text-transform:uppercase;
  display:flex; align-items:center; gap:10px;
  padding-bottom:8px; border-bottom:1px solid var(--line);
}
.area-count{
  font-family:'IBM Plex Mono',monospace; font-size:12px; font-weight:500;
  color:var(--chalk-faint); font-variant-numeric:tabular-nums;
}
.items{list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:8px;}
.item{
  background:var(--ink-1); border:1px solid var(--line); border-left:3px solid var(--line-strong);
  border-radius:var(--r-md); padding:14px 16px; display:flex; flex-direction:column; gap:8px;
}
.item.state-dark{border-left-color:var(--flare);}
.item.state-partial{border-left-color:var(--warn);}
.item.state-discuss{border-left-color:var(--chalk-faint);}
.item-top{display:flex; align-items:center; gap:8px; flex-wrap:wrap;}
.id{
  font-family:'IBM Plex Mono',monospace; font-weight:600; font-size:13px;
  color:var(--chalk-dim); font-variant-numeric:tabular-nums;
}
.chip{
  font-size:11px; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
  padding:2px 7px; border-radius:999px; border:1px solid currentColor;
}
.sev-bug{color:var(--neg);} .sev-polish{color:var(--ice);} .sev-idea{color:var(--warn);}
.st-dark{color:var(--flare);} .st-partial{color:var(--warn);} .st-discuss{color:var(--chalk-dim);}
.plain{margin:0; color:var(--chalk); max-width:66ch;}
.meta{
  margin:0; font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--chalk-faint);
  font-variant-numeric:tabular-nums; display:flex; flex-wrap:wrap; gap:8px; align-items:baseline;
}
.note{color:var(--flare); font-family:Archivo,sans-serif; font-size:12px;}
.state-partial .note{color:var(--warn);}
.state-open .note, .state-discuss .note{color:var(--chalk-dim);}
.foot{border-top:1px solid var(--line); padding-top:16px;}
.foot p{margin:0; color:var(--chalk-faint); font-size:13px;}
code{font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--chalk-dim);}
@media (max-width:600px){
  .wrap{padding:32px 16px 48px;} h1{font-size:34px;} .stat{flex-basis:100px;}
}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=PROD_BASE)
    ap.add_argument("--out", default=str(SKILL_DIR / "board.html"))
    ap.add_argument("--check", action="store_true", help="report missing descriptions, write nothing")
    args = ap.parse_args()

    items = [i for i in fetch_all(args.base) if (i.get("status") or "new") in OPEN_STATUSES]
    items.sort(key=lambda i: i["id"])
    desc = load_descriptions()

    missing = [str(i["id"]) for i in items if str(i["id"]) not in desc]
    stale = [k for k in desc if k not in {str(i["id"]) for i in items}]

    if missing:
        print(f"MISSING DESCRIPTIONS ({len(missing)}): {', '.join('#'+m for m in missing)}", file=sys.stderr)
        for i in items:
            if str(i["id"]) in missing:
                print(f"  #{i['id']} [{i.get('severity')}] {i.get('screen')} v{i.get('app_version')} "
                      f"{i.get('username')}\n    {i.get('text','').strip()}", file=sys.stderr)
    if stale:
        print(f"CLOSED SINCE LAST BUILD ({len(stale)}): {', '.join('#'+s for s in sorted(stale))} "
              f"— they drop off the board automatically; prune descriptions.json when convenient.",
              file=sys.stderr)
    if args.check:
        sys.exit(1 if missing else 0)

    Path(args.out).write_text(render(items, desc, missing), encoding="utf-8")
    print(f"wrote {args.out} — {len(items)} open items, {len(missing)} without a description")


if __name__ == "__main__":
    main()
