#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h}"
RUNTIME_DIR="$PROJECT_DIR/.runtime"
DMG_PATH="$RUNTIME_DIR/mac_yyb_0.6.5.1684.dmg"
DMG_URL="https://downmac.yyb.qq.com/channel/formal/raw/fPyBcvLYsbHR04zD/mac_yyb_0.6.5.1684.dmg"
DMG_SHA256="80384908d2ec01408a3ed9e4602d0b495d79b268a07f06a9bac7d7c1bb399edd"
MOUNT_DIR=""

cleanup() {
  if [[ -n "$MOUNT_DIR" && -d "$MOUNT_DIR" ]]; then
    hdiutil detach "$MOUNT_DIR" -quiet 2>/dev/null || true
    rmdir "$MOUNT_DIR" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [[ "$(uname -m)" != "x86_64" ]]; then
  print -u2 "这套方案只为 Intel Mac 准备。"
  exit 1
fi

/usr/bin/python3 "$PROJECT_DIR/apply-intel-retina.py" --stop

mkdir -p "$RUNTIME_DIR"

if [[ ! -d "$RUNTIME_DIR/wine-engine.app" ]]; then
  if [[ -n "${YYB_DMG_PATH:-}" ]]; then
    SOURCE_DMG="$YYB_DMG_PATH"
  elif [[ -f "$DMG_PATH" ]]; then
    SOURCE_DMG="$DMG_PATH"
  elif [[ -f /private/tmp/mac_yyb_0.6.5.1684.dmg ]]; then
    SOURCE_DMG=/private/tmp/mac_yyb_0.6.5.1684.dmg
  else
    print "正在从腾讯官网下载应用宝运行环境（约 1.27 GB）……"
    curl --fail --location --progress-bar "$DMG_URL" --output "$DMG_PATH"
    SOURCE_DMG="$DMG_PATH"
  fi

  if [[ ! -f "$SOURCE_DMG" ]]; then
    print -u2 "找不到腾讯应用宝安装镜像：$SOURCE_DMG"
    exit 1
  fi

  ACTUAL_SHA256="$(shasum -a 256 "$SOURCE_DMG" | awk '{print $1}')"
  if [[ "$ACTUAL_SHA256" != "$DMG_SHA256" ]]; then
    print -u2 "下载文件校验失败，没有继续安装。"
    print -u2 "实际 SHA-256：$ACTUAL_SHA256"
    exit 1
  fi

  MOUNTED_ENGINE_ZIP="/Volumes/腾讯应用宝/YYBMacApp.app/Contents/Resources/wine-engine.zip"
  if [[ -f "$MOUNTED_ENGINE_ZIP" ]]; then
    ENGINE_ZIP="$MOUNTED_ENGINE_ZIP"
  else
    MOUNT_DIR="$(mktemp -d /private/tmp/yyb-intel-mount.XXXXXX)"
    hdiutil attach "$SOURCE_DMG" -nobrowse -readonly -mountpoint "$MOUNT_DIR" -quiet
    ENGINE_ZIP="$MOUNT_DIR/YYBMacApp.app/Contents/Resources/wine-engine.zip"
  fi
  if [[ ! -f "$ENGINE_ZIP" ]]; then
    print -u2 "腾讯安装包结构已改变，找不到 PC 游戏引擎。"
    exit 1
  fi
  print "正在解压 PC 游戏运行引擎……"
  ditto -x -k "$ENGINE_ZIP" "$RUNTIME_DIR"
fi

print "正在编译 Intel 兼容启动器……"
mkdir -p "$PROJECT_DIR/WineServerHost.app/Contents/MacOS"
clang -O2 -Wall -Wextra \
  -Wl,-segalign,0x1000 \
  -Wl,-pagezero_size,0x1000 \
  -Wl,-no_pie \
  -Wl,-image_base,0x200000000 \
  -Wl,-no_huge \
  -Wl,-no_fixup_chains \
  -Wl,-segaddr,WINE_RESERVE,0x1000 \
  -Wl,-segaddr,WINE_TOP_DOWN,0x7ff000000000 \
  -o "$PROJECT_DIR/wine-loader" \
  "$PROJECT_DIR/wine_loader.c"

clang -O2 -Wall -Wextra \
  -o "$PROJECT_DIR/wineserver-wrapper" \
  "$PROJECT_DIR/wineserver_wrapper.c"

clang -O2 -Wall -Wextra \
  -o "$PROJECT_DIR/WineServerHost.app/Contents/MacOS/host" \
  "$PROJECT_DIR/wineserver_host.c"

clang -O2 -Wall -Wextra \
  -o "$PROJECT_DIR/patch-ws2" \
  "$PROJECT_DIR/patch_ws2_32.c"

clang -O2 -Wall -Wextra \
  -o "$PROJECT_DIR/patch-retina-engine" \
  "$PROJECT_DIR/patch_retina_engine.c"

clang++ -std=c++17 -O2 -Wall -Wextra \
  "$PROJECT_DIR/launch_via_engine.cpp" \
  -L "$RUNTIME_DIR/wine-engine.app/Contents/Frameworks" \
  -lengine \
  -Wl,-rpath,@executable_path/../Frameworks \
  -framework AppKit \
  -framework Foundation \
  -o "$PROJECT_DIR/winelauncher"

INSTALLED_BIN="$HOME/Library/Application Support/YYBIntelLauncher"
mkdir -p "$INSTALLED_BIN/.runtime" "$INSTALLED_BIN/lib" "$INSTALLED_BIN/bin"
if [[ ! -x "$INSTALLED_BIN/.runtime/wine-engine.app/Contents/MacOS/wineserver" ]]; then
  print "正在把运行环境安装到用户资料库……"
  ditto "$RUNTIME_DIR/wine-engine.app" "$INSTALLED_BIN/.runtime/wine-engine.app"
fi
ditto "$PROJECT_DIR/wine-loader" "$INSTALLED_BIN/wine-loader"
ditto "$PROJECT_DIR/wineserver-wrapper" "$INSTALLED_BIN/wineserver-wrapper"
ditto "$PROJECT_DIR/WineServerHost.app" "$INSTALLED_BIN/WineServerHost.app"
ditto "$PROJECT_DIR/lib/common.sh" "$INSTALLED_BIN/lib/common.sh"
ditto "$PROJECT_DIR/launch-windows-app" "$INSTALLED_BIN/bin/launch-windows-app"
ditto "$PROJECT_DIR/winelauncher" \
  "$INSTALLED_BIN/.runtime/wine-engine.app/Contents/MacOS/winelauncher"
ENGINE_WINELOADER="$INSTALLED_BIN/.runtime/wine-engine.app/Contents/MacOS/wineloader"
if [[ -f "$ENGINE_WINELOADER.yyb-intel-original" ]]; then
  ditto "$ENGINE_WINELOADER.yyb-intel-original" "$ENGINE_WINELOADER"
fi
plutil -replace NSHighResolutionCapable -bool YES \
  "$INSTALLED_BIN/.runtime/wine-engine.app/Contents/Info.plist"

WS2_DLL="$INSTALLED_BIN/.runtime/wine-engine.app/Contents/SharedSupport/wine/lib/wine/x86_64-windows/ws2_32.dll"
if [[ -f "$WS2_DLL" ]]; then
  if [[ ! -f "$WS2_DLL.yyb-intel-original" ]]; then
    ditto "$WS2_DLL" "$WS2_DLL.yyb-intel-original"
  fi
  "$PROJECT_DIR/patch-ws2" "$WS2_DLL"
fi
ENGINE_LIB="$INSTALLED_BIN/.runtime/wine-engine.app/Contents/Frameworks/libengine.dylib"
if [[ -f "$ENGINE_LIB.yyb-intel-original" ]]; then
  ditto "$ENGINE_LIB.yyb-intel-original" "$ENGINE_LIB"
fi
WINEMAC_LIB="$INSTALLED_BIN/.runtime/wine-engine.app/Contents/SharedSupport/wine/lib/wine/x86_64-unix/winemac.so"
if [[ ! -f "$WINEMAC_LIB.yyb-intel-original" ]]; then
  ditto "$WINEMAC_LIB" "$WINEMAC_LIB.yyb-intel-original"
fi
ditto "$WINEMAC_LIB.yyb-intel-original" "$WINEMAC_LIB"
"$PROJECT_DIR/patch-retina-engine" "$WINEMAC_LIB"
codesign --force --sign - "$INSTALLED_BIN/WineServerHost.app" >/dev/null
codesign --force --deep --sign - \
  "$INSTALLED_BIN/.runtime/wine-engine.app" >/dev/null

if [[ "$(file "$PROJECT_DIR/wine-loader")" != *"x86_64"* ]]; then
  print -u2 "启动器编译结果不是 Intel 版本。"
  exit 1
fi

chmod +x "$PROJECT_DIR/wineserver-wrapper" \
  "$PROJECT_DIR/2-install-steam.command" \
  "$PROJECT_DIR/3-install-netease.command" \
  "$PROJECT_DIR/4-run-netease.command" \
  "$PROJECT_DIR/5-run-steam.command" \
  "$PROJECT_DIR/7-install-launchpad-sync.command" \
  "$PROJECT_DIR/install-all.command" \
  "$PROJECT_DIR/install.command" \
  "$PROJECT_DIR/restore.command" \
  "$PROJECT_DIR/launch-windows-app" \
  "$PROJECT_DIR/apply-intel-retina.py" \
  "$PROJECT_DIR/download-sky.py" \
  "$PROJECT_DIR/sky-dock-watch.py" \
  "$PROJECT_DIR/windows-app-process.py" \
  "$PROJECT_DIR/sync-launchpad-apps.py"

"$PROJECT_DIR/7-install-launchpad-sync.command"

print
print "准备完成。"
print "这个窗口可以关掉了。"
