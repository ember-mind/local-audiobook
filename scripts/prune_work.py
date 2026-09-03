#!/usr/bin/env python3

"""Cancella da books/<slug>/work/ quello che è sicuro ricostruire.

`work/` accumula: run di QC superate, audio di prova, output di esperimenti
chiusi. Nessuno li cancella e crescono per sempre — su un libro reale sono
arrivati a 122 MB su 170.

Cancellare dentro un progetto-libro è irreversibile: `books/` non è in git.
Per questo qui c'è una **allowlist** di cosa si può togliere, non una lista di
cosa risparmiare: una categoria nuova di file non diventa cancellabile per
sbaglio, e tutto ciò che non è elencato resta dov'è.

Di default mostra e basta. Cancella solo con --yes.

    prune_work.py /path/to/book.json [--yes] [--keep N]
"""

from pathlib import Path
import json
import shutil
import sys


# Ciò che NON è qui non viene mai toccato: il checkpoint di traduzione
# (work/translation/, ore di LLM), la cache del QC (work/language_qc/), lo
# stato della sessione Pandrator (work/pandrator/), i report e le decisioni.
CATEGORIES = {
    "runs": {
        "label": "Run di QC superate",
        "why": "Sostituite da work/language_qc.json.",
        "globs": [
            "language_qc-full-book-*",
        ],
        "keep_recent": True,
    },
    "samples": {
        "label": "Audio di prova",
        "why": "Rigenerabili con ./audiobook sample.",
        "globs": [
            "qwen_sample*.wav",
        ],
        "keep_recent": False,
    },
    "experiments": {
        "label": "Esperimenti di chunking",
        "why": "L'esito (600) è già in pandrator_prepare_audio.py.",
        "globs": [
            "chunking-ab",
        ],
        "keep_recent": False,
    },
}


def size_of(path):
    if path.is_file():
        return path.stat().st_size

    return sum(
        item.stat().st_size
        for item in path.rglob("*")
        if item.is_file()
    )


def human(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def collect(work, keep):
    """Cosa è cancellabile, per categoria, già ordinato dal più recente."""

    found = {}

    for name, category in CATEGORIES.items():
        matches = []

        for pattern in category["globs"]:
            matches.extend(work.glob(pattern))

        # Dedup: un glob può pescare sia la cartella sia il suo .json.
        matches = sorted(
            set(matches),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if category["keep_recent"] and keep > 0:
            # `keep` conta le run, e una run è una coppia dir + json con lo
            # stesso nome: tenerne N significa tenere N nomi distinti.
            kept_stems = []

            for item in matches:
                stem = item.name.removesuffix(".json")

                if stem not in kept_stems and len(kept_stems) < keep:
                    kept_stems.append(stem)

            matches = [
                item
                for item in matches
                if item.name.removesuffix(".json") not in kept_stems
            ]

        if matches:
            found[name] = matches

    return found


def main():
    argv = sys.argv[1:]

    if not argv:
        raise SystemExit(
            "Uso: prune_work.py /path/to/book.json [--yes] [--keep N]"
        )

    confirmed = "--yes" in argv
    argv = [item for item in argv if item != "--yes"]

    keep = 2

    if "--keep" in argv:
        index = argv.index("--keep")

        try:
            keep = int(argv[index + 1])
        except (IndexError, ValueError):
            raise SystemExit("--keep vuole un numero") from None

        if keep < 0:
            raise SystemExit("--keep non può essere negativo")

        del argv[index : index + 2]

    if len(argv) != 1:
        raise SystemExit(
            "Uso: prune_work.py /path/to/book.json [--yes] [--keep N]"
        )

    config = Path(argv[0]).resolve()

    if not config.is_file():
        raise SystemExit(f"book.json non trovato: {config}")

    book = config.parent
    work = book / "work"

    if not work.is_dir():
        raise SystemExit(f"Cartella work/ non trovata: {work}")

    found = collect(work, keep)

    print()
    print(f"work/ occupa {human(size_of(work))}")
    print()

    if not found:
        print("✓ Niente da cancellare.")
        print()
        return

    total = 0

    for name, matches in found.items():
        category = CATEGORIES[name]
        subtotal = sum(size_of(item) for item in matches)
        total += subtotal

        print(f"{category['label']} · {human(subtotal)}")
        print(f"  {category['why']}")

        for item in matches:
            marker = "/" if item.is_dir() else ""
            print(f"    {item.name}{marker}  ({human(size_of(item))})")

        print()

    if not confirmed:
        print(f"Recuperabili: {human(total)}")
        print()
        print("Niente è stato cancellato. Per farlo davvero:")
        print(f"  ./audiobook prune {book.name} --yes")
        print()
        return

    removed = 0

    for matches in found.values():
        for item in matches:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

            removed += 1

    print(f"✓ Cancellati {removed} elementi · {human(total)} liberati")
    print(f"  work/ ora occupa {human(size_of(work))}")
    print()


if __name__ == "__main__":
    main()
