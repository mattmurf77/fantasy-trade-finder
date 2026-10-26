"""CI guard: server.py's deck-shaping code can't change without a deck pipeline bump.

server.py isn't in the engine code hash (that would cold every stored page on
every deploy), so a change to its deck layers reaches stored pages only through
the manual `DECK_PIPELINE_VERSION` bump (and, after 11-10, it's a MOD-M1 re-run
trigger). This pins `server.DECK_PIPELINE_DIGEST`, the digest of the functions
in `server.DECK_PIPELINE_FUNCTIONS`, normalized as their AST with docstrings
stripped, so a comment, docstring or formatting edit doesn't trip it and a
logic edit does.

On a failure: bump DECK_PIPELINE_VERSION, re-pin DECK_PIPELINE_DIGEST to
`server._deck_pipeline_digest()`, and have models-eng review.
"""
import inspect

import pytest

import backend.server as server

MESSAGE = "bump DECK_PIPELINE_VERSION and re-pin (models-eng reviews)"


def test_the_deck_pipeline_digest_is_pinned():
    if server._deck_pipeline_digest() != server.DECK_PIPELINE_DIGEST:
        pytest.fail(MESSAGE)


def test_every_listed_function_exists_in_server():
    for name in server.DECK_PIPELINE_FUNCTIONS:
        assert inspect.isfunction(getattr(server, name, None)), name
    assert len(set(server.DECK_PIPELINE_FUNCTIONS)) == len(server.DECK_PIPELINE_FUNCTIONS)


def _digest_with(name, edit):
    """The digest with one listed function's source edited."""
    real = lambda fn: inspect.getsource(getattr(server, fn))
    return server._deck_pipeline_digest(
        source_of=lambda fn: edit(real(fn)) if fn == name else real(fn))


def test_comment_docstring_and_formatting_edits_keep_the_digest():
    def cosmetic(source):
        lines = source.splitlines()
        lines.insert(1, "    # a new comment")
        source = "\n".join(lines) + "\n"
        return source.replace('"""', '"""Reworded. ', 1).replace(", ", ",  ")
    assert _digest_with("_order_deck", cosmetic) == server.DECK_PIPELINE_DIGEST


def test_a_one_token_logic_edit_moves_the_digest():
    source = inspect.getsource(server._apply_deck_suppression)
    assert "max(declines)" in source
    assert _digest_with("_apply_deck_suppression",
                        lambda s: s.replace("max(declines)", "min(declines)", 1)) != server.DECK_PIPELINE_DIGEST
