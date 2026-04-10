# voice-input

A local, hotkey-triggered speech-to-text daemon for Wayland. Hold a key combo, speak, release — your words appear in the focused text field. No cloud APIs; everything runs on your machine.

This application was written entirely by an LLM.

## Requirements

- Linux with Wayland (tested on Pop!_OS / COSMIC)
- Python 3.12+
- PipeWire (for audio cues)
- A working microphone

## Installation

```bash
git clone <this-repo> ~/Code/voice-input
cd ~/Code/voice-input
./install.sh
```

The install script will:
1. Install system packages (`wl-clipboard`, `wtype`, `libportaudio2`)
2. Add your user to the `input` group (requires logout/login)
3. Create a Python venv and install dependencies
4. Generate audio cue files
5. Install a launcher at `~/.local/bin/voice-input`
6. Install a systemd user service for auto-start

**After install, log out and back in** for the `input` group membership to take effect.

## Usage

### Starting the daemon

```bash
# Run in foreground (useful for first-time testing / seeing logs)
voice-input

# Or use the systemd service
systemctl --user start voice-input
systemctl --user status voice-input
```

### Recording

1. **Hold Ctrl+Super** — you hear a short beep; recording starts
2. **Speak** your instruction
3. **Release Ctrl+Super** — you hear a lower beep; transcription begins
4. After 1-3 seconds, the transcribed text is typed into the focused field
5. A chirp confirms insertion is complete

### LLM cleanup toggle

**Tap Ctrl+Super+Shift** to toggle LLM-based post-processing on or off.

- Ascending tone = LLM cleanup ON
- Descending tone = LLM cleanup OFF

When enabled, transcriptions are sent through a local Ollama model (default: `qwen2.5:7b`) to fix punctuation, capitalization, and mishearings. Adds ~1-3 seconds of latency.

The toggle state is persisted in `settings.json`.

### If auto-type doesn't work

If `wtype` isn't available or working, the text is still copied to your clipboard. Just press **Ctrl+V** to paste manually.

## Configuration

Edit `settings.json` in the project root. See [SETTINGS.md](SETTINGS.md) for all available options.

If `settings.json` doesn't exist, the daemon uses `settings.defaults.json`.

## Testing

### Automated tests

```bash
# Run all unit/integration tests (fast, no hardware needed)
./venv/bin/pytest tests/ --ignore=tests/test_transcription.py -v

# Run transcription integration test (downloads tiny model on first run)
./venv/bin/pytest tests/test_transcription.py -v
```

### Manual pipeline test

```bash
# Record 3 seconds and transcribe (default)
./test-manual.sh

# Record 5 seconds
./test-manual.sh 5

# Record 3 seconds with LLM cleanup
./test-manual.sh --llm
```

## Troubleshooting

**"No keyboard devices found"**
- You're not in the `input` group. Run `groups` to check. If missing: `sudo usermod -aG input $USER` then log out/in.

**Recording works but no text appears in the field**
- If running as a systemd service, ensure `WAYLAND_DISPLAY` is set in the service file (the install script does this automatically)
- Check if `wtype` is installed: `which wtype`
- Try pasting manually with Ctrl+V (text should be on your clipboard)
- Set `"auto_paste": false` in settings.json to disable auto-type

**Transcription is slow**
- Switch to a smaller model in settings.json: `"whisper_model": "tiny"` or `"base"`
- The `small` model is the default balance of speed and accuracy on CPU

**LLM cleanup fails**
- Ensure Ollama is running: `ollama list`
- Check the model is available: `ollama run qwen2.5:7b "test"`
- The daemon falls back to raw transcription if LLM cleanup fails

**No sound cues**
- Ensure PipeWire is running: `pw-cli info`
- Check that WAV files exist in `sounds/` — regenerate with `voice-input --generate-sounds`
