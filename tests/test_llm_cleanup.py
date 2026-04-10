import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import voice_input_lib as vi

DEFAULT_LLM_SETTINGS = {
    "llm_url": "http://localhost:11434/api/generate",
    "llm_model": "qwen2.5:7b",
    "llm_prompt": "Clean up this speech-to-text transcription.",
}


class TestLlmCleanup:
    def test_empty_text_returns_empty(self):
        result = vi.llm_cleanup("", DEFAULT_LLM_SETTINGS)
        assert result == ""

    @patch("voice_input_lib.requests.post")
    def test_successful_cleanup(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "Hello, how are you?"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = vi.llm_cleanup("hello how are you", DEFAULT_LLM_SETTINGS)
        assert result == "Hello, how are you?"

        # Verify the request was made correctly
        call_args = mock_post.call_args
        assert call_args[0][0] == DEFAULT_LLM_SETTINGS["llm_url"]
        body = call_args[1]["json"]
        assert body["model"] == "qwen2.5:7b"
        assert "hello how are you" in body["prompt"]
        assert body["stream"] is False

    @patch("voice_input_lib.requests.post")
    def test_fallback_on_error(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")

        result = vi.llm_cleanup("hello world", DEFAULT_LLM_SETTINGS)
        assert result == "hello world"  # Returns original text

    @patch("voice_input_lib.requests.post")
    def test_fallback_on_empty_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": ""}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = vi.llm_cleanup("hello world", DEFAULT_LLM_SETTINGS)
        assert result == "hello world"  # Returns original text

    @patch("voice_input_lib.requests.post")
    def test_prompt_includes_transcription(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "cleaned"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        vi.llm_cleanup("test input text", DEFAULT_LLM_SETTINGS)

        body = mock_post.call_args[1]["json"]
        assert "test input text" in body["prompt"]
        assert DEFAULT_LLM_SETTINGS["llm_prompt"] in body["prompt"]
