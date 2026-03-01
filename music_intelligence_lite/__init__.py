# music_intelligence_lite — Ponderador global determinista (sin ML)
# ================================================================
# Activation read from config/mil_lite.json (file-based, deterministic).
# Env var ENABLE_MIL_LITE overrides file if set.
# ================================================================

MILLite = None

try:
    from config.mil_lite_config import is_mil_lite_enabled
    _enabled = is_mil_lite_enabled()
except Exception:
    _enabled = False

if _enabled:
    try:
        from .mil_lite import MILLite  # noqa: F811
        print("[MIL-Lite] Music Intelligence Lite ACTIVADO")
    except Exception as e:
        print(f"[MIL-Lite] Error al importar: {e} — sistema continua sin MIL-Lite")
        MILLite = None
