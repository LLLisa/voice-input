import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import voice_input_lib as vi


class TestInsertText:
    @patch("voice_input_lib.subprocess.run")
    def test_copies_to_clipboard_and_pastes(self, mock_run):
        settings = {"auto_paste": True}
        vi.insert_text("hello world", settings)

        assert mock_run.call_count == 2
        # First call: wl-copy
        wl_copy_call = mock_run.call_args_list[0]
        assert wl_copy_call[0][0] == ["wl-copy", "--", "hello world"]
        # Second call: wtype
        wtype_call = mock_run.call_args_list[1]
        assert wtype_call[0][0][0] == "wtype"

    @patch("voice_input_lib.subprocess.run")
    def test_clipboard_only_when_auto_paste_disabled(self, mock_run):
        settings = {"auto_paste": False}
        vi.insert_text("hello world", settings)

        assert mock_run.call_count == 1
        wl_copy_call = mock_run.call_args_list[0]
        assert wl_copy_call[0][0] == ["wl-copy", "--", "hello world"]

    @patch("voice_input_lib.subprocess.run")
    def test_empty_text_does_nothing(self, mock_run):
        settings = {"auto_paste": True}
        vi.insert_text("", settings)
        mock_run.assert_not_called()

    @patch("voice_input_lib.subprocess.run")
    def test_special_characters_passed_through(self, mock_run):
        settings = {"auto_paste": True}
        vi.insert_text("hello 'world' \"foo\" & bar", settings)

        wl_copy_call = mock_run.call_args_list[0]
        assert wl_copy_call[0][0] == ["wl-copy", "--", "hello 'world' \"foo\" & bar"]

    @patch("voice_input_lib.subprocess.run")
    def test_wl_copy_failure_skips_paste(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, "wl-copy")

        settings = {"auto_paste": True}
        vi.insert_text("hello", settings)

        # Only wl-copy was attempted, wtype was not called
        assert mock_run.call_count == 1

    @patch("voice_input_lib.subprocess.run")
    def test_wtype_missing_graceful_fallback(self, mock_run):
        def side_effect(*args, **kwargs):
            if args[0][0] == "wtype":
                raise FileNotFoundError("wtype not found")

        mock_run.side_effect = side_effect
        settings = {"auto_paste": True}
        # Should not raise
        vi.insert_text("hello", settings)
