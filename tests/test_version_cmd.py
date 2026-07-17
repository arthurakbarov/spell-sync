#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""version command tests."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import spell_sync.version_cmd as version_mod
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode


class TestVersionCmd(unittest.TestCase):
    def test_version_prints_installed(self):
        buf = io.StringIO()
        with (
            patch.object(version_mod, "installed_package_version", return_value="0.1.0"),
            redirect_stdout(buf),
        ):
            code = version_mod.cmd_version(CliOptions())
        self.assertEqual(code, int(ExitCode.OK))
        self.assertEqual(buf.getvalue().strip(), "0.1.0")

    def test_version_json(self):
        buf = io.StringIO()
        with (
            patch.object(version_mod, "installed_package_version", return_value="0.1.0"),
            redirect_stdout(buf),
        ):
            code = version_mod.cmd_version(CliOptions(json_output=True))
        self.assertEqual(code, int(ExitCode.OK))
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["version"], "0.1.0")
        self.assertEqual(payload["command"], "version")


if __name__ == "__main__":
    unittest.main(verbosity=2)
