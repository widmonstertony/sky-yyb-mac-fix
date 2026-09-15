#!/usr/bin/env python3
"""Mirror installed YYB/Steam games into macOS Launchpad as small .app bundles."""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile
import urllib.request


def home() -> Path:
    override = os.environ.get("YYB_INTEL_TEST_HOME")
    return Path(override).expanduser() if override else Path.home()


HOME = home()
SUPPORT = HOME / "Library/Application Support/YYBIntelLauncher"
PREFIX = HOME / "Library/Application Support/com.tencent.yybmac.wine.engine/wine"
DRIVE_C = PREFIX / "drive_c"
STEAM_ROOT = DRIVE_C / "Program Files (x86)/Steam"
USER_REG = PREFIX / "user.reg"
LAUNCH_SCRIPT = SUPPORT / "bin/launch-windows-app"
APP_ROOT = HOME / "Applications/腾讯应用宝"
ICON_CACHE = SUPPORT / "launchpad-icons"
MANAGED_KEY = "YYBIntelLaunchpadManaged"
LSREGISTER = Path(
    "/System/Library/Frameworks/CoreServices.framework/Frameworks/"
    "LaunchServices.framework/Support/lsregister"
)


@dataclass(frozen=True)
class Game:
    platform: str
    game_id: str
    name: str
    install_path: Path
    local_artwork: Path | None = None
    remote_artwork: str | None = None

    @property
    def bundle_id(self) -> str:
        return f"local.yybintel.game.{self.platform}.{self.game_id}"

    @property
    def launch_arguments(self) -> list[str]:
        if self.platform == "steam":
            return ["steam", "-applaunch", self.game_id]
        return ["netease-game", self.game_id]


def valve_pairs(text: str) -> dict[str, str]:
    return dict(re.findall(r'"([^"]+)"\s+"([^"]*)"', text))


