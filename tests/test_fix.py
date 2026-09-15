#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
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
        self.module.PUBLIC_MMKV_CRC.write_bytes(struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF) + b"\0" * 28)

    def tearDown(self):
        self.temp.cleanup()
        os.environ.pop("SKY_YYB_TEST_HOME", None)
        os.environ.pop("SKY_YYB_TEST_APPLICATIONS", None)

    def test_complete_fix_and_restore(self):
        original_user = self.module.USER_REG.read_bytes()
        changes = self.module.apply_fix(60)
        self.assertTrue(changes)

        database = json.loads(self.module.APPS_DB.read_text())
        child = database[self.module.PACKAGE_SKY_PREFIX + "fixture"]
        self.assertEqual(child["entry_path"], "fevergames://mygame/?gameId=63&autoRun=1")
        self.assertIn('"RetinaMode"="Y"', self.module.USER_REG.read_text())
        self.assertIn(b"\x04\x032.0", self.module.PUBLIC_MMKV.read_bytes())

        prefs = self.module.PREFERENCES.read_bytes()
        self.assertIn(struct.pack("<I", 60), prefs)
        self.module.restore_latest()
        self.assertEqual(self.module.USER_REG.read_bytes(), original_user)

    def test_unknown_preferences_are_rejected(self):
        self.module.PREFERENCES.write_bytes(b"not-a-preference-file")
        with self.assertRaises(self.module.FixError):
            self.module.apply_fix(60)


if __name__ == "__main__":
    unittest.main()
