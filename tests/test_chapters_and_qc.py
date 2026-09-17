"""Chapter provenance, ffmetadata escaping and QC response validation.

No Pandrator, no model: the API layer is stubbed and ffmpeg is only used by
the round-trip test, which skips when it is not installed.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import add_chapters
import language_qc


class ChapterTimingTests(unittest.TestCase):
    def test_a_segment_without_a_duration_stops_the_stage(self):
        segments = [{"id": "a", "ordinal": 1}, {"id": "b", "ordinal": 2}]
        durations = {"a": (1000, 100)}

        with self.assertRaisesRegex(SystemExit, "durata di 1 segmenti"):
            add_chapters.locate(
                [{"title": "Uno", "start_marker": "x"}], segments, durations
            )

    def test_known_durations_accumulate_in_order(self):
        segments = [{"id": "a", "ordinal": 1, "text": "Primo capitolo"},
                    {"id": "b", "ordinal": 2, "text": "Secondo capitolo"}]
        durations = {"a": (1000, 100), "b": (2000, 0)}

        located, problems = add_chapters.locate(
            [{"title": "Uno", "start_marker": "Primo capitolo"},
             {"title": "Due", "start_marker": "Secondo capitolo"}],
            segments,
            durations,
        )

        self.assertEqual(problems, [])
        self.assertEqual(located, [("Uno", 0), ("Due", 1100)])


class FFMetadataTests(unittest.TestCase):
    def test_syntax_characters_are_escaped(self):
        self.assertEqual(
            add_chapters.ffmetadata_escape("a=b;c#d\\e"),
            "a\\=b\;c\\#d\\\\e",
        )

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "ffmpeg not installed")
    def test_titles_survive_a_real_mux(self):
        titles = ["Uno; con = segni", "Due\nSeconda riga", "Tre #tre"]

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source, output = tmp / "in.m4b", tmp / "out.m4b"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-f", "lavfi",
                 "-i", "anullsrc=r=24000:cl=mono", "-t", "6",
                 "-c:a", "aac", str(source), "-y"], check=True)

            metadata = tmp / "chapters.txt"
            add_chapters.write_metadata_file(
                list(zip(titles, (0, 2000, 4000))), 6000, metadata)

            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(source), "-i", str(metadata),
                 "-map_metadata", "1", "-map_chapters", "1", "-c", "copy",
                 str(output), "-y"], check=True)

            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_chapters",
                 "-print_format", "json", str(output)],
                capture_output=True, text=True, check=True)

            written = [c["tags"]["title"] for c in json.loads(probe.stdout)["chapters"]]

        self.assertEqual(written, titles)


class ChapterProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "book.m4b"
        self.target.write_bytes(b"audio")
        self.digest = add_chapters.sha256_file(self.target)

    def test_a_file_other_than_the_exported_one_is_refused(self):
        state = {"export_sha256": "0" * 64, "export_assembly_id": "assembly-1"}

        with self.assertRaisesRegex(SystemExit, "hash diverso"):
            add_chapters.check_provenance(state, self.target)

    def test_matching_file_returns_the_assembly_to_demand(self):
        state = {"export_sha256": self.digest, "export_assembly_id": "assembly-1"}

        self.assertEqual(
            add_chapters.check_provenance(state, self.target), "assembly-1"
        )

    def test_a_newer_assembly_does_not_describe_the_exported_file(self):
        with patch.object(add_chapters, "api", return_value={
                "item": {"id": "assembly-2", "status": "completed"}}):
            with self.assertRaisesRegex(SystemExit, "non e' quello"):
                add_chapters.take_durations("session", "assembly-1")

    def test_state_without_provenance_only_warns(self):
        self.assertIsNone(add_chapters.check_provenance({}, self.target))


class QCResponseTests(unittest.TestCase):
    def test_a_response_without_issues_is_not_a_clean_verdict(self):
        for payload in ('{}', '{"verdict": "ok"}'):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "issues"):
                    language_qc.clean_json(payload)

    def test_issues_must_be_a_list_of_objects(self):
        for payload in ('{"issues": null}', '{"issues": "nessuno"}',
                        '{"issues": ["testo"]}'):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    language_qc.clean_json(payload)

    def test_an_empty_list_is_still_a_valid_clean_verdict(self):
        self.assertEqual(language_qc.clean_json('{"issues": []}'), {"issues": []})

    def test_cache_key_follows_prompt_model_and_validator(self):
        base = language_qc.qc_fingerprint("testo", "model-a")

        self.assertNotEqual(base, language_qc.qc_fingerprint("testo", "model-b"))
        self.assertNotEqual(base, language_qc.qc_fingerprint("altro", "model-a"))

        with patch.object(language_qc, "VALIDATOR_VERSION",
                          language_qc.VALIDATOR_VERSION + 1):
            self.assertNotEqual(base, language_qc.qc_fingerprint("testo", "model-a"))


if __name__ == "__main__":
    unittest.main()
