# Services

Accende e spegne i tre processi locali che servono per generare audio: l'adapter
Qwen3-TTS, il server web Pandrator e il worker che esegue i job.

## Sub-features

- `start` — avvia Qwen (attende `/readyz`, fino a 180s), poi server, poi worker
- `stop` — ferma nell'ordine inverso: worker, server, Qwen
- `restart` — `stop` seguito da `start`
- `status` — stato dei tre servizi + room tone corrente
- `logs` — ultime 20 righe dei tre log
- `open` — apre la web UI Pandrator nel browser
- `daemon install|uninstall|status` — Qwen come LaunchAgent, che riparte da solo

## How to get to it

    ./audiobook daemon install    # una volta sola, consigliato
    ./audiobook start
    ./audiobook status
    ./audiobook open      # http://127.0.0.1:8097
    ./audiobook logs
    ./audiobook stop

Porte: Qwen `8042`, Pandrator web `8097`.

## Driving it

    ./audiobook daemon install
    ./audiobook daemon status
    ./audiobook daemon uninstall
    ./audiobook start
    ./audiobook status
    ./audiobook restart
    ./audiobook logs
    ./audiobook stop
    ./audiobook open

Controlli senza CLI, per un agente che non vuole aprire il browser:

    curl -fsS http://127.0.0.1:8042/readyz
    curl -fsS http://127.0.0.1:8042/health
    lsof -nP -iTCP:8097 -sTCP:LISTEN

## Where it lives

- `audiobook` — funzioni `start_qwen`, `start_server`, `start_worker`, `stop_pid`, `show_status`
- `qwen/qwen_pandrator_server.py` — adapter FastAPI, endpoint OpenAI-like su :8042
- `launchd/local.audiobook.qwen.plist.template` — il LaunchAgent, con i path
  sostituiti all'installazione (launchd non espande variabili)
- `run/` — pidfile (`qwen.pid`, `pandrator-server.pid`, `pandrator-worker.pid`)
- `logs/` — `qwen.log`, `pandrator-server.log`, `pandrator-worker.log`
- `setup.sh` — ricostruisce le virtualenv se una si rompe

## Gotchas

- `setup.sh` usa l'adapter direttamente dal repository e verifica audio e
  trascrizione dichiarati in `config/voice.json` (override:
  `AUDIOBOOK_VOICE_CONFIG`). Non copia più la vecchia `reference_it.wav`,
  assente dai clone nuovi. Il bootstrap senza modelli è coperto da
  `tests/test_setup.py`; questi test non certificano l'installazione dei modelli.

- **Senza LaunchAgent l'adapter muore con la shell che lo ha acceso.** `nohup`
  protegge dal SIGHUP, non dalla pulizia del process group: chiudere il terminale,
  o un task in background che finisce, si è già portato via Qwen a metà lavoro.
  `./audiobook daemon install` lo mette sotto launchd, che lo tiene vivo e lo
  fa ripartire da solo se muore male (`KeepAlive`/`SuccessfulExit false`).
- Con il LaunchAgent installato, `stop` passa da `launchctl stop`: uccidere il pid
  a mano non serve a niente, perché launchd lo fa ripartire.
- Il LaunchAgent non parte al login (`RunAtLoad false`): lo accende `start`.
- L'adapter scrive una riga `HEALTH:` ogni 25 richieste (`QWEN_HEALTH_EVERY`) con
  memoria di processo e memoria MPS, e svuota la cache MPS ogni 50
  (`QWEN_EMPTY_CACHE_EVERY`). Serve a capire perché una generazione lunga è morta
  dopo ~9 ore senza lasciare traccia — vedi [audio](audio.md).
- Il caricamento del modello Qwen su MPS non è istantaneo: `start` può stare fermo
  su "Caricamento modello…" per decine di secondi. `status` distingue `loading` da `ready`.
- `start` muore se la porta è occupata da un processo non gestito dal pidfile: è
  deliberato, non un bug — evita di parlare con un server che non controlli.
- Il worker non ha health endpoint: `status` si fida solo del pidfile. Un worker vivo
  ma bloccato risulta `running`.
- Lo script usa `set -e -u -o pipefail`: un comando interno che fallisce ferma
  tutto. Dove un exit non-zero è un esito previsto (`doctor` che trova problemi,
  `language-qc` che chiede una revisione) sta in una condizione o è marcato
  `|| true`. Aggiungendo codice qui, tenere presente la differenza.
- I path di Pandrator e Qwen si spostano con `PANDRATOR_HOME` e `QWEN_HOME`; default
  `~/src/Pandrator` e `~/src/qwen3-tts-official`.
