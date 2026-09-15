#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h}"
source "$PROJECT_DIR/lib/common.sh"
check_ready

FEVER_EXE="$WINE_PREFIX/drive_c/Program Files/FeverGames/FeverGamesLauncher.exe"
if [[ -f "$FEVER_EXE" ]]; then
  print "网易游戏启动器已经安装，跳过安装程序。"
  exit 0
fi

NETEASE_META="$(/usr/bin/python3 - <<'PY'
import json
import re
import urllib.request
url = "https://loadingbaycn.webapp.163.com/app/v1/download_client/windows"
request = urllib.request.Request(url, headers={"User-Agent": "sky-yyb-mac-fix-intel/1.0"})
with urllib.request.urlopen(request, timeout=30) as response:
    data = json.load(response)["data"]
match = re.fullmatch(r"FeverGames_([0-9.]+)_setup\.exe", data["file_name"])
if not match:
    raise SystemExit("网易安装包文件名格式异常")
print(match.group(1), data["package_md5"], data["download_url"], sep="\t")
PY
)"
IFS=$'\t' read -r NETEASE_VERSION NETEASE_MD5 NETEASE_URL <<<"$NETEASE_META"
NETEASE_SETUP="$RUNTIME_DIR/FeverGames_${NETEASE_VERSION}_setup.exe"
SAFE_INSTALLER_DIR="$WINE_PREFIX/drive_c/YYBInstallers"
SAFE_NETEASE_SETUP="$SAFE_INSTALLER_DIR/FeverGames_${NETEASE_VERSION}_setup.exe"
if [[ ! -f "$NETEASE_SETUP" ]]; then
  print "正在从网易官方 CDN 下载安装器……"
  curl --fail --location --progress-bar "$NETEASE_URL" --output "$NETEASE_SETUP"
fi

if [[ "$(md5 -q "$NETEASE_SETUP")" != "$NETEASE_MD5" ]]; then
  print -u2 "安装包校验失败，未执行安装。"
  exit 1
fi

mkdir -p "$SAFE_INSTALLER_DIR"
ditto "$NETEASE_SETUP" "$SAFE_NETEASE_SETUP"

print "网易发烧游戏官方安装包校验通过。"
print "将按默认选项自动安装。"
run_windows "C:\\YYBInstallers\\FeverGames_${NETEASE_VERSION}_setup.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-

print
print "网易游戏启动器安装完成。"
