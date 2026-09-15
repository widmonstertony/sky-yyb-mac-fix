#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h}"
source "$PROJECT_DIR/lib/common.sh"
check_ready

STEAM_EXE="$WINE_PREFIX/drive_c/Program Files (x86)/Steam/Steam.exe"
if [[ -f "$STEAM_EXE" ]]; then
  print "Windows 版 Steam 已经安装，跳过安装程序。"
  exit 0
fi

STEAM_SETUP="$RUNTIME_DIR/SteamSetup.exe"
SAFE_INSTALLER_DIR="$WINE_PREFIX/drive_c/YYBInstallers"
SAFE_STEAM_SETUP="$SAFE_INSTALLER_DIR/SteamSetup.exe"
if [[ ! -f "$STEAM_SETUP" ]]; then
  print "正在从 Steam 官网下载安装器……"
  curl --fail --location --progress-bar \
    "https://cdn.akamai.steamstatic.com/client/installer/SteamSetup.exe" \
    --output "$STEAM_SETUP"
fi

mkdir -p "$SAFE_INSTALLER_DIR"
ditto "$STEAM_SETUP" "$SAFE_STEAM_SETUP"

print "即将打开 Windows 版 Steam 安装程序。"
print "将按默认选项自动安装。"
run_windows 'C:\YYBInstallers\SteamSetup.exe' /S

print
print "Steam 安装完成。"
