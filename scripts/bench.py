"""AgentSeed performance baseline.

Generates a deterministic ~``--mb`` Python source, then times the two hot
engines (AST symbol analysis + hallucination scan). Use ``--mb`` to scale the
corpus; the default (1 MB) is what CHANGELOG cites as the 2.3 s baseline.

    python scripts/bench.py                 # ~1 MB
    python scripts/bench.py --mb 5.0        # ~5 MB stress run

Testsuite integration: ``server/test_guard.TestPerformanceBaseline`` runs the
same measurement on a ~0.5 MB corpus and asserts ``elapsed < 10 s`` so a
pathological slowdown cannot ship silently.
"""

from __future__ import annotations

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "server"))

import guard_engine as engine  # noqa: E402


def make_source(target_mb: float = 1.0) -> str:
    """Deterministic synthetic module of roughly target_mb megabytes."""
    block = (
        "def handler_%d(request, context):\n"
        "    payload = request.get('body')\n"
        "    if not payload:\n"
        "        return None\n"
        "    result = transform(payload)\n"
        "    return finalize(result, context)\n\n"
    )
    unit = len(block.encode("utf-8")) % 100 + 100  # ~200 bytes per fn
    count = int(target_mb * 1024 * 1024 / unit)
    return "".join(block % i for i in range(count)) + "\ntransform(1)\n"


def main(argv: list[str]) -> int:
    mb = 1.0
    if "--mb" in argv:
        mb = float(argv[argv.index("--mb") + 1])
    src = make_source(mb)
    size_mb = len(src.encode("utf-8")) / 1024 / 1024

    t0 = time.perf_counter()
    sym = engine.detect_undefined_symbols(src)
    t1 = time.perf_counter()
    scan = engine.scan_hallucination_words(src)
    t2 = time.perf_counter()

    print(f"source: {size_mb:.2f} MB | functions: {src.count('def ')}")
    print(f"verify_code : {(t1 - t0) * 1000:8.1f} ms | suspects={len(sym['suspects'])}")
    print(f"scan        : {(t2 - t1) * 1000:8.1f} ms | hits={len(scan['hits'])}")
    print(f"total       : {(t2 - t0):.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
