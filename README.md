<div align="center">

<img src="docs/logo.png" width="96" alt="AgentSeed logo">

# AgentSeed

**The anti-hallucination gate for AI coding agents.**

AI agents invent APIs. They claim "all tests pass" without running anything.
They ship confident, fabricated code. **AgentSeed is the gate that stops it** —
a zero-dependency plugin that verifies code *before* it is marked done, so
"done" means *observed fact*, not self-report.

[![License](https://img.shields.io/badge/license-Apache_2.0-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.0-blue)](https://gitcode.com/badhope/AgentSeed/releases)
[![CI](https://github.com/Morningstar202604/AgentSeed/actions/workflows/ci.yml/badge.svg)](https://github.com/Morningstar202604/AgentSeed/actions/workflows/ci.yml)
[![Platforms](https://img.shields.io/badge/platform-Cursor%20%7C%20VS%20Code%20%7C%20Claude%20Code%20%7C%20Copilot-blue)](https://agent-plugins.org)

**English** · [中文](./README.zh.md) · [日本語](./README.ja.md)

⭐ **Like this project? Star it — it helps developers find guardrails before they ship hallucinated code.**

</div>

---

## Why you need this

LLMs hallucinate — and in code that means **invented APIs, undefined
identifiers, fake test passes, and confident overclaims**:

- **15.1%** of code hallucinations call APIs that don't exist or were never imported ([arXiv:2404.00971](https://arxiv.org/abs/2404.00971)).
- **<10%** of hallucinated code fails tests — **~90% slips past CI** ([arXiv:2404.00971](https://arxiv.org/abs/2404.00971)).
- **60%+** of model-output errors are *unverifiable* on their face (FAVA, [SoK](https://arxiv.org/abs/2502.18468)).

Prompt-only guardrails are soft: a model can *agree* to verify and then skip
it. **AgentSeed binds the instruction to a hard gate** — the evidence comes
from running code, not from the model's own word.

## What AgentSeed is — in 30 seconds

A drop-in [Agent Plugins](https://agent-plugins.org) 1.0.0 plugin
(Skill + MCP server + optional client hook + CI gate) that makes three
promises:

| Promise | How it's kept |
| --- | --- |
| **🚫 No invented APIs** | `verify_code` parses your code in **12+ languages** and flags any symbol that is called but never defined or imported |
| **🚫 No fake "done"** | `scan_hallucination` catches stubs, overclaims, and fabricated claims in **English and CJK**; `sandbox_run` proves runtime claims by actually running them |
| **🚫 No skipped verification** | the Skill gates the workflow, the **client hook** blocks `Write`/`Edit` on files that don't pass, and `guard_cli gate` enforces the same rules in CI with exit codes |

It also fills the two gaps the 1.0.0 spec deliberately leaves open:

| Gap in Agent Plugins 1.0.0 | AgentSeed's answer |
| --- | --- |
| No enforcement mechanism (skills are optional to follow) | `verify-before-code` skill + optional **client-enforced hook** make verification non-skippable |
| No official conformance linter | `check_plugin` is the **first strict 1.0.0 linter** — and AgentSeed passes its own linter (`ok: true`) |

## See it catch a hallucination

```python
# Your coding agent just "finished" this — it calls magic_unknown(),
# an API that doesn't exist and was never imported:

def f():
    return magic_unknown()      # ← hallucinated API

# AgentSeed, before the task can be marked done:
$ verify_code(source=..., language="python")
{
  "language": "python",
  "suspects": ["magic_unknown"]       # ← caught, blocking
}
```

```text
# And the agent's completion claim doesn't survive either:
"The feature is production ready, all tests pass. Trust me."

$ scan_hallucination(source=...)
{
  "hits": [
    {"word": "all tests pass",   "group": "oversold",  "line": 1},
    {"word": "production ready", "group": "oversold",  "line": 1},
    {"word": "trust me",         "group": "oversold",  "line": 1}
  ],
  "clean": false                        # ← caught, blocking
}
```

The verdict is **measured, not promised**: on a seeded synthetic corpus
(5 defect classes, 100 defective + 40 clean modules) AgentSeed scores
**precision 1.0 · recall 1.0** (tp=100, fp=0, fn=0) — locked in by a
regression test. Methodology and honest limits:
[docs/BENCHMARK.md](./docs/BENCHMARK.md).

## How the gate works

1. **Before coding** — load the SDD contract and state it in one sentence.
2. **Implement** — real code only: no placeholders, no invented APIs.
3. **Before "done"** — run `verify_code` + `scan_hallucination`; prove runtime
   claims with `sandbox_run`; validate structure with `schema_validate`.
4. **Language audit** — completion reports attach evidence; overclaim
   vocabulary is banned.
5. Only when **all checks pass** may the task be marked complete.

## Quick start

**Option A — download a release (no git needed):**

```bash
# grab the latest asset from https://gitcode.com/badhope/AgentSeed/releases
# or use the installer, which wires it into your client:
bash install.sh --client auto --hooks        # macOS / Linux
./install.ps1 -Client auto -Hooks            # Windows PowerShell
# --client: claude | opencode | cursor | manual
# --hooks / -Hooks: also register the Claude Code enforcement hook
```

**Option B — clone:**

```bash
git clone https://gitcode.com/badhope/AgentSeed.git
# mirrors: https://gitcode.com/badhope/AgentSeed · https://gitee.com/badhope/AgentSeed
```

1. **Drop** the `AgentSeed/` directory into any Agent Plugins–capable client
   (Cursor, VS Code, Claude Code, Copilot…). No build, no install.
2. The client auto-discovers the `verify-before-code` skill and the
   `agentseed` MCP server from `plugin.json` + `mcp.json`.
3. **That's it.** Every coding task is now gated: contract → implement →
   verify → evidence.

Run it standalone or gate a human PR with the same rules:

```bash
python3 server/guard_engine.py              # self-check demo
python3 -m unittest discover -s server      # 160+ unit tests
python3 server/guard_cli.py gate --root .   # CI-equivalent hard gate
python3 server/guard_cli.py check . --ci    # plugin conformance only
python3 server/guard_cli.py scan src/ --strict
```

> **Windows note:** `mcp.json` launches the server via `python3`. On many
> Windows installs that alias is a Microsoft Store stub; change `command` to
> `["python", "server/guard_server.py"]` or use your interpreter's absolute path.

## The 7 MCP tools

Zero *required* dependencies — pure Python standard library; optional extras
upgrade two tools to industry-standard engines (see below).

| Tool | Catches | Technique |
| --- | --- | --- |
| `verify_code` | Invented APIs / undefined symbols | Python AST + config-driven lexical passes (12+ languages) |
| `check_contract` | Code violates a written spec | requires/prohibits contract check |
| `scan_hallucination` | Placeholder code, overclaims, fabricated content | 28+ signals in 3 groups, EN + CJK |
| `check_plugin` | Non-conformant plugin packaging | Strict 1.0.0 linter |
| `sandbox_run` | "Tests pass" without running anything | Deterministic execution channel (bounded-memory output) |
| `schema_validate` | Invalid structured output | JSON Schema validation |
| `record_verification` | No persistent evidence trail | JSONL audit trail under `PLUGIN_DATA` |

### Language coverage (honest scope)

| Language | `verify_code` analysis |
| --- | --- |
| Python | full AST scope walk (+ pyflakes when installed), line numbers |
| TypeScript / JavaScript | lexical regex pass (documented false-positive classes) |
| Go · Rust · Java · C · C++ · C# · PHP · Ruby · Kotlin · Swift | config-driven generic lexical pass |
| any other language | add a `LangSpec` registry entry — no engine change |

Honest limits: attribute calls (`obj.m()`), macros, and cross-file symbols
are not analyzed; Ruby's paren-less calls are supported.

## Client-enforced hook mode

Skills persuade; **hooks enforce at the client boundary**. Register AgentSeed
as a Claude Code hook and every `Write`/`Edit`/`MultiEdit` is scanned
automatically — no prompt can skip it:

```bash
python3 server/guard_hook.py register --client claude   # idempotent, merges settings
python3 server/guard_hook.py --file path/to/source.py   # scan any file directly
```

- **PreToolUse** inspects the incoming content *before* it lands on disk; a
  blocking finding exits `2`, and the agent must fix the flagged lines.
- **PostToolUse** re-checks saved files on write paths without inline content.
- **Failure policy (honest):** infrastructure problems (bad stdin, unreadable
  files) never block work — fail-open; only positive scan findings block.

## Platform support

| Client | Status | Notes |
| --- | --- | --- |
| Claude Code | ✅ verified | skills + MCP + optional enforcement hook |
| opencode | ✅ verified | `~/.config/opencode/opencode.json` |
| Cursor | ⚪ spec-compatible* | copy into project; no stable plugin dir yet |
| VS Code (+Copilot) | ⚪ spec-compatible* | MCP support rolling out |
| Cline / Windsurf | ⚪ spec-compatible* | stdio server entry maps directly |

\* honest states: formats are spec-compatible and expected to work, but not yet
exercised by the maintainers. If you verify one, open a PR updating this table.

## Optional dependencies

```bash
pip install -r server/requirements.txt
```

| Extra | Upgrades | Without it |
| --- | --- | --- |
| `jsonschema` | `schema_validate` → full Draft 2020-12 | built-in subset validator |
| `pyflakes` | `verify_code` → pyflakes F821 analysis | built-in AST walk |
| `pyyaml` | SKILL.md frontmatter → full YAML | built-in lite parser |

## Configuration (`agentseed.config.json`)

| Key | Effect |
| --- | --- |
| `allowlist` | scan exclusions (replaces built-in test-idiom list) |
| `severities` | per-group severity override (`error` \| `warning` \| `info`) |
| `timeout` | default `sandbox_run` timeout, seconds (1–120) |
| `extra_tokens` | extend the hallucination word pool at runtime |
| `suppress_symbols` | names `verify_code` never flags (reported in `suppressed`) |
| `sandbox_allowed_prefixes` | **allowlist of executables** `sandbox_run` may launch; PATH-resolved, separator-boundary enforced (absent = unrestricted) |
| `sandbox_env` | `"inherit"` \| `"scrub"` — `scrub` drops credential-looking env vars |

Unknown keys are warned on stderr — a typo is never silently ignored.

> ⚠️ **Security note:** `sandbox_run` executes real processes with your user's
> permissions. Gate it behind user approval; set `sandbox_allowed_prefixes` in
> shared/CI environments. Commands resolve through `PATH` to absolute paths
> before execution, so a hostile `cwd` cannot shadow an allowlisted binary;
> unmatched commands are refused (exit -10) without running.

## Compatibility & graceful degradation

| Host capability | What you get |
| --- | --- |
| Full Agent Plugins | drop-in: skill + MCP auto-discovered, `${PLUGIN_DATA}` config honored |
| MCP-capable client | all 7 tools via registration |
| Skills-only client | skill workflow; verification degrades to `guard_cli.py` via shell |
| Plain terminal / CI | CLI gates with exit codes |

## Built-in guardrail library (EN / 中文 / 日本語)

`PROMPT-POOL` (20+ copy-paste guardrail prompts) · `HALLUCINATION-PATTERNS`
(5-class failure-mode catalog) · `VERIFICATION-CHECKLIST` (executable
end-of-task checklist) · `SDD-CONTRACT` (the contract every task must
satisfy) · `VENDOR-SOLUTIONS` (adoption map of vendor techniques).

## Why AgentSeed vs. alternatives

| | Prompt-only guardrail skills | Static import linters (MCP) | **AgentSeed** |
| --- | --- | --- | --- |
| Touches code | ❌ prompt only | ✅ import graphs | ✅ AST + lexical (12+ langs) |
| Runs verification tools | ❌ | lint gates | ✅ 7 MCP tools incl. sandbox |
| Hallucination-language scan | ❌ | ❌ | ✅ stub/oversold/fabricated, EN + CJK |
| Enforcement | soft (skill text) | CI gate | **hard**: skill + MCP + hook + CLI exit codes |
| 1.0.0 conformance linter | ❌ | ❌ | ✅ first |

## FAQ

**Does it need a specific LLM?** No — client-agnostic and model-agnostic; the
gate is enforced by skill + MCP + hooks + CI, not by any model.

**Zero dependencies?** Yes. The MCP server is pure Python standard library.

**Does it work with our existing AGENTS.md / CLAUDE.md?** Yes — it
complements them. Those files carry project facts (prose, persuasive);
AgentSeed carries the behavior contract and the hard enforcement.

**How do I extend it to another language?** Add a `LangSpec` registry entry in
`server/engine/symbols.py` — one config, no engine change.

## Contributing

Issues, PRs and ideas welcome — or open an issue for a hallucination pattern
we haven't catalogued yet. See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

Apache-2.0 © AgentSeed. See [LICENSE](./LICENSE).

---

<div align="center">

⭐ **If AgentSeed saved you from shipping hallucinated code, star the repo — it's the best signal that guardrails matter.**

</div>
