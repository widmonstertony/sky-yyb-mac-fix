#include <errno.h>
#include <stdio.h>
#include <string.h>

/* Tencent's x86_64 ws2_32.dll leaves Windows Network Location Awareness
   lookup unimplemented.  Chromium/CEF treats the resulting debug break as a
   fatal child-process failure.  Make Begin return a harmless opaque handle,
   and make Next report WSAEFAULT, which Chromium interprets as "connected". */

static int patch_at(FILE *file, long offset, const unsigned char *expected,
                    const unsigned char *replacement, size_t size) {
    unsigned char current[32];
    if (size > sizeof(current) || fseek(file, offset, SEEK_SET) != 0 ||
        fread(current, 1, size, file) != size) {
        return -1;
    }
    if (memcmp(current, replacement, size) == 0) return 0;
    if (memcmp(current, expected, size) != 0) return -2;
    if (fseek(file, offset, SEEK_SET) != 0 ||
        fwrite(replacement, 1, size, file) != size) {
        return -1;
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: %s ws2_32.dll\n", argv[0]);
        return 2;
    }

    FILE *file = fopen(argv[1], "r+b");
    if (!file) {
        fprintf(stderr, "open failed: %s\n", strerror(errno));
        return 3;
    }

    const unsigned char begin_original[] = {
        0x41, 0x57, 0x41, 0x56, 0x56, 0x57, 0x53, 0x48, 0x83, 0xec
    };
    const unsigned char begin_connected[] = {
        0x49, 0xc7, 0x00, 0x01, 0x00, 0x00, 0x00, 0x31, 0xc0, 0xc3
    };
    const unsigned char next_original[] = {0x7e, 0x27};
    const unsigned char next_connected[] = {0x1e, 0x27};

    int begin = patch_at(file, 0xcde0, begin_original, begin_connected,
                         sizeof(begin_original));
    int next = patch_at(file, 0xd1b1, next_original, next_connected,
                        sizeof(next_original));
    int close_result = fclose(file);
    if (begin || next || close_result) {
        fprintf(stderr, "unexpected ws2_32.dll build or write failure (%d, %d)\n",
                begin, next);
        return 4;
    }

    puts("CEF network compatibility patch applied.");
    return 0;
}
