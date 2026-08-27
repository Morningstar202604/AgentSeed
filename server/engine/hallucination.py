"""AgentSeed hallucination word scanning.

Flags tokens across three signal groups:
  - stub_code:     stub/mock/fake/placeholder/dummy/todo/...
  - oversold:      guaranteed/"all tests pass"/"production ready"/...
  - fabricated:    simulated/invented/fabricated/...
"""

from __future__ import annotations

import re

from .config import _VALID_SEVERITIES

# ---------------------------------------------------------------------------
# Hallucination token pools (grouped by signal type).
# ---------------------------------------------------------------------------

STUB_TOKENS = [
    "stub",
    "mock",
    "fake",
    "placeholder",
    "dummy",
    "todo",
    "fixme",
    "xxx",
    "tbd",
    "tba",
    "wip",
    "not implemented",
    "coming soon",
    "to be implemented",
    "not implemented yet",
    "pending implementation",
]

# CJK tokens: \b word boundaries are meaningless between CJK chars, so these
# are matched as substrings (they are specific enough to stay low-noise).
STUB_TOKENS_ZH = [
    "占位",
    "待实现",
    "未实现",
    "待补充",
    "稍后补",
    "假数据",
    "模拟数据",
    "临时方案",
    "先这样",
    "待完成",
    "尚未实现",
]

OVERSOLD_TOKENS = [
    "guaranteed",
    "definitely works",
    "all tests pass",
    "everything works",
    "fully tested",
    "production ready",
    "no bugs",
    "works perfectly",
    "should work",
    "trust me",
    "works on my machine",
    "100% correct",
    "bug free",
    "zero errors",
    "foolproof",
    "bulletproof",
    "cannot fail",
    "guaranteed to pass",
    "impossible to break",
]

OVERSOLD_TOKENS_ZH = [
    "保证通过",
    "绝对没问题",
    "肯定能跑",
    "万无一失",
    "完美运行",
    "零缺陷",
    "无需测试",
    "包过",
    "绝无问题",
    "不可能失败",
    "绝对可靠",
    "稳过",
]

FABRICATED_TOKENS = [
    "simulated",
    "invented",
    "fabricated",
    "fictional",
    "pretend",
    "made up",
    "fictitious",
    "nonexistent",
    "non-existent",
    "mythical",
]

FABRICATED_TOKENS_ZH = [
    "虚构",
    "编造",
    "凭空捏造",
    "子虚乌有",
]

# Full pool: token -> group (kept for backward compatibility).
HALLUCINATION_WORDS: dict[str, str] = {}
for _tokens, _group in [
    (STUB_TOKENS + STUB_TOKENS_ZH, "stub_code"),
    (OVERSOLD_TOKENS + OVERSOLD_TOKENS_ZH, "oversold"),
    (FABRICATED_TOKENS + FABRICATED_TOKENS_ZH, "fabricated"),
]:
    for _t in _tokens:
        HALLUCINATION_WORDS[_t] = _group

_GROUP_LABELS = {
    "stub_code": "placeholder / not-really-done code",
    "oversold": "unverified confidence claim",
    "fabricated": "fabricated / invented content",
}

# Tokens that are legitimate in common testing/idiomatic contexts.
DEFAULT_ALLOWLIST = [
    "unittest.mock",
    "Mock(",
    "MagicMock(",
    "AsyncMock(",
    "PropertyMock(",
    "patch(",
    "monkeypatch",
    "mocker",
]

_IMPORT_LINE_RE = re.compile(r"^\s*(?:from\s+[\w.]+\s+import\b|import\s+\w)", re.IGNORECASE)

# Default severity per signal group.
DEFAULT_SEVERITIES: dict[str, str] = {
    "stub_code": "warning",
    "oversold": "error",
    "fabricated": "error",
}

