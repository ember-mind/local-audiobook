"""Regression tests for session identity, stale jobs and interrupted monitoring."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pandrator_prepare_audio as prepare
import pandrator_generate_audio as generate


def response(status, body):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    return result


class SessionIdentityTests(unittest.TestCase):
    def test_only_404_recreates_a_missing_session_and_clears_all_old_artifacts(self):
        state = {"session_id": "old", "source_sha256": "old-source",
                 "prepared_fingerprint": "old-fingerprint", "generation_job_id": "old-job",
                 "cover_artifact_id": "old-cover", "export_artifact_id": "old-export"}
        with patch.object(prepare, "headers", return_value={}), \
                patch.object(prepare.requests, "request", side_effect=[
                    response(404, {}), response(201, {"id": "new"})]):
            self.assertEqual(prepare.ensure_session("Book", state), "new")
        self.assertEqual(state, {"session_id": "new"})

    def test_auth_and_server_errors_do_not_create_duplicate_sessions(self):
        for status in (401, 403, 429, 500, 503):
            with self.subTest(status=status):
                state = {"session_id": "old", "prepared_fingerprint": "keep"}
                before = dict(state)
                with patch.object(prepare, "headers", return_value={}), \
                        patch.object(prepare.requests, "request", side_effect=[
                            response(status, {}), response(201, {"id": "wrong-new"})]) as call:
                    with self.assertRaises(RuntimeError):
                        prepare.ensure_session("Book", state)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(state, before)

    def test_existing_session_preserves_cache(self):
        state = {"session_id": "old", "prepared_fingerprint": "keep"}
        with patch.object(prepare, "api", return_value={}) as call:
            self.assertEqual(prepare.ensure_session("Book", state), "old")
            call.assert_called_once_with("GET", "/sessions/old")
        self.assertEqual(state["prepared_fingerprint"], "keep")


class AudioRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.book = self.root / "books/demo"
        (self.book / "text").mkdir(parents=True)
        (self.book / "book.json").write_text('{"title": "Demo"}')
        self.source = self.book / "text/narration_ready_it.txt"
        self.source.write_text("Una narrazione di prova.\n")
        self.state_path = self.book / "work/pandrator/session.json"
        self.state_path.parent.mkdir(parents=True)
        self.token = self.root / "token"
        self.token.write_text("test-token")
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.state = {"session_id": "session", "source_sha256": digest,
                      "prepared_sha256": digest, "prepared_fingerprint": "old-fingerprint",
                      "max_sentence_length": 600, "generation_job_id": "old-job"}
        self.state_path.write_text(json.dumps(self.state))

    def run_main(self, module):
        with patch.object(module, "ROOT", self.root), patch.object(module, "TOKEN_FILE", self.token), \
                patch.object(sys, "argv", ["script", "demo"]), \
                contextlib.redirect_stdout(io.StringIO()):
            module.main()

    def test_repreparing_changed_text_invalidates_generation_and_export_state(self):
        self.state.update(assembly_id="old-assembly", export_artifact_id="old-export")
        self.state_path.write_text(json.dumps(self.state))
        self.source.write_text("Una versione diversa del testo.\n")
        with patch.object(prepare, "api", return_value={"status": "completed"}), \
                patch.object(prepare, "upload_source") as upload, patch.object(prepare, "run_stage"):
            self.run_main(prepare)
        upload.assert_called_once()
        updated = json.loads(self.state_path.read_text())
        self.assertNotIn("generation_job_id", updated)
        self.assertNotIn("assembly_id", updated)
        self.assertNotIn("export_artifact_id", updated)
        self.assertTrue(updated["generation_requires_fresh_run"])
        self.assertEqual(updated["prepared_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_reprepare_refuses_to_replace_input_of_a_running_job(self):
        self.source.write_text("Changed text")
        before = self.state_path.read_bytes()
        with patch.object(prepare, "api", return_value={"status": "running"}), \
                patch.object(prepare, "upload_source") as upload, \
                patch.object(prepare, "run_stage") as stage:
            with self.assertRaises(SystemExit):
                self.run_main(prepare)
        upload.assert_not_called()
        stage.assert_not_called()
        self.assertEqual(json.loads(self.state_path.read_bytes()), json.loads(before))

    def test_completed_historical_job_does_not_hide_pending_current_segments(self):
        def api(method, path, **kwargs):
            if method == "GET":
                return {"status": "completed"}
            return {"id": "new-run", "job_id": "new-job"}
        with patch.object(generate, "api", side_effect=api) as call, \
                patch.object(generate, "qwen_ready", return_value=True), \
                patch.object(generate, "pending_segment_ids", return_value=(["pending"], 2)) as pending, \
                patch.object(generate, "wait_job") as wait:
            self.run_main(generate)
            pending.assert_called_once_with("session")
            wait.assert_called_once()
            self.assertEqual(wait.call_args.args[0], "new-job")
            self.assertTrue(any(c.args[0] == "POST" for c in call.call_args_list))

    def test_new_preparation_never_reuses_segments_of_a_previous_generation(self):
        self.state.pop("generation_job_id")
        self.state["generation_requires_fresh_run"] = True
        self.state_path.write_text(json.dumps(self.state))
        with patch.object(generate, "api", return_value={"id": "fresh-job"}) as call, \
                patch.object(generate, "qwen_ready", return_value=True), \
                patch.object(generate, "pending_segment_ids", return_value=([], 20)) as old_segments, \
                patch.object(generate, "wait_job"):
            self.run_main(generate)
        old_segments.assert_not_called()
        call.assert_called_once()
        self.assertEqual(call.call_args.args[:2],
                         ("POST", "/sessions/session/stages/generate_audio/run"))
        updated = json.loads(self.state_path.read_text())
        self.assertFalse(updated["generation_requires_fresh_run"])
        self.assertEqual(updated["generation_job_id"], "fresh-job")

    def test_job_lookup_failure_never_starts_a_replacement(self):
        with patch.object(generate, "api", side_effect=RuntimeError("temporary outage")) as call, \
                patch.object(generate, "qwen_ready", return_value=True), \
                patch.object(generate, "pending_segment_ids", return_value=(["pending"], 1)) as pending:
            with self.assertRaisesRegex(RuntimeError, "temporary outage"):
                self.run_main(generate)
            pending.assert_not_called()
            self.assertEqual(call.call_count, 1)

    def test_monitor_failure_never_starts_a_replacement(self):
        with patch.object(generate, "api", return_value={"status": "running", "id": "duplicate"}) as call, \
                patch.object(generate, "qwen_ready", return_value=True), \
                patch.object(generate, "pending_segment_ids", return_value=(["pending"], 1)) as pending, \
                patch.object(generate, "wait_job", side_effect=RuntimeError("monitor disconnected")):
            with self.assertRaisesRegex(RuntimeError, "monitor disconnected"):
                self.run_main(generate)
            pending.assert_not_called()
            self.assertEqual(call.call_count, 1)

    def test_stale_preparation_cannot_generate_changed_local_text(self):
        self.source.write_text("New version not prepared")
        with patch.object(generate, "api") as api, \
                patch.object(generate, "qwen_ready", return_value=False):
            with self.assertRaisesRegex(SystemExit, "prepare-audio"):
                self.run_main(generate)
        api.assert_not_called()

    def test_all_completed_segments_do_not_require_qwen_running(self):
        with patch.object(generate, "api", return_value={"status": "completed"}), \
                patch.object(generate, "pending_segment_ids", return_value=([], 2)), \
                patch.object(generate, "qwen_ready", return_value=False) as ready:
            self.run_main(generate)
        ready.assert_not_called()

    def test_failed_reprepare_does_not_leave_an_old_prepared_marker(self):
        self.source.write_text("Changed text")
        with patch.object(prepare, "api", return_value={"status": "completed"}), \
                patch.object(prepare, "upload_source"), \
                patch.object(prepare, "run_stage", side_effect=RuntimeError("stage failed")):
            with self.assertRaisesRegex(RuntimeError, "stage failed"):
                self.run_main(prepare)
        updated = json.loads(self.state_path.read_text())
        self.assertNotIn("prepared_sha256", updated)
        self.assertNotIn("prepared_fingerprint", updated)
        self.assertNotIn("generation_job_id", updated)

    def test_repeated_segment_cursor_fails_instead_of_looping(self):
        page = {"items": [{"id": "1"}], "next_cursor": 1}
        with patch.object(generate, "api", return_value=page) as call:
            with self.assertRaisesRegex(RuntimeError, "cursore"):
                generate.segments("session")
            self.assertEqual(call.call_count, 2)

    def test_pagination_follows_cursor_even_without_total(self):
        pages = [{"items": [{"id": "1"}], "next_cursor": 1},
                 {"items": [{"id": "2"}], "next_cursor": None}]
        with patch.object(generate, "api", side_effect=pages):
            self.assertEqual([s["id"] for s in generate.segments("session")], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
