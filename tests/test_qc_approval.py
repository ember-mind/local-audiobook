"""apply-fixes must account for every issue before naming a file 'reviewed'."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import apply_review_fixes as apply_fixes


class PendingIssueTests(unittest.TestCase):
    ISSUES = [
        {"from": "una svista", "to": "una svista corretta"},
        {"from": "un residuo", "to": "un residuo tolto"},
    ]

    def test_an_issue_still_in_the_text_is_pending(self):
        pending = apply_fixes.pending_issues(
            self.ISSUES, "Qui resta una svista e un residuo.", {}
        )
        self.assertEqual([number for number, _ in pending], [1, 2])

    def test_text_that_no_longer_contains_it_closes_it(self):
        pending = apply_fixes.pending_issues(
            self.ISSUES, "Qui resta un residuo.", {}
        )
        self.assertEqual([number for number, _ in pending], [2])

    def test_rejection_by_number_or_by_text_closes_it(self):
        text = "Qui resta una svista e un residuo."

        self.assertEqual(
            apply_fixes.pending_issues(self.ISSUES, text, {"1": "va bene così"}),
            apply_fixes.pending_issues(self.ISSUES, text, {"una svista": "idem"}),
        )


class ApplyFixesGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.book = Path(self.temp.name) / "books/demo"
        (self.book / "text").mkdir(parents=True)
        (self.book / "work").mkdir(parents=True)
        (self.book / "book.json").write_text("{}", encoding="utf-8")
        (self.book / "text/narration_final_it.txt").write_text(
            "Il testo con una svista dentro.\n", encoding="utf-8")
        (self.book / "work/language_qc.json").write_text(json.dumps(
            {"issues": [{"from": "una svista", "to": "una correzione",
                         "reason": "errore"}]}), encoding="utf-8")
        self.output = self.book / "text/narration_reviewed_it.txt"
        self.approval = self.book / "work/language_qc_approval.json"
        self.decisions = self.book / "work/language_qc_manual_fixes.json"

    def run_stage(self):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/apply_review_fixes.py"),
             str(self.book / "book.json")],
            capture_output=True, text=True)

    def test_no_decisions_and_an_open_issue_writes_nothing(self):
        result = self.run_stage()

        self.assertEqual(result.returncode, 2)
        self.assertIn("senza decisione", result.stdout)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.approval.exists())

    def test_a_rejection_with_a_reason_is_enough_to_pass(self):
        self.decisions.write_text(json.dumps(
            {"operations": [], "rejected": {"1": "la frase è corretta"}}),
            encoding="utf-8")

        result = self.run_stage()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.output.exists())
        approval = json.loads(self.approval.read_text(encoding="utf-8"))
        self.assertEqual(approval["issues"], 1)
        self.assertEqual(approval["rejected"], {"1": "la frase è corretta"})

    def test_approval_records_the_text_it_approves(self):
        self.decisions.write_text(json.dumps({"operations": [
            {"issue": 1, "kind": "exact", "from": "una svista",
             "to": "una correzione", "expected": 1}]}), encoding="utf-8")

        self.assertEqual(self.run_stage().returncode, 0)

        approval = json.loads(self.approval.read_text(encoding="utf-8"))
        self.assertEqual(
            approval["output_sha256"],
            apply_fixes.sha256(self.output.read_text(encoding="utf-8")),
        )
        self.assertIn("una correzione", self.output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
