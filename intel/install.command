#!/bin/zsh

set -u

SCRIPT_DIR="${0:A:h}"
clear
echo "Intel Mac · 腾讯应用宝 PC 启动器安装"
echo "================================================"
echo "将安装腾讯官方 PC 游戏引擎、Windows 版 Steam、网易游戏启动器，"
echo "并启用 Retina 与 macOS 启动台自动同步。"
echo

"$SCRIPT_DIR/1-setup.command"
RESULT=$?
if [[ $RESULT -eq 0 ]]; then
  "$SCRIPT_DIR/install-all.command"
  RESULT=$?
fi

echo
if [[ $RESULT -eq 0 ]]; then
  echo "完成。Steam、网易启动器以及之后安装的游戏会出现在 macOS 启动台。"
else
  echo "本次没有完成（错误码 $RESULT）。再次双击本文件可安全续接。"
fi
echo "按回车键关闭窗口。"
read -r
exit $RESULT
