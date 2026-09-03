#!/usr/bin/env python3

import json
import shutil
import sys
from pathlib import Path


def extract_pdf(source: Path) -> tuple[str, int, str]:
    # Prima scelta: PyMuPDF
    try:
        import fitz

        doc = fitz.open(source)
        pages = [page.get_text("text") for page in doc]
        return "\n\n".join(pages), len(pages), "PyMuPDF"
    except ImportError:
        pass

    # Fallback: pypdf
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(source))
        pages = [(page.extract_text() or "") for page in reader.pages]
        return "\n\n".join(pages), len(pages), "pypdf"
    except ImportError:
        raise RuntimeError(
            "Né PyMuPDF né pypdf sono installati nel virtualenv Pandrator."
        )


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: extract_book.py /path/to/book.json")

    config_path = Path(sys.argv[1]).resolve()

    if not config_path.is_file():
        raise SystemExit(f"Configurazione non trovata: {config_path}")

    book = config_path.parent
    config = json.loads(config_path.read_text())

    source = book / config["source"]["file"]

    if not source.is_file():
        raise SystemExit(f"Sorgente non trovata: {source}")

    text_dir = book / "text"
    text_dir.mkdir(exist_ok=True)

    raw_output = text_dir / "source_raw.txt"

    suffix = source.suffix.lower()

    if suffix == ".pdf":
        print(f"→ Estraggo PDF: {source.name}")

        try:
            text, pages, engine = extract_pdf(source)
        except RuntimeError as e:
            raise SystemExit(str(e))

        text = text.replace("\x00", "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.strip() + "\n"

        raw_output.write_text(text, encoding="utf-8")

        print(f"✓ Motore: {engine}")
        print(f"✓ Pagine: {pages}")

    elif suffix == ".txt":
        print(f"→ Copio testo: {source.name}")
        shutil.copyfile(source, raw_output)

    else:
        raise SystemExit(
            f"Formato non ancora supportato da extract: {suffix}"
        )

    words = len(raw_output.read_text(encoding="utf-8").split())
    size = raw_output.stat().st_size

    print(f"✓ Parole: {words:,}")
    print(f"✓ Dimensione: {size:,} bytes")
    print()
    print(f"Output: {raw_output}")


if __name__ == "__main__":
    main()
