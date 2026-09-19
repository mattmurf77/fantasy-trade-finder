"""Regression checks for conservative status migration and reproducible indexes."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "project_hygiene", Path(__file__).resolve().parents[2] / "scripts/project_hygiene.py"
)
hygiene = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hygiene
SPEC.loader.exec_module(hygiene)


class ProjectHygieneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def record(self, status="planned", evidence="scope.md", summary="A useful initiative"):
        return hygiene.encode_status({"status": status, "updated": "2026-09-06", "summary": summary, "evidence": evidence}) + "\n"

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_new_untracked_home_is_initialized_without_claiming_shipped(self):
        source = self.put("docs/plans/new/status.md", "# Old status\n\nCOMPLETE — perhaps shipped!\n")
        self.assertTrue(hygiene.run(self.root, write=False))
        self.assertEqual(hygiene.run(self.root, write=True), [])
        record = hygiene.read_status(source.read_text(), source)
        self.assertEqual(record["status"], "needs-review")
        self.assertEqual(record["updated"], "")
        self.assertIn("COMPLETE — perhaps shipped!", source.read_text())
        self.assertIn("new/status.md", (self.root / "docs/plans/README.md").read_text())

    def test_write_is_idempotent_and_check_is_read_only(self):
        self.put("docs/plans/new/status.md", self.record())
        self.assertEqual(hygiene.run(self.root, write=True), [])
        before = self.snapshot()
        self.assertEqual(hygiene.run(self.root, write=True), [])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(hygiene.run(self.root, write=False), [])
        self.assertEqual(self.snapshot(), before)
        self.put("docs/plans/new/status.md", self.record("blocked"))
        before = self.snapshot()
        self.assertTrue(hygiene.run(self.root, write=False))
        self.assertEqual(self.snapshot(), before)

    def test_archive_and_inactive_are_catalog_only(self):
        self.put("docs/plans/archive/2026/old/status.md", self.record("needs-review"))
        self.put("docs/plans/finished/status.md", self.record("shipped", "release.md: merged PR #42 and enabled"))
        self.put("docs/plans/current/status.md", self.record())
        self.assertEqual(hygiene.run(self.root, write=True), [])
        active = (self.root / "docs/plans/README.md").read_text()
        full = (self.root / "docs/plans/CATALOG.md").read_text()
        self.assertNotIn("old/status.md", active)
        self.assertNotIn("finished/status.md", active)
        self.assertIn("current/status.md", active)
        self.assertIn("archive/2026/old/status.md", full)
        self.assertIn("finished/status.md", full)
        self.assertIn("3 entries.", full)

    def test_flat_plans_and_duplicate_item_ids_keep_distinct_sources(self):
        self.put("docs/plans/flat.md", "# A flat plan\n")
        self.put("docs/feedback/items/169-first/status.md", self.record())
        self.put("docs/feedback/items/169-second/status.md", self.record())
        self.put("docs/feedback/items/403-pointer.md", "# Pointer\n")
        self.assertEqual(hygiene.run(self.root, write=True), [])
        catalog = (self.root / "docs/feedback/items/CATALOG.md").read_text()
        self.assertIn("169-first/status.md", catalog)
        self.assertIn("169-second/status.md", catalog)
        self.assertIn("403-pointer.md", catalog)
        self.assertIn("3 entries.", catalog)
        self.assertIn("# A flat plan", (self.root / "docs/plans/flat.md").read_text())

    def test_invalid_status_prevents_all_writes(self):
        self.put("docs/plans/invalid/status.md", self.record("looks-done"))
        self.put("docs/plans/new/plan.md", "# Newly discovered plan\n")
        before = self.snapshot()
        self.assertTrue(hygiene.run(self.root, write=True))
        self.assertEqual(self.snapshot(), before)

    def test_released_state_needs_evidence_and_unknown_date_stays_unknown(self):
        source = self.put("docs/plans/invalid/status.md", self.record("shipped", ""))
        with self.assertRaisesRegex(ValueError, "requires a concrete evidence"):
            hygiene.read_status(source.read_text(), source)

    def test_malformed_and_duplicate_records_are_not_silently_replaced(self):
        for text in ["```project-status\n{bad}\n```", "```project-status\n", self.record() + self.record()]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    hygiene.read_status(text, Path("status.md"))

    def test_extra_unfinished_status_opener_is_not_ignored(self):
        valid = self.record()
        for text in (valid + "\n```project-status\n",
                     valid + "\n```project-status\n{bad}\n```",
                     "```project-status\n" + valid):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    hygiene.read_status(text, Path("status.md"))

    def test_quoted_status_example_does_not_become_the_current_record(self):
        example = "````md\n" + self.record("shipped", "example-only.md") + "````\n"
        self.assertIsNone(hygiene.read_status(example, Path("status.md")))
        record = hygiene.read_status(example + self.record("planned"), Path("status.md"))
        self.assertEqual(record["status"], "planned")

    def test_misplaced_archive_work_fails_without_rewriting_indexes(self):
        for path in ("stranded.md", "legacy/status.md", "2026.md"):
            with self.subTest(path=path):
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    stray = root / "docs/plans/archive" / path
                    stray.parent.mkdir(parents=True)
                    stray.write_text("# Unindexed history\n")
                    errors = hygiene.run(root, write=True)
                    self.assertTrue(any("archive/<year>/" in error for error in errors))
                    self.assertEqual(stray.read_text(), "# Unindexed history\n")
                    self.assertFalse((root / "docs/plans/README.md").exists())
                    self.assertTrue(hygiene.run(root, write=False))

    def test_archive_readme_and_claude_are_allowed_beside_years(self):
        self.put("docs/plans/archive/README.md", "# Archive map\n")
        self.put("docs/plans/archive/CLAUDE.md", "# Historical retrieval\n")
        self.put("docs/plans/archive/2026/old/status.md", self.record("needs-review"))
        self.assertEqual(hygiene.run(self.root, write=True), [])
        self.assertEqual(hygiene.run(self.root, write=False), [])
        catalog = (self.root / "docs/plans/CATALOG.md").read_text()
        self.assertIn("archive/2026/old/status.md", catalog)
        self.assertIn("1 entries.", catalog)

    def test_hidden_templates_symlinks_are_excluded_and_table_cells_escaped(self):
        self.put("docs/plans/_templates/example.md", "template")
        self.put("docs/plans/.scratch/example.md", "scratch")
        source = self.put("docs/plans/current/status.md", self.record(summary="Choice A | B\nnext line <tag>"))
        (source.parent.parent / "linked").symlink_to(source.parent, target_is_directory=True)
        self.assertEqual(hygiene.run(self.root, write=True), [])
        active = (self.root / "docs/plans/README.md").read_text()
        self.assertIn("1 entries.", active)
        self.assertIn("Choice A &#124; B next line &lt;tag&gt;", active)
        self.assertNotIn("_templates", active)

    def test_linked_status_source_cannot_write_outside_its_home(self):
        target = self.put("outside.md", "# Preserve this source\n")
        folder = self.root / "docs/plans/current"
        folder.mkdir(parents=True)
        (folder / "status.md").symlink_to(target)
        before = self.snapshot()
        self.assertTrue(hygiene.run(self.root, write=True))
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
