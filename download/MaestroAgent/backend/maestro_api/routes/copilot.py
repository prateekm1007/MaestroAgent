"""
Maestro Live Copilot — WebSocket transcription endpoint.

Receives audio chunks from the browser extension, transcribes them
(Whisper local or OpenAI fallback), and returns transcript chunks
to the extension for live display.

Phase 2 scope: audio reception + transcription + transcript streaming.
Phase 4 will add live intelligence (objection/commitment/whisper/pattern).
Phase 5 will add post-call summary.

Consent: the backend trusts the extension's consent state (the extension
is the consent authority). The backend does NOT record audio — it
transcribes in-memory and discards the audio after transcription.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class CopilotSession:
    """Per-connection session state for a Live Copilot WebSocket."""

    def __init__(self, websocket: WebSocket) -> None:
        self.ws = websocket
        self.session_id = f"copilot-{int(time.time() * 1000)}"
        self.transcript_chunks: list[dict[str, Any]] = []
        self.start_time = time.time()
        self.is_capturing = False

    async def send_json(self, data: dict) -> None:
        await self.ws.send_json(data)

    async def receive_loop(self) -> None:
        """Receive audio chunks and transcript requests from the extension."""
        try:
            while True:
                message = await self.ws.receive()

                if message["type"] == "websocket.disconnect":
                    break

                if "bytes" in message and message["bytes"]:
                    # Binary audio chunk: [8 bytes timestamp][audio data]
                    data = message["bytes"]
                    if len(data) <= 8:
                        continue
                    timestamp = int.from_bytes(data[:8], "little")
                    audio_data = data[8:]
                    await self._process_audio(audio_data, timestamp)

                elif "text" in message and message["text"]:
                    # JSON control message
                    try:
                        msg = json.loads(message["text"])
                        await self._handle_control_message(msg)
                    except json.JSONDecodeError:
                        logger.warning("Copilot: invalid JSON message")

        except WebSocketDisconnect:
            logger.info(f"Copilot session {self.session_id} disconnected")
        except Exception as e:
            logger.error(f"Copilot session {self.session_id} error: {e}")
        finally:
            await self._on_disconnect()

    async def _handle_control_message(self, msg: dict) -> None:
        """Handle JSON control messages from the extension."""
        msg_type = msg.get("type", "")

        if msg_type == "CAPTURE_STOPPED":
            self.is_capturing = False
            logger.info(f"Copilot {self.session_id}: capture stopped")

        elif msg_type == "CAPTURE_STARTED":
            self.is_capturing = True
            logger.info(f"Copilot {self.session_id}: capture started")

    async def _process_audio(self, audio_data: bytes, timestamp: int) -> None:
        """Transcribe audio chunk and send transcript back to extension.

        Phase 2: uses a stub transcription (returns a placeholder).
        Phase 2.5 (when Whisper is available): uses whisper.cpp for real STT.
        """
        # Phase 2 stub: acknowledge receipt
        # In production, this calls the transcription service:
        #   transcript = await transcribe_audio(audio_data)
        # For now, send a heartbeat so the extension knows the backend is alive
        await self.send_json({
            "type": "AUDIO_RECEIVED",
            "timestamp": timestamp,
            "bytes": len(audio_data),
            "session_id": self.session_id,
        })

        # When transcription is available, send transcript chunks:
        # await self.send_json({
        #     "type": "TRANSCRIPT_CHUNK",
        #     "speaker": speaker,
        #     "text": transcript_text,
        #     "trigger_words": detected_triggers,
        #     "timestamp": timestamp,
        # })

    async def _on_disconnect(self) -> None:
        """Clean up when the WebSocket disconnects (call ended)."""
        duration = time.time() - self.start_time
        logger.info(
            f"Copilot session {self.session_id} ended: "
            f"{duration:.1f}s, {len(self.transcript_chunks)} chunks"
        )
        # Phase 5: trigger post-call summary generation here


@router.websocket("/ws/copilot")
async def copilot_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for the Live Copilot extension.

    Protocol:
      - Extension connects: ws://localhost:8000/ws/copilot
      - Extension sends binary audio chunks (8-byte timestamp header + audio)
      - Extension sends JSON control messages (CAPTURE_STARTED, CAPTURE_STOPPED)
      - Backend sends JSON: AUDIO_RECEIVED, TRANSCRIPT_CHUNK, SUGGESTION, SUMMARY

    Consent: the backend trusts the extension's consent state. The extension
    is the consent authority. The backend does not record audio — it
    transcribes in-memory and discards audio after transcription.
    """
    await websocket.accept()
    session = CopilotSession(websocket)
    logger.info(f"Copilot session started: {session.session_id}")

    # Send session info to the extension
    await session.send_json({
        "type": "SESSION_STARTED",
        "session_id": session.session_id,
        "server_time": int(time.time() * 1000),
    })

    await session.receive_loop()
