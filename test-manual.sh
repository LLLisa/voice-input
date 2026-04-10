#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: venv not found. Run ./install.sh first."
    exit 1
fi

DURATION="${1:-3}"
USE_LLM=false

for arg in "$@"; do
    case "$arg" in
        --llm) USE_LLM=true ;;
        [0-9]*) DURATION="$arg" ;;
    esac
done

echo "=== Manual voice-input test ==="
echo "Recording for ${DURATION} seconds..."
echo "Speak now!"
echo ""

"$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
import numpy as np
import sounddevice as sd
from voice_input_lib import Transcriber, llm_cleanup, load_settings

duration = float($DURATION)
use_llm = $( [ "$USE_LLM" = true ] && echo True || echo False )
sr = 16000

# Record
print('Recording...')
audio = sd.rec(int(sr * duration), samplerate=sr, channels=1, dtype='float32')
sd.wait()
audio = audio.flatten()
print(f'Recorded {len(audio)/sr:.1f}s of audio.')

# Transcribe
settings = load_settings()
settings['whisper_model'] = settings.get('whisper_model', 'small')
transcriber = Transcriber(settings)
print('Transcribing...')
text = transcriber.transcribe(audio, sr)
print(f'Raw:     {text}')

if use_llm:
    print('Running LLM cleanup...')
    cleaned = llm_cleanup(text, settings)
    print(f'Cleaned: {cleaned}')

print()
print('Done.')
"
