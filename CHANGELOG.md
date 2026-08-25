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

## [1.3.3] — 2026-08

### Added
- **Compatibility & graceful-degradation matrix** in the READMEs: full Agent Plugins clients (drop-in) → MCP-only clients → skills-only clients → plain terminal/CI, each with a defined setup path.
- **CLI fallback built into the skill**: when the `agentseed` MCP tools are not registered in the session, SKILL.md/zh/ja now instruct the agent to run `guard_cli.py verify/scan` via the shell and apply the same blocking rules — verification is never silently skipped.
- CI: `macos-latest` added to the test matrix; POSIX skill-script smoke now runs on macOS too.

## [1.3.2] — 2026-08

### Fixed
- Skill scripts check `.agentseed-plugin-root` at both the `scripts/` and skill-root level; the v1.3.1 installers shipped scripts that missed the skill-root copy, so freshly installed check.ps1/check.sh still could not locate guard_cli.py. Verified against a real installer run.

## [1.3.1] — 2026-08

### Fixed
- **Installers rewired after an end-to-end fresh-clone audit**: full plugin now lives at a stable home (~/.agentseed/AgentSeed) so the MCP server path never breaks; skill is copied *flat* (SKILL.md at the top level) so clients that scan one level deep actually discover it; installer prints the exact MCP registration step for claude/opencode/cursor.
- Skill scripts resolve guard_cli.py via AGENTSEED_PLUGIN_ROOT, a .agentseed-plugin-root pointer file written by the installer, or directory walk-up.
- install.ps1: replaced PowerShell 7-only ?? operator (parse error on Windows PowerShell 5.1).

### Added
- Community files: CONTRIBUTING.md, bug/feature issue templates, pull request template.
- READMEs: exact per-client configuration snippets (Claude Code, opencode, generic MCP).

## [1.3.0] — 2026-08

### Changed — modular engine, standard libraries over hand-rolled code
- `guard_engine.py` split into the `server/engine/` package (config / hallucination / plugin / sandbox / schema / symbols); `guard_engine.py` remains as the import hub.
- **schema_validate** now delegates to [`jsonschema`](https://pypi.org/project/jsonschema/) (Draft 2020-12, full keyword coverage) when installed; a built-in subset validator keeps bare environments working. Results report which validator ran (`validator` field).
- **verify_code** (Python) uses [`pyflakes`](https://pypi.org/project/pyflakes/) F821 analysis when available for more reliable undefined-name detection; zero-dep AST walk remains the fallback.
- SKILL.md frontmatter parsing uses PyYAML when available; lite parser remains the fallback.
- Optional extras: `pip install -r server/requirements.txt` (jsonschema, pyflakes, pyyaml). The plugin still runs without any of them.

### Fixed
- Skill rules and tool text aligned with the severity model (only error-severity hits block; warnings reported but non-blocking).
- `serverInfo` version is now read from root `plugin.json` (single source of truth) instead of a drifting literal.
- Skill scripts (`check.sh`/`check.ps1`) locate the CLI by walking up to the plugin root or `AGENTSEED_PLUGIN_ROOT`; ps1 no longer assigns to the reserved `$args` variable.
- Install scripts dropped speculative Cursor/VS Code auto-paths; platform matrix marks only actually-exercised clients as verified.
- CI: main matrix installs requirements.txt; a new `bare` job pins the zero-dependency fallback path so an unconditional import cannot land again.

## [1.2.0] — 2026-08

### Added
- **Severity levels** for `scan_hallucination`: each hit carries `error` / `warning` / `info`; defaults block on oversold & fabricated claims, warn on stub markers. Result includes a `blocking` flag and severity counts. Group severities are remappable via config.
- **Persistent config** via Agent Plugins §9.1: `load_config()` resolves `agentseed.config.json` from `${PLUGIN_DATA}` (spec-guaranteed persistent per-plugin dir), `AGENTSEED_CONFIG`, or cwd. Keys: `allowlist`, `severities`, `timeout`.
- **CLI** (`server/guard_cli.py`, zero dependencies): `verify`, `scan`, `check --ci`, `sandbox` with CI-friendly exit codes — the same gates that bind agent sessions can now block human PRs. `scan --strict` restores strict matching with stub hits as errors.
- **Skill scripts**: `skills/verify-before-code/scripts/check.sh` / `check.ps1` one-command gate using the CLI.

### Changed — conformance linter (§7.2.1, §9.1)
- Server entries validated as closed variants: unknown fields are errors (e.g. `url` on stdio).
- stdio `command` must be a bare token or plugin-relative `./...` path; `args` string arrays enforced.
- `env` must not define reserved `PLUGIN_ROOT` / `PLUGIN_DATA`.
- Remote URLs: absolute HTTP(S), no userinfo/fragment, HTTPS required off-loopback; duplicate header names rejected.

## [1.1.0] — 2026-08

### Fixed
- `verify_code` (Python): collect all binding targets (assignments, `for`/`with`/`except as`, walrus, comprehensions, `global`/`nonlocal`) — ordinary local state no longer flagged as hallucinated symbols.
- `scan_hallucination`: skip import lines and dotted paths; default allowlist covers standard test doubles (`unittest.mock`, `Mock()`, `patch()`, …); new optional `allowlist` argument.
- `schema_validate`: `const: null` validated; boolean ≠ number in enum/const equality; `type` arrays supported.
- MCP server: unknown methods return JSON-RPC `-32601`; `ping` returns `{}`; internal errors return `-32603` without killing the session; BrokenPipe handled.
- Frontmatter parser tolerates `---` lines in body; TS analysis collects multi-declarations.

### Changed
- Tests use `sys.executable` (Windows portability); protocol and CLI test suites added.

## [1.0.0] — initial release
- Hybrid Skill + MCP guardrails: `verify_code`, `scan_hallucination`, `check_plugin`, `sandbox_run`, `schema_validate`. First strict Agent Plugins 1.0.0 linter. Zero dependencies (pure Python standard library).
