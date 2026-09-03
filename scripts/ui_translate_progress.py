#!/usr/bin/env python3

import re
import sys


BAR_WIDTH = 26

current = 0
total = 0

times = []
last_words = None
progress_visible = False


def format_time(seconds):
    seconds = max(0, int(seconds))

    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60

    if minutes < 60:
        return f"{minutes}m"

    hours = minutes // 60
    minutes %= 60

    return f"{hours}h {minutes:02d}m"


def draw(done, total, chunk_seconds=None):
    global progress_visible

    if total <= 0:
        return

    done = max(0, min(done, total))

    ratio = done / total
    filled = round(ratio * BAR_WIDTH)

    bar = (
        "█" * filled
        + "░" * (BAR_WIDTH - filled)
    )

    pct = round(ratio * 100)

    details = [
        f"{pct:3d}%",
        f"{done}/{total}",
    ]

    if chunk_seconds is not None:
        details.append(f"{chunk_seconds:.1f}s")

    if len(times) >= 3 and done < total:
        average = sum(times) / len(times)
        eta = average * (total - done)
        details.append(f"ETA ~{format_time(eta)}")

    line = (
        f"      ◈ [{bar}] "
        + " · ".join(details)
    )

    if sys.stdout.isatty():
        sys.stdout.write("\r\x1b[2K" + line)
        sys.stdout.flush()
    else:
        print(line, flush=True)

    progress_visible = True


def finish_progress():
    global progress_visible

    if progress_visible and sys.stdout.isatty():
        sys.stdout.write("\n")
        sys.stdout.flush()

    progress_visible = False


for raw in sys.stdin:
    line = raw.rstrip("\n")

    # Header già mostrato dal wrapper.
    if re.match(r"^Translate · ", line):
        continue

    if re.match(r"^[─━]+$", line.strip()):
        continue

    if line.strip() == "Traduzione":
        continue

    # Nuovo chunk.
    match = re.search(
        r"→\s*(\d+)\s*/\s*(\d+)",
        line,
    )

    if match:
        current = int(match.group(1))
        total = int(match.group(2))

        # Prima che il chunk finisca, consideriamo
        # completati quelli precedenti.
        draw(max(0, current - 1), total)
        continue

    # Chunk completato.
    match = re.search(
        r"✓\s*([\d.,]+)\s+parole\s*·\s*([\d.]+)s",
        line,
    )

    if match and total:
        words_text = match.group(1)
        seconds = float(match.group(2))

        last_words = words_text
        times.append(seconds)

        # Evita che un run lunghissimo renda l'ETA
        # troppo dipendente dai primi chunk.
        if len(times) > 30:
            times = times[-30:]

        draw(current, total, seconds)
        continue

    # Se Pandrator/llama stampa altro mentre la barra è
    # visibile, chiudiamola prima per non sovrascrivere.
    if line.strip():
        finish_progress()

        cleaned = line.strip()

        # Compattiamo un po' le informazioni.
        cleaned = cleaned.replace(
            "google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0",
            "Gemma 4 12B · Q4",
        )

        print(f"      {cleaned}", flush=True)


finish_progress()

if total and current >= total:
    print("      ✓ Translation complete", flush=True)
