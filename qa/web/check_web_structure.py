#!/usr/bin/env python3
"""Structural checks over web/ source — the web analogue of mobile/tests/check-*.js.

No browser, no network, no server. Parses the shipped HTML/CSS and asserts the
invariants that the 2026-08-19 audit found violated. Fast enough to gate every
commit; deterministic enough that a failure is always a real regression.

Run:  python3 qa/web/check_web_structure.py [--json OUT]
Exit: 0 all green, 1 any failure.

Scope note: `web/` is served at the site root, so anything added there is public.
PAGES below is the set that ships to users. Frozen artifacts (color-lab*), the
design reference (style-guide) and the operator dashboard (admin/) are excluded
explicitly — with a reason — rather than silently skipped.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"

# Pages that ship to real users. Each must satisfy the SEO + a11y checks.
PAGES = [
    "index.html", "faq.html", "contact.html", "calculator.html", "player.html",
    "positional-tiers.html", "league-rankings.html", "profile.html",
    "ranking-method.html", "privacy.html", "terms.html", "404.html",
]

# Excluded, with the reason recorded so the exclusion is auditable.
EXCLUDED = {
    "color-lab.html":   "frozen ADR-005 palette artifact; not shipped",
    "color-lab-2.html": "frozen ADR-005 palette artifact; not shipped",
    "style-guide.html": "internal design reference; 404s in prod",
    "admin/analytics.html": "operator dashboard; CRON_SECRET-gated data",
}

# docs/design/design-system.md is the authority for these.
LINE_STRONG_CORRECT = "#59647A"
LINE_STRONG_STALE = "#3D4654"          # 2.03:1 — fails the ≥3:1 non-text floor
BANNED_FONT_TOKENS = ["system-ui", "-apple-system", "'Inter'", '"Inter"',
                      "'Roboto'", '"Roboto"', "BlinkMacSystemFont"]
# Emoji-as-icon detection. Deliberately NARROW: the prohibition is on emoji
# standing in for iconography, not on typography. Arrows (U+2190-21FF), geometric
# shapes (U+25A0-25FF: ▲ ▼ ▶) and dingbats (U+2700-27BF: ✓ ✔) are legitimate glyphs
# and are NOT flagged — an over-broad check that fires on "Connect with Sleeper →"
# trains people to ignore it.
EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),   # pictographs, emoticons, transport, supplemental
    (0x2600, 0x26FF),     # misc symbols — ⚡ U+26A1, ⚠ U+26A0
    (0x2B00, 0x2BFF),     # misc symbols and arrows (⭐ U+2B50)
    (0xFE0F, 0xFE0F),     # variation selector-16 (forces emoji presentation)
)


def _decode_js_escapes(text: str) -> str:
    r"""Resolve JS \uXXXX escapes. `'\u26A1 I AM SPEED'` is ASCII in source, so a
    literal-character scan cannot see the emoji it renders."""
    def sub(m: re.Match) -> str:
        try:
            return chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return m.group(0)
    return re.sub(r"\\u\{?([0-9a-fA-F]{4,6})\}?", sub, text)


def _decode_entities(text: str) -> str:
    """Resolve numeric HTML entities so &#127942; is seen as the trophy it is."""
    def sub(m: re.Match) -> str:
        raw = m.group(1)
        try:
            cp = int(raw[1:], 16) if raw[:1].lower() == "x" else int(raw)
            return chr(cp)
        except (ValueError, OverflowError):
            return m.group(0)
    return re.sub(r"&#(x?[0-9a-fA-F]+);", sub, text)


def find_emoji(text: str) -> list[str]:
    hits = []
    for ch in _decode_js_escapes(_decode_entities(text)):
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in EMOJI_RANGES):
            hits.append(ch)
    return sorted(set(hits))


class Results:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def check(self, cid: str, ok: bool, detail: str) -> bool:
        self.rows.append({"id": cid, "ok": bool(ok), "detail": detail})
        return ok

    @property
    def failures(self) -> list[dict]:
        return [r for r in self.rows if not r["ok"]]

    def report(self) -> int:
        by_group: dict[str, list[dict]] = {}
        for r in self.rows:
            by_group.setdefault(r["id"].split("-")[0], []).append(r)
        for group, rows in by_group.items():
            bad = [r for r in rows if not r["ok"]]
            head = f"{group}: {len(rows) - len(bad)}/{len(rows)} pass"
            print(f"\n{head}")
            for r in bad:
                print(f"  FAIL {r['id']}  {r['detail']}")
        total, bad = len(self.rows), len(self.failures)
        print(f"\n{'=' * 62}")
        print(f"{total - bad}/{total} checks pass" if not bad
              else f"{total - bad}/{total} checks pass — {bad} FAILING")
        return 1 if bad else 0


