#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


def load_script(name: str, path: Path, test_home: Path):
    os.environ["YYB_INTEL_TEST_HOME"] = str(test_home)
    module_name = f"test_{name}_{id(test_home)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def make_preferences() -> bytes:
    names = [b"quality_fps\0", b"kUserPreference_MotionBlurScalar\0"]
    counts = (2, 0, 0, 0)
    string_base = 28 + 16
    header = b"PREF" + b"\0" * 4 + struct.pack("<4I", *counts) + struct.pack("<I", string_base)
    records = struct.pack("<II", 0, 30) + struct.pack("<II", len(names[0]), 0x3F800000)
    return header + records + b"".join(names)


def make_preferences_without_fps() -> bytes:
    name = b"some_flag\0"
    string_base = 28 + 8
    header = b"PREF" + b"\0" * 4 + struct.pack("<4I", 1, 0, 0, 0)
    return header + struct.pack("<I", string_base) + struct.pack("<II", 0, 1) + name


class IntelFixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"

    def tearDown(self):
        self.temp.cleanup()
        os.environ.pop("YYB_INTEL_TEST_HOME", None)

    def test_retina_registry_patch_is_idempotent_and_preserves_paths(self):
        module = load_script(
            "intel_retina", REPO / "intel/apply-intel-retina.py", self.home
        )
        module.PREFIX.mkdir(parents=True)
        module.USER_REG.write_text("WINE REGISTRY Version 2\n", encoding="utf-8")
        module.SYSTEM_REG.write_text("WINE REGISTRY Version 2\n", encoding="utf-8")
        module.PREFERENCES.parent.mkdir(parents=True)
        original_preferences = make_preferences()
        module.PREFERENCES.write_bytes(original_preferences)

        backup = module.apply()
        self.assertIsNotNone(backup)
        first_user = module.USER_REG.read_text(encoding="utf-8")
        first_system = module.SYSTEM_REG.read_text(encoding="utf-8")
        self.assertIn('"RetinaMode"="Y"', first_user)
        self.assertIn(
            '"C:\\\\FeverApps\\\\sky\\\\Sky.exe"="~ HIGHDPIAWARE"', first_user
        )
        self.assertIn('"dpiAwareness"=dword:00000002', first_system)
        patched_preferences = module.PREFERENCES.read_bytes()
        self.assertIn(struct.pack("<I", 60), patched_preferences)
        self.assertNotEqual(original_preferences, patched_preferences)
        self.assertIsNone(module.apply())
        self.assertEqual(first_user, module.USER_REG.read_text(encoding="utf-8"))

        module.USER_REG.write_text("changed\n", encoding="utf-8")
        restored_from = module.restore_latest()
        self.assertEqual(restored_from, backup)
        self.assertEqual("WINE REGISTRY Version 2\n", module.USER_REG.read_text(encoding="utf-8"))
        self.assertEqual(original_preferences, module.PREFERENCES.read_bytes())

    def test_launchpad_windows_paths_keep_single_and_escaped_slashes(self):
        module = load_script(
            "intel_launchpad", REPO / "intel/sync-launchpad-apps.py", self.home
        )
        self.assertEqual(
            module.windows_path(r"C:\Games\Sky"), module.DRIVE_C / "Games/Sky"
        )
        self.assertEqual(
            module.windows_path(r"C:\\Games\\Sky"), module.DRIVE_C / "Games/Sky"
        )
        module.USER_REG.parent.mkdir(parents=True)
        module.USER_REG.write_text("WINE REGISTRY Version 2\n", encoding="utf-8")
        sky = module.DRIVE_C / "FeverApps/sky/Sky.exe"
        sky.parent.mkdir(parents=True)
        sky.write_bytes(b"MZ-fixture")
        games = module.discover_netease_games()
        self.assertEqual([(game.game_id, game.name) for game in games], [("63", "光·遇")])
        self.assertEqual(
            games[0].launch_arguments,
            ["netease-game", "63"],
        )

    def test_official_download_is_verified_and_rejects_path_traversal(self):
        module = load_script(
            "intel_download", REPO / "intel/download-sky.py", self.home
        )
        payload = b"official-sky-fixture"
        expected = hashlib.md5(payload).hexdigest()
        original_urlopen = module.urllib.request.urlopen
        module.urllib.request.urlopen = lambda *_args, **_kwargs: FakeResponse(payload)
        try:
            size = module.complete_file(
                {
                    "path": "fixture/data.bin",
                    "url": "https://example.invalid/data.bin",
                    "md5": expected,
                    "size": len(payload),
                }
            )
        finally:
            module.urllib.request.urlopen = original_urlopen
        self.assertEqual(size, len(payload))
        self.assertEqual((module.SKY_DIR / "fixture/data.bin").read_bytes(), payload)
        with self.assertRaises(module.DownloadError):
            module.target_for("../outside.bin")

    def test_first_run_preferences_wait_for_game_to_add_fps_field(self):
        module = load_script(
            "intel_retina_first_run",
            REPO / "intel/apply-intel-retina.py",
            self.home,
        )
        module.PREFIX.mkdir(parents=True)
        module.USER_REG.write_text("WINE REGISTRY Version 2\n", encoding="utf-8")
        module.SYSTEM_REG.write_text("WINE REGISTRY Version 2\n", encoding="utf-8")
        module.PREFERENCES.parent.mkdir(parents=True)
        module.PREFERENCES.write_bytes(make_preferences_without_fps())
        self.assertIsNone(module.patched_preferences(60))
        self.assertIsNotNone(module.apply(60))


if __name__ == "__main__":
    unittest.main()
