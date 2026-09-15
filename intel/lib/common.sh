#!/bin/zsh

set -euo pipefail

COMMON_FILE="${${(%):-%N}:A}"
PROJECT_DIR="${COMMON_FILE:h:h}"

RUNTIME_DIR="$PROJECT_DIR/.runtime"
USER_HOME="${HOME:?HOME is not set}"
INSTALLED_ROOT="$USER_HOME/Library/Application Support/YYBIntelLauncher"
INSTALLED_ENGINE="$INSTALLED_ROOT/.runtime/wine-engine.app"

if [[ -x "$INSTALLED_ENGINE/Contents/MacOS/wineserver" ]]; then
  ENGINE_APP="$INSTALLED_ENGINE"
  INTEL_LOADER="$INSTALLED_ROOT/wine-loader"
  SERVER_WRAPPER="$INSTALLED_ROOT/wineserver-wrapper"
  SERVER_HOST_APP="$INSTALLED_ROOT/WineServerHost.app"
else
  ENGINE_APP="$RUNTIME_DIR/wine-engine.app"
  INTEL_LOADER="$PROJECT_DIR/wine-loader"
  SERVER_WRAPPER="$PROJECT_DIR/wineserver-wrapper"
  SERVER_HOST_APP="$PROJECT_DIR/WineServerHost.app"
fi

ENGINE_CONTENTS="$ENGINE_APP/Contents"
WINE_ROOT="$ENGINE_CONTENTS/SharedSupport/wine"
WINE_LIB="$WINE_ROOT/lib/wine"
WINDOWS_BUILTINS="$WINE_LIB/x86_64-windows"
FRAMEWORKS="$ENGINE_CONTENTS/Frameworks"
YYB_SUPPORT="$USER_HOME/Library/Application Support/com.tencent.yybmac.wine.engine"
WINE_PREFIX="$YYB_SUPPORT/wine"
LAUNCH_LOG="$RUNTIME_DIR/launcher.log"

check_ready() {
  if [[ "$(uname -m)" != "x86_64" ]]; then
    print -u2 "这个启动器只用于 Intel Mac。"
    return 1
  fi

  if [[ ! -x "$INTEL_LOADER" || ! -x "$ENGINE_CONTENTS/MacOS/wineserver" ]]; then
    print -u2 "运行环境还没准备好。请先双击 1-setup.command。"
    return 1
  fi
}

wine_env() {
  local debug_mode="${YYB_WINEDEBUG:--all}"
  env \
    YYB_NTDLL_PATH="$WINE_LIB/x86_64-unix/ntdll.so" \
    YYB_WINESERVER_HOST_APP="$SERVER_HOST_APP" \
    WINEPREFIX="$WINE_PREFIX" \
    WINESERVER="$SERVER_WRAPPER" \
    WINELOADER="$INTEL_LOADER" \
    WINEDLLPATH="$WINE_LIB" \
    DYLD_FALLBACK_LIBRARY_PATH="$FRAMEWORKS" \
    GFX_BACKEND_PATH="$FRAMEWORKS/render/dxvk/wine" \
    WINE_RETINA_MODE=1 \
    WINE_RETINA_SCALE=2.0 \
    QT_ENABLE_HIGHDPI_SCALING=1 \
    QT_AUTO_SCREEN_SCALE_FACTOR=1 \
    QT_SCALE_FACTOR=1 \
    QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --disable-gpu-compositing --disable-direct-composition --force-device-scale-factor=2" \
    DXVK_HUD=0 \
    MTL_HUD_ENABLED=0 \
    D3DM_ENABLE_METALFX=0 \
    WINEDEBUG="$debug_mode" \
    "$INTEL_LOADER" "$@"
}

start_engine_host() {
  local server="$ENGINE_CONTENTS/MacOS/wineserver"
  local device inode server_socket
  device="$(stat -f %d "$WINE_PREFIX")"
  inode="$(stat -f %i "$WINE_PREFIX")"
  server_socket="/tmp/.wine-$(id -u)/server-$(printf '%x' "$device")-$(printf '%x' "$inode")/socket"

  # Tencent's engine admits new top-level clients through a one-session lock.
  # If the previous Windows app has exited but its persistent server remains,
  # restart only that idle server before starting the next app.
  if pgrep -f "$server" >/dev/null 2>&1 && ! pgrep -f "$INTEL_LOADER" >/dev/null 2>&1; then
    pkill -f "$server" >/dev/null 2>&1 || true
    for _ in {1..50}; do
      pgrep -f "$server" >/dev/null 2>&1 || break
      sleep 0.1
    done
  fi

  if ! pgrep -f "$server" >/dev/null 2>&1; then
    # Wine leaves the socket pathname behind when an earlier test is stopped.
    # Remove only that prefix-specific stale socket before starting a new host.
    [[ -S "$server_socket" ]] && rm -f "$server_socket"
    /usr/bin/open -n -gj "$SERVER_HOST_APP" --args -p120
  fi

  local attempt
  for attempt in {1..150}; do
    if [[ -S "$server_socket" ]] && pgrep -f "$server" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done

  print -u2 "腾讯 PC 游戏后台没有成功启动。"
  return 1
}

run_windows() {
  check_ready
  mkdir -p "$RUNTIME_DIR" "$YYB_SUPPORT/apps" "$YYB_SUPPORT/appsdata" "$WINE_PREFIX"
  start_engine_host
  # Do not expose the caller's Documents/Desktop working directory to Wine.
  # macOS privacy checks can suspend the server while it resolves that cwd.
  (
    cd "$WINE_PREFIX/drive_c"
    wine_env "$@"
  )
}
