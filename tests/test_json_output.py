#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from spell_sync.json_output import emit_json


class TestJsonOutput(unittest.TestCase):
    def test_emit_json_requires_command_and_exit(self):
        with self.assertRaises(ValueError) as ctx:
            emit_json({"command": "status"})
        self.assertIn("exit", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            emit_json({"exit": 0})
        self.assertIn("command", str(ctx.exception))
