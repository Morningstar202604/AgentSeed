"""AgentSeed evidence receipts — machine-checkable completion records.

A receipt freezes WHAT was verified and the state of the verified files at
verification time: every check (tool + status + summary), every file with its
SHA256 and size, plus the agentseed/python/platform versions. The receipt
file itself is hashed, and one line linking to it is appended to the JSONL
audit log — so a completion claim can cite a self-verifying artifact instead
of prose. "Done" becomes a receipt, not a statement.

Zero dependencies; stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone

from .audit import VALID_STATUSES, record_verification
from .version import plugin_version

RECEIPT_SCHEMA = "agentseed.receipt.v1"


def _sha256_file(path: str) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _clean_checks(checks: list | None) -> list[dict]:
    out: list[dict] = []
    for c in checks if isinstance(checks, list) else []:
        if not isinstance(c, dict):
            continue
        status = c.get("status")
        if status not in VALID_STATUSES:
            continue
        entry = {"tool": str(c.get("tool", "unknown")), "status": status}
        if isinstance(c.get("summary"), str):
            entry["summary"] = c["summary"]
        out.append(entry)
    return out


def build_receipt(
    task: str,
    checks: list | None = None,
    files: list | None = None,
    summary: str | None = None,
    data_dir: str | None = None,
) -> dict:
    """Build, persist, and audit-link one evidence receipt.

    ``files``: existing paths are hashed (sha256 + size) into the receipt. A
    missing path fails the whole receipt loudly — silently omitting a named
    file would be the exact "reports clean for a file it never opened"
    failure this project exists to prevent.

    Returns {"ok", "path", "digest", "receipt"} on success; the digest is
    the SHA256 of the receipt file itself, so any later edit to the receipt
    is detectable by re-hashing.
    """
    if not isinstance(task, str) or not task.strip():
        return {"ok": False, "error": "task must be a non-empty string", "path": "", "digest": ""}
    file_entries: list[dict] = []
    missing: list[str] = []
    for raw in files if isinstance(files, list) else []:
        if not isinstance(raw, str) or not raw.strip():
            continue
        full = os.path.abspath(os.path.expanduser(raw))
        if not os.path.isfile(full):
            missing.append(raw)
            continue
        digest, size = _sha256_file(full)
        file_entries.append({"path": full, "bytes": size, "sha256": digest})
    if missing:
        return {
            "ok": False,
            "error": "files not found: " + ", ".join(missing),
            "path": "",
            "digest": "",
        }
    base = data_dir or os.environ.get("PLUGIN_DATA") or os.path.join(os.getcwd(), ".agentseed")
    receipts_dir = os.path.join(base, "receipts")
    try:
        os.makedirs(receipts_dir, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "error": f"cannot create receipts dir: {exc}", "path": "", "digest": ""}
    now = datetime.now(timezone.utc)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "ts": now.isoformat(timespec="seconds"),
        "plugin_version": plugin_version(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "task": task,
        "checks": _clean_checks(checks),
        "files": file_entries,
    }
    if isinstance(summary, str) and summary:
        receipt["summary"] = summary
    # unique name even when two receipts land in the same second
    stamp = now.strftime("%Y%m%dT%H%M%S")
    path = os.path.join(receipts_dir, f"{stamp}.json")
    n = 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(receipts_dir, f"{stamp}-{n}.json")
    payload = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        # newline="" keeps the digest honest on Windows: text-mode translation
        # would write \r\n and the self-hash would no longer match the bytes
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(payload)
    except OSError as exc:
        return {"ok": False, "error": f"cannot write receipt: {exc}", "path": path, "digest": ""}
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    record_verification(
        f"receipt:{task}",
        _clean_checks(checks),
        summary=f"receipt {os.path.basename(path)} sha256 {digest}",
        data_dir=data_dir,
    )
    return {"ok": True, "path": path, "digest": digest, "receipt": receipt}
