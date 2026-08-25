"""AgentSeed deterministic execution channel.

Runs a command (no shell) in a subprocess with timeout and captured output.
Turns "tests pass" into an observed fact.
"""

from __future__ import annotations

import os
import subprocess


def _decode(raw) -> str:
    return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else (raw or "")


def _prefix_allowed(exe: str, prefixes: list[str]) -> bool:
    """Pure check (never executes): basename or path-prefix match."""
    base = os.path.basename(exe).lower()
    return any(
        base == p.lower() or base == f"{p.lower()}.exe" or exe.startswith(p)
        for p in prefixes
        if isinstance(p, str)
    )


def _run_command(command: list[str], timeout: int, cwd: str | None, on_proc=None) -> dict:
    """Spawn + wait + capture. Shared by sync and async callers.

    ``on_proc`` (optional callable taking the Popen) lets callers register the
    live process for cancellation. stdin is DEVNULL: sandbox commands never read
    interactive input, and inheriting a piped stdin can deadlock children at
    startup on Windows (observed with MCP stdio servers).
    """
    try:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
    except FileNotFoundError as exc:
        return {
            "exit_code": -2,
            "stdout": "",
            "stderr": f"command not found: {exc}",
            "timed_out": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {"exit_code": -9, "stdout": "", "stderr": f"run failed: {exc}", "timed_out": False}
    if callable(on_proc):
        on_proc(proc)
    try:
        out, errb = proc.communicate(timeout=max(1, min(int(timeout), 120)))
        return {
            "exit_code": proc.returncode,
            "stdout": _decode(out)[-8000:],
            "stderr": _decode(errb)[-4000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        proc.kill()
        out, errb = proc.communicate()
        return {
            "exit_code": -1,
            "stdout": _decode(out)[-8000:],
            "stderr": _decode(errb)[-4000:],
            "timed_out": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {"exit_code": -9, "stdout": "", "stderr": f"run failed: {exc}", "timed_out": False}


def sandbox_run(
    command: list[str],
    timeout: int = 30,
    cwd: str | None = None,
    allowed_prefixes: list[str] | None = None,
    on_proc=None,
) -> dict:
    """Run a command as a subprocess (no shell) with a timeout.

    Deterministic verification channel: turns "the test passes" into an
    observed fact (exit code + output). No shell means no injection via args;
    output is truncated to keep the tool response bounded.

    ``allowed_prefixes`` (config: ``sandbox_allowed_prefixes``): when a
    non-empty list, only commands whose first argument matches an entry —
    by basename or path prefix — are executed; anything else is refused
    with exit code -10 WITHOUT running. None/empty = unrestricted.

    ``on_proc`` (advanced): invoked with the live Popen so async callers can
    register it for cancellation.

    Returns:
        {"exit_code": int, "stdout": str, "stderr": str, "timed_out": bool}
    """
    if not isinstance(command, list) or not command:
        return {
            "exit_code": -3,
            "stdout": "",
            "stderr": "command must be a non-empty list",
            "timed_out": False,
        }
    if allowed_prefixes and not _prefix_allowed(command[0], allowed_prefixes):
        return {
            "exit_code": -10,
            "stdout": "",
            "stderr": (
                f"blocked: '{command[0]}' is not in sandbox_allowed_prefixes {allowed_prefixes}"
            ),
            "timed_out": False,
        }
    return _run_command(command, timeout, cwd, on_proc=on_proc)
