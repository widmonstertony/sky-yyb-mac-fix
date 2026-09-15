# 光遇 PC 国服 · macOS 应用宝一键安装/高清修复

让 Apple Silicon 或 Intel Mac 通过腾讯应用宝自带的 Windows 游戏引擎安装、登录并启动网易《光·遇》PC 国服，同时修复 M4 上的“设备不支持”、协议启动、Retina 模糊、鼠标坐标缩放和旧版 Intel 引擎下载无响应等问题。

> 这是非官方社区兼容工具，与腾讯、网易或 thatgamecompany 无关。它不会绕过登录、反作弊、付费或服务器验证；你仍需使用自己的合法账号扫码登录。

## 已验证环境

- Apple M4，10 核 GPU，16 GB 内存
- macOS 27.0
- 腾讯应用宝 macOS 0.8.0（Build 2140）
- 应用宝 Wine 引擎 1.2.2（Build 683，EngineVersionCode 12241）
- 网易发烧游戏平台 1.18.43.22

- MacBook Pro 13-inch (M2, 2022)，10 核 GPU，16 GB 内存
- macOS 27.0
- 腾讯应用宝 macOS 0.8.0（Build 2140）
- 网易发烧游戏平台 1.18.43.22
- 光遇 PC 国服 `v3_4868_e579d901f2e7c3411dbf9bc551b65546`
- 内置屏幕 Retina 2560×1600

- MacBook Pro 16-inch (Intel, 2019)，Core i9-9980HK、Radeon Pro 5600M
- macOS 26.7
- 腾讯应用宝 macOS 0.6.5（Build 1684）内置 x86_64 Wine 引擎
- 网易发烧游戏平台 1.18.43.22

其他 Retina 机型会按屏幕缩放输出，不会硬编码成 2560×1600。外接非 Retina 屏幕以及未来版本尚未逐台验证。

## 一键使用

