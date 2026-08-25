"""Cross-platform manifest consistency tests.

AgentSeed is published to GitHub Releases, GitCode Releases and npm from a
single artifact. These tests fail the build when plugin.json / package.json /
server.json drift apart (version, license, files list) — the exact failure
mode that shipped 1.3.3 vs 0.1.0 in the past.
"""

from __future__ import annotations

import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name: str) -> dict:
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return json.load(fh)


class TestManifestConsistency(unittest.TestCase):
    def test_versions_match_across_manifests(self):
        versions = {
            "plugin.json": _load("plugin.json").get("version"),
            "package.json": _load("package.json").get("version"),
            "server.json packages[0]": (_load("server.json").get("packages") or [{}])[0].get("version"),
        }
        self.assertEqual(
            len(set(versions.values())), 1,
            f"version drift across platforms: {versions}",
        )
        self.assertNotIn(None, set(versions.values()))

    def test_license_matches_across_manifests_and_file(self):
        licenses = {
            "plugin.json": _load("plugin.json").get("license"),
            "package.json": _load("package.json").get("license"),
            "server.json": _load("server.json").get("license"),
        }
        self.assertEqual(len(set(licenses.values())), 1,
                         f"license drift across platforms: {licenses}")
        declared = next(iter(set(licenses.values())))
        with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as fh:
            first_line = fh.readline().strip().lower()
        self.assertIn(declared.split("-")[0].lower(), first_line,
                      f"LICENSE file does not match declared '{declared}'")

    def test_package_files_entries_exist(self):
        for entry in _load("package.json").get("files", []):
            self.assertTrue(os.path.exists(os.path.join(ROOT, entry)),
                            f"package.json 'files' entry missing on disk: {entry}")


if __name__ == "__main__":
    unittest.main()
