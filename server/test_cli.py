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
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("directory", r.stderr)

    def test_missing_path_is_usage_error_not_clean_scan(self):
        """A path that does not exist must never be scanned as inline text.

        The old fallback treated any unreadable argument as source code, so
        `scan src/ --strict` on a typo'd path reported clean / exit 0 — a
        guardrail that gives a false green is the one failure mode this
        project exists to prevent.
        """
        for cmd in ("verify", "scan", "imports"):
            with self.subTest(cmd=cmd):
                r = run_cli(cmd, "does_not_exist_xyz.py")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("does not exist", r.stderr)
                self.assertNotIn('"clean": true', r.stdout)
                self.assertNotIn('"imports_ok": true', r.stdout)

    def test_missing_path_with_separator_is_also_a_path(self):
        for arg in ("./src", "src/app.py", "~/code/x.py"):
            with self.subTest(arg=arg):
                r = run_cli("scan", arg)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_baseline_scan_missing_path_is_usage_error(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            r = run_cli(
                "scan", os.path.join(d, "nope"), "--baseline", os.path.join(d, "b.json")
            )
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("neither an existing file nor a directory", r.stderr)

    def test_multiline_inline_source_still_accepted(self):
        # the path heuristic must not swallow genuine inline source
        r = run_cli("verify", "import math\nprint(math.sqrt(4))\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_scan_string_allowlist_does_not_suppress_all(self):
        sys.path.insert(0, HERE)
        from guard_engine import scan_hallucination_words  # type: ignore

        # "tx": per-character iteration (the old bug) would see 't' and
        # suppress the hit; the coerced whole-string "tx" must not.
        r = scan_hallucination_words("x = todo()", allowlist="tx")
        self.assertEqual(len(r["hits"]), 1)

    def test_baseline_create_then_new_signal_fails(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "mod.py")
            base = os.path.join(d, "baseline.json")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# fine\nx = 1\n")
            r = run_cli("scan", d, "--baseline", base)  # no baseline yet -> creates
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.isfile(base))
            # same content: pass
            r = run_cli("scan", d, "--baseline", base)
            self.assertEqual(r.returncode, 0, r.stdout)
            # NEW oversold signal appears -> exit 1 and names it
            with open(src, "a", encoding="utf-8") as fh:
                fh.write("\n# all tests pass, guaranteed\n")
            r = run_cli("scan", d, "--baseline", base)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("oversold|all tests pass", r.stdout)
            # --update-baseline freezes the new state
            r = run_cli("scan", d, "--baseline", base, "--update-baseline")
            self.assertEqual(r.returncode, 0, r.stdout)
            r = run_cli("scan", d, "--baseline", base)
            self.assertEqual(r.returncode, 0, r.stdout)

    def test_baseline_line_edits_do_not_churn(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "doc.md")
            base = os.path.join(d, "baseline.json")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("production ready claim lives here\n")
            run_cli("scan", d, "--baseline", base)
            # moving the SAME hit to another line must stay green (line-free fp)
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("\n\n\nproduction ready claim lives here\n")
            r = run_cli("scan", d, "--baseline", base)
            self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
