#!/bin/zsh
set -u

SCRIPT_DIR=${0:A:h}

if [[ "$(uname -m)" == "x86_64" ]]; then
  exec "$SCRIPT_DIR/intel/install.command"
fi

clear
echo "Sky 国服 · 腾讯应用宝 macOS 一键安装/修复"
echo "================================================"
echo "此过程会关闭正在运行的光遇/网易发烧游戏窗口，并在修改前自动备份。"
echo

/usr/bin/python3 "$SCRIPT_DIR/sky_yyb_fix.py" setup --fps 60
RESULT=$?

echo
if [[ $RESULT -eq 0 ]]; then
  echo "完成。以后可直接双击 launch.command。"
else
  echo "本次没有完成（错误码 $RESULT）。看上面的提示处理后，再双击本文件即可续接。"
fi
echo "按回车键关闭窗口。"
read -r
exit $RESULT
