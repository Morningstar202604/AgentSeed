# Contributing to AgentSeed

## Working rules for this repository

* Dependency updates: search the whole repository for every occurrence of a dependency (build files, lockfiles, CI workflows, docs) before bumping. A partial bump — declaration updated but lockfile or a pinned action left behind — is the most common cause of "works locally, CI fails". Keep lockfiles in the same commit as the declaration. Move version-coupled toolchain upgrades together in one commit.
* Refactoring: pull latest main first, work on a fresh branch, keep commits atomic with messages that state the why, and always run the full check suite before pushing (for this repo: `python -m unittest discover -s server` and `python server/guard_cli.py gate --root .`). A branch left behind main cannot be merged under the repository's branch protection.
* Merge conflicts: resolve conflicts in the working tree against the latest main; never force-push shared branches; never resolve a conflict by blindly taking either side — re-read both sides and keep both changes when they are both valid.
* Versioning: releases follow X.Y.Z starting at 0.0.0. Last digit = fixes, middle digit = feature work, first digit stays 0 until a stable release is declared. Bump the version in code, CHANGELOG.md and the tag in the same change.

Thanks for helping guard AI coding agents. Any contribution — a new
hallucination pattern, a bug report, a verified platform — makes the gate
better.

## Quick start

```bash
git clone https://github.com/Morningstar202604/AgentSeed.git
cd AgentSeed
python -m unittest discover -s server -p "test_*.py"   # no deps needed
python server/guard_cli.py gate --root .               # the CI-equivalent hard gate
```

Optional extras used by the test suite when present:
`pip install -r server/requirements.txt`

## Ground rules

- **Zero required dependencies.** The plugin must run on a bare Python 3.9+.
  Third-party libraries are welcome only behind an optional import with a
  working stdlib fallback (see `server/engine/schema.py` for the pattern).
- **Every behavior change ships with tests.** CI discovers `server/test_*.py`
  and runs the whole suite both with and without the optional dependencies
  installed; both must pass.
- **The plugin must stay self-conformant.** CI runs `guard_cli.py gate --root .`
  (conformance + undefined symbols + hallucination scan against the committed
  `baseline-scan.json`); `guard_cli.py check . --ci` is the conformance stage on
  its own. `main` is protected: a red check blocks the merge.
- **Docs may not drift from the engine.** `server/test_docs_sync.py` asserts the
  language/tool counts, repository URLs, registry identity and version strings
  in README/DESIGN against the language registry and `tools/list`. If you change
  a number in prose, run that file.
- **Adding a language = one registry entry.** A `LangSpec` must declare its own
  `extensions`; the CLI's path heuristic, tree scanning, the MCP schema `enum`
  and the prompt-pool exporter all derive from the registry, and an entry
  without suffixes fails at import rather than going unnoticed.
- **Release discipline.** A change that is not yet released gets its own
  `## [x.y.z]` section — never append entries to a version that has already been
  tagged. `CHANGELOG.md` describes what shipped, not what is planned.
- Match the existing code style (stdlib, type hints, no comments unless the
  logic genuinely needs one).

## Adding a hallucination pattern

1. Add the token to the right group in `server/engine/hallucination.py`
   (`STUB_TOKENS` / `OVERSOLD_TOKENS` / `FABRICATED_TOKENS`).
2. Add a test in `server/test_guard.py` proving it fires — and, importantly,
   a case proving legitimate usage does *not* fire.
3. Update `CHANGELOG.md`.

## Reporting a false positive

False positives are bugs. Open an issue with:

- the exact source line that was flagged,
- which tool/group/severity fired,
- why the line is legitimate.

## Reporting a verified client

Ran AgentSeed in Cursor / VS Code / Cline / anything? Open a PR updating the
Platform support table in all three READMEs (`verified` + how you configured
it). Verified rows are the single most-trusted signal for new users.

## Pull requests

- Branch from `main`, keep commits atomic.
- CI must be green (tests × OS × Python matrix, bare job, conformance gate).
- Update `CHANGELOG.md` under an appropriate heading.
