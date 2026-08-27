"""AgentSeed client-enforcement hook for Claude Code.

The skill teaches the workflow; hooks enforce it at the client boundary.
Registered as a Claude Code hook, every Write/Edit/MultiEdit tool call is
scanned here — PreToolUse inspects the incoming ``content``/``new_string``
BEFORE anything lands on disk, PostToolUse re-checks the saved file.

Modes:
  hook mode (default)  one event JSON on stdin -> JSON verdict on stdout.
                       Exit codes follow the Claude Code hook contract:
                       0 = pass / skipped / warning-only,
                       2 = blocking findings (stderr carries the reason).
  --file PATH          scan one file directly instead of reading stdin.
  register --client claude [--settings PATH]
                       merge this hook into Claude settings.json (idempotent).
  register --client cursor [--settings PATH]
                       merge into Cursor hooks.json (afterFileEdit + preToolUse,
                       idempotent; schema per cursor.com/docs/agent/hooks).
  register --client opencode [--settings DEST]
                       install plugin/opencode/agentseed-guard.js into
                       ~/.config/opencode/plugin/ (or DEST).

Failure policy (honest scope): infrastructure problems — malformed stdin,
unreadable files, unrecognized tool shapes — never block work (skipped,
exit 0). Only positive scan findings block. Zero dependencies: stdlib plus
the local guard_engine package.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

import guard_engine as engine

SCAN_SUFFIXES = (
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".md",
    ".json",
    ".yaml",
    ".yml",
)

LANG_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}

MATCHER = "Write|Edit|MultiEdit"
HOOK_EVENTS = ("PreToolUse", "PostToolUse")

# Cursor marks its payloads with these top-level fields (common schema,
# cursor.com/docs/agent/hooks); its afterFileEdit event puts file_path at
# the top level and carries edits as a sibling list.
CURSOR_MARKERS = ("cursor_version", "workspace_roots")
CURSOR_EDIT_EVENTS = ("afterFileEdit", "afterTabFileEdit")


def _detect_protocol(event: dict) -> str:
    if any(k in event for k in CURSOR_MARKERS):
        return "cursor"
    if event.get("hook_event_name") in CURSOR_EDIT_EVENTS:
        return "cursor"
    return "claude"


def _inline_content(tool_input: dict) -> str | None:
    """New text a PreToolUse event would write, from documented fields only:
    Write.content, Edit.new_string, MultiEdit.edits[].new_string."""
    parts: list[str] = []
    for key in ("content", "new_string"):
        val = tool_input.get(key)
        if isinstance(val, str):
            parts.append(val)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for e in edits:
            if isinstance(e, dict) and isinstance(e.get("new_string"), str):
                parts.append(e["new_string"])
    if parts:
        return "\n".join(parts)
    return None


def _extract_target(event: dict) -> tuple[str | None, str | None]:
    """Return (file_path_or_None, inline_text_or_None) for an event."""
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    path = tool_input.get("file_path")
    if not isinstance(path, str) or not path:
        # Cursor afterFileEdit: {file_path, edits[]} at the top level
        path = event.get("file_path")
    if not isinstance(path, str) or not path:
        path = None
    inline = _inline_content(tool_input)
    if inline is None:
        edits = event.get("edits")
        if isinstance(edits, list):
            parts = [
                e["new_string"]
                for e in edits
                if isinstance(e, dict) and isinstance(e.get("new_string"), str)
            ]
            inline = "\n".join(parts) if parts else None
    return path, inline


def _load_file(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def scan_source(text: str, label: str, config: dict) -> dict:
    """Run the two detection engines over one source text."""
    allowlist = engine.config_str_list(config, "allowlist") or engine.DEFAULT_ALLOWLIST
    severities = engine.config_severities(config)
    scan = engine.scan_hallucination_words(
        text, allowlist, severities, extra_tokens=engine.config_extra_tokens(config)
    )
    suffix = os.path.splitext(label)[1].lower()
    suspects: list[str] = []
    lang = LANG_BY_SUFFIX.get(suffix)
    if lang:
        res = engine.detect_undefined_symbols(
            text,
            lang,
            suppress=engine.config_str_list(config, "suppress_symbols"),
        )
        suspects = list(res.get("suspects", []))
    hits = [
        {k: h[k] for k in ("word", "group", "line", "severity") if k in h}
        for h in scan.get("hits", [])
    ]
    blocking = bool(scan.get("blocking")) or bool(suspects)
    return {"suspects": suspects, "hits": hits, "blocking": blocking}


def run_hook(event: dict, config_path: str | None = None) -> tuple[dict, int]:
    """Evaluate one hook event; returns (verdict, exit_code)."""
    config = engine.load_config(config_path)
    verdict: dict = {
        "event": event.get("hook_event_name"),
        "tool": event.get("tool_name"),
        "file": None,
        "protocol": _detect_protocol(event),
        "status": "pass",
        "suspects": [],
        "hits": [],
        "blocking": False,
    }
    path, inline = _extract_target(event)
    verdict["file"] = path
    if path is None and inline is None:
        verdict["status"] = "skipped"
        verdict["reason"] = "no file_path and no inline content in tool_input"
        return verdict, 0
    target = path or "<inline>"
    if path is not None and os.path.splitext(path)[1].lower() not in SCAN_SUFFIXES:
        verdict["status"] = "skipped"
        verdict["reason"] = f"extension not scannable: {os.path.splitext(path)[1] or '<none>'}"
        return verdict, 0
    try:
        if inline is not None:
            text = inline
        elif isinstance(path, str):
            text = _load_file(path)
        else:
            verdict["status"] = "skipped"
            verdict["reason"] = "nothing to scan"
            return verdict, 0
    except OSError as exc:
        verdict["status"] = "skipped"
        verdict["reason"] = f"cannot read target: {exc}"
        return verdict, 0
    findings = scan_source(text, target, config)
    verdict.update(findings)
    if not findings["blocking"]:
        return verdict, 0
    verdict["status"] = "blocked"
    reasons = []
    if findings["suspects"]:
        reasons.append("possibly-hallucinated symbol(s): " + ", ".join(findings["suspects"]))
    for h in findings["hits"]:
        reasons.append(
            f"{h.get('severity', '?')} {h.get('group', '?')} '{h.get('word')}' "
            f"(line {h.get('line', '?')})"
        )
    message = f"[agentseed] blocked edit to {target}: fix these before proceeding — " + "; ".join(
        reasons
    )
    verdict["reason"] = message
    try:
        engine.record_verification(
            f"hook:{event.get('tool_name', '?')}:{os.path.basename(target)}",
            [{"tool": "guard_hook", "status": "fail"}],
            summary=message,
        )
    except Exception:
        pass  # audit trail is best-effort; enforcement never depends on it
    return verdict, 2


def _is_agentseed_entry(entry: dict) -> bool:
    return "guard_hook.py" in str(entry.get("command", ""))


def _clean_groups(groups: list, command: str) -> list:
    """Drop every previous agentseed entry so re-registration is idempotent."""
    kept: list = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            continue
        hooks = [h for h in group["hooks"] if not (isinstance(h, dict) and _is_agentseed_entry(h))]
        if hooks:
            group["hooks"] = hooks
            kept.append(group)
    kept.append({"matcher": MATCHER, "hooks": [{"type": "command", "command": command}]})
    return kept


def _write_json_config(path: str, data: dict) -> None:
    """Persist a client config atomically, keeping one `.bak` of the previous
    contents.

    The registration path used to `open(path, "w")` the user's own
    `settings.json` / `hooks.json` directly: that truncates the file before a
    single byte is written, so an interrupt or a full disk leaves the client
    with a corrupt config and no way back. Writing a sibling temp file and
    `os.replace`-ing it is atomic on every supported platform.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            if fh.read() != payload:
                shutil.copyfile(path, path + ".bak")
    tmp = path + f".agentseed-tmp-{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except OSError:
        if os.path.isfile(tmp):
            os.remove(tmp)
        raise


