"""Founders' review, "Review pages" (docs/plans/founder-review/pages-design.md).

The operator's review documents (self-contained single-file HTML with comment
boxes) are uploaded at runtime and stored in the database (``founder_pages``);
the founders' comments are saved per box per account (``founder_page_notes``).
The repo is public, so page content is never committed.

This module is the validation: slugs, uploads, note writes. A leaf: no
database, flag, request or server imports. ``server.py`` owns the gate and the
routes; ``database.py`` owns storage.
"""
from __future__ import annotations

import re

SLUG_RE = re.compile(r"[a-z0-9-]{1,64}")
MAX_PAGE_BYTES = 8 * 1024 * 1024       # an upload's raw body
MAX_TITLE_CHARS = 200
MAX_KEY_CHARS = 128
MAX_LABEL_CHARS = 300
MAX_BODY_CHARS = 10_000
MAX_KEYS_PER_SAVE = 200
# A note write is JSON: 200 boxes x 10,000 characters fits well inside this.
MAX_NOTES_BODY_BYTES = 4 * 1024 * 1024

_DOCTYPE = "<!doctype html"


class InvalidRequest(ValueError):
    """``code`` is the route's error string (400 unless the route says otherwise)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def valid_slug(slug) -> bool:
    return isinstance(slug, str) and SLUG_RE.fullmatch(slug) is not None


def parse_upload(slug, title, raw: bytes) -> tuple[str, str]:
    """(title, html) for an upload, or InvalidRequest. The body must be UTF-8, non-empty,
    at most MAX_PAGE_BYTES, and start with ``<!DOCTYPE html`` (any case; leading whitespace
    and a byte-order mark allowed). A missing title defaults to the slug."""
    if not valid_slug(slug):
        raise InvalidRequest("invalid_slug")
    if not raw:
        raise InvalidRequest("empty_body")
    if len(raw) > MAX_PAGE_BYTES:
        raise InvalidRequest("too_large")
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidRequest("not_utf8") from None
    if not html.lstrip("﻿ \t\r\n\f").lower().startswith(_DOCTYPE):
        raise InvalidRequest("not_html")
    text = (title if isinstance(title, str) else "").strip() or slug
    if len(text) > MAX_TITLE_CHARS:
        raise InvalidRequest("title_too_long")
    return text, html


def parse_notes(body) -> list[tuple[str, str, str]]:
    """[(box_key, label, body)] from ``{"set": {key: {"label", "body"}}}``, or InvalidRequest.
    The box key is the page's own free text: only its type and length are checked. A blank
    body is a clear."""
    if not isinstance(body, dict) or not isinstance(body.get("set"), dict):
        raise InvalidRequest("invalid_body")
    entries = body["set"]
    if len(entries) > MAX_KEYS_PER_SAVE:
        raise InvalidRequest("too_many_keys")
    out = []
    for key, value in entries.items():
        if not isinstance(key, str) or not key or len(key) > MAX_KEY_CHARS:
            raise InvalidRequest("invalid_key")
        if not isinstance(value, dict):
            raise InvalidRequest("invalid_note")
        label = value.get("label", "")
        text = value.get("body")
        if label is None:
            label = ""
        if not isinstance(label, str) or not isinstance(text, str):
            raise InvalidRequest("invalid_note")
        if len(label) > MAX_LABEL_CHARS:
            raise InvalidRequest("label_too_long")
        if len(text) > MAX_BODY_CHARS:
            raise InvalidRequest("body_too_long")
        out.append((key, label, text))
    return out
