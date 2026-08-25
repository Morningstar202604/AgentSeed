"""AgentSeed verification audit trail (P2-10).

The SDD contract requires a completion report with attached evidence, but
until now nothing persisted verification history. ``record_verification``
appends one JSONL line per call to

    ${PLUGIN_DATA}/verification-log.jsonl   (fallback: ./.agentseed/)

creating a tamper-evident-by-append audit trail agents (or CI) can cite.
Zero dependencies; stdlib only.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from .version import plugin_version

VALID_STATUSES = {"pass", "fail", "skipped"}


def audit_path(data_dir: str | None = None) -> str:
    base = data_dir or os.environ.get("PLUGIN_DATA") or os.path.join(os.getcwd(), ".agentseed")
    return os.path.join(base, "verification-log.jsonl")


def record_verification(
    task: str,
    checks: list[dict] | None = None,
    summary: str | None = None,
    data_dir: str | None = None,
) -> dict:
    """Append one verification record; returns {"ok", "path", "entries"}."""
    if not isinstance(task, str) or not task.strip():
        return {"ok": False, "error": "task must be a non-empty string", "path": "", "entries": 0}
    clean_checks = []
    for c in checks if isinstance(checks, list) else []:
        if not isinstance(c, dict):
            continue
        status = c.get("status")
        if status not in VALID_STATUSES:
            continue
        entry = {"tool": str(c.get("tool", "unknown")), "status": status}
        if isinstance(c.get("summary"), str):
            entry["summary"] = c["summary"]
        clean_checks.append(entry)
    path = audit_path(data_dir)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plugin_version": plugin_version(),
        "task": task,
        "checks": clean_checks,
    }
    if isinstance(summary, str) and summary:
        record["summary"] = summary
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        return {"ok": False, "error": f"cannot write audit log: {exc}", "path": path, "entries": 0}
    entries = 0
    try:
        with open(path, encoding="utf-8") as fh:
            entries = sum(1 for line in fh if line.strip())
    except OSError:
        pass
    return {"ok": True, "path": path, "entries": entries}


def main() -> int:  # pragma: no cover - CLI convenience
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    print(json.dumps(record_verification(args[0]), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
