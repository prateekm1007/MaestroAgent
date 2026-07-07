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

        Phase 2: stub transcription.
        Phase 4: live intelligence engine processes transcript chunks.
        """
        # Phase 2 stub: acknowledge receipt
        await self.send_json({
            "type": "AUDIO_RECEIVED",
            "timestamp": timestamp,
            "bytes": len(audio_data),
            "session_id": self.session_id,
        })

        # Phase 4: when transcription is available, process transcript chunks
        # through the LiveIntelligenceEngine and send suggestion cards.
        # For now, the engine is wired but waiting for real transcription.
        # When transcript_text is available:
        #   cards = self.live_engine.process_transcript(transcript_text, speaker, entity)
        #   for card in cards:
        #       await self.send_json({"type": "SUGGESTION", "card": card.to_dict()})

    async def process_transcript_chunk(self, text: str, speaker: str = "", entity: str | None = None):
        """Phase 4: process a transcript chunk through the live intelligence engine.

        Called when the transcription service produces a transcript chunk.
        Generates suggestion cards and sends them to the extension.
        """
        if not hasattr(self, "live_engine"):
            try:
                from maestro_oem.live_intelligence import LiveIntelligenceEngine
                from maestro_api.oem_state import oem_state
                self.live_engine = LiveIntelligenceEngine(oem_state)
            except Exception as e:
                logger.warning(f"Copilot: could not init live engine: {e}")
                return

        cards = self.live_engine.process_transcript(text, speaker, entity)
        for card in cards:
            await self.send_json({
                "type": "SUGGESTION",
                "card": card.to_dict(),
            })

        # Also send the transcript chunk for display
        await self.send_json({
            "type": "TRANSCRIPT_CHUNK",
            "speaker": speaker,
            "text": text,
            "trigger_words": self._extract_trigger_words(text),
            "timestamp": int(time.time() * 1000),
        })

    def _extract_trigger_words(self, text: str) -> list[str]:
        """Extract words that triggered detection (for highlighting)."""
        triggers = []
        text_lower = text.lower()
        for word in ["budget", "pricing", "expensive", "commit", "promise", "deliver", "by friday", "by next"]:
            if word in text_lower:
                triggers.append(word)
        return triggers

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
