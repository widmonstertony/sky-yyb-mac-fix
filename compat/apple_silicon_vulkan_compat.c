// Compatibility shim for Sky PC China running through YYB's Wine engine.
//
// Sky currently rejects newer Apple GPU identities before it creates a Vulkan
// device.  MoltenVK's Apple-Silicon device ID contains the OS and GPU-family
// numbers, so the ID changes on new macOS/GPU combinations even when all
// required Vulkan features are present.  Keep the workaround narrowly scoped:
// it activates only when SKY_YYB_GPU_COMPAT=1 and only rewrites Apple M4.

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define APPLE_VENDOR_ID 0x106bU
#define DEVICE_NAME_OFFSET (5U * sizeof(uint32_t))
#define DEVICE_NAME_SIZE 256U

extern void vkGetPhysicalDeviceProperties(void *physical_device, void *properties);
extern void vkGetPhysicalDeviceProperties2(void *physical_device, void *properties);
extern void vkGetPhysicalDeviceProperties2KHR(void *physical_device, void *properties);

static int compat_enabled(void) {
    const char *value = getenv("SKY_YYB_GPU_COMPAT");
    return value && strcmp(value, "1") == 0;
}

static void rewrite_m4_identity(void *properties) {
    uint32_t *words = (uint32_t *)properties;
    char *name = (char *)properties + DEVICE_NAME_OFFSET;
    if (!compat_enabled() || words[2] != APPLE_VENDOR_ID ||
        strncmp(name, "Apple M4", 8) != 0) {
        return;
    }

    // Preserve the OS and Mac-GPU-family bytes. Apple GPU family 8 is the
    // identity exposed by the M2 environment already verified with Sky.
    words[3] = (words[3] & 0xffffff00U) | 8U;
    memset(name, 0, DEVICE_NAME_SIZE);
    memcpy(name, "Apple M2", sizeof("Apple M2"));
}

static void sky_get_physical_device_properties(void *physical_device,
                                                void *properties) {
    vkGetPhysicalDeviceProperties(physical_device, properties);
    rewrite_m4_identity(properties);
}

static void sky_get_physical_device_properties2(void *physical_device,
                                                 void *properties) {
    vkGetPhysicalDeviceProperties2(physical_device, properties);
    rewrite_m4_identity((unsigned char *)properties + 16);
}

static void sky_get_physical_device_properties2_khr(void *physical_device,
                                                     void *properties) {
    vkGetPhysicalDeviceProperties2KHR(physical_device, properties);
    rewrite_m4_identity((unsigned char *)properties + 16);
}

#define DYLD_INTERPOSE(replacement, replacee)                                  \
    __attribute__((used)) static struct {                                      \
        const void *replacement;                                               \
        const void *replacee;                                                  \
    } _interpose_##replacee __attribute__((section("__DATA,__interpose"))) = { \
        (const void *)(uintptr_t)&replacement,                                 \
        (const void *)(uintptr_t)&replacee                                     \
    }

DYLD_INTERPOSE(sky_get_physical_device_properties,
               vkGetPhysicalDeviceProperties);
DYLD_INTERPOSE(sky_get_physical_device_properties2,
               vkGetPhysicalDeviceProperties2);
DYLD_INTERPOSE(sky_get_physical_device_properties2_khr,
               vkGetPhysicalDeviceProperties2KHR);
