#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h}"
GUI_DIR="$PROJECT_DIR/gui"
APP="/Applications/Windows 游戏.app"
CONTENTS="$APP/Contents"
EXECUTABLE="$CONTENTS/MacOS/YYBGameLauncher"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

print "正在构建 Intel 原生 Windows 游戏库……"
mkdir -p "$GUI_DIR/.build"
clang -arch x86_64 -fobjc-arc -O2 -Wall -Wextra -framework Cocoa \
  -mmacosx-version-min=14.0 \
  -o "$GUI_DIR/.build/YYBGameLauncher" \
  "$GUI_DIR/YYBGameLauncher.m"

mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources"
ditto "$GUI_DIR/.build/YYBGameLauncher" "$EXECUTABLE"
ditto "$GUI_DIR/App/Info.plist" "$CONTENTS/Info.plist"
chmod +x "$EXECUTABLE"
codesign --force --deep --sign - "$APP" >/dev/null

if [[ -x "$LSREGISTER" ]]; then
  "$LSREGISTER" -f "$APP"
fi
mdimport -i "$APP" >/dev/null 2>&1 || true

print "Windows 游戏已安装到系统应用与启动台。"
