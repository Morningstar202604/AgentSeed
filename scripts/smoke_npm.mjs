#!/usr/bin/env node
/**
 * npm smoke test for agentseed-mcp.
 *
 * Exercises the *distribution* path that CI otherwise never runs: it locates
 * the `agentseed-mcp` bin shim (preferring the globally installed npm package,
 * falling back to the repo copy), spawns it exactly like an MCP client would,
 * and speaks line-delimited JSON-RPC 2.0 over stdio:
 *
 *   initialize -> notifications/initialized -> tools/list -> tools/call verify_code
 *
 * Assertions (any failure => non-zero exit with a clear message):
 *   - the server responds to every request;
 *   - tools/list returns exactly 8 tools, including `verify_code`;
 *   - verify_code reports an invented symbol as a suspect.
 *
 * Python detection is NOT duplicated here: we spawn the bin shim itself and
 * let it pick python/python3 (or $PYTHON) per platform, identical to real use.
 *
 * No npm dependencies; stdlib ESM only. Works on Windows and Linux.
 */

import { spawn, execSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const TIMEOUT_MS = 90_000;
const EXPECTED_TOOL_COUNT = 8;
const INVENTED_SYMBOL = "agentseedSmokeZzqInvented_91827";

const REPO_SHIM = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "bin",
  "cli.js",
);

function fail(message) {
  console.error(`[smoke-npm] FAIL: ${message}`);
  process.exitCode = 1;
  throw new Error(message);
}

/** Prefer the globally installed package (what CI verifies); else repo shim. */
function resolveShim() {
  let globalRoot = "";
  try {
    // Run through the shell so the `npm` .cmd wrapper is resolvable on Windows.
    globalRoot = execSync("npm root -g", { encoding: "utf8" }).trim();
  } catch {
    // npm not on PATH — fall back to the repo shim.
  }
  const installed = globalRoot
    ? path.join(globalRoot, "agentseed-mcp", "bin", "cli.js")
    : "";
  if (installed && existsSync(installed)) {
    console.log(`[smoke-npm] using globally installed shim: ${installed}`);
    return installed;
  }
  if (existsSync(REPO_SHIM)) {
    console.log(
      `[smoke-npm] NOTE: global agentseed-mcp not found; using repo shim: ${REPO_SHIM}`,
    );
    return REPO_SHIM;
  }
  fail("could not resolve the agentseed-mcp bin shim (no global install, no repo copy)");
}

