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
        "/steam/steam.exe",
        r"\steam\steam",
        "/steam/steam",
        "steamwebhelper.exe",
    ),
    "netease": (
        r"\fevergamesinstaller.exe",
        "/fevergamesinstaller.exe",
        r"\fevergamesinstaller",
        "/fevergamesinstaller",
        r"\fevergameslauncher.exe",
        "/fevergameslauncher.exe",
        r"\fevergameslauncher",
        "/fevergameslauncher",
        r"\fevergamesweb.exe",
        "/fevergamesweb.exe",
        r"\fevergamesweb",
        "/fevergamesweb",
    ),
    "netease-game": (
        r"\feverapps\sky\sky.exe",
        "/feverapps/sky/sky.exe",
        r"\feverapps\sky\sky",
        "/feverapps/sky/sky",
    ),
}


def path_markers(path: str) -> tuple[str, ...]:
    normalized = path.replace("\\", "/").rstrip("/").casefold()
    markers = [normalized + "/"]
    drive_marker = "/drive_c/"
    if drive_marker in normalized:
        relative = normalized.split(drive_marker, 1)[1]
        markers.extend((f"/{relative}/", "\\" + relative.replace("/", "\\") + "\\"))
    return tuple(markers)


def process_markers(mode: str, details: list[str] | None = None) -> tuple[str, ...]:
    if mode == "steam-game":
        return path_markers(details[-1]) if details else ()
    return tuple(marker.casefold() for marker in MARKERS[mode])


def belongs_to_windows_steam(executable: str) -> bool:
    normalized = executable.replace("\\", "/").casefold()
    return (
        executable.casefold().startswith("c:\\")
        or "/drive_c/" in normalized
        or "/com.tencent.yybmac.wine.engine/" in normalized
    )


def processes(
    mode: str,
    details: list[str] | None = None,
    *,
    include_links: bool = False,
) -> dict[int, str]:
    markers = process_markers(mode, details)
    if not markers:
        return {}
    try:
        output = subprocess.check_output(
            ["ps", "-axo", "pid=,comm="], text=True, stderr=subprocess.DEVNULL
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
        executable = fields[1].casefold()
        if not include_links and "/com.tencent.yybmac.wine.engine/links/" in executable:
            continue
        if mode == "steam" and not belongs_to_windows_steam(fields[1]):
            continue
        if pid not in (own_pid, parent_pid) and any(
            marker in executable for marker in markers
        ):
            found[pid] = fields[1]
    return found


def stop(mode: str, details: list[str] | None = None) -> int:
    targets = processes(mode, details, include_links=True)
    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    for _ in range(30):
        remaining = processes(mode, details, include_links=True)
        if not remaining:
            return 0
        time.sleep(0.1)
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    return 0


def wait(mode: str, details: list[str] | None = None) -> int:
    while processes(mode, details):
        time.sleep(0.5)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--wait", action="store_true")
    action.add_argument("--stop", action="store_true")
    parser.add_argument("mode", choices=sorted((*MARKERS, "steam-game")))
    parser.add_argument("details", nargs="*")
    args = parser.parse_args()
    if args.check:
        return 0 if processes(args.mode, args.details) else 1
    if args.wait:
        return wait(args.mode, args.details)
    return stop(args.mode, args.details)


if __name__ == "__main__":
    raise SystemExit(main())
