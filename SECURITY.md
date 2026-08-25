# Security Policy

## Supported versions

| Version | Support |
|---------|---------|
| 0.1.x   | active  |

## Reporting a vulnerability

Do NOT open a public issue for security reports.

1. Use GitCode private issue / contact the maintainer (`badhope`) directly.
2. Include: affected version (plugin.json `version`), reproduction steps,
   impact assessment.
3. Expect an initial response within 7 days; fixes ship as a patch release
   with a CHANGELOG entry crediting the reporter (unless anonymity requested).

## Threat model notes

AgentSeed is a **developer-machine tool**, not a sandbox boundary:

- `sandbox_run` executes real processes with the permissions of the MCP
  client's user. It is a *verification* channel, not isolation. Clients MUST
  gate every call behind explicit user approval; enterprises should set
  `sandbox_allowed_prefixes` in `agentseed.config.json` to restrict which
  executables may run at all.
- With an allowlist configured, the command head resolves through `PATH` to
  its absolute path BEFORE execution: bare names can never be shadowed by an
  executable planted in the caller-controlled working directory, path-prefix
  entries require a separator boundary (`dir/safe` does not match
  `dir/safe-x/app.exe`), and unmatched or unresolvable commands are refused
  with exit code -10 without spawning. Matched commands execute under their
  resolved absolute path.
- Known hardening limits (documented non-goals): a timed-out child's own
  descendants are not killed (no process-group/Job-Object teardown), child
  output is buffered in full before truncation, and spawned processes inherit
  the server's environment variables.
- The stdio MCP server trusts its launching client (local process). It binds
  no sockets and performs no network I/O itself.
- Installers verify release archives only when given `--sha256` /
  `-Sha256`; without it they warn and proceed — always pin checksums in CI.

## Known non-goals

- No authentication on the stdio transport (local trust model by design).
- `check_plugin` reads arbitrary local paths passed to it — it is a linter,
  not a security boundary for file access.
