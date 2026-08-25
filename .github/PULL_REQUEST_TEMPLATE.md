<!-- Title format: <area>: <imperative summary>  e.g. "engine: add Go lexical pass" -->

## What & why

<!-- Link the issue; one paragraph on the change and its motivation. -->

## Verification evidence (required by the SDD contract)

Paste real command output — not claims:

```text
$ cd server && python -m pytest ... -q
<output>

$ ruff check .
All checks passed!
```

- [ ] New/changed logic covered by tests in `server/test_*.py`
- [ ] `ruff check .` clean
- [ ] `python scripts/pack.py --check-only` green (manifest drift gate)
- [ ] CHANGELOG.md updated under `[Unreleased]`
- [ ] Docs updated if user-facing (README*.md / SKILL.md)

## Breaking changes?

<!-- Tool schemas, CLI flags, config keys, exit codes. -->