CURSOR_HOOK_EVENTS = ("preToolUse", "afterFileEdit")


def _register_cursor(command: str, path: str) -> int:
    data: dict = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            print(json.dumps({"ok": False, "error": f"cannot parse {path}: {exc}"}, indent=2))
            return 1
    if not isinstance(data, dict):
        data = {}
    data["version"] = 1
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks
    for ev in CURSOR_HOOK_EVENTS:  # Cursor's own event names (docs: agent/hooks)
        groups = hooks.get(ev)
        if not isinstance(groups, list):
            groups = []
        hooks[ev] = _clean_groups(groups, command)
    try:
        _write_json_config(path, data)
    except OSError as exc:
        print(json.dumps({"ok": False, "error": f"cannot write {path}: {exc}"}, indent=2))
        return 1
    print(
        json.dumps({"ok": True, "registered": list(CURSOR_HOOK_EVENTS), "settings": path}, indent=2)
    )
    return 0


def _opencode_plugin_src() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "plugin",
        "opencode",
        "agentseed-guard.js",
    )


def _register_opencode(dest: str) -> int:
    src = _opencode_plugin_src()
    if not os.path.isfile(src):
        print(json.dumps({"ok": False, "error": f"plugin file missing: {src}"}, indent=2))
        return 1
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
    except OSError as exc:
        print(json.dumps({"ok": False, "error": f"cannot install plugin: {exc}"}, indent=2))
        return 1
    print(json.dumps({"ok": True, "registered": ["tool.execute.before"], "plugin": dest}, indent=2))
    return 0


