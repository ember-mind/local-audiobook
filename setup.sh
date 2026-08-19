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

if [ ! -d "$PANDRATOR_HOME/.git" ]; then
  echo "→ Clono Pandrator..."
  mkdir -p "$(dirname "$PANDRATOR_HOME")"
  git clone https://github.com/lukaszliniewicz/Pandrator.git "$PANDRATOR_HOME"
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
    uv pip install --python .venv/bin/python -U qwen-tts
  )
else
  echo "✓ Ambiente Qwen esistente"
fi

#
# Nostro adapter + voce
#

echo "→ Installo configurazione Qwen..."

cp "$ROOT/qwen/qwen_pandrator_server.py" \
   "$QWEN_HOME/qwen_pandrator_server.py"

cp "$ROOT/qwen/reference_it.wav" \
   "$QWEN_HOME/reference_it.wav"

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
