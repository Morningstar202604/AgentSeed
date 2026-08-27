# Security Policy

## Supported versions

| Version | Support |
|---------|---------|
| 0.3.x   | active (current release line) |
| 0.2.x   | critical security fixes only |
| 0.1.x   | end-of-life |

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
- With an allowlist configured, the command head resolves through `PATH` (or
  the run `cwd` for relative paths) to its absolute path BEFORE execution:
  bare names can never be shadowed by an executable planted in the
  caller-controlled working directory, path-prefix entries require a
  separator boundary (`dir/safe` does not match `dir/safe-x/app.exe`), and
  unmatched or unresolvable commands are refused with exit code -10 without
  spawning. Matched commands execute under their resolved absolute path.
- Timeouts and MCP cancellations terminate the whole process TREE (POSIX:
  per-child session + SIGKILL on the group; Windows: `taskkill /F /T`), not
  just the direct child.
- Setting config `sandbox_env: "scrub"` drops credential-looking environment
  variable names before spawn. This is a best-effort denylist for leak
  reduction — NOT a security boundary; treat any spawned process as able to
  read whatever remains.
- A child that floods its output can no longer balloon the server: both pipes
  are drained incrementally by reader threads into tail ring buffers (8 KB
  stdout / 4 KB stderr), so memory stays bounded while the "last output wins"
  truncation semantics hold (see `server/engine/sandbox.py`).
- Known hardening limit (documented non-goal): no CPU/memory rlimits are
  imposed on children — an escaping process can still consume host CPU or disk.
- The stdio MCP server trusts its launching client (local process). It binds
  no sockets and performs no network I/O itself. Protocol frames larger than
  2 MB are rejected unread (-32600) as a parse-cost bound.
- Installers verify release archives only when given `--sha256` /
  `-Sha256`; without it they warn and proceed — always pin checksums in CI.

## Known non-goals

- No authentication on the stdio transport (local trust model by design).
- `check_plugin` reads arbitrary local paths passed to it — it is a linter,
  not a security boundary for file access.
