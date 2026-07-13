"""
Audio transcription module — pluggable speech-to-text for the Copilot.

Supports multiple transcription providers (configured via env vars):
  1. Wit.ai (free cloud, Meta-owned) — set MAESTRO_WITAI_TOKEN
     Recommended: completely free, no usage limits, cloud-based (scalable).
     Get a free token at https://wit.ai (create app → Settings → Server Access Token)
  2. OpenAI Whisper (local) — `pip install openai-whisper` + set MAESTRO_WHISPER_MODEL
     Not scalable (requires CPU/GPU per instance) but free + offline.
  3. OpenAI Whisper API (cloud) — set MAESTRO_OPENAI_API_KEY
     Paid but high quality.
  4. Google Cloud Speech-to-Text — set MAESTRO_GOOGLE_STT_KEY
     Paid (60 min/month free tier).
  5. Placeholder (default) — returns a clear message that no provider is configured

Priority order: Wit.ai (free + scalable) > Whisper local (free + offline)
> OpenAI cloud (paid) > Google STT (paid) > none

The endpoint POST /api/copilot/transcribe accepts an audio file upload,
calls the configured provider, and returns the transcribed text. The
mobile app uploads recorded audio here, gets text back, then sends that
text through the existing /api/copilot/transcript pipeline.
"""

from __future__ import annotations

import io
import os
import logging
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


def _get_transcription_provider() -> str:
    """Detect which transcription provider is configured.

    Priority: Wit.ai (free + scalable) first, then local Whisper,
    then paid cloud providers.
    """
    if os.environ.get("MAESTRO_WITAI_TOKEN"):
        return "witai"
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

    if provider == "witai":
        return _transcribe_witai(audio_data, filename)
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
                "MAESTRO_WITAI_TOKEN (recommended — free, scalable, cloud-based; "
                "get a token at https://wit.ai), "
                "MAESTRO_WHISPER_MODEL (local Whisper — free but not scalable), "
                "MAESTRO_OPENAI_API_KEY (cloud Whisper API — paid), or "
                "MAESTRO_GOOGLE_STT_KEY (Google Speech-to-Text — paid)."
            ),
        }


def _transcribe_witai(audio_data: bytes, filename: str) -> dict[str, Any]:
    """Transcribe using Wit.ai (free, Meta-owned, cloud-based — scalable).

    Wit.ai is completely free with no usage limits. Just need a server
    access token from https://wit.ai (create app → Settings → Server Access Token).

    API: POST https://api.wit.ai/speech
    Headers: Authorization: Bearer <token>, Content-Type: audio/raw
    Response: JSON with 'text' field

    This is the recommended provider — free, scalable, no server resources.
    """
    token = os.environ.get("MAESTRO_WITAI_TOKEN", "")
    if not token:
        return {
            "text": "",
            "provider": "witai",
            "configured": False,
            "error": "MAESTRO_WITAI_TOKEN not set. Get a free token at https://wit.ai",
        }

    try:
        import urllib.request
        import urllib.error

        # Wit.ai accepts raw audio (wav, m4a, mp3) via POST
        # Content-Type must match the audio format
        ext = os.path.splitext(filename)[1].lower()
        content_types = {
            ".wav": "audio/wav",
            ".m4a": "audio/m4a",
            ".mp3": "audio/mpeg",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
        }
        content_type = content_types.get(ext, "audio/m4a")

        url = "https://api.wit.ai/speech?v=20240304"
        req = urllib.request.Request(
            url,
            data=audio_data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": content_type,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                response_data = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            logger.error(f"Wit.ai HTTP error: {e.code} {error_body[:200]}")
            return {
                "text": "",
                "provider": "witai",
                "configured": True,
                "error": f"Wit.ai API error {e.code}: {error_body[:200]}",
            }

        # Wit.ai returns newline-delimited JSON or a single JSON object
        # Parse the response — may be {"text": "..."} or {"_text": "..."}
        import json
        try:
            # Try parsing as JSON
            result = json.loads(response_data)
            text = result.get("text") or result.get("_text") or ""
            if isinstance(text, list):
                # Some responses return [{"text": "..."}, ...]
                text = " ".join(t if isinstance(t, str) else t.get("text", "") for t in text)
            return {
                "text": text.strip(),
                "provider": "witai",
                "configured": True,
                "error": "",
            }
        except json.JSONDecodeError:
            # Wit.ai sometimes returns newline-delimited JSON
            # Try the last non-empty line
            lines = [l.strip() for l in response_data.split("\n") if l.strip()]
            if lines:
                try:
                    last = json.loads(lines[-1])
                    text = last.get("text") or last.get("_text") or ""
                    return {
                        "text": text.strip(),
                        "provider": "witai",
                        "configured": True,
                        "error": "",
                    }
                except json.JSONDecodeError:
                    pass
            return {
                "text": "",
                "provider": "witai",
                "configured": True,
                "error": f"Could not parse Wit.ai response: {response_data[:200]}",
            }
    except Exception as e:
        logger.error(f"Wit.ai transcription failed: {e}")
        return {
            "text": "",
            "provider": "witai",
            "configured": True,
            "error": f"Transcription failed: {e}",
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
