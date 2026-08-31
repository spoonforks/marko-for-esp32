from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class DeviceSecurity:
    provisioning_key: str
    device_auth_token: str
    public_base_url: str

    @classmethod
    def from_env(cls) -> "DeviceSecurity":
        values = {
            "MARKO_PROVISIONING_KEY": os.environ.get("MARKO_PROVISIONING_KEY", "").strip(),
            "MARKO_DEVICE_AUTH_TOKEN": os.environ.get("MARKO_DEVICE_AUTH_TOKEN", "").strip(),
            "MARKO_PUBLIC_BASE_URL": os.environ.get("MARKO_PUBLIC_BASE_URL", "").strip().rstrip("/"),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
        if len(values["MARKO_PROVISIONING_KEY"]) < 32:
            raise RuntimeError("MARKO_PROVISIONING_KEY must contain at least 32 characters.")
        if len(values["MARKO_DEVICE_AUTH_TOKEN"]) < 32:
            raise RuntimeError("MARKO_DEVICE_AUTH_TOKEN must contain at least 32 characters.")
        parsed = urlparse(values["MARKO_PUBLIC_BASE_URL"])
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("MARKO_PUBLIC_BASE_URL must be an http(s) origin without a query or fragment.")
        return cls(
            provisioning_key=values["MARKO_PROVISIONING_KEY"],
            device_auth_token=values["MARKO_DEVICE_AUTH_TOKEN"],
            public_base_url=values["MARKO_PUBLIC_BASE_URL"],
        )

    @property
    def websocket_url(self) -> str:
        prefix = "wss://" if self.public_base_url.startswith("https://") else "ws://"
        return prefix + self.public_base_url.split("://", 1)[1] + "/api/device/ws"

    def provisioning_matches(self, candidate: str | None) -> bool:
        return bool(candidate) and secrets.compare_digest(candidate, self.provisioning_key)

    def device_token_matches(self, candidate: str | None) -> bool:
        if candidate and candidate.startswith("Bearer "):
            candidate = candidate.removeprefix("Bearer ").strip()
        return bool(candidate) and secrets.compare_digest(candidate, self.device_auth_token)
