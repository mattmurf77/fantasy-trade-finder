"""The startup envelope must remain bounded without mangling source evidence."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/session_context.py"
SPEC = importlib.util.spec_from_file_location("session_context", SCRIPT)
context = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(context)


class SessionContextTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "living-memory").mkdir()

    def write(self, name, text):
        (self.root / "living-memory" / name).write_text(text)

    def envelope(self):
        output = context.hook_json(context.build_brief(self.root))
        self.assertLessEqual(len(output.encode("utf-8")), 6000)
        return json.loads(output)["hookSpecificOutput"]["additionalContext"]

    def valid(self):
        self.write("HANDOFF.md", "# HANDOFF\n\n## Current State\n\n" + "\n\n".join(
            f"**{label}:** recorded" for label in
            ("Where I stopped", "In flight", "Blocked on", "Don't repeat")))
        self.write("NEXT.md", "# NEXT\n\n## Priority Queue\n\n1. Follow evidence.\n")

    def test_missing_sources_are_explicit_and_do_not_crash(self):
        output = self.envelope()
        for name in context.MEMORY_FILES:
            self.assertIn(name, output)
        self.assertIn("missing", output)
        self.assertTrue(context.validate(self.root))

    def test_complete_unicode_sections_survive_json_escaping(self):
        self.valid()
        entry = '## 2026-09-06 — Test\n\n' + ('😀 "é" \\ example\n' * 25)
        self.write("CHANGELOG.md", '# CHANGELOG\n\n' + entry)
        output = self.envelope()
        self.assertIn(entry.strip(), output)
        self.assertEqual(context.validate(self.root), [])

    def test_oversized_sections_are_omitted_whole(self):
        self.valid()
        self.write("NEXT.md", "# NEXT\n\n## Priority Queue\n\n1. " + "🦄" * 150000)
        self.write("CHANGELOG.md", "## 2026-09-06\n\nBEGIN-OVERSIZED " + '"\\😀' * 8000)
        output = self.envelope()
        self.assertIn("NEXT.md", output)
        self.assertIn("over budget", output)
        self.assertNotIn("BEGIN-OVERSIZED", output)
        self.assertNotIn("🦄", output)
        self.assertTrue(any("exceeds 1500" in e for e in context.validate(self.root)))

    def test_combined_serialized_budget_counts_quotes_and_backslashes(self):
        handoff = '# HANDOFF\n\n## Current State\n\n' + ('"\\' * 950)
        queue = '# NEXT\n\n## Priority Queue\n\n' + ('"\\' * 700)
        first = '## 2026-09-06\n\nFIRST ' + ('"\\' * 550)
        second = '## 2026-09-05\n\nSECOND ' + ('"\\' * 550)
        self.write("HANDOFF.md", handoff)
        self.write("NEXT.md", queue)
        self.write("CHANGELOG.md", first + '\n\n' + second)
        output = self.envelope()
        self.assertIn("Reference only: over budget", output)
        for block in (handoff, queue, first, second):
            # Selection either preserves a whole block or omits it, never slices.
            if block.splitlines()[0] in output:
                self.assertIn(block, output)

    def test_fenced_fake_dates_do_not_displace_real_recent_entries(self):
        self.valid()
        self.write("CHANGELOG.md", "# Changes\n\n```md\n## 2099-01-01\nFAKE\n```\n"
                   "\n## 2026-09-06\nREAL FIRST\n\n## 2026-09-05\nREAL SECOND\n"
                   "\n## 2026-09-04\nOLD THIRD\n")
        output = self.envelope()
        self.assertIn("REAL FIRST", output)
        self.assertIn("REAL SECOND", output)
        self.assertNotIn("OLD THIRD", output)
        self.assertNotIn("FAKE", output)

    def test_unclosed_fence_is_not_injected(self):
        self.valid()
        self.write("CHANGELOG.md", "## 2026-09-06\n\n```sh\nUNFINISHED-CODE\n")
        self.assertNotIn("UNFINISHED-CODE", self.envelope())

    def test_seven_item_and_single_section_contract(self):
        self.valid()
        self.write("NEXT.md", "# NEXT\n\n## Priority Queue\n\n" +
                   "\n".join(f"{i}. task" for i in range(1, 9)))
        self.assertTrue(any("8 items" in e for e in context.validate(self.root)))
        self.write("HANDOFF.md", "## Current State\ncurrent\n## Old State\nhistory")
        self.assertTrue(any("exactly one" in e for e in context.validate(self.root)))

    def test_symlink_cannot_pull_a_credential_into_context(self):
        secret = self.root / "secrets.local.env"
        secret.write_text("SHOULD-NEVER-BE-IN-CONTEXT")
        (self.root / "living-memory/HANDOFF.md").symlink_to(secret)
        output = self.envelope()
        self.assertIn("symlink skipped", output)
        self.assertNotIn(secret.read_text(), output)

    def test_alternative_or_nested_list_markers_cannot_bypass_queue_limit(self):
        self.valid()
        for marker in ("- task", "1) task", "  1. task", "* task", "+ task"):
            with self.subTest(marker=marker):
                self.write("NEXT.md", "# NEXT\n\n## Priority Queue\n\n" +
                           "\n".join([marker] * 8))
                self.assertTrue(any("flat numbered list" in error
                                    for error in context.validate(self.root)))

    def test_fenced_queue_examples_and_continuations_are_not_items(self):
        self.valid()
        self.write("NEXT.md", "# NEXT\n\n## Priority Queue\n\n" +
                   "\n".join(f"{n}. action\n   continuation text" for n in range(1, 8)) +
                   "\n\n````md\n```project-status\n- example\n" +
                   "\n".join(f"{n}) fenced example" for n in range(1, 9)) +
                   "\n```\n````\n")
        self.assertEqual(context.validate(self.root), [])

    def test_symlinked_memory_directory_cannot_import_another_checkout(self):
        outside = self.root / "other-checkout"
        outside.mkdir()
        (outside / "HANDOFF.md").write_text("OUTSIDE-CONTEXT-SENTINEL")
        (self.root / "living-memory").rmdir()
        (self.root / "living-memory").symlink_to(outside, target_is_directory=True)
        output = self.envelope()
        self.assertIn("symlink skipped", output)
        self.assertNotIn("OUTSIDE-CONTEXT-SENTINEL", output)

    def test_literal_shell_text_is_never_executed(self):
        self.valid()
        marker = self.root / "must-not-exist"
        literal = f'$(touch "{marker}")'
        self.write("CHANGELOG.md", "## 2026-09-06\n\n" + literal)
        self.assertIn(literal, self.envelope())
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
