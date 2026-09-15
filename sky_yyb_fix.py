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
import platform
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
SCRIPT_ROOT = Path(__file__).resolve().parent
GPU_COMPAT_SOURCE = SCRIPT_ROOT / "compat/apple_silicon_vulkan_compat.c"
GPU_COMPAT_DIR = STATE_ROOT / "compat"
GPU_COMPAT_DYLIB = GPU_COMPAT_DIR / "libSkyYYBGPUCompat.dylib"


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


def find_engine_app() -> Path | None:
    base = YYB_DATA / "ExeEngineDownload"
    if not base.exists():
        return None
    candidates = []
    for app in base.glob("*.app"):
        wineserver = app / "Contents/MacOS/wineserver"
        moltenvk = app / "Contents/Frameworks/libMoltenVK.dylib"
        if wineserver.exists() and moltenvk.exists():
            candidates.append(app)
    return max(candidates, key=lambda item: item.stat().st_mtime) if candidates else None


def engine_wineserver() -> Path | None:
    app = find_engine_app()
    return app / "Contents/MacOS/wineserver" if app else None


def is_apple_m4() -> bool:
    if platform.machine() != "arm64" or os.environ.get("SKY_YYB_TEST_HOME"):
        return False
    result = subprocess.run(
        ["sysctl", "-n", "machdep.cpu.brand_string"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip().startswith("Apple M4")


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
        "FeverGamesWeb",
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
    if YYB_SHORTCUTS.exists():
        for executable in YYB_SHORTCUTS.glob("*.app/Contents/MacOS/YYBPackage"):
            subprocess.run(
                ["pkill", "-f", str(executable)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    # Wine launchers appear under truncated Windows paths in macOS process
    # listings, so name-based pkill does not actually stop them. Ask the YYB
    # wineserver to close the whole prefix before editing its live databases.
    wineserver = engine_wineserver()
    if wineserver:
        environment = os.environ.copy()
        environment["WINEPREFIX"] = str(PREFIX)
        subprocess.run(
            [str(wineserver), "-k"],
            env=environment,
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


def open_new_path(path: Path) -> None:
    if os.environ.get("SKY_YYB_TEST_HOME"):
        say(f"[test] open new {path}")
        return
    subprocess.run(["open", "-n", str(path)], check=True)


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


def patch_fever_shortcuts(backups: BackupSet) -> list[str]:
    programs = PREFIX / "drive_c/users"
    if not programs.exists():
        return []
    pattern = re.compile(
        rb"(?m)^URL=fevergames://mygame/\?gameId=63[^\r\n]*"
    )
    replacement = b"URL=fevergames://mygame/?gameId=63&autoRun=1"
    changed = 0
    # YYB rebuilds apps.db from both the Desktop and Start Menu copies. Patch
    # every matching shortcut source so the cached entry cannot regress.
    for shortcut in programs.rglob("*.url"):
        data = shortcut.read_bytes()
        if not pattern.search(data):
            continue
        updated = pattern.sub(replacement, data)
        if updated == data:
            continue
        backups.capture(shortcut)
        atomic_write(shortcut, updated)
        changed += 1
    return [f"修复 {changed} 个发烧平台自动启动入口"] if changed else []


def ensure_gpu_compat() -> bool:
    if not is_apple_m4():
        return False
    engine = find_engine_app()
    if not engine:
        raise FixError("未找到应用宝 Wine 引擎，无法安装 Apple Silicon GPU 兼容层。")
    moltenvk = engine / "Contents/Frameworks/libMoltenVK.dylib"
    if not GPU_COMPAT_SOURCE.exists():
        raise FixError(f"GPU 兼容层源码缺失：{GPU_COMPAT_SOURCE}")
    compiler = Path("/usr/bin/clang")
    if not compiler.exists():
        raise FixError("需要 Apple clang 编译 M4 兼容层；请先安装 Xcode Command Line Tools。")

    ensure_private_dir(GPU_COMPAT_DIR)
    signature = hashlib.sha256(
        GPU_COMPAT_SOURCE.read_bytes()
        + str(moltenvk.stat().st_mtime_ns).encode("ascii")
        + str(moltenvk.stat().st_size).encode("ascii")
    ).hexdigest()
    stamp = GPU_COMPAT_DIR / "build.json"
    try:
        current = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        current = {}
    if GPU_COMPAT_DYLIB.exists() and current.get("signature") == signature:
        return True

    temporary = GPU_COMPAT_DYLIB.with_suffix(".dylib.new")
    command = [
        str(compiler),
        "-arch", "x86_64",
        "-Os",
        "-dynamiclib",
        "-Wall", "-Wextra", "-Werror",
        f"-Wl,-rpath,{moltenvk.parent}",
        "-o", str(temporary),
        str(GPU_COMPAT_SOURCE),
        str(moltenvk),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        temporary.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise FixError("M4 GPU 兼容层编译失败：" + (detail[-1] if detail else "未知错误"))
    temporary.chmod(0o700)
    os.replace(temporary, GPU_COMPAT_DYLIB)
    atomic_write(
        stamp,
        (json.dumps({"signature": signature}, indent=2) + "\n").encode("utf-8"),
        0o600,
    )
    return True


def start_gpu_compat_engine() -> bool:
    if not ensure_gpu_compat():
        return False
    engine = find_engine_app()
    if not engine:
        raise FixError("应用宝 Wine 引擎不完整。")
    # Starting the engine app directly is intentionally session-only: it avoids
    # modifying or re-signing Tencent's app while ensuring its Wine children
    # inherit the compatibility library. The parent Fever shortcut can then
    # connect normally; the generated Sky child shortcut cannot initialize the
    # engine this way and otherwise stalls at 99%.
    subprocess.run(
        [
            "open", "-n",
            "--env", f"WINEPREFIX={PREFIX}",
            "--env", "SKY_YYB_GPU_COMPAT=1",
            "--env", f"DYLD_INSERT_LIBRARIES={GPU_COMPAT_DYLIB}",
            str(engine),
        ],
        check=True,
    )
    time.sleep(8)
    return True


def patch_mmkv(backups: BackupSet) -> list[str]:
    if not PUBLIC_MMKV.exists() or not PUBLIC_MMKV_CRC.exists():
        return []
    blob = bytearray(PUBLIC_MMKV.read_bytes())
    prefix = b"exe_app_retina_zoom_ratio_" + PACKAGE_PARENT.encode("ascii")
    actual_size = struct.unpack_from("<I", blob, 0)[0]
    if actual_size <= 0 or actual_size + 4 > len(blob):
        raise FixError("应用宝 MMKV 长度异常，拒绝写入。")
    meta = bytearray(PUBLIC_MMKV_CRC.read_bytes())
    if len(meta) < 40:
        raise FixError("应用宝 MMKV CRC 文件异常，拒绝写入。")
    original_crc = zlib.crc32(blob[4:4 + actual_size]) & 0xFFFFFFFF
    if struct.unpack_from("<I", meta, 0)[0] != original_crc:
        raise FixError("应用宝 MMKV 校验不一致；请完全退出应用宝后重试。")
    version = struct.unpack_from("<I", meta, 4)[0]
    if version >= 3 and struct.unpack_from("<I", meta, 28)[0] != actual_size:
        raise FixError("应用宝 MMKV 元数据长度不一致，拒绝写入。")
    if any(meta[12:28]) or (len(meta) >= 112 and any(meta[104:112])):
        raise FixError("不支持加密或带过期配置的 MMKV，拒绝写入。")
    positions = []
    start = 0
    while True:
        index = blob.find(prefix, start, actual_size + 4)
        if index < 0:
            break
        positions.append(index)
        start = index + len(prefix)
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
    # A fresh YYB install has no saved zoom records. Append ordinary MMKV
    # string entries instead of silently reporting success without enabling HD.
    packages = [PACKAGE_PARENT]
    sky_package = find_sky_package()
    if sky_package:
        packages.append(sky_package)
    def varint(value: int) -> bytes:
        result = bytearray()
        while value >= 128:
            result.append((value & 127) | 128)
            value >>= 7
        result.append(value)
        return bytes(result)
    additions = bytearray()
    for package in packages:
        key = b"exe_app_retina_zoom_ratio_" + package.encode("ascii")
        # Appending also supersedes an older entry or a tombstone for this key.
        additions.extend(varint(len(key)) + key + b"\x04\x032.0")
    end = actual_size + 4
    needed = end + len(additions)
    if needed > len(blob):
        blob.extend(b"\0" * (((needed + 16383) // 16384) * 16384 - len(blob)))
    blob[end:needed] = additions
    actual_size += len(additions)
    struct.pack_into("<I", blob, 0, actual_size)
    crc = zlib.crc32(blob[4:4 + actual_size]) & 0xFFFFFFFF
    struct.pack_into("<I", meta, 0, crc)
    # Tencent MMKV v3+ stores both the current and last-confirmed sizes/CRCs.
    # Keep the full-write sequence in sync so other readers reload the file.
    struct.pack_into("<I", meta, 8, (struct.unpack_from("<I", meta, 8)[0] + 1) & 0xFFFFFFFF)
    if version >= 3:
        struct.pack_into("<III", meta, 28, actual_size, actual_size, crc)
    backups.capture(PUBLIC_MMKV)
    backups.capture(PUBLIC_MMKV_CRC)
    atomic_write(PUBLIC_MMKV, bytes(blob))
    atomic_write(PUBLIC_MMKV_CRC, bytes(meta))
    return [f"将 {len(packages)} 个启动器/游戏入口设为 Retina 2×"]


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
        # The initial PREF only contains first_open_ts and readback settings.
        # Graphics preferences are created after the first successful session.
        return ["帧率设置待首次成功进入游戏后生成；本次保留偏好文件"]
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
        changes.extend(patch_fever_shortcuts(backups))
        changes.extend(patch_mmkv(backups))
        changes.extend(patch_preferences(backups, fps))
        if ensure_gpu_compat():
            changes.append("Apple M4 Vulkan 设备兼容层")
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
    gpu_compat = start_gpu_compat_engine()
    if gpu_compat:
        say("已启用 Apple M4 Vulkan 兼容启动环境。")
    package = find_sky_package()
    child = shortcut_for(package) if package else None
    parent = shortcut_for(PACKAGE_PARENT)
    if gpu_compat and parent:
        # Fever 1.18 ignores autoRun on this YYB engine, while its parent entry
        # reliably joins the already-running compatible engine. Keep the login
        # and anti-cheat flow intact and let the user press Start in Fever.
        say("正在启动网易发烧游戏平台；请在平台里点“开始游戏”。")
        open_new_path(parent)
    elif child:
        say(f"正在启动《光·遇》：{child.name}")
        open_new_path(child)
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
    if is_apple_m4():
        checks["Apple M4 GPU 兼容层"] = GPU_COMPAT_DYLIB.exists()
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
