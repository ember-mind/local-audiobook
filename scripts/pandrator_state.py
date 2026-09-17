"""Small persistence and error contracts shared by the Pandrator stages."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


class PandratorAPIError(RuntimeError):
    """Preserve HTTP status so only a real 404 can trigger recovery."""

    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path, state):
    """Replace a complete JSON document, never truncate the previous state.

    A unique temporary file avoids temporary-name collisions. This is not a
    multi-process lock: callers must still serialize writes to the same book.
    """
    path = Path(path)
    serialized = json.dumps(state, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def invalidate_generation(state):
    """Drop downstream references before replacing prepared text in a session."""
    for key in list(state):
        if key.startswith(("generation_", "assembly_", "export_")):
            state.pop(key)
