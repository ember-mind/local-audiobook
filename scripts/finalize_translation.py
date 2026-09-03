#!/usr/bin/env python3

import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: finalize_translation.py /path/to/book.json")

    config_path = Path(sys.argv[1]).resolve()
    book = config_path.parent

    text_path = book / "text" / "book_it.txt"
    qc_path = book / "qc.json"

    if not text_path.exists():
        raise SystemExit("book_it.txt non trovato.")

    if not qc_path.exists():
        print("✓ Nessun qc.json: niente da applicare")
        return

    qc = json.loads(qc_path.read_text(encoding="utf-8"))
    text = text_path.read_text(encoding="utf-8")

    changed = 0

    for item in qc.get("replacements", []):
        old = item["from"]
        new = item["to"]

        if old in text:
            count = text.count(old)
            text = text.replace(old, new)
            changed += count
            print(f"✓ Correzione applicata × {count}")
        elif new in text:
            print("○ Correzione già presente")
        else:
            print(f"⚠ Testo non trovato: {old[:70]}")

    for value in qc.get("remove", []):
        count = text.count(value)

        if count:
            text = text.replace(value, "")
            changed += count
            print(f"✓ Rimosso {value!r} × {count}")

    text_path.write_text(text, encoding="utf-8")

    print()
    print(f"✓ Finalize completato · {changed} modifica/he")


if __name__ == "__main__":
    main()
