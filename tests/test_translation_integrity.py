"""Checkpoint and response contracts; no model downloads or HTTP calls."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import translate_book as translate


class TranslationFixture(unittest.TestCase):
    """Libro finto su disco: solo fixture, nessun test."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.book = Path(self.temp.name) / "books/demo"
        (self.book / "text").mkdir(parents=True)
        self.config = self.book / "book.json"
        self.settings = {"translation": {"server_model": "test-model", "chunk_chars": 3500}}
        self.config.write_text(json.dumps(self.settings))
        (self.book / "text/source_en.txt").write_text("An original paragraph.")
        self.checkpoint = self.book / "work/translation/checkpoint.json"
        self.chunks = self.book / "work/translation/translated"
        self.addCleanup(setattr, translate, "SYSTEM_PROMPT", translate.SYSTEM_PROMPT)

    def run_main(self):
        with patch.object(sys, "argv", ["translate_book.py", str(self.config)]), \
                contextlib.redirect_stdout(io.StringIO()):
            translate.main()

    def prepare_checkpoint(self):
        with patch.object(translate, "start_llama_server", return_value=(None, "test-model")), \
                patch.object(translate, "translate_chunk", return_value="Un paragrafo originale."):
            self.run_main()


class TranslationIntegrityTests(TranslationFixture):
    def test_unchanged_configuration_reuses_chunks(self):
        self.prepare_checkpoint()
        with patch.object(translate, "start_llama_server", return_value=(None, "test-model")), \
                patch.object(translate, "translate_chunk") as call:
            self.run_main()
            call.assert_not_called()

    def test_prompt_changes_refuse_to_reuse_old_chunks(self):
        self.prepare_checkpoint()
        before = (self.chunks / "chunk-0001.txt").read_bytes()
        for key, value in (("context", "A history of clothing"),
                           ("terminology", {"dress": "abito"}),
                           ("instructions", "Keep film titles in English.")):
            with self.subTest(field=key):
                changed = {"translation": dict(self.settings["translation"], **{key: value})}
                self.config.write_text(json.dumps(changed))
                with patch.object(translate, "start_llama_server") as start:
                    with self.assertRaisesRegex(SystemExit, "--reset"):
                        self.run_main()
                    start.assert_not_called()
                self.assertEqual((self.chunks / "chunk-0001.txt").read_bytes(), before)

    def test_legacy_checkpoint_is_not_silently_trusted(self):
        self.prepare_checkpoint()
        data = json.loads(self.checkpoint.read_text())
        data["version"] = 2
        data.pop("system_prompt_sha256", None)
        self.checkpoint.write_text(json.dumps(data))
        with patch.object(translate, "start_llama_server") as start:
            with self.assertRaisesRegex(SystemExit, "--reset"):
                self.run_main()
            start.assert_not_called()
        self.assertTrue((self.chunks / "chunk-0001.txt").is_file())

    def test_truncated_response_is_not_committed_as_a_chunk(self):
        response = Mock()
        response.json.return_value = {"choices": [{"finish_reason": "length",
            "message": {"content": "Traduzione troncata a metà"}}]}
        with patch.object(translate, "start_llama_server", return_value=(None, "test-model")), \
                patch.object(translate.requests, "post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "length"):
                self.run_main()
        self.assertEqual(list(self.chunks.glob("chunk-*.txt")), [])
        self.assertFalse((self.book / "text/book_it.txt").exists())

    def test_only_complete_text_responses_are_accepted(self):
        for reason in ("length", "content_filter", "tool_calls", None):
            with self.subTest(reason=reason):
                response = Mock()
                response.json.return_value = {"choices": [{"finish_reason": reason,
                    "message": {"content": "Risposta non completa"}}]}
                with patch.object(translate.requests, "post", return_value=response):
                    with self.assertRaises(RuntimeError):
                        translate.translate_chunk("http://unused/v1", "test", "source")

    def test_valid_completion_is_returned(self):
        response = Mock()
        response.json.return_value = {"choices": [{"finish_reason": "stop",
            "message": {"content": "  Traduzione completa.  "}}]}
        with patch.object(translate.requests, "post", return_value=response):
            self.assertEqual(translate.translate_chunk("http://unused/v1", "test", "source"),
                             "Traduzione completa.")

    def test_malformed_content_has_actionable_error(self):
        for content in (None, [], 42, "   "):
            with self.subTest(content=content):
                response = Mock()
                response.json.return_value = {"choices": [{"finish_reason": "stop",
                    "message": {"content": content}}]}
                with patch.object(translate.requests, "post", return_value=response):
                    with self.assertRaises(RuntimeError):
                        translate.translate_chunk("http://unused/v1", "test", "source")


if __name__ == "__main__":
    unittest.main()


class LegacyCheckpointAdoptionTests(TranslationFixture):
    """Version 2 checkpoints: block by default, adopt only when told to."""

    def downgrade_to_version_2(self):
        data = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        data["version"] = 2
        data.pop("system_prompt_sha256")
        self.checkpoint.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def run_main_with(self, *flags):
        argv = ["translate_book.py", str(self.config), *flags]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            translate.main()

    def test_version_2_blocks_and_keeps_the_translated_chunks(self):
        self.prepare_checkpoint()
        self.downgrade_to_version_2()
        before = (self.chunks / "chunk-0001.txt").read_bytes()
        stored = self.checkpoint.read_bytes()

        with patch.object(translate, "start_llama_server") as start:
            with self.assertRaisesRegex(SystemExit, "--adopt-checkpoint"):
                self.run_main_with()
            start.assert_not_called()

        self.assertEqual(self.checkpoint.read_bytes(), stored)
        self.assertEqual((self.chunks / "chunk-0001.txt").read_bytes(), before)

    def test_adopting_stamps_the_current_prompt_and_reuses_the_work(self):
        self.prepare_checkpoint()
        self.downgrade_to_version_2()
        before = (self.chunks / "chunk-0001.txt").read_bytes()

        with patch.object(translate, "start_llama_server", return_value=(None, "test-model")), \
                patch.object(translate, "translate_chunk") as call:
            self.run_main_with("--adopt-checkpoint")
            call.assert_not_called()

        data = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 3)
        self.assertEqual(
            data["system_prompt_sha256"],
            translate.sha256(translate.SYSTEM_PROMPT),
        )
        self.assertEqual((self.chunks / "chunk-0001.txt").read_bytes(), before)

    def test_adoption_does_not_cover_a_changed_source(self):
        self.prepare_checkpoint()
        self.downgrade_to_version_2()
        (self.book / "text/source_en.txt").write_text("A different paragraph.")

        with patch.object(translate, "start_llama_server") as start:
            with self.assertRaisesRegex(SystemExit, "--reset"):
                self.run_main_with("--adopt-checkpoint")
            start.assert_not_called()

        self.assertEqual(
            json.loads(self.checkpoint.read_text(encoding="utf-8"))["version"], 2
        )
