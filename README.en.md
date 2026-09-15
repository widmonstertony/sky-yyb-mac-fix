# Sky China PC on macOS through Tencent YYB

An unofficial repair tool that installs and launches the NetEase China PC edition of *Sky: Children of the Light* through Tencent YYB's bundled Windows-game engine on verified M2, M4, and Intel Macs.

It preserves the required Fever Games login flow, enables true Retina backing, repairs per-process DPI awareness and pointer scaling, and applies a 60 FPS/no-motion-blur preference. Verified M2 and M4 systems use the same hash-pinned `winevulkan.dll` from YYB engine 1.10.41, so both apply the same Vulkan interoperability fix: report the feature and desktop-GPU identity required by Sky's startup checks, then remove the unsupported geometry-shader request before `vkCreateDevice` reaches MoltenVK. The original DLL, every replaced instruction sequence, and the transformed result are verified before writing, and the local original is backed up. No game, launcher, Wine, token, or copyrighted binary is included.

See the [Chinese README](README.md) for the verified configuration, one-click instructions, limitations, safety notes, and troubleshooting.

Quick start: install and open [Tencent YYB for macOS](https://sj.qq.com/download) once (choose the Apple-silicon Mac build), download this repository, then double-click `install.command`. On M2/M4, open NetEase Fever normally and press **Start Game** for Sky. `launch.command` opens that verified path. On the verified M4 setup, the standalone Launchpad Sky icon is wrapped so it opens or focuses Fever instead of invoking YYB's broken child shortcut and returning `errCode:-1`; the original executable is backed up and restorable.

The binary patch is applied only when the chip is exactly Apple M2 or Apple M4 and the local DLL exactly matches the verified build. M2/M4 variants and unknown YYB engine builds are rejected rather than patched by fixed offset.

On Intel, the same `install.command` automatically uses Tencent's SHA-256-pinned legacy x86_64 engine, installs Windows Steam and Fever Games, enables true Retina rendering, and mirrors installed games into macOS Launchpad. Because the legacy engine's Fever download IPC stalls on current macOS, an explicit Sky download click is resumed from NetEase's public official manifest/CDN with per-file MD5 verification. No proprietary binary is stored in this repository. MetalFX/frame generation is not available in this Intel engine.

This project is not affiliated with Tencent, NetEase, or thatgamecompany. It does not bypass authentication, anti-cheat, purchases, or server checks. Use your own legitimate account.
