#!/usr/bin/env python3

"""Registra e verifica le versioni con cui la pipeline funziona davvero.

Pandrator viene clonato da git e qwen-tts installato da PyPI: due macchine
allestite in momenti diversi, o la stessa macchina dopo un aggiornamento,
possono ritrovarsi con codice diverso sotto la stessa procedura. La patch
del room tone, poi, e' scritta contro un punto preciso del codice di
Pandrator.

    ./audiobook lock          scrive config/environment.lock.json
    ./audiobook lock --check  confronta e basta (esce 1 se qualcosa e' cambiato)

Il lock non e' un vincolo automatico: `setup.sh` lo usa per fissare la
revisione di Pandrator, `doctor` segnala le differenze. Aggiornare vuol dire
rifare il lock di proposito, dopo aver provato su un libro piccolo.
"""

from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "config" / "environment.lock.json"

PANDRATOR_HOME = Path(
    os.environ.get("PANDRATOR_HOME", Path.home() / "src/Pandrator")
)
QWEN_HOME = Path(
    os.environ.get("QWEN_HOME", Path.home() / "src/qwen3-tts-official")
)

# Quello che conta per la sintesi e per la patch. Non tutto l'ambiente:
# un lock che elenca ogni pacchetto e' rumore che nessuno rilegge.
TRACKED = (
    "qwen-tts",
    "torch",
    "torchaudio",
    "transformers",
    "fastapi",
    "uvicorn",
    "soundfile",
    "numpy",
)


def git_revision(repo):
    if not (repo / ".git").is_dir():
        return None

    try:
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return None


def git_describe(repo):
    try:
        return subprocess.run(
            ["git", "-C", str(repo), "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return None


def packages(venv_python):
    """Versioni installate, lette dentro il venv che le usa davvero."""

    if not venv_python.is_file():
        return {}

    code = (
        "import importlib.metadata as m, json, platform;"
        f"names={TRACKED!r};"
        "out={'python': platform.python_version()};"
        "out.update({n: (m.version(n) if _try(n) else None) for n in names});"
        "print(json.dumps(out))"
    )

    helper = (
        "def _try(name):\n"
        "    import importlib.metadata as m\n"
        "    try:\n"
        "        m.version(name)\n"
        "        return True\n"
        "    except Exception:\n"
        "        return False\n"
    )

    try:
        result = subprocess.run(
            [str(venv_python), "-c", helper + code],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return {}

    return json.loads(result.stdout)


def sha256_file(path):
    if not path.is_file():
        return None

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def snapshot():
    return {
        "version": 1,
        "pandrator": {
            "home": str(PANDRATOR_HOME),
            "revision": git_revision(PANDRATOR_HOME),
            "describe": git_describe(PANDRATOR_HOME),
            "python": packages(PANDRATOR_HOME / ".venv/bin/python").get(
                "python"
            ),
        },
        "qwen": packages(QWEN_HOME / ".venv/bin/python"),
        "roomtone_patch_sha256": sha256_file(
            ROOT / "patches" / "pandrator-roomtone.patch"
        ),
    }


def differences(locked, current):
    """Coppie (percorso, atteso, trovato) fra due snapshot."""

    found = []

    def walk(path, expected, actual):
        if isinstance(expected, dict):
            for key, value in expected.items():
                if key in ("home", "recorded_at", "version"):
                    continue
                walk(
                    f"{path}.{key}" if path else key,
                    value,
                    (actual or {}).get(key),
                )
            return

        if expected != actual:
            found.append((path, expected, actual))

    walk("", locked, current)

    return found


def main():
    check = "--check" in sys.argv[1:]
    current = snapshot()

    if check:
        if not LOCK.is_file():
            print("○ Nessun lock: ./audiobook lock per registrarlo")
            return 0

        locked = json.loads(LOCK.read_text(encoding="utf-8"))
        drift = differences(locked, current)

        if not drift:
            print("✓ Ambiente come da lock")
            print(f"  Pandrator {locked['pandrator'].get('describe')}")
            return 0

        print("⚠ Ambiente diverso dal lock")

        for path, expected, actual in drift:
            print(f"  {path}: {expected} → {actual}")

        print()
        print("Se il cambiamento e' voluto e provato: ./audiobook lock")

        return 1

    current["recorded_at"] = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(
        json.dumps(current, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"✓ Lock scritto · {LOCK}")
    print(f"  Pandrator {current['pandrator'].get('describe')}")
    print(f"  qwen-tts {current['qwen'].get('qwen-tts')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
