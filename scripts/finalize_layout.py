#!/usr/bin/env python3

from pathlib import Path
import hashlib
import json
import re
import sys


def sha256(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


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

    if not source.is_file():
        raise SystemExit(
            f"File non trovato: {source}"
        )

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
        # Prendiamo la prima occorrenza DOPO lo start
        # specifico di questo caso.
        search_from = start + len(start_anchor)

        end = text.find(
            end_anchor,
            search_from,
        )

        if end < 0:
            raise SystemExit(
                f"STOP: CASE {case}: end anchor "
                "non trovato dopo lo start anchor"
            )

        end += len(end_anchor)

        text = (
            text[:start]
            + replacement
            + text[end:]
        )

        applied.append(case)


    # CASE 1 — Rags caption.
    splice(
        1,
        "Non essendoci ancora un sistema organizzato, "
        "la gestione dei costumi era inevitabilmente "
        "un insieme eterogeneo.",
        "—E.E. Barrett (sceneggiatore)",
        (
            "Non essendoci ancora un sistema organizzato, "
            "la gestione dei costumi era inevitabilmente "
            "un insieme eterogeneo."
        ),
    )


    # CASE 2 — Canary Murder Case caption.
    splice(
        2,
        "ma tutti osservano con attenzione il lavoratore "
        "della bottega che, a queste doti, aggiunge la "
        "capacità di esprimere le emozioni umane in "
        "termini di abiti».",
        "Travis Banton, costumista",
        (
            "ma tutti osservano con attenzione il lavoratore "
            "della bottega che, a queste doti, aggiunge la "
            "capacità di esprimere le emozioni umane in "
            "termini di abiti»."
        ),
    )


    # CASE 3 — frase sul razionamento spezzata.
    splice(
        3,
        "“Ciò limitò drasticamente le...",
        "“...la quantità di tessuto",
        "“Ciò limitò drasticamente la quantità di tessuto",
    )


    # CASE 4 — frase di Sharaff spezzata da Casablanca.
    splice(
        4,
        "«Una buona storia... prevale sulla star e sul",
        (
            "«...tutti gli altri elementi nella realizzazione "
            "di un film», disse Sharaff."
        ),
        (
            "«Una buona storia... prevale sulla star e su "
            "tutti gli altri elementi nella realizzazione "
            "di un film», disse Sharaff."
        ),
    )


    # CASE 5 — realismo dopoguerra / Wild One.
    splice(
        5,
        (
            "Il realismo degli anni del dopoguerra "
            "continuò a catturare..."
        ),
        "...il pubblico",
        (
            "Il realismo degli anni del dopoguerra "
            "continuò a catturare il pubblico"
        ),
    )


    # CASE 6 — Cleopatra / Gypsy.
    splice(
        6,
        (
            "La produzione epica di *Cleopatra*, "
            "uscita due anni dopo,"
        ),
        "fu un disastro finanziario",
        (
            "La produzione epica di *Cleopatra*, "
            "uscita due anni dopo, fu un disastro finanziario"
        ),
    )


    # CASE 7 — indie / American Beauty / Pulp Fiction.
    splice(
        7,
        (
            'Gli "indies" costituivano un\'industria '
            'che non si opponeva tanto a Hollywood...'
        ),
        "...come parallelo ad esso.",
        (
            'Gli "indies" costituivano un’industria '
            'non tanto in opposizione a Hollywood '
            'quanto parallela ad essa.'
        ),
    )


    # Pulizia minima dopo gli splice.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = text.strip() + "\n"


    forbidden = [
        "OPPOSITO",
        "OPPOSIZIONE",
        "[Nota:",
        "C SSGNATURE",
        "speseò",
        "seta di seta",
        "hasorta",
        "ever-proliferanti",
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
                "cases_resolved": applied,
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
    print(f"✓ Layout cases risolti: {len(applied)}/7")
    print(f"✓ OPPOSITO rimasti: {text.count('OPPOSITO')}")
    print(f"✓ Parole finali: {len(text.split()):,}")
    print()
    print("READY FOR TTS")
    print(f"  {output}")


if __name__ == "__main__":
    main()
