# config/mil_lite_config.py — Single source of truth for MIL-Lite activation
# =========================================================================
# Reads from config/mil_lite.json (file-based, deterministic).
# Env var ENABLE_MIL_LITE overrides file if set (backward compat).
# No dependencies beyond stdlib.
# =========================================================================
import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mil_lite.json")


def is_mil_lite_enabled() -> bool:
    """
    Returns True if MIL-Lite should be active.

    Priority:
      1. Env var ENABLE_MIL_LITE (if set and non-empty) — overrides file
      2. config/mil_lite.json  {"enabled": true/false}
      3. Default: False
    """
    # 1. Env override (explicit "0" or "1")
    env_val = os.environ.get("ENABLE_MIL_LITE")
    if env_val is not None and env_val != "":
        return env_val not in ("0", "false", "False", "no")

    # 2. Config file
    try:
        with open(_CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        return bool(cfg.get("enabled", False))
    except Exception:
        pass

    # 3. Default
    return False
