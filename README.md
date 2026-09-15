# 光遇 PC 国服 · macOS 应用宝一键安装/高清修复

让 Apple Silicon Mac 通过腾讯应用宝自带的 Wine/GPTK 引擎安装、登录并启动网易《光·遇》PC 国服，同时修复“设备不支持”、协议启动、Retina 模糊和鼠标坐标缩放问题。

> 这是非官方社区兼容工具，与腾讯、网易或 thatgamecompany 无关。它不会绕过登录、反作弊、付费或服务器验证；你仍需使用自己的合法账号扫码登录。

## 已验证环境

- MacBook Pro 13-inch (M2, 2022)，10 核 GPU，16 GB 内存
- macOS 27.0
- 腾讯应用宝 macOS 0.8.0（Build 2140）
- 应用宝 Windows/Wine 引擎 1.10.41
- 网易发烧游戏平台 1.18.43.22
- 光遇 PC 国服 `v3_4868_e579d901f2e7c3411dbf9bc551b65546`
- 内置屏幕 Retina 2560×1600

其他 Apple Silicon 机型会按本机 Retina 像素尺寸输出，不会硬编码成 2560×1600。Intel Mac、外接非 Retina 屏幕以及未来版本尚未逐台验证。

## 一键使用

1. 安装并至少打开一次[腾讯应用宝 macOS 版](https://sj.qq.com/download)（下载页选择 **Mac 版 / Apple 芯片**）。
2. 点击本仓库右上角 **Code → Download ZIP**，解压。
3. 双击 `install.command`。
4. 第一次使用时，脚本会从[网易官方接口](https://loadingbaycn.webapp.163.com/app/v1/download_client/windows)取得最新版发烧游戏平台安装器，并交给应用宝安装。按出现的官方界面登录、安装《光·遇》即可；脚本会等待并自动续接高清修复。
5. 以后双击 `launch.command`，或使用应用宝生成的《光·遇》图标。

若 macOS 首次阻止 `.command`，右键文件 → **打开**。脚本不需要 `sudo`。

也可以在终端执行：

```bash
python3 sky_yyb_fix.py setup --fps 60
```

## 它实际修改了什么

- 从网易官方接口动态获取安装包 URL 与 MD5，不在仓库分发任何游戏/启动器二进制。
- 将应用宝里的光遇入口保持为 `fevergames://mygame/?gameId=63&autoRun=1`，确保先经过发烧游戏平台登录，而不是绕过启动器直接运行 `Sky.exe`。
- 开启应用宝 Wine 的 `RetinaMode`，为 `Sky.exe`、FeverGamesLauncher/Web/Installer 设置 Per-Monitor High-DPI 感知。
- 将应用宝保存的发烧平台/光遇缩放比例修正为 Retina 2×，并同步 MMKV CRC32。
- 将光遇目标帧率设为 60，关闭动态模糊。
- 关闭 Wine 的鼠标限制裁剪，避免 Retina 缩放后鼠标坐标与窗口错位。

工具不会替换或修改 `Sky.exe`、`winevulkan.dll` 或网易启动器 EXE。

## 安全与恢复

每次修改前，相关文件都会备份到：

```text
~/Library/Application Support/SkyYYBMacFix/backups/
```

双击 `restore.command` 可恢复最近一次修改。备份可能包含本机应用设置，因此权限设为仅当前用户可读，切勿上传。

仓库不采集遥测，也不会读取或输出网易登录 token。建议先阅读脚本；其全部实现只有 Python 标准库。

## 常见问题

### 仍提示“不支持”

确保使用 Apple Silicon Mac，并让应用宝完成 Windows/Wine 引擎初始化。退出光遇、网易发烧游戏和应用宝生成的窗口后，再运行 `install.command`。

### 安装或登录停在 99%

不要直接运行 `Sky.exe`。本工具会恢复 `fevergames://` 协议入口；请让发烧游戏平台保持打开并完成扫码登录。网络与服务器异常不属于本地兼容层问题。

### 启动器或游戏仍然模糊

关闭所有相关窗口后再运行一次 `install.command`。应用宝只有在入口首次启动后才可能生成对应 MMKV Retina 记录，因此第一次安装后重跑一次是安全且幂等的。

### 想用 30 或 120 FPS

```bash
python3 sky_yyb_fix.py fix --fps 30
python3 sky_yyb_fix.py fix --fps 120
```

帧率能否达到目标取决于芯片、温度和场景；Retina 原生输出不等于保证 60 FPS。

## 诊断

```bash
python3 sky_yyb_fix.py status
```

提交 Issue 时只贴上述状态、Mac 型号、macOS/应用宝/发烧平台版本和报错截图。不要上传 `user.reg`、MMKV、整个 Wine 前缀或任何二维码/账号文件。

## 开发与测试

```bash
python3 -m unittest discover -s tests -v
```

测试使用临时伪造前缀，不接触真实应用宝数据。

## License

[MIT](LICENSE)。本许可证仅覆盖本仓库原创脚本，不覆盖腾讯、网易、thatgamecompany 或其他第三方软件与商标。
