# ESP32-S3 setup

## 1. Prepare the bridge

Create `.env` and `config/assistant.yaml` from their examples, generate two
different random secrets, install dependencies, and start:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item config\assistant.example.yaml config\assistant.yaml
.venv\Scripts\python scripts\run_device_server.py
```

Use `http://127.0.0.1:8001` as `MARKO_PUBLIC_BASE_URL` for a same-network test.
For a LAN test, explicitly set `server.host` to `0.0.0.0` and use the computer's
LAN origin. Restore `127.0.0.1` before using Funnel.

## 2. Prepare Xiaozhi firmware

Install ESP-IDF 6.0.2, enter its activated shell, then run:

```powershell
python scripts\prepare_firmware.py
Set-Location firmware-src
python scripts\build.py zhengchen-cam --language en-US
idf.py menuconfig
```

In **Xiaozhi Assistant**, set **Default OTA URL** to
`<MARKO_PUBLIC_BASE_URL>/api/device/provision` and set **Marko provisioning
key** to the value in `.env`. Never commit the generated `sdkconfig`.

Connect the board over USB, then run `idf.py flash monitor`. On first boot,
follow the Xiaozhi Wi-Fi provisioning prompt. Other supported boards may be
selected instead of `zhengchen-cam`; their microphone, speaker, and buttons
must be supported by upstream Xiaozhi.

## 3. Anywhere access with Tailscale Funnel

With the bridge listening only on `127.0.0.1:8001`:

```powershell
tailscale funnel --bg 8001
tailscale funnel status
```

Set `MARKO_PUBLIC_BASE_URL` to the displayed `https://...ts.net` origin,
rebuild/flash the firmware, and restart the bridge. Funnel is public internet
access: keep both secrets long and unique. Tailscale terminates HTTPS and WSS;
the local bridge remains HTTP on loopback.

Funnel is currently beta, accepts only TLS on supported public ports, and has
non-configurable bandwidth limits. See the official
[Funnel documentation](https://tailscale.com/docs/features/tailscale-funnel).

## Troubleshooting and rotation

- A provisioning 401 means the firmware and `.env` keys differ.
- A WebSocket 401/close code 1008 means the device token is stale.
- Confirm the local model, Piper voice, and Whisper model work before testing remotely.
- Rotate the device token in `.env` and restart to revoke existing devices.
- Rotating the provisioning key also requires rebuilding and flashing firmware.
