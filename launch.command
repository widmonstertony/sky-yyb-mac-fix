#!/bin/zsh
set -u
SCRIPT_DIR=${0:A:h}
/usr/bin/python3 "$SCRIPT_DIR/sky_yyb_fix.py" launch
