# Text pipeline

Da file sorgente a testo italiano validato e ritagliato. Sei stadi, ognuno con un
comando proprio, più `prepare` che li concatena con una UI a step.

## Sub-features

- `extract` — PDF/EPUB/TXT → `text/source_raw.txt`
- `clean` — de-hyphenation, header/footer, note → `text/source_en.txt` + `work/cleaning_report.txt`;
  con `source.body` in `book.json` taglia anche front matter e coda (Note, bibliografia)
- `translate` — chunk → LLM locale → `text/book_it.txt`, con checkpoint per riprendere
- `finalize` — pulizia finale di `book_it.txt`, poi validazione automatica
- `validate` — confronto EN/IT → `work/validation_report.txt`
- `narrate` — ritaglia il corpo → `text/narration_it.txt` (vedi [narration](narration.md))
- `prepare` — orchestratore: extract → clean → translate → QC → narrate → proofread

## How to get to it

Tutto d'un fiato:

    ./audiobook prepare nome-libro

Uno stadio alla volta:

    ./audiobook extract nome-libro
    ./audiobook clean nome-libro
    ./audiobook translate nome-libro
    ./audiobook finalize nome-libro
    ./audiobook validate nome-libro
    ./audiobook narrate nome-libro

`translate` riprende dal checkpoint. Per ricominciare da zero:

    ./audiobook translate nome-libro --reset

## Driving it

    ./audiobook prepare nome-libro; echo "exit=$?"

    ./audiobook extract nome-libro
    ./audiobook clean nome-libro
    ./audiobook translate nome-libro --reset
    ./audiobook finalize nome-libro
    ./audiobook validate nome-libro
    ./audiobook narrate nome-libro

A che punto è il libro, senza rilanciare niente:

    ./audiobook info nome-libro
    cat books/<slug>/work/translation/checkpoint.json
    ls books/<slug>/work/translation/translated | wc -l

Chiamare uno script direttamente (serve il python di Pandrator, non `python3`):

    ~/src/Pandrator/.venv/bin/python scripts/translate_book.py books/<slug>/book.json

## Where it lives

- `scripts/extract_book.py`
- `scripts/clean_book.py`
- `scripts/translate_book.py` — chunking, avvio del server llama.cpp, checkpoint
- `scripts/finalize_translation.py`
- `scripts/validate_translation.py`
- `scripts/ui_translate_progress.py` — barra di avanzamento per `prepare`
- `audiobook` — `run_stage`, `prepare_book`, `ui_run_step`, `ui_compact`, `ui_translate`

## Gotchas

- `prepare` propaga l'exit code dello stadio fallito e non avvia gli stadi
  successivi. Anche `finalize` interrompe la catena se fallisce la pulizia:
  non valida un vecchio output. Queste garanzie sono verificate senza modelli
  da `tests/test_cli_pipeline.py`.

- **`prepare` rilancia `extract` e `clean` ogni volta.** Sono idempotenti solo se il
  taglio del corpo sta in `book.json`. Modificare `source_en.txt` a mano funziona una
  volta sola: alla `prepare` successiva `clean` lo riscrive intero, l'hash non torna e
  `translate` chiede `--reset`, cioè ore di traduzione buttate. Il taglio va in
  `source.body`:

      "source": {
        "file": "source/original.pdf",
        "language": "en",
        "body": {
          "start_marker": "Introduction This book is for people who want to think",
          "end_marker": "Notes 1. KNOWLEDGE"
        }
      }

  I marcatori sono **sottostringhe**, non righe intere come quelli di `narration`: dopo
  la pulizia una riga è un paragrafo intero e la coda comincia spesso a metà riga. Il
  marcatore finale è escluso. Se un marcatore non si trova, `clean` esce con errore
  invece di tradurre in silenzio anche la bibliografia.
- **Gli exit code di `prepare` dicono cose diverse.** 0 = testo pronto; 2 = il QC
  linguistico chiede una revisione umana; 3 = mancano i marcatori di narrazione in
  `book.json`; 1 = errore vero. Uno script chiamante deve distinguerli.
- `prepare` si ferma a `language-qc`. Il resto della catena è `./audiobook finish`,
  perché in mezzo c'è una decisione umana. Vedi [proofread](proofread.md).
- Gli stadi non verificano il proprio input: `translate` senza `clean` fallisce con
  un errore su file mancante, non con un messaggio sull'ordine giusto. `info` è il
  modo di vedere l'ordine reale.
- Il checkpoint di `translate` (versione 3) include l'hash del prompt effettivo,
  quindi anche contesto, glossario e istruzioni per libro. Se cambiano questi dati,
  sorgente, modello o chunking, il riuso viene bloccato prima di avviare il modello.
  La configurazione viene letta da `book.json`, non riscritta.
- **Migrazione conservativa:** i checkpoint versione 2 non contengono il prompt
  originale e non sono adottati automaticamente. Il comando si ferma senza
  modificare chunk o output. I checkpoint già versione 3 e invariati si riusano
  normalmente. Non serve nessuna migrazione per esportare o riascoltare audio
  già prodotto.
- Se sorgente, modello, chunking e numero di chunk coincidono e manca solo il
  prompt, si può **dichiarare** che il lavoro esistente vale per il prompt attuale:

      ./audiobook translate nome-libro --adopt-checkpoint

  È un'attestazione umana, non una verifica: il file registra l'hash del prompt di
  oggi sui chunk di ieri. Va usato solo se `translation.context`, `terminology` e
  `instructions` non sono cambiati da quando il libro è stato tradotto. In caso
  contrario serve `--reset`, che ritraduce tutto e costa ore.
- Una risposta LLM deve terminare con `finish_reason=stop` e contenere testo:
  risposte troncate (`length`), filtrate o malformate non diventano chunk completati.
  Un backend compatibile deve fornire questo campo. Queste garanzie sono coperte
  da `tests/test_translation_integrity.py`, senza chiamate al modello.
- I test importano `translate_book.py`, che richiede `requests`: vanno lanciati con
  il python di Pandrator, non con `python3` di sistema.

      $PANDRATOR_PY -m unittest discover -s tests
- `translate` avvia da sé il server llama.cpp su `:1234` se non c'è. Un modello già
  caricato ma diverso da `server_model` viene usato comunque.
- `ui_compact` filtra l'output degli stadi con `awk`, riconoscendo l'intestazione
  `<Label> · <slug>` che stampa `run_stage`: uno stadio che stampa un'intestazione
  di forma diversa fa ricomparire righe di rumore nella UI di `prepare`.
