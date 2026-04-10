#!/usr/bin/env python3
"""voice-input: hold-to-speak local speech-to-text daemon.

Listens for a hotkey combo via evdev, records audio while held,
transcribes with faster-whisper, optionally cleans up via a local LLM,
and pastes the result into the focused text field.
"""

import argparse
import json
import logging
import os
import re
import signal
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import evdev
import numpy as np
import requests
import sounddevice as sd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DEFAULTS_PATH = BASE_DIR / "settings.defaults.json"
SETTINGS_PATH = BASE_DIR / "settings.json"
SOUNDS_DIR = BASE_DIR / "sounds"

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger("voice-input")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def load_settings() -> dict:
    """Load settings, merging user overrides on top of defaults."""
    with open(DEFAULTS_PATH) as f:
        defaults = json.load(f)

    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH) as f:
            user = json.load(f)
        # Merge: user values override defaults
        merged = {**defaults, **user}
    else:
        merged = defaults

    return merged


VALID_MODELS = {"tiny", "base", "small", "medium", "large-v3"}
VALID_COMPUTE = {"int8", "float16", "float32"}


def validate_settings(s: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors = []
    if s.get("whisper_model") not in VALID_MODELS:
        errors.append(f"whisper_model must be one of {VALID_MODELS}")
    if s.get("whisper_compute_type") not in VALID_COMPUTE:
        errors.append(f"whisper_compute_type must be one of {VALID_COMPUTE}")
    if not isinstance(s.get("min_duration"), (int, float)) or s["min_duration"] < 0:
        errors.append("min_duration must be a non-negative number")
    if s.get("sample_rate") not in (8000, 16000, 22050, 44100, 48000):
        errors.append("sample_rate must be 8000, 16000, 22050, 44100, or 48000")
    for key in ("hotkey_record", "hotkey_toggle_llm"):
        val = s.get(key)
        if not isinstance(val, list) or not all(isinstance(k, str) for k in val):
            errors.append(f"{key} must be a list of evdev key name strings")
    return errors


# ---------------------------------------------------------------------------
# Audio cues
# ---------------------------------------------------------------------------
def _generate_tone(freq: float, duration: float, sample_rate: int = 44100) -> np.ndarray:
    """Generate a sine wave tone."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # Apply a short fade-in/out to avoid clicks
    tone = np.sin(2 * np.pi * freq * t).astype(np.float32)
    fade = min(int(sample_rate * 0.01), len(tone) // 2)
    tone[:fade] *= np.linspace(0, 1, fade)
    tone[-fade:] *= np.linspace(1, 0, fade)
    return tone


def generate_sounds():
    """Generate WAV sound cues if they don't exist."""
    from scipy.io import wavfile

    sr = 44100
    sounds = {
        "start.wav": _generate_tone(880, 0.15, sr),       # A5 — short high beep
        "stop.wav": _generate_tone(440, 0.15, sr),         # A4 — lower beep
        "done.wav": np.concatenate([                        # two-tone chirp
            _generate_tone(660, 0.1, sr),
            _generate_tone(880, 0.1, sr),
        ]),
        "llm_on.wav": np.concatenate([                      # ascending
            _generate_tone(440, 0.1, sr),
            _generate_tone(660, 0.1, sr),
            _generate_tone(880, 0.1, sr),
        ]),
        "llm_off.wav": np.concatenate([                     # descending
            _generate_tone(880, 0.1, sr),
            _generate_tone(660, 0.1, sr),
            _generate_tone(440, 0.1, sr),
        ]),
    }

    SOUNDS_DIR.mkdir(exist_ok=True)
    for name, data in sounds.items():
        path = SOUNDS_DIR / name
        if not path.exists():
            # Convert float32 [-1,1] to int16
            int_data = (data * 32767).astype(np.int16)
            wavfile.write(str(path), sr, int_data)
            log.info("Generated %s", path)


def play_sound(name: str, settings: dict):
    """Play a sound cue in a background thread (non-blocking)."""
    if not settings.get("audio_cues", True):
        return
    path = SOUNDS_DIR / name
    if not path.exists():
        return

    def _play():
        try:
            subprocess.run(
                ["pw-play", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    threading.Thread(target=_play, daemon=True).start()


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------
class Transcriber:
    """Lazy-loaded faster-whisper model wrapper."""

    def __init__(self, settings: dict):
        self._settings = settings
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        model_size = self._settings["whisper_model"]
        compute_type = self._settings["whisper_compute_type"]
        log.info("Loading Whisper model '%s' (compute=%s) ...", model_size, compute_type)
        self._model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
        log.info("Model loaded.")

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcribe a numpy float32 audio array. Returns text."""
        self._ensure_model()

        # faster-whisper expects float32, mono, any sample rate (it resamples)
        segments, info = self._model.transcribe(
            audio,
            language=self._settings.get("language"),
            beam_size=5,
            vad_filter=True,
            initial_prompt='Commands: "begin spell" and "end spell".',
        )
        text = " ".join(seg.text.strip() for seg in segments)
        return text.strip()


# ---------------------------------------------------------------------------
# LLM cleanup
# ---------------------------------------------------------------------------
def llm_cleanup(text: str, settings: dict) -> str:
    """Send transcription through Ollama for cleanup. Returns cleaned text."""
    if not text:
        return text

    try:
        resp = requests.post(
            settings["llm_url"],
            json={
                "model": settings["llm_model"],
                "prompt": f"{settings['llm_prompt']}\n\nTranscription: {text}",
                "stream": False,
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json().get("response", "").strip()
        return result if result else text
    except Exception as e:
        log.warning("LLM cleanup failed, using raw transcription: %s", e)
        return text


# ---------------------------------------------------------------------------
# Spelling mode
# ---------------------------------------------------------------------------
# Map spoken words to characters.  Order matters: longer phrases first so that
# "upper <letter>" is matched before the bare letter.
_SPELL_SPECIAL: dict[str, str] = {
    "space": " ",
    "hyphen": "-",
    "dash": "-",
    "underscore": "_",
    "dot": ".",
    "period": ".",
    "comma": ",",
    "colon": ":",
    "semicolon": ";",
    "slash": "/",
    "backslash": "\\",
    "at": "@",
    "hash": "#",
    "pound": "#",
    "dollar": "$",
    "percent": "%",
    "ampersand": "&",
    "and": "&",
    "star": "*",
    "asterisk": "*",
    "plus": "+",
    "equals": "=",
    "equal": "=",
    "exclamation": "!",
    "bang": "!",
    "question": "?",
    "tilde": "~",
    "caret": "^",
    "pipe": "|",
    "open paren": "(",
    "close paren": ")",
    "open bracket": "[",
    "close bracket": "]",
    "open brace": "{",
    "close brace": "}",
    "less than": "<",
    "greater than": ">",
    "quote": "'",
    "double quote": '"',
    "apostrophe": "'",
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}

# Phonetic / homophone map for single letters
_SPELL_LETTERS: dict[str, str] = {
    "a": "a", "ay": "a", "eh": "a",
    "b": "b", "be": "b", "bee": "b",
    "c": "c", "see": "c", "sea": "c",
    "d": "d", "de": "d", "dee": "d",
    "e": "e", "ee": "e",
    "f": "f", "ef": "f", "eff": "f",
    "g": "g", "ge": "g", "gee": "g",
    "h": "h", "aitch": "h",
    "i": "i", "eye": "i",
    "j": "j", "jay": "j",
    "k": "k", "kay": "k",
    "l": "l", "el": "l", "ell": "l",
    "m": "m", "em": "m",
    "n": "n", "en": "n",
    "o": "o", "oh": "o",
    "p": "p", "pe": "p", "pee": "p",
    "q": "q", "queue": "q", "cue": "q",
    "r": "r", "ar": "r", "are": "r",
    "s": "s", "es": "s", "ess": "s",
    "t": "t", "te": "t", "tea": "t", "tee": "t",
    "u": "u", "you": "u",
    "v": "v", "ve": "v", "vee": "v",
    "w": "w", "double you": "w", "double u": "w",
    "x": "x", "ex": "x",
    "y": "y", "why": "y", "wie": "y",
    "z": "z", "ze": "z", "zee": "z", "zed": "z",
}

# Pre-compile: begin/end spell markers (case-insensitive).
# Toggle in/out of spelling mode on each successive match.
_SPELL_MARKER = re.compile(
    r"(?:begin|end)\s+spell\.?",
    re.IGNORECASE,
)


def _spell_segment(segment: str) -> str:
    """Convert a spoken spelling segment into actual characters."""
    # Strip punctuation Whisper adds between letters (commas, hyphens, periods)
    # but preserve words like "space", "hyphen", "dot" etc.
    segment = re.sub(r"[,\-.\;:!?]+", " ", segment)
    result = []
    words = segment.lower().split()
    i = 0
    while i < len(words):
        matched = False
        # Try "upper <letter>" for capitals
        if words[i] == "upper" and i + 1 < len(words):
            letter = _SPELL_LETTERS.get(words[i + 1])
            if letter:
                result.append(letter.upper())
                i += 2
                continue
        # Try multi-word special tokens (up to 3 words)
        for length in (3, 2):
            if i + length <= len(words):
                phrase = " ".join(words[i:i + length])
                if phrase in _SPELL_SPECIAL:
                    result.append(_SPELL_SPECIAL[phrase])
                    i += length
                    matched = True
                    break
                if phrase in _SPELL_LETTERS:
                    result.append(_SPELL_LETTERS[phrase])
                    i += length
                    matched = True
                    break
        if matched:
            continue
        # Single-word lookup
        word = words[i]
        if word in _SPELL_SPECIAL:
            result.append(_SPELL_SPECIAL[word])
        elif word in _SPELL_LETTERS:
            result.append(_SPELL_LETTERS[word])
        else:
            # Unknown token — pass through as-is
            result.append(word)
        i += 1
    return "".join(result)


def process_spelling(text: str) -> str:
    """Process spell-mode blocks in transcribed text.

    Toggles in/out of spelling mode on each successive marker
    (e.g. "begin spell", "end spell", "begin the spell", "king spell").
    """
    parts = _SPELL_MARKER.split(text)
    if len(parts) == 1:
        return text  # no spelling markers

    output = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Even segments are normal text
            output.append(part)
        else:
            # Odd segments are inside spelling mode
            output.append(_spell_segment(part))
    return "".join(output)


# ---------------------------------------------------------------------------
# Text insertion
# ---------------------------------------------------------------------------
def insert_text(text: str, settings: dict):
    """Copy text to clipboard and optionally auto-paste."""
    if not text:
        return

    # Copy to Wayland clipboard
    try:
        subprocess.run(
            ["wl-copy", "--", text],
            check=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        log.error("wl-copy failed: %s", e)
        return

    if not settings.get("auto_paste", True):
        log.info("Text copied to clipboard (auto-paste disabled).")
        return

    # wtype: type the text via Wayland input method protocol
    try:
        time.sleep(0.15)
        subprocess.run(
            ["wtype", "--", text],
            check=True,
            timeout=10,
        )
    except FileNotFoundError:
        log.warning("wtype not found — text is on the clipboard, paste manually.")
    except subprocess.CalledProcessError as e:
        log.warning("wtype failed: %s — text is on the clipboard, paste manually.", e)


# ---------------------------------------------------------------------------
# Audio recorder
# ---------------------------------------------------------------------------
class Recorder:
    """Records audio from the default input device."""

    def __init__(self, sample_rate: int):
        self.sample_rate = sample_rate
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()

    def start(self):
        """Start recording."""
        with self._lock:
            self._chunks = []
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        if status:
            log.debug("Audio status: %s", status)
        self._chunks.append(indata.copy())

    def stop(self) -> np.ndarray | None:
        """Stop recording and return the audio as a 1-D float32 array."""
        with self._lock:
            if self._stream is None:
                return None
            self._stream.stop()
            self._stream.close()
            self._stream = None

            if not self._chunks:
                return None
            audio = np.concatenate(self._chunks, axis=0).flatten()
            return audio


# ---------------------------------------------------------------------------
# Hotkey state machine
# ---------------------------------------------------------------------------
class HotkeyState:
    """
    Tracks which keys are currently held and detects hotkey combos.

    States:
      IDLE       — waiting for hotkey
      RECORDING  — hotkey held, audio recording
      PROCESSING — released, transcribing
    """

    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"

    def __init__(self, settings: dict):
        self.record_keys = set(settings["hotkey_record"])
        self.toggle_keys = set(settings["hotkey_toggle_llm"])
        self.held_keys: set[str] = set()
        self.state = self.IDLE
        self._record_start_time: float = 0.0

    def key_down(self, key_name: str) -> str | None:
        """
        Process a key-down event. Returns an action string or None.
        Actions: "start_recording", "toggle_llm"
        """
        self.held_keys.add(key_name)

        if self.state == self.IDLE:
            # Check toggle first (it's a superset of record keys + shift)
            if self.toggle_keys.issubset(self.held_keys):
                return "toggle_llm"
            if self.record_keys.issubset(self.held_keys):
                self.state = self.RECORDING
                self._record_start_time = time.monotonic()
                return "start_recording"

        return None

    def key_up(self, key_name: str) -> str | None:
        """
        Process a key-up event. Returns an action string or None.
        Actions: "stop_recording"
        """
        self.held_keys.discard(key_name)

        if self.state == self.RECORDING:
            # If any of the record keys is released, stop recording
            if not self.record_keys.issubset(self.held_keys):
                elapsed = time.monotonic() - self._record_start_time
                self.state = self.PROCESSING
                return "stop_recording"

        return None

    def recording_duration(self) -> float:
        """How long recording has been active."""
        if self.state != self.RECORDING:
            return 0.0
        return time.monotonic() - self._record_start_time

    def finish_processing(self):
        """Transition back to idle after processing is complete."""
        self.state = self.IDLE


# ---------------------------------------------------------------------------
# evdev keyboard listener
# ---------------------------------------------------------------------------
def find_keyboards() -> list[evdev.InputDevice]:
    """Find all keyboard input devices."""
    keyboards = []
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        caps = dev.capabilities(verbose=True)
        # Check if device has EV_KEY events
        for (ev_type_name, _), keys in caps.items():
            if ev_type_name == "EV_KEY":
                # Check for typical keyboard keys
                key_names = [k[0] if isinstance(k, list) else k for _, k in keys]
                has_keyboard_keys = any(
                    name in str(key_names)
                    for name in ["KEY_A", "KEY_ENTER", "KEY_SPACE"]
                )
                if has_keyboard_keys:
                    keyboards.append(dev)
                break
    return keyboards


def find_keyboards_simple() -> list[evdev.InputDevice]:
    """Find keyboards using a simpler heuristic — has KEY_LEFTCTRL and KEY_LEFTMETA."""
    keyboards = []
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        caps = dev.capabilities()
        ev_key = evdev.ecodes.EV_KEY
        if ev_key in caps:
            key_codes = caps[ev_key]
            has_ctrl = evdev.ecodes.KEY_LEFTCTRL in key_codes
            has_meta = evdev.ecodes.KEY_LEFTMETA in key_codes
            if has_ctrl and has_meta:
                keyboards.append(dev)
    return keyboards


# ---------------------------------------------------------------------------
# Main daemon
# ---------------------------------------------------------------------------
class VoiceInputDaemon:
    """Orchestrates hotkey detection, recording, transcription, and insertion."""

    def __init__(self, settings: dict):
        self.settings = settings
        self.hotkey = HotkeyState(settings)
        self.recorder = Recorder(settings["sample_rate"])
        self.transcriber = Transcriber(settings)
        self.llm_enabled = settings.get("llm_enabled", False)
        self._running = False

    def run(self):
        """Main loop: listen for keyboard events and act on hotkey combos."""
        # Generate sounds if needed
        generate_sounds()

        # Pre-load the whisper model
        log.info("Pre-loading transcription model...")
        self.transcriber._ensure_model()

        keyboards = find_keyboards_simple()
        if not keyboards:
            log.error(
                "No keyboard devices found. "
                "Make sure you're in the 'input' group: sudo usermod -aG input $USER"
            )
            sys.exit(1)

        log.info("Monitoring %d keyboard(s):", len(keyboards))
        for kb in keyboards:
            log.info("  %s (%s)", kb.name, kb.path)
        log.info("LLM cleanup: %s", "ON" if self.llm_enabled else "OFF")
        log.info("Ready — hold %s to record, %s to toggle LLM",
                 "+".join(self.settings["hotkey_record"]),
                 "+".join(self.settings["hotkey_toggle_llm"]))

        self._running = True

        # Use selectors for multi-device listening
        import selectors
        sel = selectors.DefaultSelector()
        for kb in keyboards:
            sel.register(kb, selectors.EVENT_READ)

        try:
            while self._running:
                events = sel.select(timeout=0.1)
                for selector_key, _ in events:
                    dev = selector_key.fileobj
                    try:
                        for event in dev.read():
                            self._handle_event(event)
                    except OSError:
                        # Device disconnected
                        log.warning("Device disconnected: %s", dev.name)
                        sel.unregister(dev)
        except KeyboardInterrupt:
            log.info("Shutting down.")
        finally:
            sel.close()
            for kb in keyboards:
                try:
                    kb.close()
                except Exception:
                    pass

    def _handle_event(self, event):
        """Process a single evdev input event."""
        if event.type != evdev.ecodes.EV_KEY:
            return

        key_event = evdev.categorize(event)
        key_name = evdev.ecodes.KEY.get(event.code)
        if key_name is None:
            return
        # key_name can be a list for keys with aliases
        if isinstance(key_name, list):
            key_name = key_name[0]

        if key_event.keystate == evdev.events.KeyEvent.key_down:
            action = self.hotkey.key_down(key_name)
            if action == "start_recording":
                self._on_start_recording()
            elif action == "toggle_llm":
                self._on_toggle_llm()

        elif key_event.keystate == evdev.events.KeyEvent.key_up:
            action = self.hotkey.key_up(key_name)
            if action == "stop_recording":
                self._on_stop_recording()

    def _on_start_recording(self):
        log.info("Recording...")
        play_sound("start.wav", self.settings)
        self.recorder.start()

    def _on_stop_recording(self):
        play_sound("stop.wav", self.settings)
        audio = self.recorder.stop()

        if audio is None or len(audio) == 0:
            log.warning("No audio captured.")
            self.hotkey.finish_processing()
            return

        duration = len(audio) / self.settings["sample_rate"]
        if duration < self.settings["min_duration"]:
            log.info("Recording too short (%.2fs < %.2fs), ignoring.",
                     duration, self.settings["min_duration"])
            self.hotkey.finish_processing()
            return

        log.info("Recorded %.2fs of audio. Transcribing...", duration)

        # Run transcription + insertion in a thread so we don't block key events
        threading.Thread(
            target=self._process_audio,
            args=(audio,),
            daemon=True,
        ).start()

    def _process_audio(self, audio: np.ndarray):
        try:
            text = self.transcriber.transcribe(audio, self.settings["sample_rate"])
            log.info("Transcribed: %s", text)

            if self.llm_enabled and text:
                log.info("Running LLM cleanup...")
                text = llm_cleanup(text, self.settings)
                log.info("Cleaned: %s", text)

            if text:
                text = process_spelling(text)
                insert_text(text, self.settings)
                play_sound("done.wav", self.settings)
                log.info("Done.")
            else:
                log.warning("No text transcribed.")
        except Exception:
            log.exception("Error during transcription/insertion")
        finally:
            self.hotkey.finish_processing()

    def _on_toggle_llm(self):
        self.llm_enabled = not self.llm_enabled
        state = "ON" if self.llm_enabled else "OFF"
        log.info("LLM cleanup: %s", state)
        sound = "llm_on.wav" if self.llm_enabled else "llm_off.wav"
        play_sound(sound, self.settings)

        # Persist the toggle state
        try:
            if SETTINGS_PATH.exists():
                with open(SETTINGS_PATH) as f:
                    user_settings = json.load(f)
            else:
                user_settings = {}
            user_settings["llm_enabled"] = self.llm_enabled
            with open(SETTINGS_PATH, "w") as f:
                json.dump(user_settings, f, indent=2)
                f.write("\n")
        except Exception:
            log.exception("Failed to persist LLM toggle state")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Voice input daemon")
    parser.add_argument(
        "--generate-sounds", action="store_true",
        help="Generate sound files and exit",
    )
    args = parser.parse_args()

    settings = load_settings()
    errors = validate_settings(settings)
    if errors:
        for e in errors:
            log.error("Settings error: %s", e)
        sys.exit(1)

    if args.generate_sounds:
        generate_sounds()
        return

    daemon = VoiceInputDaemon(settings)

    # Handle SIGTERM gracefully
    def _sigterm(signum, frame):
        log.info("Received SIGTERM, shutting down.")
        daemon._running = False

    signal.signal(signal.SIGTERM, _sigterm)

    daemon.run()


if __name__ == "__main__":
    main()
