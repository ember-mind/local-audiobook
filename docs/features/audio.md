# Audio

Crea la sessione Pandrator dal testo pronto, la fa segmentare, lancia la generazione
TTS su Qwen e ne segue i job. Include gli strumenti di prova usati per scegliere il
preset di chunking.

L'assemblaggio finale è una feature a parte: vedi [export](export.md).

## Sub-features

- `prepare-audio` — crea/riusa la sessione, carica `text/narration_ready_it.txt`,
  esegue clean_source e prepare_text con `max_sentence_length=600`
  → `work/pandrator/session.json`
- `generate` — lancia la generazione, riprende il monitoraggio se un job è già attivo
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

- **La generazione è il punto fragile della pipeline.** L'ultima run registrata è
  morta dopo ~10h con `The speech service returned no audio.` — l'adapter ha smesso
  di restituire audio a metà libro. Prima di lanciare un libro intero, provare
  `./audiobook sample` e guardare `logs/qwen.log`.
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
