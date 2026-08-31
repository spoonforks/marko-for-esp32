from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "firmware-src"
PATCH = ROOT / "firmware" / "patches" / "marko-provisioning-header.patch"
UPSTREAM = "https://github.com/78/xiaozhi-esp32.git"
REVISION = "5df5b7fb4da2b4d80e2b7f87285ec1f8a9ca565c"


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True, shell=False)


def main() -> None:
    if TARGET.exists():
        raise SystemExit(f"{TARGET} already exists; move or remove it before preparing again.")
    run("git", "clone", UPSTREAM, str(TARGET))
    run("git", "checkout", "--detach", REVISION, cwd=TARGET)
    run("git", "apply", "--check", str(PATCH), cwd=TARGET)
    run("git", "apply", str(PATCH), cwd=TARGET)
    print(f"Prepared Xiaozhi firmware in {TARGET}")


if __name__ == "__main__":
    main()
