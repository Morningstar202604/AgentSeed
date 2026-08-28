"""Evidence receipts, the plugin toolchain (init/validate/pack/doctor), and
the 0.4 gate semantics (conformance degrade + baseline bootstrap)."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

import guard_engine as engine

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "guard_cli.py")
PLUGIN_ROOT = os.path.dirname(HERE)
PY = sys.executable

OVERSOLD = "all tests pass, guaranteed"


def run_cli(*argv, cwd=None):
    return subprocess.run(
        [PY, CLI, *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        cwd=cwd,
    )


def _write(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _gate_summary(result) -> dict:
    """The gate prints sub-stage output first; the summary is the last JSON
    object, the one that starts with the \"root\" key."""
    marker = '{\n  "root"'
    start = result.stdout.rindex(marker)
    return json.loads(result.stdout[start:])


class TestReceipts(unittest.TestCase):
    def test_receipt_hashes_files_and_links_the_audit_log(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(os.path.join(d, "m.py"), "x = 1\n")
            data_dir = os.path.join(d, ".agentseed")
            res = engine.build_receipt(
                "fix #1",
                [{"tool": "verify_code", "status": "pass"}],
                files=[src],
                data_dir=data_dir,
            )
            self.assertTrue(res["ok"], res)
            with open(res["path"], "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), res["digest"])
            receipt = res["receipt"]
            self.assertEqual(receipt["schema"], "agentseed.receipt.v1")
            self.assertEqual(receipt["files"][0]["path"], os.path.abspath(src))
            self.assertEqual(receipt["checks"][0]["tool"], "verify_code")
            log = os.path.join(data_dir, "verification-log.jsonl")
            with open(log, encoding="utf-8") as fh:
                lines = [json.loads(line) for line in fh if line.strip()]
            self.assertTrue(any(e["task"].startswith("receipt:") for e in lines))

    def test_missing_file_fails_loudly(self):
        res = engine.build_receipt("t", files=["no/such/file.py"], data_dir=self.temp())
        self.assertFalse(res["ok"])
        self.assertIn("files not found", res["error"])

    def test_blank_task_rejected(self):
        res = engine.build_receipt("   ", data_dir=self.temp())
        self.assertFalse(res["ok"])

    def test_two_receipts_in_one_second_get_distinct_paths(self):
        with tempfile.TemporaryDirectory() as d:
            r1 = engine.build_receipt("t", data_dir=d)
            r2 = engine.build_receipt("t", data_dir=d)
            self.assertTrue(r1["ok"] and r2["ok"])
            self.assertNotEqual(r1["path"], r2["path"])

    @staticmethod
    def temp() -> str:
        return tempfile.mkdtemp()


class TestPluginToolchain(unittest.TestCase):
    def test_init_validate_pack_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "demo")
            r1 = run_cli("plugin", "init", "demo", "--dir", target)
            self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
            self.assertTrue(os.path.isfile(os.path.join(target, "plugin.json")))
            self.assertTrue(
                os.path.isfile(os.path.join(target, "skills", "demo", "SKILL.md"))
            )
            r2 = run_cli("plugin", "validate", target)
            self.assertEqual(r2.returncode, 0, r2.stdout)
            self.assertTrue(json.loads(r2.stdout)["ok"])
            r3 = run_cli("plugin", "pack", target)
            pack1 = json.loads(r3.stdout)
            self.assertTrue(pack1["ok"], pack1)
            r4 = run_cli("plugin", "pack", target)
            pack2 = json.loads(r4.stdout)
            self.assertEqual(pack1["sha256"], pack2["sha256"], "pack must be deterministic")
            # a spec-legal name re-init must refuse to overwrite (exit 2)
            r5 = run_cli("plugin", "init", "demo", "--dir", target)
            self.assertEqual(r5.returncode, 2)

    def test_init_rejects_bad_names_and_scaffold_passes_its_own_linter(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_cli("plugin", "init", "Bad_Name", cwd=d)
            self.assertEqual(r.returncode, 2)
            r2 = run_cli("plugin", "init", "okname", cwd=d)
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            conf = engine.check_plugin_conformance(os.path.join(d, "okname"))
            self.assertTrue(conf["ok"], conf)

    def test_pack_refuses_non_plugin_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_cli("plugin", "pack", d)
            self.assertEqual(r.returncode, 1)
            self.assertIn("no plugin.json", r.stdout)

    def test_doctor_reports_live_mcp_and_conformance(self):
        r = run_cli("plugin", "doctor", PLUGIN_ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        report = json.loads(r.stdout)
        self.assertTrue(report["python"]["supported"])
        self.assertTrue(report["mcp_server"]["ok"], report["mcp_server"])
        self.assertGreaterEqual(report["mcp_server"]["tools"], 9)
        self.assertIsNotNone(report["plugin"])
        self.assertTrue(report["plugin"]["ok"], report["plugin"])
        self.assertTrue(any(v["installed"] for v in report["toolchain_verifiers"]))


class TestGateSemantics(unittest.TestCase):
    def test_gate_on_a_plain_repo_bootstraps_then_enforces(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "main.py"), "import os\nprint(os.getcwd())\n")
            r1 = run_cli("gate", "--root", d)
            self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
            s1 = _gate_summary(r1)
            self.assertEqual(s1["verdict"], "pass")
            self.assertEqual(s1["checks"]["conformance"]["status"], "skipped")
            self.assertEqual(s1["checks"]["scan"]["status"], "pass")
            self.assertTrue(os.path.isfile(os.path.join(d, "baseline-scan.json")))
            r2 = run_cli("gate", "--root", d)
            self.assertEqual(r2.returncode, 0)
            self.assertEqual(_gate_summary(r2)["verdict"], "pass")
            # --require-conformance restores the plugin-only contract, loudly
            r3 = run_cli("gate", "--root", d, "--require-conformance")
            self.assertEqual(r3.returncode, 1)
            self.assertEqual(_gate_summary(r3)["checks"]["conformance"]["status"], "fail")

    def test_gate_fails_on_new_hallucination_signals(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "main.py"), "import os\nprint(os.getcwd())\n")
            r1 = run_cli("gate", "--root", d)
            self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
            _write(os.path.join(d, "notes.md"), OVERSOLD + "\n")
            r2 = run_cli("gate", "--root", d)
            self.assertEqual(r2.returncode, 1)
            self.assertEqual(_gate_summary(r2)["checks"]["scan"]["status"], "fail")

    def test_verify_engine_auto_uses_best_available(self):
        with tempfile.TemporaryDirectory() as d:
            bad = _write(
                os.path.join(d, "bad.py"), "def f():\n    return magic_unknown()\n"
            )
            r = run_cli("verify", bad, "--engine", "auto")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            payload = json.loads(r.stdout)
            self.assertIn("magic_unknown", payload["suspects"])
            self.assertIn(payload["engine"], ("ruff", "pyflakes", "builtin", "standin"))
            r2 = run_cli("verify", bad, "--engine", "builtin")
            self.assertEqual(r2.returncode, 1, r2.stdout + r2.stderr)
            self.assertEqual(json.loads(r2.stdout)["engine"], "builtin")

    def test_verifiers_listing_runs(self):
        r = run_cli("verifiers")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        names = [v["name"] for v in json.loads(r.stdout)["verifiers"]]
        self.assertIn("ruff", names)

    def test_receipt_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(os.path.join(d, "m.py"), "x = 1\n")
            data_dir = os.path.join(d, ".data")
            r = run_cli(
                "receipt",
                "cli roundtrip",
                "--check",
                "verify_code=pass",
                "--file",
                src,
                "--data-dir",
                data_dir,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            payload = json.loads(r.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(os.path.isfile(payload["path"]))


if __name__ == "__main__":
    unittest.main()
