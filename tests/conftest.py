import json
import shutil
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def defaults_settings():
    """Return the default settings dict."""
    defaults_path = Path(__file__).parent.parent / "settings.defaults.json"
    with open(defaults_path) as f:
        return json.load(f)


@pytest.fixture
def tmp_settings(tmp_path, defaults_settings):
    """
    Provide a temporary directory with a copy of settings.defaults.json.
    Returns (tmp_dir, defaults_dict).
    """
    dst = tmp_path / "settings.defaults.json"
    with open(dst, "w") as f:
        json.dump(defaults_settings, f)
    return tmp_path, defaults_settings


@pytest.fixture
def sample_audio():
    """Generate a 2-second 440Hz sine wave at 16kHz as float32."""
    sr = 16000
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    return audio, sr


@pytest.fixture
def short_audio():
    """Generate a 0.1-second audio clip (below default min_duration)."""
    sr = 16000
    duration = 0.1
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    return audio, sr
