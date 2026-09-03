# Doctor

Una passata di controlli prima di lanciare una generazione lunga: virtualenv,
import, MPS, voce, token, patch di Pandrator, config e servizi.

## Sub-features

- venv — Pandrator e Qwen python eseguibili, `import pandrator`, `import torch, qwen_tts`
- hardware — `torch.backends.mps.is_available()`
- voce — `config/voice.json` valido, clip di riferimento e trascrizione presenti
- asset — adapter Qwen, room tone WAV, `roomtone.json` valido
- credenziali — token Pandrator presente e non vuoto
- patch — `_room_tone_pcm` presente in Pandrator, patch di backup non vuota
- runtime — Qwen `/readyz`, porta 8097, LLM di traduzione su 1234 (informativi)

## How to get to it

    ./audiobook doctor

Exit 0 se nessun errore, 1 con il conteggio dei problemi. Le righe `○` sono servizi
spenti: informative, non contano come errori.

## Driving it

    ./audiobook doctor; echo "exit=$?"

## Where it lives

- `audiobook` — funzione `run_doctor`
- `audiobook` — funzione `check_installation` (versione ridotta, gira prima di `start`)
- `audiobook` — funzione `voice_reference_path` (risolve la clip dalla config)
- `config/voice.json`, `config/roomtone.json`, `config/roomtone_it.wav`
- `patches/pandrator-roomtone.patch`

## Gotchas

- La reference voice viene risolta dalla **stessa** `config/voice.json` che legge
  l'adapter: cambiando voce il check segue senza modifiche al codice. Controlla anche
  la trascrizione, che deve esistere e non essere vuota — il cloning ICL la usa.
- Il check della patch room tone è un `grep` di una stringa nel sorgente di Pandrator:
  cambia nome alla funzione a monte e diventa un falso rosso. È comunque l'unico posto
  che si accorge se un aggiornamento di Pandrator ha spento il room tone.
- Verde non garantisce che una generazione riesca: dice che l'ambiente è a posto, non
  che il modello risponderà. Vedi il gotcha sulla generazione in [audio](audio.md).
- Il doctor non prova a generare audio: è deliberato, serve a essere veloce.
