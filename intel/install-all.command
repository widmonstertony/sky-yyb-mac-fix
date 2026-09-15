#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h}"
INSTALL_LOG="$PROJECT_DIR/.runtime/install.log"

: >"$INSTALL_LOG"
exec >>"$INSTALL_LOG" 2>&1

"$PROJECT_DIR/2-install-steam.command"
"$PROJECT_DIR/3-install-netease.command"
"$PROJECT_DIR/7-install-launchpad-sync.command"

print
print "两个 Windows 启动器及其启动台自动同步已安装。这个窗口可以关闭。"
