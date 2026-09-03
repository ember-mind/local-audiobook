# Proofread

QC linguistico del testo di narrazione con un LLM locale, poi applicazione delle
correzioni: prima quelle sicure, poi le decisioni umane.

## Sub-features

- `language-qc` — legge `text/narration_it.txt`, scrive `work/language_qc.json`
- `resolve-qc` — applica le correzioni sicure → `text/narration_final_it.txt`
- `apply-fixes` — applica le decisioni umane → `text/narration_reviewed_it.txt`

## How to get to it

    ./audiobook language-qc nome-libro

Se trova problemi da rivedere esce **2** e lascia il verdetto in
`books/<slug>/work/language_qc.json`. Le decisioni umane si scrivono in
`books/<slug>/work/language_qc_manual_fixes.json`, poi:

    ./audiobook resolve-qc nome-libro
    ./audiobook apply-fixes nome-libro

Oppure, per fare resolve-qc + apply-fixes + layout in una volta:

    ./audiobook finish nome-libro

Senza file di decisioni `apply-fixes` fa passare il testo invariato: un libro il cui
QC non ha richiesto interventi attraversa comunque lo stadio.

### Formato delle decisioni

`work/language_qc_manual_fixes.json` — dati per libro, non codice:

    {
      "operations": [
        {"issue": 1, "kind": "exact", "from": "Risa di cuore.",
         "to": "Risero di cuore.", "expected": 1, "note": "perché"},
        {"issue": "13+14", "kind": "regex", "pattern": "...",
         "replacement": "...", "expected": 1, "flags": ["ignorecase"]}
      ],
      "rejected": {"11": "frase grammaticalmente valida"},
      "forbidden": ["hasorta"],
      "structural_remaining": {"issues": [2, 9], "token": "OPPOSITO"}
    }

Il formato completo è documentato in testa a `scripts/apply_review_fixes.py`.

## Driving it

    ./audiobook language-qc nome-libro; echo "exit=$?"
    ./audiobook resolve-qc nome-libro
    ./audiobook apply-fixes nome-libro
    ./audiobook finish nome-libro

Leggere il verdetto e il resoconto:

    python3 -m json.tool books/<slug>/work/language_qc.json | head -60
    python3 -m json.tool books/<slug>/work/language_qc_manual_resolution.json | head -40

## Where it lives

- `scripts/language_qc.py` — chunking, chiamate LLM, retry, timeout, parsing JSON
- `scripts/resolve_language_qc.py`
- `scripts/apply_review_fixes.py` — motore generico; le correzioni stanno nei dati
- `audiobook` — `language_qc_book`, `resolve_qc_book`, `apply_fixes_book`, `finish_book`
- `books/dressed-a-century-of-hollywood-costume-design-landis-deborah-nadoolman/work/language_qc.json`
  — esempio di verdetto reale

## Gotchas

- Exit **2** significa "serve una revisione umana", non "errore". `prepare` lo
  interpreta e stampa REVIEW REQUIRED; qualsiasi altro chiamante deve fare lo stesso.
- **`apply-fixes` non scrive niente se una sostituzione non trova quello che si
  aspetta.** `expected` è la guardia contro l'applicazione di una patch a un testo
  diverso da quello per cui era scritta: mezza patch è peggio di nessuna patch.
  Ometterlo, o mettere `"optional": true`, disattiva la guardia per quella riga: da
  usare solo per le ricuciture opportunistiche (un page break che può non esserci).
- `forbidden` è il controllo opposto: token che dopo le correzioni **non** devono più
  esistere. Se ne resta uno, lo stadio non scrive.
- `resolve-qc` verifica che `language_qc.json` appartenga alla versione corrente di
  `narration_it.txt` (via sha256) e si ferma se non torna. Rifare `narrate` invalida
  un QC già fatto.
- Le run vecchie restano in `work/` con il timestamp nel nome
  (`language_qc-full-book-<data>.json`): nessuno le cancella, crescono per sempre.
- L'LLM risponde JSON; il parsing ha retry e autosplit dei chunk, segno che fallisce
  regolarmente su chunk lunghi. Un chunk che non torna JSON valido dopo i retry ferma
  lo stadio.