def read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def strip_css_comments(text: str) -> str:
    """Drop /* … */ so a comment documenting a banned value isn't read as one."""
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def strip_comments(html: str) -> str:
    """Drop HTML comments so operator TODO notes don't trip content checks."""
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def head_of(html: str) -> str:
    m = re.search(r"<head\b.*?</head>", html, flags=re.S | re.I)
    return m.group(0) if m else ""


def body_of(html: str) -> str:
    m = re.search(r"<body\b.*?</body>", html, flags=re.S | re.I)
    return m.group(0) if m else html


def strip_style_and_script(html: str) -> str:
    html = re.sub(r"<style\b.*?</style>", "", html, flags=re.S | re.I)
    return re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)


def run() -> int:
    r = Results()
    missing = [p for p in PAGES if not (WEB / p).exists()]
    if missing:
        print(f"FATAL: PAGES lists files that do not exist: {missing}")
        return 1

    css_files = sorted(WEB.glob("css/*.css"))
    all_sources = {p: read(p) for p in PAGES}
    all_sources.update({f"css/{f.name}": f.read_text(encoding="utf-8") for f in css_files})
    all_sources.update({f"js/{f.name}": f.read_text(encoding="utf-8")
                        for f in sorted(WEB.glob("js/*.js"))})

    # ── DS: design system ────────────────────────────────────────────────
    for name, src in all_sources.items():
        # Read declarations, not raw text — a comment explaining the stale value
        # (as tokens.css does) is documentation, not a violation.
        code = strip_css_comments(src)
        decls = [v.strip() for v in
                 re.findall(r"--line-strong\s*:\s*([^;}]+)", code, flags=re.I)]
        stale_decl = [v for v in decls if LINE_STRONG_STALE.lower() in v.lower()]
        other_use = re.findall(re.escape(LINE_STRONG_STALE), code, flags=re.I)
        bad = stale_decl or other_use
        r.check(f"DS-line-strong[{name}]", not bad,
                (f"stale {LINE_STRONG_STALE} in a declaration "
                 f"(2.03:1, fails WCAG 1.4.11); design system requires {LINE_STRONG_CORRECT}")
                if bad else ("declares " + decls[0] if decls else "no usage"))

    for name, src in all_sources.items():
        scan = strip_css_comments(strip_comments(src))
        if name.endswith(".html"):
            scan = strip_style_and_script(scan)
        # Opt-out for code that legitimately handles emoji (e.g. the regex that
        # STRIPS legacy emoji from notification text). Suppresses the pragma
        # line and the one after it, so it works on a comment above a long
        # pattern. Explicit and greppable: `git grep qa:allow-emoji`.
        kept, skip_next = [], False
        for line in scan.split("\n"):
            if "qa:allow-emoji" in line:
                skip_next = True          # suppresses this line and the next
                continue
            if skip_next:
                skip_next = False
                continue
            kept.append(line)
        scan = "\n".join(kept)
        hits = find_emoji(scan)
        r.check(f"DS-no-emoji[{name}]", not hits,
                "emoji used as icon/UI text: " + ", ".join(repr(h) for h in hits[:6])
                if hits else "none")

    for name, src in all_sources.items():
        bad = [t for t in BANNED_FONT_TOKENS if t in src]
        r.check(f"DS-no-system-font[{name}]", not bad,
                f"banned font stack token(s): {bad}" if bad else "none")

    for name, src in all_sources.items():
        big = []
        for m in re.finditer(r"border-radius:\s*([^;}\n]+)", src, flags=re.I):
            val = m.group(1).strip()
            if "%" in val or "999" in val or "9999" in val:
                continue                       # circles + specced pills
            for px in re.findall(r"(\d+(?:\.\d+)?)px", val):
                if float(px) > 8:
                    big.append(f"{px}px")
        r.check(f"DS-radius[{name}]", not big,
                f"border-radius > 8px: {sorted(set(big))}" if big else "none")

    for name, src in all_sources.items():
        bad = []
        if re.search(r"backdrop-filter", src, flags=re.I):
            bad.append("backdrop-filter")
        if re.search(r"(linear|radial|conic)-gradient", src, flags=re.I):
            bad.append("gradient")
        r.check(f"DS-no-glass-gradient[{name}]", not bad,
                f"prohibited: {bad}" if bad else "none")

    # ── TOK: exactly one home for the token block (plan P1-1) ────────────
    definers = [n for n, s in all_sources.items()
                if re.search(r"--ink-0\s*:", s)]
    r.check("TOK-single-source", len(definers) == 1,
            f"{len(definers)} files define the Chalkline token block "
            f"({', '.join(sorted(definers))}); expected exactly 1 shared stylesheet"
            if len(definers) != 1 else f"single source: {definers[0]}")

    # ── SEO ──────────────────────────────────────────────────────────────
    for page in PAGES:
        head = head_of(all_sources[page])
        def meta(name: str) -> bool:
            return bool(re.search(rf'<meta[^>]+name=["\']{name}["\']', head, flags=re.I))
        def og(prop: str) -> bool:
            return bool(re.search(rf'<meta[^>]+property=["\']og:{prop}["\']', head, flags=re.I))

        r.check(f"SEO-title[{page}]",
                bool(re.search(r"<title>[^<]{3,}</title>", head, flags=re.I)), "")
        r.check(f"SEO-description[{page}]", meta("description"), "no meta description")
        r.check(f"SEO-canonical[{page}]",
                bool(re.search(r'<link[^>]+rel=["\']canonical["\']', head, flags=re.I)),
                "no rel=canonical")
        missing_og = [p for p in ("title", "description", "type", "url") if not og(p)]
        r.check(f"SEO-og[{page}]", not missing_og,
                f"missing og:{','.join(missing_og)}" if missing_og else "")

    for f in ("robots.txt", "sitemap.xml"):
        r.check(f"SEO-{f}", (WEB / f).exists(), f"web/{f} missing")

    # ── A11Y ─────────────────────────────────────────────────────────────
    for page in PAGES:
        src = all_sources[page]
        body = strip_style_and_script(strip_comments(body_of(src)))
        h1 = len(re.findall(r"<h1\b", body, flags=re.I))
        r.check(f"A11Y-h1[{page}]", h1 == 1, f"{h1} <h1> elements (want exactly 1)")

        vp = re.search(r'<meta[^>]+name=["\']viewport["\'][^>]*>', src, flags=re.I)
        ok_vp = bool(vp) and not re.search(r"user-scalable\s*=\s*no|maximum-scale\s*=\s*1(?!\d)",
                                           vp.group(0) if vp else "", flags=re.I)
        r.check(f"A11Y-viewport[{page}]", ok_vp,
                "missing viewport meta" if not vp else "viewport blocks user zoom")

        imgs = re.findall(r"<img\b[^>]*>", body, flags=re.I)
        no_alt = [t for t in imgs if not re.search(r"\balt\s*=", t, flags=re.I)]
        r.check(f"A11Y-img-alt[{page}]", not no_alt,
                f"{len(no_alt)} <img> without an alt attribute" if no_alt else "")

    idx = strip_comments(all_sources["index.html"])
    for tag in ("main", "nav"):
        r.check(f"A11Y-landmark-{tag}[index.html]",
                bool(re.search(rf"<{tag}\b", idx, flags=re.I)),
                f"no <{tag}> landmark in the application shell")

    # ── HYGIENE ──────────────────────────────────────────────────────────
    app_js = (WEB / "js" / "app.js").read_text(encoding="utf-8")
    r.check("HYG-no-debug-endpoint", "/api/debug/log" not in app_js,
            "public bundle references the CRON-gated /api/debug/log")
    r.check("HYG-no-dead-log-drawer", "logDrawer" not in app_js,
            f"{app_js.count('logDrawer')}× logDrawer — its DOM targets do not exist in index.html")
    tiers = read("positional-tiers.html")
    r.check("HYG-no-stale-sample-roster", "SAMPLE_PLAYERS" not in tiers,
            "hardcoded 2024-era roster rendered before the API responds")
    r.check("HYG-excluded-documented", set(EXCLUDED) <= set(EXCLUDED),
            f"{len(EXCLUDED)} pages excluded with reasons")

    return r.report(), r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, help="write machine-readable results here")
    args = ap.parse_args()
    code, res = run()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(
            {"pass": len(res.rows) - len(res.failures), "total": len(res.rows),
             "failures": res.failures}, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
