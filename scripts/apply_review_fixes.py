#!/usr/bin/env python3

"""Applica al testo di narrazione le decisioni umane sul language QC.

Le correzioni automatiche le fa resolve_language_qc.py. Qui entrano solo
quelle che una persona ha deciso leggendo work/language_qc.json, descritte
in work/language_qc_manual_fixes.json — dati, non codice: sono specifiche
del libro e non devono vivere in questo script.

    text/narration_final_it.txt  →  text/narration_reviewed_it.txt

Nessuna issue del QC puo' restare senza risposta: o la stringa contestata
non e' piu' nel testo, o compare in "rejected" con un motivo. Altrimenti lo
stadio non scrive ed esce 2, e il testo di narrazione resta quello di
resolve-qc. Senza issue aperte il testo passa invariato anche senza file di
decisioni.

Insieme all'output viene scritto work/language_qc_approval.json: il verdetto
a cui si riferisce, gli hash del testo prima e dopo, quante issue e quali
respinte. Cambiando il testo quell'approvazione non vale piu'.

Formato di work/language_qc_manual_fixes.json:

    {
      "operations": [
        {
          "issue": 1,
          "kind": "exact",
          "from": "Risa di cuore.",
          "to": "Risero di cuore.",
          "expected": 1,
          "note": "perché"
        },
        {
          "issue": "13+14",
          "kind": "regex",
          "pattern": "White\\\\s+consid-\\\\s*erava",
          "replacement": "White considerava",
          "expected": 1,
          "count": 1,
          "flags": ["ignorecase"]
        }
      ],
      "rejected": {"11": "frase grammaticalmente valida"},
      "structural_remaining": {"issues": [2, 9], "token": "OPPOSITO"},
      "forbidden": ["hasorta"],
      "collapse_whitespace": true
    }

`expected` è il numero di sostituzioni che l'operazione deve fare: se non
coincide, NIENTE viene scritto. È la guardia che impedisce di applicare a
un testo cambiato una patch pensata per un altro. Ometterlo (o metterlo a
null) significa "quante capitano": va usato solo per le ricuciture
opportunistiche, tipo un page break che può esserci o non esserci.
"""

from datetime import datetime
from pathlib import Path
import hashlib
import json
import re
import sys


FLAGS = {
    "ignorecase": re.IGNORECASE,
    "multiline": re.MULTILINE,
    "dotall": re.DOTALL,
}


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compile_flags(operation):
    flags = 0

    for name in operation.get("flags", []) or []:
        key = str(name).strip().lower()

        if key not in FLAGS:
            raise SystemExit(
                f"Issue {operation.get('issue')}: flag non riconosciuto "
                f"{name!r} (usare: {', '.join(sorted(FLAGS))})"
            )

        flags |= FLAGS[key]

    return flags


def apply_operation(text, operation, errors):
    """Ritorna il testo aggiornato e la descrizione di cosa è stato fatto."""

    issue = operation.get("issue", "?")
    kind = str(operation.get("kind") or "exact").lower()

    expected = operation.get("expected", 1)

    if operation.get("optional"):
        expected = None

    limit = int(operation.get("count") or 0)

    if kind == "exact":
        old = operation.get("from")
        new = operation.get("to")

        if old is None or new is None:
            raise SystemExit(
                f"Issue {issue}: un'operazione 'exact' richiede 'from' e 'to'"
            )

        found = text.count(old)

        if expected is not None and found != expected:
            errors.append(
                f"Issue {issue}: attese {expected} occorrenze, "
                f"trovate {found}: {old!r}"
            )
            return text, None

        if found == 0:
            return text, None

        text = text.replace(old, new, limit if limit else -1)
        applied = found if not limit else min(found, limit)

    elif kind == "regex":
        pattern = operation.get("pattern")
        replacement = operation.get("replacement")

        if pattern is None or replacement is None:
            raise SystemExit(
                f"Issue {issue}: un'operazione 'regex' richiede "
                "'pattern' e 'replacement'"
            )

        try:
            text, applied = re.subn(
                pattern,
                replacement,
                text,
                count=limit,
                flags=compile_flags(operation),
            )
        except re.error as error:
            raise SystemExit(
                f"Issue {issue}: regex non valida · {error}"
            ) from None

        if expected is not None and applied != expected:
            errors.append(
                f"Issue {issue}: attese {expected} sostituzioni, "
                f"fatte {applied}: {pattern!r}"
            )
            return text, None

        if applied == 0:
            return text, None

    else:
        raise SystemExit(
            f"Issue {issue}: kind non riconosciuto {kind!r} "
            "(usare 'exact' o 'regex')"
        )

    record = {
        "issue": issue,
        "kind": kind,
        "occurrences": applied,
    }

    if kind == "exact":
        record["from"] = operation["from"]
        record["to"] = operation["to"]
    else:
        record["pattern"] = operation["pattern"]
        record["replacement"] = operation["replacement"]

    if operation.get("note"):
        record["note"] = operation["note"]

    return text, record


def load_issues(book):
    """Il verdetto del QC, o lista vuota se non c'e'."""

    path = book / "work" / "language_qc.json"

    if not path.is_file():
        return [], None

    data = json.loads(path.read_text(encoding="utf-8"))

    return (
        data.get("issues") or [],
        sha256(path.read_text(encoding="utf-8")),
    )


