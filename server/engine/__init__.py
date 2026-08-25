"""AgentSeed guard engine — modular package.

Modules:
  config    — Config loading (load_config, config helpers)
  symbols   — Undefined symbol detection (detect_undefined_symbols)
  hallucination — Hallucination word scanning (scan_hallucination_words)
  plugin    — Agent Plugins 1.0.0 conformance checker (check_plugin_conformance)
  sandbox   — Deterministic execution channel (sandbox_run)
  schema    — JSON Schema subset validator (schema_validate)
"""

from .audit import VALID_STATUSES, audit_path, record_verification
from .config import (
    CONFIG_FILENAME,
    KNOWN_CONFIG_KEYS,
    VALID_GROUPS,
    _config_extra_tokens,
    _config_severities,
    _config_str_list,
    _parse_timeout,
    load_config,
    unknown_config_keys,
)
from .hallucination import (
    DEFAULT_ALLOWLIST,
    HALLUCINATION_WORDS,
    _GROUP_LABELS,
    scan_hallucination_words,
)
from .plugin import check_plugin_conformance
from .sandbox import _decode, _prefix_allowed, _run_command, sandbox_run
from .schema import schema_validate
from .symbols import detect_undefined_symbols
from .version import plugin_version

__all__ = [
    "CONFIG_FILENAME",
    "DEFAULT_ALLOWLIST",
    "HALLUCINATION_WORDS",
    "KNOWN_CONFIG_KEYS",
    "VALID_GROUPS",
    "VALID_STATUSES",
    "_GROUP_LABELS",
    "_config_extra_tokens",
    "_config_severities",
    "_config_str_list",
    "_decode",
    "_parse_timeout",
    "_prefix_allowed",
    "_run_command",
    "audit_path",
    "check_plugin_conformance",
    "detect_undefined_symbols",
    "load_config",
    "plugin_version",
    "record_verification",
    "sandbox_run",
    "scan_hallucination_words",
    "schema_validate",
    "unknown_config_keys",
]
