"""AgentSeed release packer — consistency gate + artifact build + SHA256.

Single source of truth for publishing to every platform (GitHub Releases,
GitCode Releases, npm). One invocation:

  1. Verifies plugin.json / package.json / server.json agree on version and
     license (exits non-zero on any drift — the multi-platform killer).
  2. Stages the files listed in package.json "files" plus ARTIFACT_EXTRA_DOCS
     (READMEs, SECURITY, CONTRIBUTING, DESIGN) so an installed plugin is
     self-documenting.
  3. Builds dist/agentseed-<version>.zip and dist/SHA256SUMS.txt.

The SAME zip + the SAME hash are uploaded everywhere; users pin it via
``--sha256`` / ``-Sha256`` on the installers, so platform mirrors cannot
serve tampered archives unnoticed.

Usage:
  python scripts/pack.py                 # check + build
  python scripts/pack.py --check-only    # manifest drift gate (CI)
Zero third-party dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Documentation the release zip must carry so an installed plugin is readable
# on its own. npm ships README/LICENSE regardless of package.json "files", so
# this list is only for the zip that the installers download; missing paths
# are skipped by build().
ARTIFACT_EXTRA_DOCS = [
    "README.md",
    "README.zh.md",
    "README.ja.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "DESIGN.md",
    "DESIGN.zh.md",
    "DESIGN.ja.md",
]


def _load(name: str) -> dict:
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return json.load(fh)


def check_consistency() -> list[str]:
    """Cross-platform manifest drift checks. Empty list == green."""
    errors: list[str] = []
    plugin = _load("plugin.json")
    pkg = _load("package.json")
    server = _load("server.json")

    # server.json may legitimately advertise zero registry packages while no
    # npm artifact exists; any package it DOES list must agree on version.
    versions = {
        "plugin.json": plugin.get("version"),
        "package.json": pkg.get("version"),
    }
    for i, entry in enumerate(server.get("packages") or []):
        versions[f"server.json packages[{i}]"] = (entry or {}).get("version")
    unique = set(versions.values())
    if len(unique) != 1 or None in unique:
        errors.append(f"version drift across manifests: {versions}")

    licenses = {
        "plugin.json": plugin.get("license"),
        "package.json": pkg.get("license"),
        "server.json": server.get("license"),
    }
    if len(set(licenses.values())) != 1:
        errors.append(f"license drift across manifests: {licenses}")

    lic_path = os.path.join(ROOT, "LICENSE")
    try:
        with open(lic_path, encoding="utf-8") as fh:
            first_line = fh.readline().strip().lower()
        expected = str(next(iter(set(licenses.values())))).split("-")[0].lower()
        if expected not in first_line:
            errors.append(
                f"LICENSE file starts with '{first_line}' which does not "
                f"match declared license '{licenses['plugin.json']}'"
            )
    except OSError as exc:
        errors.append(f"LICENSE unreadable: {exc}")

    files_list = pkg.get("files")
    if not isinstance(files_list, list) or not files_list:
        errors.append("package.json 'files' must be a non-empty array")
    else:
        for entry in files_list:
            if not os.path.exists(os.path.join(ROOT, entry)):
                errors.append(f"package.json 'files' entry missing on disk: {entry}")
    return errors


# Runtime state and tool caches that must never enter a public artifact.
ARTIFACT_SKIP_DIRS = {
    "__pycache__",
    ".git",
    ".agentseed",
    ".agentseed_cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
}
ARTIFACT_SKIP_FILES = {"verification-log.jsonl"}
ARTIFACT_SKIP_SUFFIXES = (".pyc", ".log")


def build() -> tuple[str, str]:
    """Build dist/agentseed-<version>.zip; returns (zip_path, sha256_hex)."""
    pkg = _load("package.json")
    version = pkg["version"]
    dist = os.path.join(ROOT, "dist")
    if os.path.isdir(dist):
        shutil.rmtree(dist)
    os.makedirs(dist)

    zip_name = f"agentseed-{version}.zip"
    zip_path = os.path.join(dist, zip_name)
    entries: list[str] = []
    for raw in list(pkg["files"]) + ARTIFACT_EXTRA_DOCS:
        full = os.path.join(ROOT, raw)
        if os.path.isdir(full):
            for base, dirs, names in os.walk(full):
                # never ship caches, VCS metadata, or local runtime state: an
                # audit log written under server/.agentseed/ during a local run
                # would otherwise leave the build machine in a public artifact
                dirs[:] = [d for d in dirs if d not in ARTIFACT_SKIP_DIRS]
                entries.extend(
                    os.path.join(base, n)
                    for n in names
                    if n not in ARTIFACT_SKIP_FILES
                    and not n.endswith(ARTIFACT_SKIP_SUFFIXES)
                )
        elif os.path.isfile(full):
            entries.append(full)
    # Deterministic archive: fixed timestamp + sorted order so the same
    # tree always yields the same SHA256 across rebuilds/platforms.
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(entries):
            arc = os.path.relpath(p, ROOT).replace(os.sep, "/")
            info = zipfile.ZipInfo(arc, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            zf.writestr(info, open(p, "rb").read())
    return zip_path, _sha256(zip_path)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str]) -> int:
    args = argv[1:]
    check_only = "--check-only" in args
    errors = check_consistency()
    if errors:
        print("MANIFEST DRIFT — fix before publishing:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("manifests consistent: version/license/files OK")
    if check_only:
        return 0

    zip_path, digest = build()
    sums_path = os.path.join(os.path.dirname(zip_path), "SHA256SUMS.txt")
    zip_name = os.path.basename(zip_path)
    with open(sums_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{digest}  {zip_name}\n")

    version = _load("plugin.json")["version"]
    print(f"built {os.path.relpath(zip_path, ROOT)}")
    print(f"sha256 {digest}")
    print("")
    print("publish steps (same artifact + same hash on ALL platforms):")
    print(
        f"  GitHub : gh release create v{version} '{zip_path}' --title v{version} --notes-file <notes>"
    )
    print("  GitCode: upload the SAME zip via web UI or API release endpoint")
    print(f"  npm    : npm publish   (bin/cli.js shim; package.json already at {version})")
    print("")
    print("tell users to pin integrity:")
    print(f"  ./install.sh  --sha256 {digest}")
    print(f"  .\\install.ps1 -Sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
