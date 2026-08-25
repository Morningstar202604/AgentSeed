"""Server/plugin version — single source of truth (plugin.json ``version``)."""

from __future__ import annotations

import json
import os


def plugin_version() -> str:
    """Return the ``version`` field of the root plugin.json, or ``"0.0.0"``."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        with open(os.path.join(root, "plugin.json"), encoding="utf-8") as fh:
            version = json.load(fh).get("version")
            return version if isinstance(version, str) else "0.0.0"
    except (OSError, ValueError):
        return "0.0.0"
