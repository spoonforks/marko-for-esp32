from __future__ import annotations

import os
import asyncio
import json
import struct
import wave
from pathlib import Path
from unittest.mock import AsyncMock

import av
from fastapi.testclient import TestClient


os.environ.setdefault("MARKO_PROVISIONING_KEY", "test-provisioning-key-00000000000000000000")
os.environ.setdefault("MARKO_DEVICE_AUTH_TOKEN", "test-device-token-0000000000000000000000")
os.environ.setdefault("MARKO_PUBLIC_BASE_URL", "https://example.ts.net")

import app.device_main as device_main
from app.device_main import SECURITY, app
from app.services.device_security import DeviceSecurity
from app.services.ogg_opus import wav_to_opus_packets, write_ogg_opus


def test_health_contains_no_configuration() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_provisioning_rejects_missing_and_bad_keys() -> None:
    client = TestClient(app)
    assert client.post("/api/device/provision").status_code == 401
    assert client.post("/api/device/provision", headers={"X-Marko-Provisioning-Key": "bad"}).status_code == 401


def test_provisioning_returns_xiaozhi_v1_configuration() -> None:
    response = TestClient(app).post(
        "/api/device/provision",
        headers={"X-Marko-Provisioning-Key": SECURITY.provisioning_key},
    )
    assert response.status_code == 200
    assert response.json() == {
        "websocket": {
            "url": "wss://example.ts.net/api/device/ws",
            "token": SECURITY.device_auth_token,
            "version": 1,
        },
        "audio": {
            "format": "opus",
            "sample_rate": 16000,
            "channels": 1,
            "frame_duration_ms": 60,
        },
    }


def test_status_allows_only_bearer_header() -> None:
    client = TestClient(app)
    assert client.get("/api/device/status").status_code == 401
    assert client.get("/api/device/status?token=" + SECURITY.device_auth_token).status_code == 401
    response = client.get("/api/device/status", headers={"Authorization": "Bearer " + SECURITY.device_auth_token})
    assert response.status_code == 200
    assert response.json()["protocol"] == "xiaozhi-websocket-v1"


def test_websocket_handshake_and_malformed_json() -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/device/ws", headers={"Authorization": "Bearer " + SECURITY.device_auth_token}) as socket:
        socket.send_text("not json")
        assert socket.receive_json()["status"] == "Protocol error"
        socket.send_json({"type": "hello", "version": 1, "transport": "websocket"})
        hello = socket.receive_json()
        assert hello["type"] == "hello"
        assert hello["audio_params"]["sample_rate"] == 16000


def test_recording_limit_stops_before_accepting_an_extra_packet(monkeypatch) -> None:
    received: list[list[bytes]] = []

    async def fake_handle(websocket, session_id, packets, history) -> None:
        received.append(list(packets))
        await websocket.send_json({"type": "limit-test"})

    monkeypatch.setattr(device_main, "MAX_RECORDING_PACKETS", 2)
    monkeypatch.setattr(device_main, "handle_recording", fake_handle)
    client = TestClient(app)
    with client.websocket_connect(
        "/api/device/ws",
        headers={"Authorization": "Bearer " + SECURITY.device_auth_token},
    ) as socket:
        socket.send_json({"type": "listen", "state": "start"})
        socket.send_bytes(b"one")
        socket.send_bytes(b"two")
        socket.send_bytes(b"not-accepted")
        assert socket.receive_json() == {"type": "limit-test"}
    assert received == [[b"one", b"two"]]


def test_response_messages_and_audio_are_ordered(monkeypatch, tmp_path: Path) -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.events: list[tuple[str, object]] = []

        async def send_text(self, value: str) -> None:
            self.events.append(("json", json.loads(value)))

        async def send_bytes(self, value: bytes) -> None:
            self.events.append(("bytes", value))

    async def fake_turn(**_kwargs):
        return {
            "transcript": "hello",
            "reply_text": "hi",
            "response_audio_path": tmp_path / "reply.wav",
        }

    socket = FakeSocket()
    monkeypatch.setattr(device_main, "write_ogg_opus", lambda **_kwargs: None)
    monkeypatch.setattr(device_main, "process_assistant_turn", fake_turn)
    monkeypatch.setattr(device_main, "wav_to_opus_packets", lambda _path: [b"a", b"b"])
    monkeypatch.setattr(device_main.asyncio, "sleep", AsyncMock())
    asyncio.run(device_main.handle_recording(socket, "session", [b"input"], []))  # type: ignore[arg-type]

    assert [event[0] for event in socket.events] == ["json", "json", "json", "bytes", "bytes", "json"]
    assert [event[1]["type"] for event in socket.events if event[0] == "json"] == ["stt", "tts", "tts", "tts"]  # type: ignore[index]


def test_security_validates_origins_and_tokens(monkeypatch) -> None:
    assert SECURITY.websocket_url == "wss://example.ts.net/api/device/ws"
    assert SECURITY.device_token_matches("Bearer " + SECURITY.device_auth_token)
    monkeypatch.setenv("MARKO_PUBLIC_BASE_URL", "https://example.ts.net/not-an-origin")
    try:
        DeviceSecurity.from_env()
    except RuntimeError as exc:
        assert "origin" in str(exc)
    else:
        raise AssertionError("Invalid public URL was accepted")


def test_opus_packet_round_trip(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    with wave.open(str(wav_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"".join(struct.pack("<h", 0) for _ in range(3200)))
    packets = wav_to_opus_packets(wav_path)
    assert packets
    ogg_path = tmp_path / "tone.ogg"
    write_ogg_opus(packets=packets, output_path=ogg_path, sample_rate=16000, channels=1, frame_duration_ms=60)
    with av.open(str(ogg_path)) as container:
        assert sum(1 for _ in container.decode(audio=0)) > 0
