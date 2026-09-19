#!/usr/bin/env python3
"""Render a bounded, read-only session brief; validate compact memory contracts.

Only named memory files are read. Document contents are never executed. Output is
assembled from complete blocks and measured after JSON serialization, so Unicode,
quotes and newlines cannot exceed the hook's 6,000-byte transport budget.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

MAX_OUTPUT_BYTES = 6000
HANDOFF_BYTES = 2000
NEXT_BYTES = 1500
MAX_SOURCE_BYTES = 1024 * 1024
MEMORY_FILES = ("HANDOFF.md", "NEXT.md", "CHANGELOG.md", "GOTCHAS.md")
INTRO = (
    "# Session brief\n\n"
    "Use this brief without rereading it. Omitted/missing sections are labelled; "
    "follow their references only when relevant. Historical notes are not current "
    "release proof or permission. Rules: AGENTS.md and docs/agent-workflow.md.\n"
)


def byte_size(value: str) -> int:
    return len(value.encode("utf-8"))


def read_memory(root: Path, name: str) -> tuple[str | None, str]:
    if name not in MEMORY_FILES:
        raise ValueError("not a session-memory source")
    path = root / "living-memory" / name
    try:
        # Never follow a memory alias into a credential file or another checkout.
        if (root / "living-memory").is_symlink() or path.is_symlink():
            return None, "symlink skipped"
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            return None, "source exceeds read limit"
        return raw.decode("utf-8"), "available"
    except FileNotFoundError:
        return None, "missing"
    except (OSError, UnicodeError):
        return None, "unreadable"


def sections(text: str) -> list[tuple[str, str]]:
    """Return real H2 sections; fenced examples do not create section boundaries."""
    result: list[tuple[str, str]] = []
    heading = ""
    block: list[str] = []
    fence_char = ""
    fence_size = 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        fence = re.match(r"(`{3,}|~{3,})", stripped)
        if fence:
            marker = fence.group(1)
            if not fence_char:
                fence_char, fence_size = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_size:
                if not stripped[len(marker):].strip():
                    fence_char = ""
        if not fence_char and line.startswith("## "):
            if heading:
                result.append((heading, "".join(block).strip()))
            heading, block = line.rstrip(), [line]
        elif heading:
            block.append(line)
    if heading:
        result.append((heading, "".join(block).strip()))
    return result


def fenced_complete(text: str) -> bool:
    """Do not inject an unfinished code example that could swallow later sections."""
    opened = ""
    size = 0
    for line in text.splitlines():
        stripped = line.lstrip()
        match = re.match(r"(`{3,}|~{3,})", stripped)
        if not match:
            continue
        marker = match.group(1)
        if not opened:
            opened, size = marker[0], len(marker)
        elif marker[0] == opened and len(marker) >= size:
            if not stripped[len(marker):].strip():
                opened = ""
    return not opened


def hook_json(content: str) -> str:
    envelope = {"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": content,
    }}
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n"


def build_brief(root: Path) -> str:
    candidates: list[tuple[str, str | None, int, str]] = []
    for name, limit in (("HANDOFF.md", HANDOFF_BYTES), ("NEXT.md", NEXT_BYTES)):
        text, state = read_memory(root, name)
        candidates.append((f"living-memory/{name}", text, limit, state))

    changelog, state = read_memory(root, "CHANGELOG.md")
    entries = [body for title, body in sections(changelog or "")
               if re.match(r"## 20\d\d-\d\d-\d\d", title)][:2]
    if entries:
        for index, entry in enumerate(entries, 1):
            candidates.append((f"living-memory/CHANGELOG.md (recent {index})",
                               entry, 1200, "available"))
    else:
        candidates.append(("living-memory/CHANGELOG.md", None, 0,
                           state if changelog is None else "no dated entries"))

    gotchas, state = read_memory(root, "GOTCHAS.md")
    match = re.search(r"<!-- GOTCHAS-INDEX:START -->(.*?)<!-- GOTCHAS-INDEX:END -->",
                      gotchas or "", re.DOTALL)
    candidates.append(("living-memory/GOTCHAS.md (index)",
                       match.group(1).strip() if match else None, 1000,
                       state if gotchas is None else "index omitted"))

    # Reserve all reference blocks first. Upgrading a block can never silently
    # drop a later file or truncate part of a source.
    blocks = [f"## {name}\n\nReference only: {state if text is None else 'over budget'}; "
              f"read the source when relevant.\n"
              for name, text, _limit, state in candidates]
    for index, (name, text, limit, _state) in enumerate(candidates):
        if text is None or byte_size(text) > limit or not fenced_complete(text):
            continue
        replacement = f"## {name}\n\n{text.strip()}\n"
        trial = blocks[:]
        trial[index] = replacement
        content = INTRO + "\n".join(trial)
        if byte_size(hook_json(content)) <= MAX_OUTPUT_BYTES:
            blocks = trial
    content = INTRO + "\n".join(blocks)
    assert byte_size(hook_json(content)) <= MAX_OUTPUT_BYTES
    return content



def queue_items(text: str) -> tuple[int, bool]:
    """Count a flat `1. action` list; reject alternative/nested list markers.

    Fenced examples and ordinary indented continuation text are not queue items.
    The exact grammar keeps the seven-action limit unambiguous across clients.
    """
    count = 0
    invalid_marker = False
    opened = ""
    size = 0
    for line in text.splitlines():
        stripped = line.lstrip()
        fence = re.match(r"(`{3,}|~{3,})", stripped)
        if fence:
            marker = fence.group(1)
            if not opened:
                opened, size = marker[0], len(marker)
            elif marker[0] == opened and len(marker) >= size and not stripped[len(marker):].strip():
                opened = ""
            continue
        if opened:
            continue
        if re.match(r"^\d+\.[ \t]+\S", line):
            count += 1
        elif re.match(r"^\s*(?:\d+[.)]|[-+*])(?:[ \t]+|$)", line):
            invalid_marker = True
    return count, invalid_marker

def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for name, limit in (("HANDOFF.md", HANDOFF_BYTES), ("NEXT.md", NEXT_BYTES)):
        text, state = read_memory(root, name)
        if text is None:
            errors.append(f"living-memory/{name}: {state}")
            continue
        if byte_size(text) > limit:
            errors.append(f"living-memory/{name}: {byte_size(text)} bytes exceeds {limit}")
        if not fenced_complete(text):
            errors.append(f"living-memory/{name}: incomplete fenced block")
        titles = [title for title, _body in sections(text)]
        expected = "## Current State" if name == "HANDOFF.md" else "## Priority Queue"
        if len(titles) != 1 or not titles[0].startswith(expected):
            errors.append(f"living-memory/{name}: requires exactly one {expected} section")
        if name == "HANDOFF.md":
            for label in ("Where I stopped", "In flight", "Blocked on", "Don't repeat"):
                if f"**{label}:**" not in text:
                    errors.append(f"living-memory/{name}: missing {label} bucket")
        else:
            count, invalid_marker = queue_items(text)
            if invalid_marker:
                errors.append(f"living-memory/{name}: use a flat numbered list with column-one '1. action' items")
            if count > 7:
                errors.append(f"living-memory/{name}: {count} items exceeds 7")
    if byte_size(hook_json(build_brief(root))) > MAX_OUTPUT_BYTES:
        errors.append("session hook exceeds output budget")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--hook", action="store_true", help="Claude SessionStart JSON")
    modes.add_argument("--check", action="store_true", help="validate the memory contract")
    modes.add_argument("--stop-hook", action="store_true", help="report format drift without blocking")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.check or args.stop_hook:
        errors = validate(root)
        if args.stop_hook:
            result = {"systemMessage": "Memory contract needs attention:\n" + "\n".join(errors)} if errors else {}
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        print("Session memory valid; hook output <= 6000 UTF-8 bytes.")
        return 0
    brief = build_brief(root)
    print(hook_json(brief) if args.hook else brief, end="" if args.hook else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