def pending_issues(issues, text, rejected):
    """Issue di cui non risulta nessuna decisione.

    Una issue e' chiusa quando il testo non contiene piu' la stringa che il
    QC contestava — l'abbia sistemata una correzione sicura, una operazione
    manuale o un rifacimento della frase — oppure quando e' respinta con una
    motivazione. Tutto il resto e' lavoro che nessuno ha ancora guardato, e
    un file chiamato "reviewed" non deve poterlo nascondere.
    """

    keys = {str(key) for key in rejected}
    pending = []

    for number, issue in enumerate(issues, 1):
        old_text = str(issue.get("from") or "")

        if not old_text or old_text not in text:
            continue

        if str(number) in keys or old_text in keys:
            continue

        pending.append((number, issue))

    return pending


def report_pending(pending, decisions_path):
    print()
    print(f"◈ {len(pending)} issue senza decisione")
    print()

    for number, issue in pending[:20]:
        print(f"  {number:3d}. {issue.get('from', '')}")
        print(f"       → {issue.get('to', '')}")

        reason = str(issue.get("reason") or "").strip()

        if reason:
            print(f"       {reason[:100]}")

    if len(pending) > 20:
        print(f"  … e altre {len(pending) - 20}")

    print()
    print("Per ognuna serve una scelta, in")
    print(f"  {decisions_path}")
    print()
    print('  correggere → una voce in "operations"')
    print('  lasciare   → una voce in "rejected" con il motivo')
    print()
    print("Niente e' stato scritto: il testo di narrazione resta quello di")
    print("resolve-qc.")


def write_approval(book, issues, qc_hash, source_text, text, rejected, applied):
    """La prova che qualcuno ha deciso, legata a questo testo esatto."""

    path = book / "work" / "language_qc_approval.json"

    path.write_text(
        json.dumps(
            {
                "version": 1,
                "qc_sha256": qc_hash,
                "input_sha256": sha256(source_text),
                "output_sha256": sha256(text),
                "issues": len(issues),
                "operations": len(applied),
                "rejected": rejected,
                "approved_at": datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return path


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: apply_review_fixes.py /path/to/book.json"
        )

    config = Path(sys.argv[1]).resolve()
    book = config.parent

    source = book / "text" / "narration_final_it.txt"
    output = book / "text" / "narration_reviewed_it.txt"
    decisions_path = book / "work" / "language_qc_manual_fixes.json"
    report = book / "work" / "language_qc_manual_resolution.json"

    if not source.is_file():
        raise SystemExit(
            f"File non trovato: {source}\n"
            "Eseguire prima resolve-qc."
        )

    text = source.read_text(encoding="utf-8")
    original = text

    issues, qc_hash = load_issues(book)

    if not decisions_path.is_file():
        pending = pending_issues(issues, text, {})

        if pending:
            report_pending(pending, decisions_path)
            raise SystemExit(2)

        output.write_text(text, encoding="utf-8")
        approval = write_approval(book, issues, qc_hash, original, text, {}, [])

        print()
        print("○ Nessuna decisione manuale")
        print(f"  {decisions_path.name} assente, e nessuna issue aperta.")
        print(f"Output: {output}")
        print(f"Approvazione: {approval}")
        print()
        return

    decisions = json.loads(
        decisions_path.read_text(encoding="utf-8")
    )

    operations = decisions.get("operations", [])

    if not isinstance(operations, list):
        raise SystemExit(
            f"{decisions_path.name}: 'operations' deve essere una lista"
        )

    applied = []
    errors = []

    for operation in operations:
        if not isinstance(operation, dict):
            raise SystemExit(
                f"{decisions_path.name}: ogni operazione deve essere "
                "un oggetto"
            )

        text, record = apply_operation(text, operation, errors)

        if record is not None:
            applied.append(record)

    # Una sostituzione che non trova quello che si aspetta significa che il
    # testo non è quello per cui la patch è stata scritta: meglio non
    # scrivere niente che scrivere metà patch.
    if errors:
        print()
        print("✕ PATCH NON APPLICATA")
        print()

        for error in errors:
            print("  " + error)

        print()
        print("Il file originale non è stato modificato.")
        raise SystemExit(1)

    if decisions.get("collapse_whitespace", True):
        # Pulizia innocua dopo la rimozione di residui OCR.
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r" {2,}", " ", text)

    forbidden = [
        token
        for token in decisions.get("forbidden", []) or []
        if token in text
    ]

    if forbidden:
        print()
        print("✕ Token vietati ancora presenti:")

        for token in forbidden:
            print("  " + repr(token))

        print()
        print("Il file originale non è stato modificato.")
        raise SystemExit(1)

    structural = dict(decisions.get("structural_remaining", {}) or {})

    if structural.get("token"):
        structural["occurrences"] = text.count(structural["token"])

    rejected = decisions.get("rejected", {}) or {}

    pending = pending_issues(issues, text, rejected)

    if pending:
        report_pending(pending, decisions_path)
        raise SystemExit(2)

    output.write_text(text, encoding="utf-8")

    approval = write_approval(
        book, issues, qc_hash, original, text, rejected, applied
    )

    report.write_text(
        json.dumps(
            {
                "input": str(source),
                "output": str(output),
                "decisions": str(decisions_path),
                "input_sha256": sha256(original),
                "output_sha256": sha256(text),
                "applied_count": len(applied),
                "rejected_count": len(rejected),
                "applied_operations": applied,
                "rejected": rejected,
                "structural_remaining": structural,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(f"Operazioni applicate: {len(applied)}")
    print(f"Issue respinte:       {len(rejected)}")

    if structural.get("token"):
        print(
            f"Residui strutturali:  {structural['occurrences']} × "
            f"{structural['token']!r}"
        )

    print(f"Output: {output}")
    print(f"Report: {report}")
    print(f"Approvazione: {approval}")
    print()


if __name__ == "__main__":
    main()
