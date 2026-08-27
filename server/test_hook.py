"""AgentSeed client-enforcement hook tests (stdlib unittest, subprocess)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "guard_hook.py")
PLUGIN_ROOT = os.path.dirname(HERE)
PY = sys.executable

OVERSOLD = "all tests pass, guaranteed"


def run_hook(payload=None, *extra: str) -> subprocess.CompletedProcess:
    stdin = "" if payload is None else json.dumps(payload)
    return subprocess.run(
        [PY, HOOK, *extra],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        cwd=PLUGIN_ROOT,
    )


class TestHookMode(unittest.TestCase):
    def test_pretooluse_clean_write_passes(self):
        r = run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "mod.py", "content": "x = 1\n"},
            }
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        v = json.loads(r.stdout)
        self.assertEqual(v["status"], "pass")
        self.assertFalse(v["blocking"])

    def test_pretooluse_blocks_oversold_write(self):
        r = run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "notes.md", "content": OVERSOLD + "\n"},
            }
        )
        self.assertEqual(r.returncode, 2, r.stdout)
        v = json.loads(r.stdout)
        self.assertEqual(v["status"], "blocked")
        self.assertTrue(v["blocking"])
        self.assertTrue(v["hits"])
        self.assertIn(OVERSOLD.split(",")[0], r.stderr)

    def test_pretooluse_blocks_hallucinated_symbol(self):
        r = run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "m.py", "content": "return magic_unknown()\n"},
            }
        )
        self.assertEqual(r.returncode, 2, r.stdout)
        v = json.loads(r.stdout)
        self.assertIn("magic_unknown", v["suspects"])

    def test_edit_new_string_is_scanned(self):
        r = run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Edit",
                "tool_input": {"file_path": "a.md", "old_string": "x", "new_string": OVERSOLD},
            }
        )
        self.assertEqual(r.returncode, 2, r.stdout)
        v = json.loads(r.stdout)
        self.assertEqual(v["status"], "blocked")

    def test_multiedit_edits_list_is_scanned(self):
        r = run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "MultiEdit",
                "tool_input": {
                    "file_path": "a.md",
                    "edits": [{"old_string": "x", "new_string": OVERSOLD}],
                },
            }
        )
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_warning_only_does_not_block(self):
        r = run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "m.py", "content": "# TODO: later\n"},
            }
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        v = json.loads(r.stdout)
        self.assertFalse(v["blocking"])
        self.assertTrue(v["hits"])  # reported, just not blocking

    def test_posttooluse_scans_file_from_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "doc.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("this module is production ready now\n")
            # no inline content key -> falls back to reading the file on disk
            r = run_hook(
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "NotebookSave",
                    "tool_input": {"file_path": path},
                }
            )
            self.assertEqual(r.returncode, 2, r.stdout)
            v = json.loads(r.stdout)
            self.assertEqual(v["status"], "blocked")

    def test_unsupported_extension_skips(self):
        r = run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "img.png", "content": OVERSOLD},
            }
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        v = json.loads(r.stdout)
        self.assertEqual(v["status"], "skipped")

    def test_unknown_tool_shape_skips(self):
        r = run_hook({"hook_event_name": "PostToolUse", "tool_name": "WebFetch", "tool_input": {}})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        v = json.loads(r.stdout)
        self.assertEqual(v["status"], "skipped")

    def test_malformed_stdin_fails_open(self):
        r = subprocess.run(
            [PY, HOOK],
            input="this is not json",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=PLUGIN_ROOT,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        v = json.loads(r.stdout)
        self.assertEqual(v["status"], "skipped")
        self.assertIn("not valid JSON", v["reason"])

    def test_empty_stdin_fails_open(self):
        r = run_hook(None)
        self.assertEqual(r.returncode, 0, r.stderr)
        v = json.loads(r.stdout)
        self.assertEqual(v["status"], "skipped")


class TestDirectFileScan(unittest.TestCase):
    def test_file_flag_scans_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "m.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("return magic_unknown()\n")
            r = run_hook(None, "--file", path)
            self.assertEqual(r.returncode, 2, r.stdout)
            v = json.loads(r.stdout)
            self.assertIn("magic_unknown", v["suspects"])

    def test_file_flag_missing_file_skips(self):
        r = run_hook(None, "--file", os.path.join(tempfile.gettempdir(), "no-such-file-xyz.py"))
        self.assertEqual(r.returncode, 0, r.stderr)
        v = json.loads(r.stdout)
        self.assertEqual(v["status"], "skipped")


class TestRegister(unittest.TestCase):
    def test_register_merges_idempotent_and_preserves_unrelated(self):
        with tempfile.TemporaryDirectory() as d:
            settings = os.path.join(d, "settings.json")
            with open(settings, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "model": "opus",
                        "hooks": {
                            "Stop": [{"hooks": [{"type": "command", "command": "notify.sh"}]}]
                        },
                    },
                    fh,
                )
            r1 = run_hook(None, "register", "--client", "claude", "--settings", settings)
            self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
            r2 = run_hook(None, "register", "--client", "claude", "--settings", settings)
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            with open(settings, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["model"], "opus")
            stop = data["hooks"]["Stop"]
            self.assertEqual(len(stop), 1)
            self.assertEqual(stop[0]["hooks"][0]["command"], "notify.sh")
            for ev in ("PreToolUse", "PostToolUse"):
                groups = data["hooks"][ev]
                agentseed_groups = [
                    g
                    for g in groups
                    if any("guard_hook.py" in str(h.get("command", "")) for h in g.get("hooks", []))
                ]
                self.assertEqual(len(agentseed_groups), 1, ev)
                self.assertEqual(agentseed_groups[0]["matcher"], "Write|Edit|MultiEdit")

    def test_register_leaves_rollback_backup(self):
        """Registration must never destroy the user's previous config (P1-8).

        Registering rewrites ~/.claude/settings.json (or ~/.cursor/hooks.json);
        a `.bak` of the exact pre-registration bytes is kept so the user can
        roll back if the merged result is not what their client expected.
        """
        with tempfile.TemporaryDirectory() as d:
            settings = os.path.join(d, "settings.json")
            original = {"model": "opus", "hooks": {}}
            with open(settings, "w", encoding="utf-8") as fh:
                json.dump(original, fh)
            r = run_hook(None, "register", "--client", "claude", "--settings", settings)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            backup = settings + ".bak"
            self.assertTrue(os.path.isfile(backup), "no .bak written before overwrite")
            with open(backup, encoding="utf-8") as fh:
                saved = json.load(fh)
            self.assertEqual(saved, original)
            with open(settings, encoding="utf-8") as fh:
                self.assertIn("PreToolUse", json.load(fh)["hooks"])

    def test_register_replaces_stale_agentseed_entries(self):
        with tempfile.TemporaryDirectory() as d:
            settings = os.path.join(d, "settings.json")
            stale = {"type": "command", "command": '"old-python" "old/guard_hook.py"'}
            with open(settings, "w", encoding="utf-8") as fh:
                json.dump({"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [stale]}]}}, fh)
            r = run_hook(None, "register", "--client", "claude", "--settings", settings)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(settings, encoding="utf-8") as fh:
                data = json.load(fh)
            groups = data["hooks"]["PreToolUse"]
            commands = [
                h["command"]
                for g in groups
                for h in g.get("hooks", [])
                if "guard_hook.py" in h.get("command", "")
            ]
            self.assertEqual(len(commands), 1)
            self.assertNotIn("old-python", commands[0])

    def test_register_cursor_merges_hooks_json_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            hooks_json = os.path.join(d, "hooks.json")
            with open(hooks_json, "w", encoding="utf-8") as fh:
                json.dump(
                    {"version": 1, "hooks": {"stop": [{"command": "notify.sh"}]}},
                    fh,
                )
            r1 = run_hook(None, "register", "--client", "cursor", "--settings", hooks_json)
            self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
            r2 = run_hook(None, "register", "--client", "cursor", "--settings", hooks_json)
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            with open(hooks_json, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["version"], 1)
            self.assertEqual(data["hooks"]["stop"], [{"command": "notify.sh"}])
            for ev in ("afterFileEdit", "preToolUse"):
                groups = data["hooks"][ev]
                mine = [
                    g
                    for g in groups
                    if any("guard_hook.py" in str(h.get("command", "")) for h in g.get("hooks", []))
                ]
                self.assertEqual(len(mine), 1, ev)

    def test_register_opencode_installs_plugin_file(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "plugin", "agentseed-guard.js")
            r = run_hook(None, "register", "--client", "opencode", "--settings", dest)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.isfile(dest))
            with open(dest, encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("tool.execute.before", body)
            self.assertIn("guard_hook.py", body)

    def test_register_bad_settings_json_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            settings = os.path.join(d, "settings.json")
            with open(settings, "w", encoding="utf-8") as fh:
                fh.write("{broken")
            r = run_hook(None, "register", "--client", "claude", "--settings", settings)
            self.assertEqual(r.returncode, 1)
            self.assertIn("cannot parse", r.stdout)


class TestCursorProtocol(unittest.TestCase):
    def test_afterfileedit_toplevel_shape_blocks_with_deny_json(self):
        event = {
            "hook_event_name": "afterFileEdit",
            "cursor_version": "1.7.2",
            "workspace_roots": ["C:/proj"],
            "file_path": "report.md",
            "edits": [{"old_string": "x", "new_string": OVERSOLD}],
        }
        r = run_hook(event)
        self.assertEqual(r.returncode, 2, r.stdout)
        v = json.loads(r.stdout.split('{"continue"')[0])  # verdict JSON first
        self.assertEqual(v["protocol"], "cursor")
        self.assertEqual(v["status"], "blocked")
        deny = r.stdout[r.stdout.index('{"continue"') :]
        self.assertIn('"permission": "deny"', deny)
        self.assertIn("agent_message", deny)

    def test_cursor_pretooluse_toolinput_shape_blocks(self):
        event = {
            "hook_event_name": "preToolUse",
            "cursor_version": "1.7.2",
            "workspace_roots": ["C:/proj"],
            "tool_name": "Write",
            "tool_input": {"file_path": "m.md", "content": OVERSOLD},
        }
        r = run_hook(event)
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_claude_payload_has_no_cursor_deny_json(self):
        r = run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "m.md", "content": OVERSOLD},
            }
        )
        self.assertEqual(r.returncode, 2)
        v = json.loads(r.stdout)
        self.assertEqual(v["protocol"], "claude")
        self.assertNotIn('"permission"', r.stdout)


if __name__ == "__main__":
    unittest.main()
