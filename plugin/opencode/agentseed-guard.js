// AgentSeed enforcement plugin for opencode.
// Installed by `python server/guard_hook.py register --client opencode`
// into ~/.config/opencode/plugin/. Blocks edit-tool calls whose incoming
// content trips the AgentSeed gates, before anything lands on disk.
// Protocol per opencode.ai/docs/plugins: throw inside tool.execute.before
// to block the call; the error text goes back to the model.
import { spawnSync } from "node:child_process"
import { existsSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

const EDIT_TOOLS = new Set(["edit", "write", "patch", "multiedit"])

function locateHook() {
  const candidates = []
  if (process.env.AGENTSEED_PLUGIN_ROOT) {
    candidates.push(join(process.env.AGENTSEED_PLUGIN_ROOT, "server", "guard_hook.py"))
  }
  candidates.push(join(homedir(), ".agentseed", "AgentSeed", "server", "guard_hook.py"))
  return candidates.find((p) => existsSync(p))
}

// A guard that silently never runs is worse than no guard: the model keeps
// reporting "verified" and nothing checks it. So resolve an interpreter that
// actually exists and make every bypass path visible.
const warned = new Set()
function warnOnce(key, message) {
  if (warned.has(key)) return
  warned.add(key)
  console.error(`[agentseed] ${message}`)
}

function interpreterCandidates() {
  if (process.env.PYTHON) return [process.env.PYTHON]
  const other = process.platform === "win32" ? "python3" : "python"
  const preferred = process.platform === "win32" ? "python" : "python3"
  return [preferred, other]
}

let resolvedPython = null
function locatePython() {
  if (resolvedPython) return resolvedPython
  for (const candidate of interpreterCandidates()) {
    const probe = spawnSync(candidate, ["--version"], { encoding: "utf8" })
    if (!probe.error && probe.status === 0) {
      resolvedPython = candidate
      return candidate
    }
  }
  return null
}

export const AgentSeedGuard = async () => {
  const hookPy = locateHook()
  if (!hookPy) {
    warnOnce(
      "hook",
      "guard_hook.py not found (set AGENTSEED_PLUGIN_ROOT or install the plugin) — " +
        "the enforcement hook is INACTIVE and edits will NOT be gated",
    )
  }
  const python = locatePython()
  if (hookPy && !python) {
    warnOnce(
      "python",
      `no working Python interpreter (${interpreterCandidates().join(", ")}) — ` +
        "the enforcement hook is INACTIVE and edits will NOT be gated",
    )
  }
  return {
    "tool.execute.before": async (input, output) => {
      if (!hookPy || !python) return // bypass already announced once on stderr
      const tool = String(input.tool || "").toLowerCase()
      const args = output.args || {}
      const hasEditShape =
        EDIT_TOOLS.has(tool) ||
        args.filePath != null ||
        args.file_path != null ||
        args.content != null ||
        args.newString != null ||
        args.new_string != null
      if (!hasEditShape) return
      const event = {
        hook_event_name: "PreToolUse",
        tool_name: tool,
        tool_input: {
          file_path: args.filePath ?? args.file_path ?? null,
          content: typeof args.content === "string" ? args.content : null,
          new_string:
            typeof args.newString === "string"
              ? args.newString
              : typeof args.new_string === "string"
                ? args.new_string
                : null,
        },
      }
      const res = spawnSync(python, [hookPy], {
        input: JSON.stringify(event),
        encoding: "utf8",
      })
      if (res.error || res.status === null) {
        warnOnce(
          "spawn",
          `guard_hook invocation failed (${res.error?.code ?? "killed"}) — this edit ` +
            "was NOT verified; the gate is failing open",
        )
        return
      }
      if (res.status === 2) {
        const reason = String(res.stderr || "").trim()
        throw new Error(reason || "blocked by agentseed")
      }
      // any other exit code (pass/skip/internal fail-open) lets the call proceed
    },
  }
}
