#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

import stellar_blade_fix as fix


class FakeBackups:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def capture(self, path: Path) -> None:
        self.paths.append(path)


class StellarBladeFixTests(unittest.TestCase):
    def test_ini_patch_is_scoped_and_idempotent(self):
        original = "[First]\nValue=old\n\n[Target]\nValue=old\n"
        once = fix.set_ini_values(original, "Target", {"Value": "new", "Added": "yes"})
        twice = fix.set_ini_values(once, "Target", {"Value": "new", "Added": "yes"})
        self.assertEqual(once, twice)
        self.assertIn("[First]\nValue=old", once)
        self.assertIn("[Target]\nValue=new\nAdded=yes", once)

    def test_steam_launch_options_are_written_to_app_block(self):
        with tempfile.TemporaryDirectory() as temp:
            userdata = Path(temp) / "userdata"
            config = userdata / "123/config/localconfig.vdf"
            config.parent.mkdir(parents=True)
            config.write_text(
                '"UserLocalConfigStore"\n{\n'
                '\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n'
                '\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n'
                '\t\t\t\t{\n\t\t\t\t\t"3489700"\n'
                '\t\t\t\t\t{\n\t\t\t\t\t\t"LastPlayed"\t\t"1"\n'
                '\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n',
                encoding="utf-8",
            )
            backups = FakeBackups()
            with mock.patch.object(fix, "STEAM_USERDATA", userdata):
                fix.patch_steam_launch_options(backups)
                first = config.read_text(encoding="utf-8")
                fix.patch_steam_launch_options(backups)
                second = config.read_text(encoding="utf-8")
            self.assertEqual(first, second)
            self.assertEqual(first.count('"LaunchOptions"'), 1)
            self.assertIn("-NoStartupMovies", first)
            self.assertEqual(backups.paths, [config, config])


if __name__ == "__main__":
    unittest.main()
