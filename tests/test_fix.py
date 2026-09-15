#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import plistlib
import struct
import sys
import tempfile
import unittest
import zlib


REPO = Path(__file__).resolve().parents[1]


def load_module(test_home: Path, applications: Path):
    os.environ["SKY_YYB_TEST_HOME"] = str(test_home)
    os.environ["SKY_YYB_TEST_APPLICATIONS"] = str(applications)
    spec = importlib.util.spec_from_file_location("sky_yyb_fix", REPO / "sky_yyb_fix.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def make_preferences() -> bytes:
    names = [b"quality_fps\0", b"kUserPreference_MotionBlurScalar\0"]
    counts = (2, 0, 0, 0)
    string_base = 28 + 16
    strings = b"".join(names)
    header = b"PREF" + b"\0" * 4 + struct.pack("<4I", *counts) + struct.pack("<I", string_base)
    records = struct.pack("<II", 0, 30) + struct.pack("<II", len(names[0]), 0x3F800000)
    return header + records + strings


class FixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.home = root / "home"
        self.apps = root / "Applications"
        self.module = load_module(self.home, self.apps)
        self.module.YYB_APP.mkdir(parents=True)
        self.module.PREFIX.mkdir(parents=True)
        self.module.SKY_DIR.mkdir(parents=True)
        self.module.SKY_EXE.write_bytes(b"MZ-test")
        self.module.USER_REG.write_text("WINE REGISTRY Version 2\n", encoding="utf-8")
        self.module.SYSTEM_REG.write_text("WINE REGISTRY Version 2\n", encoding="utf-8")
        self.module.PREFERENCES.parent.mkdir(parents=True)
        self.module.PREFERENCES.write_bytes(make_preferences())

        shortcut = self.module.PREFIX / "drive_c/users/test/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/光·遇.url"
        shortcut.parent.mkdir(parents=True)
        shortcut.write_bytes(b"[InternetShortcut]\r\nURL=fevergames://mygame/?gameId=63\r\n")
        self.shortcut = shortcut

        self.module.APPS_DB.parent.mkdir(parents=True)
        self.module.APPS_DB.write_text(json.dumps({
            self.module.PACKAGE_PARENT: {
                "entry_path": r"C:\\old.exe",
                "install_path": r"C:\\old",
            },
            self.module.PACKAGE_SKY_PREFIX + "fixture": {
                "game_id": "63",
                "install_path": r"C:\\FeverApps\\sky",
                "entry_path": r"C:\\FeverApps\\sky\\Sky.exe",
            },
        }), encoding="utf-8")

        self.module.PUBLIC_MMKV.parent.mkdir(parents=True)
        payload = b"exe_app_retina_zoom_ratio_" + self.module.PACKAGE_PARENT.encode() + b"\x04\x031.0"
        blob = struct.pack("<I", len(payload)) + payload + b"\0" * 16
        self.module.PUBLIC_MMKV.write_bytes(blob)
        meta = bytearray(112)
        struct.pack_into("<III", meta, 0, zlib.crc32(payload) & 0xFFFFFFFF, 4, 1)
        struct.pack_into("<III", meta, 28, len(payload), len(payload), zlib.crc32(payload) & 0xFFFFFFFF)
        self.module.PUBLIC_MMKV_CRC.write_bytes(meta)

    def tearDown(self):
        self.temp.cleanup()
        os.environ.pop("SKY_YYB_TEST_HOME", None)
        os.environ.pop("SKY_YYB_TEST_APPLICATIONS", None)
        os.environ.pop("SKY_YYB_TEST_CHIP", None)

    def test_complete_fix_and_restore(self):
        original_user = self.module.USER_REG.read_bytes()
        changes = self.module.apply_fix(60)
        self.assertTrue(changes)

        database = json.loads(self.module.APPS_DB.read_text())
        child = database[self.module.PACKAGE_SKY_PREFIX + "fixture"]
        self.assertEqual(child["entry_path"], "fevergames://mygame/?gameId=63&autoRun=1")
        self.assertIn('"RetinaMode"="Y"', self.module.USER_REG.read_text())
        self.assertIn(
            '"C:\\\\FeverApps\\\\sky\\\\Sky.exe"="~ HIGHDPIAWARE"',
            self.module.USER_REG.read_text(),
        )
        self.assertIn(b"\x04\x032.0", self.module.PUBLIC_MMKV.read_bytes())
        self.assertIn(b"gameId=63&autoRun=1", self.shortcut.read_bytes())

        prefs = self.module.PREFERENCES.read_bytes()
        self.assertIn(struct.pack("<I", 60), prefs)
        self.module.restore_latest()
        self.assertEqual(self.module.USER_REG.read_bytes(), original_user)
        self.assertNotIn(b"autoRun=1", self.shortcut.read_bytes())

    def test_unknown_preferences_are_rejected(self):
        self.module.PREFERENCES.write_bytes(b"not-a-preference-file")
        with self.assertRaises(self.module.FixError):
            self.module.apply_fix(60)

    def test_first_session_preferences_do_not_rollback_hd(self):
        name = b"kUserPreference_EnableReadbackBuffer\0"
        data = b"PREF" + struct.pack("<6I", 2, 1, 0, 0, 0, 36) + struct.pack("<II", 0, 1) + name
        self.module.PREFERENCES.write_bytes(data)
        self.module.apply_fix(60)
        self.assertEqual(self.module.PREFERENCES.read_bytes(), data)
        self.assertIn('"RetinaMode"="Y"', self.module.USER_REG.read_text())

    def test_fresh_mmkv_gets_missing_retina_keys_and_valid_metadata(self):
        payload = b"\x00\x03foo\x04\x03bar"
        blob = struct.pack("<I", len(payload)) + payload + b"\0" * 1024
        meta = bytearray(112)
        crc = zlib.crc32(payload) & 0xffffffff
        struct.pack_into("<III", meta, 0, crc, 4, 7)
        struct.pack_into("<III", meta, 28, len(payload), len(payload), crc)
        self.module.PUBLIC_MMKV.write_bytes(blob)
        self.module.PUBLIC_MMKV_CRC.write_bytes(meta)
        self.module.apply_fix(60)
        result = self.module.PUBLIC_MMKV.read_bytes()
        result_meta = self.module.PUBLIC_MMKV_CRC.read_bytes()
        size = struct.unpack_from("<I", result)[0]
        self.assertTrue(result[4:].startswith(payload))
        self.assertIn(b"exe_app_retina_zoom_ratio_" + self.module.PACKAGE_PARENT.encode() + b"\x04\x032.0", result[:size+4])
        self.assertIn(b"fixture\x04\x032.0", result[:size+4])
        self.assertEqual(struct.unpack_from("<III", result_meta, 28), (size, size, zlib.crc32(result[4:size+4]) & 0xffffffff))
        self.module.restore_latest()
        self.assertEqual(self.module.PUBLIC_MMKV.read_bytes(), blob)
        self.assertEqual(self.module.PUBLIC_MMKV_CRC.read_bytes(), meta)

    def test_discovers_both_yyb_internal_and_user_facing_shortcuts(self):
        package = self.module.PACKAGE_PARENT
        expected = []
        for root in (
            self.module.YYB_INTERNAL_SHORTCUTS,
            self.module.YYB_SHORTCUTS,
        ):
            app = root / f"{package}.app"
            app.joinpath("Contents").mkdir(parents=True)
            with app.joinpath("Contents/Info.plist").open("wb") as stream:
                plistlib.dump({"YYBPackageName": package}, stream)
            expected.append(app)
        self.assertEqual(self.module.all_shortcuts_for(package), expected)

    def test_m2_vulkan_transform_is_exact_and_idempotent(self):
        end = max(
            offset + len(original)
            for offset, original, _replacement in self.module.M2_WINEVULKAN_PATCHES
        )
        image = bytearray(end + 32)
        for offset, original, _replacement in self.module.M2_WINEVULKAN_PATCHES:
            image[offset:offset + len(original)] = original

        patched = self.module.patch_m2_winevulkan_image(bytes(image))
        for offset, _original, replacement in self.module.M2_WINEVULKAN_PATCHES:
            self.assertEqual(
                patched[offset:offset + len(replacement)],
                replacement,
            )
        self.assertEqual(
            self.module.patch_m2_winevulkan_image(patched),
            patched,
        )

    def test_m2_vulkan_transform_rejects_unknown_binary(self):
        end = max(
            offset + len(original)
            for offset, original, _replacement in self.module.M2_WINEVULKAN_PATCHES
        )
        with self.assertRaises(self.module.FixError):
            self.module.patch_m2_winevulkan_image(bytes(end + 32))


if __name__ == "__main__":
    unittest.main()
