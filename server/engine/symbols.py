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


# ---------------------------------------------------------------------------
# Generic multi-language lexical verification (config-driven language
# registry). Every registered language is analyzed by the SAME engine:
# comments/strings are masked, defined symbols are collected from the
# per-language patterns, then bare calls / `new` expressions are checked.
# Adding a language is a LangSpec config change, not a code change — this
# is how verify_code scales to "any language" without a parser per language.
# ---------------------------------------------------------------------------

from dataclasses import dataclass


@dataclass(frozen=True)
class LangSpec:
    name: str
    aliases: tuple[str, ...] = ()
    line_comments: tuple[str, ...] = ()
    block_comments: tuple[tuple[str, str], ...] = ()
    strings: tuple[str, ...] = ()
    ident: str = r"[A-Za-z_][A-Za-z0-9_]*"
    keywords: frozenset[str] = frozenset()
    globals_: frozenset[str] = frozenset()
    # Each pattern must have exactly ONE capturing group: the defined name(s),
    # which may be comma-separated (e.g. `var a, b = ...`).
    defn_patterns: tuple[str, ...] = ()
    import_patterns: tuple[str, ...] = ()
    # Patterns whose group(1) is a function parameter list body, e.g. "a int, b string".
    param_patterns: tuple[str, ...] = ()
    # How to pick the parameter NAME from one comma-part:
    #   "last"         -> `Type name` (C/Java/C#/C++/PHP)
    #   "first"        -> `name Type` (Go) or bare `name` (Ruby)
    #   "before_colon" -> `name: Type` (Rust/Kotlin/Swift)
    param_mode: str = "last"
    # Characters masked to spaces before analysis (e.g. PHP "$" variable sigil).
    strip_chars: str = ""
    # Ruby-style languages allow bare method calls without parentheses;
    # standalone undefined identifiers are then flagged as calls too.
    bare_calls: bool = False


_LANG_REGISTRY: dict[str, LangSpec] = {}
_LANG_ALIASES: dict[str, str] = {}


def _register_lang(spec: LangSpec) -> None:
    _LANG_REGISTRY[spec.name] = spec
    _LANG_ALIASES[spec.name] = spec.name
    for alias in spec.aliases:
        _LANG_ALIASES[alias] = spec.name


def resolve_language(name: str) -> LangSpec | None:
    """Map a user-supplied language name to a registered spec (or None)."""
    if not name:
        return None
    canonical = _LANG_ALIASES.get(name.strip().lower())
    return _LANG_REGISTRY.get(canonical) if canonical else None


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort and merge overlapping [start, end) spans."""
    if not spans:
        return []
    ordered = sorted(spans)
    merged = [ordered[0]]
    for s, e in ordered[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _mask_source(source: str, spec: LangSpec) -> str:
    """Blank out strings and comments so patterns only see real code."""
    spans: list[tuple[int, int]] = []
    for pat in spec.strings:
        for m in re.finditer(pat, source):
            spans.append((m.start(), m.end()))
    for lc in spec.line_comments:
        for m in re.finditer(re.escape(lc) + r"[^\r\n]*", source):
            spans.append((m.start(), m.end()))
    for start, end in spec.block_comments:
        for m in re.finditer(re.escape(start) + r".*?" + re.escape(end), source, re.DOTALL):
            spans.append((m.start(), m.end()))
    buf = list(source)
    for s, e in _merge_spans(spans):
        for i in range(s, min(e, len(buf))):
            if buf[i] not in "\r\n":  # keep line structure for readability
                buf[i] = " "
    out = "".join(buf)
    for ch in spec.strip_chars:
        out = out.replace(ch, " ")
    return out


def _collect_names(m: re.Match, spec: LangSpec) -> list[str]:
    """Names captured by a defn/import pattern (group 1 may be comma-separated)."""
    out: list[str] = []
    for g in m.groups():
        if not g:
            continue
        for part in g.split(","):
            name = part.strip()
            if name and re.fullmatch(spec.ident, name):
                out.append(name)
    return out


def _params_from(body: str, spec: LangSpec) -> list[str]:
    """Pick parameter names out of one comma-part per the spec's param_mode."""
    if spec.param_mode == "before_colon":
        m = re.search(r"([A-Za-z_]\w*)\s*:", body)
        return [m.group(1)] if m else []
    if spec.param_mode == "first":
        idents = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", body)
        return idents[:1]
    # "last": drop default-value initializers (`int x = foo()`) first
    head = body.split("=", 1)[0]
    idents = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", head)
    return idents[-1:] if idents else []


