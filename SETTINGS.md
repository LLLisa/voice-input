# Settings Reference

Edit `settings.json` in the project root. Any field you omit falls back to the default from `settings.defaults.json`.

## All settings

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hotkey_record` | `string[]` | `["KEY_LEFTCTRL", "KEY_LEFTMETA"]` | evdev key names for the hold-to-record combo. See `/usr/include/linux/input-event-codes.h` for all key names. |
| `hotkey_toggle_llm` | `string[]` | `["KEY_LEFTCTRL", "KEY_LEFTMETA", "KEY_LEFTSHIFT"]` | evdev key names for the LLM toggle tap combo. |
| `whisper_model` | `string` | `"small"` | Whisper model size. Options: `tiny`, `base`, `small`, `medium`, `large-v3`. Larger = more accurate but slower. |
| `whisper_compute_type` | `string` | `"int8"` | Quantization type. Options: `int8`, `float16`, `float32`. `int8` is fastest on CPU. |
| `language` | `string` | `"en"` | Language hint for Whisper. Set to `null` for auto-detection (slower). |
| `llm_enabled` | `bool` | `false` | Whether LLM cleanup is on at startup. Toggled at runtime with the toggle hotkey. |
| `llm_model` | `string` | `"qwen2.5:7b"` | Ollama model name for cleanup. |
| `llm_url` | `string` | `"http://localhost:11434/api/generate"` | Ollama API endpoint. |
| `llm_prompt` | `string` | *(see defaults)* | System prompt sent to the LLM along with the transcription. |
| `min_duration` | `number` | `0.5` | Minimum recording length in seconds. Shorter recordings are discarded (prevents accidental taps). |
| `sample_rate` | `int` | `16000` | Audio sample rate in Hz. 16000 is Whisper's native rate. Valid: `8000`, `16000`, `22050`, `44100`, `48000`. |
| `auto_paste` | `bool` | `true` | Automatically type text via wtype after transcription. If `false`, text is only copied to clipboard. |
| `audio_cues` | `bool` | `true` | Play sound effects for recording start/stop/done and LLM toggle. |

## Example: minimal override

```json
{
  "whisper_model": "medium",
  "llm_enabled": true,
  "auto_paste": false
}
```

This uses the `medium` model, starts with LLM cleanup on, and copies to clipboard without auto-pasting.
