<div align="center">

# 🛡️ AgentSeed

**Anti-hallucination guardrails for AI coding agents.**

A hybrid [Agent Plugins](https://agent-plugins.org) plugin (Skill + MCP Server) that forces spec-driven development and **verifies code before it is marked done** — so "Done, all tests pass" becomes an observed fact, not a claim.

[![License](https://img.shields.io/badge/license-Apache_2.0-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.2.0-blue)](https://gitcode.com/badhope/AgentSeed/releases)
[![CI](https://github.com/Morningstar202604/AgentSeed/actions/workflows/ci.yml/badge.svg)](https://github.com/Morningstar202604/AgentSeed/actions/workflows/ci.yml)
[![Platforms](https://img.shields.io/badge/platform-Cursor%20%7C%20VS%20Code%20%7C%20Claude%20Code%20%7C%20Copilot-blue)](https://agent-plugins.org)

**English** · [中文](./README.zh.md) · [日本語](./README.ja.md)

⭐ **Like this project? Consider giving it a star — it helps developers find guardrails before they ship hallucinated code.**

</div>

---

## Why AgentSeed

LLMs hallucinate — in code, that means **invented APIs, undefined identifiers, fake test passes, and confident overclaims**. The numbers:

- **15.1%** of code hallucinations are knowledge-conflicting: calling APIs that don't exist or were never imported ([arXiv:2404.00971](https://arxiv.org/abs/2404.00971)).
- **<10%** of hallucinated code fails tests — most slips through CI ([arXiv:2404.00971](https://arxiv.org/abs/2404.00971)).
- **60%+** of model-output errors are *unverifiable* — no way to tell fact from fiction (FAVA, cited in [SoK](https://arxiv.org/abs/2502.18468)).

Prompt-only guardrails are soft: a model can *agree* to verify and then skip it. **AgentSeed binds the instruction to a hard MCP gate** — the evidence comes from running code, not from the model's self-report.

It also fills two gaps the 1.0.0 spec deliberately leaves open:

| Gap in Agent Plugins 1.0.0 | What AgentSeed does |
| --- | --- |
| No enforcement mechanism (skills are optional to follow) | `verify-before-code` skill makes verification **non-skippable** |
| No official conformance linter | `check_plugin` is the **first strict 1.0.0 linter** |

## What it does

Six MCP tools — zero *required* dependencies, enhanced by optional extras:

| Tool | Catches | Technique |
| --- | --- | --- |
| `verify_code` | Invented APIs / undefined symbols | Python AST + TS/JS lexical pass |
| `scan_hallucination` | Placeholder code, overclaims, fabricated content | 28+ signals in 3 groups |
| `check_plugin` | Non-conformant plugin packaging | Strict 1.0.0 linter |
| `sandbox_run` | "Tests pass" without running anything | Deterministic execution channel |
| `schema_validate` | Invalid structured output | JSON Schema validation |
| `record_verification` | No persistent evidence trail | Appends a JSONL audit entry under `PLUGIN_DATA` |

Measured on a seeded synthetic corpus (5 defect classes): **precision 1.0, recall 1.0** (tp=100, fp=0, fn=0) with the regression test locking it in — methodology and honest scope in [docs/BENCHMARK.md](./docs/BENCHMARK.md).

## Live demo

```
$ verify_code(source="def f():\n    return magic_unknown()\n", language="python")
{
  "language": "python",
  "suspects": ["magic_unknown"]      # ← hallucinated API caught
}

$ scan_hallucination(source="The feature is production ready, all tests pass. Trust me.")
{
  "hits": [
    {"word": "all tests pass", "group": "oversold", "line": 1},
    {"word": "production ready", "group": "oversold", "line": 1},
    {"word": "trust me", "group": "oversold", "line": 1}
  ],
  "clean": false                      # ← overclaim caught
}

$ check_plugin(path="/path/to/AgentSeed")
{ "ok": true, "errors": [], "warnings": [] }   # ← strict 1.0.0 conformance
```

## Quick start

**Option A — download a release (no git needed):**

```bash
# grab the latest asset from https://gitcode.com/badhope/AgentSeed/releases
# or use the installer, which drops it into a client of your choice:
bash install.sh --client auto        # macOS / Linux
./install.ps1 -Client auto           # Windows PowerShell
# --client: claude | opencode | cursor | manual
# add --hooks / -Hooks to also register the Claude Code enforcement hook
```

**Option B — clone:**

```bash
git clone https://gitcode.com/badhope/AgentSeed.git
# or: https://gitcode.com/badhope/AgentSeed · https://gitee.com/badhope/AgentSeed
```

1. **Drop** the `AgentSeed/` directory into any client that supports Agent Plugins (Cursor, VS Code, Claude Code, Copilot…). No build, no install; zero required dependencies (optional extras below).
2. The client auto-discovers the `verify-before-code` skill and the `agentseed` MCP server from `plugin.json` + `mcp.json`.
3. **That's it.** The skill now gates every coding task: contract → implement → verify → evidence.

Run it standalone for a self-check:

```bash
python3 server/guard_engine.py              # self-check: demo verify_code + scan_hallucination
python3 -m unittest discover -s server      # 90+ unit tests (also: `pytest` in CI)
```

Gate a human PR with the same rules (CI mode):

```bash
python3 server/guard_cli.py gate --root .    # composite hard gate: conformance
                                             # + symbols + baseline scan, exit 1 on any failure
python3 server/guard_cli.py check . --ci     # plugin conformance only, exit 1 on errors
python3 server/guard_cli.py scan src/ --strict   # hallucination scan, blocking severities only
```

> **Windows note:** `mcp.json` launches the server via `python3`. On many
> Windows installs that alias is a Microsoft Store stub; if the server fails
> to start, change `command` to `["python", "server/guard_server.py"]` or
> point it at your interpreter's absolute path.

## Client-enforced hook mode (Claude Code)

Skills persuade; hooks enforce at the client boundary. Register AgentSeed as
a Claude Code hook and every `Write`/`Edit`/`MultiEdit` tool call is scanned
automatically — no prompt can skip it:

```bash
python3 server/guard_hook.py register --client claude   # merges into ~/.claude/settings.json, idempotent
python3 server/guard_hook.py --file path/to/source.py   # scan any file directly
```

- **PreToolUse** inspects the incoming `content`/`new_string` *before* it
  lands on disk; a blocking finding exits `2`, so Claude receives the reason
  on stderr and must fix the flagged lines instead of writing the file.
- **PostToolUse** re-checks the saved file for write paths without inline
  content.
- **Failure policy (honest scope):** infrastructure problems — malformed
  stdin, unreadable files, unknown tool shapes — never block work
  (fail-open); only positive scan findings block. Warning-severity signals
  are reported but do not block.
- Severity/allowlist/suppression tuning uses the same `agentseed.config.json`
  keys as the rest of the plugin.

Manual settings.json entry, if you prefer not to run the register command:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Write|Edit|MultiEdit",
        "hooks": [ { "type": "command",
                     "command": "python /path/to/AgentSeed/server/guard_hook.py" } ] }
    ],
    "PostToolUse": [
      { "matcher": "Write|Edit|MultiEdit",
        "hooks": [ { "type": "command",
                     "command": "python /path/to/AgentSeed/server/guard_hook.py" } ] }
    ]
  }
}
```

The installers wire this for you with `--hooks` (bash) / `-Hooks`
(PowerShell).

## Optional dependencies

AgentSeed runs on the Python standard library alone. Installing the extras
upgrades two tools to industry-standard engines (auto-detected, graceful
fallback either way):

```bash
pip install -r server/requirements.txt
```

| Extra | Upgrades | Without it |
| --- | --- | --- |
| `jsonschema` | `schema_validate` → full Draft 2020-12 validation | built-in subset validator |
| `pyflakes` | `verify_code` → pyflakes F821 undefined-name analysis | built-in AST walk |
| `pyyaml` | SKILL.md frontmatter parsing → full YAML | built-in lite parser |

> Use an absolute path to `guard_server.py`; the server resolves everything
> else from its own location, so no special cwd is required.

## Compatibility & graceful degradation

AgentSeed adapts to whatever the host supports, degrading one level at a time
— never silently skipping verification:

| Host capability | What you get | Setup |
| --- | --- | --- |
| Full Agent Plugins | drop-in: skill + MCP auto-discovered, `${PLUGIN_DATA}` config honored | copy the plugin directory |
| MCP-capable client | all 6 tools via registration | exact snippets above |
| Skills-only client | skill workflow; **verification degrades to `guard_cli.py` via shell** (the skill contains the fallback instructions) | copy `skills/verify-before-code` flat |
| Plain terminal / CI / no agent at all | CLI gates with exit codes | `python server/guard_cli.py check . --ci` |

The skill itself carries the degradation path: when the MCP tools are absent,
it instructs the agent to run `guard_cli.py verify/scan` through the shell and
apply the same blocking rules to exit codes.

## Platform support

| Client | Agent Plugins 1.0.0 | Status | Notes |
| --- | --- | --- | --- |
| Claude Code | skills + MCP config | verified | skills via `~/.claude/skills`, server via `claude mcp add`; optional enforcement hook via `guard_hook.py register --client claude` |
| opencode | skills + MCP config | verified | `~/.config/opencode/opencode.json` — exact snippet below |
| Cursor | skills + mcp.json | untested* | copy into project; no stable plugin dir yet |
| VS Code (+Copilot) | MCP support rolling out | untested* | use mcp.json fields as-is |
| Cline / Windsurf | MCP config compatible | untested* | stdio server entry maps directly |

\* honest states: the formats are spec-compatible and expected to work, but we
have not run AgentSeed in these clients ourselves. Verified = actually exercised
by the maintainers. If you verify one, open a PR updating this table.

Clients honoring the full spec also set `${PLUGIN_DATA}`; AgentSeed reads
`agentseed.config.json` from there.

### Configuration reference (`agentseed.config.json`)

| Key | Type | Effect |
| --- | --- | --- |
| `allowlist` | `string[]` | scan exclusions (replaces built-in test-idiom list) |
| `severities` | `{group: error\|warning\|info}` | per-group severity override |
| `timeout` | `int` | default `sandbox_run` timeout, seconds (clamped 1–120) |
| `extra_tokens` | `{group: string[]}` | extend the hallucination word pool at runtime |
| `suppress_symbols` | `string[]` | names `verify_code` never flags (reported in `suppressed`) |
| `sandbox_allowed_prefixes` | `string[]` | **allowlist of executables** `sandbox_run` may launch (absent = unrestricted). Entries without a path separator match the command's PATH-resolved basename (`python` also accepts `python.exe`); entries WITH a separator must equal or be a directory-prefix of the resolved absolute path (separator boundary enforced) |
| `sandbox_env` | `"inherit"` \| `"scrub"` | child environment policy: `scrub` drops credential-looking variable names (TOKEN/SECRET/PASSWORD/API_KEY/…) before spawn — best-effort denylist, not a security boundary |

Unknown keys are warned about on stderr — a typo'd key is never silently
ignored.

### Language coverage (honest scope)

| Language | `verify_code` analysis |
| --- | --- |
| Python | full AST scope walk (+ pyflakes when installed), line numbers |
| TypeScript / JavaScript | lexical regex pass (documented false-positive classes) |
| Go / Java / Rust / C/C++ / others | **not analyzed yet** — returns an empty result |

> ⚠️ **Security note**: `sandbox_run` executes real processes with your user's
> permissions. Clients must gate it behind user approval; set
> `sandbox_allowed_prefixes` in shared/CI environments. When an allowlist is
> configured, commands resolve through `PATH` to their absolute path before
> execution — a hostile working directory cannot shadow an allowlisted
> basename with a planted executable, and unmatched/unresolvable commands are
> refused (exit -10) without running.

## Client setup — exact configuration

AgentSeed has two halves; both are needed for the full gate:

1. **Skill** (`skills/verify-before-code/`) — teaches the agent the workflow.
2. **MCP server** (`server/guard_server.py`) — provides the 6 tools.

The installers wire step 1 and print step 2 for your client. Manual setup:

**Claude Code**

```bash
# skill: copy it flat so SKILL.md sits directly in the folder
cp -R skills/verify-before-code ~/.claude/skills/verify-before-code
# MCP server:
claude mcp add agentseed -- python /path/to/AgentSeed/server/guard_server.py
```

**opencode** — copy `skills/verify-before-code/` to
`~/.config/opencode/skill/verify-before-code`, then add to `opencode.json`:

```json
{
  "mcp": {
    "agentseed": {
      "type": "local",
      "command": ["python", "/path/to/AgentSeed/server/guard_server.py"],
      "enabled": true
    }
  }
}
```

**Cursor / other MCP clients** — register a stdio server with
`command: python`, `args: ["/path/to/AgentSeed/server/guard_server.py"]`,
and copy the skill folder per your client's skills location.

> Use an absolute path to `guard_server.py`; the server resolves everything
> else from its own location, so no special cwd is required.

## Changelog

See [CHANGELOG.md](./CHANGELOG.md).

## Built-in guardrail library (EN / 中文 / 日本語)

| Resource | Contents |
| --- | --- |
| `PROMPT-POOL` | 20+ copy-paste guardrail prompts: completion evidence, verify-before-claim, uncertainty, API verification, citation rules… |
| `HALLUCINATION-PATTERNS` | Failure-mode catalog: 5-class code taxonomy + SoK findings + real legal/chat cases |
| `VERIFICATION-CHECKLIST` | Executable end-of-task checklist: risk class → contract → evidence → language audit |
| `SDD-CONTRACT` | The contract every coding task must satisfy |
| `VENDOR-SOLUTIONS` | Adoption map of vendor techniques (Anthropic, OpenAI, AWS, NVIDIA, IBM, Guardrails AI, Vectara) |

## How the gate works

1. **Before coding** — load the SDD contract, state it in one sentence.
2. **Implement** — real code only: no placeholders, no invented APIs.
3. **Before "done"** — call `verify_code` + `scan_hallucination`; prove runtime claims with `sandbox_run`; validate structure with `schema_validate`.
4. **Language audit** — completion reports attach evidence; overclaim vocabulary is banned.
5. Only when **all checks pass** may the task be marked complete.

## The enforced norms (how the AI is constrained)

The skill does not just *suggest* behavior — each norm maps to a gate that
observes compliance:

| Norm | Enforced by |
| --- | --- |
| Contract before code (goal / interface / non-goals / verification) | Gate 1 of `verify-before-code` |
| No invented APIs — never call an undefined symbol | `verify_code` suspects gate |
| Real implementations only — no stubs/placeholders/fakes | `scan_hallucination` stub signals |
| Verification before completion claims — run it, then say it | Gate 3 + `sandbox_run` exit codes |
| Evidence-backed reports — file:line you read, output you saw | Gate 4 audit + `record_verification` JSONL |
| Smallest diff, no drive-by refactors; surface ambiguity, ask once | contract non-goals + CI `guard_cli gate` |

These synthesize what strong agent operators converged on publicly — the
[AGENTS.md](https://agents.md) open standard, [Anthropic's Claude Code best
practices](https://code.claude.com/docs/en/best-practices), and community
disciplines like
[FerroxLabs/agents-md](https://github.com/FerroxLabs/agents-md) (senior-
engineer stance, anti-sycophancy, forced verification loops). The difference:
**there they are prose; here every norm has an enforcing tool or exit code.**
Full table with rationale:
[`skills/verify-before-code/references/DEFAULT-NORMS.md`](./skills/verify-before-code/references/DEFAULT-NORMS.md).

## Works alongside your agent config files

AgentSeed complements — not replaces — the context files your team already
maintains for AI coding agents (`CLAUDE.md`, `AGENTS.md`, `.cursor/rules/`,
`.github/copilot-instructions.md`, `CONTRIBUTING.md` conventions):

- **Those files carry project facts**: stack, commands, layout, style. They are
  prose — persuasive but soft.
- **AgentSeed carries the behavior contract and the enforcement**: hallucination
  detection, verification gates, evidence trails — hard MCP tools plus CI exit
  codes that cannot be quietly deprioritized.
- Keep one source of truth per concern: point your `AGENTS.md` at this skill's
  norms instead of copying them; the plugin updates and the norm stays binding.

## Why AgentSeed vs. alternatives

| | Prompt-only guardrail skills (e.g. superpowers) | Static import linters (MCP) | **AgentSeed** |
| --- | --- | --- | --- |
| Touches code | ❌ prompt only | ✅ import-graph analysis | ✅ AST + lexical analysis |
| Runs verification tools | ❌ | lint gates | ✅ 6 MCP tools incl. sandboxed execution |
| Hallucination-language scan | ❌ | ❌ | ✅ stub / oversold / fabricated signals (EN + CJK) |
| Enforcement | soft (skill text) | CI gate | **hard gate**: skill + MCP + CLI exit codes |
| Agent Plugins 1.0.0 conformance linter | ❌ | ❌ | ✅ first |

## FAQ

**Does it need a specific LLM?** No — it's client-agnostic and model-agnostic. The gate is enforced by the skill + MCP server, not by any model.

**Zero dependencies?** Yes. The entire MCP server is pure Python standard library.

**Conformant?** `check_plugin` validates the plugin against the spec (§5/§6/§7) — and AgentSeed passes its own linter (`ok: true`).

## Contributing

Issues, PRs and ideas welcome — or open an issue for a hallucination pattern we haven't catalogued yet.

## License

Apache-2.0 © AgentSeed. See [LICENSE](./LICENSE).

---

<div align="center">

⭐ **If AgentSeed saved you from shipping hallucinated code, star the repo — it's the best signal that guardrails matter.**

</div>
