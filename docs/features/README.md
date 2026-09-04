# Feature Map

Catalogo di tutto ciò che si può fare con Local Audiobook: per ogni feature *cosa fa*,
*come ci si arriva da utente*, *come la pilota un agente*, *dove vive nel codice*,
*quali trappole ha*.

Non è architettura (com'è fatto dentro) e non è un backlog. È la proiezione compatta
del codice: il codice resta la memoria vera.

## Indice

| Feature | Scopo | File principali |
|---|---|---|
| [services](services.md) | Accendere e spegnere i tre servizi locali (Qwen, Pandrator server, worker) | `audiobook`, `qwen/qwen_pandrator_server.py` |
| [doctor](doctor.md) | Verificare che venv, modello, voce, token, patch e servizi siano a posto | `audiobook` (`run_doctor`) |
| [books](books.md) | Creare, ispezionare e sfoltire progetti-libro | `audiobook` (`new_book`, `book_info`, `list_books`), `scripts/prune_work.py` |
| [text-pipeline](text-pipeline.md) | Da PDF/EPUB/TXT a traduzione italiana validata | `scripts/extract_book.py`, `clean_book.py`, `translate_book.py`, `finalize_translation.py`, `validate_translation.py` |
| [proofread](proofread.md) | QC linguistico con LLM e applicazione delle correzioni | `scripts/language_qc.py`, `resolve_language_qc.py`, `apply_review_fixes.py` |
| [narration](narration.md) | Ritagliare il corpo del libro e pulire i residui di impaginazione | `scripts/build_narration.py`, `clean_layout.py`, `finalize_layout.py` |
| [audio](audio.md) | Sessione Pandrator, generazione TTS, prove di chunking | `scripts/pandrator_prepare_audio.py`, `pandrator_generate_audio.py`, `qwen_sample.py`, `qwen_chunking_ab.py` |
| [export](export.md) | Assemblare l'M4B finale con cover e metadata | `scripts/export_m4b.py` |
| [chapters](chapters.md) | Scrivere i capitoli nell'M4B, senza ricodificare | `scripts/add_chapters.py` |
| [voice-reference](voice-reference.md) | Costruire e cambiare la voce di riferimento per il cloning | `config/voice.json`, `scripts/build_reference.py`, `transcribe_reference.py` |
| [roomtone](roomtone.md) | Room tone al posto del silenzio digitale nelle pause | `audiobook` (`roomtone`), `config/roomtone.json`, `patches/pandrator-roomtone.patch` |

## La pipeline in una schermata

    new                       source/original.pdf
      extract                 text/source_raw.txt
      clean                   text/source_en.txt
      translate               text/book_it.txt
      finalize + validate     work/validation_report.txt
      narrate                 text/narration_it.txt          ← serve narration.* in book.json
      language-qc             work/language_qc.json          ← exit 2: revisione umana
      ────────────────────────────────────────────── prepare si ferma qui
      resolve-qc              text/narration_final_it.txt
      apply-fixes             text/narration_reviewed_it.txt ← work/language_qc_manual_fixes.json
      layout                  text/narration_ready_it.txt
      ────────────────────────────────────────────── finish arriva qui
      prepare-audio           work/pandrator/session.json
      generate                segmenti audio in Pandrator
      export                  output/<slug>.m4b
      chapters                capitoli nell'M4B          ← serve "chapters" in book.json

`./audiobook prepare` copre il primo blocco, `./audiobook finish` il secondo.
`./audiobook info <slug>` dice a che punto è un libro e quali stadi sono da rifare
perché il loro input è cambiato.

## Manutenzione

**Regola: la scheda si aggiorna nella stessa modifica del codice.**

Guardia meccanica, tre direzioni:

    python3 tests/feature_map_check.py

- *verità* (mappa → codice): ogni path citato esiste; ogni `./audiobook <cmd>` citato è
  un ramo reale del `case`.
- *copertura* (codice → mappa): ogni ramo del `case` è nominato da una scheda; ogni
  `scripts/*.py` non-backup è nominato da una scheda.
- *puntatori*: ogni `./audiobook <cmd>` che il CLI stampa a schermo esiste. È il check
  che ha preso `Next → ./audiobook generate` quando quel comando non esisteva ancora.

Passata semantica, per milestone: aprire ogni scheda e i suoi path, cancellare i
gotchas senza codice dietro, aggiungere le sub-feature nuove.

**La deriva che nessun test vede:** comportamento nuovo su un comando che esiste già
(una riga in più nell'output, un file intermedio nuovo). Non rinomina niente, quindi
ogni riga della mappa resta vera — la mappa dice solo *meno* di quanto fa il codice.
È silenzio, non errore. Solo la passata semantica la prende.
