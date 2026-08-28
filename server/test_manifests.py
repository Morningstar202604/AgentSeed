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


class TestArtifactHygiene(unittest.TestCase):
    """What the release zip must NOT contain (and must contain)."""

    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "pack", os.path.join(ROOT, "scripts", "pack.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.pack = module

    def test_local_runtime_state_never_ships(self):
        """A local run wrote server/.agentseed/verification-log.jsonl and it
        ended up in the built artifact — an audit log (task names, absolute
        paths) must never ride along in a public zip."""
        skip_dirs = self.pack.ARTIFACT_SKIP_DIRS
        for runtime in (".agentseed", ".agentseed_cache", "__pycache__", ".git"):
            self.assertIn(runtime, skip_dirs, f"{runtime} would ship in the artifact")
        self.assertIn("verification-log.jsonl", self.pack.ARTIFACT_SKIP_FILES)
        for suffix in (".pyc", ".log"):
            self.assertIn(suffix, self.pack.ARTIFACT_SKIP_SUFFIXES)

    def test_artifact_ships_its_own_documentation(self):
        docs = self.pack.ARTIFACT_EXTRA_DOCS
        for name in ("README.md", "SECURITY.md"):
            self.assertIn(name, docs, f"{name} missing from the release artifact")
        for name in docs:
            self.assertTrue(
                os.path.exists(os.path.join(ROOT, name)),
                f"ARTIFACT_EXTRA_DOCS entry missing: {name}",
            )
        overlap = set(docs) & set(_load("package.json").get("files", []))
        self.assertEqual(overlap, set(), "artifact docs duplicated in package.json files")

    def test_npm_channel_ignores_the_same_state(self):
        """The npm artifact is packed from package.json "files" alone: `npm
        pack` never executes scripts/pack.py, so a whitelisted directory's
        nested .npmignore is the only thing standing between a maintainer's
        local runtime state (server/.agentseed/verification-log.jsonl,
        __pycache__, *.log) and the tarball users install. Every whitelisted
        directory must therefore express the same exclusions pack.py enforces
        for the zip channel, or the npm artifact leaks what the zip does not.
        """
        files = _load("package.json").get("files", [])
        dirs = [f.rstrip("/") for f in files if f.endswith("/")]
        self.assertTrue(dirs, "no whitelisted directories to guard")
        for d in dirs:
            ignore_path = os.path.join(ROOT, d, ".npmignore")
            with open(ignore_path, encoding="utf-8") as fh:
                rules = {line.strip() for line in fh if line.strip() and not line.startswith("#")}
            for skip_dir in self.pack.ARTIFACT_SKIP_DIRS:
                self.assertIn(f"{skip_dir}/", rules, f"{d}/.npmignore must exclude {skip_dir}/")
            for skip_file in self.pack.ARTIFACT_SKIP_FILES:
                self.assertIn(skip_file, rules, f"{d}/.npmignore must exclude {skip_file}")
            for suffix in self.pack.ARTIFACT_SKIP_SUFFIXES:
                # pack.py filters with endswith(); npm needs a glob, so a rule
                # covers a suffix when it appears bare or "*.suffix"-globbed.
                covered = (suffix in rules) or (f"*{suffix}" in rules)
                self.assertTrue(covered, f"{d}/.npmignore must exclude *{suffix}")


if __name__ == "__main__":
    unittest.main()
