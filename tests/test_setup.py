"""Exercise setup against a fresh clone layout without installing anything."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy2(ROOT / "setup.sh", self.root / "setup.sh")
        for directory in ("config", "qwen", "patches"):
            shutil.copytree(ROOT / directory, self.root / directory)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        uv = self.bin / "uv"
        uv.write_text("#!/bin/sh\nexit 0\n")
        uv.chmod(0o755)
        for name in ("Pandrator", "Qwen"):
            home = self.root / name
            interpreter = home / ".venv/bin/python"
            interpreter.parent.mkdir(parents=True)
            interpreter.symlink_to(sys.executable)
        (self.root / "Pandrator/.git").mkdir()
        assembler = self.root / "Pandrator/pandrator/web/audio_assembly.py"
        assembler.parent.mkdir(parents=True)
        assembler.write_text("# _room_tone_pcm: already patched test fixture\n")
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        PANDRATOR_HOME=str(self.root / "Pandrator"),
                        QWEN_HOME=str(self.root / "Qwen"))

    def setup(self):
        return subprocess.run(["bash", str(self.root / "setup.sh")], env=self.env,
                              capture_output=True, text=True, timeout=10)

    def test_fresh_clone_uses_configured_reference_not_obsolete_clip(self):
        self.assertFalse((self.root / "qwen/reference_it.wav").exists())
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "Qwen/qwen_pandrator_server.py").exists())
        self.assertTrue((self.root / "Pandrator/roomtone.json").exists())

    def test_missing_configured_transcript_is_reported(self):
        config = json.loads((self.root / "config/voice.json").read_text())
        transcript = self.root / config["reference_dir"] / config["reference_text"]
        transcript.unlink()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(transcript), result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
