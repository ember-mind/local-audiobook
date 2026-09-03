#!/usr/bin/env python3

from pathlib import Path
import json
import re
import sys
import unicodedata


def find_suspicious_chars(text):
    found = []

    for i, char in enumerate(text):
        cp = ord(char)

        suspicious = (
            0x4E00 <= cp <= 0x9FFF      # CJK
            or 0x3400 <= cp <= 0x4DBF
            or 0x3040 <= cp <= 0x30FF  # Japanese
            or 0xAC00 <= cp <= 0xD7AF  # Korean
            or char == "\ufffd"         # replacement character
        )

        if suspicious:
            line = text.count("\n", 0, i) + 1

            found.append({
                "line": line,
                "char": char,
                "code": f"U+{cp:04X}",
                "name": unicodedata.name(char, "UNKNOWN"),
            })

    return found


def find_controls(text):
    results = []

    for i, char in enumerate(text):
        if char in "\n\t":
            continue

        category = unicodedata.category(char)

        if category == "Cc":
            line = text.count("\n", 0, i) + 1
            results.append((line, repr(char), ord(char)))

    return results


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: validate_translation.py /path/to/book.json"
        )

    config_path = Path(sys.argv[1]).resolve()
    book = config_path.parent

    source_path = book / "text" / "source_en.txt"
    italian_path = book / "text" / "book_it.txt"
    report_path = book / "work" / "validation_report.txt"

    if not italian_path.is_file():
        raise SystemExit("book_it.txt non trovato.")

    italian = italian_path.read_text(
        encoding="utf-8",
        errors="strict",
    )

    source = (
        source_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        if source_path.exists()
        else ""
    )

    fatal = []
    warnings = []

    suspicious = find_suspicious_chars(italian)

    if suspicious:
        fatal.append(
            f"{len(suspicious)} carattere/i Unicode sospetto/i"
        )

    controls = find_controls(italian)

    if controls:
        fatal.append(
            f"{len(controls)} carattere/i di controllo"
        )

    if "```" in italian:
        warnings.append(
            "Sono presenti code fence Markdown (```)"
        )

    meta_patterns = [
        r"(?im)^\s*here is (?:the )?translation",
        r"(?im)^\s*translation:\s*$",
        r"(?im)^\s*traduzione:\s*$",
        r"(?im)^\s*sure[,!].*translation",
    ]

    meta_hits = []

    for pattern in meta_patterns:
        meta_hits.extend(
            match.group(0)
            for match in re.finditer(pattern, italian)
        )

    if meta_hits:
        warnings.append(
            f"{len(meta_hits)} possibile/i frase/i meta del modello"
        )

    en_words = len(source.split())
    it_words = len(italian.split())

    ratio = (
        it_words / en_words
        if en_words
        else 0
    )

    if en_words and not 0.70 <= ratio <= 1.50:
        warnings.append(
            f"Rapporto parole IT/EN insolito: {ratio:.2f}"
        )

    en_chapters = source.count("[[Chapter]]")
    it_chapters = italian.count("[[Chapter]]")

    if en_chapters != it_chapters:
        warnings.append(
            "Numero marker [[Chapter]] diverso: "
            f"EN={en_chapters}, IT={it_chapters}"
        )

    if not italian.strip():
        fatal.append("Il file italiano è vuoto")

    report = [
        "LOCAL AUDIOBOOK — TRANSLATION VALIDATION",
        "=" * 42,
        "",
        f"Source:      {source_path}",
        f"Translation: {italian_path}",
        "",
        f"EN words: {en_words:,}",
        f"IT words: {it_words:,}",
        f"IT/EN:    {ratio:.3f}" if en_words else "IT/EN: n/a",
        "",
        f"[[Chapter]] EN: {en_chapters}",
        f"[[Chapter]] IT: {it_chapters}",
        "",
    ]

    if suspicious:
        report += [
            "SUSPICIOUS UNICODE",
            "------------------",
        ]

        for item in suspicious:
            report.append(
                f"line {item['line']:>5}: "
                f"{item['char']} "
                f"{item['code']} "
                f"{item['name']}"
            )

        report.append("")

    if controls:
        report += [
            "CONTROL CHARACTERS",
            "------------------",
        ]

        for line, char, code in controls:
            report.append(
                f"line {line}: {char} U+{code:04X}"
            )

        report.append("")

    if meta_hits:
        report += [
            "POSSIBLE MODEL META TEXT",
            "------------------------",
        ]

        report.extend(meta_hits)
        report.append("")

    report += ["RESULT", "------"]

    if fatal:
        report.append("FAIL")

        for item in fatal:
            report.append(f"✗ {item}")
    else:
        report.append("PASS")

    for item in warnings:
        report.append(f"⚠ {item}")

    if not warnings and not fatal:
        report.append("✓ Nessun problema rilevato")

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )

    print()
    print(f"EN words:     {en_words:,}")
    print(f"IT words:     {it_words:,}")

    if en_words:
        print(f"IT/EN ratio:  {ratio:.3f}")

    print(
        f"Chapters:     EN {en_chapters} → IT {it_chapters}"
    )
    print()

    if fatal:
        for item in fatal:
            print(f"✗ {item}")

        print()
        print(f"Report: {report_path}")
        raise SystemExit(1)

    if warnings:
        for item in warnings:
            print(f"⚠ {item}")
    else:
        print("✓ Nessun problema rilevato")

    print()
    print("✓ Traduzione pronta per TTS")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
