"""Exercise the active lint against disposable archive/source trees."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class HistoricalFlowLintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        scripts = self.root / "mobile/scripts"
        scripts.mkdir(parents=True)
        self.script = scripts / "testid-lint.sh"
        shutil.copyfile(ROOT / "mobile/scripts/testid-lint.sh", self.script)
        (scripts / "testid-lint-allow.txt").write_text("")
        source = self.root / "mobile/src"
        source.mkdir()
        (source / "Example.tsx").write_text('<View testID="example.ready" />')
        self.archive = self.root / "archive/retired-tooling/mobile/maestro"

    def run_lint(self):
        return subprocess.run(["bash", str(self.script)], cwd=self.root,
                              capture_output=True, text=True, check=False)

    def test_missing_archive_is_a_failure(self):
        result = self.run_lint()
        self.assertEqual(result.returncode, 2)
        self.assertIn("required historical flow archive missing", result.stderr)

    def test_empty_archive_is_a_failure(self):
        self.archive.mkdir(parents=True)
        (self.archive / "README.md").write_text("Historical archive")
        result = self.run_lint()
        self.assertEqual(result.returncode, 2)
        self.assertIn("contains no YAML", result.stderr)

    def test_preserved_flow_references_current_source(self):
        self.archive.mkdir(parents=True)
        flow = self.archive / "example.yaml"
        flow.write_text('- tapOn:\n    id: "example.ready"\n')
        self.assertEqual(self.run_lint().returncode, 0)
        flow.write_text('- tapOn:\n    id: "example.missing"\n')
        result = self.run_lint()
        self.assertEqual(result.returncode, 1)
        self.assertIn("example.missing", result.stderr)

    def test_banned_historical_pattern_still_fails(self):
        self.archive.mkdir(parents=True)
        (self.archive / "example.yaml").write_text('- sleep: 1000\n')
        self.assertEqual(self.run_lint().returncode, 2)


if __name__ == "__main__":
    unittest.main()
