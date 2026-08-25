"""AgentSeed undefined symbol detection.

Static analysis to flag symbols the model may have hallucinated
(called/used but never defined or imported). Supports python (AST)
and typescript/javascript (lexical regex pass).
"""

from __future__ import annotations

import ast
import builtins
import re

# Optional: pyflakes for more accurate Python undefined-name detection (F821).
# When available its scope-aware analysis is merged in (e.g. ``del x`` on an
# undefined name, which the hand-rolled walk's Store/Load contexts miss).
# When unavailable, the zero-dep fallback applies unchanged.
_HAS_PYFLAKES = False
try:
    from pyflakes.checker import Checker as _PyflakesChecker
    from pyflakes.messages import UndefinedName as _PyflakesUndefinedName

    _HAS_PYFLAKES = True
except ImportError:  # pragma: no cover
    _PyflakesChecker = None
    _PyflakesUndefinedName = None


def _pyflakes_undefined(source: str) -> list[tuple[str, int]] | None:
    """Undefined-name findings via optional pyflakes, or None when pyflakes
    is unavailable or the source cannot be compiled (caller already handled
    SyntaxError separately). Returns (name, lineno) pairs."""
    if not _HAS_PYFLAKES:
        return None
    try:
        tree = compile(source, "<agentseed>", "exec", ast.PyCF_ONLY_AST)
        checker = _PyflakesChecker(tree, "<agentseed>")
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return None
    out: list[tuple[str, int]] = []
    for msg in checker.messages:
        if isinstance(msg, _PyflakesUndefinedName) and msg.message_args:
            out.append((str(msg.message_args[0]), getattr(msg, "lineno", 0)))
    return out


# ---------------------------------------------------------------------------
# TypeScript lightweight static analysis (zero-dependency regex pass).
# ---------------------------------------------------------------------------

TS_GLOBALS = {
    "console",
    "Math",
    "JSON",
    "Object",
    "Array",
    "String",
    "Number",
    "Boolean",
    "Date",
    "Promise",
    "RegExp",
    "Error",
    "Set",
    "Map",
    "Symbol",
    "BigInt",
    "process",
    "global",
    "window",
    "document",
    "module",
    "exports",
    "require",
    "fetch",
    "setTimeout",
    "setInterval",
    "clearTimeout",
    "clearInterval",
    "parseInt",
    "parseFloat",
    "isNaN",
    "isFinite",
    "encodeURIComponent",
    "decodeURIComponent",
    "undefined",
    "NaN",
    "Infinity",
}

TS_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "return",
    "typeof",
    "instanceof",
    "function",
    "class",
    "interface",
    "import",
    "export",
    "const",
    "let",
    "var",
    "new",
    "delete",
    "in",
    "of",
    "await",
    "yield",
    "throw",
    "try",
    "do",
    "case",
    "default",
    "else",
    "this",
    "super",
    "void",
    "break",
    "continue",
    "as",
    "from",
    "type",
    "extends",
    "implements",
    "public",
    "private",
    "protected",
    "readonly",
    "static",
    "async",
    "keyof",
    "never",
    "unknown",
    "any",
}

_TS_IDENT = r"[A-Za-z_$][A-Za-z0-9_$]*"


