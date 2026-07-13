"""
Audio transcription module — pluggable speech-to-text for the Copilot.

Supports multiple transcription providers (configured via env vars):
  1. OpenAI Whisper (local) — `pip install openai-whisper` + set MAESTRO_WHISPER_MODEL
  2. OpenAI Whisper API (cloud) — set MAESTRO_OPENAI_API_KEY
  3. Google Cloud Speech-to-Text — set MAESTRO_GOOGLE_STT_KEY
  4. Placeholder (default) — returns a clear message that no provider is configured

The endpoint POST /api/copilot/transcribe accepts an audio file upload,
calls the configured provider, and returns the transcribed text. The
mobile app uploads recorded audio here, gets text back, then sends that
text through the existing /api/copilot/transcript pipeline.

This is the same pattern as the connectors: real infrastructure, honest
about what's configured. When no provider is set, the endpoint returns
a 200 with a clear "transcription not configured" message — the mobile
app shows this to the user rather than silently failing.
"""

from __future__ import annotations

import io
import os
import logging
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


def _get_transcription_provider() -> str:
    """Detect which transcription provider is configured."""
    if os.environ.get("MAESTRO_WHISPER_MODEL"):
        return "whisper-local"
    if os.environ.get("MAESTRO_OPENAI_API_KEY"):
        return "openai-cloud"
    if os.environ.get("MAESTRO_GOOGLE_STT_KEY"):
        return "google-stt"
    return "none"


def is_transcription_configured() -> bool:
    """Check if any real transcription provider is configured."""
    return _get_transcription_provider() != "none"


def transcribe_audio(audio_data: bytes, filename: str = "audio.m4a") -> dict[str, Any]:
    """Transcribe audio data using the configured provider.

    Args:
        audio_data: raw audio file bytes (m4a, wav, mp3, etc.)
        filename: original filename (for extension detection)

    Returns: {
        text: str — the transcribed text (empty if no provider)
        provider: str — which provider was used
        configured: bool — whether a real provider was available
        error: str — error message if transcription failed
    }
    """
    provider = _get_transcription_provider()

    if provider == "whisper-local":
        return _transcribe_whisper_local(audio_data, filename)
    elif provider == "openai-cloud":
        return _transcribe_openai_cloud(audio_data, filename)
    elif provider == "google-stt":
        return _transcribe_google_stt(audio_data, filename)
    else:
        return {
            "text": "",
            "provider": "none",
            "configured": False,
            "error": (
                "No transcription provider configured. Set one of: "
                "MAESTRO_WHISPER_MODEL (local Whisper), "
                "MAESTRO_OPENAI_API_KEY (cloud Whisper API), or "
                "MAESTRO_GOOGLE_STT_KEY (Google Speech-to-Text)."
            ),
        }


def _transcribe_whisper_local(audio_data: bytes, filename: str) -> dict[str, Any]:
    """Transcribe using local OpenAI Whisper (pip install openai-whisper)."""
    try:
        import whisper
    except ImportError:
        return {
            "text": "",
            "provider": "whisper-local",
            "configured": True,
            "error": "MAESTRO_WHISPER_MODEL is set but `openai-whisper` is not installed. Run: pip install openai-whisper",
        }

    model_name = os.environ.get("MAESTRO_WHISPER_MODEL", "base")
    try:
        model = whisper.load_model(model_name)
        # Write to temp file (Whisper needs a file path)
        ext = os.path.splitext(filename)[1] or ".m4a"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(audio_data)
            temp_path = f.name
        try:
            result = model.transcribe(temp_path)
            return {
                "text": result.get("text", "").strip(),
                "provider": f"whisper-local ({model_name})",
                "configured": True,
                "error": "",
            }
        finally:
            os.unlink(temp_path)
    except Exception as e:
        logger.error(f"Whisper local transcription failed: {e}")
        return {
            "text": "",
            "provider": "whisper-local",
            "configured": True,
            "error": f"Transcription failed: {e}",
        }


def _transcribe_openai_cloud(audio_data: bytes, filename: str) -> dict[str, Any]:
    """Transcribe using OpenAI's Whisper API (cloud)."""
    try:
        import httpx
    except ImportError:
        return {
            "text": "",
            "provider": "openai-cloud",
            "configured": True,
            "error": "httpx not installed",
        }

    api_key = os.environ.get("MAESTRO_OPENAI_API_KEY", "")
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, io.BytesIO(audio_data))},
                data={"model": "whisper-1"},
            )
            response.raise_for_status()
            result = response.json()
            return {
                "text": result.get("text", "").strip(),
                "provider": "openai-cloud (whisper-1)",
                "configured": True,
                "error": "",
            }
    except Exception as e:
        logger.error(f"OpenAI cloud transcription failed: {e}")
        return {
            "text": "",
            "provider": "openai-cloud",
            "configured": True,
            "error": f"Transcription failed: {e}",
        }


def _transcribe_google_stt(audio_data: bytes, filename: str) -> dict[str, Any]:
    """Transcribe using Google Cloud Speech-to-Text."""
    # Placeholder for Google STT — requires google-cloud-speech package
    # Implementation would use speech.SyncRecognizeRequest with the audio bytes
    return {
        "text": "",
        "provider": "google-stt",
        "configured": True,
        "error": "Google STT provider not yet implemented. Use whisper-local or openai-cloud.",
    }
