#!/usr/bin/env python3

from pathlib import Path
import json
import re
import sys


MARKER = re.compile(
    r"(?:L['’])?OPPOSITO\s*:",
    re.IGNORECASE,
)

LINE_MARKER = re.compile(
    r"^\s*(?:L['’])?OPPOSITO\s*:",
    re.IGNORECASE,
)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: clean_layout.py /path/to/book.json"
        )

    config = Path(sys.argv[1]).resolve()
    book = config.parent

    source = (
        book
        / "text"
        / "narration_reviewed_it.txt"
    )

    output = (
        book
        / "text"
        / "narration_layout_it.txt"
    )

    json_report = (
        book
        / "work"
        / "layout_cleanup.json"
    )

    text_report = (
        book
        / "work"
        / "layout_embedded_review.txt"
    )

    if not source.is_file():
        raise SystemExit(
            f"File non trovato: {source}"
        )

    lines = source.read_text(
        encoding="utf-8"
    ).splitlines()

    kept = []
    removed = []

    for number, line in enumerate(lines, 1):
        if LINE_MARKER.search(line):
            removed.append({
                "line": number,
                "text": line.strip(),
            })
            continue

        kept.append(line)

    cleaned = "\n".join(kept).strip() + "\n"

    output.write_text(
        cleaned,
        encoding="utf-8",
    )

    # Trova i marker rimasti: sono quelli incastrati
    # dentro una frase/paragrafo.
    embedded = []

    for match in MARKER.finditer(cleaned):
        before = cleaned[:match.start()]

        line_number = before.count("\n") + 1

        start = max(0, match.start() - 350)
        end = min(
            len(cleaned),
            match.end() + 550,
        )

        context = cleaned[start:end].strip()

        embedded.append({
            "line": line_number,
            "marker": match.group(0),
            "context": context,
        })

    json_report.write_text(
        json.dumps(
            {
                "source": str(source),
                "output": str(output),
                "standalone_removed": removed,
                "embedded_remaining": embedded,
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    report = []

    report.append(
        "OPPOSITO — EMBEDDED LAYOUT REVIEW"
    )
    report.append("=" * 70)
    report.append("")

    for index, item in enumerate(
        embedded,
        1,
    ):
        report.append(
            f"CASE {index} — line {item['line']}"
        )
        report.append("-" * 70)
        report.append(
            item["context"].replace(
                item["marker"],
                f"⟦{item['marker']}⟧",
                1,
            )
        )
        report.append("")
        report.append("")

    text_report.write_text(
        "\n".join(report),
        encoding="utf-8",
    )

    print()
    print("LAYOUT CLEANUP")
    print("──────────────")
    print(
        f"✓ Didascalie standalone rimosse: "
        f"{len(removed)}"
    )
    print(
        f"◈ OPPOSITO ancora embedded: "
        f"{len(embedded)}"
    )
    print()
    print(f"Output: {output}")

    if embedded:
        print(f"Review: {text_report}")
    else:
        print("✓ Nessun marker OPPOSITO rimasto")


if __name__ == "__main__":
    main()
