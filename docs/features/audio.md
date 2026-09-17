# Audio

Crea la sessione Pandrator dal testo pronto, la fa segmentare, lancia la generazione
TTS su Qwen e ne segue i job. Include gli strumenti di prova usati per scegliere il
preset di chunking.

L'assemblaggio finale è una feature a parte: vedi [export](export.md).

## Sub-features

- `prepare-audio` — crea/riusa la sessione, carica `text/narration_ready_it.txt`,
  esegue clean_source e prepare_text con `max_sentence_length=600`
  → `work/pandrator/session.json`
- `generate` — esegue `prepare-audio` (che non rifà niente se è già a posto), poi
  lancia la generazione; riprende dai segmenti mancanti se una run precedente si è
  fermata a metà, e riprende il monitoraggio se un job è già attivo
- `sample` — un campione audio dal testo pronto, per ascoltare la voce
- `chunking-ab` — A/B fra lunghezze di chunk diverse

## How to get to it

Servono: servizi accesi, token Pandrator, `text/narration_ready_it.txt`.

    ./audiobook start
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

- `scripts/pandrator_state.py` — errori HTTP tipizzati, hash e scritture JSON atomiche

- `scripts/pandrator_prepare_audio.py`
- `scripts/pandrator_generate_audio.py`
- `scripts/qwen_sample.py`
- `scripts/qwen_chunking_ab.py`
- `qwen/qwen_pandrator_server.py` — `/v1/audio/speech`, la rotta che Pandrator chiama
- `audiobook` — `run_audio_stage`, `require_token`
- `.secrets/` — token, mai committato

## Gotchas

- Una sessione viene ricreata **solo su HTTP 404**, non su errori di autenticazione,
  rate limit o server. La nuova sessione non eredita hash, job o artefatti di quella
  precedente. Prima di risegmentare vengono invalidati i riferimenti downstream;
  una generazione ancora attiva impedisce di sostituirne il testo. Una preparazione
  nuova richiede una run TTS nuova: i segmenti ancora esposti da una vecchia run
  non possono far risultare già letto il testo nuovo.
- Un job storico completato non basta per dichiarare concluso il lavoro:
  `generate` verifica i segmenti correnti. Errori durante il recupero del job o
  il monitoraggio sono propagati senza avviare una generazione duplicata.
- Anche invocato direttamente, lo script di generazione controlla l'hash del testo
  preparato. Se manca o differisce, richiede `prepare-audio`. Un lavoro già completo
  o il solo monitoraggio di un job attivo non richiedono Qwen acceso.
- `session.json` viene sostituito atomicamente con un temporaneo univoco. Questo
  evita JSON troncato durante una scrittura, **non** fornisce un lock fra due processi:
  non lanciare contemporaneamente due comandi mutanti sullo stesso libro.
- `tests/test_audio_recovery.py` copre recupero 404, errori HTTP, ripreparazione,
  job obsoleti, interruzioni del monitoraggio e paginazione senza modelli reali.

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
- `generate` esegue `prepare-audio` da sé: lanciarlo su un libro mai preparato
  funziona. Lo stato vive in `work/pandrator/session.json`, e cancellarlo perde il
  riferimento a una sessione che su Pandrator continua a esistere — `prepare-audio`
  ne creerebbe una seconda.
- Se un job è già in coda o in esecuzione, `generate` **non** ne crea un secondo:
  riprende il monitoraggio. Rilanciarlo dopo un Ctrl-C è sicuro.
- Le scritture usano un header `Idempotency-Key` nuovo a ogni chiamata: non c'è
  ancora un'identità persistente dell'operazione fra rilanci. Un'interruzione fra
  accettazione del POST e salvataggio del job locale resta un caso da gestire.
- `prepare-audio` è idempotente su un'impronta di testo + impostazioni: se non è
  cambiato niente non risegmenta, e lo dice.
- **Le pause non si configurano per libro.** `sentence_silence_ms` (250) e
  `paragraph_silence_ms` (700) stanno in `scripts/pandrator_generate_audio.py`, e
  il livello del room tone in `config/roomtone.json`. `book.json` non ha voce in
  capitolo: un blocco `audio` lì dentro non viene letto da nessuno.
