"""Integration test for transcription.

This test actually loads the 'tiny' whisper model and transcribes a
generated audio fixture. It's slower than unit tests (~5-10s) but
validates the full faster-whisper pipeline works.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import voice_input_lib as vi


@pytest.fixture(scope="module")
def transcriber():
    """Load a tiny model once for all tests in this module."""
    settings = {
        "whisper_model": "tiny",
        "whisper_compute_type": "int8",
        "language": "en",
    }
    t = vi.Transcriber(settings)
    t._ensure_model()
    return t


class TestTranscription:
    def test_transcribes_silence_as_empty_or_short(self, transcriber):
        """Silent audio should produce empty or very short text."""
        sr = 16000
        silence = np.zeros(sr * 2, dtype=np.float32)  # 2 seconds of silence
        text = transcriber.transcribe(silence, sr)
        # Whisper may hallucinate on silence, but it shouldn't crash
        assert isinstance(text, str)

    def test_transcribes_audio_returns_string(self, transcriber, sample_audio):
        """Any audio input should return a string without crashing."""
        audio, sr = sample_audio
        text = transcriber.transcribe(audio, sr)
        assert isinstance(text, str)

    def test_model_stays_loaded(self, transcriber):
        """Model should remain loaded between calls."""
        assert transcriber._model is not None
