"""Per-token coverage analyzer for the hallucination word pools.

Answers "which tokens actually earn their place?" by counting, per token,
how many lines it matches across a corpus and how many of those lines NO
other token in the same group matches (its unique contribution):

    python scripts/token_coverage.py                 # analyze the repo itself
    python scripts/token_coverage.py path/to/corpus  # any directory

Dev tool only — not wired into CI. Matching mirrors
engine/hallucination.py:scan_hallucination_words (import-line skip,
dotted-path skip, allowlist prefix skip) via the same compiler.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))

import guard_cli  # noqa: E402
from engine import hallucination as hal  # noqa: E402


def _iter_corpus(root: str):
    if os.path.isfile(root):
        yield root
        return
    for path in guard_cli._iter_source_files(root):
        yield path


def analyze(corpus_root: str) -> list[dict]:
    groups = [
        ("stub_code", hal.STUB_TOKENS + hal.STUB_TOKENS_ZH),
        ("oversold", hal.OVERSOLD_TOKENS + hal.OVERSOLD_TOKENS_ZH),
        ("fabricated", hal.FABRICATED_TOKENS + hal.FABRICATED_TOKENS_ZH),
    ]
    # one compiled pattern per single token (same rules as production)
    token_res = []
    for group, tokens in groups:
        for t in tokens:
            token_res.append((group, t, hal._compile_group([t])))

    stats: dict[tuple[str, str], dict] = {
        (g, t): {"hits": 0, "unique": 0, "files": set()} for g, t, _ in token_res
    }
    for path in _iter_corpus(corpus_root):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            if hal._IMPORT_LINE_RE.match(line):
                continue
            matched_here: set[tuple[str, str]] = set()
            for group, t, rx in token_res:
                hit = False
                for m in rx.finditer(line):
                    before = line[max(0, m.start() - 1) : m.start()]
                    after = line[m.end() : m.end() + 1]
                    if before == "." or after == ".":
                        continue
                    rest = line[m.start() :]
                    if any(rest.lower().startswith(a.lower()) for a in hal.DEFAULT_ALLOWLIST):
                        continue
                    hit = True
                    break
                if hit:
                    matched_here.add((group, t))
                    stats[(group, t)]["hits"] += 1
                    stats[(group, t)]["files"].add(os.path.basename(path))
            for key in matched_here:
                others = [k for k in matched_here if k[0] == key[0] and k != key]
                if not others:
                    stats[key]["unique"] += 1
    rows = []
    for (group, t), s in stats.items():
        rows.append(
            {
                "group": group,
                "token": t,
                "hits": s["hits"],
                "unique_lines": s["unique"],
                "files": len(s["files"]),
            }
        )
    rows.sort(key=lambda r: (-r["hits"], r["group"], r["token"]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", nargs="?", default=".", help="directory or file to analyze")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    rows = analyze(args.corpus)
    dead = [r for r in rows if r["hits"] == 0]
    shadowed = [r for r in rows if r["hits"] > 0 and r["unique_lines"] == 0]
    if args.json:
        print(
            json.dumps(
                {
                    "tokens_total": len(rows),
                    "tokens_zero_hits": len(dead),
                    "tokens_no_unique_contribution": len(shadowed),
                    "rows": rows,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"{'group':<11} {'token':<18} {'hits':>6} {'unique':>7} {'files':>6}")
        for r in rows:
            print(
                f"{r['group']:<11} {r['token']:<18} {r['hits']:>6} "
                f"{r['unique_lines']:>7} {r['files']:>6}"
            )
        print(
            f"\n{len(rows)} tokens | zero-hit: {len(dead)} | "
            f"no unique contribution: {len(shadowed)}"
        )
        if dead:
            print("zero-hit tokens:", ", ".join(sorted(r["token"] for r in dead)))
        if shadowed:
            print("shadowed tokens:", ", ".join(sorted(r["token"] for r in shadowed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
