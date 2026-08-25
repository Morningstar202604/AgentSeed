"""Cross-platform manifest consistency tests.

AgentSeed ships as one artifact to GitHub Releases and GitCode Releases
(npm is advertised in server.json only once the package actually exists).
These tests fail the build when plugin.json / package.json / server.json
drift apart (version, license, files list) — the exact failure mode that
shipped 1.3.3 vs 0.1.0 in the past.
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
        plugin_version = _load("plugin.json").get("version")
        package_version = _load("package.json").get("version")
        self.assertEqual(
            plugin_version,
            package_version,
            f"version drift plugin.json vs package.json: {plugin_version} != {package_version}",
        )
        # server.json may legitimately list zero registry packages while no
        # npm artifact exists; anything it DOES list must agree on version.
        packages = _load("server.json").get("packages") or []
        for i, pkg in enumerate(packages):
            self.assertEqual(
                pkg.get("version"),
                plugin_version,
                f"server.json packages[{i}] version drift",
            )

    def test_license_matches_across_manifests_and_file(self):
        licenses = {
            "plugin.json": _load("plugin.json").get("license"),
            "package.json": _load("package.json").get("license"),
            "server.json": _load("server.json").get("license"),
        }
        self.assertEqual(
            len(set(licenses.values())), 1, f"license drift across platforms: {licenses}"
        )
        declared = next(iter(set(licenses.values())))
        with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as fh:
            first_line = fh.readline().strip().lower()
        self.assertIn(
            declared.split("-")[0].lower(),
            first_line,
            f"LICENSE file does not match declared '{declared}'",
        )

    def test_package_files_entries_exist(self):
        for entry in _load("package.json").get("files", []):
            self.assertTrue(
                os.path.exists(os.path.join(ROOT, entry)),
                f"package.json 'files' entry missing on disk: {entry}",
            )


if __name__ == "__main__":
    unittest.main()
