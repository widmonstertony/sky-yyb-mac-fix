#!/bin/zsh
set -u
SCRIPT_DIR=${0:A:h}
clear
echo "将恢复最近一次修复前的应用宝/光遇配置。"
/usr/bin/python3 "$SCRIPT_DIR/sky_yyb_fix.py" restore
RESULT=$?
echo
echo "按回车键关闭窗口。"
read -r
exit $RESULT
