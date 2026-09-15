#!/usr/bin/env python3
"""Attach the generated Sky macOS app to a game started inside FeverGames."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
import subprocess
import time


HOME = Path(os.environ.get("YYB_INTEL_TEST_HOME", Path.home()))
SUPPORT = HOME / "Library/Application Support/YYBIntelLauncher"
PROCESS_HELPER = SUPPORT / "bin/windows-app-process.py"
LOCK = SUPPORT / "sky-dock-watch.lock"
APPLICATIONS = Path(os.environ.get("YYB_INTEL_APPLICATIONS", "/Applications"))
SKY_APP = APPLICATIONS / "光·遇.app"


def running(mode: str) -> bool:
    if not PROCESS_HELPER.is_file():
        return False
    return subprocess.run(
        [str(PROCESS_HELPER), "--check", mode],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def main() -> int:
    SUPPORT.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0

        saw_launcher = running("netease")
        launch_deadline = time.monotonic() + 90
        while True:
            if running("netease-game"):
                if SKY_APP.is_dir():
                    subprocess.run(
                        ["/usr/bin/open", str(SKY_APP)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                return 0

            launcher_running = running("netease")
            saw_launcher = saw_launcher or launcher_running
            if saw_launcher and not launcher_running:
                return 0
            if not saw_launcher and time.monotonic() >= launch_deadline:
                return 0
            time.sleep(0.25)


if __name__ == "__main__":
    raise SystemExit(main())
