"""CLI soft-wrap width contract."""

import unittest
from io import StringIO
from unittest.mock import patch

from spell_sync.cli_wrap import wrap_cli_line
from spell_sync.config import CLI_OUTPUT_WIDTH, CLI_WRAP_CONTINUATION_INDENT
from spell_sync.log import Log


class TestCliWrap(unittest.TestCase):
    def test_short_line_unchanged(self) -> None:
        self.assertEqual(wrap_cli_line("hello"), ["hello"])

    def test_soft_wrap_prefers_spaces(self) -> None:
        msg = "[info ] " + ("word " * 30).strip()
        lines = wrap_cli_line(msg, width=40, continuation_indent=2)
        self.assertTrue(all(len(line) <= 40 for line in lines))
        self.assertGreater(len(lines), 1)
        for line in lines[1:]:
            self.assertTrue(line.startswith("  "), line)
        # Reconstruction without hard-splitting "word"
        self.assertEqual(
            " ".join(line.strip() for line in lines),
            msg.strip(),
        )

    def test_continuation_uses_primary_indent_plus_hang(self) -> None:
        msg = "       " + ("alpha " * 40).strip()
        lines = wrap_cli_line(msg, width=40, continuation_indent=2)
        self.assertTrue(lines[0].startswith("       "))
        for line in lines[1:]:
            self.assertTrue(line.startswith("         "), repr(line[:12]))

    def test_hard_split_long_token(self) -> None:
        token = "x" * 50
        lines = wrap_cli_line(token, width=20, continuation_indent=2)
        self.assertTrue(all(len(line) <= 20 for line in lines))
        self.assertGreater(len(lines), 1)
        self.assertTrue(lines[1].startswith("  "))
        # Hang spaces are display-only; body concatenates to the token.
        body = lines[0] + "".join(line[2:] for line in lines[1:])
        self.assertEqual(body, token)

    def test_default_width_is_100(self) -> None:
        self.assertEqual(CLI_OUTPUT_WIDTH, 100)
        self.assertEqual(CLI_WRAP_CONTINUATION_INDENT, 2)
        msg = "[info ] " + ("path/segment/" * 20)
        lines = wrap_cli_line(msg)
        self.assertTrue(all(len(line) <= 100 for line in lines))

    def test_log_emit_wraps(self) -> None:
        buf = StringIO()
        long = "word " * 40
        with patch("sys.stdout", buf):
            Log().info(long.strip())
        out_lines = [line for line in buf.getvalue().splitlines() if line]
        self.assertTrue(all(len(line) <= 100 for line in out_lines))
        self.assertGreater(len(out_lines), 1)
        self.assertTrue(out_lines[0].startswith("[info ] "))
        for line in out_lines[1:]:
            self.assertTrue(line.startswith("  "))

    def test_log_write_wraps_even_when_quiet(self) -> None:
        buf = StringIO()
        long = "word " * 40
        quiet = Log(quiet=True)
        with patch("sys.stdout", buf):
            quiet.write(long.strip())
        out_lines = [line for line in buf.getvalue().splitlines() if line]
        self.assertTrue(all(len(line) <= 100 for line in out_lines))
        self.assertGreater(len(out_lines), 1)


if __name__ == "__main__":
    unittest.main()
