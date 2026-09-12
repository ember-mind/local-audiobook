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
  - `finalize_layout.py` → `text/narration_ready_it.txt` + `work/layout_finalization.json`,
    ricuciture da `work/layout_manual_fixes.json`

## How to get to it

Prima servono i marcatori in `book.json`, presi dal testo tradotto:

    "narration": {
      "start_marker": "Prefazione di …",
      "end_marker": "RINGRAZIAMENTI"
    }

`end_marker` è la **prima riga da non leggere**: il taglio è `lines[start:end]`, la
riga del marcatore finale resta fuori. È opzionale: se manca, è vuoto o vale `"EOF"`,
la narrazione arriva a fine file — il caso dei libri in cui `clean` ha già tagliato
tutto quello che segue il corpo (es. `think`).

Senza `start_marker` `./audiobook prepare` si ferma allo step NARRATE, esce **3** e
stampa il frammento di config da aggiungere.

    ./audiobook narrate nome-libro
    ./audiobook layout nome-libro

Le frasi spezzate da una didascalia o da un page break non si riconoscono in modo
generico: si indicano una per una in `books/<slug>/work/layout_manual_fixes.json`,
dati del libro come le correzioni del QC:

    {
      "cases": [
        {"id": 1, "note": "Rags caption",
         "start_anchor": "<testo prima del buco>",
         "end_anchor": "<testo dopo il buco>",
         "replacement": "<la frase ricucita>"}
      ],
      "forbidden": ["hasorta"]
    }

Lo splice sostituisce tutto ciò che sta fra i due anchor (inclusi): è così che la
didascalia in mezzo alla frase se ne va insieme al buco. Senza il file lo stadio fa
solo la pulizia degli spazi.

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
- `scripts/finalize_layout.py` — motore; le ricuciture stanno nei dati del libro
- `books/dressed-.../work/layout_manual_fixes.json` — esempio con 7 ricuciture
- `audiobook` — `narrate_book`, `layout_book`, `has_narration_markers`
- `books/dressed-a-century-of-hollywood-costume-design-landis-deborah-nadoolman/text/`
  — un libro che ha attraversato tutta la catena

## Gotchas

- `narration_report.json` registra `"end_marker": "EOF"` quando il taglio va a fine
  file, così dal report si vede che la fine non era ancorata a una riga.
- I marcatori sono match di testo sul **tradotto**: se il QC linguistico riscrive la
  frase-marcatore, il taglio non trova più l'ancora. Prenderli da `text/book_it.txt`,
  non dal PDF originale.
- `narrate` va **prima** di `language-qc`: il QC legge `narration_it.txt`, non
  `book_it.txt`. Rifare `narrate` dopo un QC invalida il QC, che verifica lo sha256
  del suo input.
- `clean_layout.py` legge `narration_reviewed_it.txt`: saltando `apply-fixes` lavora
  su un file vecchio o inesistente. `finish` esegue i tre stadi nell'ordine giusto.
- Lo `start_anchor` deve comparire **una volta sola** in tutto il libro, altrimenti
  lo stadio si ferma: un anchor ambiguo ricucirebbe il punto sbagliato. L'`end_anchor`
  si cerca solo dopo lo start e può comparire anche altrove.
- `forbidden` del libro si somma ai marcatori generici della pipeline (`OPPOSITO`,
  `OPPOSIZIONE`, `[Nota:`), che restano nello script.
- `finalize_layout.py` esce 1 quando trova casi che non sa risolvere: va letto
  `work/layout_finalization.json`, non solo l'exit code.
- Cinque file di testo con nomi simili nella stessa cartella. Un rerun parziale lascia
  file incoerenti fra loro senza che niente se ne accorga: `info` mostra quali
  esistono, non se sono coerenti.
