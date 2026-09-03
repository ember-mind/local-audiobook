#!/usr/bin/env python3

import json
import re
import sys
from collections import Counter
from pathlib import Path


KNOWN_JUNK = {
    "oceanofpdf.com",
    "www.oceanofpdf.com",
}


def normalized_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def is_page_number(line: str) -> bool:
    s = line.strip()

    return bool(
        re.fullmatch(r"\d{1,4}", s)
        or re.fullmatch(r"[-–—]?\s*\d{1,4}\s*[-–—]?", s)
        or re.fullmatch(r"page\s+\d{1,4}", s, re.I)
    )


def find_repeated_marginals(lines: list[str]) -> set[str]:
    """
    Identifica header/footer ripetuti senza essere troppo aggressivo.
    Consideriamo solo righe corte ripetute almeno 5 volte.
    """

    candidates = []

    for line in lines:
        s = normalized_line(line)

        if not s:
            continue

        if len(s) > 100:
            continue

        if len(s.split()) > 14:
            continue

        candidates.append(s)

    counts = Counter(candidates)

    repeated = {
        text
        for text, count in counts.items()
        if count >= 5
    }

    return repeated


def join_wrapped_lines(lines: list[str]) -> list[str]:
    """
    Ricostruisce i paragrafi distrutti dall'estrazione PDF.

    Le righe vuote restano confini di paragrafo.
    """

    output = []
    paragraph = ""

    def flush():
        nonlocal paragraph

        if paragraph.strip():
            output.append(paragraph.strip())

        paragraph = ""

    for raw in lines:
        line = raw.strip()

        if not line:
            flush()

            if output and output[-1] != "":
                output.append("")

            continue

        if not paragraph:
            paragraph = line
            continue

        # Parola spezzata a fine riga:
        # "informa-\nzione" -> "informazione"
        if (
            paragraph.endswith("-")
            and line
            and line[0].islower()
            and paragraph[-2:-1].isalpha()
        ):
            paragraph = paragraph[:-1] + line
            continue

        # Altrimenti è normalmente una linea spezzata dal PDF.
        paragraph += " " + line

    flush()

    # Evita più righe vuote consecutive.
    cleaned = []
    previous_blank = False

    for line in output:
        blank = not line.strip()

        if blank and previous_blank:
            continue

        cleaned.append(line)
        previous_blank = blank

    return cleaned


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: clean_book.py /path/to/book.json")

    config_path = Path(sys.argv[1]).resolve()
    book = config_path.parent

    raw_path = book / "text" / "source_raw.txt"
    output_path = book / "text" / "source_en.txt"
    report_path = book / "work" / "cleaning_report.txt"

    if not raw_path.is_file():
        raise SystemExit(
            "source_raw.txt non trovato. Esegui prima audiobook extract."
        )

    original = raw_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    original = (
        original
        .replace("\x00", "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    lines = original.splitlines()

    repeated = find_repeated_marginals(lines)

    kept = []
    removed = Counter()

    for raw in lines:
        s = normalized_line(raw)
        lower = s.lower()

        if lower in KNOWN_JUNK:
            removed[f"junk: {s}"] += 1
            continue

        if is_page_number(s):
            removed[f"page-number: {s}"] += 1
            continue

        if s and s in repeated:
            removed[f"repeated: {s}"] += 1
            continue

        kept.append(raw)

    cleaned = join_wrapped_lines(kept)

    final = "\n".join(cleaned).strip() + "\n"

    output_path.write_text(final, encoding="utf-8")

    report = [
        "LOCAL AUDIOBOOK CLEANING REPORT",
        "",
        f"Input:  {raw_path}",
        f"Output: {output_path}",
        "",
        f"Raw characters:   {len(original):,}",
        f"Clean characters: {len(final):,}",
        f"Raw words:        {len(original.split()):,}",
        f"Clean words:      {len(final.split()):,}",
        "",
        "Removed lines:",
    ]

    if removed:
        for item, count in sorted(
            removed.items(),
            key=lambda x: (-x[1], x[0]),
        ):
            report.append(f"{count:5} × {item}")
    else:
        report.append("None")

    report_path.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )

    print("✓ Pulizia completata")
    print()
    print(f"Raw words:   {len(original.split()):,}")
    print(f"Clean words: {len(final.split()):,}")
    print()
    print(f"Output: {output_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
