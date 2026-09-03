# Narration

Il libro tradotto contiene indice, note, didascalie, numeri di pagina: cose che non
si leggono ad alta voce. Questi stadi ritagliano il corpo e ripuliscono i residui di
impaginazione, fino al testo che va in TTS.

## Sub-features

- `narrate` — taglia fra `narration.start_marker` e `end_marker` →
  `text/narration_it.txt` + `work/narration_report.json`
- `layout` — due passate sui residui di impaginazione:
  - `clean_layout.py` → `text/narration_layout_it.txt` + `work/layout_cleanup.json`,
    `work/layout_embedded_review.txt`
  - `finalize_layout.py` → `text/narration_ready_it.txt` + `work/layout_finalization.json`

## How to get to it

Prima servono i marcatori in `book.json`, presi dal testo tradotto:

    "narration": {
      "start_marker": "Prefazione di …",
      "end_marker": "RINGRAZIAMENTI"
    }

Senza marcatori `./audiobook prepare` si ferma allo step NARRATE, esce **3** e stampa
il frammento di config da aggiungere.

    ./audiobook narrate nome-libro
    ./audiobook layout nome-libro

`layout` viene dopo la revisione linguistica: `./audiobook finish` fa
resolve-qc → apply-fixes → layout in una volta.

Catena dei file, nell'ordine reale:

    book_it.txt
      → narration_it.txt          narrate
      → narration_final_it.txt    resolve-qc
      → narration_reviewed_it.txt apply-fixes
      → narration_layout_it.txt   layout, passata 1
      → narration_ready_it.txt    layout, passata 2   ← input della fase audio

## Driving it

    ./audiobook narrate nome-libro
    ./audiobook layout nome-libro
    ./audiobook finish nome-libro

Verificare a che punto è un libro:

    ./audiobook info nome-libro
    python3 -m json.tool books/<slug>/work/narration_report.json
    python3 -m json.tool books/<slug>/work/layout_finalization.json

## Where it lives

- `scripts/build_narration.py`
- `scripts/clean_layout.py`
- `scripts/finalize_layout.py`
- `audiobook` — `narrate_book`, `layout_book`, `has_narration_markers`
- `books/dressed-a-century-of-hollywood-costume-design-landis-deborah-nadoolman/text/`
  — un libro che ha attraversato tutta la catena

## Gotchas

- I marcatori sono match di testo sul **tradotto**: se il QC linguistico riscrive la
  frase-marcatore, il taglio non trova più l'ancora. Prenderli da `text/book_it.txt`,
  non dal PDF originale.
- `narrate` va **prima** di `language-qc`: il QC legge `narration_it.txt`, non
  `book_it.txt`. Rifare `narrate` dopo un QC invalida il QC, che verifica lo sha256
  del suo input.
- `clean_layout.py` legge `narration_reviewed_it.txt`: saltando `apply-fixes` lavora
  su un file vecchio o inesistente. `finish` esegue i tre stadi nell'ordine giusto.
- `finalize_layout.py` esce 1 quando trova casi che non sa risolvere: va letto
  `work/layout_finalization.json`, non solo l'exit code.
- Cinque file di testo con nomi simili nella stessa cartella. Un rerun parziale lascia
  file incoerenti fra loro senza che niente se ne accorga: `info` mostra quali
  esistono, non se sono coerenti.
