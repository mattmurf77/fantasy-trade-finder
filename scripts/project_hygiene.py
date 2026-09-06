#!/usr/bin/env python3
"""Generate project indexes from one explicit status record per document set.

No dependencies, git commands, network, timestamps, or application imports. --write
initializes missing records conservatively; it never infers release state from prose.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re
import sys

STATUSES = frozenset({
    "planned", "active", "in-progress", "built-unmerged", "built-dark",
    "partly-shipped", "shipped", "blocked", "deferred", "superseded",
    "abandoned", "declined", "reference", "needs-review",
})
INACTIVE = frozenset({"shipped", "deferred", "superseded", "abandoned", "declined", "reference"})
EVIDENCE_REQUIRED = frozenset({"shipped", "built-dark", "built-unmerged", "partly-shipped", "superseded", "abandoned", "declined"})
ADMIN_FILES = frozenset({"README.md", "CLAUDE.md", "INDEX.md", "CATALOG.md", "status.md"})


@dataclass(frozen=True)
class Entry:
    home: Path
    source: Path
    archived: bool


def discover(base: Path) -> list[Entry]:
    """Inspect immediate homes, including untracked files; never descend into sources."""
    entries = []

    def scan(directory: Path, archived: bool) -> None:
        if not directory.exists():
            return
        for child in sorted(directory.iterdir(), key=lambda p: p.name):
            if child.is_symlink() or child.name.startswith((".", "_")):
                continue
            if child.name == "archive" or child.name in ADMIN_FILES:
                continue
            if child.is_dir():
                entries.append(Entry(child, child / "status.md", archived))
            elif child.suffix == ".md":
                entries.append(Entry(child, child, archived))

    scan(base, False)
    archive = base / "archive"
    if archive.exists():
        for year in sorted(archive.iterdir(), key=lambda p: p.name):
            if year.name in {"README.md", "CLAUDE.md"} and year.is_file() and not year.is_symlink():
                continue
            if year.is_dir() and not year.is_symlink() and re.fullmatch(r"\d{4}", year.name):
                scan(year, True)
            else:
                raise ValueError(f"{year}: archived work must live under archive/<year>/; only README.md and CLAUDE.md may be directly under archive/")
    return entries


def default_status(entry: Entry) -> dict[str, str]:
    return {
        "status": "needs-review",
        "updated": "",
        "summary": entry.home.stem.replace("-", " "),
        "evidence": "Legacy or newly discovered document set; current disposition has not been verified. Review the retained notes before changing status.",
    }


def encode_status(record: dict[str, str]) -> str:
    return "```project-status\n" + json.dumps(record, ensure_ascii=False, indent=2) + "\n```"


def initialize(entry: Entry, text: str) -> str:
    heading = f"# Status — {entry.home.stem}\n\n"
    if entry.home.is_dir():
        tail = ("\n\n## Historical notes\n\n"
                "The material below is retained evidence. Its former status wording does not override the record above.\n\n" + text) if text.strip() else "\n"
        return heading + encode_status(default_status(entry)) + tail
    # A flat plan is its own status source; preserve the original document in place.
    return encode_status(default_status(entry)) + "\n\n" + text


def status_block(text: str, source: Path) -> str | None:
    """Read one complete status fence, ignoring examples inside other fences."""
    records: list[str] = []
    fence_char = ""
    fence_size = 0
    in_status = False
    body: list[str] = []
    for line in text.splitlines():
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if not fence_char:
            if not fence:
                continue
            marker, info = fence.groups()
            fence_char, fence_size = marker[0], len(marker)
            in_status = info.strip() == "project-status"
            body = []
            if in_status and records:
                raise ValueError(f"{source}: expected exactly one project-status block")
            continue
        if fence:
            marker, info = fence.groups()
            if marker[0] == fence_char and len(marker) >= fence_size and not info.strip():
                if in_status:
                    records.append("\n".join(body))
                fence_char, in_status = "", False
                continue
            if in_status and info.strip() == "project-status":
                raise ValueError(f"{source}: malformed or additional project-status opener")
        if in_status:
            body.append(line)
    if in_status:
        raise ValueError(f"{source}: malformed project-status block: missing closing fence")
    return records[0] if records else None


def read_status(text: str, source: Path) -> dict[str, str] | None:
    block = status_block(text, source)
    if block is None:
        return None
    try:
        record = json.loads(block)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source}: invalid status JSON: {exc.msg}") from exc
    keys = {"status", "updated", "summary", "evidence"}
    if not isinstance(record, dict) or set(record) != keys or not all(isinstance(v, str) for v in record.values()):
        raise ValueError(f"{source}: status record must contain string fields {', '.join(sorted(keys))}")
    if record["status"] not in STATUSES:
        raise ValueError(f"{source}: unsupported status {record['status']!r}; use needs-review for uncertain legacy claims")
    if record["updated"]:
        try:
            parsed = date.fromisoformat(record["updated"])
            if parsed.isoformat() != record["updated"]:
                raise ValueError()
        except ValueError as exc:
            raise ValueError(f"{source}: updated must be YYYY-MM-DD or empty when unknown") from exc
    if not record["summary"].strip() or len(record["summary"]) > 240:
        raise ValueError(f"{source}: summary must contain 1–240 characters")
    if record["status"] in EVIDENCE_REQUIRED and record["evidence"].strip().lower() in {"", "n/a", "none", "todo", "unknown"}:
        raise ValueError(f"{source}: {record['status']} requires a concrete evidence reference")
    return record


def cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "&#124;").replace("<", "&lt;").replace(">", "&gt;")


def render(base: Path, records: list[tuple[Entry, dict[str, str]]], *, catalog: bool, feedback: bool) -> str:
    label = "Feedback items" if feedback else "Initiatives"
    selected = records if catalog else [(e, r) for e, r in records if not e.archived and r["status"] not in INACTIVE]
    selected = sorted(selected, key=lambda item: item[0].home.relative_to(base).as_posix())
    lines = [f"# {label} — {'full catalog' if catalog else 'active index'}", "",
             "<!-- Generated by scripts/project_hygiene.py. Edit each linked status source, then run --write. -->", "",
             "Status records describe the last documented disposition; they are not a fresh production audit.", ""]
    if catalog:
        active = "INDEX.md" if feedback else "README.md"
        lines += [f"Use the [active index]({active}) for normal work. This catalog also includes inactive and archived history.", ""]
    else:
        guide = "README.md" if feedback else "CLAUDE.md"
        lines += [f"Start here for current work and unresolved status reviews. Use the [full catalog](CATALOG.md) for duplicate checks and history, and [{guide}]({guide}) for the workflow.", "",
                  "`needs-review` preserves an uncertain or conflicting legacy claim; it does not mean the feature is unbuilt.", ""]
    lines += [f"{len(selected)} entries. Counts and rows come from the same status records.", "",
              "| Initiative / item | Status | Updated | Summary |",
              "|---|---|---|---|"]
    for entry, record in selected:
        home = entry.home.relative_to(base).as_posix()
        source = entry.source.relative_to(base).as_posix()
        archived = " · archived" if entry.archived else ""
        lines.append(f"| [{cell(home)}]({source}) | {record['status']}{archived} | {record['updated'] or '—'} | {cell(record['summary'])} |")
    counts = Counter(record["status"] for _, record in selected)
    lines += ["", "## Status counts", "", "| Status | Count |", "|---|---|"]
    lines += [f"| {status} | {counts[status]} |" for status in sorted(counts)]
    return "\n".join(lines) + "\n"


def run(root: Path, *, write: bool) -> list[str]:
    errors: list[str] = []
    updates: dict[Path, str] = {}
    for rel, feedback in [("docs/plans", False), ("docs/feedback/items", True)]:
        base = root / rel
        records = []
        try:
            entries = discover(base)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        for entry in entries:
            if entry.source.is_symlink():
                errors.append(f"{entry.source.relative_to(root)}: status source must not be a symlink")
                continue
            text = entry.source.read_text(encoding="utf-8") if entry.source.exists() else ""
            try:
                record = read_status(text, entry.source.relative_to(root))
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if record is None:
                if not write:
                    errors.append(f"{entry.source.relative_to(root)}: missing status record; run --write to initialize as needs-review")
                    continue
                text = initialize(entry, text)
                updates[entry.source] = text
                record = default_status(entry)
            records.append((entry, record))
        for filename, catalog in [("INDEX.md" if feedback else "README.md", False), ("CATALOG.md", True)]:
            target = base / filename
            expected = render(base, records, catalog=catalog, feedback=feedback)
            actual = target.read_text(encoding="utf-8") if target.exists() else ""
            if actual != expected:
                if write:
                    updates[target] = expected
                else:
                    errors.append(f"{target.relative_to(root)}: generated index is stale; run python3 scripts/project_hygiene.py --write")
    # Validate the entire inventory before any write, avoiding half-rebuilt indexes.
    if write and not errors:
        for path, contents in updates.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="initialize unknown statuses and regenerate indexes")
    mode.add_argument("--check", action="store_true", help="validate statuses and fail on index drift without writing")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    errors = run(args.root.resolve(), write=args.write)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Project status records and indexes are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
