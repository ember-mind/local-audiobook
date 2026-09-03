#!/usr/bin/env python3

from pathlib import Path
import hashlib
import json
import sys


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def words(text):
    return len(text.split())


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: build_narration.py /path/to/book.json"
        )

    config_path = Path(sys.argv[1]).resolve()
    book = config_path.parent

    config = json.loads(
        config_path.read_text(encoding="utf-8")
    )

    settings = config.get("narration", {})

    start_marker = str(
        settings.get("start_marker") or ""
    ).strip()

    end_marker = str(
        settings.get("end_marker") or ""
    ).strip()

    if not start_marker or not end_marker:
        raise SystemExit(
            "Configurare narration.start_marker "
            "e narration.end_marker in book.json"
        )

    source = book / "text" / "book_it.txt"
    output = book / "text" / "narration_it.txt"

    if not source.is_file():
        raise SystemExit(
            f"Traduzione non trovata: {source}"
        )

    full_text = source.read_text(encoding="utf-8")
    lines = full_text.splitlines()

    start = next(
        (
            i for i, line in enumerate(lines)
            if line.strip().startswith(start_marker)
        ),
        None,
    )

    if start is None:
        raise SystemExit(
            f"Marker iniziale non trovato: {start_marker}"
        )

    end = next(
        (
            i for i in range(start + 1, len(lines))
            if lines[i].strip().startswith(end_marker)
        ),
        None,
    )

    if end is None:
        raise SystemExit(
            f"Marker finale non trovato: {end_marker}"
        )

    narration_lines = lines[start:end]

    while narration_lines and not narration_lines[0].strip():
        narration_lines.pop(0)

    while narration_lines and not narration_lines[-1].strip():
        narration_lines.pop()

    narration = "\n".join(narration_lines).strip() + "\n"

    output.write_text(
        narration,
        encoding="utf-8",
    )

    report = {
        "source": str(source),
        "output": str(output),
        "source_sha256": sha256(full_text),
        "narration_sha256": sha256(narration),
        "start_marker": start_marker,
        "end_marker": end_marker,
        "source_words": words(full_text),
        "narration_words": words(narration),
        "source_start_line": start + 1,
        "source_end_line": end,
    }

    report_path = book / "work" / "narration_report.json"

    report_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    kept = (
        report["narration_words"]
        / report["source_words"]
        * 100
    )

    print("✓ Testo di narrazione creato")
    print()
    print(
        f"Libro completo: {report['source_words']:,} parole"
    )
    print(
        f"Narrazione:     {report['narration_words']:,} parole"
    )
    print(
        f"Conservato:     {kept:.1f}%"
    )
    print()
    print("Da:")
    print(f"  {start_marker}")
    print("A:")
    print(f"  prima di {end_marker}")
    print()
    print(f"Output: {output}")


if __name__ == "__main__":
    main()
