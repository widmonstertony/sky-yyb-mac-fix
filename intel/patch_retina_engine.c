#include <errno.h>
#include <stdio.h>
#include <string.h>

/*
 * Tencent's 0.6.5 Intel mac driver falls back to a literal 1.0 scale when
 * its private package map has no entry for a locally launched EXE.  That
 * literal is also the lower bound of the validity check, so changing it
 * directly disables the very 2x value we want.  Instead, make only the
 * fallback load read the driver's retina_scale variable, and initialize that
 * variable to 2.0.  Exact original bytes are verified before writing, so an
 * unknown engine build is rejected.
 */

static int patch_at(FILE *file, long offset, const unsigned char *expected,
                    const unsigned char *replacement, size_t size) {
    unsigned char current[16];
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
        fprintf(stderr, "usage: %s winemac.so\n", argv[0]);
        return 2;
    }

    FILE *file = fopen(argv[1], "r+b");
    if (!file) {
        fprintf(stderr, "open failed: %s\n", strerror(errno));
        return 3;
    }

    const unsigned char scale_1x[] = {
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf0, 0x3f
    };
    const unsigned char scale_2x[] = {
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40
    };
    const unsigned char fallback_load_1x[] = {
        0xf2, 0x0f, 0x10, 0x05, 0x0e, 0x0f, 0x05, 0x00
    };
    const unsigned char fallback_load_retina_scale[] = {
        0xf2, 0x0f, 0x10, 0x05, 0x16, 0x2c, 0x0b, 0x00
    };

    int load_result = patch_at(file, 0xdd48a, fallback_load_1x,
                               fallback_load_retina_scale,
                               sizeof(fallback_load_1x));
    int scale_result = patch_at(file, 0x1900a8, scale_1x, scale_2x,
                                sizeof(scale_1x));
    int close_result = fclose(file);
    if (load_result || scale_result || close_result) {
        fprintf(stderr,
                "unexpected winemac build or write failure (%d, %d)\n",
                load_result, scale_result);
        return 4;
    }

    puts("Retina 2x mac-driver default applied.");
    return 0;
}
