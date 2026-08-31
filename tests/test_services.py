from __future__ import annotations

import asyncio
from pathlib import Path

from app.services.config import STTSettings, TTSSettings, load_settings
from app.services.ollama_client import OllamaAssistantService
from app.services.stt import SpeechToTextService
from app.services.tts import PiperTextToSpeechService


class FakeResponse:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.data


class FakeAsyncClient:
    response: dict[str, object] = {}
    last_url = ""
    last_payload: dict[str, object] = {}

    def __init__(self, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def post(self, url: str, json: dict[str, object]) -> FakeResponse:
        type(self).last_url = url
        type(self).last_payload = json
        return FakeResponse(type(self).response)


def test_mocked_ollama_and_openai_flows(monkeypatch) -> None:
    monkeypatch.setattr("app.services.ollama_client.httpx.AsyncClient", FakeAsyncClient)
    settings = load_settings()
    service = OllamaAssistantService(settings)

    FakeAsyncClient.response = {"message": {"content": "Ollama reply"}}
    reply = asyncio.run(service.generate_reply(transcript="Hello", memories=[], history=[]))
    assert reply == "Ollama reply"
    assert FakeAsyncClient.last_url.endswith("/api/chat")

    settings.llm.provider = "openai"
    FakeAsyncClient.response = {"choices": [{"message": {"content": "OpenAI reply"}}]}
    reply = asyncio.run(service.generate_reply(transcript="Hello", memories=[], history=[]))
    assert reply == "OpenAI reply"
    assert FakeAsyncClient.last_url.endswith("/v1/chat/completions")


def test_mocked_stt_and_tts_flows(tmp_path: Path, monkeypatch) -> None:
    class Segment:
        text = "Hello Marco"

    class Model:
        def transcribe(self, *_args, **_kwargs):
            return [Segment()], None

    stt = SpeechToTextService(STTSettings("base", "cpu", "int8", "en"))
    stt._model = Model()
    assert stt.transcribe(tmp_path / "audio.wav") == "Hello Marko"

    tts = PiperTextToSpeechService(TTSSettings("piper", "voice.onnx", "", None), tmp_path)
    expected = tmp_path / "reply.wav"
    monkeypatch.setattr(tts, "_synthesize_with_python_voice", lambda _text: expected)
    assert tts.synthesize("Hello") == expected
