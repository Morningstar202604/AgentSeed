"""Export the AgentSeed prompt pool into per-client guardrail configs.

Reads ``skills/verify-before-code/references/PROMPT-POOL.md`` and renders the
same 23 anti-hallucination prompts as drop-in config files for the three
main agent-config formats, so the guardrails apply OUTSIDE plugin-aware
clients (roadmap item: "wire the PROMPT-POOL into per-client configs"):

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
            "globs: *.py,*.ts,*.tsx,*.js,*.jsx,*.go,*.rs,*.java,*.c,*.cpp,*.cs,*.php,*.rb,*.kt,*.swift\n"
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
