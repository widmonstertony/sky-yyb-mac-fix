#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h}"
SUPPORT_ROOT="$HOME/Library/Application Support/YYBIntelLauncher"
BIN_DIR="$SUPPORT_ROOT/bin"
USER_APPS="$HOME/Applications"
AGENT="$HOME/Library/LaunchAgents/local.yybintel.launchpad-sync.plist"
DOMAIN="gui/$(id -u)"

mkdir -p "$BIN_DIR" "$USER_APPS" "$HOME/Library/LaunchAgents"
ditto "$PROJECT_DIR/launch-windows-app" "$BIN_DIR/launch-windows-app"
ditto "$PROJECT_DIR/sync-launchpad-apps.py" "$BIN_DIR/sync-launchpad-apps.py"
ditto "$PROJECT_DIR/apply-intel-retina.py" "$BIN_DIR/apply-intel-retina.py"
ditto "$PROJECT_DIR/download-sky.py" "$BIN_DIR/download-sky.py"
chmod +x "$BIN_DIR/launch-windows-app" "$BIN_DIR/sync-launchpad-apps.py" \
  "$BIN_DIR/apply-intel-retina.py" "$BIN_DIR/download-sky.py"

"$BIN_DIR/apply-intel-retina.py"

ditto "$PROJECT_DIR/app-bundles/Steam（Windows）.app" "$USER_APPS/Steam（Windows）.app"
ditto "$PROJECT_DIR/app-bundles/网易游戏启动器.app" "$USER_APPS/网易游戏启动器.app"
codesign --force --deep --sign - "$USER_APPS/Steam（Windows）.app" >/dev/null
codesign --force --deep --sign - "$USER_APPS/网易游戏启动器.app" >/dev/null

ditto "$PROJECT_DIR/launchpad-sync-agent.plist" "$AGENT"
launchctl bootout "$DOMAIN" "$AGENT" >/dev/null 2>&1 || true
launchctl bootstrap "$DOMAIN" "$AGENT"
launchctl enable "$DOMAIN/local.yybintel.launchpad-sync"

"$BIN_DIR/sync-launchpad-apps.py"

LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [[ -x "$LSREGISTER" ]]; then
  "$LSREGISTER" -f "$USER_APPS/Steam（Windows）.app"
  "$LSREGISTER" -f "$USER_APPS/网易游戏启动器.app"
fi

print "启动台同步已启用。新安装的游戏会在 60 秒内出现为独立 App。"