async function main() {
  const shim = resolveShim();
  const child = spawn(process.execPath, [shim], {
    stdio: ["pipe", "pipe", "pipe"],
  });

  const pending = new Map(); // request id -> { resolve, reject, timer }
  let lineBuf = "";
  let stderrTail = "";
  const closeReasons = [];

  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    lineBuf += chunk;
    let nl;
    while ((nl = lineBuf.indexOf("\n")) >= 0) {
      const line = lineBuf.slice(0, nl).trim();
      lineBuf = lineBuf.slice(nl + 1);
      if (!line) continue;
      let msg;
      try {
        msg = JSON.parse(line);
      } catch {
        continue; // ignore non-JSON noise on stdout
      }
      const entry = msg.id !== undefined ? pending.get(msg.id) : undefined;
      if (entry) {
        clearTimeout(entry.timer);
        pending.delete(msg.id);
        entry.resolve(msg);
      }
    }
  });
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => {
    stderrTail = (stderrTail + chunk).slice(-4000);
  });
  child.on("exit", (code, signal) => {
    closeReasons.push(`bin exited code=${code} signal=${signal}`);
    for (const [id, entry] of pending) {
      clearTimeout(entry.timer);
      pending.delete(id);
      entry.reject(new Error(`bin died before replying (id=${id}; ${closeReasons.join("; ")})`));
    }
  });
  child.on("error", (err) => {
    closeReasons.push(`spawn error: ${err.message}`);
  });

  function request(id, payload) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`timeout (>${TIMEOUT_MS}ms) waiting for response id=${id}`)),
        TIMEOUT_MS,
      );
      pending.set(id, { resolve, reject, timer });
      child.stdin.write(JSON.stringify(payload) + "\n");
    });
  }

  try {
    // 1. initialize
    const init = await request(1, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2025-03-26",
        capabilities: {},
        clientInfo: { name: "smoke_npm", version: "0.0.0" },
      },
    });
    if (init.error) fail(`initialize returned an error: ${JSON.stringify(init.error)}`);
    if (!init.result || !init.result.serverInfo) {
      fail(`initialize response missing serverInfo: ${JSON.stringify(init)}`);
    }
    console.log(
      `[smoke-npm] initialize OK (server ${init.result.serverInfo.name}@${init.result.serverInfo.version}, protocol ${init.result.protocolVersion})`,
    );

    // 2. notifications/initialized (notification: no reply expected)
    child.stdin.write(
      JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n",
    );

    // 3. tools/list — exactly 8 tools, must include verify_code
    const list = await request(2, { jsonrpc: "2.0", id: 2, method: "tools/list" });
    if (list.error) fail(`tools/list returned an error: ${JSON.stringify(list.error)}`);
    const tools = list.result && list.result.tools;
    if (!Array.isArray(tools)) fail(`tools/list result.tools is not an array: ${JSON.stringify(list.result)}`);
    const names = tools.map((t) => t.name);
    if (tools.length !== EXPECTED_TOOL_COUNT) {
      fail(`expected exactly ${EXPECTED_TOOL_COUNT} tools, got ${tools.length}: ${names.join(", ")}`);
    }
    if (!names.includes("verify_code")) fail(`tools/list is missing verify_code: ${names.join(", ")}`);
    console.log(`[smoke-npm] tools/list OK (${tools.length} tools: ${names.join(", ")})`);

    // 4. tools/call verify_code on a source containing an invented symbol
    const source =
      "def agentseed_smoke_entry():\n" +
      `    return ${INVENTED_SYMBOL}(\"the question is the answer\")\n`;
    const call = await request(3, {
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: { name: "verify_code", arguments: { source, language: "python" } },
    });
    if (call.error) fail(`tools/call returned an error: ${JSON.stringify(call.error)}`);
    const content = call.result && call.result.content;
    if (!Array.isArray(content) || !content[0] || typeof content[0].text !== "string") {
      fail(`tools/call response has no text content: ${JSON.stringify(call.result)}`);
    }
    if (call.result.isError) fail(`tools/call reported isError: ${content[0].text}`);
    let verdict;
    try {
      verdict = JSON.parse(content[0].text);
    } catch {
      fail(`tools/call content is not valid JSON: ${content[0].text.slice(0, 300)}`);
    }
    if (!Array.isArray(verdict.suspects) || !verdict.suspects.includes(INVENTED_SYMBOL)) {
      fail(
        `verify_code did not report invented symbol ${INVENTED_SYMBOL}; got suspects=${JSON.stringify(verdict.suspects)}`,
      );
    }
    console.log(`[smoke-npm] tools/call verify_code OK (suspects: ${verdict.suspects.join(", ")})`);

    console.log("[smoke-npm] PASS: npm distribution path speaks MCP over stdio end-to-end");
  } finally {
    try {
      child.stdin.end(); // python read loop sees EOF and exits cleanly
    } catch {
      /* ignore */
    }
    if (child.exitCode === null && child.signalCode === null) {
      child.kill("SIGTERM"); // the child is terminated even on the failure path
      const hard = setTimeout(() => child.kill("SIGKILL"), 5_000);
      hard.unref();
    }
    if (stderrTail.trim()) {
      console.log(`[smoke-npm] child stderr tail:\n${stderrTail.trim()}`);
    }
  }
}

main().catch((err) => {
  console.error(`[smoke-npm] FAIL: ${err.message}`);
  process.exit(1);
});