def cmd_register(client: str, settings_path: str | None = None) -> int:
    command = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
    if client == "cursor":
        path = settings_path or os.path.join(os.path.expanduser("~"), ".cursor", "hooks.json")
        return _register_cursor(command, path)
    if client == "opencode":
        dest = settings_path or os.path.join(
            os.path.expanduser("~"), ".config", "opencode", "plugin", "agentseed-guard.js"
        )
        return _register_opencode(dest)
    path = settings_path or os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    data: dict = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            print(json.dumps({"ok": False, "error": f"cannot parse {path}: {exc}"}, indent=2))
            return 1
    if not isinstance(data, dict):
        data = {}
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks
    for ev in HOOK_EVENTS:
        groups = hooks.get(ev)
        if not isinstance(groups, list):
            groups = []
        hooks[ev] = _clean_groups(groups, command)
    try:
        _write_json_config(path, data)
    except OSError as exc:
        print(json.dumps({"ok": False, "error": f"cannot write {path}: {exc}"}, indent=2))
        return 1
    print(json.dumps({"ok": True, "registered": list(HOOK_EVENTS), "settings": path}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv and argv[0] == "register":
            parser = argparse.ArgumentParser(prog="agentseed-hook register")
            parser.add_argument(
                "--client", default="claude", choices=["claude", "opencode", "cursor"]
            )
            parser.add_argument(
                "--settings",
                help="explicit target path (claude/cursor settings or hooks json; "
                "opencode destination plugin file)",
            )
            ns = parser.parse_args(argv[1:])
            return cmd_register(ns.client, ns.settings)
        parser = argparse.ArgumentParser(prog="agentseed-hook", description=__doc__)
        parser.add_argument("--file", help="scan this file directly (skip stdin)")
        parser.add_argument("--config", help="explicit agentseed config path")
        ns = parser.parse_args(argv)
        if ns.file:
            event = {
                "hook_event_name": "ManualScan",
                "tool_name": "manual",
                "tool_input": {"file_path": ns.file},
            }
        else:
            raw = sys.stdin.buffer.read().decode("utf-8", "replace")
            try:
                event = json.loads(raw) if raw.strip() else {}
            except ValueError:
                print(
                    json.dumps({"status": "skipped", "reason": "stdin is not valid JSON"}, indent=2)
                )
                return 0
        verdict, code = run_hook(event, ns.config)
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
        if code == 2:
            reason = verdict.get("reason", "blocked by agentseed")
            # exit 2 blocks in BOTH clients; Claude Code feeds stderr back to the
            # model, while Cursor's documented deny flow reads agent_message
            # from stdout — emit both so each client gets its channel
            if verdict.get("protocol") == "cursor":
                print(
                    json.dumps(
                        {
                            "continue": True,
                            "permission": "deny",
                            "user_message": reason,
                            "agent_message": reason,
                        },
                        ensure_ascii=False,
                    )
                )
            print(reason, file=sys.stderr)
        return code
    except Exception as exc:  # fail-open: broken tooling must not block editors
        print(
            json.dumps({"status": "skipped", "reason": f"internal error: {exc!r}"}, indent=2),
            file=sys.stdout,
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
