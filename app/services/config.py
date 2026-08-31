from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "assistant.yaml"


@dataclass(slots=True)
class AssistantSettings:
    name: str
    personality: str


@dataclass(slots=True)
class LLMSettings:
    provider: str
    base_url: str
    model: str
    temperature: float
    num_ctx: int
    request_timeout_seconds: int


@dataclass(slots=True)
class STTSettings:
    model_size: str
    device: str
    compute_type: str
    language: str


@dataclass(slots=True)
class TTSSettings:
    binary_path: str
    model_path: str
    config_path: str
    speaker: int | None


@dataclass(slots=True)
class MemorySettings:
    max_items: int
    inject_limit: int


@dataclass(slots=True)
class WeatherToolSettings:
    enabled: bool
    default_location: str
    geocoding_country_code: str


@dataclass(slots=True)
class ObsidianToolSettings:
    enabled: bool
    vault_path: str
    inbox_folder: str
    daily_notes_folder: str
    search_result_limit: int
    write_requires_explicit_instruction: bool
    task_note_title: str


@dataclass(slots=True)
class ToolSettings:
    weather: WeatherToolSettings
    obsidian: ObsidianToolSettings


@dataclass(slots=True)
class ServerSettings:
    host: str
    port: int


@dataclass(slots=True)
class AppSettings:
    assistant: AssistantSettings
    llm: LLMSettings
    stt: STTSettings
    tts: TTSSettings
    memory: MemorySettings
    tools: ToolSettings
    server: ServerSettings
    config_path: Path


def _nested(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key, {})
    return value if isinstance(value, dict) else {}


def resolve_path(path_value: str) -> Path | None:
    if not path_value:
        return None
    candidate = Path(path_value).expanduser()
    return candidate if candidate.is_absolute() else (REPO_ROOT / candidate).resolve()


def configured_path() -> Path:
    override = os.environ.get("MARKO_CONFIG", "").strip()
    return Path(override).expanduser().resolve() if override else DEFAULT_CONFIG_PATH


def load_settings(config_path: Path | None = None) -> AppSettings:
    config_path = config_path or configured_path()
    if not config_path.exists():
        raise RuntimeError(
            f"Missing configuration: {config_path}. Copy config/assistant.example.yaml "
            "to config/assistant.yaml and customize it."
        )
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    assistant = _nested(raw, "assistant")
    llm = _nested(raw, "llm")
    stt = _nested(raw, "stt")
    tts = _nested(raw, "tts")
    memory = _nested(raw, "memory")
    tools = _nested(raw, "tools")
    weather = _nested(tools, "weather")
    obsidian = _nested(tools, "obsidian")
    server = _nested(raw, "server")

    provider = str(llm.get("provider", "ollama")).strip().lower()
    if provider not in {"ollama", "openai"}:
        raise ValueError("llm.provider must be 'ollama' or 'openai'.")

    return AppSettings(
        assistant=AssistantSettings(
            name=str(assistant.get("name", "Marko")).strip() or "Marko",
            personality=str(assistant.get("personality", "")).strip(),
        ),
        llm=LLMSettings(
            provider=provider,
            base_url=str(llm.get("base_url", "http://127.0.0.1:11434")).rstrip("/"),
            model=str(llm.get("model", "")).strip(),
            temperature=float(llm.get("temperature", 0.7)),
            num_ctx=int(llm.get("num_ctx", 8192)),
            request_timeout_seconds=int(llm.get("request_timeout_seconds", 180)),
        ),
        stt=STTSettings(
            model_size=str(stt.get("model_size", "base")),
            device=str(stt.get("device", "auto")),
            compute_type=str(stt.get("compute_type", "auto")),
            language=str(stt.get("language", "en")),
        ),
        tts=TTSSettings(
            binary_path=str(tts.get("binary_path", "piper")),
            model_path=str(tts.get("model_path", "")),
            config_path=str(tts.get("config_path", "")),
            speaker=tts.get("speaker"),
        ),
        memory=MemorySettings(
            max_items=int(memory.get("max_items", 100)),
            inject_limit=int(memory.get("inject_limit", 20)),
        ),
        tools=ToolSettings(
            weather=WeatherToolSettings(
                enabled=bool(weather.get("enabled", False)),
                default_location=str(weather.get("default_location", "")).strip(),
                geocoding_country_code=str(weather.get("geocoding_country_code", "")).strip(),
            ),
            obsidian=ObsidianToolSettings(
                enabled=bool(obsidian.get("enabled", False)),
                vault_path=str(obsidian.get("vault_path", "")).strip(),
                inbox_folder=str(obsidian.get("inbox_folder", "Inbox")).strip(),
                daily_notes_folder=str(obsidian.get("daily_notes_folder", "Daily")).strip(),
                search_result_limit=int(obsidian.get("search_result_limit", 5)),
                write_requires_explicit_instruction=bool(
                    obsidian.get("write_requires_explicit_instruction", True)
                ),
                task_note_title=str(obsidian.get("task_note_title", "Tasks")).strip(),
            ),
        ),
        server=ServerSettings(
            host=str(server.get("host", "127.0.0.1")),
            port=int(server.get("port", 8001)),
        ),
        config_path=config_path,
    )