# ---------------------------------------------------------------------------
# Precompiled regex patterns (one per group, compiled once at import time).
# ASCII tokens use \b word boundaries; CJK tokens are substring matches
# (\b never fires between two CJK chars, so boundaries would miss 占位符 etc).
# ---------------------------------------------------------------------------

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def _compile_group(tokens: list[str]) -> re.Pattern:
    ascii_alts = [re.escape(t).replace(r"\ ", r"\s+") for t in tokens if not _CJK_RE.search(t)]
    cjk_alts = [re.escape(t) for t in tokens if _CJK_RE.search(t)]
    parts = []
    if ascii_alts:
        parts.append(rf"\b(?:{'|'.join(ascii_alts)})\b")
    if cjk_alts:
        parts.append("|".join(cjk_alts))
    return re.compile("(?:" + "|".join(parts) + ")", re.IGNORECASE)


_HALLUCINATION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_compile_group(STUB_TOKENS + STUB_TOKENS_ZH), "stub_code"),
    (_compile_group(OVERSOLD_TOKENS + OVERSOLD_TOKENS_ZH), "oversold"),
    (_compile_group(FABRICATED_TOKENS + FABRICATED_TOKENS_ZH), "fabricated"),
]


def scan_hallucination_words(
    source: str,
    allowlist: list[str] | None = None,
    severities: dict[str, str] | None = None,
    extra_tokens: dict[str, list[str]] | None = None,
) -> dict:
    """Scan source for tokens in the grouped hallucination pool.

    To avoid flagging legitimate code, matches are skipped when:
      - the line is an import statement;
      - the match is part of a dotted path (``unittest.mock``, ``os.path``);
      - the matched text starts with an entry of the effective allowlist.

    ``extra_tokens`` extends the pool at runtime (config: ``extra_tokens``
    mapping group -> [words]); unknown groups are ignored.

    Each hit carries a severity (``error`` | ``warning`` | ``info``) taken
    from ``severities`` (group -> severity), falling back to
    DEFAULT_SEVERITIES.

    Returns:
        {
          "hits": [{"word": "stub", "group": "stub_code", "line": 12,
                    "severity": "warning"}, ...],
          "clean": bool,
          "blocking": bool,
          "groups": {"stub_code": 2, "oversold": 1, "fabricated": 0},
          "severities": {"error": 1, "warning": 2, "info": 0}
        }
    """
    if allowlist is None:
        allowlist = DEFAULT_ALLOWLIST
    elif isinstance(allowlist, str):
        # MCP clients sometimes send a bare string instead of a list; a raw
        # string would iterate characters and silently suppress every match.
        allowlist = [allowlist]
    elif not isinstance(allowlist, list):
        allowlist = (
            [a for a in allowlist if isinstance(a, str)] if hasattr(allowlist, "__iter__") else []
        )
    allowlist = [a for a in allowlist if isinstance(a, str) and a]
    sev = dict(DEFAULT_SEVERITIES)
    if severities:
        for g, s in severities.items():
            if g in _GROUP_LABELS and s in _VALID_SEVERITIES:
                sev[g] = s
    patterns = list(_HALLUCINATION_PATTERNS)
    if extra_tokens:
        for g, words in extra_tokens.items():
            if g in _GROUP_LABELS and isinstance(words, list):
                words = [w for w in words if isinstance(w, str) and w]
                if words:
                    patterns.append((_compile_group(words), g))
    hits: list[dict] = []
    group_counts: dict[str, int] = {g: 0 for g in _GROUP_LABELS}
    severity_counts: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for i, line in enumerate(source.splitlines(), start=1):
        if _IMPORT_LINE_RE.match(line):
            continue
        for pattern, group in patterns:
            for m in pattern.finditer(line):
                before = line[max(0, m.start() - 1) : m.start()]
                after = line[m.end() : m.end() + 1]
                if before == "." or after == ".":
                    continue  # part of a dotted path (module/attribute)
                rest = line[m.start() :]
                if any(rest.lower().startswith(a.lower()) for a in allowlist):
                    continue
                word = m.group(0).lower()
                severity = sev.get(group, "warning")
                hits.append({"word": word, "group": group, "line": i, "severity": severity})
                group_counts[group] += 1
                severity_counts[severity] += 1
    return {
        "hits": hits,
        "clean": len(hits) == 0,
        "blocking": severity_counts["error"] > 0,
        "groups": group_counts,
        "severities": severity_counts,
    }
