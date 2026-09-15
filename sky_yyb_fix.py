#!/usr/bin/env python3
"""Install, repair and launch the NetEase China edition of Sky in YYB on macOS.

Only Python's standard library is used. The script never bundles or uploads
Tencent/NetEase binaries and never reads account tokens.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import time
import urllib.request
import zlib


PACKAGE_PARENT = "com.tencent.macexe.com.45a7ca33"
PACKAGE_SKY_PREFIX = PACKAGE_PARENT + "."
FEVER_API = "https://loadingbaycn.webapp.163.com/app/v1/download_client/windows"


def home() -> Path:
    override = os.environ.get("SKY_YYB_TEST_HOME")
    return Path(override).expanduser() if override else Path.home()


def applications_root() -> Path:
    override = os.environ.get("SKY_YYB_TEST_APPLICATIONS")
    return Path(override).expanduser() if override else Path("/Applications")


HOME = home()
APP_SUPPORT = HOME / "Library/Application Support"
YYB_DATA = APP_SUPPORT / "com.tencent.yybmac"
ENGINE_ROOT = APP_SUPPORT / "com.tencent.yybmac.wine.engine"
PREFIX = ENGINE_ROOT / "wine"
APPS_DB = ENGINE_ROOT / "apps/apps.db"
PUBLIC_MMKV = YYB_DATA / "publicMMKV/mmkv/com.tencent.yybmac.publicMMKV"
PUBLIC_MMKV_CRC = Path(str(PUBLIC_MMKV) + ".crc")
SKY_DIR = PREFIX / "drive_c/FeverApps/sky"
SKY_EXE = SKY_DIR / "Sky.exe"
PREFERENCES = SKY_DIR / "data/ThatGameCompany/com.netease.sky/preferences.sav"
USER_REG = PREFIX / "user.reg"
SYSTEM_REG = PREFIX / "system.reg"
STATE_ROOT = APP_SUPPORT / "SkyYYBMacFix"
LATEST_FILE = STATE_ROOT / "latest-backup.txt"
YYB_APP = applications_root() / "YYBMacApp.app"
YYB_SHORTCUTS = applications_root() / "腾讯应用宝"


class FixError(RuntimeError):
    pass


def say(message: str) -> None:
    print(message, flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


class BackupSet:
    def __init__(self) -> None:
        ensure_private_dir(STATE_ROOT)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.root = STATE_ROOT / "backups" / stamp
        ensure_private_dir(self.root)
        self.manifest: list[dict[str, str | bool]] = []

    def capture(self, path: Path) -> None:
        if any(item["path"] == str(path) for item in self.manifest):
            return
        relative = f"item-{len(self.manifest):03d}"
        target = self.root / relative
        existed = path.exists()
        if existed:
            shutil.copy2(path, target)
            target.chmod(0o600)
        self.manifest.append(
            {"path": str(path), "backup": relative, "existed": existed}
        )

        # Keep the manifest crash-safe as each item is captured, so a failed
        # write later in the transaction can still be rolled back immediately.
        self._persist_manifest()

    def _persist_manifest(self) -> None:
        manifest = self.root / "manifest.json"
        manifest.write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest.chmod(0o600)

    def finish(self) -> None:
        self._persist_manifest()
        LATEST_FILE.write_text(str(self.root) + "\n", encoding="utf-8")
        LATEST_FILE.chmod(0o600)


def atomic_write(path: Path, data: bytes, mode: int | None = None) -> None:
    tmp = path.with_name(path.name + ".skyfix-new")
    tmp.write_bytes(data)
    if mode is None and path.exists():
        mode = path.stat().st_mode & 0o777
    if mode is not None:
        tmp.chmod(mode)
    os.replace(tmp, path)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FixError(f"无法读取 {path}: {exc}") from exc


def find_fever_launcher() -> Path | None:
    candidate = PREFIX / "drive_c/Program Files/FeverGames/FeverGamesLauncher.exe"
    return candidate if candidate.exists() else None


def installed_fever_versions() -> list[Path]:
    base = PREFIX / "drive_c/Program Files/FeverGames"
    if not base.exists():
        return []
    return sorted(
        (item for item in base.iterdir() if item.is_dir() and re.fullmatch(r"[0-9.]+", item.name)),
        key=lambda item: tuple(int(part) for part in item.name.split(".")),
    )


def shortcut_for(package_name: str) -> Path | None:
    direct = YYB_SHORTCUTS / f"{package_name}.app"
    if direct.exists():
        return direct
    if not YYB_SHORTCUTS.exists():
        return None
    for app in YYB_SHORTCUTS.glob("*.app"):
        plist = app / "Contents/Info.plist"
        try:
            with plist.open("rb") as stream:
                info = plistlib.load(stream)
        except (OSError, plistlib.InvalidFileException):
            continue
        if info.get("YYBPackageName") == package_name:
            return app
    return None


def stop_related_processes() -> None:
    if os.environ.get("SKY_YYB_TEST_HOME"):
        return
    # Exact executable names only. Failures are harmless when nothing is open.
    for name in (
        "Sky.exe",
        "FeverGamesWeb.exe",
        "FeverGamesInstaller.exe",
        "FeverGamesLauncher.exe",
        "YYBPackage",
        "YYBMacApp",
    ):
        subprocess.run(
            ["pkill", "-x", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    time.sleep(1)


def open_path(path: Path) -> None:
    if os.environ.get("SKY_YYB_TEST_HOME"):
        say(f"[test] open {path}")
        return
    subprocess.run(["open", str(path)], check=True)


def open_with_yyb(path: Path) -> None:
    if os.environ.get("SKY_YYB_TEST_HOME"):
        say(f"[test] open with YYB: {path}")
        return
    subprocess.run(["open", "-a", str(YYB_APP), str(path)], check=True)


def wait_for(path: Path, seconds: int, prompt: str) -> bool:
    say(prompt)
    if os.environ.get("SKY_YYB_TEST_HOME"):
        return path.exists()
    deadline = time.time() + seconds
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(2)
    return False


def fetch_official_installer() -> Path:
    say("正在查询网易官方安装包……")
    request = urllib.request.Request(
        FEVER_API,
        headers={"User-Agent": "sky-yyb-mac-fix/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
        data = payload["data"]
        url = data["download_url"]
        expected_md5 = data["package_md5"].lower()
        file_name = Path(data["file_name"]).name
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise FixError(f"无法从网易官方接口取得安装包信息: {exc}") from exc

    downloads = HOME / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    target = downloads / file_name
    if target.exists() and md5(target) == expected_md5:
        say(f"已存在并通过校验：{target.name}")
        return target

    partial = target.with_suffix(target.suffix + ".download")
    say(f"正在从网易官方下载 {file_name}……")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out, 1024 * 1024)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise FixError(f"下载失败: {exc}") from exc
    if md5(partial) != expected_md5:
        partial.unlink(missing_ok=True)
        raise FixError("官方安装包 MD5 校验失败，已删除临时文件。")
    os.replace(partial, target)
    return target


def md5(path: Path) -> str:
    # MD5 is used only to match the checksum published by NetEase's download
    # API, not for signatures or any other security boundary.
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_prerequisites() -> bool:
    if sys.platform != "darwin" and not os.environ.get("SKY_YYB_TEST_HOME"):
        raise FixError("此工具只支持 macOS。")
    if not YYB_APP.exists():
        raise FixError("未找到腾讯应用宝。请先从腾讯官方安装 YYBMacApp.app。")
    if not PREFIX.exists():
        open_path(YYB_APP)
        if not wait_for(PREFIX, 600, "请在应用宝中完成首次初始化，本窗口会自动等待……"):
            raise FixError("应用宝 Wine 引擎尚未初始化，请打开应用宝后重新运行本工具。")

    if find_fever_launcher() is None:
        installer = fetch_official_installer()
        open_with_yyb(installer)
        launcher = PREFIX / "drive_c/Program Files/FeverGames/FeverGamesLauncher.exe"
        if not wait_for(
            launcher,
            900,
            "已交给应用宝安装。请在出现的安装界面完成网易发烧游戏平台安装……",
        ):
            raise FixError("等待发烧游戏平台安装超时；安装完成后再次运行本工具即可续接。")

    if not SKY_EXE.exists():
        parent = shortcut_for(PACKAGE_PARENT)
        open_path(parent or YYB_APP)
        if not wait_for(
            SKY_EXE,
            3600,
            "请在发烧游戏平台内登录并安装《光·遇》；本窗口会自动等待……",
        ):
            say("尚未检测到 Sky.exe。安装完游戏后，再双击 install.command 即可自动续接。")
            return False
    return True


def upsert_reg_value(text: str, section: str, name: str, value: str) -> str:
    header_re = re.compile(rf"(?m)^\[{re.escape(section)}\](?: [0-9]+)?$")
    match = header_re.search(text)
    line = f'"{name}"={value}'
    if not match:
        suffix = "" if text.endswith("\n") else "\n"
        return text + suffix + f"\n[{section}] {int(time.time())}\n{line}\n"
    section_end = text.find("\n[", match.end())
    if section_end < 0:
        section_end = len(text)
    block = text[match.start():section_end]
    value_re = re.compile(rf'(?m)^"{re.escape(name)}"=.*$')
    if value_re.search(block):
        block = value_re.sub(lambda _match: line, block)
    else:
        block = block.rstrip("\n") + "\n" + line + "\n"
    return text[:match.start()] + block + text[section_end:]


def patch_registries(backups: BackupSet) -> list[str]:
    changed: list[str] = []
    for path in (USER_REG, SYSTEM_REG):
        if not path.exists():
            raise FixError(f"Wine 注册表不存在：{path}")
        backups.capture(path)

    user = USER_REG.read_text(encoding="utf-8")
    mac_driver = "Software\\\\Wine\\\\Mac Driver"
    user = upsert_reg_value(user, mac_driver, "RetinaMode", '"Y"')
    user = upsert_reg_value(user, mac_driver, "CursorClippingLocksWindows", '"N"')
    user = upsert_reg_value(user, mac_driver, "UseConfinementCursorClipping", '"N"')

    layers = "Software\\\\Microsoft\\\\Windows NT\\\\CurrentVersion\\\\AppCompatFlags\\\\Layers"
    executables = [
        r"C:\\FeverApps\\sky\\Sky.exe",
        r"C:\\Program Files\\FeverGames\\FeverGamesLauncher.exe",
    ]
    for version in installed_fever_versions():
        executables.extend(
            [
                rf"C:\\Program Files\\FeverGames\\{version.name}\\FeverGamesInstaller.exe",
                rf"C:\\Program Files\\FeverGames\\{version.name}\\FeverGamesWeb.exe",
            ]
        )
    for executable in executables:
        user = upsert_reg_value(user, layers, executable, '"~ HIGHDPIAWARE"')
    atomic_write(USER_REG, user.encode("utf-8"))
    changed.append("Wine Retina 与逐进程 High-DPI 感知")

    system = SYSTEM_REG.read_text(encoding="utf-8")
    ifeo = "Software\\\\Microsoft\\\\Windows NT\\\\CurrentVersion\\\\Image File Execution Options"
    for exe_name in ("FeverGamesLauncher.exe", "FeverGamesInstaller.exe", "FeverGamesWeb.exe", "Sky.exe"):
        system = upsert_reg_value(system, ifeo + "\\\\" + exe_name, "dpiAwareness", "dword:00000002")
    atomic_write(SYSTEM_REG, system.encode("utf-8"))
    changed.append("启动器与光遇 Per-Monitor DPI 感知")
    return changed


def patch_apps_db(backups: BackupSet) -> list[str]:
    if not APPS_DB.exists():
        return []
    database = load_json(APPS_DB)
    sky_keys = []
    for key, record in database.items():
        install_path = str(record.get("install_path", "")).lower()
        if (
            key.startswith(PACKAGE_SKY_PREFIX)
            and (record.get("game_id") == "63" or install_path.endswith("feverapps\\sky"))
        ):
            sky_keys.append(key)
    if not sky_keys:
        return []
    backups.capture(APPS_DB)
    for key in sky_keys:
        record = database[key]
        record.update(
            {
                "entry_path": "fevergames://mygame/?gameId=63&autoRun=1",
                "launcher_id": "fevergames_launcher",
                "launcher_package": PACKAGE_PARENT,
                "launcher_child_exe": "sky.exe",
            }
        )
    parent = database.get(PACKAGE_PARENT)
    if parent is not None:
        parent["entry_path"] = r"C:\Program Files\FeverGames\FeverGamesLauncher.exe"
        parent["install_path"] = r"C:\Program Files\FeverGames"
    encoded = (json.dumps(database, ensure_ascii=False, indent=4) + "\n").encode("utf-8")
    atomic_write(APPS_DB, encoded)
    return [f"修复 {len(sky_keys)} 个应用宝协议启动入口"]


def patch_mmkv(backups: BackupSet) -> list[str]:
    if not PUBLIC_MMKV.exists() or not PUBLIC_MMKV_CRC.exists():
        return []
    blob = bytearray(PUBLIC_MMKV.read_bytes())
    prefix = b"exe_app_retina_zoom_ratio_" + PACKAGE_PARENT.encode("ascii")
    positions = []
    start = 0
    while True:
        index = blob.find(prefix, start)
        if index < 0:
            break
        positions.append(index)
        start = index + len(prefix)
    if not positions:
        return []
    replacements = 0
    for index in positions:
        end = index + len(prefix)
        while end < len(blob) and blob[end] not in (0x04,):
            end += 1
        if bytes(blob[end:end + 2]) == b"\x04\x03" and end + 5 <= len(blob):
            old = bytes(blob[end + 2:end + 5])
            if old in (b"1.0", b"2.0"):
                blob[end + 2:end + 5] = b"2.0"
                replacements += 1
    if not replacements:
        return []
    actual_size = struct.unpack_from("<I", blob, 0)[0]
    if actual_size <= 0 or actual_size + 4 > len(blob):
        raise FixError("应用宝 MMKV 长度异常，拒绝写入。")
    meta = bytearray(PUBLIC_MMKV_CRC.read_bytes())
    if len(meta) < 4:
        raise FixError("应用宝 MMKV CRC 文件异常，拒绝写入。")
    struct.pack_into("<I", meta, 0, zlib.crc32(blob[4:4 + actual_size]) & 0xFFFFFFFF)
    backups.capture(PUBLIC_MMKV)
    backups.capture(PUBLIC_MMKV_CRC)
    atomic_write(PUBLIC_MMKV, bytes(blob))
    atomic_write(PUBLIC_MMKV_CRC, bytes(meta))
    return [f"将 {replacements} 个启动器/游戏入口设为 Retina 2×"]


def patch_preferences(backups: BackupSet, fps: int) -> list[str]:
    if not PREFERENCES.exists():
        return []
    data = bytearray(PREFERENCES.read_bytes())
    if data[:4] != b"PREF" or len(data) < 32:
        raise FixError("光遇 preferences.sav 格式不符合预期，拒绝写入。")
    counts = struct.unpack_from("<4I", data, 8)
    record_count = sum(counts)
    string_base = struct.unpack_from("<I", data, 24)[0]
    if 28 + record_count * 8 != string_base or string_base >= len(data):
        raise FixError("光遇偏好表结构不符合预期，拒绝写入。")
    found: set[str] = set()
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
            found.add(name)
        elif name == "kUserPreference_MotionBlurScalar":
            struct.pack_into("<f", data, record + 4, 0.0)
            found.add(name)
    if "quality_fps" not in found:
        raise FixError("找不到光遇帧率设置；可能是游戏版本已更新。")
    backups.capture(PREFERENCES)
    atomic_write(PREFERENCES, bytes(data))
    return [f"光遇目标帧率 {fps} FPS、关闭动态模糊"]


def apply_fix(fps: int) -> list[str]:
    stop_related_processes()
    backups = BackupSet()
    changes: list[str] = []
    try:
        changes.extend(patch_registries(backups))
        changes.extend(patch_apps_db(backups))
        changes.extend(patch_mmkv(backups))
        changes.extend(patch_preferences(backups, fps))
    except Exception:
        restore_from(backups.root, announce=False)
        raise
    backups.finish()
    return changes


def find_sky_package() -> str | None:
    if not APPS_DB.exists():
        return None
    for key, record in load_json(APPS_DB).items():
        if key.startswith(PACKAGE_SKY_PREFIX) and (
            record.get("game_id") == "63"
            or str(record.get("install_path", "")).lower().endswith("feverapps\\sky")
        ):
            return key
    return None


def launch() -> None:
    package = find_sky_package()
    child = shortcut_for(package) if package else None
    parent = shortcut_for(PACKAGE_PARENT)
    if child:
        say(f"正在启动《光·遇》：{child.name}")
        open_path(child)
    elif parent:
        say("未找到独立光遇快捷方式，先打开网易发烧游戏平台。")
        open_path(parent)
    else:
        say("未找到应用宝快捷方式，已打开应用宝。")
        open_path(YYB_APP)


def restore_from(root: Path, announce: bool = True) -> None:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        # During an interrupted apply, the in-memory manifest is not available.
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stop_related_processes()
    for item in manifest:
        target = Path(item["path"])
        if item["existed"]:
            source = root / item["backup"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif target.exists():
            target.unlink()
    if announce:
        say(f"已从 {root.name} 恢复。")


def restore_latest() -> None:
    if not LATEST_FILE.exists():
        raise FixError("没有找到可恢复的本地备份。")
    restore_from(Path(LATEST_FILE.read_text(encoding="utf-8").strip()))


def status() -> int:
    checks = {
        "腾讯应用宝": YYB_APP.exists(),
        "应用宝 Wine 引擎": PREFIX.exists(),
        "网易发烧游戏平台": find_fever_launcher() is not None,
        "光遇 PC 国服": SKY_EXE.exists(),
        "应用宝应用数据库": APPS_DB.exists(),
        "光遇偏好文件": PREFERENCES.exists(),
    }
    for label, ok in checks.items():
        say(f"{'✓' if ok else '✗'} {label}")
    if SKY_EXE.exists():
        say(f"  Sky.exe SHA-256: {sha256(SKY_EXE)[:16]}…")
    return 0 if all(checks.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="在 macOS 应用宝中安装、修复并启动光遇 PC 国服")
    parser.add_argument("command", nargs="?", choices=("setup", "fix", "launch", "status", "restore"), default="setup")
    parser.add_argument("--fps", type=int, choices=(30, 60, 120), default=60)
    args = parser.parse_args()
    try:
        if args.command == "status":
            return status()
        if args.command == "restore":
            restore_latest()
            return 0
        if args.command == "launch":
            launch()
            return 0
        if args.command == "setup" and not ensure_prerequisites():
            return 2
        changes = apply_fix(args.fps)
        say("\n修复完成：")
        for change in changes:
            say(f"  ✓ {change}")
        say("所有原文件备份仅保存在本机：" + str(STATE_ROOT / "backups"))
        launch()
        return 0
    except FixError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消。重新运行会从当前阶段续接。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
