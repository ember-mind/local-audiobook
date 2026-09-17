"""Run the real CLI with an isolated book and a fake stage interpreter."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGES = ["extract_book.py", "clean_book.py", "translate_book.py",
          "finalize_translation.py", "validate_translation.py",
          "build_narration.py", "language_qc.py"]


class PipelineFixture(unittest.TestCase):
    """CLI vera, stadi finti: solo fixture, nessun test."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy2(ROOT / "audiobook", self.root / "audiobook")
        (self.root / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts/ui_translate_progress.py", self.root / "scripts")
        book = self.root / "books/demo"
        book.mkdir(parents=True)
        self.config = book / "book.json"
        self.config.write_text(json.dumps({"title": "Test book", "narration": {
            "start_marker": "Chapter one", "end_marker": "EOF"}}))
        self.calls = self.root / "calls.txt"
        interpreter = self.root / "pandrator/.venv/bin/python"
        interpreter.parent.mkdir(parents=True)
        interpreter.write_text('''#!/bin/bash
name="${1##*/}"
printf '%s\\n' "$name" >> "$CALL_LOG"
if [ "$name" = "${FAIL_SCRIPT:-}" ]; then
  echo "stage failed: $name" >&2
  exit "${FAIL_CODE:-7}"
fi
echo "stage completed: $name"
''')
        interpreter.chmod(0o755)
        self.env = dict(os.environ, PANDRATOR_HOME=str(self.root / "pandrator"),
                        QWEN_HOME=str(self.root / "qwen-home"), CALL_LOG=str(self.calls))

    def prepare(self, failed="", code=7):
        self.calls.unlink(missing_ok=True)
        return subprocess.run(["bash", str(self.root / "audiobook"), "prepare", "demo"],
                              env=dict(self.env, FAIL_SCRIPT=failed, FAIL_CODE=str(code)),
                              capture_output=True, text=True, timeout=10)

    def called(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []


class PipelineTests(PipelineFixture):
    def test_every_stage_failure_stops_the_pipeline(self):
        for index, stage in enumerate(STAGES):
            with self.subTest(stage=stage):
                result = self.prepare(stage)
                self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
                self.assertEqual(self.called(), STAGES[:index + 1])
                self.assertNotIn("TEXT READY", result.stdout)

    def test_review_exit_code_is_preserved(self):
        result = self.prepare("language_qc.py", 2)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("REVIEW REQUIRED", result.stdout)
        self.assertEqual(self.called(), STAGES)

    def test_missing_narration_markers_stop_before_narration(self):
        self.config.write_text(json.dumps({"title": "Test book"}))
        result = self.prepare()
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertEqual(self.called(), STAGES[:5])

    def test_success_runs_each_stage_once(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.called(), STAGES)

    def test_missing_book_does_not_invoke_stages(self):
        self.config.unlink()
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.called(), [])


if __name__ == "__main__":
    unittest.main()


class BookLockTests(PipelineFixture):
    """Un comando per libro: il secondo si ferma invece di sovrascrivere."""

    def lock_dir(self):
        return self.root / "books/demo/work/.lock"

    def hold_lock(self, pid):
        lock = self.lock_dir()
        lock.mkdir(parents=True)
        (lock / "owner").write_text(f"{pid}\nnarrate\n", encoding="utf-8")

    def test_a_live_owner_stops_the_second_command(self):
        self.hold_lock(os.getpid())

        result = self.prepare()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sta lavorando", result.stdout + result.stderr)
        self.assertEqual(self.called(), [])

    def test_a_dead_owner_does_not_block_forever(self):
        self.hold_lock(999999)

        result = self.prepare()

        self.assertIn("processo terminato", result.stdout)
        self.assertEqual(self.called(), STAGES)

    def test_the_lock_is_released_when_the_command_ends(self):
        self.assertEqual(self.prepare().returncode, 0)
        self.assertFalse(self.lock_dir().exists())
