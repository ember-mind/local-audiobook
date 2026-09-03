#!/usr/bin/env python3

from pathlib import Path
import re
import subprocess
import sys


LINE = re.compile(
    r"^\[(\d+(?:\.\d+)?)\s*→\s*(\d+(?:\.\d+)?)\]\s*(.+)$"
)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: build_reference.py <reference-bank-dir>")

    root = Path(sys.argv[1]).resolve()

    audio = root / "reference_source_3min.wav"
    transcript = root / "reference_source_transcript.txt"

    out_audio = root / "reference_it_v2.wav"
    out_text = root / "reference_it_v2.txt"

    if not audio.exists():
        raise SystemExit(f"Audio mancante: {audio}")

    if not transcript.exists():
        raise SystemExit(f"Trascrizione mancante: {transcript}")

    segments = []

    for raw in transcript.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()

        if not raw:
            continue

        m = LINE.match(raw)

        if not m:
            raise SystemExit(
                "Riga non riconosciuta:\n"
                + raw
                + "\n\nMantieni il formato [inizio → fine] testo."
            )

        segments.append(
            {
                "start": float(m.group(1)),
                "end": float(m.group(2)),
                "text": m.group(3).strip(),
            }
        )

    if not segments:
        raise SystemExit("Nessun segmento trovato.")

    total_start = segments[0]["start"]
    total_end = segments[-1]["end"]
    midpoint = (total_start + total_end) / 2

    TARGET = 38.0
    MINIMUM = 32.0
    MAXIMUM = 45.0

    candidates = []

    for i in range(len(segments)):
        for j in range(i, len(segments)):
            start = segments[i]["start"]
            end = segments[j]["end"]
            duration = end - start

            if duration > MAXIMUM:
                break

            if duration >= MINIMUM:
                center = (start + end) / 2

                score = (
                    abs(duration - TARGET)
                    + 0.15 * abs(center - midpoint)
                )

                candidates.append((score, i, j))

    if not candidates:
        raise SystemExit(
            "Non trovo una finestra fra 32 e 45 secondi."
        )

    _, i, j = min(candidates)

    selected = segments[i:j + 1]

    start = selected[0]["start"]
    end = selected[-1]["end"]
    duration = end - start

    text = " ".join(
        seg["text"] for seg in selected
    ).strip()

    out_text.write_text(
        text + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss", f"{start:.3f}",
            "-i", str(audio),
            "-t", f"{duration:.3f}",
            "-ac", "1",
            "-ar", "24000",
            "-c:a", "pcm_s16le",
            str(out_audio),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print()
    print("REFERENCE V2")
    print("────────────")
    print(f"✓ Start:   {start:.2f}s")
    print(f"✓ End:     {end:.2f}s")
    print(f"✓ Durata:  {duration:.2f}s")
    print(f"✓ Caratteri testo: {len(text):,}")
    print()
    print("Audio:")
    print(out_audio)
    print()
    print("Trascrizione:")
    print(out_text)
    print()
    print("TESTO")
    print("─────")
    print(text)


if __name__ == "__main__":
    main()
