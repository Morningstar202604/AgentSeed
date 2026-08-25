"""AgentSeed detection benchmark — measurable hallucination-detection rates.

Builds a deterministic synthetic corpus (seeded), injects one known defect
per defective sample across five defect classes, runs the engine, and
reports per-class recall plus overall precision/recall:

    python scripts/bench_detection.py            # human-readable table
    python scripts/bench_detection.py --json     # machine-readable
    python scripts/bench_detection.py -n 50 -m 80

This is the project's first quantitative detection baseline; the numbers are
synthetic-corpus figures, NOT real-world estimates (see docs/BENCHMARK.md).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))

import guard_engine as engine  # noqa: E402

# ---------------------------------------------------------------------------
# Corpus construction (deterministic under a fixed seed)
# ---------------------------------------------------------------------------

_CLEAN_TEMPLATE = """\
import math
import os


def compute_{i}(values):
    total = sum(values)
    scaled = [v * {k} for v in values]
    return {{
        "total": total,
        "peak": max(values) if values else 0,
        "scaled": scaled,
        "root": math.sqrt(total),
    }}


if __name__ == "__main__":
    data = list(range({k}))
    print(compute_{i}(data))
    print(os.getcwd()[:3])
"""

# kind "code" -> judged by verify_code suspects; "scan:<group>" -> by scan hits.
_DEFECTS: dict[str, str] = {
    "undefined_call": "code",
    "del_undefined": "code",
    "stub_token": "scan:stub_code",
    "oversold_claim": "scan:oversold",
    "fabricated_token": "scan:fabricated",
}

_INJECT = {
    "undefined_call": "\n\ndef trigger_{i}():\n    return phantom_helper_{i}(7)\n",
    "del_undefined": "\n\ndef cleanup_{i}():\n    del ghost_state_{i}\n",
    "stub_token": "\n\n# TODO: placeholder implementation for step {i}\n",
    "oversold_claim": (
        "\n\ndef certify_{i}():\n"
        '    """All tests pass, guaranteed. Production ready."""\n'
        "    return True\n"
    ),
    "fabricated_token": ("\n\n# The following numbers are simulated and invented for demo {i}.\n"),
}


def build_corpus(n_per_class: int, n_clean: int, seed: int = 20260826) -> list[dict]:
    rng = random.Random(seed)
    samples: list[dict] = []
    for i in range(n_clean):
        samples.append(
            {
                "name": f"clean_{i:03d}",
                "source": _CLEAN_TEMPLATE.format(i=i, k=rng.randint(2, 9)),
                "defects": [],
            }
        )
    for cls, template in _INJECT.items():
        for i in range(n_per_class):
            samples.append(
                {
                    "name": f"{cls}_{i:03d}",
                    "source": _CLEAN_TEMPLATE.format(i=100 + i, k=rng.randint(2, 9))
                    + template.format(i=i),
                    "defects": [cls],
                }
            )
    return samples


def run_engine(sample: dict) -> dict:
    verified = engine.detect_undefined_symbols(sample["source"])
    scanned = engine.scan_hallucination_words(sample["source"])
    return {
        "code_flagged": bool(verified["suspects"]),
        "scan_groups": {h["group"] for h in scanned["hits"]},
        "blocking": scanned["blocking"],
    }


def evaluate(samples: list[dict]) -> dict:
    per_class = {cls: {"tp": 0, "fn": 0} for cls in _DEFECTS}
    tp = fp = fn = 0
    for s in samples:
        observed = run_engine(s)
        for cls in s["defects"]:
            kind = _DEFECTS[cls]
            if kind == "code":
                detected = observed["code_flagged"]
            else:
                detected = kind.split(":", 1)[1] in observed["scan_groups"]
            if detected:
                per_class[cls]["tp"] += 1
                tp += 1
            else:
                per_class[cls]["fn"] += 1
                fn += 1
        if not s["defects"] and (observed["code_flagged"] or observed["blocking"]):
            fp += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    out = {
        "totals": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        },
        "per_class": {},
    }
    for cls, c in per_class.items():
        denom = c["tp"] + c["fn"]
        out["per_class"][cls] = {
            "tp": c["tp"],
            "fn": c["fn"],
            "recall": round(c["tp"] / denom, 4) if denom else None,
        }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", type=int, default=20, help="defective samples per class")
    ap.add_argument("-m", type=int, default=40, help="clean samples")
    ap.add_argument("--seed", type=int, default=20260826)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args(argv)

    report = evaluate(build_corpus(args.n, args.m, args.seed))
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    t = report["totals"]
    print("AgentSeed detection benchmark (synthetic corpus)")
    print(
        f"samples: {args.n * len(_DEFECTS)} defective ({args.n}/class) + "
        f"{args.m} clean, seed={args.seed}"
    )
    print()
    print("| defect class | tp | fn | recall |")
    print("| --- | --- | --- | --- |")
    for cls, c in report["per_class"].items():
        print(f"| {cls} | {c['tp']} | {c['fn']} | {c['recall']} |")
    print()
    print(
        f"precision={t['precision']}  recall={t['recall']}  "
        f"(tp={t['tp']} fp={t['fp']} fn={t['fn']})"
    )
    print("NOTE: synthetic-corpus figures; real-world rates will differ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
