#!/usr/bin/env python3
"""Inspect or stop only the Windows process owned by one generated macOS app."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time


MARKERS = {
    "steam": (
        r"\steam\steam.exe",
        "steamwebhelper.exe",
        r"\steam\steamservice.exe",
    ),
    "netease": (
        r"\fevergamesinstaller.exe",
        r"\fevergameslauncher.exe",
        r"\fevergamesweb.exe",
    ),
    "netease-game": (r"\feverapps\sky\sky.exe",),
}


def processes(mode: str) -> dict[int, str]:
    markers = tuple(marker.casefold() for marker in MARKERS[mode])
    try:
        output = subprocess.check_output(
            ["ps", "-axo", "pid=,command="], text=True, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError):
        return {}
    found: dict[int, str] = {}
    own_pid = os.getpid()
    parent_pid = os.getppid()
    for line in output.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2 or not fields[0].isdecimal():
            continue
        pid = int(fields[0])
        command = fields[1].casefold()
        if pid not in (own_pid, parent_pid) and any(
            marker in command for marker in markers
        ):
            found[pid] = fields[1]
    return found


def stop(mode: str) -> int:
    targets = processes(mode)
    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    for _ in range(30):
        remaining = processes(mode)
        if not remaining:
            return 0
        time.sleep(0.1)
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    return 0


def wait(mode: str) -> int:
    while processes(mode):
        time.sleep(0.5)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--wait", action="store_true")
    action.add_argument("--stop", action="store_true")
    parser.add_argument("mode", choices=sorted(MARKERS))
    args = parser.parse_args()
    if args.check:
        return 0 if processes(args.mode) else 1
    if args.wait:
        return wait(args.mode)
    return stop(args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
