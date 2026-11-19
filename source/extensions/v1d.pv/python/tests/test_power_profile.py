# SPDX-License-Identifier: MIT
import importlib.util
import subprocess
import unittest
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "v1d" / "pv" / "ui" / "power_profile.py"
_spec = importlib.util.spec_from_file_location("v1d_power_profile", _PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
active_profile = _mod.active_profile
profile_ids = _mod.profile_ids
set_profile = _mod.set_profile


def _ok(stdout: str = "", code: int = 0):
    def run(args, **_kwargs):
        if args[:2] == ["powerprofilesctl", "get"]:
            return subprocess.CompletedProcess(args, code, stdout=stdout, stderr="")
        if args[:2] == ["powerprofilesctl", "set"]:
            return subprocess.CompletedProcess(args, code, stdout="", stderr="" if code == 0 else "denied")
        raise AssertionError(args)

    return run


class TestPowerProfile(unittest.TestCase):
    def test_ids_match_menu(self):
        self.assertEqual(profile_ids(), ("performance", "balanced", "power-saver"))

    def test_active_strips_name(self):
        self.assertEqual(active_profile(_ok("balanced\n")), "balanced")

    def test_active_missing_tool(self):
        def run(*_a, **_k):
            raise FileNotFoundError

        self.assertIsNone(active_profile(run))

    def test_set_rejects_unknown(self):
        ok, err = set_profile("turbo", _ok())
        self.assertFalse(ok)
        self.assertIn("unknown", err)

    def test_set_ok(self):
        ok, err = set_profile("performance", _ok())
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_set_failure_message(self):
        ok, err = set_profile("power-saver", _ok(code=1))
        self.assertFalse(ok)
        self.assertEqual(err, "denied")


if __name__ == "__main__":
    unittest.main()