def _generic_defined(source: str, spec: LangSpec) -> set[str]:
    """Collect everything a generic language source defines or imports."""
    defined = set(spec.globals_)
    for pat in spec.import_patterns:
        for m in re.finditer(pat, source):
            defined.update(_collect_names(m, spec))
    for pat in spec.defn_patterns:
        for m in re.finditer(pat, source):
            defined.update(_collect_names(m, spec))
    for pat in spec.param_patterns:
        for m in re.finditer(pat, source):
            for name in _params_from(m.group(1), spec):
                defined.add(name)
    return defined


def _generic_detect_undefined(source: str, spec: LangSpec) -> tuple[list[str], str]:
    """Lexical pass shared by every registered language (see LangSpec)."""
    masked = _mask_source(source, spec)
    defined = _generic_defined(masked, spec)
    suspects: list[str] = []
    ident = spec.ident
    for m in re.finditer(r"\bnew\s+(" + ident + r")\s*\(", masked):
        name = m.group(1)
        if name not in defined and name not in spec.keywords:
            suspects.append(name)
    # lookbehind blocks attribute (`obj.m()`, `obj->m()`), path (`a::b()`),
    # and `$`-prefixed calls so only bare calls are checked
    for m in re.finditer(r"(?<![\w$.>:-])(" + ident + r")\s*\(", masked):
        name = m.group(1)
        if name not in defined and name not in spec.keywords:
            suspects.append(name)
    # languages that allow paren-less method calls (Ruby): flag standalone
    # undefined identifiers, while excluding attribute/symbol/definition sites
    if spec.bare_calls:
        for m in re.finditer(r"(?<![\w$.@:>-])([A-Za-z_]\w*)(?![\w$.@:(=])", masked):
            name = m.group(1)
            if name not in defined and name not in spec.keywords:
                suspects.append(name)
    note = (
        f"Generic lexical pass for {spec.name} (config-driven registry); "
        "not a type checker — attribute calls, macros, and cross-file "
        "symbols are not analyzed."
    )
    return _deduplicate(suspects), note


