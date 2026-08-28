"""Generic plugin artifact packer (the `plugin pack` toolchain command).

Deterministic zip of an Agent Plugins root: fixed timestamp + sorted order,
so the same tree always yields the same SHA256 across rebuilds/platforms.

Skip rules are IMPORTED from scripts/pack.py when the source checkout is
present (single source of truth). The fallback constants below serve
installed copies that do not ship scripts/; server/test_manifests.py pins
the fallback to the packer's constants so the two can never drift silently.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile

# Fallback for installed copies (npm ships bin/, server/, skills/ only).
_FALLBACK_SKIP_DIRS = {
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
_FALLBACK_SKIP_FILES = {"verification-log.jsonl"}
_FALLBACK_SKIP_SUFFIXES = (".pyc", ".log")

# scripts/pack.py stages an explicit file list, so it never walks the packer's
# own output or dependency trees; a whole-root walker must.
_PACK_WALK_SKIP_DIRS = {"dist", "node_modules"}
_PACK_WALK_SKIP_SUFFIXES = (".zip",)


def _load_pack_constants():
    here = os.path.dirname(os.path.abspath(__file__))
    scripts = os.path.join(os.path.dirname(os.path.dirname(here)), "scripts")
    if not os.path.isdir(scripts):
        return None
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        import pack  # scripts/pack.py
    except Exception:  # noqa: BLE001 - installed copy without a usable scripts/
        return None
    return pack.ARTIFACT_SKIP_DIRS, pack.ARTIFACT_SKIP_FILES, pack.ARTIFACT_SKIP_SUFFIXES


_LOADED = _load_pack_constants()
if _LOADED is not None:
    SKIP_DIRS, SKIP_FILES, SKIP_SUFFIXES = _LOADED
else:
    SKIP_DIRS = _FALLBACK_SKIP_DIRS
    SKIP_FILES = _FALLBACK_SKIP_FILES
    SKIP_SUFFIXES = _FALLBACK_SKIP_SUFFIXES


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def pack_plugin(root: str, out_dir: str | None = None) -> dict:
    """Zip one plugin root deterministically; returns {"ok","path","sha256","files"}."""
    root = os.path.abspath(root)
    manifest = os.path.join(root, "plugin.json")
    if not os.path.isfile(manifest):
        return {
            "ok": False,
            "error": f"no plugin.json in {root} — 'plugin pack' packages an Agent Plugins root",
        }
    try:
        with open(manifest, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": f"plugin.json unreadable: {exc}"}
    name = str(data.get("name") or "plugin")
    version = str(data.get("version") or "0.0.0")
    out_dir = os.path.abspath(out_dir) if out_dir else os.path.join(root, "dist")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "error": f"cannot create output dir: {exc}"}
    zip_path = os.path.join(out_dir, f"{name}-{version}.zip")
    entries: list[str] = []
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(
            d for d in dirs if d not in SKIP_DIRS and d not in _PACK_WALK_SKIP_DIRS
        )
        for fn in sorted(names):
            if fn in SKIP_FILES:
                continue
            if fn.endswith(SKIP_SUFFIXES) or fn.endswith(_PACK_WALK_SKIP_SUFFIXES):
                continue
            p = os.path.abspath(os.path.join(base, fn))
            if p == os.path.abspath(zip_path):
                continue
            entries.append(p)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(entries):
                arc = os.path.relpath(p, root).replace(os.sep, "/")
                info = zipfile.ZipInfo(arc, date_time=(1980, 1, 1, 0, 0, 0))
                info.external_attr = 0o644 << 16
                with open(p, "rb") as fh:
                    zf.writestr(info, fh.read())
    except OSError as exc:
        return {"ok": False, "error": f"cannot write zip: {exc}"}
    return {"ok": True, "path": zip_path, "sha256": _sha256(zip_path), "files": len(entries)}
