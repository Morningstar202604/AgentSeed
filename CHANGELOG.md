# Changelog

All notable changes to AgentSeed are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com); versioning follows [SemVer](https://semver.org).

## [0.1.1] — 2026-08-25

### Fixed
- **Documentation drift**: READMEs (en/zh/ja) and DESIGN.zh now state **six** MCP tools — the previously-undocumented `record_verification` audit tool was shipped but never counted. `guard_engine.py` is no longer described as running "conformance + demos"; it now actually runs a dependency-free self-check (`python server/guard_engine.py`) exercising `verify_code` + `scan_hallucination`.
- **Test hygiene**: eliminated `ResourceWarning` leaks in `test_server.py` / `test_features.py` — the MCP-server subprocess and its stdio pipes are now reaped and closed in teardown, so the suite runs clean even under `-W error::ResourceWarning`.

### Added
- **P0 infrastructure**: GitHub Actions CI (3 OS × Python 3.9–3.13 matrix with coverage, bare-env stdlib-only degradation job, ruff lint job, manifest-drift gate) and tag-triggered Release workflow (pack.py build → gh release upload → conditional npm publish). Community files: SECURITY.md (threat model incl. sandbox_run), bug/feature issue templates, PR template with mandatory verification evidence.
- **`record_verification` audit tool** (MCP + `guard_cli.py record`): appends JSONL entries to `${PLUGIN_DATA}/verification-log.jsonl`, giving the SDD contract's "completion report with evidence" a persistent trail. Exposed via MCP tools/list and protocol-tested.
- **Chinese/CJK hallucination tokens** in all three groups (占位/待实现/保证通过/万无一失/虚构…), matched as substrings since `\b` never fires between CJK chars; `extra_tokens` config key extends the pool at runtime per group.
- **`verify_code` line numbers**: new `suspects_detail: [{name, line}]` alongside the backward-compatible `suspects`.
- **`suppress_symbols` config / `--suppress` CLI flag**: exclude known false-positive symbol names from `verify_code`; suppressed names stay visible in the `suppressed` field.
- **`sandbox_allowed_prefixes` config key**: optional executable allowlist enforced engine-side AND in the async server path BEFORE spawning — non-matching commands are refused with exit code -10 and never executed.
- **Unknown-config-key warnings** on stderr for both the MCP server and the CLI (typo'd keys can no longer silently no-op).
- **Performance baseline** (`scripts/bench.py` + 1 MB <30 s regression gate): measured ~2.3 s total for verify+scan on a synthetic megabyte module.
- **Example fixtures** (`examples/plugins/good-plugin|broken-plugin`) exercised by tests as check_plugin conformance samples.
- **Hardened Dockerfile**: runs as unprivileged user `seed` (uid 10001) with an import-based HEALTHCHECK.
- READMEs (en/zh/ja): honest language-coverage table, full configuration reference, explicit sandbox_run security warning.

### Changed
- **De-duplicated the sandbox execution core** (reduces reinventing the wheel): the entire spawn→communicate→timeout→error→truncate logic lived in two places (`engine.sandbox_run` and the async `_run_sandbox_async` worker), which is also how the Windows stdin deadlock shipped silently in one path only. It now lives once in `engine._run_command`; both callers delegate, and the async path registers the live process via a new `on_proc` callback for cancellation. The duplicate `_plugin_version()` (guard_server vs `engine/audit.py`) is now a single `engine.plugin_version()` shared module. `record_verification` also gained a `checks` default so the CLI is callable.

### Fixed
- **Windows stdin-inheritance deadlock in sandbox execution** (found by the local E2E/bare-env simulation layer): children spawned while the MCP server's main thread blocked on a piped stdin inherited that handle and stalled at startup until timeout — async `sandbox_run` failed 100% of the time in this environment. Both sync (`engine.sandbox_run`) and async paths now spawn with `stdin=DEVNULL`, `close_fds=True` and `CREATE_NO_WINDOW`; regression test `test_async_sandbox_completes_normally` locks it in.
- **draft-07 tuple `items` no longer crashes either validator path**: the jsonschema route degrades to the builtin subset when Draft 2020-12 rejects a legacy schema, and the builtin subset now understands positional `items` arrays plus `additionalItems`.
- **initialize() negotiates protocolVersion**: echoes the client's requested version when supported (2024-11-05 / 2025-03-26 / 2025-06-18), otherwise falls back to 2024-11-05 instead of always replying with the baseline.
- **Python 3.9 compatibility restored for match-statement analysis**: ast.Match* node types are resolved via getattr guards (they only exist on 3.10+); regression test simulates their absence.
- **Async sandbox no longer double-executes allowed commands**: prefix policy is now a pure check (`engine._prefix_allowed`) shared by both sync and async paths instead of a probe run that actually launched the process.
- **Identity unified to the canonical home**: server.json repository.url → gitcode.com/badhope/AgentSeed; mcpName/server name → io.gitcode.badhope/agentseed. Installers gain `--forge gitcode` / `-Forge gitcode` to resolve releases natively from GitCode's v5 API.

### Added
- **sandbox_run is cancellable**: long-running commands execute in a worker thread; MCP `notifications/cancelled` kills the child process and suppresses the result frame per spec, while the session stays responsive for other requests.

### Fixed
- **CLI `sandbox` no longer exits 0 when the command never ran**: command-not-found (-2) and run-failure (-9) now exit 1, so CI gating cannot mistake an unexecuted check for a pass.
- **Version chaos resolved**: test_server.py now derives the expected version from plugin.json (the declared single source of truth) instead of a hard-coded 1.3.3; server.json npm package version synced to 0.1.0. The suite is green again.
- **check_plugin false positive on relative stdio commands**: `"./bin/run.sh"` was rejected because of a list-membership bug (`"./" in command.split("/")[0:1]`); validation now uses a proper prefix check, matching what its own error message promised.
- **License unified to Apache-2.0** in plugin.json and server.json (previously "MIT" there while LICENSE/package.json said Apache-2.0).
- **MCP server forces UTF-8 on stdin/stdout** (`reconfigure`), fixing session-killing UnicodeEncodeError on Windows ANSI code pages (e.g. cp936); sandbox subprocess output decodes with `errors="replace"` instead of degrading to `-9`.
- **JSON-RPC notification handling**: notifications (frames without `id`, e.g. `notifications/cancelled`) are never answered — previously unknown ones triggered a spec-violating error reply with `id: null`.

### Added
- **Multi-platform release pipeline** (`scripts/pack.py` + `release.ps1`/`release.sh`): one command verifies plugin.json/package.json/server.json agree on version & license, builds a single deterministic zip from package.json `files`, and emits SHA256SUMS — the SAME artifact + hash goes to GitHub Releases, GitCode Releases and npm; users pin it via installer `--sha256`/`-Sha256`.
- `--check-only` mode (also enforced by new `server/test_manifests.py`) fails CI on any cross-platform manifest drift.
- Installers accept `--url ZIP_URL` / `-Url ZIP_URL` to install from any host (GitCode, self-hosted) and `--repo` / `-Repo` to override the release repo; default remains the canonical source.
- Installers accept `--sha256 HEX` / `-Sha256 HEX` to pin release-archive integrity; without it they print an explicit supply-chain warning (downloads were previously unverified).
- CLI `verify --strict`: a source file that cannot be parsed at all becomes exit 1 under strict gating.

### Changed
- `check_plugin` now reports `skills/<dir>/ missing required SKILL.md` instead of silently skipping such directories.
- Schema fallback validator: `additionalProperties: false` also applies when the schema has no `properties` key (all keys unexpected).
- npm launcher defaults to `python` on Windows (where `python3` is normally absent); PYTHON override unchanged.
