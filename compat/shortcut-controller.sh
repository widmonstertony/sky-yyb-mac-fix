#!/bin/zsh
set -eu

mode="$1"
original="$2"
shift 2

user_home="$HOME"
prefix="$user_home/Library/Application Support/com.tencent.yybmac.wine.engine/wine"
engine_root="$user_home/Library/Application Support/com.tencent.yybmac/ExeEngineDownload"
shim="$user_home/Library/Application Support/SkyYYBMacFix/compat/libSkyYYBGPUCompat.dylib"

engine=""
for candidate in "$engine_root"/*.app(Nom); do
    if [[ -x "$candidate/Contents/MacOS/wineserver" && -f "$candidate/Contents/Frameworks/libMoltenVK.dylib" ]]; then
        engine="$candidate"
        break
    fi
done

if [[ -z "$engine" || ! -x "$original" || ! -f "$shim" ]]; then
    print -u2 "Sky YYB fix: M4 compatibility files are incomplete. Run install.command again."
    exit 75
fi

compat_engine_running() {
    local pid
    for pid in $(/usr/bin/pgrep -f "$engine/Contents/MacOS/wineserver" 2>/dev/null || true); do
        if /usr/sbin/lsof -p "$pid" -Fn 2>/dev/null | /usr/bin/grep -Fq "n$shim"; then
            return 0
        fi
    done
    return 1
}

if ! compat_engine_running; then
    WINEPREFIX="$prefix" "$engine/Contents/MacOS/wineserver" -k >/dev/null 2>&1 || true
    /bin/sleep 1
    /usr/bin/open -n \
        --env "WINEPREFIX=$prefix" \
        --env "SKY_YYB_GPU_COMPAT=1" \
        --env "DYLD_INSERT_LIBRARIES=$shim" \
        "$engine"

    ready=0
    for _ in {1..40}; do
        if compat_engine_running; then
            ready=1
            break
        fi
        /bin/sleep 0.25
    done
    if (( ! ready )); then
        print -u2 "Sky YYB fix: the compatible Wine engine did not start."
        exit 76
    fi
    /bin/sleep 3
fi

if [[ "$mode" == "child" ]]; then
    child_app="${original%%.app/*}.app"
    shortcuts_root="${child_app:h}"
    parent_app="$shortcuts_root/com.tencent.macexe.com.45a7ca33.app"
    if [[ -d "$parent_app" ]]; then
        /usr/bin/open -n "$parent_app"
        # Fever 1.18 ignores the generated child's autoRun request on this YYB
        # engine and leaves its helper at 99%. Route the icon to the working
        # parent login flow instead; Start Game then uses this same compatible
        # Wine server and keeps NetEase authentication/anti-cheat intact.
        exit 0
    fi
fi

exec "$original" "$@"
