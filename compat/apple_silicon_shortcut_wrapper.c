#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Kept in the binary so the installer can identify its own wrapper safely. */
__attribute__((used)) static const char kMarker[] = "SKY_YYB_SHORTCUT_WRAPPER_V1";

int main(int argc, char **argv) {
    (void)kMarker;
    char executable[PATH_MAX];
    uint32_t size = sizeof(executable);
    if (_NSGetExecutablePath(executable, &size) != 0) {
        fputs("Sky YYB fix: shortcut path is too long.\n", stderr);
        return 70;
    }

    char resolved[PATH_MAX];
    if (realpath(executable, resolved) == NULL) {
        strncpy(resolved, executable, sizeof(resolved) - 1);
        resolved[sizeof(resolved) - 1] = '\0';
    }

    const char *user_home = getenv("HOME");
    if (user_home == NULL || user_home[0] == '\0') {
        fputs("Sky YYB fix: HOME is unavailable.\n", stderr);
        return 71;
    }

    char controller[PATH_MAX];
    char original[PATH_MAX];
    if (snprintf(controller, sizeof(controller),
                 "%s/Library/Application Support/SkyYYBMacFix/compat/shortcut-controller.sh",
                 user_home) >= (int)sizeof(controller) ||
        snprintf(original, sizeof(original), "%s.skyfix-original", resolved) >=
            (int)sizeof(original)) {
        fputs("Sky YYB fix: generated path is too long.\n", stderr);
        return 72;
    }

    const char *mode = strstr(
        resolved,
        "/com.tencent.macexe.com.45a7ca33.app/Contents/MacOS/YYBPackage")
        ? "parent"
        : "child";

    char **shell_argv = calloc((size_t)argc + 4, sizeof(char *));
    if (shell_argv == NULL) {
        return 73;
    }
    shell_argv[0] = "/bin/zsh";
    shell_argv[1] = controller;
    shell_argv[2] = (char *)mode;
    shell_argv[3] = original;
    for (int index = 1; index < argc; ++index) {
        shell_argv[index + 3] = argv[index];
    }
    shell_argv[argc + 3] = NULL;

    execv(shell_argv[0], shell_argv);
    perror("Sky YYB fix: cannot start shortcut controller");
    free(shell_argv);
    return 74;
}
