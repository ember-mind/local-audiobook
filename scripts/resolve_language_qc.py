#!/usr/bin/env python3

"""Applica al testo di narrazione le correzioni SICURE del language QC.

Sicura significa: una persona ha già deciso, per questo libro, che quella
sostituzione esatta va bene. La whitelist sta in
work/language_qc_safe_fixes.json — dati, non codice: è specifica del libro
e non deve vivere in questo script. Tutto il resto finisce in revisione,
e le decisioni umane le applica apply_review_fixes.py.

    text/narration_it.txt  →  text/narration_final_it.txt

Senza whitelist nessuna correzione è automatica: il testo passa invariato
e tutti gli issue del QC finiscono in revisione. È il default per un libro
nuovo.

Formato di work/language_qc_safe_fixes.json:

    {
      "safe": {
        "nella affascinante": "nell'affascinante",
        "produzione prolifico": "produzione prolifica"
      }
    }

La chiave è il `from` dell'issue, il valore il `to` atteso: la correzione
parte solo se la proposta dell'LLM coincide esattamente col valore, e solo
se la stringa compare una volta sola nel testo.
"""

from pathlib import Path
import hashlib
import json
import sys


def load_safe(path):
    """La whitelist del libro, o vuota se non c'è."""

    if not path.is_file():
        return {}

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    safe = data.get("safe") or {}

    if not isinstance(safe, dict):
        raise SystemExit(
            f"STOP: {path.name}: \"safe\" deve essere "
            "un oggetto from → to"
        )

    return {
        str(key): str(value)
        for key, value in safe.items()
    }


def sha256(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: resolve_language_qc.py /path/to/book.json"
        )

    config = Path(sys.argv[1]).resolve()
    book = config.parent

    source = book / "text" / "narration_it.txt"
    output = book / "text" / "narration_final_it.txt"

    qc_path = book / "work" / "language_qc.json"
    resolution_path = (
        book / "work" / "language_qc_resolution.json"
    )
    safe_path = book / "work" / "language_qc_safe_fixes.json"

    safe_fixes = load_safe(safe_path)

    if not source.is_file():
        raise SystemExit(
            f"Narrazione non trovata: {source}"
        )

    if not qc_path.is_file():
        raise SystemExit(
            f"Language QC non trovato: {qc_path}"
        )

    text = source.read_text(encoding="utf-8")
    qc = json.loads(
        qc_path.read_text(encoding="utf-8")
    )

    expected_hash = qc.get("source_sha256")

    if expected_hash and expected_hash != sha256(text):
        raise SystemExit(
            "STOP: language_qc.json appartiene a una "
            "versione diversa di narration_it.txt."
        )

    applied = []
    review = []

    for issue in qc.get("issues", []):
        old = str(issue.get("from") or "")
        proposed = str(issue.get("to") or "")

        safe_to = safe_fixes.get(old)

        # Anche se la stringa è nella whitelist,
        # la proposta deve coincidere esattamente.
        if safe_to is None or proposed != safe_to:
            review.append({
                **issue,
                "status": "review",
                "why": "non-whitelisted",
            })
            continue

        occurrences = text.count(old)

        # Mai fare replace automatici ambigui.
        if occurrences != 1:
            review.append({
                **issue,
                "status": "review",
                "why": (
                    f"safe-fix trovato "
                    f"{occurrences} volte"
                ),
            })
            continue

        text = text.replace(old, safe_to, 1)

        applied.append({
            **issue,
            "status": "applied",
        })

    output.write_text(
        text,
        encoding="utf-8",
    )

    result = {
        "source_sha256": sha256(
            source.read_text(encoding="utf-8")
        ),
        "output_sha256": sha256(text),
        "applied": applied,
        "review": review,
    }

    resolution_path.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    print()
    print("LANGUAGE QC RESOLUTION")
    print("──────────────────────")
    print(f"SAFE applicate: {len(applied)}")
    print(f"SAFE in whitelist: {len(safe_fixes)}")
    print(f"Da revisionare: {len(review)}")
    print()
    print("Output:")
    print(f"  {output}")
    print()
    print("Report:")
    print(f"  {resolution_path}")

    if review:
        print()
        print("REVIEW")
        print("──────")

        for i, issue in enumerate(review, 1):
            print(
                f"{i:2}. {issue.get('from', '')}"
            )
            print(
                f"    → {issue.get('to', '')}"
            )


if __name__ == "__main__":
    main()
