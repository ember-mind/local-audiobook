#!/usr/bin/env python3

from pathlib import Path
import subprocess
import sys
import time

import requests
from pydub import AudioSegment

from pandrator.logic.text_preprocessor import preprocess_text


ROOT = Path(__file__).resolve().parent.parent
QWEN = "http://127.0.0.1:8042"


def wait_ready():
    for _ in range(600):
        try:
            r = requests.get(QWEN + "/readyz", timeout=2)
            if r.ok:
                return
        except requests.RequestException:
            pass
        time.sleep(1)

    raise RuntimeError("Qwen3-TTS non pronto")


def sample_source(path):
    text = path.read_text(encoding="utf-8")

    # Salta il titolo iniziale.
    paragraphs = [
        p.strip()
        for p in text.split("\n\n")
        if p.strip()
    ]

    body = " ".join(paragraphs[1:])

    # Circa 1400 caratteri, ma termina a fine frase.
    target = 1400

    end = max(
        body.rfind(". ", 1000, target + 300),
        body.rfind("? ", 1000, target + 300),
        body.rfind("! ", 1000, target + 300),
    )

    if end < 0:
        end = target
    else:
        end += 1

    return body[:end].strip()


def generate(text, target):
    r = requests.post(
        QWEN + "/v1/audio/speech",
        json={
            "model": "qwen3-tts",
            "input": text,
            "voice": "italiano",
            "speed": 1.0,
            "response_format": "wav",
            "language": "it",
        },
        timeout=1800,
    )

    if not r.ok:
        raise RuntimeError(
            f"Qwen HTTP {r.status_code}\n{r.text[:1000]}"
        )

    target.write_bytes(r.content)


def make_version(source_text, source_path, limit, work):
    segments = preprocess_text(
        source_text,
        {
            "source_file": str(source_path),
            "language": "it",
            "tts_service": "XTTS",
            "max_sentence_length": limit,
            "enable_sentence_splitting": True,
            "enable_sentence_appending": True,
            "enable_nemo_normalization": False,
            "remove_diacritics": False,
            "remove_quotation_marks": False,
            "normalize_all_caps": False,
        },
    )

    print()
    print(f"VERSIONE {limit}")
    print("────────────")
    print(f"Segmenti: {len(segments)}")

    combined = AudioSegment.empty()

    segment_dir = work / f"segments_{limit}"
    segment_dir.mkdir(parents=True, exist_ok=True)

    for i, record in enumerate(segments, 1):
        text = (
            record.get("text")
            or record.get("original_sentence")
            or ""
        ).strip()

        if not text:
            continue

        print(
            f"→ {i}/{len(segments)} "
            f"[{len(text)} chars]"
        )

        wav = segment_dir / f"{i:03d}.wav"

        generate(text, wav)

        audio = AudioSegment.from_wav(wav)
        combined += audio

        if i < len(segments):
            if record.get("paragraph") == "yes":
                pause = 700
            elif record.get("sentence_continues_after"):
                pause = 80
            else:
                pause = 250

            combined += AudioSegment.silent(
                duration=pause,
                frame_rate=24000,
            )

    raw = work / f"chunking_{limit}_raw.wav"
    normalized = work / f"chunking_{limit}.wav"

    combined.export(raw, format="wav")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(raw),
            "-af", "loudnorm=I=-18:LRA=11:TP=-2",
            str(normalized),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print(f"✓ {normalized}")

    return normalized


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: qwen_chunking_ab.py <slug>")

    slug = sys.argv[1]

    source = (
        ROOT / "books" / slug /
        "text" / "narration_ready_it.txt"
    )

    work = ROOT / "books" / slug / "work" / "chunking-ab"
    work.mkdir(parents=True, exist_ok=True)

    text = sample_source(source)

    (work / "sample_text.txt").write_text(
        text + "\n",
        encoding="utf-8",
    )

    print()
    print("CHUNKING A/B")
    print("────────────")
    print(f"Testo: {len(text)} caratteri")

    wait_ready()

    a = make_version(text, source, 160, work)
    b = make_version(text, source, 600, work)

    print()
    print("A/B COMPLETATO")
    print("──────────────")
    print(f"A · 160: {a}")
    print(f"B · 600: {b}")


if __name__ == "__main__":
    main()
