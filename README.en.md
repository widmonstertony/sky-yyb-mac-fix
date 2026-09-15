# Sky China PC on macOS through Tencent YYB

An unofficial repair tool that installs and launches the NetEase China PC edition of *Sky: Children of the Light* through Tencent YYB's bundled Windows-game engine on verified M2, M4, and Intel Macs.

It preserves the required Fever Games login flow, enables true Retina backing, repairs per-process DPI awareness and pointer scaling, and applies a 60 FPS/no-motion-blur preference. On M2, it applies the exact Vulkan interoperability fix proven on YYB engine 1.10.41: report the feature and desktop-GPU identity required by Sky's startup checks, then remove the unsupported geometry-shader request before `vkCreateDevice` reaches MoltenVK. Both the original and transformed DLL are SHA-256 pinned, all replaced instruction sequences are verified, and the local original is backed up. On M4, it instead builds a narrowly scoped compatibility library from the included C source so the game sees the already-supported M2 MoltenVK identity; Vulkan features and memory information are unchanged. No game, launcher, Wine, token, or copyrighted binary is included.

See the [Chinese README](README.md) for the verified configuration, one-click instructions, limitations, safety notes, and troubleshooting.

Quick start: install and open [Tencent YYB for macOS](https://sj.qq.com/download) once (choose the Apple-silicon Mac build), download this repository, then double-click `install.command`. On M4, the installer adds a reversible wrapper to YYB's locally generated shortcuts. Open NetEase Fever normally and press **Start Game** for Sky; the standalone Sky icon routes to the same reliable login flow.

The hash-pinned M2 binary patch is deliberately not applied to M4/M4 Pro or unknown YYB engine builds. M4 uses the separate source-built compatibility library and shortcut wrapper; it does not patch or re-sign Tencent YYB or its Wine engine.

On Intel, the same `install.command` automatically uses Tencent's SHA-256-pinned legacy x86_64 engine, installs Windows Steam and Fever Games, enables true Retina rendering, and mirrors installed games into macOS Launchpad. Because the legacy engine's Fever download IPC stalls on current macOS, an explicit Sky download click is resumed from NetEase's public official manifest/CDN with per-file MD5 verification. No proprietary binary is stored in this repository. MetalFX/frame generation is not available in this Intel engine.

This project is not affiliated with Tencent, NetEase, or thatgamecompany. It does not bypass authentication, anti-cheat, purchases, or server checks. Use your own legitimate account.
