"""AgentSeed import verification — package-hallucination (slopsquatting) guard.

Motivated by "We Have a Package for You!" (USENIX Security 2025,
arXiv:2406.10279): across 576k generated samples, LLMs invented non-existent
package names in ~5.2% (commercial) to ~21.7% (open-source) of outputs, and
~58% of those names recurred across runs — predictable enough that attackers
pre-register the exact hallucinated names with malicious payloads
("slopsquatting").

``check_imports`` flags top-level imports that are neither Python stdlib nor
in the project's ``known_packages`` allowlist, so a model-suggested phantom
package cannot reach a lockfile silently. It is a REPORT, not a hard gate:
a legit long-tail package will also be flagged for the human to confirm —
that is the intended cost. Python (AST) only; other languages return an
honest empty result.
"""

from __future__ import annotations

import ast
import sys

# Fallback for Python < 3.10 (``sys.stdlib_module_names`` is 3.10+): a curated
# list of the most commonly imported stdlib modules. On 3.10+ the exact set is
# used and this list is never consulted.
_STDLIB_FALLBACK = frozenset(
    {
        "abc", "argparse", "array", "ast", "asyncio", "atexit", "base64",
        "bisect", "builtins", "collections", "concurrent", "configparser",
        "contextlib", "copy", "csv", "ctypes", "dataclasses", "datetime",
        "decimal", "difflib", "enum", "errno", "functools", "gc", "getpass",
        "glob", "gzip", "hashlib", "heapq", "hmac", "html", "http", "importlib",
        "inspect", "io", "ipaddress", "itertools", "json", "logging", "math",
        "multiprocessing", "os", "pathlib", "pickle", "platform", "queue",
        "random", "re", "readline", "secrets", "shlex", "shutil", "signal",
        "site", "socket", "sqlite3", "ssl", "stat", "statistics", "string",
        "struct", "subprocess", "sys", "tempfile", "textwrap", "threading",
        "time", "timeit", "token", "tokenize", "traceback", "types", "typing",
        "unicodedata", "unittest", "urllib", "uuid", "venv", "warnings",
        "weakref", "xml", "zipfile", "zoneinfo",
    }
)

# Common third-party packages treated as known by default (beyond stdlib).
# The full resolution for anything not listed is: user config ``known_packages``.
_DEFAULT_COMMON = frozenset(
    {
        "numpy", "pandas", "scipy", "sklearn", "matplotlib", "seaborn", "plotly",
        "requests", "httpx", "aiohttp", "urllib3", "beautifulsoup4", "bs4",
        "scrapy", "selenium", "playwright", "flask", "fastapi", "django",
        "starlette", "uvicorn", "gunicorn", "jinja2", "sqlalchemy", "pymysql",
        "psycopg2", "redis", "pymongo", "elasticsearch", "celery", "kafka",
        "pydantic", "pydantic_settings", "click", "typer", "rich", "tqdm",
        "pytest", "coverage", "black", "ruff", "mypy", "flake8", "isort",
        "tox", "nox", "hypothesis", "unittest", "jupyter", "notebook",
        "ipykernel", "ipython", "nbformat", "nbconvert", "tensorflow", "torch",
        "keras", "transformers", "datasets", "tokenizers", "accelerate",
        "sentence_transformers", "openai", "anthropic", "google", "googleapiclient",
        "boto3", "botocore", "azure", "awscli", "paramiko", "cryptography",
        "pycryptodome", "bcrypt", "jwt", "pyjwt", "passlib", "yaml", "pyyaml",
        "tomllib", "tomli", "tomlkit", "jsonschema", "setuptools", "wheel",
        "pip", "pipenv", "poetry", "uv", "pre_commit", "arrow", "pendulum",
        "dateutil", "python_dateutil", "pytz", "tzlocal", "zoneinfo", "natsort",
        "more_itertools", "toolz", "pydash", "tenacity", "structlog", "loguru",
        "colorama", "clickhouse_driver", "duckdb", "polars", "dask", "ray",
    }
)


def _stdlib_modules() -> frozenset[str]:
    names = getattr(sys, "stdlib_module_names", None)
    return frozenset(names) if names is not None else _STDLIB_FALLBACK


def _imported_top_level(source: str) -> list[tuple[str, int]]:
    """(top-level module name, lineno) for every import / from-import."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append((node.module.split(".")[0], node.lineno))
    return out


def check_imports(
    source: str,
    language: str = "python",
    known_packages: list[str] | None = None,
) -> dict:
    """Flag top-level imports neither in stdlib nor in the known-package set.

    ``known_packages`` (config key of the same name) extends the default
    common third-party allowlist with project-local packages. Python only
    (AST); other languages return an honest empty result.

    Returns:
        {"language", "imports_ok", "suspicious": [{"package", "line"}, ...],
         "note"}
    """
    lang = (language or "python").strip().lower()
    if lang != "python":
        return {
            "language": lang,
            "imports_ok": True,
            "suspicious": [],
            "note": "Import verification is implemented for python (AST); "
            "other languages are not covered yet.",
        }
    known = set(_DEFAULT_COMMON)
    for pkg in known_packages or []:
        if isinstance(pkg, str) and pkg.strip():
            known.add(pkg.strip())
    stdlib = _stdlib_modules()
    suspicious = [
        {"package": pkg, "line": line}
        for pkg, line in _imported_top_level(source)
        if pkg not in stdlib and pkg not in known
    ]
    note = (
        "Top-level import is neither Python stdlib nor in the known-package "
        "set (stdlib + common third-party + config `known_packages`) — a "
        "possible hallucinated package (slopsquatting). Verify the name exists "
        "in the registry before installing. This is a report, not a gate."
    )
    return {
        "language": "python",
        "imports_ok": not suspicious,
        "suspicious": suspicious,
        "note": note,
    }
