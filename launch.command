#!/bin/zsh
set -u
SCRIPT_DIR=${0:A:h}

if [[ "$(uname -m)" == "x86_64" ]]; then
  open "$HOME/Applications/网易游戏启动器.app"
  exit $?
fi

/usr/bin/python3 "$SCRIPT_DIR/sky_yyb_fix.py" launch
