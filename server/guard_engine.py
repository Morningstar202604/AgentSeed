"""AgentSeed guard engine — path-setup hub + standalone self-check.

This module is the single entry point that sets up ``sys.path`` so that
``engine/`` can be imported from any working directory, and re-exports the
``engine`` package's public API (the old ``from engine import *`` contract the
tests and the MCP server rely on). All entry-point scripts (server, CLI,
tests) import through this module instead of duplicating the
``sys.path.insert(0, ...)`` boilerplate.

Run ``python server/guard_engine.py`` for a dependency-free end-to-end
self-check: it exercises the two core detectors on tiny samples and prints
the results, proving the engine works without starting the MCP server.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import *  # noqa: E402, F401, F403
from engine import (  # noqa: E402  (explicit names clear F405 in _self_check)
    plugin_version,
    detect_undefined_symbols,
    defined_symbols,
    scan_hallucination_words,
)


def check_contract(source: str, contract: str, language: str = "python") -> dict:
    """Verify source against a declared contract (the roadmap 'check_contract').

    ``contract`` is a JSON string:
        {"requires": ["symbol", ...], "prohibits": ["token", ...]}
    - ``requires``: names the module MUST define or import (checked against
      ``defined_symbols`` for the same language set as ``verify_code``).
    - ``prohibits``: tokens that MUST NOT appear (word-boundary scan).

    Returns:
        {"language", "contract_ok", "missing": [...], "prohibited_hits": [...],
         "note"}
    """
    try:
        spec = json.loads(contract)
    except (ValueError, TypeError) as exc:
        return {
            "language": language,
            "contract_ok": False,
            "missing": [],
            "prohibited_hits": [],
            "note": f"invalid contract JSON: {exc}",
        }
    if not isinstance(spec, dict):
        return {
            "language": language,
            "contract_ok": False,
            "missing": [],
            "prohibited_hits": [],
            "note": "contract must be a JSON object",
        }
    requires = [r for r in spec.get("requires", []) if isinstance(r, str) and r]
    prohibits = [p for p in spec.get("prohibits", []) if isinstance(p, str) and p]

    defined = set(defined_symbols(source, language))
    missing = [r for r in requires if r not in defined]
    hits = [
        p
        for p in prohibits
        if re.search(r"\b" + re.escape(p) + r"\b", source, re.IGNORECASE)
    ]
    return {
        "language": language,
        "contract_ok": not missing and not hits,
        "missing": missing,
        "prohibited_hits": hits,
        "note": (
            "Contract check: 'requires' names must be defined/imported by the "
            "source; 'prohibits' tokens must not appear anywhere."
        ),
    }


def _self_check() -> int:
    print(f"AgentSeed engine self-check (version {plugin_version()})")
    ok = True

    # 1) verify_code must catch a hallucinated (never-defined) symbol
    res = detect_undefined_symbols("def f():\n    return magic_unknown()\n", "python")
    suspects = res.get("suspects", [])
    if "magic_unknown" in suspects:
        print(f"  verify_code        -> caught hallucinated symbol {suspects}")
    else:
        print(f"  verify_code        -> FAIL: expected 'magic_unknown', got {suspects}")
        ok = False

    # 2) scan_hallucination must catch an overclaim
    res = scan_hallucination_words("All tests pass, production ready. Trust me.")
    if not res.get("clean", True):
        print(f"  scan_hallucination -> caught {len(res.get('hits', []))} overclaim signal(s)")
    else:
        print("  scan_hallucination -> FAIL: expected an overclaim to be flagged")
        ok = False

    print("self-check: " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_self_check())
