"""Fault injection for local state publication and content-addressed covers."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import export_m4b as export
import pandrator_generate_audio as generate
import pandrator_prepare_audio as prepare
import pandrator_state as state_io


class AudioPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "session.json"

    def test_failed_atomic_replace_preserves_previous_state_and_cleans_temporary(self):
        for save in (prepare.save_state, generate.save, export.save):
            with self.subTest(writer=save.__module__):
                self.path.write_text('{"session_id": "keep-me"}')
                before = self.path.read_bytes()
                with patch.object(state_io.os, "replace", side_effect=OSError("disk error")):
                    with self.assertRaisesRegex(OSError, "disk error"):
                        save(self.path, {"session_id": "new"})
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_successful_write_is_valid_unicode_json(self):
        state_io.save_json(self.path, {"title": "Un po’ di felicità"})
        self.assertEqual(json.loads(self.path.read_text()), {"title": "Un po’ di felicità"})

    def test_serialization_error_preserves_previous_state(self):
        state_io.save_json(self.path, {"session_id": "old"})
        before = self.path.read_bytes()
        with self.assertRaises(TypeError):
            state_io.save_json(self.path, {"invalid": object()})
        self.assertEqual(self.path.read_bytes(), before)

    def test_same_size_cover_change_is_uploaded_but_unchanged_cover_is_reused(self):
        cover = self.root / "cover.png"
        cover.write_bytes(b"old-image")
        state = {}
        response = Mock(ok=True)
        response.json.side_effect = [{"artifact_id": "old-cover"}, {"artifact_id": "new-cover"},
                                     {"artifact_id": "other-session-cover"}]
        with patch.object(export, "headers", return_value={}), \
                patch.object(export.requests, "post", return_value=response) as upload:
            self.assertEqual(export.upload_cover("session", cover, state, self.path), "old-cover")
            self.assertEqual(export.upload_cover("session", cover, state, self.path), "old-cover")
            self.assertEqual(upload.call_count, 1)
            cover.write_bytes(b"new-image")
            self.assertEqual(export.upload_cover("session", cover, state, self.path), "new-cover")
            self.assertEqual(upload.call_count, 2)
            self.assertEqual(export.upload_cover("other-session", cover, state, self.path),
                             "other-session-cover")
            self.assertEqual(upload.call_count, 3)


if __name__ == "__main__":
    unittest.main()
