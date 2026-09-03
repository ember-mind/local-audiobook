#!/usr/bin/env python3

from pathlib import Path
import json
import sys
import time
import wave

import requests


ROOT = Path(__file__).resolve().parent.parent
QWEN = "http://127.0.0.1:8042"


def wait_ready():
    print("→ Attendo Qwen3-TTS")

    for _ in range(600):
        try:
            r = requests.get(
                QWEN + "/readyz",
                timeout=2,
            )

            if r.ok:
                print("✓ Qwen3-TTS pronto")
                return
        except requests.RequestException:
            pass

        time.sleep(1)

    raise RuntimeError(
        "Qwen3-TTS non è diventato pronto."
    )


def choose_sample(text):
    paragraphs = [
        p.strip()
        for p in text.split("\n\n")
        if p.strip()
    ]

    # Salta titoli/didascalie molto corte e prende
    # il primo vero paragrafo narrativo.
    for paragraph in paragraphs:
        if len(paragraph) >= 500:
            if len(paragraph) > 900:
                cut = paragraph.rfind(
                    ". ",
                    500,
                    900,
                )

                if cut > 0:
                    return paragraph[:cut + 1]

                return paragraph[:800]

            return paragraph

    raise RuntimeError(
        "Nessun paragrafo adatto trovato."
    )


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: qwen_sample.py <slug>"
        )

    slug = sys.argv[1]

    source = (
        ROOT
        / "books"
        / slug
        / "text"
        / "narration_ready_it.txt"
    )

    output = (
        ROOT
        / "books"
        / slug
        / "work"
        / "qwen_sample.wav"
    )

    sample_txt = (
        ROOT
        / "books"
        / slug
        / "work"
        / "qwen_sample.txt"
    )

    if not source.is_file():
        raise SystemExit(
            f"File non trovato: {source}"
        )

    text = source.read_text(
        encoding="utf-8"
    )

    sample = choose_sample(text)

    sample_txt.write_text(
        sample + "\n",
        encoding="utf-8",
    )

    print()
    print("QWEN SAMPLE")
    print("───────────")
    print(f"Caratteri: {len(sample):,}")
    print()
    print(sample[:300] + "...")
    print()

    wait_ready()

    print("→ Generazione audio")

    started = time.time()

    response = requests.post(
        QWEN + "/v1/audio/speech",
        json={
            "model": "qwen3-tts",
            "input": sample,
            "voice": "italiano",
            "speed": 1.0,
            "response_format": "wav",
            "language": "it",
        },
        timeout=1800,
    )

    if not response.ok:
        raise RuntimeError(
            f"Qwen → HTTP {response.status_code}\n"
            + response.text[:2000]
        )

    output.write_bytes(response.content)

    elapsed = time.time() - started

    with wave.open(str(output), "rb") as wav:
        duration = (
            wav.getnframes()
            / wav.getframerate()
        )

    print()
    print("✓ Sample generato")
    print(f"Durata audio: {duration:.1f}s")
    print(f"Tempo generazione: {elapsed:.1f}s")
    print()
    print(f"Audio: {output}")
    print(f"Testo: {sample_txt}")


if __name__ == "__main__":
    main()
