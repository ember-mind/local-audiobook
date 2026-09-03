# Voice reference

Qwen fa voice cloning ICL: gli si dà una clip di riferimento con la sua trascrizione
esatta, e imita quella voce. Quale clip usare è configurazione, non codice.

## Sub-features

- `config/voice.json` — quale clip carica l'adapter
- `transcribe` — trascrive una registrazione con Whisper
- `reference` — ritaglia e normalizza la clip finale con ffmpeg, allineata alla
  trascrizione

## How to get to it

Cambiare voce:

    # config/voice.json
    {
      "voice_id": "italiano",
      "language": "Italian",
      "reference_dir": "qwen/reference-bank/harry",
      "reference_audio": "reference_it_v2.wav",
      "reference_text": "reference_it_v2.txt"
    }

    ./audiobook restart

Costruirne una nuova da una registrazione:

    ./audiobook transcribe qwen/reference-bank/<nome>/reference_source.wav \
                           qwen/reference-bank/<nome>/reference_source_transcript_plain.txt
    ./audiobook reference qwen/reference-bank/<nome>

`reference_dir` è relativo alla radice del repo, o assoluto.

## Driving it

    ./audiobook transcribe <audio-in> <testo-out>
    ./audiobook reference qwen/reference-bank/harry

    ./audiobook restart
    ./audiobook doctor | grep Reference
    curl -fsS http://127.0.0.1:8042/health

Provare la voce su testo reale:

    ./audiobook sample nome-libro

## Where it lives

- `config/voice.json` — la config
- `qwen/qwen_pandrator_server.py` — `load_voice_config`, override con
  `AUDIOBOOK_VOICE_CONFIG`
- `audiobook` — `voice_reference_path` (il doctor risolve il path dalla stessa config)
- `scripts/transcribe_reference.py`
- `scripts/build_reference.py`
- `qwen/reference-bank/harry/reference_it_v2.wav` — la clip in uso
- `qwen/reference-bank/harry/reference_it_v2.txt` — la sua trascrizione
- `environments/whisper` — ambiente Whisper per la trascrizione

## Gotchas

- **Trascrizione e audio devono corrispondere parola per parola.** Una parola sbagliata
  degrada il cloning in modo silenzioso: nessun errore, solo voce peggiore. Il doctor
  verifica che la trascrizione esista e non sia vuota, non che sia corretta.
- Cambiata la config, va fatto `restart`: modello e clip si caricano al boot.
- La voce è **globale**, una per installazione. `book.json` ha un campo
  `voice.reference` che nessuno legge: resta lì dalle versioni precedenti. Un libro
  non può avere una voce sua.
- `voice_id` è il nome che l'adapter espone a Pandrator; le impostazioni di
  generazione in [audio](audio.md) mandano `kobo`, che l'adapter tratta come alias.
  Cambiando `voice_id` quell'alias resta l'unico canale che funziona.
- La clip in uso è tracciata in git (serve a far partire un clone fresco); il
  materiale grezzo da cui si ricava — `reference_source_*` — no, è grosso e
  ricostruibile solo dalla registrazione originale.
