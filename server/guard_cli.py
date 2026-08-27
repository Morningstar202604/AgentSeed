"""AgentSeed CLI — zero-dependency command-line entry point.

Enables CI gating for human PRs as well as agent sessions. One subcommand per
MCP tool:

    python guard_cli.py verify   SOURCE_OR_PATH [--language LANG] [--strict]
    python guard_cli.py contract SOURCE_OR_PATH --contract FILE [--language LANG]
    python guard_cli.py imports  SOURCE_OR_PATH [--known PKG]...
    python guard_cli.py scan     SOURCE_OR_PATH [--strict] [--baseline FILE]
    python guard_cli.py check    [plugin_dir] [--ci]
    python guard_cli.py gate     [--root DIR] [--baseline FILE]
    python guard_cli.py sandbox  -- COMMAND [args...]
    python guard_cli.py record   TASK [--check TOOL=STATUS]... [--note TEXT]

``SOURCE_OR_PATH`` is either inline source text or an existing file path; a
tree is only swept through ``scan --baseline DIR``. A path that does not exist
is a usage error, never silently treated as empty source.

Exit codes: 0 = pass, 1 = findings/errors, 2 = usage error (bad flags, a
directory passed where a file was expected, or a missing path).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import guard_engine as engine  # noqa: E402
from engine.symbols import SUPPORTED_LANGUAGES, language_for_file, source_extensions  # noqa: E402

# Prose/config formats worth hallucination-scanning. They belong to no language
# in the registry, so they live here; language suffixes do not.
TEXT_EXTENSIONS = (".md", ".json", ".yaml", ".yml", ".toml")

# Derived from the language registry: a language added to the engine becomes
# recognizable here (path-vs-inline heuristic + tree walking) with no edit.
SOURCE_SUFFIXES: tuple[str, ...] = tuple(source_extensions()) + TEXT_EXTENSIONS


def _usage_error(message: str) -> None:
    """Reject the invocation the same way argparse does: stderr + exit 2."""
    print(f"agentseed: {message}", file=sys.stderr)
    raise SystemExit(2)


def _looks_like_path(text: str) -> bool:
    """True when the argument was clearly meant to name a file on disk.

    Inline source is what the CLI also accepts, so the two have to be told
    apart: real code rarely looks like a bare relative path, while a typo'd
    or missing path must never be scanned as if it were source (a guardrail
    that reports ``clean`` for a file that does not exist is worse than one
    that crashes).
    """
    if "\n" in text or "\r" in text:
        return False  # multi-line: inline source
    stripped = text.strip()
    if not stripped:
        return False
    if "/" in text or "\\" in text or os.sep in text:
        return True
    if stripped.startswith((".", "~", "/")):
        return True
    return stripped.lower().endswith(SOURCE_SUFFIXES)


def _read_source(path_or_source: str) -> str:
    if os.path.isdir(path_or_source):
        _usage_error(
            f"'{path_or_source}' is a directory; pass a file path, inline source "
            f"text, or use 'scan <dir> --baseline FILE' to sweep a tree"
        )
    if os.path.isfile(path_or_source):
        with open(path_or_source, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    if _looks_like_path(path_or_source):
        _usage_error(
            f"'{path_or_source}' does not exist; pass an existing file path or "
            f"inline source text (a missing path is never scanned as empty source)"
        )
    return path_or_source


def _warn_unknown_config(config: dict) -> None:
    unknown = engine.unknown_config_keys(config)
    for key in unknown:
        print(
            f"[agentseed] WARNING: unknown config key '{key}' ignored "
            f"(known keys: {sorted(engine.KNOWN_CONFIG_KEYS)})",
            file=sys.stderr,
        )


def _resolve_language(args: argparse.Namespace) -> str:
    """Explicit ``--language`` wins; otherwise pick the language from the file
    the argument names, falling back to python for inline source text."""
    explicit = getattr(args, "language", None)
    if explicit:
        return explicit
    return language_for_file(args.source) or "python"


def cmd_verify(args: argparse.Namespace) -> int:
    config = engine.load_config(args.config)
    _warn_unknown_config(config)
    suppress = args.suppress or engine.config_str_list(config, "suppress_symbols")
    source = _read_source(args.source)
    result = engine.detect_undefined_symbols(
        source, _resolve_language(args), suppress=suppress
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("note", "").startswith("Cannot parse"):
        # syntax error is reported, not a finding — unless gating strictly
        return 1 if getattr(args, "strict", False) else 0
    return 1 if result["suspects"] else 0


def cmd_contract(args: argparse.Namespace) -> int:
    """Contract gate: exit 1 unless every `requires` symbol is defined and
    no `prohibits` token appears."""
    source = _read_source(args.source)
    result = engine.check_contract(source, args.contract, _resolve_language(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["contract_ok"] else 1


def cmd_imports(args: argparse.Namespace) -> int:
    """Slopsquatting gate: exit 1 when a top-level import is neither stdlib
    nor in the known-package set (defaults + config known_packages + --known)."""
    config = engine.load_config(getattr(args, "config", None))
    known = args.known or engine.config_str_list(config, "known_packages")
    source = _read_source(args.source)
    result = engine.check_imports(source, known_packages=known)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["imports_ok"] else 1


def _iter_source_files(root: str):
    """Deterministic walk of text sources worth scanning (skips VCS/cache)."""
    skip_dirs = {".git", ".agentseed", "__pycache__", "node_modules", ".github", ".workbuddy"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        for fn in sorted(filenames):
            if fn.lower().endswith(SOURCE_SUFFIXES):
                yield os.path.join(dirpath, fn)


def _fingerprint_counts(source: str, allowlist, severities, extra_tokens) -> dict:
    result = engine.scan_hallucination_words(
        source, allowlist, severities, extra_tokens=extra_tokens
    )
    counts: dict[str, int] = {}
    for h in result["hits"]:
        key = f"{h['group']}|{h['word']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def cmd_scan_baseline(args: argparse.Namespace) -> int:
    """Baseline mode: fail only on NEW hallucination signals vs a frozen
    fingerprint. Deliberately line-number-free so ordinary edits don't
    churn the baseline; only genuinely new occurrences block."""
    target = os.path.abspath(args.source)
    base_abs = os.path.abspath(args.baseline)
    if os.path.isdir(target):
        files = list(_iter_source_files(target))

        def rel(p: str) -> str:
            return os.path.relpath(p, target).replace(os.sep, "/")
    elif os.path.isfile(target):
        files = [target]

        def rel(p: str) -> str:
            return os.path.basename(p)
    else:
        _usage_error(
            f"'{args.source}' is neither an existing file nor a directory; "
            f"'scan --baseline' sweeps a file or a tree, not inline text"
        )
        return 2

    # never fingerprint the baseline file itself: its own content would
    # re-enter every comparison as "new" signals (self-reference recursion)
    files = [p for p in files if os.path.abspath(p) != base_abs]

    config = engine.load_config(args.config)
    _warn_unknown_config(config)
    allowlist = (
        []
        if args.strict
        else (
            args.allowlist
            or engine.config_str_list(config, "allowlist")
            or engine.DEFAULT_ALLOWLIST
        )
    )
    severities = (
        {"stub_code": "error"}
        if (args.strict and not args.stub_ok)
        else engine.config_severities(config)
    )
    extra = engine.config_extra_tokens(config)

    current: dict[str, dict] = {}
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as fh:
            counts = _fingerprint_counts(fh.read(), allowlist, severities, extra)
        if counts:
            current[rel(path)] = counts

    exists = os.path.isfile(args.baseline)
    if args.update_baseline or not exists:
        payload = {"version": 1, "files": current}
        with open(args.baseline, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        n = sum(sum(c.values()) for c in current.values())
        action = "updated" if exists else "created"
        print(f"baseline {action}: {args.baseline} ({len(current)} files, {n} hits frozen)")
        return 0

    with open(args.baseline, encoding="utf-8") as fh:
        old = json.load(fh).get("files", {})
    grew = []
    for path, counts in sorted(current.items()):
        base = old.get(path, {})
        for key, cnt in counts.items():
            if cnt > base.get(key, 0):
                grew.append((path, key, cnt - base.get(key, 0)))
    if grew:
        print(f"NEW hallucination signals vs baseline ({args.baseline}):")
        for path, key, delta in grew:
            print(f"  +{delta}  {key}  in {path}")
        return 1
    print("baseline check: no NEW hallucination signals")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    if getattr(args, "baseline", None):
        return cmd_scan_baseline(args)
    config = engine.load_config(args.config)
    _warn_unknown_config(config)
    allowlist = (
        []
        if args.strict
        else (
            args.allowlist
            or engine.config_str_list(config, "allowlist")
            or engine.DEFAULT_ALLOWLIST
        )
    )
    severities = (
        {"stub_code": "error"}
        if (args.strict and not args.stub_ok)
        else engine.config_severities(config)
    )
    source = _read_source(args.source)
    result = engine.scan_hallucination_words(
        source,
        allowlist,
        severities,
        extra_tokens=engine.config_extra_tokens(config),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["blocking"] else 0


def cmd_check(args: argparse.Namespace) -> int:
    path = os.path.abspath(args.plugin_dir or ".")
    if not os.path.isdir(path):
        print(
            json.dumps(
                {"ok": False, "errors": [f"not a directory: {path}"], "warnings": []},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    result = engine.check_plugin_conformance(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def cmd_sandbox(args: argparse.Namespace) -> int:
    config = engine.load_config()
    _warn_unknown_config(config)
    timeout = args.timeout if args.timeout is not None else engine.parse_timeout(config)
    env_mode = getattr(args, "env", None) or engine.sandbox_env_mode(config)
    result = engine.sandbox_run(
        args.command,
        timeout,
        args.cwd,
        allowed_prefixes=engine.config_str_list(config, "sandbox_allowed_prefixes"),
        env_mode=env_mode,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["timed_out"]:
        return 1
    if result["exit_code"] < 0:
        return 1  # -2 not found / -9 failed / -10 policy-blocked: never a "pass"
    return result["exit_code"]  # propagate the child's real exit code


def cmd_record(args: argparse.Namespace) -> int:
    checks = []
    for raw in args.check or []:
        tool, _, status = raw.partition("=")
        checks.append({"tool": tool or "manual", "status": status or "pass"})
    result = engine.record_verification(
        args.task,
        checks,
        summary="; ".join(args.note) if args.note else None,
        data_dir=args.data_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_gate(args: argparse.Namespace) -> int:
    """Composite CI gate — the hard layer behind the soft skill:
    1) plugin conformance (spec linter)
    2) verify_code over every Python file (any suspect or unparseable file fails)
    3) scan with baseline comparison (only NEW signals fail)
    Single exit code: 0 = all gates pass, 1 = any failure."""
    import time

    root = os.path.abspath(args.root)
    started = time.perf_counter()
    summary: dict = {"root": root, "checks": {}}
    failed = False

    # -- 1. conformance ----------------------------------------------------
    conf = engine.check_plugin_conformance(root)
    ok = bool(conf.get("ok"))
    summary["checks"]["conformance"] = {
        "status": "pass" if ok else "fail",
        "errors": conf.get("errors", []),
    }
    failed |= not ok

    # -- 2. symbols over all Python sources --------------------------------
    py_files = [p for p in _iter_source_files(root) if p.endswith(".py")]
    suspects_total: dict[str, list] = {}
    unparseable: list[str] = []
    for path in py_files:
        with open(path, encoding="utf-8", errors="replace") as fh:
            res = engine.detect_undefined_symbols(fh.read())
        if res.get("note", "").startswith("Cannot parse"):
            unparseable.append(os.path.relpath(path, root))
        if res["suspects"]:
            suspects_total[os.path.relpath(path, root)] = res["suspects"]
    symbols_ok = not suspects_total and not unparseable
    summary["checks"]["symbols"] = {
        "status": "pass" if symbols_ok else "fail",
        "files_checked": len(py_files),
        "suspects": suspects_total,
        "unparseable": unparseable,
    }
    failed |= not symbols_ok

    # -- 3. hallucination scan vs baseline ---------------------------------
    baseline = args.baseline
    if baseline is None and not args.no_baseline:
        candidate = os.path.join(root, "baseline-scan.json")
        baseline = candidate if os.path.isfile(candidate) else None
    if args.no_baseline:
        scan_status = "skipped"
    elif baseline is None:
        scan_status = "fail"
        summary["checks"]["scan"] = {
            "status": scan_status,
            "error": "no baseline provided (--baseline PATH or <root>/baseline-scan.json)",
        }
        failed = True
    else:
        ns = argparse.Namespace(
            source=root,
            config=args.config,
            strict=False,
            stub_ok=False,
            allowlist=None,
            baseline=baseline,
            update_baseline=False,
        )
        rc = cmd_scan_baseline(ns)
        scan_status = "pass" if rc == 0 else "fail"
        summary["checks"]["scan"] = {"status": scan_status, "baseline": os.path.abspath(baseline)}
        failed |= rc != 0

    summary["verdict"] = "fail" if failed else "pass"
    summary["elapsed_s"] = round(time.perf_counter() - started, 2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentseed", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser("verify", help="flag possibly-hallucinated symbols")
    p_verify.add_argument("source", help="source code or a file path")
    p_verify.add_argument(
        "--language",
        default=None,
        choices=list(SUPPORTED_LANGUAGES),
        help="default: inferred from the file extension, else python",
    )
    p_verify.add_argument(
        "--strict", action="store_true", help="exit 1 when the source cannot be parsed at all"
    )
    p_verify.add_argument(
        "--suppress",
        action="append",
        metavar="NAME",
        help="symbol name never to flag (repeatable; default: config suppress_symbols)",
    )
    p_verify.add_argument("--config", help="explicit config file path")
    p_verify.set_defaults(func=cmd_verify)

    p_contract = sub.add_parser(
        "contract", help="verify source against a declared contract (requires/prohibits)"
    )
    p_contract.add_argument("source", help="source code or a file path")
    p_contract.add_argument(
        "--contract",
        required=True,
        help='JSON: {"requires": [...], "prohibits": [...]}',
    )
    p_contract.add_argument(
        "--language",
        default=None,
        choices=list(SUPPORTED_LANGUAGES),
        help="default: inferred from the file extension, else python",
    )
    p_contract.set_defaults(func=cmd_contract)

    p_imports = sub.add_parser(
        "imports", help="flag imports not in stdlib / known packages (slopsquatting)"
    )
    p_imports.add_argument("source", help="source code or a file path")
    p_imports.add_argument(
        "--known",
        action="append",
        metavar="PKG",
        help="extra known package (repeatable; default: config known_packages)",
    )
    p_imports.add_argument("--config", help="explicit config file path")
    p_imports.set_defaults(func=cmd_imports)

    p_scan = sub.add_parser("scan", help="scan for hallucination signals")
    p_scan.add_argument("source", help="source text or a file path")
    p_scan.add_argument("--allowlist", action="append", help="exclusion prefix (repeatable)")
    p_scan.add_argument(
        "--strict", action="store_true", help="disable default exclusions; stub hits become errors"
    )
    p_scan.add_argument(
        "--stub-ok", action="store_true", help="with --strict: keep stub_code at warning severity"
    )
    p_scan.add_argument("--config", help="explicit config file path")
    p_scan.add_argument(
        "--baseline",
        metavar="FILE",
        help="compare against a frozen hit fingerprint; exit 1 "
        "only on NEW signals (source may be a directory)",
    )
    p_scan.add_argument(
        "--update-baseline",
        action="store_true",
        help="(with --baseline) write the current fingerprint and exit 0",
    )
    p_scan.set_defaults(func=cmd_scan)

    p_check = sub.add_parser("check", help="validate a plugin directory")
    p_check.add_argument("plugin_dir", nargs="?", default=".")
    p_check.add_argument(
        "--ci", action="store_true", help="(default in CI use) exit 1 on any conformance error"
    )
    p_check.set_defaults(func=cmd_check)

    p_gate = sub.add_parser("gate", help="composite CI gate: conformance + symbols + baseline scan")
    p_gate.add_argument("--root", default=".", help="plugin/repo root to gate")
    p_gate.add_argument(
        "--baseline", help="scan baseline JSON (default: <root>/baseline-scan.json when present)"
    )
    p_gate.add_argument("--no-baseline", action="store_true", help="skip the scan stage")
    p_gate.add_argument("--config", help="explicit config file path")
    p_gate.set_defaults(func=cmd_gate)

    p_sandbox = sub.add_parser("sandbox", help="run a command with timeout + captured output")
    p_sandbox.add_argument(
        "command", nargs="+", help="command to run; use '--' before flags of the child"
    )
    p_sandbox.add_argument("--timeout", type=int, default=None, help="seconds (1-120)")
    p_sandbox.add_argument("--cwd", help="working directory")
    p_sandbox.add_argument(
        "--env",
        choices=engine.SANDBOX_ENV_MODES,
        default=None,
        help="environment policy (default: config sandbox_env / inherit)",
    )
    p_sandbox.set_defaults(func=cmd_sandbox)

    p_record = sub.add_parser("record", help="append a verification audit entry")
    p_record.add_argument("task", help="what was being verified")
    p_record.add_argument(
        "--check",
        action="append",
        default=[],
        metavar="TOOL=STATUS",
        help="e.g. sandbox_run=pass (repeatable; default pass)",
    )
    p_record.add_argument("--note", action="append", help="free-text note (repeatable)")
    p_record.add_argument("--data-dir", help="override PLUGIN_DATA for the log")
    p_record.set_defaults(func=cmd_record)

    args = parser.parse_args(argv)
    if args.cmd == "sandbox" and args.command and args.command[0] == "--":
        args.command = args.command[1:]
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
