#!/usr/bin/env python3
"""Structural check for web/ranking-method.html (C7, 2026-10-27).

WHY THIS EXISTS. The page is the read-more for the app's "How trades are
priced" help sheet. It drifted from the app: it recommended a trio "Journey"
the app no longer has and never explained pricing. It also drew the methods
as raised tiles that looked tappable on a page that cannot open any app
screen. This pins:

  APP    every [app] string is verbatim with the app source it comes from:
         the help-sheet body (TradesScreen.tsx), the chooser model's titles,
         roles, bodies and Quick set follow-on (rankChooserModel.ts), and
         RankHome's "Then, if you want:" lead-in. Trends stays out.
  OLD    the old Journey / three-option copy is gone.
  FLAT   no card construction: no raised fills, borders other than the
         hairline separator, radius, shadow, cursor:pointer or :hover.
  TAP    nothing interactive except body links (none today) and the standard
         site footer; no link or control in the header or the methods lists.
  FOOT   the footer is web/contact.html's `.foot` verbatim: the same links
         (Home · FAQ · Privacy · Terms) and the same two CSS rules.
  ICE    ice only on the TickLabel tick, the logotype period and the focus
         ring; flare only on the "Recommended" text tag; no raw hex.

HONEST LABEL (G-035): this reads source text. It proves the strings and the
CSS shape, not how the page renders. The manual width check is in
docs/plans/ranking-method-page/scope.md.

Run:  python3 qa/web/check_ranking_method_page.py     (exit 0 green, 1 red)
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "web" / "ranking-method.html"
TRADES = ROOT / "mobile" / "src" / "screens" / "TradesScreen.tsx"
MODEL = ROOT / "mobile" / "src" / "navigation" / "rankChooserModel.ts"
RANK_HOME = ROOT / "mobile" / "src" / "screens" / "RankHomeScreen.tsx"

failures: list[str] = []


def check(name: str, ok: bool, why: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n      {why}"))
    if not ok:
        failures.append(name)


def js_concat(expr: str) -> str:
    """Join a JS `'a' + "b" + 'c'` string expression."""
    parts = re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", expr)
    return "".join(a or b for a, b in parts).replace("\\'", "'")


src = PAGE.read_text(encoding="utf-8")
style = "\n".join(re.findall(r"<style\b[^>]*>(.*?)</style>", src, flags=re.S | re.I))
style_code = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
body = re.search(r"<body\b.*?</body>", src, flags=re.S | re.I).group(0)
body_code = re.sub(r"<!--.*?-->", "", body, flags=re.S)
text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body_code))).strip()
# Text with tags removed but no extra spaces inserted (inline spans join words).
flat = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", body_code))).strip()

# ── APP: verbatim strings ───────────────────────────────────────────────────
trades = TRADES.read_text(encoding="utf-8")
m = re.search(r'title="How trades are priced"\s*body=\{(.*?)\}\s*readMoreUrl', trades, flags=re.S)
help_body = js_concat(m.group(1)) if m else ""
check("APP-help-body-found", bool(help_body), "could not read the HelpSheet body in TradesScreen.tsx")
paras = [html.unescape(re.sub(r"<[^>]+>", "", p)).strip()
         for p in re.findall(r'<p class="prose">(.*?)</p>', body_code, flags=re.S)]
check("APP-help-body-verbatim", " ".join(paras) == help_body,
      f"pricing prose != the help sheet body\n      page: {' '.join(paras)!r}\n      app:  {help_body!r}")

model = MODEL.read_text(encoding="utf-8")
entries = re.findall(r"\{\s*(pref:.*?key:\s*'\w+',)\s*\}", model, flags=re.S)
app_strings = []
for e in entries:
    key = re.search(r"key:\s*'(\w+)'", e).group(1)
    if key == "trends":
        trends_title = js_concat(re.search(r"title:\s*([^\n]+)", e).group(1))
        trends_body = js_concat(re.search(r"body:\s*(.*?),\n", e, flags=re.S).group(1))
        continue
    for field in ("title", "role", "body", "sub"):
        fm = re.search(rf"\b{field}:\s*(.*?),\n\s*(?://.*\n\s*)?(?:\w+:|$)", e, flags=re.S)
        if fm:
            app_strings.append((f"{key}.{field}", js_concat(fm.group(1))))
check("APP-model-read", len(app_strings) == 14,
      f"expected 14 chooser strings (3 primary × title/role/body, Quick set's sub, "
      f"2 more × title/body), read {len(app_strings)}: {[k for k, _ in app_strings]}")
for key, value in app_strings:
    check(f"APP-verbatim[{key}]", value in flat, f"not verbatim on the page: {value!r}")
lead = re.search(r"subLead\}>([^<]+)</Text>", RANK_HOME.read_text(encoding="utf-8"))
lead_text = lead.group(1).strip() if lead else ""
check("APP-verbatim[then-lead-in]", bool(lead_text) and lead_text in flat,
      f"RankHome's lead-in {lead_text!r} is not on the page")
check("APP-trends-left-out", trends_title not in text and trends_body not in text,
      "the chooser's Trends row (a view, not a way to rank) is on the page")

# ── OLD: the retired copy is gone ───────────────────────────────────────────
old = [s for s in ("Journey", "Let me set", "Guide me", "Pick the method that works best",
                   "power every trade suggestion", "Dynasty Trade Finder</div>")
       if s in body_code]
check("OLD-copy-removed", not old, f"old copy still present: {old}")

# ── FLAT: no card construction ──────────────────────────────────────────────
flat_bad = []
for pat, what in ((r"--ink-[123]\b", "raised ink fill"), (r"border-radius", "radius"),
                  (r"box-shadow", "shadow"), (r"cursor\s*:\s*pointer", "cursor:pointer"),
                  (r":hover", ":hover"), (r"\bborder(?!-top)\s*:", "border other than the top hairline"),
                  (r"background\s*:\s*var\(--(?!ink-0|ice)\w", "background other than the page")):
    if re.search(pat, style_code):
        flat_bad.append(what)
tops = re.findall(r"border-top\s*:\s*([^;]+);", style_code)
if any("var(--line)" not in t for t in tops):
    flat_bad.append(f"border-top not a --line hairline: {tops}")
check("FLAT-no-cards", not flat_bad, f"card construction in the page CSS: {flat_bad}")

# ── TAP: nothing interactive except body links and the site footer ─────────
interactive = re.findall(r"<(a|button|input|select|textarea|details|summary|label)\b[^>]*>", body_code, flags=re.I)
attrs = re.findall(r"\b(onclick|onkeydown|tabindex|role=\"button\"|contenteditable)\b", body_code, flags=re.I)
non_link = [t for t in interactive if t.lower() != "a"]
check("TAP-no-controls", not non_link and not attrs,
      f"interactive elements: tags={non_link} attrs={attrs}")


def foot_links(markup: str) -> list[tuple[str, str]]:
    m = re.search(r'<div class="foot">(.*?)</div>', markup, flags=re.S)
    return re.findall(r'<a href="([^"]*)">([^<]*)</a>', m.group(1)) if m else []


all_links = len(re.findall(r"<a\b", body_code, flags=re.I))
prose_links = sum(len(re.findall(r"<a\b", para, flags=re.I)) for para in
                  re.findall(r'<p class="(?:prose|method-line|subtitle)[^"]*">(.*?)</p>', body_code, flags=re.S))
footer = foot_links(body_code)
stray = all_links - prose_links - len(footer)
check("TAP-links-only-in-body-or-footer", stray == 0,
      f"{stray} link(s) outside body copy and the site footer")
header = re.search(r"<header\b.*?</header>", body_code, flags=re.S | re.I)
lists = re.findall(r'<ul class="methods".*?</ul>', body_code, flags=re.S)
chrome = [frag for frag in ([header.group(0)] if header else []) + lists
          if re.search(r"<(a|button|input|select|textarea)\b", frag, flags=re.I)]
check("TAP-header-and-methods-inert", bool(header) and len(lists) == 2 and not chrome,
      f"a link or control inside the header or a methods list ({len(chrome)} fragment(s))")
check("TAP-logotype-plain-text",
      bool(re.search(r'<div class="wordmark">FLEECED<span>\.</span></div>', body_code)),
      "the FLEECED. logotype is not the plain-text <div class=\"wordmark\">")

# ── FOOT: verbatim web/contact.html site footer ─────────────────────────────
contact = (ROOT / "web" / "contact.html").read_text(encoding="utf-8")
want = foot_links(contact)
check("FOOT-links-match-contact", footer == want and len(want) == 4,
      f"footer links {footer} != contact.html's {want}")
rule = lambda text, sel: re.findall(rf"^\s*{re.escape(sel)}\s*\{{([^}}]*)\}}", text, flags=re.M)
check("FOOT-style-matches-contact",
      rule(style, ".foot") == rule(contact, ".foot") != [] and
      rule(style, ".foot a") == rule(contact, ".foot a") != [],
      "the .foot / .foot a rules differ from web/contact.html's")

# ── ICE / FLARE / HEX ───────────────────────────────────────────────────────
rules = re.findall(r"([^{}]+)\{([^{}]*)\}", style_code)
ice_sel = sorted({sel.strip() for sel, decl in rules if "var(--ice" in decl})
check("ICE-only-tick-logo-focus",
      set(ice_sel) <= {".tick-label::before", ".wordmark span", ":focus-visible"},
      f"ice used on: {ice_sel}")
flare_sel = sorted({sel.strip() for sel, decl in rules if "var(--flare" in decl})
check("FLARE-only-recommended", flare_sel == [".tag-recommended"], f"flare used on: {flare_sel}")
hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", style_code + re.sub(r'href="[^"]*"', "", body_code))
check("HEX-none", not hexes, f"raw hex in the page: {hexes}")
rec = re.findall(r'class="tag tag-recommended">([^<]+)<', body_code)
first_other = body_code.find('class="method-name">', body_code.find("Quick set") + 1)
check("TAG-recommended-on-quickset-only", rec == ["Recommended"] and
      0 <= body_code.find("tag-recommended") < first_other,
      f"Recommended tags: {rec} (want exactly one, on Quick set's row)")

print(f"\n{'all ranking-method page checks passed' if not failures else f'{len(failures)} FAILING'}")
sys.exit(1 if failures else 0)
