#!/usr/bin/env python3

from pathlib import Path
import hashlib
import json
import sys


SAFE = {
    "nella affascinante": "nell'affascinante",
    "quanto le aneddoti": "quanto gli aneddoti",
    "nel esaltare": "nell'esaltare",
    "insista nel uscire": "insista nell'uscire",
    "della audace": "dell'audace",
    "a grande spese": "a grandi spese",
    "far aspettare il autista": "far aspettare l'autista",
    "il suo andatura": "la sua andatura",
    "produzione prolifico": "produzione prolifica",
    "quell'fascino": "quel fascino",
    "mentre io parlavano": "mentre io parlavo",
    "pochi perline": "poche perline",

    "| chiesi quanti abiti |": "chiesi quanti abiti",
    "| pensavo che i miei fianchi fossero troppo grandi":
        "pensavo che i miei fianchi fossero troppo grandi",
    "| Avrei dovuto indossare quel maledetto pareo":
        "Avrei dovuto indossare quel maledetto pareo",
    "Vestivamo ogni ragazza | con lo stesso pareo":
        "Vestivamo ogni ragazza con lo stesso pareo",

    "così come i rubriche": "così come le rubriche",
    "Daii Montgomery Clift": "Dai Montgomery Clift",
    "| ho vestito": "Ho vestito",
    "nel indossare": "nell'indossare",

    "Yul si rasò la testa rasata":
        "Yul si rasò la testa",

    "contro il intrattenimento":
        "contro l'intrattenimento",
    "la sua portamento":
        "il suo portamento",
    "dal entusiasmo":
        "dall'entusiasmo",
    "il scenografo":
        "lo scenografo",
    "gli scimmie":
        "le scimmie",
    "una tartufo":
        "un tartufo",
    "lo ho tinto":
        "l'ho tinto",
    "la autorità":
        "l'autorità",
    "film diepoca":
        "film d'epoca",
    "il adolescente maschio":
        "l'adolescente maschio",
    "fecci":
        "feci",
    "unaaspirante":
        "un'aspirante",
    "i caratteristici bretelle":
        "le caratteristiche bretelle",
    "in uno stato di assoluto disperazione":
        "in uno stato di assoluta disperazione",
    "delXVIII":
        "del XVIII",
    "un comparsa":
        "una comparsa",
    "Raggiungere i incassi":
        "Raggiungere gli incassi",
    "I enormi progressi":
        "Gli enormi progressi",
    "pura oro":
        "puro oro",
    "per il incarnato":
        "per l'incarnato",
    "de *The Hours*":
        "di *The Hours*",
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

        safe_to = SAFE.get(old)

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
