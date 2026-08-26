<div align="center">

# 🛡️ AgentSeed

**面向 AI 编程智能体的防幻觉护栏。**

基于 [Agent Plugins 1.0.0](https://agent-plugins.org) 规范的混合插件（Skill + MCP 服务器）：强制规范驱动开发，**在代码被标记为"完成"之前先验证**——让 "Done, all tests pass" 变成可观测的事实，而不是一句空话。

[![License](https://img.shields.io/badge/license-Apache_2.0-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.2.0-blue)](https://gitcode.com/badhope/AgentSeed/releases)
[![CI](https://github.com/Morningstar202604/AgentSeed/actions/workflows/ci.yml/badge.svg)](https://github.com/Morningstar202604/AgentSeed/actions/workflows/ci.yml)
[![Platforms](https://img.shields.io/badge/platform-Cursor%20%7C%20VS%20Code%20%7C%20Claude%20Code%20%7C%20Copilot-blue)](https://agent-plugins.org)

**中文** · [English](./README.md) · [日本語](./README.ja.md)

> 本仓库以**英文版为准则**（内容最全、更新最快）；中/日文为核心内容的对照版本。

⭐ **觉得有用？点个 star 支持一下——帮助更多开发者在上线幻觉代码之前装上护栏。**

</div>

---

## 为什么需要 AgentSeed

大模型会幻觉——落到代码里就是**编造 API、未定义的标识符、假测试通过、自信的夸大声称**。数据说话：

- **15.1%** 的代码幻觉是知识冲突型：调用不存在的 API 或从未导入的 API（[arXiv:2404.00971](https://arxiv.org/abs/2404.00971)）。
- **<10%** 的幻觉代码会在测试中失败——大部分能溜过 CI（同上）。
- **60%+** 的模型输出错误**无法验证**——分不清事实与虚构（FAVA，见 [SoK](https://arxiv.org/abs/2502.18468)）。

纯 prompt 的护栏是"软"的：模型可以口头答应"完成前验证"，然后偷偷跳过。**AgentSeed 把指令和硬的 MCP 闸门绑死**——证据来自真实运行的代码，而不是模型的自我陈述。

它还填补了 1.0.0 规范故意留下的两个缺口：

| 规范缺口 | AgentSeed 的做法 |
| --- | --- |
| 无强制执行机制（skill 可被跳过） | `verify-before-code` 技能把验证做成**不可跳过** |
| 无官方一致性 linter | `check_plugin` 是**第一个严格 1.0.0 linter** |

## 它能做什么

六个 MCP 工具——零*必需*依赖，可选增强：

| 工具 | 拦截什么 | 技术 |
| --- | --- | --- |
| `verify_code` | 编造的 API / 未定义符号 | Python AST + TS/JS 词法分析 |
| `scan_hallucination` | 占位代码、夸大声称、虚构内容 | 3 组 28+ 信号 |
| `check_plugin` | 不合规的插件打包 | 严格 1.0.0 linter |
| `sandbox_run` | 什么都没跑就说"测试通过" | 确定性执行通道 |
| `schema_validate` | 不合法的结构化输出 | JSON Schema 校验 |
| `record_verification` | 没有持久化证据链 | 向 `PLUGIN_DATA` 下的 JSONL 追加一条审计记录 |

## 实机演示

```
$ verify_code(source="def f():\n    return magic_unknown()\n", language="python")
{
  "language": "python",
  "suspects": ["magic_unknown"]      # ← 幻觉 API 被抓
}

$ scan_hallucination(source="The feature is production ready, all tests pass. Trust me.")
{
  "hits": [
    {"word": "all tests pass", "group": "oversold", "line": 1},
    {"word": "production ready", "group": "oversold", "line": 1},
    {"word": "trust me", "group": "oversold", "line": 1}
  ],
  "clean": false                      # ← 夸大声称被抓
}

$ check_plugin(path="/path/to/AgentSeed")
{ "ok": true, "errors": [], "warnings": [] }   # ← 严格合规
```

## 快速开始

**方式一 —— 下载 release（无需 git）：**

```bash
# 从 https://gitcode.com/badhope/AgentSeed/releases 获取最新资产，
# 或用安装器直接装入你选择的客户端：
bash install.sh --client auto        # macOS / Linux
./install.ps1 -Client auto           # Windows PowerShell
# --client: claude | opencode | cursor | manual
# 追加 --hooks / -Hooks 可同时注册 Claude Code 强制钩子
```

**方式二 —— 克隆：**

```bash
git clone https://gitcode.com/badhope/AgentSeed.git
# 或：https://gitcode.com/badhope/AgentSeed · https://gitee.com/badhope/AgentSeed
```

1. **把** `AgentSeed/` 目录丢进任何支持 Agent Plugins 的客户端（Cursor、VS Code、Claude Code、Copilot……）。无需构建、无需安装；核心零依赖（可选增强见下文）。
2. 客户端从 `plugin.json` + `mcp.json` 自动发现 `verify-before-code` 技能和 `agentseed` MCP 服务器。
3. **完事。** 技能从此给每个编程任务上锁：契约 → 实现 → 验证 → 证据。

想独立自测：

```bash
python3 server/guard_engine.py              # 自检：演示 verify_code + scan_hallucination
python3 -m unittest discover -s server      # 90+ 个单元测试（CI 中亦用 pytest）
```

用同一套规则给人类 PR 上闸门（CI 模式）：

```bash
python3 server/guard_cli.py gate --root .        # 复合硬闸门：合规+符号+基线扫描，任一失败退出码 1
python3 server/guard_cli.py check . --ci         # 插件合规检查，出错退出码 1
python3 server/guard_cli.py scan src/ --strict   # 幻觉扫描，仅阻断级严重度
```

> **Windows 提示：** `mcp.json` 通过 `python3` 启动服务器。很多 Windows 环境下该别名是
> Microsoft Store 占位符；若服务器无法启动，请把 `command` 改为
> `["python", "server/guard_server.py"]` 或解释器的绝对路径。

## 客户端强制钩子（Claude Code）

技能负责说服；钩子在客户端边界上强制执行。把 AgentSeed 注册为 Claude Code 钩子后，
每次 `Write`/`Edit`/`MultiEdit` 工具调用都会被自动扫描——任何提示词都无法绕过：

```bash
python3 server/guard_hook.py register --client claude   # 合并写入 ~/.claude/settings.json，幂等可重跑
python3 server/guard_hook.py --file path/to/source.py   # 直接扫描任意文件
```

- **PreToolUse** 在内容落盘*之前*检查传入的 `content`/`new_string`；出现阻断级命中即以退出码 `2`
  结束，Claude 会通过 stderr 收到原因，必须先修复被标记的行，文件才写得进去。
- **PostToolUse** 对没有内联内容的写路径，落盘后再复查一次。
- **失败策略（如实说明）：** 基础设施问题——stdin 格式非法、文件不可读、未知工具结构——绝不阻塞
  编辑（fail-open）；只有真实扫描命中才会阻断。warning 级信号会报告但不阻断。
- 严重度 / 白名单 / 抑制符号调优与插件其他部分共用同一份 `agentseed.config.json`。

不想跑 register 命令的话，也可以手工往 settings.json 里加：

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

安装器加 `--hooks`（bash）/ `-Hooks`（PowerShell）即可自动完成上述注册。

## 可选依赖

AgentSeed 仅靠 Python 标准库即可运行。安装以下增强后，两个工具会升级为工业级引擎
（自动探测，未安装则优雅回退，反之亦然）：

```bash
pip install -r server/requirements.txt
```

| 增强包 | 升级效果 | 未安装时 |
| --- | --- | --- |
| `jsonschema` | `schema_validate` → 完整 Draft 2020-12 校验 | 内置子集校验器 |
| `pyflakes` | `verify_code` → 合并 pyflakes F821 未定义名分析 | 内置 AST 遍历 |
| `pyyaml` | SKILL.md frontmatter 解析 → 完整 YAML | 内置轻量解析器 |

> 请使用 `guard_server.py` 的绝对路径；服务器会从自身位置解析其余文件，无需特殊 cwd。

## 兼容性与优雅降级

AgentSeed 适配宿主环境的实际能力，逐级降级——绝不静默跳过验证：

| 宿主能力 | 你得到什么 | 安装方式 |
| --- | --- | --- |
| 完整 Agent Plugins | 即插即用：skill + MCP 自动发现，`${PLUGIN_DATA}` 配置生效 | 拷贝插件目录 |
| 支持 MCP 的客户端 | 全部 6 个工具（需注册） | 见下方确切片段 |
| 仅技能的客户端 | skill 工作流；**验证降级为 shell 调用 `guard_cli.py`**（技能内含回退指引） | 平铺拷贝 `skills/verify-before-code` |
| 纯终端 / CI / 无智能体 | CLI 闸门 + 退出码 | `python server/guard_cli.py check . --ci` |

## 平台支持

| 客户端 | Agent Plugins 1.0.0 | 状态 | 说明 |
| --- | --- | --- | --- |
| Claude Code | skills + MCP config | verified | skills 放 `~/.claude/skills`，服务器走 `claude mcp add`；可选强制钩子用 `guard_hook.py register --client claude` |
| opencode | skills + MCP config | verified | `~/.config/opencode/opencode.json`，确切片段见下 |
| Cursor | skills + mcp.json | untested* | 拷入项目即可；暂无稳定插件目录 |
| VS Code (+Copilot) | MCP 支持逐步推出 | untested* | 直接使用 mcp.json 字段 |
| Cline / Windsurf | MCP config 兼容 | untested* | stdio 服务器条目可直接映射 |

\* 诚实标注：格式兼容、预期可用，但我们没有亲自在这些客户端里跑过。verified = 维护者
实际验证过。你验证了一个？请提 PR 更新此表。

支持完整规范的客户端还会设置 `${PLUGIN_DATA}`；AgentSeed 从那里读取
`agentseed.config.json`。

### 配置参考（`agentseed.config.json`）

| 键 | 类型 | 作用 |
| --- | --- | --- |
| `allowlist` | `string[]` | 扫描排除项（替换内置测试惯用语列表） |
| `severities` | `{group: error\|warning\|info}` | 按组覆盖严重度 |
| `timeout` | `int` | `sandbox_run` 默认超时秒数（钳制 1–120） |
| `extra_tokens` | `{group: string[]}` | 运行时扩展幻觉词池 |
| `suppress_symbols` | `string[]` | `verify_code` 永不标记的名字（在 `suppressed` 中可见） |
| `sandbox_allowed_prefixes` | `string[]` | **可执行文件白名单**，`sandbox_run` 只允许启动清单内命令（缺省 = 不限制）。不带路径分隔符的条目按 PATH 解析后的 basename 匹配（`python` 也接受 `python.exe`）；带分隔符的条目必须与解析后的绝对路径相等或为其目录前缀（强制分隔符边界） |
| `sandbox_env` | `"inherit"` \| `"scrub"` | 子进程环境策略：`scrub` 在启动前剔除形似凭据的变量名（TOKEN/SECRET/PASSWORD/API_KEY/…）——尽力而为的黑名单，不是安全边界 |

未知键会在 stderr 上告警——拼错的键永远不会被静默忽略。

### 语言覆盖（诚实范围）

| 语言 | `verify_code` 分析 |
| --- | --- |
| Python | 完整 AST 作用域遍历（装了 pyflakes 则合并其结果），带行号 |
| TypeScript / JavaScript | 词法正则扫描（有明确记录的误报类别） |
| Go / Java / Rust / C/C++ / 其他 | **尚未支持** —— 返回空结果 |

> ⚠️ **安全提示**：`sandbox_run` 以你的用户权限执行真实进程。客户端必须将其置于用户
> 批准之后；共享/CI 环境请设置 `sandbox_allowed_prefixes`。配置白名单后，命令会先经
> `PATH` 解析为绝对路径再执行——恶意工作目录无法用植入的同名可执行文件冒充白名单条目，
> 未匹配/无法解析的命令会被拒绝（退出码 -10），不会运行。

## 更新日志

见 [CHANGELOG.md](./CHANGELOG.md)。

## 客户端配置（确切片段）

AgentSeed 有两半，完整闸门两者都要装：

1. **技能**（`skills/verify-before-code/`）—— 教会智能体工作流。
2. **MCP 服务器**（`server/guard_server.py`）—— 提供 6 个工具。

安装器负责第 1 步并为你所用客户端打印第 2 步。手动配置：

**Claude Code**

```bash
# 技能：平铺拷贝，SKILL.md 直接位于目录下
cp -R skills/verify-before-code ~/.claude/skills/verify-before-code
# MCP 服务器：
claude mcp add agentseed -- python /path/to/AgentSeed/server/guard_server.py
```

**opencode** —— 把 `skills/verify-before-code/` 拷到
`~/.config/opencode/skill/verify-before-code`，然后在 `opencode.json` 加入：

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

**Cursor / 其他 MCP 客户端** —— 注册 stdio 服务器：
`command: python`、`args: ["/path/to/AgentSeed/server/guard_server.py"]`，
并按你客户端的技能目录平铺拷贝技能文件夹。

> 请使用 `guard_server.py` 的绝对路径；服务器会从自身位置解析其余文件，无需特殊 cwd。

## 内置护栏库（中 / EN / 日本語）

| 资源 | 内容 |
| --- | --- |
| `PROMPT-POOL` | 20+ 条即用型护栏提示词：完成证据、先验证后声称、不确定性、API 验证、引用规则等 |
| `HALLUCINATION-PATTERNS` | 失效模式目录：五类代码幻觉分类法 + SoK 结论 + 真实法律/对话案例 |
| `VERIFICATION-CHECKLIST` | 任务收尾可执行清单：风险分级 → 契约 → 证据 → 语言审查 |
| `SDD-CONTRACT` | 每个编程任务必须满足的契约 |
| `VENDOR-SOLUTIONS` | 厂商方案引进地图（Anthropic、OpenAI、AWS、NVIDIA、IBM、Guardrails AI、Vectara） |

## 闸门如何工作

1. **写码前** —— 加载 SDD 契约，一句话陈述。
2. **实现** —— 只写真实代码：不用占位符、不编造 API。
3. **宣称完成前** —— 调用 `verify_code` + `scan_hallucination`；运行时声明用 `sandbox_run` 实证；结构用 `schema_validate` 校验。
4. **语言审查** —— 完成报告附证据；夸大词汇禁用。
5. 只有**全部检查通过**才能标记完成。

## 强制规范（AI 是如何被约束的）

技能不只是"建议"——每条规范都映射到一个可观测的门禁（完整表见
[`DEFAULT-NORMS.md`](./skills/verify-before-code/references/DEFAULT-NORMS.md)，
其来源综合自 AGENTS.md 开放标准、Anthropic Claude Code 官方最佳实践与
FerroxLabs/agents-md 等社区纪律；区别在于：**那里是散文，这里每条都有执行工具或退出码**）：

| 规范 | 执行者 |
| --- | --- |
| 先契约后写码 | Gate 1 |
| 不编造 API / 未定义符号 | `verify_code` |
| 只写真实现，无占位 | `scan_hallucination` |
| 先验证后声称完成 | Gate 3 + `sandbox_run` |
| 完成报告必须附证据 | Gate 4 + `record_verification` |

## 与你的智能体配置文件共存

AgentSeed 与团队已有的 AI 配置文件（`CLAUDE.md` / `AGENTS.md` / `.cursor/rules/` /
`.github/copilot-instructions.md`）互补而非替代：那些文件承载**项目事实**
（技术栈、命令、目录），是"软"的散文；AgentSeed 承载**行为契约与强制力**——
幻觉检测、验证门禁、证据链，是无法被静默降权的硬工具与 CI 退出码。

## 对比

| | 纯 prompt 技能（superpowers…） | 静态 import 检查器 | **AgentSeed** |
| --- | --- | --- | --- |
| 碰代码 | ❌ 仅 prompt | ✅ import 图分析 | ✅ AST + 词法分析 |
| 跑验证工具 | ❌ | lint 门禁 | ✅ 含沙箱共 6 个 MCP 工具 |
| 幻觉语言扫描 | ❌ | ❌ | ✅ 占位/夸大/编造信号（中英日） |
| 强制 | 软（skill 文本） | CI 门禁 | **硬闸门**：skill + MCP + CLI 退出码 |
| 1.0.0 linter | ❌ | ❌ | ✅ 首个 |

## 路线图

- [x] 混合 Skill + MCP 护栏，6 个工具 —— 首个严格 1.0.0 linter
- [x] 提示池 + 模式库 + 分组信号 + 厂商技术引进
- [x] `verify_code` 支持 TypeScript / JavaScript（零依赖词法分析）
- [ ] `verify_code` 支持 Go
- [ ] 结构化输出的语法约束解码
- [ ] 可选远程事实检查器（HHEM 风格）MCP 服务器

## 常见问题

**需要特定的大模型吗？** 不需要——与客户端、模型无关。闸门由 skill + MCP 服务器强制，不依赖任何模型。

**零依赖？** 核心零依赖——不装任何包也能完整运行。可选安装 `server/requirements.txt`（jsonschema / pyflakes / pyyaml）后，`schema_validate` 升级为完整 Draft 2020-12 校验、`verify_code` 获得 pyflakes 分析、frontmatter 解析支持完整 YAML；未安装时自动回退到内置实现。

**符合规范吗？** `check_plugin` 按规范 §5/§6/§7 校验插件——而 AgentSeed 通过了它自己的 linter（`ok: true`）。

## 贡献

欢迎 Issue、PR 和点子。方向见[路线图](#路线图)——如果你发现了我们还没收录的幻觉模式，开个 Issue。

## 许可证

Apache-2.0 © AgentSeed。见 [LICENSE](./LICENSE)。

---

<div align="center">

⭐ **如果 AgentSeed 帮你拦住了幻觉代码，给个 star 吧——这是"护栏有用"最好的信号。**

</div>
