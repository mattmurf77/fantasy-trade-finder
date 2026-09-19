#!/usr/bin/env python3
"""Generate city-data.json for the Code City visualization.

Walks the git-tracked file list, measures each file (lines of code, bytes,
commit count, last-touched date), and emits a nested tree that the viewer
lays out as a treemap city: directories are districts, files are buildings.

Usage:  python3 scripts/codecity/generate.py            # writes scripts/codecity/city-data.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "city-data.json"

# Extensions we count lines for. Everything else is measured by bytes only.
TEXT_EXT = {
    "py", "ts", "tsx", "js", "jsx", "md", "html", "css", "json", "yaml", "yml",
    "sh", "swift", "kt", "gradle", "properties", "xml", "txt", "csv", "toml",
    "patch", "plist", "sql", "env", "cfg", "ini", "pro", "storyboard",
    "xcscheme", "xcworkspacedata", "xcprivacy", "gitignore", "easignore",
    "python-version",
}

# Coarse language buckets — the viewer colors buildings by these.
LANG = {
    "py": "python",
    "ts": "typescript", "tsx": "typescript",
    "js": "javascript", "jsx": "javascript",
    "md": "docs",
    "html": "web", "css": "web",
    "json": "config", "yaml": "config", "yml": "config", "toml": "config",
    "properties": "config", "plist": "config", "xml": "config",
    "gitignore": "config", "easignore": "config", "env": "config",
    "sh": "shell",
    "swift": "native", "kt": "native", "gradle": "native", "pro": "native",
    "storyboard": "native", "xcscheme": "native", "xcworkspacedata": "native",
    "xcprivacy": "native",
    "png": "asset", "webp": "asset", "jpg": "asset", "jpeg": "asset",
    "gif": "asset", "svg": "asset", "ico": "asset", "xlsx": "asset",
    "csv": "data", "patch": "data", "txt": "data",
}


def sh(*args: str) -> str:
    return subprocess.run(
        args, cwd=REPO, capture_output=True, text=True, check=True
    ).stdout


def ext_of(path: str) -> str:
    base = os.path.basename(path)
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[1].lower()


def count_lines(path: Path) -> int:
    try:
        with path.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def churn_and_age() -> tuple[dict[str, int], dict[str, str]]:
    """commits-per-file and last-commit-date-per-file, from git history."""
    log = sh("git", "log", "--pretty=format:@%cI", "--name-only")
    commits: dict[str, int] = defaultdict(int)
    last: dict[str, str] = {}
    stamp = ""
    for line in log.splitlines():
        if line.startswith("@"):
            stamp = line[1:11]  # "@2026-08-13T…" -> "2026-08-13"
        elif line.strip():
            commits[line] += 1
            last.setdefault(line, stamp)
    return commits, last


def main() -> None:
    files = [f for f in sh("git", "ls-files").splitlines() if f.strip()]
    commits, last = churn_and_age()
    today = datetime.now(timezone.utc).date()

    root: dict = {"name": REPO.name, "type": "dir", "children": {}}
    totals = defaultdict(int)
    lang_loc = defaultdict(int)

    for rel in files:
        disk = REPO / rel
        if not disk.exists():  # deleted-but-staged, skip
            continue
        ext = ext_of(rel)
        size = disk.stat().st_size
        loc = count_lines(disk) if ext in TEXT_EXT else 0
        lang = LANG.get(ext, "other")
        modified = last.get(rel, "")
        age_days = None
        if modified:
            try:
                age_days = (today - datetime.strptime(modified, "%Y-%m-%d").date()).days
            except ValueError:
                age_days = None

        node = root
        parts = rel.split("/")
        for part in parts[:-1]:
            kids = node["children"]
            if part not in kids:
                kids[part] = {"name": part, "type": "dir", "children": {}}
            node = kids[part]
        node["children"][parts[-1]] = {
            "name": parts[-1],
            "type": "file",
            "path": rel,
            "ext": ext,
            "lang": lang,
            "loc": loc,
            "bytes": size,
            "commits": commits.get(rel, 1),
            "modified": modified,
            "age": age_days,
        }

        totals["files"] += 1
        totals["loc"] += loc
        totals["bytes"] += size
        lang_loc[lang] += loc or max(1, size // 200)

    def listify(node: dict) -> dict:
        if node["type"] == "file":
            return node
        kids = [listify(c) for c in node["children"].values()]
        kids.sort(key=lambda k: -(k.get("loc") or k.get("subtotal", {}).get("loc", 0)))
        loc = sum(k["loc"] if k["type"] == "file" else k["subtotal"]["loc"] for k in kids)
        nfiles = sum(1 if k["type"] == "file" else k["subtotal"]["files"] for k in kids)
        nbytes = sum(k["bytes"] if k["type"] == "file" else k["subtotal"]["bytes"] for k in kids)
        ncommits = sum(
            k["commits"] if k["type"] == "file" else k["subtotal"]["commits"] for k in kids
        )
        return {
            "name": node["name"],
            "type": "dir",
            "children": kids,
            "subtotal": {"loc": loc, "files": nfiles, "bytes": nbytes, "commits": ncommits},
        }

    tree = listify(root)
    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = sh("git", "rev-parse", "--short", "HEAD").strip()

    payload = {
        "repo": REPO.name,
        "branch": branch,
        "head": head,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "totals": {
            "files": totals["files"],
            "loc": totals["loc"],
            "bytes": totals["bytes"],
            "commits": int(sh("git", "rev-list", "--count", "HEAD").strip()),
        },
        "langLoc": dict(sorted(lang_loc.items(), key=lambda kv: -kv[1])),
        "tree": tree,
    }

    blob = json.dumps(payload, separators=(",", ":"))
    OUT.write_text(blob)
    # JS wrapper for the served copy — fetch() of a local .json is blocked by
    # the file:// origin policy.
    OUT.with_suffix(".js").write_text("window.CITY_DATA = " + blob + ";\n")

    # Standalone build with the data inlined. Safari refuses to load even a
    # sibling <script src> from a file:// page, so double-clicking index.html
    # comes up empty; city.html has no subresources and always opens.
    here = OUT.parent
    tpl = (here / "index.html").read_text()
    tag = '<script src="city-data.js"></script>'
    if tag not in tpl:
        raise SystemExit(f"index.html no longer contains {tag!r} — update generate.py")
    inline = tpl.replace(
        tag, "<script>window.CITY_DATA=" + blob.replace("</", "<\\/") + ";</script>"
    )
    (here / "city.html").write_text(inline)

    print(
        f"wrote {OUT.relative_to(REPO)} (+.js, + standalone city.html) — "
        f"{totals['files']} files, {totals['loc']:,} lines"
    )


if __name__ == "__main__":
    sys.exit(main())