_register_lang(
    LangSpec(
        name="go",
        aliases=("golang",),
        line_comments=("//",),
        block_comments=(("/*", "*/"),),
        strings=(r'"(?:[^"\\]|\\.)*"', r"`[^`]*`", r"'(?:[^'\\]|\\.)*'"),
        keywords=frozenset(
            {
                "package", "import", "func", "var", "const", "type", "struct",
                "interface", "map", "chan", "go", "defer", "select", "range",
                "return", "if", "else", "for", "switch", "case", "default",
                "break", "continue", "fallthrough", "goto", "panic", "recover",
                "nil", "true", "false", "iota", "len", "cap", "make", "new",
                "append", "copy", "delete", "close", "complex", "real", "imag",
                "min", "max", "print", "println", "error", "byte", "rune",
                "int", "int8", "int16", "int32", "int64", "uint", "uint8",
                "uint16", "uint32", "uint64", "uintptr", "float32", "float64",
                "string", "bool", "any",
            }
        ),
        defn_patterns=(
            r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(",
            r"\btype\s+([A-Za-z_]\w*)",
            r"\bvar\s+([A-Za-z_]\w*)",
            r"\bconst\s+([A-Za-z_]\w*)",
            r"([A-Za-z_]\w*)\s*:=",
        ),
        param_patterns=(r"\bfunc\s+(?:\([^)]*\)\s*)?[A-Za-z_]\w*\s*\(([^)]*)\)",),
        param_mode="first",
    )
)

_register_lang(
    LangSpec(
        name="rust",
        aliases=("rs",),
        line_comments=("//",),
        block_comments=(("/*", "*/"),),
        strings=(r'"(?:[^"\\]|\\.)*"', r"'(?:[^'\\]|\\.)*'"),
        keywords=frozenset(
            {
                "fn", "let", "mut", "const", "static", "struct", "enum",
                "trait", "impl", "use", "mod", "pub", "crate", "self", "Self",
                "super", "if", "else", "match", "while", "loop", "for", "in",
                "return", "break", "continue", "move", "ref", "type", "where",
                "async", "await", "dyn", "unsafe", "extern", "as", "true",
                "false", "Option", "Result", "Some", "None", "Ok", "Err",
                "Vec", "String", "Box", "Rc", "Arc", "i8", "i16", "i32",
                "i64", "i128", "isize", "u8", "u16", "u32", "u64", "u128",
                "usize", "f32", "f64", "bool", "char", "str", "println",
                "print", "eprintln", "eprint", "panic", "assert", "assert_eq",
                "assert_ne", "vec", "format", "dbg", "todo", "unimplemented",
                "unreachable", "macro_rules",
            }
        ),
        defn_patterns=(
            r"\bfn\s+([A-Za-z_]\w*)\s*\(",
            r"\bstruct\s+([A-Za-z_]\w*)",
            r"\benum\s+([A-Za-z_]\w*)",
            r"\btrait\s+([A-Za-z_]\w*)",
            r"\bconst\s+([A-Za-z_]\w*)\s*:",
            r"\bstatic\s+(?:mut\s+)?([A-Za-z_]\w*)\s*:",
            r"\blet\s+(?:mut\s+)?([A-Za-z_]\w*)\s*[=:]",
        ),
        import_patterns=(
            r"\buse\s+(?:[A-Za-z_]\w*::)*([A-Za-z_]\w*)\s*;",
            r"\buse\s+(?:[A-Za-z_]\w*::)*\{([^}]*)\}",
        ),
        param_patterns=(r"\bfn\s+[A-Za-z_]\w*\s*\(([^)]*)\)",),
        param_mode="before_colon",
    )
)

_register_lang(
    LangSpec(
        name="java",
        aliases=(),
        line_comments=("//",),
        block_comments=(("/*", "*/"),),
        strings=(r'"(?:[^"\\]|\\.)*"', r"'(?:[^'\\]|\\.)*'"),
        keywords=frozenset(
            {
                "public", "private", "protected", "static", "final", "void",
                "int", "long", "float", "double", "boolean", "char", "byte",
                "short", "class", "interface", "enum", "extends", "implements",
                "import", "package", "new", "return", "if", "else", "for",
                "while", "do", "switch", "case", "default", "break",
                "continue", "try", "catch", "finally", "throw", "throws",
                "this", "super", "abstract", "synchronized", "native",
                "transient", "volatile", "instanceof", "true", "false", "null",
                "String", "System", "Math", "Object", "Integer", "Long",
                "Double", "Boolean", "Character", "List", "Map", "Set",
                "ArrayList", "HashMap", "HashSet", "Optional", "StringBuilder",
                "Thread", "Exception", "RuntimeException", "Iterable",
                "Collection", "Stream",
            }
        ),
        defn_patterns=(
            r"\bclass\s+([A-Za-z_]\w*)",
            r"\binterface\s+([A-Za-z_]\w*)",
            r"\benum\s+([A-Za-z_]\w*)",
            r"(?:(?:public|private|protected|static|final|abstract|synchronized|native)\s+)*(?:[A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*\(",
            r"(?:(?:public|private|protected|static|final|volatile|transient)\s+)*(?:[A-Za-z_]\w*)(?:\[\])?\s+([A-Za-z_]\w*)\s*(?:=|;)",
        ),
        import_patterns=(
            r"\bimport\s+(?:static\s+)?(?:[A-Za-z_]\w*\.)*([A-Za-z_]\w*)\s*;",
        ),
        param_patterns=(
            r"(?:[A-Za-z_]\w*)(?:\[\])?\s+[A-Za-z_]\w*\s*\(([^)]*)\)",
        ),
        param_mode="last",
    )
)

_register_lang(
    LangSpec(
        name="c",
        aliases=(),
        line_comments=("//",),
        block_comments=(("/*", "*/"),),
        strings=(r'"(?:[^"\\]|\\.)*"', r"'(?:[^'\\]|\\.)*'"),
        keywords=frozenset(
            {
                "auto", "break", "case", "char", "const", "continue",
                "default", "do", "double", "else", "enum", "extern", "float",
                "for", "goto", "if", "inline", "int", "long", "register",
                "restrict", "return", "short", "signed", "sizeof", "static",
                "struct", "switch", "typedef", "union", "unsigned", "void",
                "volatile", "while", "NULL", "size_t", "printf", "scanf",
                "malloc", "calloc", "free", "realloc", "memcpy", "memset",
                "strlen", "strcmp", "strcpy", "strncpy", "strcat", "sprintf",
                "snprintf", "fopen", "fclose", "fprintf", "fgets", "fputs",
                "exit", "assert", "getchar", "putchar", "puts",
            }
        ),
        defn_patterns=(
            r"\b(?:void|int|char|long|float|double|short|unsigned|signed|size_t|ssize_t|[A-Za-z_]\w*_t)\s+([A-Za-z_]\w*)\s*\(",
            r"\bstruct\s+([A-Za-z_]\w*)",
            r"\btypedef\s+(?:[A-Za-z_]\w*\s+)+([A-Za-z_]\w*)\s*;",
            r"#define\s+([A-Za-z_]\w*)",
        ),
        import_patterns=(r"#include\s*[<\"]([A-Za-z_]\w*)[>\"]",),
        param_patterns=(
            r"\b(?:void|int|char|long|float|double|short|unsigned|signed|size_t|ssize_t|[A-Za-z_]\w*_t)\s+[A-Za-z_]\w*\s*\(([^)]*)\)",
        ),
        param_mode="last",
    )
)

_register_lang(
    LangSpec(
        name="cpp",
        aliases=("c++", "cc", "cxx"),
        line_comments=("//",),
        block_comments=(("/*", "*/"),),
        strings=(r'"(?:[^"\\]|\\.)*"', r"'(?:[^'\\]|\\.)*'"),
        keywords=frozenset(
            {
                "auto", "break", "case", "char", "class", "const", "constexpr",
                "continue", "default", "delete", "do", "double", "else",
                "enum", "explicit", "extern", "float", "for", "friend", "goto",
                "if", "inline", "int", "long", "namespace", "new", "noexcept",
                "nullptr", "operator", "private", "protected", "public",
                "register", "return", "short", "signed", "sizeof", "static",
                "static_cast", "dynamic_cast", "reinterpret_cast", "const_cast",
                "struct", "switch", "template", "typename", "typedef", "union",
                "unsigned", "using", "virtual", "override", "void", "volatile",
                "while", "true", "false", "this", "NULL", "nullptr", "size_t",
                "std", "cout", "cin", "endl", "vector", "string", "map",
                "set", "shared_ptr", "unique_ptr", "make_shared", "make_unique",
                "printf", "malloc", "calloc", "free", "realloc", "memcpy",
                "memset", "strlen", "strcmp", "strcpy", "assert",
            }
        ),
        defn_patterns=(
            r"\b(?:[A-Za-z_]\w*)(?:::\s*[A-Za-z_]\w*)?\s+([A-Za-z_]\w*)\s*\(",
            r"\b(?:[A-Za-z_]\w*)(?:::\s*[A-Za-z_]\w*)?\s+([A-Za-z_]\w*)\s*(?:=|;)",
            r"\bclass\s+([A-Za-z_]\w*)",
            r"\bstruct\s+([A-Za-z_]\w*)",
            r"\bnamespace\s+([A-Za-z_]\w*)",
            r"\btypedef\s+(?:[A-Za-z_]\w*\s+)+([A-Za-z_]\w*)\s*;",
            r"#define\s+([A-Za-z_]\w*)",
        ),
        import_patterns=(r"#include\s*[<\"]([A-Za-z_]\w*)[>\"]",),
        param_patterns=(
            r"\b(?:void|int|char|long|float|double|short|unsigned|signed|size_t|ssize_t|bool|[A-Za-z_]\w*_t)\s+[A-Za-z_]\w*\s*\(([^)]*)\)",
        ),
        param_mode="last",
    )
)

_register_lang(
    LangSpec(
        name="csharp",
        aliases=("cs", "c#"),
        line_comments=("//",),
        block_comments=(("/*", "*/"),),
        strings=(r'@"(?:[^"]|"")*"', r'"(?:[^"\\]|\\.)*"', r"'(?:[^'\\]|\\.)*'"),
        keywords=frozenset(
            {
                "using", "namespace", "class", "interface", "enum", "struct",
                "public", "private", "protected", "internal", "static",
                "readonly", "const", "void", "int", "string", "bool",
                "double", "float", "long", "short", "byte", "char", "object",
                "var", "new", "return", "if", "else", "for", "foreach",
                "while", "do", "switch", "case", "default", "break",
                "continue", "try", "catch", "finally", "throw", "this",
                "base", "async", "await", "task", "delegate", "event",
                "override", "virtual", "abstract", "sealed", "partial",
                "get", "set", "null", "true", "false", "Console", "String",
                "Math", "List", "Dictionary", "IEnumerable", "Task",
                "Exception", "dynamic", "lock",
            }
        ),
        defn_patterns=(
            r"(?:(?:public|private|protected|internal|static|readonly|virtual|override|abstract|async|sealed|partial)\s+)*(?:void|int|string|bool|double|float|long|short|byte|char|object|var|[A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*\(",
            r"\bclass\s+([A-Za-z_]\w*)",
            r"\binterface\s+([A-Za-z_]\w*)",
            r"\benum\s+([A-Za-z_]\w*)",
            r"\bstruct\s+([A-Za-z_]\w*)",
            r"\bnamespace\s+([A-Za-z_]\w*)",
            r"(?:(?:public|private|protected|internal|static|readonly|const)\s+)*(?:int|string|bool|double|float|long|short|byte|char|object|var|[A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*(?:=|;)",
        ),
        import_patterns=(r"\busing\s+(?:[A-Za-z_]\w*\.)*([A-Za-z_]\w*)\s*;",),
        param_patterns=(
            r"(?:(?:public|private|protected|internal|static|readonly|virtual|override|abstract|async|sealed|partial)\s+)*(?:void|int|string|bool|double|float|long|short|byte|char|object|var|[A-Za-z_]\w*)\s+[A-Za-z_]\w*\s*\(([^)]*)\)",
        ),
        param_mode="last",
    )
)

_register_lang(
    LangSpec(
        name="php",
        aliases=(),
        line_comments=("//", "#"),
        block_comments=(("/*", "*/"),),
        strings=(r'"(?:[^"\\]|\\.)*"', r"'(?:[^'\\]|\\.)*'", r"`[^`]*`"),
        keywords=frozenset(
            {
                "function", "class", "interface", "trait", "enum", "public",
                "private", "protected", "static", "final", "abstract",
                "extends", "implements", "use", "namespace", "new", "return",
                "if", "else", "elseif", "for", "foreach", "while", "do",
                "switch", "case", "default", "break", "continue", "try",
                "catch", "finally", "throw", "this", "self", "parent", "echo",
                "print", "isset", "empty", "unset", "die", "exit", "require",
                "include", "require_once", "include_once", "global", "const",
                "var", "true", "false", "null", "array", "list", "match",
                "fn", "and", "or", "xor", "not", "as", "instanceof",
                "yield", "from", "clone",
            }
        ),
        defn_patterns=(
            r"\bfunction\s+&?\s*([A-Za-z_]\w*)\s*\(",
            r"\bclass\s+([A-Za-z_]\w*)",
            r"\binterface\s+([A-Za-z_]\w*)",
            r"\btrait\s+([A-Za-z_]\w*)",
            r"\benum\s+([A-Za-z_]\w*)",
            r"\bnamespace\s+([A-Za-z_]\w*)",
            r"(?:^|[;\s{}])([A-Za-z_]\w*)\s*=",
        ),
        import_patterns=(r"\buse\s+(?:[A-Za-z_]\w*\\)*([A-Za-z_]\w*)\s*;",),
        param_patterns=(r"\bfunction\s+(?:&?\s*[A-Za-z_]\w*\s*)?\(([^)]*)\)",),
        param_mode="last",
        strip_chars="$",
    )
)

_register_lang(
    LangSpec(
        name="ruby",
        aliases=("rb",),
        line_comments=("#",),
        block_comments=(("=begin", "=end"),),
        strings=(r'"(?:[^"\\]|\\.)*"', r"'(?:[^'\\]|\\.)*'", r"`[^`]*`"),
        keywords=frozenset(
            {
                "def", "class", "module", "end", "if", "elsif", "else",
                "unless", "while", "until", "for", "in", "do", "case",
                "when", "then", "return", "break", "next", "redo", "retry",
                "yield", "raise", "rescue", "ensure", "begin", "require",
                "include", "extend", "attr_accessor", "attr_reader",
                "attr_writer", "new", "self", "super", "true", "false",
                "nil", "and", "or", "not", "lambda", "proc", "puts", "print",
                "p", "gets", "require_relative", "alias", "undef", "defined",
                "loop",
            }
        ),
        defn_patterns=(
            r"\bdef\s+(?:self\.)?([A-Za-z_]\w*)",
            r"\bclass\s+([A-Za-z_]\w*)",
            r"\bmodule\s+([A-Za-z_]\w*)",
        ),
        import_patterns=(r"\brequire\s+['\"]([A-Za-z_]\w*)['\"]",),
        param_patterns=(r"\bdef\s+(?:self\.)?[A-Za-z_]\w*\s*\(([^)]*)\)",),
        param_mode="first",
        bare_calls=True,
    )
)

_register_lang(
    LangSpec(
        name="kotlin",
        aliases=("kt",),
        line_comments=("//",),
        block_comments=(("/*", "*/"),),
        strings=(r'"(?:[^"\\]|\\.)*"', r'"""[\s\S]*?"""', r"'(?:[^'\\]|\\.)*'"),
        keywords=frozenset(
            {
                "fun", "val", "var", "class", "interface", "object", "enum",
                "data", "sealed", "abstract", "open", "override", "internal",
                "public", "private", "protected", "companion", "init",
                "constructor", "import", "package", "if", "else", "when",
                "for", "while", "do", "return", "break", "continue", "try",
                "catch", "finally", "throw", "this", "super", "null", "true",
                "false", "by", "as", "is", "in", "out", "reified", "inline",
                "noinline", "crossinline", "suspend", "operator", "infix",
                "tailrec", "lateinit", "lazy", "List", "MutableList", "Map",
                "Set", "String", "Int", "Double", "Boolean", "Long", "Array",
                "Any", "Unit", "Nothing", "println", "print", "listOf",
                "mapOf", "setOf", "mutableListOf", "mutableMapOf",
            }
        ),
        defn_patterns=(
            r"\bfun\s+(?:[A-Za-z_]\w*\.)?([A-Za-z_]\w*)\s*\(",
            r"\bclass\s+([A-Za-z_]\w*)",
            r"\binterface\s+([A-Za-z_]\w*)",
            r"\benum\s+(?:class\s+)?([A-Za-z_]\w*)",
            r"\bobject\s+([A-Za-z_]\w*)",
            r"\bval\s+([A-Za-z_]\w*)\s*[:=]",
            r"\bvar\s+([A-Za-z_]\w*)\s*[:=]",
            r"\bconst\s+val\s+([A-Za-z_]\w*)",
        ),
        import_patterns=(r"\bimport\s+(?:[A-Za-z_]\w*\.)*([A-Za-z_]\w*)",),
        param_patterns=(r"\bfun\s+(?:[A-Za-z_]\w*\.)?[A-Za-z_]\w*\s*\(([^)]*)\)",),
        param_mode="before_colon",
    )
)

_register_lang(
    LangSpec(
        name="swift",
        aliases=(),
        line_comments=("//",),
        block_comments=(("/*", "*/"),),
        strings=(r'"(?:[^"\\]|\\.)*"', r'"""[\s\S]*?"""'),
        keywords=frozenset(
            {
                "func", "class", "struct", "enum", "protocol", "extension",
                "let", "var", "import", "return", "if", "else", "guard",
                "for", "while", "repeat", "switch", "case", "default",
                "break", "continue", "try", "catch", "throw", "throws", "do",
                "in", "as", "is", "nil", "true", "false", "self", "super",
                "init", "deinit", "public", "private", "internal",
                "fileprivate", "open", "static", "final", "override", "lazy",
                "weak", "unowned", "where", "String", "Int", "Double",
                "Bool", "Array", "Dictionary", "Set", "Optional", "print",
                "count", "map", "filter", "reduce", "sorted", "first",
                "last", "isEmpty",
            }
        ),
        defn_patterns=(
            r"\bfunc\s+([A-Za-z_]\w*)\s*\(",
            r"\bclass\s+([A-Za-z_]\w*)",
            r"\bstruct\s+([A-Za-z_]\w*)",
            r"\benum\s+([A-Za-z_]\w*)",
            r"\bprotocol\s+([A-Za-z_]\w*)",
            r"\bextension\s+([A-Za-z_]\w*)",
            r"\blet\s+([A-Za-z_]\w*)\s*[:=]",
            r"\bvar\s+([A-Za-z_]\w*)\s*[:=]",
            r"\bstatic\s+let\s+([A-Za-z_]\w*)",
        ),
        import_patterns=(r"\bimport\s+(?:[A-Za-z_]\w*\.)*([A-Za-z_]\w*)",),
        param_patterns=(r"\bfunc\s+[A-Za-z_]\w*\s*\(([^)]*)\)",),
        param_mode="before_colon",
    )
)

# Public surface for CLI/schema: canonical python + ts + every registered alias.
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "python",
    "typescript",
    "javascript",
    "ts",
    "js",
) + tuple(sorted(_LANG_ALIASES))


