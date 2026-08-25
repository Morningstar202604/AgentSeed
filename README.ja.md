<div align="center">

# 🛡️ AgentSeed

**AI コーディングエージェント向け幻覚防止ガードレール。**

[Agent Plugins 1.0.0](https://agent-plugins.org) 準拠のハイブリッドプラグイン
（Skill + MCP サーバー）。仕様駆動開発を強制し、**コードが「完了」とマークされる前に
検証**します — "Done, all tests pass" を主張ではなく観測事実にします。

[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.1-blue)](https://gitcode.com/badhope/AgentSeed/releases)
[![Platforms](https://img.shields.io/badge/platform-Cursor%20%7C%20VS%20Code%20%7C%20Claude%20Code%20%7C%20Copilot-blue)](https://agent-plugins.org)

**日本語** · [English](./README.md) · [中文](./README.zh.md)

> 本リポジトリの**基準言語は英語**です（最も完全で最新）。日・中文版は主要内容の対訳です。

⭐ **役立つと思ったらスターをお願いします — 幻覚コードを出荷する前にガードレールを
知る開発者を増やすことができます。**

</div>

---

## なぜ AgentSeed なのか

LLM は幻覚します — コードでは**存在しない API、未定義の識別子、偽のテスト合格、
自信過剰な誇張主張**として現れます。データ：

- コード幻覚の **15.1%** は知識衝突型：存在しない・未インポートの API 呼び出し
  （[arXiv:2404.00971](https://arxiv.org/abs/2404.00971)）。
- 幻覚コードの **<10%** しかテストで検出されません — ほとんどが CI をすり抜けます（同上）。
- モデル出力エラーの **60%+** は**検証不能**（FAVA、[SoK](https://arxiv.org/abs/2502.18468) 引用）。

プロンプトのみのガードレールは「弱い」：モデルは検証に同意して、スキップできます。
**AgentSeed は指示をハードな MCP ゲートに縛ります** — 証拠はモデルの自己申告ではなく、
実行されたコードが生み出します。

1.0.0 仕様が意図的に残した 2 つの穴も埋めます：

| 仕様の穴 | AgentSeed の対応 |
| --- | --- |
| 強制メカニズムなし（スキルは任意） | `verify-before-code` を**スキップ不可**に |
| 公式 linter なし | `check_plugin` が**初の厳格 1.0.0 linter** |

## 機能

ゼロ依存の MCP ツール 6 つ：

| ツール | ブロックするもの | 技術 |
| --- | --- | --- |
| `verify_code` | 捏造 API / 未定義シンボル | Python AST + TS/JS 語彙パス |
| `scan_hallucination` | プレースホルダー、誇張、捏造 | 3 グループ 28+ シグナル |
| `check_plugin` | 不適合なプラグイン | 厳格 1.0.0 linter |
| `sandbox_run` | 実行せずに「テスト合格」 | 決定的実行チャネル |
| `schema_validate` | 不正な構造化出力 | JSON Schema 検証 |
| `record_verification` | 証跡の永続化欠如 | `PLUGIN_DATA` 配下の JSONL に監査エントリを追記 |

## ライブデモ

```
$ verify_code(source="def f():\n    return magic_unknown()\n", language="python")
{
  "language": "python",
  "suspects": ["magic_unknown"]      # ← 幻覚 API を検出
}

$ scan_hallucination(source="The feature is production ready, all tests pass. Trust me.")
{
  "hits": [
    {"word": "all tests pass", "group": "oversold", "line": 1},
    {"word": "production ready", "group": "oversold", "line": 1},
    {"word": "trust me", "group": "oversold", "line": 1}
  ],
  "clean": false                      # ← 誇張主張を検出
}

$ check_plugin(path="/path/to/AgentSeed")
{ "ok": true, "errors": [], "warnings": [] }   # ← 厳格 1.0.0 適合
```

## クイックスタート

**方法 A — リリースをダウンロード（git 不要）：**

```bash
# https://gitcode.com/badhope/AgentSeed/releases から最新アセットを取得、
# またはインストーラーで任意のクライアントへ配置：
bash install.sh --client auto        # macOS / Linux
./install.ps1 -Client auto           # Windows PowerShell
# --client: claude | opencode | cursor | manual
```

**方法 B — クローン：**

```bash
git clone https://gitcode.com/badhope/AgentSeed.git
# または：https://gitcode.com/badhope/AgentSeed · https://gitee.com/badhope/AgentSeed
```

1. `AgentSeed/` ディレクトリを Agent Plugins 1.0.0 対応クライアント（Cursor、VS Code、
   Claude Code、Copilot…）に置くだけ。ビルド不要・インストール不要。コアは依存ゼロ（オプションの拡張は下記）。
2. クライアントが `plugin.json` + `mcp.json` から `verify-before-code` スキルと
   `agentseed` MCP サーバーを自動検出します。
3. **完了。** 以降、すべてのコーディングタスクにゲートがかかります：
   契約 → 実装 → 検証 → 証拠。

スタンドアロンでの自己チェック：

```bash
python3 server/guard_engine.py              # 自己チェック: verify_code + scan_hallucination のデモ
python3 -m unittest discover -s server      # 90+ 個のユニットテスト（CI は pytest も併用）
```

同じルールを人間の PR にも（CI モード）：

```bash
python3 server/guard_cli.py gate --root .        # 複合ハードゲート：適合性+シンボル+ベースライン走査、失敗時 exit 1
python3 server/guard_cli.py check . --ci         # プラグイン適合性、エラー時 exit 1
python3 server/guard_cli.py scan src/ --strict   # 幻覚スキャン、ブロック重大度のみ
```

> **Windows の注意：** `mcp.json` は `python3` でサーバーを起動します。多くの Windows
> 環境ではこの別名が Microsoft Store のスタブです。サーバーが起動しない場合は
> `command` を `["python", "server/guard_server.py"]` またはインタープリターの絶対パスに
> 変更してください。

## オプション依存

AgentSeed は Python 標準ライブラリだけで動きます。以下をインストールすると、2 つの
ツールが業界標準エンジンにアップグレードされます（自動検出、未インストールでも
グレースフルフォールバック）：

```bash
pip install -r server/requirements.txt
```

| 拡張 | アップグレード先 | 未インストール時 |
| --- | --- | --- |
| `jsonschema` | `schema_validate` → Draft 2020-12 フル検証 | 内蔵サブセット検証 |
| `pyflakes` | `verify_code` → pyflakes F821 未定義名解析をマージ | 内蔵 AST ウォーク |
| `pyyaml` | SKILL.md frontmatter 解析 → フル YAML | 内蔵ライトパーサー |

> `guard_server.py` は絶対パスで指定してください。サーバーは自身の位置から残りを解決する
> ので、特別な cwd は不要です。

## 互換性とグレースフルデグラデーション

ホストの能力に応じて一段ずつ降級します——検証の静默スキップはしません：

| ホスト能力 | 得られるもの | セットアップ |
| --- | --- | --- |
| フル Agent Plugins | 置くだけ：skill + MCP 自動検出、`${PLUGIN_DATA}` 設定有効 | プラグインディレクトリをコピー |
| MCP 対応クライアント | 全 6 ツール（登録必要） | 下記の正確なスニペット |
| スキルのみのクライアント | skill ワークフロー；**検証は shell 経由の `guard_cli.py` に降級**（skill 内にフォールバック手順あり） | `skills/verify-before-code` をフラットコピー |
| 端末のみ / CI / エージェントなし | CLI ゲート + 終了コード | `python server/guard_cli.py check . --ci` |

## プラットフォーム対応

| クライアント | Agent Plugins 1.0.0 | 状態 | 備考 |
| --- | --- | --- | --- |
| Claude Code | skills + MCP config | verified | skills は `~/.claude/skills`、サーバーは `claude mcp add` |
| opencode | skills + MCP config | verified | `~/.config/opencode/opencode.json`、スニペットは下記 |
| Cursor | skills + mcp.json | untested* | プロジェクトにコピー；安定したプラグインディレクトリはまだ無し |
| VS Code (+Copilot) | MCP サポート展開中 | untested* | mcp.json フィールドをそのまま使用 |
| Cline / Windsurf | MCP config 互換 | untested* | stdio サーバーエントリがそのまま対応 |

\* 正直なステータス：形式は仕様互換で動作見込みですが、開発者自身では未検証です。
verified = メンテナーが実際に確認済み。検証したら PR でこの表を更新してください。

フルスペックのクライアントは `${PLUGIN_DATA}` も設定します。AgentSeed はそこから
`agentseed.config.json` を読みます。

### 設定リファレンス（`agentseed.config.json`）

| キー | 型 | 効果 |
| --- | --- | --- |
| `allowlist` | `string[]` | スキャン除外（内蔵テストイディオム一覧を置き換え） |
| `severities` | `{group: error\|warning\|info}` | グループ別重大度オーバーライド |
| `timeout` | `int` | `sandbox_run` の既定タイムアウト秒（1–120 にクランプ） |
| `extra_tokens` | `{group: string[]}` | 幻覚語彙プールを実行時に拡張 |
| `suppress_symbols` | `string[]` | `verify_code` が決してフラグしない名前（`suppressed` に表示） |
| `sandbox_allowed_prefixes` | `string[]` | `sandbox_run` が起動できる**実行ファイル許可リスト**（未設定 = 無制限）。パス区切りなしのエントリは PATH 解決後の basename と一致（`python` は `python.exe` も許容）；区切りありのエントリは解決後の絶対パスと一致またはそのディレクトリプレフィックス（区切り境界を強制） |
| `sandbox_env` | `"inherit"` \| `"scrub"` | 子プロセス環境ポリシー：`scrub` は起動前に認証情報っぽい変数名（TOKEN/SECRET/PASSWORD/API_KEY/…）を落とす —— ベストエフォートの拒否リストであり、セキュリティ境界ではない |

未知のキーは stderr に警告 —— タイプミスのキーが静黙に無視されることはありません。

### 言語カバレッジ（正直な範囲）

| 言語 | `verify_code` 解析 |
| --- | --- |
| Python | フル AST スコープウォーク（pyflakes インストール時はマージ）、行番号付き |
| TypeScript / JavaScript | 語彙正規表現パス（誤検出クラスを明記） |
| Go / Java / Rust / C/C++ / その他 | **未対応** —— 空結果を返す |

> ⚠️ **セキュリティ注記**：`sandbox_run` はあなたのユーザー権限で実際のプロセスを実行します。
> クライアントは必ずユーザー承認のゲートを置いてください；共有/CI 環境では
> `sandbox_allowed_prefixes` を設定してください。許可リスト設定時、コマンドは実行前に
> `PATH` 経由で絶対パスへ解決されます —— 悪意ある作業ディレクトリが同名の実行ファイルを
> 置いて許可リスト項目になりすますことはできず、不一致・未解決のコマンドは実行せず拒否
> （exit -10）されます。

## 変更履歴

[CHANGELOG.md](./CHANGELOG.md) を参照。

## クライアント設定（正確なスニペット）

AgentSeed は二つの要素で構成され、完全なゲートには両方が必要です：

1. **スキル**（`skills/verify-before-code/`）— エージェントにワークフローを教える。
2. **MCP サーバー**（`server/guard_server.py`）— 6 ツールを提供。

インストーラーが 1 を配置し、2 の登録手順を表示します。手動設定：

**Claude Code**

```bash
# スキル：フラットにコピー（SKILL.md が直接フォルダ直下に）
cp -R skills/verify-before-code ~/.claude/skills/verify-before-code
# MCP サーバー：
claude mcp add agentseed -- python /path/to/AgentSeed/server/guard_server.py
```

**opencode** — `skills/verify-before-code/` を
`~/.config/opencode/skill/verify-before-code` にコピーし、`opencode.json` に追加：

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

**Cursor / その他の MCP クライアント** — stdio サーバーを登録：
`command: python`、`args: ["/path/to/AgentSeed/server/guard_server.py"]`、
スキルフォルダは各クライアントの技能場所へフラットコピー。

> `guard_server.py` は絶対パスで指定してください。サーバーは自身の位置から残りを解決する
> ので、特別な cwd は不要です。

## 内蔵ガードレールライブラリ（日本語 / EN / 中文）

| リソース | 内容 |
| --- | --- |
| `PROMPT-POOL` | 20+ のコピペ用プロンプト：完了証拠、先検証、不確実性、API 検証、引用規則 |
| `HALLUCINATION-PATTERNS` | 失敗モードカタログ：5 分類法 + SoK 知見 + 実在の法律/対話事例 |
| `VERIFICATION-CHECKLIST` | 実行可能チェックリスト：リスク分類 → 契約 → 証拠 → 言語監査 |
| `SDD-CONTRACT` | すべてのタスクが満たすべき契約 |
| `VENDOR-SOLUTIONS` | ベンダー技術導入マップ（Anthropic、OpenAI、AWS、NVIDIA、IBM、Guardrails AI、Vectara） |

## ゲートの仕組み

1. **コーディング前** — SDD 契約を読み、1 文で述べる。
2. **実装** — 実コードのみ：プレースホルダー・API 捏造禁止。
3. **「完了」の前** — `verify_code` + `scan_hallucination` を呼ぶ；実行主張は
   `sandbox_run` で実証；構造は `schema_validate` で検証。
4. **言語監査** — 完了報告に証拠添付；誇大語彙は禁止。
5. 全チェック通過時のみ完了とみなす。

## 強制される規範（AI の制約方法）

スキルは単なる「提案」ではありません —— 各規範は観測可能なゲートに対応します
（完全な表は
[`DEFAULT-NORMS.md`](./skills/verify-before-code/references/DEFAULT-NORMS.md)。
出典は AGENTS.md オープン標準、Anthropic Claude Code 公式ベストプラクティス、
FerroxLabs/agents-md 等のコミュニティ規律。違いはそこでは散文であり、ここでは
各規範に実行ツールか終了コードが伴うこと）：

| 規範 | 実行者 |
| --- | --- |
| 契約を先に、コードは後 | Gate 1 |
| API の捏造・未定義シンボル禁止 | `verify_code` |
| プレースホルダー禁止、実装のみ | `scan_hallucination` |
| 主張の前に検証 | Gate 3 + `sandbox_run` |
| 完了報告には証拠を添付 | Gate 4 + `record_verification` |

## エージェント設定ファイルとの共存

AgentSeed は既存の AI 設定ファイル（`CLAUDE.md` / `AGENTS.md` / `.cursor/rules/` /
`.github/copilot-instructions.md`）を置き換えず補完します：それらは**プロジェクトの
事実**（スタック・コマンド・構成）を担う「軟らかな」散文。AgentSeed は**行動契約と
強制力** —— 幻覚検出・検証ゲート・証拠チェーンという、静かに無視できないハードな
MCP ツールと CI 終了コードを担います。

## 比較

| | プロンプト専用 skill（superpowers…） | 静的 import linter | **AgentSeed** |
| --- | --- | --- | --- |
| コードに触れる | ❌ プロンプトのみ | ✅ import グラフ解析 | ✅ AST + 語彙解析 |
| 検証ツール実行 | ❌ | lint ゲート | ✅ sandbox 込み 6 種 MCP ツール |
| 幻覚言語スキャン | ❌ | ❌ | ✅ stub / 誇大 / 捏造信号（EN + CJK） |
| 強制 | 弱い（skill 文章） | CI ゲート | **ハードゲート**：skill + MCP + CLI 終了コード |
| 1.0.0 linter | ❌ | ❌ | ✅ 初 |

## ロードマップ

- [x] ハイブリッド Skill + MCP、6 ツール — 初の厳格 1.0.0 linter
- [x] プロンプトプール + パターンライブラリ + グループ信号 + ベンダー技術
- [x] `verify_code` を TypeScript / JavaScript に拡張（ゼロ依存語彙パス）
- [ ] `verify_code` を Go に拡張
- [ ] 構造化出力の文法制約付きデコーディング
- [ ] 任意のリモートファクトチェッカー（HHEM 型）MCP サーバー

## FAQ

**特定の LLM が必要ですか？** いいえ — クライアント・モデル非依存。ゲートはスキル +
MCP サーバーが強制し、モデルには依存しません。

**ゼロ依存？** コアは依存ゼロです — 何もインストールせずに完全動作します。server/requirements.txt（jsonschema / pyflakes / pyyaml）を入れると schema_validate が Draft 2020-12 フル検証に、verify_code が pyflakes F821 分析のマージに、frontmatter 解析がフル YAML にアップグレードされます（未インストール時は内蔵実装へ自動フォールバック）。

**適合していますか？** `check_plugin` が 1.0.0 §5/§6/§7 に照らして検証 — AgentSeed は
自身の linter を通過します（`ok: true`）。

## コントリビュート

Issue・PR・アイデア歓迎。方向性は[ロードマップ](#ロードマップ)を参照 —
未収録の幻覚パターンを見つけたら Issue を開いてください。

## ライセンス

Apache-2.0 © AgentSeed。[LICENSE](./LICENSE) を参照。

---

<div align="center">

⭐ **AgentSeed が幻覚コードの出荷を防いだなら、スターをお願いします — ガードレールが
重要だという最良のシグナルです。**

</div>
