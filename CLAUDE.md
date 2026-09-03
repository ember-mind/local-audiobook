# Local Audiobook — istruzioni per agenti

Pipeline locale che trasforma un libro in un audiolibro italiano: estrazione,
traduzione con LLM locale, QC linguistico, narrazione, TTS con Qwen3-TTS via
Pandrator, export M4B.

## Leggi prima la Feature Map

**[`docs/features/`](docs/features/README.md)** — un catalogo di tutto ciò che si può
fare con questo repo: per ogni feature cosa fa, come lanciarla, dove vive nel codice,
quali trappole ha. Aprila prima di esplorare i sorgenti: risparmia contesto e contiene
i gotchas che dal codice non si vedono. L'indice ha anche la pipeline completa in una
schermata.

## Regola per chi tocca il codice

La scheda si aggiorna **nella stessa modifica**. Rinomini un file, aggiungi un
comando, cambi un default: la scheda che lo nomina va aggiornata subito, non dopo.

Prima di considerare finito un lavoro:

    python3 tests/feature_map_check.py

Verifica in tre direzioni: che la mappa non citi codice inesistente, che il codice non
abbia comandi o script che nessuna scheda nomina, e che i comandi che il CLI suggerisce
a schermo esistano davvero.

## Cose da sapere subito

- Gli script Python girano con il python di Pandrator, non con `python3`:
  `$PANDRATOR_PY`, cioè `~/src/Pandrator/.venv/bin/python` (override: `PANDRATOR_HOME`).
  In `audiobook` non hardcodare quel path: passa da `run_stage` / `run_audio_stage`.
- `audiobook` gira con `set -e -u -o pipefail`. Un exit non-zero previsto va in una
  condizione o marcato `|| true`, altrimenti ferma lo script.
- Gli exit code degli stadi non sono binari: `prepare` esce 2 se serve una revisione
  umana e 3 se manca configurazione. Non collassarli in "fallito".
- Le correzioni di un libro sono **dati**, non codice: stanno in
  `books/<slug>/work/language_qc_manual_fixes.json`, mai dentro gli script.
- La voce di riferimento è `config/voice.json`, letta sia dall'adapter sia dal doctor.
  Non hardcodare path di clip.
- `books/` non è in git e pesa centinaia di MB: mai `git add -A` senza guardare.
  Non c'è undo su quella cartella: `prune` ha una allowlist di cosa può cancellare
  e di default non cancella niente. Estenderla lì, non aggirarla.
- Il room tone dipende da una patch applicata a `~/src/Pandrator`, fuori da questo
  repo. `./audiobook doctor` è l'unico posto che verifica che ci sia ancora.
