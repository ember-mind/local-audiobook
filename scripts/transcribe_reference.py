#!/usr/bin/env python3

from pathlib import Path
import sys

import mlx_whisper


if len(sys.argv) != 3:
    raise SystemExit(
        "Uso: transcribe_reference.py AUDIO OUTPUT"
    )

audio = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()

print()
print("WHISPER TRANSCRIPTION")
print("─────────────────────")
print(f"Audio: {audio.name}")
print("Modello: Whisper Large v3 Turbo")
print()

result = mlx_whisper.transcribe(
    str(audio),
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
    language="it",
    task="transcribe",
    word_timestamps=True,
    verbose=False,
)

lines = []

for segment in result.get("segments", []):
    start = float(segment["start"])
    end = float(segment["end"])
    text = segment["text"].strip()

    if not text:
        continue

    lines.append(
        f"[{start:07.2f} → {end:07.2f}] {text}"
    )

output.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8",
)

plain = output.with_name(
    "reference_source_transcript_plain.txt"
)

plain.write_text(
    result.get("text", "").strip() + "\n",
    encoding="utf-8",
)

print("✓ Trascrizione completata")
print()
print(f"Timestamp: {output}")
print(f"Testo:     {plain}")
