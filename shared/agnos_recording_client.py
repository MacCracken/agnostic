"""
AGNOS Screen Recording Client — Video Session Streaming.

Provides live video streaming of QA sessions by wrapping the AGNOS screen
recording APIs. Streams frames via SSE to the WebGUI dashboard so observers
can watch browser-based tests in real time.

This module handles the streaming lifecycle; for single screenshots use
:mod:`shared.agnos_screen_client` instead.

Configure via:
- AGNOS_SCREEN_ENABLED: Enable screen recording (default: false)
- AGNOS_AGENT_REGISTRY_URL: Daimon base URL
- AGNOS_AGENT_API_KEY: API key for daimon
"""

import asyncio
import logging
import os
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

AGNOS_PATH_PREFIX = os.getenv("AGNOS_PATH_PREFIX", "/v1")

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


class AgnosRecordingClient:
    """Manages recording sessions and provides frame streaming."""

    def __init__(self) -> None:
        self.enabled = (
            os.getenv("AGNOS_SCREEN_ENABLED", "false").lower() == "true"
            and _HTTPX_AVAILABLE
        )
        self.base_url = os.getenv(
            "AGNOS_AGENT_REGISTRY_URL", "http://localhost:8090"
        )
        self.api_key = os.getenv("AGNOS_AGENT_API_KEY", "")
        self._client: "httpx.AsyncClient | None" = None
        self._client_lock = asyncio.Lock()
        self._active_recordings: dict[str, str] = {}  # session_id → recording_id

        try:
            from shared.resilience import CircuitBreaker

            self._circuit = CircuitBreaker(
                name="agnos_recording", failure_threshold=5, recovery_timeout=60.0
            )
        except ImportError:
            self._circuit = None

    async def _get_client(self) -> "httpx.AsyncClient":
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    headers={"X-API-Key": self.api_key} if self.api_key else {},
                    timeout=15.0,
                )
        return self._client

    def _can_execute(self) -> bool:
        if not self.enabled:
            return False
        if self._circuit and not self._circuit.can_execute():
            return False
        return True

    def _record_success(self) -> None:
        if self._circuit:
            self._circuit.record_success()

    def _record_failure(self) -> None:
        if self._circuit:
            self._circuit.record_failure()

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def start_session_recording(
        self,
        session_id: str,
        *,
        agent_id: str | None = None,
        frame_interval_ms: int = 500,
        max_duration_secs: int = 300,
    ) -> dict[str, Any]:
        """Start recording for a QA session.

        Args:
            session_id: Agnostic QA session identifier.
            agent_id: Optional agent UUID for permission tracking.
            frame_interval_ms: Capture interval (default 500ms for smooth playback).
            max_duration_secs: Max recording duration (default 5 minutes).

        Returns:
            Dict with recording_id and status.
        """
        if not self._can_execute():
            return {"status": "disabled"}

        payload: dict[str, Any] = {
            "target": {"type": "full_screen"},
            "format": "png",
            "frame_interval_ms": frame_interval_ms,
            "max_duration_secs": max_duration_secs,
        }
        if agent_id:
            payload["agent_id"] = agent_id

        try:
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/screen/recording/start",
                json=payload,
            )
            response.raise_for_status()
            self._record_success()
            result = response.json()
            recording_id = result.get("recording_id", "")
            self._active_recordings[session_id] = recording_id
            logger.info(
                "Started recording for session %s (recording_id=%s)",
                session_id,
                recording_id,
            )
            return result
        except Exception as exc:
            self._record_failure()
            logger.warning("Start session recording failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def stop_session_recording(self, session_id: str) -> dict[str, Any]:
        """Stop recording for a QA session."""
        recording_id = self._active_recordings.pop(session_id, None)
        if not recording_id:
            return {"status": "not_found", "session_id": session_id}

        if not self._can_execute():
            return {"status": "disabled"}

        try:
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/screen/recording/{recording_id}/stop",
            )
            response.raise_for_status()
            self._record_success()
            logger.info("Stopped recording for session %s", session_id)
            return response.json()
        except Exception as exc:
            self._record_failure()
            logger.warning("Stop session recording failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    # ------------------------------------------------------------------
    # Frame streaming
    # ------------------------------------------------------------------

    async def stream_frames(
        self,
        session_id: str,
        *,
        poll_interval: float = 0.5,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield frames from an active session recording.

        This async generator polls for new frames and yields them as dicts.
        Use in SSE endpoints to push frames to the browser.

        Args:
            session_id: QA session identifier.
            poll_interval: Seconds between frame polls (default 0.5).

        Yields:
            Frame dicts with sequence, data_base64, width, height, etc.
        """
        recording_id = self._active_recordings.get(session_id)
        if not recording_id or not self._can_execute():
            return

        last_sequence = 0
        client = await self._get_client()

        while session_id in self._active_recordings:
            try:
                response = await client.get(
                    f"{AGNOS_PATH_PREFIX}/screen/recording/{recording_id}/frames",
                    params={"since": last_sequence},
                )
                response.raise_for_status()
                self._record_success()
                data = response.json()
                frames = data.get("frames", [])
                for frame in frames:
                    seq = frame.get("sequence", 0)
                    if seq > last_sequence:
                        last_sequence = seq
                    yield frame
            except Exception as exc:
                self._record_failure()
                logger.debug("Frame poll failed: %s", exc)

            await asyncio.sleep(poll_interval)

    def get_active_sessions(self) -> dict[str, str]:
        """Return dict of session_id → recording_id for active recordings."""
        return dict(self._active_recordings)

    async def close(self) -> None:
        # Stop all active recordings
        for session_id in list(self._active_recordings):
            await self.stop_session_recording(session_id)
        if self._client and not self._client.is_closed:
            await self._client.aclose()


agnos_recording = AgnosRecordingClient()
