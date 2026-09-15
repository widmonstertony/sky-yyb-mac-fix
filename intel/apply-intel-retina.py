#!/usr/bin/env python3
"""Apply reversible Retina/DPI fixes to Tencent's Intel Wine prefix."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import time


def home() -> Path:
    override = os.environ.get("YYB_INTEL_TEST_HOME")
    return Path(override).expanduser() if override else Path.home()


HOME = home()
SUPPORT = HOME / "Library/Application Support/YYBIntelLauncher"
PREFIX = HOME / "Library/Application Support/com.tencent.yybmac.wine.engine/wine"
USER_REG = PREFIX / "user.reg"
SYSTEM_REG = PREFIX / "system.reg"
PREFERENCES = (
    PREFIX
    / "drive_c/FeverApps/sky/data/ThatGameCompany/com.netease.sky/preferences.sav"
)
STATE_ROOT = SUPPORT / "backups"
FPS_WATCH_LOCK = SUPPORT / "sky-fps-watch.lock"


class FixError(RuntimeError):
    pass


def acquire_lock(path: Path) -> int | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for _attempt in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            return descriptor
        except FileExistsError:
            try:
                pid = int(path.read_text(encoding="ascii"))
                os.kill(pid, 0)
                return None
            except (OSError, ValueError):
                path.unlink(missing_ok=True)
    return None


def release_lock(path: Path, descriptor: int) -> None:
    os.close(descriptor)
    path.unlink(missing_ok=True)


def atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".yyb-intel-new")
    temporary.write_bytes(data)
    if path.exists():
        temporary.chmod(path.stat().st_mode & 0o777)
    os.replace(temporary, path)


def upsert_reg_value(text: str, section: str, name: str, value: str) -> str:
    header = re.compile(rf"(?m)^\[{re.escape(section)}\](?: [0-9]+)?$")
    match = header.search(text)
    line = f'"{name}"={value}'
    if not match:
        suffix = "" if text.endswith("\n") else "\n"
        return text + suffix + f"\n[{section}] {int(time.time())}\n{line}\n"
    section_end = text.find("\n[", match.end())
    if section_end < 0:
        section_end = len(text)
    block = text[match.start() : section_end]
    value_pattern = re.compile(rf'(?m)^"{re.escape(name)}"=.*$')
    if value_pattern.search(block):
        # A callable replacement keeps the doubled backslashes required by
        # Wine .reg files.  A plain replacement string would interpret them.
        block = value_pattern.sub(lambda _match: line, block)
    else:
        block = block.rstrip("\n") + "\n" + line + "\n"
    return text[: match.start()] + block + text[section_end:]


def delete_reg_value(text: str, section: str, name: str) -> str:
    header = re.compile(rf"(?m)^\[{re.escape(section)}\](?: [0-9]+)?$")
    match = header.search(text)
    if not match:
        return text
    section_end = text.find("\n[", match.end())
    if section_end < 0:
        section_end = len(text)
    block = text[match.start() : section_end]
    value_pattern = re.compile(rf'(?m)^"{re.escape(name)}"=.*\n?')
    block = value_pattern.sub("", block)
    return text[: match.start()] + block + text[section_end:]


def installed_fever_versions() -> list[Path]:
    root = PREFIX / "drive_c/Program Files/FeverGames"
    if not root.is_dir():
        return []
    versions = [
        item
        for item in root.iterdir()
        if item.is_dir() and re.fullmatch(r"[0-9.]+", item.name)
    ]
    return sorted(versions, key=lambda item: tuple(int(part) for part in item.name.split(".")))


def stop_managed_processes() -> None:
    if os.environ.get("YYB_INTEL_TEST_HOME"):
        return
    try:
        output = subprocess.check_output(
            ["ps", "-axo", "pid=,command="], text=True, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError):
        return
    markers = (
        str(PREFIX),
        str(SUPPORT / ".runtime/wine-engine.app"),
        str(SUPPORT / "wine-loader"),
        str(SUPPORT / "wineserver-wrapper"),
    )
    pids: list[int] = []
    for line in output.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2 or not fields[0].isdecimal():
            continue
        command = fields[1]
        if any(marker in command for marker in markers):
            pid = int(fields[0])
            if pid != os.getpid():
                pids.append(pid)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    if pids:
        time.sleep(1)


def patched_registry_texts() -> tuple[str, str]:
    if not USER_REG.is_file() or not SYSTEM_REG.is_file():
        raise FixError("腾讯 PC 游戏环境还没有初始化。")
    user = USER_REG.read_text(encoding="utf-8")
    system = SYSTEM_REG.read_text(encoding="utf-8")

    mac_driver = "Software\\\\Wine\\\\Mac Driver"
    user = upsert_reg_value(user, mac_driver, "RetinaMode", '"Y"')
    user = upsert_reg_value(user, mac_driver, "CursorClippingLocksWindows", '"N"')
    user = upsert_reg_value(user, mac_driver, "UseConfinementCursorClipping", '"N"')

    layers = "Software\\\\Microsoft\\\\Windows NT\\\\CurrentVersion\\\\AppCompatFlags\\\\Layers"
    executables = [
        r"C:\\FeverApps\\sky\\Sky.exe",
        r"C:\\Program Files\\FeverGames\\FeverGamesLauncher.exe",
        r"C:\\Program Files (x86)\\Steam\\Steam.exe",
        r"C:\\Program Files (x86)\\Steam\\bin\\cef\\cef.win7x64\\steamwebhelper.exe",
    ]
    for version in installed_fever_versions():
        for name in (
            "FeverGamesInstaller.exe",
            "FeverGamesWeb.exe",
            "FeverGamesDiagnosis.exe",
        ):
            executables.append(rf"C:\\Program Files\\FeverGames\\{version.name}\\{name}")
    for executable in executables:
        user = upsert_reg_value(user, layers, executable, '"~ HIGHDPIAWARE"')
    # Do not set setting/channel/gameid here. That value activates NetEase's
    # portable-install validator, which requires the game and launcher to have
    # the same parent directory and is not valid for C:\\FeverApps\\sky.
    fever_channel = (
        "Software\\\\FeverGames\\\\FeverGamesInstaller\\\\setting\\\\channel"
    )
    user = delete_reg_value(user, fever_channel, "gameid")

    ifeo = "Software\\\\Microsoft\\\\Windows NT\\\\CurrentVersion\\\\Image File Execution Options"
    for name in (
        "FeverGamesLauncher.exe",
        "FeverGamesInstaller.exe",
        "FeverGamesWeb.exe",
        "FeverGamesDiagnosis.exe",
        "Sky.exe",
        "Steam.exe",
        "steamwebhelper.exe",
    ):
        system = upsert_reg_value(
            system, ifeo + "\\\\" + name, "dpiAwareness", "dword:00000002"
        )
    # Clean up the location used by an early Intel prototype. FeverGames reads
    # gameid from the per-user setting/channel section above, not HKLM.
    fever_machine = "Software\\\\FeverGames\\\\FeverGamesInstaller"
    system = delete_reg_value(system, fever_machine, "gameid")
    return user, system


def patched_preferences(fps: int) -> bytes | None:
    if not PREFERENCES.is_file():
        return None
    data = bytearray(PREFERENCES.read_bytes())
    if data[:4] != b"PREF" or len(data) < 32:
        raise FixError("光遇 preferences.sav 格式不符合预期，拒绝写入。")
    counts = struct.unpack_from("<4I", data, 8)
    record_count = sum(counts)
    string_base = struct.unpack_from("<I", data, 24)[0]
    if 28 + record_count * 8 != string_base or string_base >= len(data):
        raise FixError("光遇偏好表结构不符合预期，拒绝写入。")
    found_fps = False
    for index in range(record_count):
        record = 28 + index * 8
        name_offset = struct.unpack_from("<I", data, record)[0]
        name_start = string_base + name_offset
        try:
            name_end = data.index(0, name_start)
        except ValueError as exc:
            raise FixError("光遇偏好表字符串损坏，拒绝写入。") from exc
        name = data[name_start:name_end].decode("utf-8", "replace")
        if name == "quality_fps":
            struct.pack_into("<I", data, record + 4, fps)
            found_fps = True
        elif name == "kUserPreference_MotionBlurScalar":
            struct.pack_into("<f", data, record + 4, 0.0)
    if not found_fps:
        return None
    return bytes(data)


def apply(fps: int = 60) -> Path | None:
    user, system = patched_registry_texts()
    changed = []
    if user.encode("utf-8") != USER_REG.read_bytes():
        changed.append((USER_REG, user.encode("utf-8")))
    if system.encode("utf-8") != SYSTEM_REG.read_bytes():
        changed.append((SYSTEM_REG, system.encode("utf-8")))
    preferences = patched_preferences(fps)
    if preferences is not None and preferences != PREFERENCES.read_bytes():
        changed.append((PREFERENCES, preferences))
    if not changed:
        return None

    if any(path in (USER_REG, SYSTEM_REG) for path, _data in changed):
        stop_managed_processes()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = STATE_ROOT / stamp
    suffix = 0
    while backup.exists():
        suffix += 1
        backup = STATE_ROOT / f"{stamp}-{suffix:02d}"
    backup.mkdir(parents=True, exist_ok=False)
    backup.chmod(0o700)
    manifest = []
    for index, (path, _) in enumerate(changed):
        copy = backup / f"item-{index:03d}"
        shutil.copy2(path, copy)
        copy.chmod(0o600)
        manifest.append({"path": str(path), "backup": copy.name})
    (backup / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for path, data in changed:
        atomic_write(path, data)
    return backup


def sky_is_running() -> bool:
    if os.environ.get("YYB_INTEL_TEST_HOME"):
        return False
    marker = str(PREFIX / "drive_c/FeverApps/sky/Sky.exe")
    return subprocess.run(
        ["pgrep", "-if", marker],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def watch_fps(fps: int, seconds: int) -> int:
    descriptor = acquire_lock(FPS_WATCH_LOCK)
    if descriptor is None:
        return 0
    try:
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                has_fps = b"quality_fps\0" in PREFERENCES.read_bytes()
            except OSError:
                has_fps = False
            if has_fps and not sky_is_running():
                backup = apply(fps)
                if backup:
                    print(f"光遇 {fps} FPS 配置已保存；备份在：{backup}")
                return 0
            time.sleep(2)
        return 0
    finally:
        release_lock(FPS_WATCH_LOCK, descriptor)


def restore_latest() -> Path:
    backups = sorted(path for path in STATE_ROOT.glob("*") if path.is_dir())
    if not backups:
        raise FixError("没有找到可恢复的 Intel Retina 配置备份。")
    backup = backups[-1]
    try:
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FixError(f"备份清单无法读取：{exc}") from exc
    allowed = {USER_REG, SYSTEM_REG, PREFERENCES}
    restored = 0
    stop_managed_processes()
    for item in manifest:
        try:
            target = Path(item["path"])
            source = backup / item["backup"]
        except (KeyError, TypeError) as exc:
            raise FixError("备份清单格式异常。") from exc
        if target not in allowed or not source.is_file():
            raise FixError("备份清单包含非本工具管理的文件，已拒绝恢复。")
        atomic_write(target, source.read_bytes())
        restored += 1
    if not restored:
        raise FixError("备份中没有可恢复的文件。")
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description="为腾讯 Intel PC 游戏环境启用 Retina 高清")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--check", action="store_true", help="只检查，不修改")
    actions.add_argument("--stop", action="store_true", help="只关闭本工具管理的 Windows 进程")
    actions.add_argument("--restore", action="store_true", help="恢复最近一次配置备份")
    actions.add_argument("--watch-fps", action="store_true", help="游戏退出后自动保存帧率")
    parser.add_argument("--fps", type=int, default=60, choices=(30, 60, 120))
    parser.add_argument("--watch-seconds", type=int, default=6 * 60 * 60)
    args = parser.parse_args()
    try:
        if args.stop:
            stop_managed_processes()
            print("已关闭腾讯 Intel 兼容层中的 Windows 进程。")
            return 0
        if args.check:
            patched_registry_texts()
            print("Retina/DPI 配置可以安全应用。")
            return 0
        if args.restore:
            backup = restore_latest()
            print(f"已经从备份恢复：{backup}")
            return 0
        if args.watch_fps:
            return watch_fps(args.fps, args.watch_seconds)
        backup = apply(args.fps)
        if backup:
            print(f"Retina/DPI 配置已更新；原文件备份在：{backup}")
        else:
            print("Retina/DPI 配置已经是最新。")
        return 0
    except (FixError, OSError) as exc:
        print(f"错误：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
