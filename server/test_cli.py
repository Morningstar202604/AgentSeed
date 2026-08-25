"""AgentSeed CLI tests (stdlib unittest, run the CLI as a subprocess)."""

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "guard_cli.py")
PLUGIN_ROOT = os.path.dirname(HERE)
PY = sys.executable


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, CLI, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        cwd=PLUGIN_ROOT,
    )


class TestCli(unittest.TestCase):
    def test_verify_clean_exit_zero(self):
        r = run_cli("verify", "import math\nprint(math.sqrt(4))\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_verify_hallucinated_exit_one(self):
        r = run_cli("verify", "return magic_unknown()\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("magic_unknown", r.stdout)

    def test_scan_warning_only_does_not_block(self):
        # TODO alone is warning-severity by default -> exit 0
        r = run_cli("scan", "# TODO: later\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn('"blocking": false', r.stdout)

    def test_scan_strict_blocks_stub(self):
        r = run_cli("scan", "# TODO: later\n", "--strict")
        self.assertEqual(r.returncode, 1)

    def test_scan_oversold_blocks(self):
        r = run_cli("scan", "all tests pass, guaranteed\n")
        self.assertEqual(r.returncode, 1)

    def test_check_self_ci_pass(self):
        r = run_cli("check", PLUGIN_ROOT, "--ci")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn('"ok": true', r.stdout)

    def test_check_bad_plugin_fails(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            r = run_cli("check", d, "--ci")  # missing plugin.json
            self.assertEqual(r.returncode, 1)

    def test_sandbox_runs_and_exit_code(self):
        r = run_cli("sandbox", "--", PY, "-c", "print(42)")
        self.assertEqual(r.returncode, 0)
        self.assertIn("42", r.stdout)

    def test_sandbox_propagates_child_failure(self):
        r = run_cli("sandbox", "--", PY, "-c", "raise SystemExit(3)")
        self.assertEqual(r.returncode, 3)

    def test_sandbox_missing_command_is_failure_not_pass(self):
        r = run_cli("sandbox", "--", "definitely-not-a-real-cmd-xyz")
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_verify_directory_gives_clean_error(self):
        r = run_cli("verify", PLUGIN_ROOT)  # a directory
        self.assertEqual(r.returncode, 1)
        self.assertIn("directory", r.stderr)

    def test_scan_string_allowlist_does_not_suppress_all(self):
        sys.path.insert(0, HERE)
        from guard_engine import scan_hallucination_words  # type: ignore

        # "tx": per-character iteration (the old bug) would see 't' and
        # suppress the hit; the coerced whole-string "tx" must not.
        r = scan_hallucination_words("x = todo()", allowlist="tx")
        self.assertEqual(len(r["hits"]), 1)


if __name__ == "__main__":
    unittest.main()
