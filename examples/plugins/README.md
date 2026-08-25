# Example plugins — `check_plugin` teaching fixtures

Two minimal plugin directories used by the test suite and by humans learning
what the strict Agent Plugins 1.0.0 linter accepts and rejects.

## Try it

```bash
python server/guard_cli.py check examples/plugins/good-plugin    # exit 0
python server/guard_cli.py check examples/plugins/broken-plugin  # exit 1 + errors
```

## What each fixture demonstrates

| Fixture | Violations shown | `check_plugin` output |
| --- | --- | --- |
| `good-plugin/` | none — closed-schema `plugin.json`, skill dir name matches SKILL.md frontmatter `name` | `"ok": true` |
| `broken-plugin/` | manifest `name` violates §5.5 naming (`Broken-Demo`: uppercase), unknown top-level field `privateExtra` breaks the closed schema | errors listing both |

## Rules exercised

- **§5.2/§5.3** — root `plugin.json`, `$schema` address, closed top-level schema:
  only the spec's fields are accepted; anything else is an error.
- **§5.5** — `name` must be 1–64 chars of `[a-z0-9.-]`, start/end alphanumeric,
  no `--` or `..`.
- **§6.1/§7.1** — `skills/<dir>/SKILL.md` must exist and its frontmatter `name`
  must equal the directory name.

Add a new violation class? Pair it with a case in `server/test_features.py`
(`TestExampleFixtures`) proving the linter flags it.
