#!/bin/zsh

set -u
SCRIPT_DIR="${0:A:h}"

/usr/bin/python3 "$SCRIPT_DIR/apply-intel-retina.py" --restore
RESULT=$?
echo
echo "按回车键关闭窗口。"
read -r
exit $RESULT
