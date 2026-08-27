# AgentSeed Detection Benchmark

First quantitative detection baseline for the guard engine, measured on a
**deterministic synthetic corpus** (`scripts/bench_detection.py`, seed
`20260826`). These are synthetic-corpus figures — they quantify whether the
detectors catch the defect classes they were built for; they are **not**
real-world hallucination-rate estimates.

## Method

- Corpus: 40 clean modules (imports + functions + comprehensions) and 100
  defective modules (20 per class), one injected defect each.
- Defect classes: `undefined_call`, `del_undefined` (judged by `verify_code`
  suspects); `stub_token`, `oversold_claim`, `fabricated_token` (judged by
  `scan_hallucination` group hits).
- A clean module flagged by either detector counts as one false positive.

## Results (2026-08-27 · Python 3.13.9 · Windows / engine 0.3.1 + pyflakes)

| defect class | tp | fn | recall |
| --- | --- | --- | --- |
| undefined_call | 20 | 0 | 1.0 |
| del_undefined | 20 | 0 | 1.0 |
| stub_token | 20 | 0 | 1.0 |
| oversold_claim | 20 | 0 | 1.0 |
| fabricated_token | 20 | 0 | 1.0 |

precision=**1.0** recall=**1.0** (tp=100 fp=0 fn=0)

Reproduce:

```bash
python scripts/bench_detection.py          # table above
python scripts/bench_detection.py --json   # machine-readable
```

The suite locks this in: `test_features.TestDetectionBenchmark` fails if any
class drops below perfect on the seeded corpus.

## Honest scope

- Real-world recall will be **lower**: attribute-call hallucinations
  (`obj.missing()`), cross-file symbols, and semantically-wrong-but-runnable
  code remain documented non-goals (DESIGN §Risks).
- The corpus exercises the detectors' target failure modes only; it is an
  anti-regression floor, not a leaderboard number.
