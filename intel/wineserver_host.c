#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int parent_dir(char *path) {
    char *slash = strrchr(path, '/');
    if (!slash) return -1;
    *slash = '\0';
    return 0;
}

int main(int argc, char **argv) {
    (void)argc;
    char raw_path[PATH_MAX], executable[PATH_MAX];
    uint32_t size = sizeof(raw_path);
    if (_NSGetExecutablePath(raw_path, &size) != 0) return 2;
    if (!realpath(raw_path, executable)) return 3;

    char project[PATH_MAX];
    snprintf(project, sizeof(project), "%s", executable);
    for (int i = 0; i < 4; ++i) {
        if (parent_dir(project) != 0) return 4;
    }

    const char *home = getenv("HOME");
    if (!home) return 5;

    char contents[PATH_MAX], wine_lib[PATH_MAX], frameworks[PATH_MAX];
    char prefix[PATH_MAX], loader[PATH_MAX], wrapper[PATH_MAX], host[PATH_MAX];
    char server[PATH_MAX], gfx[PATH_MAX], ntdll[PATH_MAX];
    snprintf(contents, sizeof(contents), "%s/.runtime/wine-engine.app/Contents", project);
    snprintf(wine_lib, sizeof(wine_lib), "%s/SharedSupport/wine/lib/wine", contents);
    snprintf(frameworks, sizeof(frameworks), "%s/Frameworks", contents);
    snprintf(prefix, sizeof(prefix), "%s/Library/Application Support/com.tencent.yybmac.wine.engine/wine", home);
    snprintf(loader, sizeof(loader), "%s/wine-loader", project);
    snprintf(wrapper, sizeof(wrapper), "%s/wineserver-wrapper", project);
    snprintf(host, sizeof(host), "%s/WineServerHost.app", project);
    snprintf(server, sizeof(server), "%s/MacOS/wineserver", contents);
    snprintf(gfx, sizeof(gfx), "%s/render/dxvk/wine", frameworks);
    snprintf(ntdll, sizeof(ntdll), "%s/x86_64-unix/ntdll.so", wine_lib);

    setenv("WINEPREFIX", prefix, 1);
    setenv("WINELOADER", loader, 1);
    setenv("WINESERVER", wrapper, 1);
    setenv("WINEDLLPATH", wine_lib, 1);
    setenv("YYB_NTDLL_PATH", ntdll, 1);
    setenv("YYB_WINESERVER_HOST_APP", host, 1);
    setenv("DYLD_FALLBACK_LIBRARY_PATH", frameworks, 1);
    setenv("GFX_BACKEND_PATH", gfx, 1);
    setenv("WINE_RETINA_MODE", "1", 1);
    // The server owns the macOS backing surfaces, so the Retina scale must be
    // set here as well as in each client launcher. Leaving the server at 1x
    // makes an otherwise DPI-aware FeverGames window look bitmap-scaled.
    setenv("WINE_RETINA_SCALE", "2.0", 1);
    setenv("DXVK_HUD", "0", 1);
    setenv("MTL_HUD_ENABLED", "0", 1);
    setenv("D3DM_ENABLE_METALFX", "0", 1);
    setenv("WINEDEBUG", "-all", 1);

    argv[0] = server;
    execv(server, argv);
    return 6;
}
