#!/bin/bash

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

PANDRATOR_HOME="${PANDRATOR_HOME:-$HOME/src/Pandrator}"
QWEN_HOME="${QWEN_HOME:-$HOME/src/qwen3-tts-official}"

echo
echo "Local Audiobook Setup"
echo "─────────────────────"

command -v uv >/dev/null 2>&1 || {
  echo "✗ uv non trovato."
  echo "  Installa uv prima di continuare."
  exit 1
}

echo "→ Verifico Python 3.12..."
uv python install 3.12

#
# Pandrator
#

# Le versioni con cui la pipeline funziona davvero: config/environment.lock.json,
# scritto da ./audiobook lock. Senza lock si prende l'ultimo commit, che e' come
# funzionava prima — e nessuno puo' sapere cosa arrivera'.
LOCKED_REVISION=""
LOCKED_QWEN=""

if [ -f "$ROOT/config/environment.lock.json" ]; then
  LOCKED_REVISION="$(python3 -c '
import json, sys
lock = json.load(open(sys.argv[1]))
print(lock.get("pandrator", {}).get("revision") or "")
' "$ROOT/config/environment.lock.json")"

  LOCKED_QWEN="$(python3 -c '
import json, sys
lock = json.load(open(sys.argv[1]))
print(lock.get("qwen", {}).get("qwen-tts") or "")
' "$ROOT/config/environment.lock.json")"
fi

if [ ! -d "$PANDRATOR_HOME/.git" ]; then
  echo "→ Clono Pandrator..."
  mkdir -p "$(dirname "$PANDRATOR_HOME")"
  git clone https://github.com/lukaszliniewicz/Pandrator.git "$PANDRATOR_HOME"

  if [ -n "$LOCKED_REVISION" ]; then
    echo "→ Revisione fissata: $LOCKED_REVISION"
    git -C "$PANDRATOR_HOME" checkout --quiet "$LOCKED_REVISION"
  fi
elif [ -n "$LOCKED_REVISION" ] && [ -d "$PANDRATOR_HOME/.git" ]; then
  current="$(git -C "$PANDRATOR_HOME" rev-parse HEAD 2>/dev/null || echo sconosciuta)"

  if [ "$current" != "$LOCKED_REVISION" ]; then
    # Un checkout qui butterebbe via la patch del room tone applicata a mano.
    echo "○ Pandrator e' su $current, il lock dice $LOCKED_REVISION"
    echo "  Allinearlo a mano, e ricordarsi della patch del room tone."
  fi
fi

if [ ! -x "$PANDRATOR_HOME/.venv/bin/python" ]; then
  echo "→ Creo ambiente Pandrator..."
  rm -rf "$PANDRATOR_HOME/.venv"

  (
    cd "$PANDRATOR_HOME"
    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -e .
  )
else
  echo "✓ Ambiente Pandrator esistente"
fi

#
# Qwen3-TTS
#

mkdir -p "$QWEN_HOME"

if [ ! -x "$QWEN_HOME/.venv/bin/python" ]; then
  echo "→ Creo ambiente Qwen3-TTS..."
  rm -rf "$QWEN_HOME/.venv"

  (
    cd "$QWEN_HOME"
    uv venv --python 3.12 .venv
    if [ -n "$LOCKED_QWEN" ]; then
      echo "→ qwen-tts==$LOCKED_QWEN (da environment.lock.json)"
      uv pip install --python .venv/bin/python "qwen-tts==$LOCKED_QWEN"
    else
      uv pip install --python .venv/bin/python -U qwen-tts
    fi
  )
else
  echo "✓ Ambiente Qwen esistente"
fi

#
# Nostro adapter + voce
#

# The CLI and launchd run the adapter directly from this repository. A copy
# in QWEN_HOME would resolve config/voice.json relative to the wrong directory.
echo "→ Verifico la voce configurata..."

"$QWEN_HOME/.venv/bin/python" - "$ROOT" <<'PYVOICE'
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
config_path = Path(os.environ.get("AUDIOBOOK_VOICE_CONFIG", root / "config/voice.json"))
if not config_path.is_file():
    raise SystemExit(f"Configurazione voce non trovata: {config_path}")
config = json.loads(config_path.read_text(encoding="utf-8"))
reference_dir = Path(config.get("reference_dir", "qwen/reference-bank/harry"))
if not reference_dir.is_absolute():
    reference_dir = root / reference_dir
for key, default in (("reference_audio", "reference_it_v2.wav"),
                     ("reference_text", "reference_it_v2.txt")):
    path = reference_dir / config.get(key, default)
    if not path.is_file() or not path.stat().st_size:
        raise SystemExit(f"File voce mancante o vuoto: {path}")
    if key == "reference_text" and not path.read_text(encoding="utf-8").strip():
        raise SystemExit(f"Trascrizione voce vuota: {path}")
    print(f"✓ {path}")
PYVOICE

#
# Room tone
#

echo "→ Configuro room tone..."

cp "$ROOT/config/roomtone_it.wav" \
   "$PANDRATOR_HOME/roomtone_it.wav"

cp "$ROOT/config/roomtone.json" \
   "$PANDRATOR_HOME/roomtone.json"

#
# Pandrator patch
#

ASSEMBLER="$PANDRATOR_HOME/pandrator/web/audio_assembly.py"

if grep -q "_room_tone_pcm" "$ASSEMBLER" 2>/dev/null; then
  echo "✓ Patch room tone già applicata"
else
  echo "→ Applico patch room tone..."

  (
    cd "$PANDRATOR_HOME"

    if git apply --check "$ROOT/patches/pandrator-roomtone.patch"; then
      git apply "$ROOT/patches/pandrator-roomtone.patch"
      echo "✓ Patch applicata"
    else
      echo
      echo "✗ La patch non è compatibile con questa versione di Pandrator."
      echo "  Nessun file è stato modificato."
      echo "  Probabilmente Pandrator è cambiato dopo un aggiornamento."
      exit 1
    fi
  )
fi

echo
echo "✓ Setup completato"
echo
echo "Ora esegui:"
echo "  ./audiobook doctor"
echo "  ./audiobook start"
