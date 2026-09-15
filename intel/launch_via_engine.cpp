#include <atomic>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <functional>
#include <iostream>
#include <libproc.h>
#include <string>
#include <strings.h>
#include <thread>
#include <vector>

class PathUtils {
public:
    static void init();
    static void prepareWineEnvironment();
};

enum class WapErrorCode : int;

class WapManager {
public:
    static WapManager &instance();
    void doLaunch(
        const std::string &package,
        const std::string &exe,
        const std::vector<std::string> &args,
        const std::function<void(WapErrorCode, const std::string &)> &callback);
};

extern "C" void wine_engine_init();
extern "C" void wine_engine_process_macos_events();

// libengine normally lives inside Tencent's wineserver executable.  These
// server-side hooks are not used by the command-line launch path, but Mach-O's
// flat namespace still requires the symbols to exist when the dylib is loaded.
extern "C" long active_app_process(...) { return 0; }
extern "C" long is_app_process_exist(...) { return 0; }
extern "C" long wineserver_kill_all_processes(...) { return 0; }
extern "C" long wineserver_kill_processe(...) { return 0; }
extern "C" long wineserver_shutdown_timeout(...) { return 0; }
extern "C" long wineserver_wake_launch_thread(...) { return 0; }

static bool processWithExecutableIsRunning(
    const std::filesystem::path &target) {
    const int required = proc_listpids(PROC_ALL_PIDS, 0, nullptr, 0);
    if (required <= 0) return false;

    std::vector<pid_t> pids(
        static_cast<size_t>(required) / sizeof(pid_t) + 32);
    const int bytes = proc_listpids(PROC_ALL_PIDS, 0, pids.data(),
                                   static_cast<int>(pids.size() *
                                                    sizeof(pid_t)));
    if (bytes <= 0) return false;

    const std::string expected = target.string();
    const std::string expectedName = target.filename().string();
    char path[PROC_PIDPATHINFO_MAXSIZE];
    char name[PROC_PIDPATHINFO_MAXSIZE];
    const size_t count = static_cast<size_t>(bytes) / sizeof(pid_t);
    for (size_t i = 0; i < count; ++i) {
        if (pids[i] <= 0) continue;
        const int length = proc_pidpath(pids[i], path, sizeof(path));
        if (length > 0 && strcasecmp(expected.c_str(), path) == 0) return true;
        const int nameLength = proc_name(pids[i], name, sizeof(name));
        if (nameLength > 0 &&
            strcasecmp(expectedName.c_str(), name) == 0) return true;
    }
    return false;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        std::cerr << "usage: winelauncher EXE [ARG ...]\n";
        return 64;
    }

    const std::filesystem::path requestedTarget(argv[1]);
    const bool isSteamTarget =
        strcasecmp(requestedTarget.filename().string().c_str(), "Steam.exe") == 0;

    wine_engine_init();

    // Tencent currently resets an unregistered app to its Apple-Silicon GPTK
    // default during initialization.  Re-apply the Intel-safe DXVK path after
    // initialization so the launched Windows process inherits it.
    const std::filesystem::path executable =
        std::filesystem::canonical(std::filesystem::path(argv[0]));
    const std::string dxvk =
        (executable.parent_path().parent_path() /
         "Frameworks/render/dxvk/wine").string();
    setenv("GFX_BACKEND_PATH", dxvk.c_str(), 1);
    setenv("WINE_RETINA_MODE", "1", 1);
    // Use a 2x backing surface for both launchers. Per-process DPI awareness
    // in the prefix keeps FeverGames' logical window size unchanged while
    // avoiding the 1x bitmap upscale that makes its text blurry.
    setenv("WINE_RETINA_SCALE", "2.0", 1);
    if (!isSteamTarget) {
        setenv("QT_ENABLE_HIGHDPI_SCALING", "1", 1);
        setenv("QT_AUTO_SCREEN_SCALE_FACTOR", "1", 1);
        setenv("QT_SCALE_FACTOR", "1", 1);
        setenv(
            "QTWEBENGINE_CHROMIUM_FLAGS",
            "--disable-gpu --disable-gpu-compositing "
            "--disable-direct-composition --force-device-scale-factor=2",
            1);
    }
    setenv("DXVK_HUD", "0", 1);
    setenv("MTL_HUD_ENABLED", "0", 1);
    setenv("D3DM_ENABLE_METALFX", "0", 1);
    setenv("WINEDEBUG", "-all", 1);
    PathUtils::prepareWineEnvironment();

    std::vector<std::string> args;
    for (int i = 2; i < argc; ++i) args.emplace_back(argv[i]);
    std::atomic<bool> finished{false};
    int result = 70;
    std::string detail;
    const std::filesystem::path target =
        std::filesystem::canonical(std::filesystem::path(argv[1]));
    const std::string package =
        isSteamTarget
            ? "com.tencent.macexe.com.steampowered.steam"
            : "com.tencent.macexe.com.45a7ca33";
    WapManager::instance().doLaunch(
        package, target.string(), args,
        [&](WapErrorCode code, const std::string &message) {
            result = static_cast<int>(code);
            detail = message;
            finished.store(true);
        });

    bool launchedProcessSeen = false;
    for (int i = 0; i < 300 && !finished.load(); ++i) {
        wine_engine_process_macos_events();
        if (processWithExecutableIsRunning(target)) {
            launchedProcessSeen = true;
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    if (!detail.empty()) std::cerr << detail << "\n";
    if (!launchedProcessSeen) {
        if (!finished.load()) return 75;
        if (result != 0) return result;
    }

    // Tencent's host must continue pumping Cocoa events for the lifetime of
    // the top-level Windows process.  Exiting the host after startup leaves
    // modern Steam's main loop stalled even though its PE process remains.
    bool seen = launchedProcessSeen;
    int missingTicks = 0;
    int prelaunchTicks = 0;
    for (;;) {
        wine_engine_process_macos_events();
        if (processWithExecutableIsRunning(target)) {
            seen = true;
            missingTicks = 0;
        } else if (seen) {
            if (++missingTicks >= 200) break;
        } else if (++prelaunchTicks >= 600) {
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    return 0;
}
