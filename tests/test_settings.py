import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent to path so we can import voice_input
sys.path.insert(0, str(Path(__file__).parent.parent))

import importlib
import voice_input_lib as vi


def _write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


class TestLoadSettings:
    def test_loads_defaults_when_no_user_settings(self, tmp_path, defaults_settings):
        defaults_path = tmp_path / "settings.defaults.json"
        settings_path = tmp_path / "settings.json"
        _write_json(defaults_path, defaults_settings)

        with patch.object(vi, "DEFAULTS_PATH", defaults_path), \
             patch.object(vi, "SETTINGS_PATH", settings_path):
            result = vi.load_settings()

        assert result == defaults_settings

    def test_user_settings_override_defaults(self, tmp_path, defaults_settings):
        defaults_path = tmp_path / "settings.defaults.json"
        settings_path = tmp_path / "settings.json"
        _write_json(defaults_path, defaults_settings)
        _write_json(settings_path, {"whisper_model": "medium", "llm_enabled": True})

        with patch.object(vi, "DEFAULTS_PATH", defaults_path), \
             patch.object(vi, "SETTINGS_PATH", settings_path):
            result = vi.load_settings()

        assert result["whisper_model"] == "medium"
        assert result["llm_enabled"] is True
        # Unoverridden defaults should still be present
        assert result["sample_rate"] == defaults_settings["sample_rate"]

    def test_partial_override_preserves_all_defaults(self, tmp_path, defaults_settings):
        defaults_path = tmp_path / "settings.defaults.json"
        settings_path = tmp_path / "settings.json"
        _write_json(defaults_path, defaults_settings)
        _write_json(settings_path, {"language": "fr"})

        with patch.object(vi, "DEFAULTS_PATH", defaults_path), \
             patch.object(vi, "SETTINGS_PATH", settings_path):
            result = vi.load_settings()

        assert result["language"] == "fr"
        for key in defaults_settings:
            assert key in result


class TestValidateSettings:
    def test_valid_defaults(self, defaults_settings):
        errors = vi.validate_settings(defaults_settings)
        assert errors == []

    def test_invalid_model(self, defaults_settings):
        defaults_settings["whisper_model"] = "nonexistent"
        errors = vi.validate_settings(defaults_settings)
        assert any("whisper_model" in e for e in errors)

    def test_invalid_compute_type(self, defaults_settings):
        defaults_settings["whisper_compute_type"] = "bfloat16"
        errors = vi.validate_settings(defaults_settings)
        assert any("whisper_compute_type" in e for e in errors)

    def test_negative_min_duration(self, defaults_settings):
        defaults_settings["min_duration"] = -1
        errors = vi.validate_settings(defaults_settings)
        assert any("min_duration" in e for e in errors)

    def test_invalid_sample_rate(self, defaults_settings):
        defaults_settings["sample_rate"] = 12345
        errors = vi.validate_settings(defaults_settings)
        assert any("sample_rate" in e for e in errors)

    def test_hotkey_not_a_list(self, defaults_settings):
        defaults_settings["hotkey_record"] = "KEY_V"
        errors = vi.validate_settings(defaults_settings)
        assert any("hotkey_record" in e for e in errors)

    def test_hotkey_non_string_elements(self, defaults_settings):
        defaults_settings["hotkey_toggle_llm"] = [1, 2, 3]
        errors = vi.validate_settings(defaults_settings)
        assert any("hotkey_toggle_llm" in e for e in errors)
