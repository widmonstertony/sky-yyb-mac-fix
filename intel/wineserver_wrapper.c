#include <stdlib.h>
#include <unistd.h>

int main(int argc, char **argv) {
    const char *host = getenv("YYB_WINESERVER_HOST_APP");
    if (!host || !*host) return 2;

    char **open_argv = calloc((size_t)argc + 5, sizeof(char *));
    if (!open_argv) return 3;

    int out = 0;
    open_argv[out++] = "open";
    open_argv[out++] = "-gj";
    open_argv[out++] = (char *)host;
    open_argv[out++] = "--args";
    for (int in = 1; in < argc; ++in) open_argv[out++] = argv[in];
    open_argv[out] = NULL;

    execv("/usr/bin/open", open_argv);
    return 4;
}
