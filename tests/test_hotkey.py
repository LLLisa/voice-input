import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import voice_input_lib as vi


def _make_state(record=None, toggle=None):
    settings = {
        "hotkey_record": record or ["KEY_LEFTMETA", "KEY_V"],
        "hotkey_toggle_llm": toggle or ["KEY_LEFTMETA", "KEY_LEFTSHIFT", "KEY_V"],
    }
    return vi.HotkeyState(settings)


class TestHotkeyState:
    def test_initial_state_is_idle(self):
        state = _make_state()
        assert state.state == vi.HotkeyState.IDLE

    def test_record_combo_starts_recording(self):
        state = _make_state()
        assert state.key_down("KEY_LEFTMETA") is None
        action = state.key_down("KEY_V")
        assert action == "start_recording"
        assert state.state == vi.HotkeyState.RECORDING

    def test_record_combo_reverse_order(self):
        """V first, then Super — should also trigger."""
        state = _make_state()
        assert state.key_down("KEY_V") is None
        action = state.key_down("KEY_LEFTMETA")
        assert action == "start_recording"
        assert state.state == vi.HotkeyState.RECORDING

    def test_release_stops_recording(self):
        state = _make_state()
        state.key_down("KEY_LEFTMETA")
        state.key_down("KEY_V")
        assert state.state == vi.HotkeyState.RECORDING

        action = state.key_up("KEY_V")
        assert action == "stop_recording"
        assert state.state == vi.HotkeyState.PROCESSING

    def test_release_super_also_stops(self):
        state = _make_state()
        state.key_down("KEY_LEFTMETA")
        state.key_down("KEY_V")

        action = state.key_up("KEY_LEFTMETA")
        assert action == "stop_recording"
        assert state.state == vi.HotkeyState.PROCESSING

    def test_finish_processing_returns_to_idle(self):
        state = _make_state()
        state.key_down("KEY_LEFTMETA")
        state.key_down("KEY_V")
        state.key_up("KEY_V")
        assert state.state == vi.HotkeyState.PROCESSING
        state.finish_processing()
        assert state.state == vi.HotkeyState.IDLE

    def test_toggle_llm_detected(self):
        state = _make_state()
        state.key_down("KEY_LEFTMETA")
        state.key_down("KEY_LEFTSHIFT")
        action = state.key_down("KEY_V")
        assert action == "toggle_llm"
        # Should NOT enter recording state
        assert state.state == vi.HotkeyState.IDLE

    def test_unrelated_keys_ignored(self):
        state = _make_state()
        assert state.key_down("KEY_A") is None
        assert state.key_down("KEY_B") is None
        assert state.key_up("KEY_A") is None
        assert state.state == vi.HotkeyState.IDLE

    def test_single_key_not_enough(self):
        state = _make_state()
        assert state.key_down("KEY_V") is None
        assert state.state == vi.HotkeyState.IDLE
        assert state.key_up("KEY_V") is None

    def test_no_action_while_processing(self):
        """While processing, new key presses should not trigger recording."""
        state = _make_state()
        state.key_down("KEY_LEFTMETA")
        state.key_down("KEY_V")
        state.key_up("KEY_V")
        assert state.state == vi.HotkeyState.PROCESSING

        # Try pressing combo again while processing
        assert state.key_down("KEY_V") is None

    def test_recording_duration(self):
        import time
        state = _make_state()
        assert state.recording_duration() == 0.0

        state.key_down("KEY_LEFTMETA")
        state.key_down("KEY_V")
        time.sleep(0.05)
        dur = state.recording_duration()
        assert dur >= 0.04  # Allow some tolerance
