from __future__ import annotations

import asyncio
import json
import logging
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect

from app.services.device_security import DeviceSecurity
from app.services.ogg_opus import wav_to_opus_packets, write_ogg_opus
from app.services.runtime import (
    DEVICE_UPLOAD_DIR,
    MAX_DEVICE_UPLOADS,
    process_assistant_turn,
    prune_old_files,
)


DEVICE_AUDIO_SAMPLE_RATE = 16_000
DEVICE_INPUT_FRAME_DURATION_MS = 60
REPLY_AUDIO_SAMPLE_RATE = 16_000
REPLY_FRAME_DURATION_MS = 60
REPLY_SEND_YIELD_EVERY = 8
REPLY_STOP_TAIL_MS = 500
MAX_RECORDING_SECONDS = 45
MAX_RECORDING_PACKETS = MAX_RECORDING_SECONDS * 1000 // DEVICE_INPUT_FRAME_DURATION_MS

SECURITY = DeviceSecurity.from_env()
app = FastAPI(title="Marko for ESP32", docs_url=None, redoc_url=None)
logger = logging.getLogger("uvicorn.error")


def require_device_auth(authorization: str | None = Header(default=None)) -> None:
    if SECURITY.device_token_matches(authorization):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/device/provision")
async def provision_device(
    provisioning_key: str | None = Header(default=None, alias="X-Marko-Provisioning-Key"),
) -> dict[str, object]:
    if not SECURITY.provisioning_matches(provisioning_key):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {
        "websocket": {
            "url": SECURITY.websocket_url,
            "token": SECURITY.device_auth_token,
            "version": 1,
        },
        "audio": {
            "format": "opus",
            "sample_rate": DEVICE_AUDIO_SAMPLE_RATE,
            "channels": 1,
            "frame_duration_ms": DEVICE_INPUT_FRAME_DURATION_MS,
        },
    }


@app.get("/api/device/status", dependencies=[Depends(require_device_auth)])
async def device_status() -> dict[str, object]:
    return {
        "service": "Marko for ESP32",
        "protocol": "xiaozhi-websocket-v1",
        "websocket_path": "/api/device/ws",
        "input_format": "opus",
        "input_sample_rate": DEVICE_AUDIO_SAMPLE_RATE,
        "input_frame_duration_ms": DEVICE_INPUT_FRAME_DURATION_MS,
        "reply_format": "opus",
        "reply_sample_rate": REPLY_AUDIO_SAMPLE_RATE,
        "reply_frame_duration_ms": REPLY_FRAME_DURATION_MS,
    }


async def send_json(websocket: WebSocket, payload: dict[str, object]) -> None:
    await websocket.send_text(json.dumps(payload, separators=(",", ":")))


@app.websocket("/api/device/ws")
async def device_websocket(websocket: WebSocket) -> None:
    if not SECURITY.device_token_matches(websocket.headers.get("authorization")):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    session_id = str(uuid4())
    logger.info("ESP32 connected: session=%s", session_id)
    audio_packets: list[bytes] = []
    history: list[dict[str, str]] = []
    recording = False

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if message.get("text") is not None:
                try:
                    payload = json.loads(message["text"])
                except (json.JSONDecodeError, TypeError):
                    await send_json(websocket, {"type": "alert", "status": "Protocol error", "message": "Invalid JSON", "emotion": "circle_xmark"})
                    continue
                if not isinstance(payload, dict):
                    continue
                message_type = payload.get("type")

                if message_type == "hello":
                    if int(payload.get("version", 1)) != 1:
                        await send_json(websocket, {"type": "alert", "status": "Protocol error", "message": "Only Xiaozhi protocol v1 is supported", "emotion": "circle_xmark"})
                        continue
                    await send_json(
                        websocket,
                        {
                            "type": "hello",
                            "transport": "websocket",
                            "session_id": session_id,
                            "audio_params": {
                                "format": "opus",
                                "sample_rate": REPLY_AUDIO_SAMPLE_RATE,
                                "channels": 1,
                                "frame_duration": REPLY_FRAME_DURATION_MS,
                            },
                        },
                    )
                    continue

                if message_type == "listen":
                    state = payload.get("state")
                    if state == "start":
                        audio_packets = []
                        recording = True
                    elif state == "stop":
                        recording = False
                        await handle_recording(websocket, session_id, audio_packets, history)
                        audio_packets = []
                    continue

                if message_type == "abort":
                    recording = False
                    audio_packets = []
                    continue

            packet = message.get("bytes")
            if packet is not None and recording:
                if len(audio_packets) >= MAX_RECORDING_PACKETS:
                    recording = False
                    await handle_recording(websocket, session_id, audio_packets, history)
                    audio_packets = []
                    continue
                audio_packets.append(packet)

    except WebSocketDisconnect:
        pass
    finally:
        logger.info("ESP32 disconnected: session=%s", session_id)


async def handle_recording(
    websocket: WebSocket,
    session_id: str,
    audio_packets: list[bytes],
    history: list[dict[str, str]],
) -> None:
    if not audio_packets:
        return

    upload_path = DEVICE_UPLOAD_DIR / f"{uuid4()}.ogg"
    write_ogg_opus(
        packets=audio_packets,
        output_path=upload_path,
        sample_rate=DEVICE_AUDIO_SAMPLE_RATE,
        channels=1,
        frame_duration_ms=DEVICE_INPUT_FRAME_DURATION_MS,
    )
    prune_old_files(DEVICE_UPLOAD_DIR, MAX_DEVICE_UPLOADS)

    try:
        result = await process_assistant_turn(audio_path=upload_path, history=history[-4:])
    except HTTPException as exc:
        await send_json(
            websocket,
            {"session_id": session_id, "type": "alert", "status": "Assistant error", "message": str(exc.detail), "emotion": "circle_xmark"},
        )
        return

    transcript = str(result["transcript"])
    reply_text = str(result["reply_text"])
    response_audio_path = result["response_audio_path"]
    history.extend((
        {"role": "user", "content": transcript},
        {"role": "assistant", "content": reply_text},
    ))
    del history[:-4]
    logger.info("Assistant turn complete: session=%s", session_id)

    await send_json(websocket, {"session_id": session_id, "type": "stt", "text": transcript})
    await send_json(websocket, {"session_id": session_id, "type": "tts", "state": "sentence_start", "text": reply_text})
    await send_json(websocket, {"session_id": session_id, "type": "tts", "state": "start"})
    await asyncio.sleep(0.1)

    reply_packets = wav_to_opus_packets(response_audio_path)
    stream_started = time.monotonic()
    for index, packet in enumerate(reply_packets):
        await websocket.send_bytes(packet)
        if (index + 1) % REPLY_SEND_YIELD_EVERY == 0:
            await asyncio.sleep(0)

    playback_ms = len(reply_packets) * REPLY_FRAME_DURATION_MS
    elapsed_ms = int((time.monotonic() - stream_started) * 1000)
    await asyncio.sleep(max(REPLY_STOP_TAIL_MS, playback_ms + REPLY_STOP_TAIL_MS - elapsed_ms) / 1000)
    await send_json(websocket, {"session_id": session_id, "type": "tts", "state": "stop"})