def decode_wine_string(value: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "\\" or index + 1 >= len(value):
            output.append(value[index])
            index += 1
            continue
        marker = value[index + 1]
        if marker == "x":
            match = re.match(r"[0-9a-fA-F]{2,4}", value[index + 2 :])
            if match:
                output.append(chr(int(match.group(0), 16)))
                index += 2 + len(match.group(0))
                continue
        escapes = {"\\": "\\", '"': '"', "n": "\n", "r": "\r", "t": "\t"}
        # Wine registry strings escape backslashes, while Valve VDF paths may
        # reach us with a single Windows path separator.  Preserve unknown
        # escape sequences instead of silently turning ``C:\\Games`` into
        # ``C:Games``.
        output.append(escapes.get(marker, "\\" + marker))
        index += 2
    return "".join(output)


def registry_value(line: str) -> tuple[str, str] | None:
    if not line.startswith('"') or "=" not in line:
        return None
    key, raw_value = line.split("=", 1)
    if not key.endswith('"'):
        return None
    key = key[1:-1]
    if raw_value.startswith('"') and raw_value.endswith('"'):
        raw_value = raw_value[1:-1]
    return key, raw_value


def byte_array_json(value: str | None) -> dict:
    if not value or not value.startswith("@ByteArray(") or not value.endswith(")"):
        return {}
    try:
        data = base64.b64decode(value[len("@ByteArray(") : -1], validate=True)
        decoded = json.loads(data.decode("utf-8"))
        return decoded if isinstance(decoded, dict) else {}
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def windows_path(value: str) -> Path | None:
    normalized = decode_wine_string(value).replace("\\", "/")
    match = re.fullmatch(r"([A-Za-z]):/(.*)", normalized)
    if not match:
        return None
    drive, rest = match.group(1).lower(), match.group(2)
    if drive == "c":
        return DRIVE_C / rest
    if drive == "z":
        return Path("/") / rest
    link = PREFIX / f"dosdevices/{drive}:"
    if link.exists():
        return link.resolve() / rest
    return None


def first_existing_executable(folder: Path, preferred: str | None) -> Path | None:
    if preferred:
        target = folder / preferred.replace("\\", "/")
        if target.is_file():
            return target
    try:
        return next(item for item in folder.iterdir() if item.is_file() and item.suffix.lower() == ".exe")
    except (OSError, StopIteration):
        return None


def steam_libraries() -> list[Path]:
    libraries = [STEAM_ROOT]
    folders = STEAM_ROOT / "steamapps/libraryfolders.vdf"
    try:
        text = folders.read_text(encoding="utf-8")
    except OSError:
        return libraries
    for raw_path in re.findall(r'"path"\s+"([^"]+)"', text):
        path = windows_path(raw_path)
        if path and path not in libraries:
            libraries.append(path)
    return libraries


def steam_artwork(app_id: str) -> Path | None:
    folder = STEAM_ROOT / f"appcache/librarycache/{app_id}"
    for name in (
        "library_600x900_schinese.jpg",
        "library_600x900_schinese.png",
        "library_header_schinese.jpg",
        "library_header.jpg",
        "header_schinese.jpg",
        "header.jpg",
        "library_600x900.jpg",
        "library_600x900.png",
    ):
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def discover_steam_games() -> list[Game]:
    games: list[Game] = []
    seen: set[str] = set()
    for library in steam_libraries():
        steamapps = library / "steamapps"
        for manifest in steamapps.glob("appmanifest_*.acf"):
            try:
                values = valve_pairs(manifest.read_text(encoding="utf-8"))
            except OSError:
                continue
            app_id = values.get("appid", "")
            install_dir = values.get("installdir", "")
            game_dir = steamapps / "common" / install_dir
            if (
                not app_id.isdecimal()
                or app_id in seen
                or values.get("StateFlags") != "4"
                or not game_dir.is_dir()
            ):
                continue
            try:
                if not any(game_dir.iterdir()):
                    continue
            except OSError:
                continue
            seen.add(app_id)
            games.append(
                Game(
                    platform="steam",
                    game_id=app_id,
                    name=values.get("name") or f"Steam 游戏 {app_id}",
                    install_path=game_dir,
                    local_artwork=steam_artwork(app_id),
                )
            )
    return games


def discover_netease_games() -> list[Game]:
    try:
        text = USER_REG.read_text(encoding="utf-8")
    except OSError:
        return []
    prefix = r"[Software\\FeverGames\\FeverGamesInstaller\\game\\"
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith(prefix) and line.endswith("]"):
            current = line[len(prefix) : -1]
            continue
        if line.startswith("["):
            current = None
            continue
        if current is None:
            continue
        pair = registry_value(line)
        if pair:
            sections.setdefault(current, {})[pair[0]] = pair[1]

    games: list[Game] = []
    for game_id, values in sections.items():
        if not game_id.isdecimal():
            continue
        info = byte_array_json(values.get("GameInfo"))
        folder = windows_path(values.get("InstallPath", ""))
        if folder is None or not folder.is_dir():
            continue
        executable = first_existing_executable(folder, info.get("startup_path"))
        if executable is None:
            continue
        name = info.get("display_name") or decode_wine_string(values.get("DisplayName", ""))
        if not name:
            name = f"网易游戏 {game_id}"
        artwork = next(
            (
                info.get(key)
                for key in ("icon", "logo", "app_build_pkg_icon", "game_library_logo", "main_image")
                if isinstance(info.get(key), str) and info.get(key)
            ),
            None,
        )
        games.append(
            Game(
                platform="netease",
                game_id=game_id,
                name=name,
                install_path=folder,
                remote_artwork=artwork,
            )
        )
    # FeverGames' legacy Intel downloader can fail before it commits its game
    # registry record. The official payload is still a valid installation once
    # Sky.exe exists, so keep Launchpad discovery independent of that IPC step.
    sky_dir = DRIVE_C / "FeverApps/sky"
    if not any(game.game_id == "63" for game in games):
        sky_executable = first_existing_executable(sky_dir, "Sky.exe")
        if sky_executable is not None:
            games.append(
                Game(
                    platform="netease",
                    game_id="63",
                    name="光·遇",
                    install_path=sky_dir,
                )
            )
    return games


def safe_app_name(name: str) -> str:
    cleaned = name.strip().replace("/", "／").replace(":", "：")
    cleaned = re.sub(r"[\x00-\x1f]", "", cleaned)
    return cleaned[:120] or "Windows 游戏"


def managed_app_path(game: Game) -> Path:
    preferred = APP_ROOT / f"{safe_app_name(game.name)}.app"
    if not preferred.exists() or is_managed(preferred):
        return preferred
    suffix = "Steam" if game.platform == "steam" else "网易"
    return APP_ROOT / f"{safe_app_name(game.name)}（{suffix}）.app"


def is_managed(app: Path) -> bool:
    try:
        with (app / "Contents/Info.plist").open("rb") as stream:
            return bool(plistlib.load(stream).get(MANAGED_KEY))
    except (OSError, plistlib.InvalidFileException):
        return False


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def fetch_artwork(url: str) -> Path | None:
    ICON_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    cached = ICON_CACHE / f"{key}.image"
    if cached.is_file() and cached.stat().st_size > 0:
        return cached
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "YYB-Intel-Launchpad-Sync/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            data = response.read(8 * 1024 * 1024)
        if data:
            cached.write_bytes(data)
            return cached
    except OSError:
        pass
    return None


def make_icns(source: Path, output: Path) -> bool:
    if not source.is_file():
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="yyb-icon-") as temp_name:
            temp = Path(temp_name)
            large = temp / "large.png"
            square = temp / "square.png"
            iconset = temp / "Game.iconset"
            iconset.mkdir()
            subprocess.run(
                ["sips", "-s", "format", "png", "-Z", "1024", str(source), "--out", str(large)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["sips", "-p", "1024", "1024", "--padColor", "151927", str(large), "--out", str(square)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for size, names in {
                16: ("icon_16x16.png",),
                32: ("icon_16x16@2x.png", "icon_32x32.png"),
                64: ("icon_32x32@2x.png",),
                128: ("icon_128x128.png",),
                256: ("icon_128x128@2x.png", "icon_256x256.png"),
                512: ("icon_256x256@2x.png", "icon_512x512.png"),
                1024: ("icon_512x512@2x.png",),
            }.items():
                rendered = temp / f"rendered-{size}.png"
                subprocess.run(
                    ["sips", "-z", str(size), str(size), str(square), "--out", str(rendered)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                for name in names:
                    shutil.copy2(rendered, iconset / name)
            subprocess.run(
                ["iconutil", "-c", "icns", str(iconset), "-o", str(output)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return output.is_file()
    except (OSError, subprocess.CalledProcessError):
        return False


def fallback_icon(game: Game) -> Path | None:
    if game.platform == "steam":
        candidate = HOME / "Applications/Steam（Windows）.app/Contents/Resources/Steam.icns"
    else:
        candidate = HOME / "Applications/网易游戏启动器.app/Contents/Resources/FeverGames.icns"
    return candidate if candidate.is_file() else None


def write_game_app(game: Game) -> Path:
    app = managed_app_path(game)
    contents = app / "Contents"
    executable_dir = contents / "MacOS"
    resources = contents / "Resources"
    executable_dir.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    info = {
        "CFBundleDevelopmentRegion": "zh_CN",
        "CFBundleDisplayName": game.name,
        "CFBundleExecutable": "start",
        "CFBundleIconFile": "GameIcon",
        "CFBundleIdentifier": game.bundle_id,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": game.name,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "LSApplicationCategoryType": "public.app-category.games",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        MANAGED_KEY: True,
        "YYBPlatform": game.platform,
        "YYBGameID": game.game_id,
        "YYBInstallPath": str(game.install_path),
    }
    with (contents / "Info.plist").open("wb") as stream:
        plistlib.dump(info, stream, sort_keys=True)

    arguments = " ".join(shell_quote(item) for item in game.launch_arguments)
    start = executable_dir / "start"
    start.write_text(
        "#!/bin/zsh\n"
        f"exec \"$HOME/Library/Application Support/YYBIntelLauncher/bin/launch-windows-app\" {arguments}\n",
        encoding="utf-8",
    )
    start.chmod(0o755)

    icon = resources / "GameIcon.icns"
    source = game.local_artwork
    if source is None and game.remote_artwork:
        source = fetch_artwork(game.remote_artwork)
    if source is None or not make_icns(source, icon):
        fallback = fallback_icon(game)
        if fallback:
            shutil.copy2(fallback, icon)

    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(app)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return app


def remove_stale_apps(expected_ids: set[str]) -> int:
    removed = 0
    if not APP_ROOT.exists():
        return removed
    for app in APP_ROOT.glob("*.app"):
        try:
            with (app / "Contents/Info.plist").open("rb") as stream:
                info = plistlib.load(stream)
        except (OSError, plistlib.InvalidFileException):
            continue
        if info.get(MANAGED_KEY) and info.get("CFBundleIdentifier") not in expected_ids:
            shutil.rmtree(app)
            removed += 1
    return removed


def register(app: Path) -> None:
    if LSREGISTER.is_file():
        subprocess.run(
            [str(LSREGISTER), "-f", str(app)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def sync(dry_run: bool = False) -> tuple[list[Game], int]:
    games = discover_steam_games() + discover_netease_games()
    games.sort(key=lambda game: (game.platform, game.name.casefold()))
    if dry_run:
        return games, 0

    APP_ROOT.mkdir(parents=True, exist_ok=True)
    expected = {game.bundle_id for game in games}
    apps = [write_game_app(game) for game in games]
    removed = remove_stale_apps(expected)
    for app in apps:
        register(app)
    for launcher in (
        HOME / "Applications/Steam（Windows）.app",
        HOME / "Applications/网易游戏启动器.app",
    ):
        if launcher.exists():
            register(launcher)
    return games, removed


def main() -> int:
    parser = argparse.ArgumentParser(description="把应用宝/Steam 已安装游戏同步到 macOS 启动台")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    games, removed = sync(args.dry_run)
    for game in games:
        print(f"{game.platform}: {game.name} [{game.game_id}]")
    if not args.dry_run:
        print(f"已同步 {len(games)} 个游戏图标，清理 {removed} 个过期图标。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
