import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import voice_input_lib as vi


class TestRecorder:
    def test_stop_without_start_returns_none(self):
        rec = vi.Recorder(16000)
        assert rec.stop() is None

    def test_records_and_returns_audio(self):
        rec = vi.Recorder(16000)

        # Simulate by manually adding chunks (bypass actual audio device)
        chunk1 = np.random.randn(1600, 1).astype(np.float32)
        chunk2 = np.random.randn(1600, 1).astype(np.float32)
        rec._chunks = [chunk1, chunk2]
        rec._stream = MagicMock()

        audio = rec.stop()
        assert audio is not None
        assert audio.ndim == 1
        assert len(audio) == 3200
        assert audio.dtype == np.float32

    def test_empty_chunks_returns_none(self):
        rec = vi.Recorder(16000)
        rec._chunks = []
        rec._stream = MagicMock()
        audio = rec.stop()
        assert audio is None


class TestMinDuration:
    def test_short_audio_detected(self, short_audio):
        """Audio shorter than min_duration should be detectable."""
        audio, sr = short_audio
        duration = len(audio) / sr
        assert duration < 0.5  # default min_duration

    def test_normal_audio_passes(self, sample_audio):
        """2-second audio should be above min_duration."""
        audio, sr = sample_audio
        duration = len(audio) / sr
        assert duration >= 0.5


class TestGenerateTone:
    def test_generates_correct_length(self):
        tone = vi._generate_tone(440, 0.5, 44100)
        assert len(tone) == 22050

    def test_generates_float32(self):
        tone = vi._generate_tone(440, 0.1, 16000)
        assert tone.dtype == np.float32

    def test_amplitude_within_bounds(self):
        tone = vi._generate_tone(440, 0.5, 44100)
        assert np.max(np.abs(tone)) <= 1.0