1. 安装并至少打开一次[腾讯应用宝 macOS 版](https://sj.qq.com/download)（下载页选择 **Mac 版 / Apple 芯片**）。
2. 点击本仓库右上角 **Code → Download ZIP**，解压。
3. 双击 `install.command`。
4. 第一次使用时，脚本会从[网易官方接口](https://loadingbaycn.webapp.163.com/app/v1/download_client/windows)取得最新版发烧游戏平台安装器，并交给应用宝安装。按出现的官方界面登录、安装《光·遇》即可；脚本会等待并自动续接高清修复。
5. 以后可像 M2 一样，直接从应用宝或“腾讯应用宝”文件夹点击网易发烧游戏平台；在平台里点《光·遇》的“开始游戏”即可。M4 兼容环境会自动建立。独立《光·遇》图标也会转到这条可靠的登录启动流程，`launch.command` 仍可作为备用入口。

若 macOS 首次阻止 `.command`，右键文件 → **打开**。脚本不需要 `sudo`。

也可以在终端执行：

```bash
python3 sky_yyb_fix.py setup --fps 60
```

## Intel Mac 一键使用

1. 下载并解压本仓库，双击根目录的 `install.command`；脚本会自动识别 Intel。
2. 脚本从腾讯官方地址取得应用宝 0.6.5 安装镜像，验证固定 SHA-256 后，只提取其中的 x86_64 PC 游戏引擎。仓库本身不包含腾讯、网易或 Steam 二进制。
3. Windows 版 Steam 和网易游戏启动器会安装到同一个应用宝 Wine 环境，并在 `~/Applications` 生成可被 macOS 启动台识别的 App。
4. 从 Steam 或网易启动器安装的游戏完成落盘后，后台同步会在 60 秒内为它生成独立的启动台 App。

Intel 版网易启动器使用真正的 2× Retina 后备缓冲和进程级 DPI 感知。该旧引擎的网易下载 IPC 在新系统上会卡住；只有当你在启动器中明确点击《光·遇》下载后，工具才会接管请求，从网易公开的官方清单/CDN 断点下载，并逐文件核对网易提供的 MD5。完成后重新打开网易启动器即可。

启动台里的《光·遇》入口会先确保网易登录会话存在，再以官方 `--start_from_launcher=1` 参数启动已安装的游戏；它不绕过登录或反作弊。游戏首次生成偏好文件后，下一次启动会自动设为 60 FPS 并关闭动态模糊。

Intel 路径可设定原生分辨率和 60 FPS，但当前腾讯 x86_64 引擎不提供可用的 MetalFX 或通用帧生成。因此本项目不会把“超分 + 插帧”伪装成已实现功能；是否有游戏内分辨率缩放取决于游戏自身。

## 它实际修改了什么

- 从网易官方接口动态获取安装包 URL 与 MD5，不在仓库分发任何游戏/启动器二进制。
- 将应用宝里的光遇入口保持为 `fevergames://mygame/?gameId=63&autoRun=1`，确保先经过发烧游戏平台登录，而不是绕过启动器直接运行 `Sky.exe`。
- 开启应用宝 Wine 的 `RetinaMode`，为 `Sky.exe`、FeverGamesLauncher/Web/Installer 设置 Per-Monitor High-DPI 感知。
- 将应用宝保存的发烧平台/光遇缩放比例修正为 Retina 2×，并同步 MMKV CRC32。
- 首次安装尚未存在 Retina MMKV 记录时，主动创建并校验记录，不再静默跳过高清修复。
- 在 M4 上按需编译一个很小的本地 Vulkan 兼容层：只当设备是 Apple M4 时，将游戏看到的 MoltenVK GPU 标识映射为已验证的 M2 标识，不修改任何 Vulkan 功能或显存数据。
- 为应用宝生成的本地快捷入口安装可恢复的启动包装，使从应用宝、启动台或 Finder 直接点击时也会自动继承兼容环境；不修改腾讯应用宝或 Wine 引擎本体。
- 将光遇目标帧率设为 60，关闭动态模糊。
- 关闭 Wine 的鼠标限制裁剪，避免 Retina 缩放后鼠标坐标与窗口错位。

工具不会替换或修改 `Sky.exe`、`winevulkan.dll`、应用宝引擎或网易启动器 EXE。M4 兼容层与快捷入口包装由仓库中可审查的源码在本机编译；应用宝生成的原始入口会单独备份并可由 `restore.command` 恢复。

## 安全与恢复

Apple Silicon 每次修改前会把相关文件备份到：

```text
~/Library/Application Support/SkyYYBMacFix/backups/
```

Intel 的注册表备份保存在：

```text
~/Library/Application Support/YYBIntelLauncher/backups/
```

两种机型都可双击根目录的 `restore.command` 恢复最近一次配置修改；脚本会自动识别架构。备份可能包含本机应用设置，因此权限设为仅当前用户可读，切勿上传。

仓库不采集遥测，也不会读取或输出网易登录 token。建议先阅读脚本；其全部实现只有 Python 标准库。

## 常见问题

### 仍提示“不支持”

M4 的硬件能力足够；问题是 MoltenVK 暴露的设备 ID 包含 macOS 和 Apple GPU family，M4 的新标识不在当前光遇国服的本地设备判断范围中，因此它在 `vkCreateDevice` 之前就退出了。重跑 `install.command` 后，应用宝生成的入口会自动带上 M4 兼容环境，可照常直接点击。

M2 以及其他机型若仍报错，请退出光遇、网易发烧游戏和应用宝生成的窗口后重跑 `install.command`。Intel 上它会安全续接已完成的步骤。

### 安装或登录停在 99%

不要直接运行 `Sky.exe`。本工具会恢复 `fevergames://` 协议入口；请让发烧游戏平台保持打开并完成扫码登录。网络与服务器异常不属于本地兼容层问题。

### Intel 上点击《光·遇》下载没有反应

请从 macOS 启动台里的“网易游戏启动器”打开并再次点击下载。随启动器启动的后台助手会接管旧引擎无法完成的 IPC 下载；支持断点续传，完成时会发出系统通知并生成《光·遇》启动台图标。不要直接运行仓库里的下载脚本来绕过这个明确点击动作。

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
