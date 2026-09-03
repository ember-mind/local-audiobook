# Room tone

Fra una frase e l'altra Pandrator inserisce silenzio digitale assoluto. Il noise
floor della voce Qwen non è zero, quindi il passaggio si sente come uno scatto.
Il room tone riempie le pause con un rumore di fondo a livello controllato.

## Sub-features

- `roomtone status` — livello attuale o OFF
- `roomtone -58` — qualsiasi livello fra -90 e -30 dBFS; -58 è il default testato
- `roomtone on` — riaccende all'ultimo livello impostato
- `roomtone off` — torna al silenzio digitale

## How to get to it

    ./audiobook roomtone status
    ./audiobook roomtone -58

Il livello compare anche in `./audiobook status` e in `./audiobook doctor`.

## Driving it

    ./audiobook roomtone status
    ./audiobook roomtone -58
    ./audiobook roomtone -62
    ./audiobook roomtone on
    ./audiobook roomtone off

Leggere la config direttamente:

    python3 -m json.tool config/roomtone.json

Verificare che la patch sia ancora applicata a monte:

    grep -c _room_tone_pcm ~/src/Pandrator/pandrator/web/audio_assembly.py

## Where it lives

- `audiobook` — funzioni `roomtone`, `roomtone_enabled`
- `config/roomtone.json` — `enabled`, `level_dbfs`
- `config/roomtone_it.wav` — la clip di rumore
- `patches/pandrator-roomtone.patch` — la modifica a Pandrator che legge la config
- `audiobook` — `start_server` / `start_worker` passano `PANDRATOR_ROOM_TONE_CONFIG`

## Gotchas

- **Funziona solo con Pandrator patchato.** La feature vive metà qui e metà in
  `~/src/Pandrator`. Un aggiornamento di Pandrator la spegne in silenzio: il room tone
  sparisce dall'audio ma i comandi continuano a rispondere OK. `doctor` è l'unico
  posto che se ne accorge.
- Il livello ammesso va da -90 a -30 dBFS: sotto è inudibile, sopra copre la voce.
  Fuori scala il comando rifiuta e dice il perché.
- Il valore va cambiato **prima** di avviare i servizi: la config si legge via env var
  al boot. Cambiarlo a generazione in corso non ha effetto, e nessun messaggio lo dice.
- `book.json` ha `audio.roomtone` e `audio.roomtone_dbfs` per libro, ma il room tone
  reale viene da `config/roomtone.json`: i campi nel libro sono decorativi.
- `status` distingue acceso (`✓`) da spento (`○`); `roomtone status` da solo stampa
  la riga senza glifo.
- `config/roomtone.json` tiene anche `source_dbfs`, il livello a cui è stata
  registrata `roomtone_it.wav`: serve a Pandrator per calcolare il guadagno. Sostituendo
  il WAV va aggiornato a mano, o il livello richiesto non è quello che si sente.
