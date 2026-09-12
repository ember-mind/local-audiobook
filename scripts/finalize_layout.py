#!/usr/bin/env python3

"""Seconda passata sui residui di impaginazione: le ricuciture del libro.

Le frasi spezzate da una didascalia o da un page break non si possono
riconoscere in modo generico: vanno indicate una per una. Stanno in
work/layout_manual_fixes.json — dati, non codice: sono specifiche del
libro e non devono vivere in questo script.

    text/narration_layout_it.txt  →  text/narration_ready_it.txt

Senza file di ricuciture lo stadio fa solo la pulizia degli spazi: un
libro le cui frasi non sono spezzate attraversa comunque lo stadio.

Formato di work/layout_manual_fixes.json:

    {
      "cases": [
        {
          "id": 1,
          "note": "Rags caption",
          "start_anchor": "<testo prima del buco>",
          "end_anchor": "<testo dopo il buco>",
          "replacement": "<la frase ricucita>"
        }
      ],
      "forbidden": ["hasorta"]
    }

Lo splice sostituisce tutto ciò che sta fra start_anchor e end_anchor
(inclusi) con `replacement`: è così che la didascalia in mezzo alla
frase spezzata se ne va insieme al buco. Lo start_anchor deve comparire
UNA volta sola in tutto il libro, altrimenti lo stadio si ferma: un
anchor ambiguo ricucirebbe il punto sbagliato. L'end_anchor invece si
cerca solo dopo lo start, e può comparire anche altrove.

`forbidden` sono i token che al termine della pulizia NON devono più
esistere: se ne resta uno lo stadio non scrive. Ai marcatori generici
della pipeline (FORBIDDEN_ALWAYS) si aggiungono quelli del libro.
"""

from pathlib import Path
import hashlib
import json
import re
import sys


# Marcatori della pipeline, non del libro: clean_layout.py li lascia
# dietro quando una review di impaginazione è rimasta aperta.
FORBIDDEN_ALWAYS = [
    "OPPOSITO",
    "OPPOSIZIONE",
    "[Nota:",
]


def sha256(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def load_fixes(path):
    """Le ricuciture del libro, o il vuoto se non ce ne sono."""

    if not path.is_file():
        return [], []

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    cases = data.get("cases") or []
    forbidden = data.get("forbidden") or []

    for position, case in enumerate(cases, 1):
        for field in ("start_anchor", "end_anchor", "replacement"):
            if not str(case.get(field) or "").strip():
                raise SystemExit(
                    f"STOP: {path.name}, case #{position}: "
                    f"manca {field}"
                )

    return cases, forbidden


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: finalize_layout.py /path/to/book.json"
        )

    config = Path(sys.argv[1]).resolve()
    book = config.parent

    source = book / "text" / "narration_layout_it.txt"
    output = book / "text" / "narration_ready_it.txt"
    report = book / "work" / "layout_finalization.json"
    fixes_path = book / "work" / "layout_manual_fixes.json"

    if not source.is_file():
        raise SystemExit(
            f"File non trovato: {source}"
        )

    cases, book_forbidden = load_fixes(fixes_path)

    text = source.read_text(encoding="utf-8")
    original = text
    applied = []


    def splice(case, start_anchor, end_anchor, replacement):
        nonlocal text

        start_count = text.count(start_anchor)

        if start_count != 1:
            raise SystemExit(
                f"STOP: CASE {case}: start anchor "
                f"trovato {start_count} volte"
            )

        start = text.index(start_anchor)

        # L'end anchor può comparire altrove nel libro.
        # Quello che conta è il primo dopo lo start.
        search_from = start + len(start_anchor)

        end = text.find(
            end_anchor,
            search_from,
        )

        if end == -1:
            raise SystemExit(
                f"STOP: CASE {case}: end anchor "
                "non trovato dopo lo start anchor"
            )

        end += len(end_anchor)

        text = text[:start] + replacement + text[end:]

        applied.append(case)


    for case in cases:
        splice(
            case.get("id", "?"),
            case["start_anchor"],
            case["end_anchor"],
            case["replacement"],
        )


    # Pulizia minima dopo gli splice.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = text.strip() + "\n"


    forbidden = FORBIDDEN_ALWAYS + [
        token for token in book_forbidden
        if token not in FORBIDDEN_ALWAYS
    ]

    remaining = {
        token: text.count(token)
        for token in forbidden
        if token in text
    }

    if remaining:
        print()
        print("✕ TESTO NON PRONTO")

        for token, count in remaining.items():
            print(f"  {token!r}: {count}")

        raise SystemExit(1)


    output.write_text(
        text,
        encoding="utf-8",
    )

    report.write_text(
        json.dumps(
            {
                "source": str(source),
                "output": str(output),
                "input_sha256": sha256(original),
                "output_sha256": sha256(text),
                "fixes": str(fixes_path) if cases else None,
                "cases_resolved": applied,
                "cases_expected": len(cases),
                "words": len(text.split()),
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    print()
    print("NARRATION FINALIZATION")
    print("──────────────────────")
    print(
        f"✓ Layout cases risolti: "
        f"{len(applied)}/{len(cases)}"
    )
    print(f"✓ OPPOSITO rimasti: {text.count('OPPOSITO')}")
    print(f"✓ Parole finali: {len(text.split()):,}")
    print()
    print("READY FOR TTS")
    print(f"  {output}")


if __name__ == "__main__":
    main()
