"""AgentSeed guard engine — modular package.

Modules:
  config    — Config loading (load_config, config helpers)
  symbols   — Undefined symbol detection (detect_undefined_symbols)
  hallucination — Hallucination word scanning (scan_hallucination_words)
  plugin    — Agent Plugins 1.0.0 conformance checker (check_plugin_conformance)
  sandbox   — Deterministic execution channel (sandbox_run)
  schema    — JSON Schema subset validator (schema_validate)

Public API only: internal helpers stay inside their modules.
"""

from .audit import VALID_STATUSES, audit_path, record_verification
from .config import (
    CONFIG_FILENAME,
    KNOWN_CONFIG_KEYS,
    SANDBOX_ENV_MODES,
    VALID_GROUPS,
    config_extra_tokens,
    config_severities,
    config_str_list,
    load_config,
    parse_timeout,
    sandbox_env_mode,
    unknown_config_keys,
)
from .hallucination import DEFAULT_ALLOWLIST, HALLUCINATION_WORDS, scan_hallucination_words
from .plugin import check_plugin_conformance
from .sandbox import build_env, kill_tree, resolve_executable, sandbox_run
from .schema import schema_validate
from .symbols import detect_undefined_symbols
from .version import plugin_version

__all__ = [
    "CONFIG_FILENAME",
    "DEFAULT_ALLOWLIST",
    "HALLUCINATION_WORDS",
    "KNOWN_CONFIG_KEYS",
    "SANDBOX_ENV_MODES",
    "VALID_GROUPS",
    "VALID_STATUSES",
    "audit_path",
    "build_env",
    "check_plugin_conformance",
    "config_extra_tokens",
    "config_severities",
    "config_str_list",
    "detect_undefined_symbols",
    "kill_tree",
    "load_config",
    "parse_timeout",
    "plugin_version",
    "record_verification",
    "resolve_executable",
    "sandbox_env_mode",
    "sandbox_run",
    "scan_hallucination_words",
    "schema_validate",
    "unknown_config_keys",
]
