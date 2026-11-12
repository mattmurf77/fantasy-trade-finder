"""KeepTradeCut value history for the Sleeper trade-universe research store.

RESEARCH TOOL, NOT APP CODE. Nothing in the Flask app imports this module.
The operator states the KeepTradeCut agreement covers reading historical
values from the site, the same way `data_loader.py` reads current values.

What it reads (two page kinds, both public HTML):

  1. https://keeptradecut.com/dynasty-rankings, once: the
     `<script type="application/json" id="ktc-players">` list (the current
     top 500, including `RDP` draft-pick entries such as "2027 Early 1st"),
     parsed with the app's own regexes (`data_loader._KTC_PLAYERS_ELEMENT`,
     `_KTC_PLAYERS_LITERAL`) and sent with the app's browser headers.
  2. https://keeptradecut.com/dynasty-rankings/players/<slug>, once per
     entry: the `id="pd-oneqb"` and `id="pd-superflex"` JSON blocks, each a
     dict whose `overallValue` is a DAILY [{"d": "YYMMDD", "v": int}] series
     from 2020 to today.

What is kept: per page, a gzip JSON checkpoint holding the parsed series
(`overallValue`, `vftValueHistory`, `blendValueHistory` for both formats) and
the entry's identity. Raw HTML (about 4 MB a page) is NOT kept unless
`keep_html=True`. A restart skips every page that already has a checkpoint.

Which series becomes source "ktc": `overallValue`, the crowd-sourced
keep/trade/cut value the site shows by default (`blendRatio = 0.0` on the
page) and the same number the app's blend reads today. `vftValueHistory`
("Values from Trades", launched 2026) and `blendValueHistory` can be loaded
as separate sources ("ktc_vft", "ktc_blend") but are not by default: they
are derived from trades, possibly including the very Sleeper trades this
research studies, and their pre-launch history is a back-fill. See the
design note `docs/plans/sleeper-trade-universe/values-history.md`.

Formats: "1qb" = pd-oneqb, "sf" = pd-superflex. The page's `tep`/`tepp`/
`teppp` objects hold only adjacent-player lists, no value series, so there
is NO tight-end-premium history: "sf" here is plain superflex, unlike the
app's live `sf_tep` read (`superflexValues.tep.value`).

Politeness: one process, one request every `interval` seconds (default 3,
floor 1), gzip accepted, back-off and retry on 429 / 5xx / network errors,
and a hard stop after `hard_stop_after` consecutive 403 or 429 answers (the
site is Cloudflare-guarded). The transport is injectable; tests use a fake.
"""

from __future__ import annotations

import datetime as _dt
import gzip
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import universe_values as uv
from .data_loader import (KTC_RANKINGS_URL, _KTC_BROWSER_HEADERS,
                          _KTC_PLAYERS_ELEMENT, _KTC_PLAYERS_LITERAL)

PLAYER_URL = "https://keeptradecut.com/dynasty-rankings/players/{slug}"
DEFAULT_OUT = os.path.join(uv.DEFAULT_DIR, "ktc")
PAGE_BLOCKS = {"1qb": "pd-oneqb", "sf": "pd-superflex"}
SERIES = {"crowd": "overallValue", "vft": "vftValueHistory", "blend": "blendValueHistory"}
SOURCE_FOR_SERIES = {"crowd": "ktc", "vft": "ktc_vft", "blend": "ktc_blend"}
KTC_POSITIONS = frozenset({"QB", "RB", "WR", "TE", "RDP"})
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*-(\d+)$")
_PICK_SLUG_RE = re.compile(r"^(\d{4})-(early|mid|late)-(\d{1,2})(st|nd|rd|th)-\d+$")
HEADERS = dict(_KTC_BROWSER_HEADERS, **{"Accept-Encoding": "gzip"})