def _deduplicate(items: list[str]) -> list[str]:
    """Remove duplicates while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _ts_defined_symbols(source: str) -> set[str]:
    """Collect identifiers defined or imported in a TS/JS source (lexical pass)."""
    defined: set[str] = set(TS_GLOBALS)
    # import { a, b as c } from '...'
    for m in re.finditer(r"\bimport\s*\{([^}]*)\}\s*from", source):
        for part in m.group(1).split(","):
            p = part.strip()
            if not p:
                continue
            alias = re.search(r"\bas\s+(" + _TS_IDENT + r")\s*$", p)
            defined.add(alias.group(1) if alias else p.split(":")[-1].strip())
    # import a / import * as a / import a = require()
    for m in re.finditer(r"\bimport\s+(?:\*\s+as\s+)?(" + _TS_IDENT + r")\s*(?:from|=)", source):
        defined.add(m.group(1))
    # const { a, b: c } = require(...) / import(...) / destructuring
    for m in re.finditer(
        r"\b(?:const|let|var)\s*\{([^}]*)\}\s*=\s*(?:require|import)\s*\(", source
    ):
        for part in m.group(1).split(","):
            p = part.strip()
            if not p:
                continue
            alias = re.search(r":\s*(" + _TS_IDENT + r")\s*$", p)
            defined.add(alias.group(1) if alias else p.split(":")[0].strip())
    # function/class/interface/type declarations
    for m in re.finditer(
        r"\b(?:async\s+)?(?:function|class|interface|type|enum)\s+(" + _TS_IDENT + r")",
        source,
    ):
        defined.add(m.group(1))
    # const/let/var declarations
    for m in re.finditer(r"\b(?:const|let|var)\s+([^;\n]+)", source):
        for part in m.group(1).split(","):
            decl = re.match(r"\s*(" + _TS_IDENT + r")(?:\s*[:=]|\s*$)", part)
            if decl:
                defined.add(decl.group(1))

    def _add_params(body: str) -> None:
        for part in re.split(r",", body):
            p = part.strip()
            if not p:
                continue
            p = re.sub(r":.*$", "", p)
            p = re.sub(r"^\.\.\.", "", p)
            p = re.sub(r"^\{|\}$", "", p)
            p = re.sub(r"^\[|\]$", "", p)
            if re.fullmatch(_TS_IDENT, p):
                defined.add(p)

    for m in re.finditer(r"\bfunction\s+(?:" + _TS_IDENT + r"\s*)?\(([^)]*)\)", source):
        _add_params(m.group(1))
    for m in re.finditer(
        r"\b(?:const|let|var)\s+" + _TS_IDENT + r"\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>",
        source,
    ):
        _add_params(m.group(1))
    for m in re.finditer(
        r"\b(?:const|let|var)\s+" + _TS_IDENT + r"\s*=\s*(?:async\s*)?(" + _TS_IDENT + r")\s*=>",
        source,
    ):
        _add_params(m.group(1))
    return defined


def _detect_ts_undefined(source: str) -> tuple[list[str], str]:
    """Lexical pass: calls/new-expressions whose callee is never defined."""
    defined = _ts_defined_symbols(source)
    suspects: list[str] = []
    for m in re.finditer(r"\bnew\s+(" + _TS_IDENT + r")\s*\(", source):
        name = m.group(1)
        if name not in defined and name not in TS_KEYWORDS:
            suspects.append(name)
    for m in re.finditer(r"(?<![\w$.])(" + _TS_IDENT + r")\s*\(", source):
        name = m.group(1)
        if name not in defined and name not in TS_KEYWORDS:
            suspects.append(name)
    note = (
        "Lexical regex pass, not a type checker; may miss destructured "
        "imports or produce false positives on dynamic/global references."
    )
    return _deduplicate(suspects), note


# Match-statement node types exist only on Python 3.10+; resolve once so
# older interpreters skip these branches instead of raising AttributeError.
_MATCH_AS = getattr(ast, "MatchAs", None)
_MATCH_STAR = getattr(ast, "MatchStar", None)
_MATCH_MAPPING = getattr(ast, "MatchMapping", None)


def detect_undefined_symbols(
    source: str, language: str = "python", suppress: list[str] | None = None
) -> dict:
    """Parse source and return symbols that look hallucinated
    (used/called but never defined or imported).

    Supports: python (AST), typescript/javascript (lexical regex pass).
    ``suppress`` removes exact symbol names from the findings (config:
    ``suppress_symbols``); suppressed names are reported separately so the
    omission stays visible.

    Returns:
        {"language": ..., "suspects": ["foo", "Bar"],
         "suspects_detail": [{"name": "foo", "line": 12}, ...],
         "suppressed": ["bar"], "note": "..."}
    """
    if language in ("typescript", "ts", "javascript", "js"):
        suspects, note = _detect_ts_undefined(source)
        return _apply_suppress({"language": language, "suspects": suspects, "note": note}, suppress)
    if language != "python":
        return {
            "language": language,
            "suspects": [],
            "note": "Supports python (AST) and typescript/javascript (lexical); "
            "other languages are not implemented yet.",
        }

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "language": "python",
            "suspects": [],
            "note": f"Cannot parse (syntax error): {exc}",
        }

    defined: set[str] = set(dir(builtins))
    defined |= {
        "__file__",
        "__doc__",
        "__package__",
        "__spec__",
        "__loader__",
        "__main__",
        "__dict__",
        "__builtins__",
        "__cached__",
    }
    imported: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            defined.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif _MATCH_AS is not None and isinstance(node, _MATCH_AS) and node.name:
            defined.add(node.name)  # case pattern capture, py3.10+
        elif _MATCH_STAR is not None and isinstance(node, _MATCH_STAR) and node.name:
            defined.add(node.name)
        elif _MATCH_MAPPING is not None and isinstance(node, _MATCH_MAPPING) and node.rest:
            defined.add(node.rest)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)

    defined |= imported

    seen: set[str] = set()
    suspects: list[str] = []
    detail: list[dict] = []
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            name = node.id
        elif isinstance(node, ast.Delete):
            # `del x` on a never-defined name raises NameError at runtime;
            # the Load/Call contexts above never visit Del targets, so this
            # class needs its own check (works without pyflakes too).
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id not in defined
                    and target.id not in seen
                ):
                    seen.add(target.id)
                    suspects.append(target.id)
                    detail.append({"name": target.id, "line": getattr(target, "lineno", 0)})
        if name is not None and name not in defined and name not in seen:
            seen.add(name)
            suspects.append(name)
            detail.append({"name": name, "line": getattr(node, "lineno", 0)})

    pyfindings = _pyflakes_undefined(source)
    note = (
        "Static scope analysis only; no runtime; attribute calls "
        "(foo.bar) are not expanded and may cause false negatives."
    )
    if pyfindings is not None:
        for name, line in pyfindings:
            if name in defined or name in seen:
                continue
            seen.add(name)
            suspects.append(name)
            detail.append({"name": name, "line": line})
        note += " Merged with pyflakes F821 scope analysis."

    return _apply_suppress(
        {
            "language": "python",
            "suspects": suspects,
            "suspects_detail": detail,
            "note": note,
        },
        suppress,
    )


def _apply_suppress(result: dict, suppress: list[str] | None) -> dict:
    """Filter suppressed symbol names out of a detection result (visible)."""
    if not suppress:
        result.setdefault("suppressed", [])
        return result
    drop = {s for s in suppress if isinstance(s, str)}
    kept = [s for s in result["suspects"] if s not in drop]
    removed = [s for s in result["suspects"] if s in drop]
    out = dict(result)
    out["suspects"] = kept
    out["suppressed"] = removed
    if "suspects_detail" in out:
        out["suspects_detail"] = [d for d in out["suspects_detail"] if d["name"] not in drop]
    return out