# Match-statement node types exist only on Python 3.10+; resolve once so
# older interpreters skip these branches instead of raising AttributeError.
_MATCH_AS = getattr(ast, "MatchAs", None)
_MATCH_STAR = getattr(ast, "MatchStar", None)
_MATCH_MAPPING = getattr(ast, "MatchMapping", None)


def _python_defined_symbols(tree: ast.AST) -> set[str]:
    """Names defined or imported by a parsed Python module (for ``defined_symbols``)."""
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
    return defined


def defined_symbols(source: str, language: str = "python") -> list[str]:
    """Names the source defines or imports (sorted). Used by ``check_contract``
    to verify that ``requires`` symbols actually exist in the module.

    Same language support as ``detect_undefined_symbols``: Python (AST),
    TypeScript/JavaScript (lexical), and the config-driven generic registry.
    Returns [] for unsupported languages or unparseable Python.
    """
    lang = (language or "python").strip().lower()
    if lang in ("typescript", "ts", "javascript", "js"):
        return sorted(_ts_defined_symbols(source))
    spec = resolve_language(lang)
    if spec is not None:
        return sorted(_generic_defined(_mask_source(source, spec), spec))
    if lang == "python":
        try:
            return sorted(_python_defined_symbols(ast.parse(source)))
        except SyntaxError:
            return []
    return []


def detect_undefined_symbols(
    source: str, language: str = "python", suppress: list[str] | None = None
) -> dict:
    """Parse source and return symbols that look hallucinated
    (used/called but never defined or imported).

    Supports: python (AST), typescript/javascript (lexical), plus a
    config-driven generic lexical pass for go, rust, java, c, c++, c#,
    php, ruby, kotlin, swift — extensible via the language registry.
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
    spec = resolve_language(language)
    if spec is not None:
        suspects, note = _generic_detect_undefined(source, spec)
        return _apply_suppress(
            {"language": spec.name, "suspects": suspects, "note": note}, suppress
        )
    if language != "python":
        return {
            "language": language,
            "suspects": [],
            "note": "Unsupported language. Supported: " + ", ".join(SUPPORTED_LANGUAGES) + ".",
        }

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "language": "python",
            "suspects": [],
            "note": f"Cannot parse (syntax error): {exc}",
        }

    defined = _python_defined_symbols(tree)

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
