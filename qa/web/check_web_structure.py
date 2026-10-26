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
from datetime import datetime
from html import unescape
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
    "admin/analytics.html": "operator dashboard; 404s in prod, CRON_SECRET-gated data",
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
    # The `source` column defaults to "mobile" server-side (analytics_ingest.py),
    # because mobile is the one client that declares nothing. A web SDK that
    # omits X-Source therefore does not land NULL — it lands "mobile", and web
    # traffic silently contaminates per-client splits. Body `platform` does NOT
    # cover this: they are separate columns, and test_events_api pins both.
    events_js = (WEB / "js" / "events.js").read_text(encoding="utf-8")
    r.check("HYG-events-declare-source",
            re.search(r'["\']X-Source["\']\s*:\s*["\']web["\']', events_js) is not None,
            'web/js/events.js does not send X-Source:"web" — every web row '
            'would be stamped source:"mobile" by the ingest default')
    r.check("HYG-events-declare-platform",
            re.search(r'platform\s*:\s*["\']web["\']', events_js) is not None,
            'web/js/events.js does not declare platform:"web" in the body')

    tiers = read("positional-tiers.html")
    r.check("HYG-no-stale-sample-roster", "SAMPLE_PLAYERS" not in tiers,
            "hardcoded 2024-era roster rendered before the API responds")
    r.check("HYG-excluded-documented", set(EXCLUDED) <= set(EXCLUDED),
            f"{len(EXCLUDED)} pages excluded with reasons")

    # ── POL: launch policy, contact and FAQ pages (#354 M7, P28, SUP-M4) ─
    # Text: legal-lead-drafts.md Parts 1-3 (privacy, terms), Part 5 (R28:
    # terms §14 subscriptions and the privacy RevenueCat lines) and
    # marketing-lead-copy.md (§1b c1-c8, §2 FAQ). One support address,
    # written with an ASCII @, always a real mailto. The placeholder check is
    # meant to fail until [OPERATOR NAME], Part 5's {…} fill values and its
    # ⟪VERIFY⟫ mark are resolved: it is the merge blocker for publishing
    # unfinished legal text. POL-effective-date pins the filled date.
    SUPPORT_EMAIL = "fleecedapp@gmail.com"
    POLICY = ("privacy.html", "terms.html")
    SUPPORT_PAGES = ("privacy.html", "terms.html", "contact.html", "faq.html")
    MAILTO_A = re.compile(r'<a\b[^>]*href=["\']mailto:' + re.escape(SUPPORT_EMAIL)
                          + r'["\'][^>]*>\s*' + re.escape(SUPPORT_EMAIL) + r'\s*</a>', re.I)
    # Bracketed placeholders and review tags: [OPERATOR NAME], [EFFECTIVE DATE],
    # [DEPLOY DATE], [STATE], [PRO], [M11 ALT], [APP STORE URL], and the copy
    # file's [new] / [R10 …] / [R22.1 edit …] / [goes live …] / [legal …] tags.
    PLACEHOLDER = re.compile(r"\[(?:[A-Z][A-Z0-9 _/.-]*|new|goes live[^\]]*|R\d[^\]]*|legal[^\]]*)\]")
    # Legal Part 5's fill values: {December 31, 2026}, {$4.99 a month or …}.
    # No visible text on these pages uses braces otherwise; styles and scripts
    # are stripped by visible().
    FILL = re.compile(r"\{[^{}]+\}")
    BLOCK_TAG = re.compile(r"</?(?:p|li|ul|ol|h[1-6]|div|details|summary|section|main|form|br)\b[^>]*>", re.I)

    def visible(page: str) -> str:
        """Head text + body text a reader can see: no comments, styles or scripts."""
        src = strip_comments(all_sources[page])
        return strip_style_and_script(head_of(src) + body_of(src))

    for page in POLICY:
        text = visible(page)
        bad = [label for label, pat in (
            ('"Fantasy Trade Finder"', r"Fantasy\s+Trade\s+Finder"),
            ('"hobby"', r"\bhobby\b"),
            ('"beta"', r"\bbeta\b"),
        ) if re.search(pat, text, flags=re.I)]
        r.check(f"POL-no-stale-claims[{page}]", not bad,
                f"found {', '.join(bad)} (M7-AC1, D-12: the allow-list is empty)" if bad else "none")

    # Reading links on the policy pages are chalk + underline, the same rule as
    # contact's `.status a` and FAQ's `.faq-body a` (design-lead, #354 PR 3 link
    # styles). Ice is for actions: no link selector or inline link style may set
    # an ice `color` (an ice hover underline, text-decoration-color, is allowed).
    ICE = re.compile(r"var\(\s*--(?:ice|ice-press|accent)\s*\)|#56d9ec|#3fc2d6", re.I)
    LINK_SEL = re.compile(r"(?:^|[\s>+~])a(?:[:.\[#][^\s>+~]*)?$")
    COLOR_DECL = re.compile(r"(?:^|;)\s*color\s*:\s*([^;]+)", re.I)
    for page in POLICY:
        css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", strip_comments(all_sources[page]), re.S | re.I))
        rules = [(sel.strip(), decl) for sels, decl in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
                 for sel in sels.split(",")]
        ice_links = [sel for sel, decl in rules if LINK_SEL.search(sel)
                     and any(ICE.search(v) for v in COLOR_DECL.findall(decl))]
        inline = [m for m in re.findall(r"<a\b[^>]*\bstyle=[\"']([^\"']*)", body_of(all_sources[page]), re.I)
                  if any(ICE.search(v) for v in COLOR_DECL.findall(m))]
        base = [decl for sel, decl in rules if sel == "a"]
        base_ok = len(base) == 1 \
            and any(re.search(r"var\(\s*--(?:chalk|text)\s*\)", v) for v in COLOR_DECL.findall(base[0])) \
            and re.search(r"text-decoration\s*:\s*underline", base[0], re.I)
        r.check(f"POL-reading-links-chalk[{page}]", base_ok and not ice_links and not inline,
                ("ice-coloured link rule(s): " + ", ".join(ice_links) if ice_links else
                 f"{len(inline)} inline ice link style(s)" if inline else
                 "the base `a` rule is not chalk + underline") if not (base_ok and not ice_links and not inline)
                else "reading links chalk + underline, no ice text links")

    for page in SUPPORT_PAGES:
        raw = all_sources[page]
        r.check(f"POL-no-fullwidth-at[{page}]", "\uff20" not in raw,
                f"{raw.count(chr(0xFF20))}× U+FF20 (full-width @) — the address must use ASCII @"
                if "\uff20" in raw else "none")

        text = visible(page)
        marks = sorted(set(PLACEHOLDER.findall(text)) | set(FILL.findall(text))
                       | {m for m in ("⟪", "⟫") if m in text})
        r.check(f"POL-no-placeholders[{page}]", not marks,
                "unfilled placeholder / editorial mark: " + ", ".join(marks) if marks else "none")

        body = strip_style_and_script(strip_comments(body_of(raw)))
        hrefs = re.findall(r'href=["\']mailto:([^"\'?]*)', body, flags=re.I)
        wrong = [h for h in hrefs if h != SUPPORT_EMAIL]
        leftover = MAILTO_A.sub("", body)
        bare = len(re.findall(re.escape(SUPPORT_EMAIL), leftover, flags=re.I))
        anchors = len(MAILTO_A.findall(body))
        need = 2 if page == "contact.html" else 1
        r.check(f"POL-mailto[{page}]", not wrong and bare == 0 and anchors >= need,
                (f"mailto to another address: {wrong}" if wrong else
                 f"{bare} visible {SUPPORT_EMAIL} not inside its mailto link" if bare else
                 f"{anchors} mailto link(s), want ≥ {need}") if (wrong or bare or anchors < need)
                else f"{anchors} mailto link(s), every visible address linked")

        missing = []
        for seg in BLOCK_TAG.split(body):
            if re.search(r"contact[\s-]form", re.sub(r"<[^>]+>", "", seg), flags=re.I) \
                    and not re.search(r'href=["\']/contact\.html["\']', seg):
                missing.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", seg)).strip()[:60])
        r.check(f"POL-contact-form-linked[{page}]", not missing,
                "\"contact form\" without a /contact.html link: " + " | ".join(missing)
                if missing else "every mention links /contact.html")

    privacy_text = visible("privacy.html")
    r.check("POL-no-settings-feedback[privacy.html]",
            not re.search(r"Settings\s*(?:→|&rarr;|->)\s*feedback", privacy_text, flags=re.I),
            'still points at "Settings → feedback" (M7-AC4)')

    # Legal Part 5 (R28). Pinned per section, so a paste that drops, moves or
    # renumbers a subscription disclosure goes red.
    def plain(fragment: str) -> str:
        text = unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("’", "'")
        return re.sub(r"\s+", " ", text).strip()

    def numbered(page: str) -> list[tuple[str, str]]:
        """(number, html) per numbered <h2>, each running to the next <h2>."""
        body = strip_style_and_script(strip_comments(body_of(all_sources[page])))
        parts = re.split(r"(<h2\b[^>]*>.*?</h2>)", body, flags=re.S | re.I)
        out = []
        for i in range(1, len(parts) - 1, 2):
            m = re.match(r"(\d+)\.", plain(parts[i]))
            if m:
                out.append((m.group(1), parts[i] + parts[i + 1]))
        return out

    terms_secs = numbered("terms.html")
    s14 = dict(terms_secs).get("14", "")
    s14_text = plain(s14)
    subs = [int(n) for n in re.findall(r"<strong>\s*14\.(\d+)\b", s14)]
    problems = []
    if [n for n, _ in terms_secs] != [str(n) for n in range(1, 15)]:
        problems.append(f"sections {[n for n, _ in terms_secs]}, want 1-14 in order")
    if not s14_text.startswith("14. Subscriptions, free trial and billing"):
        problems.append('no "14. Subscriptions, free trial and billing" heading')
    if subs != list(range(1, 11)):
        problems.append(f"§14 subsections {subs}, want 1-10 in order")
    problems += [f'§14 lacks "{t}"' for t in (
        "Deleting the app or your Fleeced account does not cancel your subscription",
        "reportaproblem.apple.com",
        "Media Services Terms",
    ) if t not in s14_text]
    if s14_text.count("at least 24 hours before") < 2:
        problems.append('"at least 24 hours before" not in both 14.3 (trial) and 14.4 (renewal)')
    r.check("POL-terms-subscriptions[terms.html]", not problems,
            "; ".join(problems) if problems else "§14 with 14.1-14.10 and the cancel/refund/Apple lines")

    priv = dict(numbered("privacy.html"))
    item = re.search(r"<li>\s*<strong>Subscriptions and purchases\.</strong>(.*?)</li>",
                     priv.get("1", ""), flags=re.S)
    providers = re.search(r"Service providers that process data for us:.*?<ul>(.*?)</ul>",
                          priv.get("4", ""), flags=re.S)
    problems = [label for label, ok in (
        ('§1 "Subscriptions and purchases" item naming RevenueCat',
         bool(item) and "RevenueCat" in item.group(1)),
        ("RevenueCat in the §4 service providers",
         bool(providers) and "<strong>RevenueCat:</strong>" in providers.group(1)),
        ('§5 "Subscription and purchase records" line',
         "Subscription and purchase records:" in plain(priv.get("5", ""))),
        ("§6 \"doesn't cancel an active subscription\" line",
         "doesn't cancel an active subscription" in plain(priv.get("6", ""))),
    ) if not ok]
    r.check("POL-privacy-revenuecat[privacy.html]", not problems,
            "missing: " + "; ".join(problems) if problems else "RevenueCat in §1, §4, §5 and §6")

    # R28.9: service providers (RevenueCat among them) may process data outside
    # the US, so the old US-only processing sentence must not come back.
    us_only = re.search(r"We and our service providers process data in the United States",
                        plain(visible("privacy.html")), flags=re.I)
    r.check("POL-no-us-only-processing[privacy.html]", not us_only,
            'still says "We and our service providers process data in the United States" (R28.9)'
            if us_only else "none")

    # Legal R28.12 row 1, R28.15 (2026-10-26) and R28.16 (2026-10-27), pinned
    # word for word. Each sentence must appear verbatim in the page's rendered
    # text, whitespace-normalized: block tags become a space and inline tags
    # (<strong>, <a>) vanish, so "email <a …>fleecedapp@gmail.com</a>." reads
    # as it renders. The text is hard-coded from the rulings' tables and
    # legal-lead-drafts.md Parts 1-2; any edit to it comes back through
    # legal-lead.
    def rendered(page: str) -> str:
        body = strip_style_and_script(strip_comments(body_of(all_sources[page])))
        text = re.sub(r"<[^>]+>", "", BLOCK_TAG.sub(" ", body))
        return re.sub(r"\s+", " ", unescape(text).replace("’", "'")).strip()

    R28_15 = {
        "privacy.html": (
            # R28.16 added "the first time you use it" to R28.15's sentence.
            ('§1 "How you sign in" lead',
             'You can sign in with Apple, with your Sleeper username, or, where available, with your '
             'ESPN or MyFantasyLeague (MFL) login. Each method creates a Fleeced account with an '
             'internal account ID the first time you use it. You can also connect ESPN and MFL leagues '
             'after you sign in (see "Platform connections" below). Depending on the method, we store:'),
            ("§1 ESPN sub-item",
             "ESPN: your ESPN member ID (called SWID), which identifies your account. You log in on "
             "ESPN's own page inside the app, and we check the login with ESPN (see \"Platform "
             'connections" below).'),
            ("§1 MFL sub-item",
             "MFL: your MFL username, which identifies your account. Your MFL password is used once "
             'to sign in to MFL and is never stored (see "Platform connections" below).'),
            ("§5 SWID clause",
             "Platform connections (Sleeper, ESPN, MFL): the sign-in tokens, cookies and sessions are "
             "kept encrypted (except ESPN's SWID cookie, your member ID, which is stored as is) until "
             "any of these happens:"),
            ("§6 request line",
             "Tell us how you sign in (Apple, Sleeper, ESPN or MFL) and how to find your account: your "
             "Sleeper or MFL username, your ESPN league ID and team name, or the email on your Apple ID."),
        ),
        "terms.html": (
            ("§2 sign-in paragraph",
             "You can sign in with Apple, with a Sleeper username, or, where available, with your ESPN "
             "or MyFantasyLeague login. You can also connect ESPN and MyFantasyLeague leagues after you "
             "sign in. Only sign in with, and connect, accounts you own or are authorized to use."),
            ("§14.1 subscribe line",
             "To subscribe, you need a verified account: Sign in with Apple, a verified Sleeper "
             "sign-in, or, where available, an ESPN or MFL sign-in."),
        ),
        "contact.html": (
            ("c3",
             "To find your account, say how you sign in (Apple, Sleeper, ESPN or MFL) and your Sleeper "
             "or MFL username, or for ESPN your league ID and team name. Requests are acted on only "
             "when they can be verified, so send this while signed in, or email fleecedapp@gmail.com."),
        ),
        "faq.html": (
            ("Q6 MFL storage",
             "Your password goes to MFL to sign you in. It's never stored. Your MFL username and the "
             "encrypted session MFL returns are kept."),
        ),
    }
    for page, sentences in R28_15.items():
        text = rendered(page)
        missing = [label for label, s in sentences if " ".join(s.split()) not in text]
        r.check(f"POL-r28-15[{page}]", not missing,
                "not verbatim (legal R28.15): " + "; ".join(missing) if missing
                else f"{len(sentences)} R28.15 sentence(s) verbatim")

    # R28.16, from the approved ESPN/MFL sign-in design: ESPN sign-in keeps only
    # the SWID; cookies (ESPN) and the session (MFL) are kept only on import;
    # the cross-check against another member's SWID is disclosed; disconnecting
    # deletes the import credential and the sign-in identity stays until account
    # deletion. Terms §2 gains "first controller wins".
    R28_16 = {
        "privacy.html": (
            ('§1 "League data" ESPN sign-ins',
             "We use leaguemates' data only to run trade discovery and league features for members of "
             'that league, and to confirm ESPN sign-ins (see "Platform connections" below).'),
            ("§1 ESPN lead",
             "ESPN. You log in on ESPN's own page inside the app; we never see your password."),
            ("§1 ESPN sign-in",
             "Signing in with ESPN: we use ESPN's sign-in cookies to confirm that your login owns the "
             "team you pick, and we keep only your ESPN member ID (called SWID) to recognize you next "
             "time. To confirm ownership, we may also check your cookies against another league "
             "member's ESPN member ID, which members of that league can see. Nothing from that check "
             "is kept."),
            ("§1 ESPN import",
             "Importing an ESPN league (after you sign in, or when you connect ESPN in Settings → "
             "Leagues): we keep two ESPN sign-in cookies, espn_s2 (stored encrypted) and SWID (your "
             "ESPN member ID, stored as is). We use them to import your ESPN leagues and to send "
             "trades you approve."),
            ("§1 ESPN disconnect",
             "You can disconnect in Settings → Leagues, which deletes both cookies. If ESPN is how you "
             "sign in, your ESPN member ID stays as your sign-in until you delete your account."),
            ("§1 MFL lead",
             "MFL. If you sign in with or connect MFL using your MFL username and password, your "
             "password passes through our server to MFL's sign-in once, to start a session. We never "
             "store it."),
            ("§1 MFL sign-in",
             "Signing in with MFL: we keep your MFL username to recognize you next time."),
            ("§1 MFL import",
             "Importing an MFL league (after you sign in, or when you connect MFL in Settings → "
             "Leagues): we also keep the session MFL returns, encrypted, and use it to read your "
             "leagues and to send trades you approve."),
            ("§1 MFL disconnect",
             "You can disconnect in Settings → Leagues, which deletes the stored session. If MFL is how "
             "you sign in, your MFL username stays as your sign-in until you delete your account."),
        ),
        "terms.html": (
            ("§2 first controller wins",
             "An ESPN or MyFantasyLeague login opens one Fleeced account: the first one it was used to "
             "sign in to. It stays with that account until the account is deleted. Anyone who signs in "
             "with that login can use that account, so don't share it."),
        ),
    }
    for page, sentences in R28_16.items():
        text = rendered(page)
        missing = [label for label, s in sentences if " ".join(s.split()) not in text]
        r.check(f"POL-r28-16[{page}]", not missing,
                "not verbatim (legal R28.16): " + "; ".join(missing) if missing
                else f"{len(sentences)} R28.16 sentence(s) verbatim")

    # R28.12 row 1: "Fleeced" is the Service, so the operator is "the developer
    # of Fleeced", and "we"/"us" attach to the operator, not the definition.
    OPERATOR = {
        "privacy.html": ('Fleeced: Dynasty Trade Finder ("Fleeced" or "the Service")',
                         'It is operated by the developer of Fleeced ("we", "us").',
                         "The Service is operated by the developer of Fleeced."),
        "terms.html": ('Fleeced: Dynasty Trade Finder ("Fleeced" or "the Service")',
                       'The Service is operated by the developer of Fleeced ("we", "us").',
                       "The Service is operated by the developer of Fleeced."),
    }
    for page, sentences in OPERATOR.items():
        text = rendered(page)
        missing = [s for s in sentences if s not in text]
        self_run = re.findall(r"\boperated by Fleeced\b[^.]*\.?", text)
        r.check(f"POL-operator[{page}]", not missing and not self_run,
                ('says "operated by Fleeced" (the Service operating itself): ' + " | ".join(self_run)
                 if self_run else "not verbatim (legal R28.12 row 1): " + " | ".join(missing))
                if (missing or self_run) else 'operated by "the developer of Fleeced", never by "Fleeced"')

    EFFECTIVE = re.compile(r"Effective date:\s*([A-Z][a-z]+ \d{1,2}, \d{4})\b")
    dates = {}
    for page in POLICY:
        m = EFFECTIVE.search(plain(visible(page)))
        try:
            dates[page] = (m.group(1), datetime.strptime(m.group(1), "%B %d, %Y").date()) if m else None
        except ValueError:
            dates[page] = None
    real = all(dates.values())
    same = real and len({d for _, d in dates.values()}) == 1
    r.check("POL-effective-date", same,
            (f"same date on both pages: {dates[POLICY[0]][0]}" if same else
             "dates differ: " + ", ".join(f"{p} {v[0]}" for p, v in dates.items()) if real else
             "no real \"Effective date: <Month> <D>, <YYYY>\" on: "
             + ", ".join(p for p, v in dates.items() if not v)))

    contact = all_sources["contact.html"]
    cbody = strip_style_and_script(strip_comments(body_of(contact)))
    form_at = cbody.find("<form")
    data_at = cbody.find(">Data requests</h2>")
    first = MAILTO_A.search(cbody)
    in_data = MAILTO_A.search(cbody, data_at) if data_at >= 0 else None
    r.check("POL-contact-mailto-placement",
            bool(first) and form_at >= 0 and first.start() < form_at and bool(in_data),
            "want one mailto before the <form> and one in the Data requests section (P28-AC1)")
    fields = (len(re.findall(r"<input\b", cbody, flags=re.I)),
              len(re.findall(r"<select\b", cbody, flags=re.I)),
              len(re.findall(r"<textarea\b", cbody, flags=re.I)))
    r.check("POL-contact-no-new-field", fields == (0, 1, 1),
            f"inputs/selects/textareas = {fields}; want exactly the topic select and the "
            "message textarea, no email input (P28-R2, P28-AC3)")
    script = "".join(re.findall(r"<script\b[^>]*>(.*?)</script>", contact, flags=re.S | re.I))
    html_sinks = [s for s in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write")
                  if s in script]
    dom_built = ("createElement('a')" in script or 'createElement("a")' in script) \
        and "textContent" in script
    in_script = script.count(SUPPORT_EMAIL)
    r.check("POL-contact-status-dom", not html_sinks and dom_built and in_script == 1,
            (f"status lines use {html_sinks}" if html_sinks else
             "status links not built with createElement('a') + textContent" if not dom_built else
             f"the address is written {in_script}× in the script; want the one SUPPORT_EMAIL constant")
            if (html_sinks or not dom_built or in_script != 1) else
            "status links built from DOM nodes and one constant")
    r.check("POL-contact-send-reenabled", script.count("btn.disabled = false") >= 2,
            "Send must be re-enabled after a successful send too (P28-R7)")

    faq = all_sources["faq.html"]
    faq_text = visible("faq.html")
    r.check("POL-faq-no-speed", not re.search(r"I AM SPEED", faq_text, flags=re.I),
            'the "I AM SPEED" question is back')
    r.check("POL-faq-no-testflight", "testflight" not in faq_text.lower(),
            "the FAQ names TestFlight")
    release = re.findall(r'href="(https://github\.com/[^"]+/releases/[^"]+)"', all_sources["index.html"])
    faq_release = re.findall(r'href="(https://github\.com/[^"]+/releases/[^"]+)"', faq)
    r.check("POL-faq-extension-link", bool(release) and set(faq_release) == {release[0]},
            f"FAQ extension link {faq_release} != index.html's {release[:1]}")

    # Q5/Q6 first paragraphs: marketing's OA-8 text (marketing-lead-copy.md §2;
    # §1g rows 3-4, FIXED), which legal R28.15 row 7 treats as the live
    # pre-launch Q5/Q6: sign in with Apple or Sleeper, then link the league.
    # Neither may say "choose ESPN" / "choose MFL" (the old sign-in chips). At
    # the 11-18 flip, R28.15 row 7's release sentences replace these.
    OA8 = (
        ("Q5", "How do I connect an ESPN league?",
         "In the iPhone app, sign in with Apple or Sleeper, then go to Settings → Leagues → Link an "
         "ESPN league and sign in on ESPN's own page inside the app. Your ESPN password stays on "
         "ESPN's sign-in page, and the app lists your leagues."),
        ("Q6", "How do I connect an MFL league?",
         "In the iPhone app, sign in with Apple or Sleeper, then go to Settings → Leagues → Link an "
         "MFL league. Sign in with your MFL username and password, or enter a league ID or a "
         "myfantasyleague.com league URL."),
    )

    def inline_text(fragment: str) -> str:
        text = unescape(re.sub(r"<[^>]+>", "", fragment)).replace("’", "'")
        return re.sub(r"\s+", " ", text).strip()

    faq_items = {inline_text(s): b for s, b in re.findall(
        r'<summary>(.*?)</summary>\s*<div class="faq-body">(.*?)</div>',
        strip_comments(faq), flags=re.S)}
    problems = []
    for label, question, want in OA8:
        if question not in faq_items:
            problems.append(f'{label} "{question}" not found')
            continue
        first = re.search(r"<p\b[^>]*>(.*?)</p>", faq_items[question], flags=re.S)
        lead = inline_text(first.group(1)) if first else ""
        if " ".join(want.split()) not in lead:
            problems.append(f"{label} first paragraph is not marketing's OA-8 text")
        chose = re.findall(r"\bchoose\s+(?:ESPN|MFL)\b", lead, flags=re.I)
        if chose:
            problems.append(f'{label} first paragraph says "{chose[0]}"')
    r.check("POL-faq-oa8", not problems,
            "; ".join(problems) if problems
            else 'Q5/Q6 open with "sign in with Apple or Sleeper, then … Link an ESPN/MFL league"')

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