class HardStop(RuntimeError):
    """Too many consecutive 403/429 answers: stop and leave the checkpoint."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _json_block(html: str, block_id: str):
    m = re.search(r"<script\b[^>]*?\sid\s*=\s*[\"']?%s[\"']?(?=[\s>])[^>]*>(.*?)</script>"
                  % re.escape(block_id), html, re.S | re.I)
    return json.loads(m.group(1)) if m else None


def parse_rankings(html: str) -> list[dict]:
    """The rankings-page list, players AND RDP picks, slimmed to identity."""
    players = None
    for pattern in (_KTC_PLAYERS_ELEMENT, _KTC_PLAYERS_LITERAL):
        m = pattern.search(html)
        if m:
            try:
                players = json.loads(m.group(1))
            except ValueError:
                players = None
            if isinstance(players, list) and players:
                break
    if not isinstance(players, list) or not players:
        raise ValueError("no ktc-players list in rankings page")
    out = []
    for p in players:
        if not isinstance(p, dict) or p.get("position") not in KTC_POSITIONS:
            continue
        slug = str(p.get("slug") or "")
        if not _SLUG_RE.match(slug):
            continue
        out.append({"id": str(p.get("playerID")), "name": p.get("playerName"),
                    "slug": slug, "position": p.get("position"),
                    "mflid": str(p.get("mflid") or "")})
    if not out:
        raise ValueError("ktc-players list holds no usable entries")
    return out


def _series(points) -> tuple[list[list], int]:
    """[{"d": "YYMMDD", "v": int}] -> ([[iso, v]...] sorted, duplicate days).
    A day listed twice keeps its LAST point."""
    by_day: dict[str, int] = {}
    dups = 0
    for pt in points or []:
        if not isinstance(pt, dict):
            continue
        d, v = str(pt.get("d") or ""), pt.get("v")
        if not re.fullmatch(r"\d{6}", d) or not isinstance(v, (int, float)):
            continue
        iso = "20%s-%s-%s" % (d[:2], d[2:4], d[4:])
        if iso in by_day:
            dups += 1
        by_day[iso] = int(v)
    return [[k, by_day[k]] for k in sorted(by_day)], dups


def parse_player_page(html: str, ktc_id: str | None = None) -> dict:
    """{"series": {fmt: {series_name: [[iso, v]...]}}, "duplicates": {...},
    "self": identity from the page's own adjacent-player lists or None}.
    Raises ValueError when either format block is missing."""
    out = {"series": {}, "duplicates": {}, "self": None}
    for fmt, block_id in PAGE_BLOCKS.items():
        block = _json_block(html, block_id)
        if not isinstance(block, dict):
            raise ValueError("no %s block" % block_id)
        out["series"][fmt] = {}
        for name, key in SERIES.items():
            pts, dups = _series(block.get(key))
            out["series"][fmt][name] = pts
            if dups:
                out["duplicates"]["%s/%s" % (fmt, name)] = dups
        if ktc_id and out["self"] is None:
            for p in block.get("adjacentOverallPlayers") or []:
                if isinstance(p, dict) and str(p.get("playerID")) == str(ktc_id):
                    out["self"] = {"name": p.get("playerName"),
                                   "position": p.get("position"),
                                   "mflid": str(p.get("mflid") or "")}
                    break
    if not out["series"]["1qb"]["crowd"] and not out["series"]["sf"]["crowd"]:
        raise ValueError("page has no overallValue points")
    return out


def pick_label_from_slug(slug: str) -> str | None:
    m = _PICK_SLUG_RE.match(slug)
    if not m:
        return None
    return "%s %s %s%s" % (m.group(1), m.group(2).capitalize(), m.group(3), m.group(4))


# ---------------------------------------------------------------------------
# Transport and polite fetching
# ---------------------------------------------------------------------------

@dataclass
class Response:
    status: int
    headers: dict
    body: bytes

    def text(self) -> str:
        body = self.body
        enc = {k.lower(): v for k, v in self.headers.items()}.get("content-encoding", "")
        if "gzip" in enc.lower() or body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return body.decode("utf-8")


def urllib_transport(url: str, headers: dict, timeout: int = 30) -> Response:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return Response(r.status, dict(r.headers), r.read())
    except urllib.error.HTTPError as e:
        return Response(e.code, dict(e.headers or {}), e.read() or b"")


class PoliteFetcher:
    def __init__(self, transport=urllib_transport, *, interval: float = 3.0,
                 max_retries: int = 4, backoff=(30, 60, 120, 240),
                 hard_stop_after: int = 3, sleep=time.sleep,
                 clock=time.monotonic, log=print):
        self.transport = transport
        self.interval = max(float(interval), 1.0)
        self.max_retries = max_retries
        self.backoff = tuple(backoff)
        self.hard_stop_after = hard_stop_after
        self.sleep, self.clock, self.say = sleep, clock, log
        self._last = None
        self._blocked = 0
        self.requests = 0

    def _pace(self):
        if self._last is not None:
            wait = self._last + self.interval - self.clock()
            if wait > 0:
                self.sleep(wait)

    def get(self, url: str) -> Response | None:
        """200 -> Response. Other final statuses -> that Response. None when
        every attempt failed at the network level. Raises HardStop."""
        resp = None
        for attempt in range(self.max_retries + 1):
            self._pace()
            self.requests += 1
            try:
                resp = self.transport(url, HEADERS)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                resp = None
                self.say("  network error %s (attempt %d): %s" % (url, attempt + 1, e))
            self._last = self.clock()
            if resp is not None and resp.status == 200:
                self._blocked = 0
                return resp
            if resp is not None and resp.status in (403, 429):
                self._blocked += 1
                if self._blocked >= self.hard_stop_after:
                    raise HardStop("%d consecutive 403/429 answers (last %d on %s)"
                                   % (self._blocked, resp.status, url))
            retryable = resp is None or resp.status in (403, 429) or resp.status >= 500
            if not retryable or attempt == self.max_retries:
                return resp
            delay = self.backoff[min(attempt, len(self.backoff) - 1)]
            ra = resp and {k.lower(): v for k, v in resp.headers.items()}.get("retry-after")
            if ra and str(ra).isdigit():
                delay = max(delay, int(ra))
            self.say("  %s on %s, retry in %ss" % (resp.status if resp else "error", url, delay))
            self.sleep(delay)
        return resp


# ---------------------------------------------------------------------------
# The pull (network, run by the operator) -> checkpoint directory
# ---------------------------------------------------------------------------

def _page_path(out_dir: str, slug: str) -> str:
    return os.path.join(out_dir, "pages", slug + ".json.gz")


def read_extra(path: str) -> list[str]:
    """One slug or numeric KTC id per line; '#' comments and blanks ignored."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.split("#", 1)[0].strip()
            if s:
                out.append(s)
    return out


def run_pull(out_dir: str = DEFAULT_OUT, *, fetcher: PoliteFetcher,
             extra: list[str] | None = None, refresh_list: bool = False,
             keep_html: bool = False, limit: int | None = None, log=print) -> dict:
    os.makedirs(os.path.join(out_dir, "pages"), exist_ok=True)
    list_path = os.path.join(out_dir, "rankings.json")
    if refresh_list or not os.path.exists(list_path):
        resp = fetcher.get(KTC_RANKINGS_URL)
        if resp is None or resp.status != 200:
            raise RuntimeError("rankings page: %s" % (resp.status if resp else "network error"))
        entries = parse_rankings(resp.text())
        with open(list_path, "w") as f:
            json.dump({"fetched_at": uv._utc_now(), "entries": entries}, f, indent=1)
    with open(list_path) as f:
        entries = json.load(f)["entries"]
    by_id = {e["id"]: e for e in entries}
    todo = [dict(e, origin="rankings") for e in entries]
    seen = {e["slug"] for e in entries}
    unresolved = []
    for item in extra or []:
        if item.isdigit():
            e = by_id.get(item)
            if e is None:
                unresolved.append(item)      # an id alone gives no URL; need its slug
            continue
        m = _SLUG_RE.match(item)
        if not m:
            unresolved.append(item)
            continue
        if item not in seen:
            seen.add(item)
            todo.append({"id": m.group(1), "name": None, "slug": item,
                         "position": "RDP" if pick_label_from_slug(item) else None,
                         "mflid": "", "origin": "extra"})
    done = fetched = failed = 0
    failures = []
    for e in todo:
        path = _page_path(out_dir, e["slug"])
        if os.path.exists(path):
            done += 1
            continue
        if limit is not None and fetched >= limit:
            break
        fetched += 1
        resp = fetcher.get(PLAYER_URL.format(slug=e["slug"]))
        if resp is None or resp.status != 200:
            failed += 1
            failures.append({"slug": e["slug"], "status": resp.status if resp else None})
            log("  FAIL %s: %s" % (e["slug"], resp.status if resp else "network"))
            continue
        html = resp.text()
        if keep_html:
            os.makedirs(os.path.join(out_dir, "html"), exist_ok=True)
            with open(os.path.join(out_dir, "html", e["slug"] + ".html"), "w") as f:
                f.write(html)
        try:
            parsed = parse_player_page(html, e["id"])
        except ValueError as err:
            failed += 1
            failures.append({"slug": e["slug"], "status": 200, "error": str(err)})
            log("  PARSE FAIL %s: %s" % (e["slug"], err))
            continue
        rec = dict(entry=e, fetched_at=uv._utc_now(), **parsed)
        tmp = path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(rec, f)
        os.replace(tmp, path)                # a page is done only once fully written
        log("  ok %s (%d 1qb / %d sf points)" % (
            e["slug"], len(parsed["series"]["1qb"]["crowd"]), len(parsed["series"]["sf"]["crowd"])))
    summary = {"listed": len(entries), "queued": len(todo), "already_done": done,
               "fetched": fetched, "failed": failed, "failures": failures,
               "unresolved_extra": unresolved, "requests": fetcher.requests}
    with open(os.path.join(out_dir, "last_pull.json"), "w") as f:
        json.dump(summary, f, indent=1)
    return summary


# ---------------------------------------------------------------------------
# Checkpoint directory -> SQLite store (offline)
# ---------------------------------------------------------------------------

def _identity(rec: dict) -> tuple[str, str | None, str | None, str]:
    e, me = rec["entry"], rec.get("self") or {}
    name = e.get("name") or me.get("name")
    pos = e.get("position") or me.get("position")
    mflid = e.get("mflid") or me.get("mflid") or ""
    return str(e["id"]), name, pos, str(mflid)


def ingest(out_dir: str = DEFAULT_OUT, db_path: str = uv.DEFAULT_DB, *,
           xw: uv.DPCrosswalk, since: _dt.date = uv.DEFAULT_START,
           until: _dt.date | None = None, series: str = "crowd") -> dict:
    """Rebuild source SOURCE_FOR_SERIES[series] from the page checkpoints:
    one board per (format, day) on or after `since`."""
    source = SOURCE_FOR_SERIES[series]
    since_iso = since.isoformat()
    until_iso = until.isoformat() if until else "9999-12-31"
    boards: dict[tuple[str, str], uv.Board] = {}
    pages = sorted(os.listdir(os.path.join(out_dir, "pages")))
    stats = {"pages": 0, "players": 0, "picks": 0, "unmapped_ids": [],
             "unknown_pick": [], "duplicate_days": 0, "tiers": {}}
    for fname in pages:
        if not fname.endswith(".json.gz"):
            continue
        with gzip.open(os.path.join(out_dir, "pages", fname), "rt", encoding="utf-8") as f:
            rec = json.load(f)
        stats["pages"] += 1
        stats["duplicate_days"] += sum(rec.get("duplicates", {}).values())
        kid, name, pos, mflid = _identity(rec)
        key, tier = None, None
        if pos == "RDP" or (pos is None and pick_label_from_slug(rec["entry"]["slug"])):
            atype = "pick"
            for label in (name, pick_label_from_slug(rec["entry"]["slug"])):
                try:
                    key, tier = uv.parse_pick_label(label or ""), "pick_label"
                    break
                except ValueError:
                    continue
            if key is None:
                stats["unknown_pick"].append(kid)
                continue
            stats["picks"] += 1
        else:
            atype = "player"
            stats["players"] += 1
            key = uv.resolve_by_id(xw.by_ktc, kid, pos)
            tier = "ktc_id" if key else None
            if key is None and mflid not in ("", "0"):
                key = uv.resolve_by_id(xw.by_mfl, mflid, pos)
                tier = "mfl_id" if key else None
            if key is None and name and pos:
                key, tier = uv.resolve_by_name(name, pos, xw)
            if key is None:
                stats["unmapped_ids"].append(kid)
        if tier:
            stats["tiers"][tier] = stats["tiers"].get(tier, 0) + 1
        for fmt in uv.FORMATS:
            for day, v in rec["series"].get(fmt, {}).get(series, []):
                if not (since_iso <= day <= until_iso) or v is None or v <= 0:
                    continue
                b = boards.get((fmt, day))
                if b is None:
                    b = boards[(fmt, day)] = uv.Board(
                        source=source, format=fmt, board_date=day,
                        published_at=day + "T23:59:59Z")
                if atype == "player":
                    b.player_rows += 1
                if key is None:
                    b.unmapped.setdefault(kid, (pos, float(v)))
                else:
                    b.add(key, float(v), atype, pos if atype == "player" else None,
                          None, kid, tier)
    out = sorted(boards.values(), key=lambda b: (b.format, b.board_date))
    stats.update({"boards": len(out), "source": source, "series": series,
                  "since": since_iso, "unmapped": len(stats["unmapped_ids"])})
    conn = uv.connect(db_path)
    try:
        write_boards_detail = {k: v for k, v in stats.items() if k != "unmapped_ids"}
        uv.write_boards(conn, out, source=source, replace="source", detail=write_boards_detail)
    finally:
        conn.close()
    return stats
