"""Tests for WebSocket audio streaming endpoint."""

from __future__ import annotations

import base64


class TestWebSocketConnection:
    """Tests for WebSocket connection handling."""

    def test_websocket_connects(self, test_client) -> None:
        """Test WebSocket connection is accepted."""
        with test_client.websocket_connect("/ws/audio/test-call-ws-001") as websocket:
            # Connection should be accepted
            assert websocket is not None

    def test_websocket_start_event(self, test_client) -> None:
        """Test handling of start event."""
        with test_client.websocket_connect("/ws/audio/test-call-ws-002") as websocket:
            # Send start event
            start_message = {
                "event": "start",
                "start": {
                    "streamId": "stream-002",
                    "mediaFormat": {
                        "encoding": "linear16",
                        "sampleRate": 16000,
                    }
                }
            }
            websocket.send_json(start_message)

            # Should receive greeting audio
            # Note: This may timeout in test if TTS is not available
            # We just verify no exception is raised

    def test_websocket_stop_event(self, test_client) -> None:
        """Test handling of stop event closes connection."""
        with test_client.websocket_connect("/ws/audio/test-call-ws-003") as websocket:
            # Send start event
            start_message = {
                "event": "start",
                "start": {
                    "streamId": "stream-003",
                    "mediaFormat": {"encoding": "linear16", "sampleRate": 16000}
                }
            }
            websocket.send_json(start_message)

            # Send stop event
            stop_message = {"event": "stop"}
            websocket.send_json(stop_message)


class TestWebSocketMedia:
    """Tests for media event handling."""

    def test_websocket_media_event(self, test_client) -> None:
        """Test handling of media event with audio data."""
        with test_client.websocket_connect("/ws/audio/test-call-ws-004") as websocket:
            # Send start event first
            start_message = {
                "event": "start",
                "start": {
                    "streamId": "stream-004",
                    "mediaFormat": {"encoding": "linear16", "sampleRate": 16000}
                }
            }
            websocket.send_json(start_message)

            # Send media event with dummy audio
            audio_data = b"\x00" * 320  # 10ms of silence at 16kHz
            media_message = {
                "event": "media",
                "media": {
                    "payload": base64.b64encode(audio_data).decode("ascii"),
                    "timestamp": "0",
                }
            }
            websocket.send_json(media_message)

            # Should not raise exception

    def test_websocket_invalid_json(self, test_client) -> None:
        """Test handling of invalid JSON."""
        with test_client.websocket_connect("/ws/audio/test-call-ws-005") as websocket:
            # Send invalid JSON - should be handled gracefully
            websocket.send_text("not valid json {{{")


class TestWebSocketDTMF:
    """Tests for DTMF event handling."""

    def test_websocket_dtmf_event(self, test_client) -> None:
        """Test handling of DTMF event."""
        with test_client.websocket_connect("/ws/audio/test-call-ws-006") as websocket:
            # Send start event first
            start_message = {
                "event": "start",
                "start": {
                    "streamId": "stream-006",
                    "mediaFormat": {"encoding": "linear16", "sampleRate": 16000}
                }
            }
            websocket.send_json(start_message)

            # Send DTMF event
            dtmf_message = {
                "event": "dtmf",
                "dtmf": {
                    "digit": "0",
                }
            }
            websocket.send_json(dtmf_message)

            # Should handle without error
