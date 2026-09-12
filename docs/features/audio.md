# Audio

Crea la sessione Pandrator dal testo pronto, la fa segmentare, lancia la generazione
TTS su Qwen e ne segue i job. Include gli strumenti di prova usati per scegliere il
preset di chunking.

L'assemblaggio finale è una feature a parte: vedi [export](export.md).

## Sub-features

- `prepare-audio` — crea/riusa la sessione, carica `text/narration_ready_it.txt`,
  esegue clean_source e prepare_text con `max_sentence_length=600`
  → `work/pandrator/session.json`
- `generate` — lancia la generazione; riprende dai segmenti mancanti se una run
  precedente si è fermata a metà, e riprende il monitoraggio se un job è già attivo
- `sample` — un campione audio dal testo pronto, per ascoltare la voce
- `chunking-ab` — A/B fra lunghezze di chunk diverse

## How to get to it

Servono: servizi accesi, token Pandrator, `text/narration_ready_it.txt`.

    ./audiobook start
    ./audiobook prepare-audio nome-libro
    ./audiobook generate nome-libro
    ./audiobook export nome-libro

Il token sta in `.secrets/pandrator-token` (fuori da git); `./audiobook doctor` lo
verifica. API Pandrator: `http://127.0.0.1:8097/api/v1`.

## Driving it

    ./audiobook start
    ./audiobook status

    ./audiobook prepare-audio nome-libro
    ./audiobook generate nome-libro
    ./audiobook sample nome-libro
    ./audiobook chunking-ab nome-libro

Stato della sessione senza rilanciare niente:

    python3 -m json.tool books/<slug>/work/pandrator/session.json

    curl -fsS -H "Authorization: Bearer $(cat .secrets/pandrator-token)" \
      http://127.0.0.1:8097/api/v1/sessions

## Where it lives

- `scripts/pandrator_prepare_audio.py`
- `scripts/pandrator_generate_audio.py`
- `scripts/qwen_sample.py`
- `scripts/qwen_chunking_ab.py`
- `qwen/qwen_pandrator_server.py` — `/v1/audio/speech`, la rotta che Pandrator chiama
- `audiobook` — `run_audio_stage`, `require_token`
- `.secrets/` — token, mai committato

## Gotchas

- **Una generazione lunga è già fallita una volta, e non si sa perché.** Il job del
  2026-09-01 è morto al segmento 3154 di 3763 — dopo ~10h45m e l'84% del libro — con
  `The speech service returned no audio.`. Il segmento su cui si è fermato non ha
  niente di strano (123 caratteri di prosa normale), e su adapter fresco la sintesi
  funziona: non è un difetto di partenza, qualcosa cede nel lungo periodo.
- **`generate` riprende, non ricomincia.** Guarda lo stato dei segmenti e, se ne
  trova di già completati, chiede una run sui soli mancanti — il che ha reso il
  retry di quel libro 609 segmenti invece di 3763. Senza questo un rilancio
  butterebbe via ore di audio buono.
- La rotta dello stage (`/stages/generate_audio/run`) **non** accetta `segment_ids`:
  la ripresa passa da `/sessions/<id>/generation-runs`, che riusa la run esistente e
  le sue impostazioni congelate. Per questo il retry non rilegge `settings`: se serve
  cambiare la configurazione TTS, va rifatta una run pulita.
- L'endpoint `/generation-runs/<id>/resume` di Pandrator accetta **solo** run in
  stato `paused`: su una run `failed` risponde 409, ed è il motivo per cui la ripresa
  è fatta per segment_ids invece che con quello.
- L'elenco dei segmenti pagina a 250: chi lo legge senza seguire `next_cursor` vede
  solo i primi, tutti completati, e conclude che non ci sia niente da fare.
- L'adapter muore insieme al process group che lo ha avviato. Lanciandolo da uno
  script o da una sessione che poi viene chiusa, la porta 8042 sparisce senza
  traceback e senza crash report: sembra un crash, è una pulizia. `./audiobook start`
  usa `nohup`, ma il process group resta quello del chiamante.
- **`max_sentence_length=600` non è arbitrario.** Scelto con `chunking-ab`: blocchi
  lunghi danno a Qwen abbastanza contesto per una prosodia narrativa. `generate`
  **rifiuta** una sessione preparata con un altro valore — è una guardia.
- `generate` senza `prepare-audio` esce con "Sessione Pandrator non trovata": lo stato
  vive in `work/pandrator/session.json`, cancellarlo perde il riferimento a una
  sessione che su Pandrator continua a esistere.
- Se un job è già in coda o in esecuzione, `generate` **non** ne crea un secondo:
  riprende il monitoraggio. Rilanciarlo dopo un Ctrl-C è sicuro.
- Le scritture usano un header `Idempotency-Key` nuovo a ogni chiamata: un retry
  interno è protetto, un rilancio manuale dello script no.
- `prepare-audio` è idempotente su un'impronta di testo + impostazioni: se non è
  cambiato niente non risegmenta, e lo dice.
- **Le pause non si configurano per libro.** `sentence_silence_ms` (250) e
  `paragraph_silence_ms` (700) stanno in `scripts/pandrator_generate_audio.py`, e
  il livello del room tone in `config/roomtone.json`. `book.json` non ha voce in
  capitolo: un blocco `audio` lì dentro non viene letto da nessuno.
