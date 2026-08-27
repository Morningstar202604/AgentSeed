"""Export the AgentSeed prompt pool into per-client guardrail configs.

Reads ``skills/verify-before-code/references/PROMPT-POOL.md`` and renders the
anti-hallucination prompts as drop-in config files for the three main
agent-config formats, so the guardrails apply OUTSIDE plugin-aware clients
(roadmap item: "wire the PROMPT-POOL into per-client configs"). The number of
prompts is whatever the pool currently parses — it is never hardcoded here:

    --format claude   -> CLAUDE.md fragment
    --format agents   -> AGENTS.md fragment
    --format cursor   -> .cursor/rules/agentseed-guardrails.mdc

Usage:
    python scripts/export_prompt_pool.py                 # all formats -> dist/prompt-pool
    python scripts/export_prompt_pool.py --format claude --out out/
    python scripts/export_prompt_pool.py --format cursor --stdout

Deterministic output: the pool is the single source of truth; the script is
parse-only (importable: ``parse_pool`` / ``render`` for tests).
"""

from __future__ import annotations

import argparse
import os
import re
import sys

_ENTRY_RE = re.compile(
    r"\*\*([A-Za-z]+\d+)\.\s*([^*\n]+)\*\*\s*```(?:[a-zA-Z0-9_-]*)\n([\s\S]*?)```"
)

# Cursor `.mdc` globs are DERIVED from the language registry (see
# server/engine/symbols.py) so they can never drift from the set of languages
# the engine actually supports. This maps each canonical registry language to
# its source-file globs; a language registered without an entry here makes the
# export fail loudly rather than silently dropping it from the generated rules.
_LANG_GLOBS = {
    "python": "*.py",
    "typescript": "*.ts,*.tsx",
    "javascript": "*.js,*.jsx",
    "go": "*.go",
    "rust": "*.rs",
    "java": "*.java",
    "c": "*.c",
    "cpp": "*.cpp",
    "csharp": "*.cs",
    "php": "*.php",
    "ruby": "*.rb",
    "kotlin": "*.kt",
    "swift": "*.swift",
    "dart": "*.dart",
    "lua": "*.lua",
    "r": "*.r",
    "zig": "*.zig",
}


def _canonical_languages() -> tuple[str, ...]:
    """Canonical engine languages, read live from server/engine/symbols.py.

    Falls back to a manually-synced list only if the engine module cannot be
    imported; the fallback stays in sync with the registry in symbols.py.
    """
    symbols_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "server",
        "engine",
        "symbols.py",
    )
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("_agentseed_symbols", symbols_path)
        module = importlib.util.module_from_spec(spec)
        # symbols.py defines a @dataclass whose annotations dataclasses.py
        # resolves via sys.modules[cls.__module__]; register the temp module so
        # that lookup succeeds, and drop it afterwards to avoid leaking state.
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
        resolve = module.resolve_language
        supported = module.SUPPORTED_LANGUAGES
    except Exception:  # pragma: no cover - keep in sync with server/engine/symbols.py
        return (
            "python", "typescript", "javascript", "go", "rust", "java", "c",
            "cpp", "csharp", "php", "ruby", "kotlin", "swift", "dart", "lua",
            "r", "zig",
        )
    canon = {"python", "typescript", "javascript"}
    for name in supported:
        lang = resolve_language_via(resolve, name)
        if lang:
            canon.add(lang)
    return tuple(sorted(canon))


def resolve_language_via(resolve, name: str) -> str | None:
    """Canonical name for a SUPPORTED_LANGUAGES entry (or None for python/ts/js)."""
    spec = resolve(name)
    return spec.name if spec is not None else None


def _cursor_globs() -> str:
    """Comma-joined source globs covering every engine-supported language."""
    canon = _canonical_languages()
    missing = sorted(c for c in canon if c not in _LANG_GLOBS)
    if missing:
        raise ValueError(
            "no cursor glob mapping for engine language(s): "
            + ", ".join(missing)
            + " — add them to _LANG_GLOBS in scripts/export_prompt_pool.py"
        )
    head = [lang for lang in ("python", "typescript", "javascript") if lang in canon]
    rest = [lang for lang in canon if lang not in head]
    return ",".join(_LANG_GLOBS[lang] for lang in head + rest)


def parse_pool(pool_path: str) -> list[dict]:
    """Parse PROMPT-POOL.md into [{"id", "title", "body"}, ...] (order kept)."""
    with open(pool_path, encoding="utf-8") as fh:
        text = fh.read()
    return [
        {"id": m.group(1), "title": m.group(2).strip(), "body": m.group(3).strip()}
        for m in _ENTRY_RE.finditer(text)
    ]


def render(fmt: str, entries: list[dict]) -> str:
    """Render entries into one client-config file (claude | agents | cursor)."""
    sections = "\n\n".join(
        f"## {e['id']} — {e['title']}\n\n```\n{e['body']}\n```" for e in entries
    )
    if fmt == "claude":
        return (
            "# CLAUDE.md — AgentSeed guardrail prompts (exported from the prompt pool)\n\n"
            "# Copy these into your CLAUDE.md so anti-hallucination gates apply in\n"
            "# every session. Source: skills/verify-before-code/references/PROMPT-POOL.md\n\n"
            + sections
            + "\n"
        )
    if fmt == "agents":
        return (
            "# AGENTS.md — AgentSeed guardrail prompts (exported from the prompt pool)\n\n"
            "# Copy these into your AGENTS.md so every agent honors the gates.\n\n"
            + sections
            + "\n"
        )
    if fmt == "cursor":
        return (
            "---\n"
            "description: AgentSeed anti-hallucination guardrail prompts\n"
            f"globs: {_cursor_globs()}\n"
            "---\n\n"
            "# AgentSeed guardrails\n\n"
            + sections
            + "\n"
        )
    raise ValueError(f"unknown format: {fmt}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="export_prompt_pool", description=__doc__)
    ap.add_argument(
        "--format",
        choices=["claude", "agents", "cursor", "all"],
        default="all",
        help="which config file(s) to render (default: all)",
    )
    ap.add_argument(
        "--out",
        default="dist/prompt-pool",
        help="output directory (default: dist/prompt-pool)",
    )
    ap.add_argument(
        "--pool",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "skills",
            "verify-before-code",
            "references",
            "PROMPT-POOL.md",
        ),
        help="path to PROMPT-POOL.md",
    )
    ap.add_argument("--stdout", action="store_true", help="print to stdout instead of writing files")
    args = ap.parse_args(argv)

    entries = parse_pool(args.pool)
    if not entries:
        print(f"no prompts parsed from {args.pool}", file=sys.stderr)
        return 1

    formats = ["claude", "agents", "cursor"] if args.format == "all" else [args.format]
    names = {
        "claude": "CLAUDE.md",
        "agents": "AGENTS.md",
        "cursor": os.path.join(".cursor", "rules", "agentseed-guardrails.mdc"),
    }
    if args.stdout:
        print(render(formats[0], entries))
        return 0
    os.makedirs(args.out, exist_ok=True)
    for fmt in formats:
        out_path = os.path.join(args.out, names[fmt])
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(render(fmt, entries))
        print(f"wrote {out_path} ({len(entries)} prompts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
