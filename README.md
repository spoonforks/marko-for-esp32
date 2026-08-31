# Marko for ESP32

Give your local AI agent a body by connecting an ESP32-S3. These are quite cheap on Aliexpress! 
Microphone audio is streamed as Opus to the bridge,
transcribed locally, sent to Ollama or another OpenAI-compatible local server,
spoken with Piper, and streamed back to the device.

## Quick start

1. Install Python 3.11+ and FFmpeg.
2. Create a virtual environment and install `requirements.txt`.
3. Copy `.env.example` to `.env` and generate both secrets independently.
4. Copy `config/assistant.example.yaml` to `config/assistant.yaml`.
5. Start Ollama or your OpenAI-compatible local model server.
6. Install a Piper voice and update the private configuration.
7. Run `python scripts/run_device_server.py`.
8. Follow [the ESP32-S3 guide](docs/ESP32_SETUP.md).

Personality guidance is in [docs/PERSONALITY.md](docs/PERSONALITY.md). The
device protocol is Xiaozhi WebSocket v1: 16 kHz mono Opus in 60 ms frames.

## Security

The provisioning endpoint requires a firmware-only header; the WebSocket and
status endpoint require a separate bearer token. Query-string authentication
is deliberately unsupported, access logging is disabled, and startup fails if
required secrets are absent or weak. Treat Funnel as public exposure.

## Development

```powershell
pip install -r requirements-dev.txt
pytest
```

Hardware flashing and a complete remote voice turn are manual acceptance
tests. This project is MIT licensed; see `THIRD_PARTY_NOTICES.md` for Xiaozhi.
