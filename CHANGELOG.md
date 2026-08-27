# Changelog

All notable changes to AgentSeed are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com); versioning follows [SemVer](https://semver.org).

## [Unreleased]

### Added
- **`verify_code` — config-driven multi-language engine**: a generic lexical
  verifier backed by a language registry (`LangSpec`). Newly supported:
  Go, Rust, Java, C, C++, C#, PHP, Ruby, Kotlin, Swift — on top of Python
  (AST) and TypeScript/JavaScript (lexical). The same engine runs every
  registered language (mask comments/strings → collect definitions/imports →
  flag undefined bare calls and `new`); adding a language is a registry entry,
  not an engine change. Ruby's paren-less calls are supported via `bare_calls`.
  MCP `verify_code.language` and CLI `verify --language` accept all aliases;
  unsupported languages now list the supported set in `note`.
- **`check_contract` — verify code against a written spec**: new MCP tool +
  `guard_cli contract` subcommand. Contract is JSON
  (`{"requires": [...], "prohibits": [...]}`); `requires` names must be
  defined/imported by the source (via new public `defined_symbols`),
  `prohibits` tokens must not appear. Exits 1 on violations.
- **`scripts/export_prompt_pool.py` — wire the prompt pool into per-client
  configs**: parses `PROMPT-POOL.md` (23 entries) and renders identical
  anti-hallucination prompts as `CLAUDE.md`, `AGENTS.md`, and Cursor
  rules (`.cursor/rules/agentseed-guardrails.mdc`) so the gates apply outside
  plugin-aware clients.

### Changed
- **`sandbox_run` — streamed, bounded-memory output truncation**: output was
  previously captured in full via `communicate()` then truncated, so a child
  flooding output could balloon server memory. Two daemon reader threads now
  drain stdout/stderr incrementally into tail ring buffers (8 KB / 4 KB caps),
  so memory stays bounded while the last-output tail semantics are preserved.
- `tools/list` now exposes 7 tools (was 6).

## [0.2.0] — 2026-08-26

### Security
- **`sandbox_allowed_prefixes` bypass fixed (High)**: the old matcher compared
  basenames and raw path prefixes, so on Windows a hostile `cwd` could plant
  `python.exe` to impersonate an allowlisted basename, and prefix `C:\tools\safe`
  matched `C:\tools\safe-evil\app.exe` (no separator boundary). Commands now
  resolve through `PATH`/`abspath` BEFORE execution; bare-name entries match the
  resolved basename (with `.exe` tolerance), path entries require a separator
  boundary, unmatched/unresolvable commands are refused with exit -10 without
  spawning, and allowed commands execute under their resolved absolute path.
  Regression tests cover boundary matching, `.exe` tolerance and cwd-shadowing.

### Changed
- **All `tools/call` requests now run in a worker thread** (previously only
  `sandbox_run`): a slow `verify_code`/`check_plugin` can no longer stall the
  stdio read loop. Cancellation semantics extend to every tool; responses stay
  single-writer serialized.
- **Engine public API cleanup**: config helpers renamed to public names
  (`config_str_list`, `config_severities`, `parse_timeout`,
  `config_extra_tokens`); private internals (`_decode`, `_run_command`,
  `_prefix_allowed`, `_GROUP_LABELS`, `_config_*`) are no longer re-exported
  from the `engine` package.
- **server.json honesty**: the npm registry package entry was removed until
  `agentseed-mcp` is actually published (the manifest previously advertised a
  package that does not exist in the registry). The manifest-drift test now
  accepts zero listed packages while enforcing version agreement for any that
  appear.
- **Comparison table rewritten**: the "Anti-Hallucinate (mcpmarket)" competitor
  could not be verified to exist; tables across READMEs/DESIGNs now compare
  against verifiable categories (prompt-only guardrail skills such as
  superpowers; static import linters).

### Added
- **Client-enforcement hook** (`server/guard_hook.py`, installers `--hooks` /
  `-Hooks`): registers as a Claude Code PreToolUse/PostToolUse hook so every
  `Write`/`Edit`/`MultiEdit` is scanned at the client boundary — PreToolUse
  checks the incoming `content`/`new_string` before anything lands on disk,
  and error-severity findings return as exit code 2 with the reason on stderr
  (the channel Claude Code feeds back to the model). Registration merges into
  `~/.claude/settings.json` idempotently (stale agentseed entries replaced,
  unrelated hooks preserved). Fail-open policy: infrastructure errors never
  block edits; only positive scan findings do. Honored config keys:
  `allowlist`, `severities`, `suppress_symbols`, `extra_tokens`. Covered by
  17 subprocess tests wired into both CI test jobs.
- **pyflakes enhancement is real**: `verify_code` now merges pyflakes F821
  undefined-name findings into its AST walk when pyflakes is installed (catches
  e.g. Del-context names the hand-rolled walk misses); previously the import
  existed but was never called. Zero-dep behavior unchanged when absent.
- **Baseline scan mode** (`guard_cli scan <path> --baseline F [--update-baseline]`):
  freezes a line-number-free fingerprint of known self-referential hits and
  fails only on NEW signals — the repo now ships its own `baseline-scan.json`
  (538 documented hits in tool descriptions/fixtures).
- **Composite hard gate** (`guard_cli gate --root .`): conformance linter +
  undefined-symbol sweep over all Python sources + baseline scan, one exit
  code; wired into CI as the `gate` job (ubuntu/windows). This is the hard
  enforcement layer behind the soft skill.
- **Detection benchmark** (`scripts/bench_detection.py` + `docs/BENCHMARK.md`):
  seeded synthetic corpus across five defect classes; current figures
  precision=1.0 recall=1.0 (tp=100 fp=0 fn=0). Locked by a regression test.
- **Sandbox tree-kill + env scrubbing**: timeouts and cancellations now
  terminate the whole process tree (POSIX process group / Windows
  `taskkill /F /T`); new config `sandbox_env: "scrub"` drops credential-like
  environment variables before spawn (opt-in best-effort denylist).
- **Input bounds**: MCP frames larger than 2 MB are rejected with -32600;
  JSON-Schema patterns longer than 256 chars are refused by both validator
  paths (defensive ReDoS bound).

### Fixed
- Documentation truth sweep: CHANGELOG 0.1.1 claim scoped to the English README
  only (zh/ja sync tracked below); CONTRIBUTING test count corrected;
  `README.md` platform-table dead link replaced with a concrete pointer.

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
- README (en): honest language-coverage table, full configuration reference, explicit sandbox_run security warning. (zh/ja equivalents land in Unreleased.)

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
