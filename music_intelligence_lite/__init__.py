# music_intelligence_lite — Ponderador global determinista (sin ML)
# ================================================================
# Kill-switch: ENABLE_MIL_LITE=0 (default) → completamente inactivo
# Cuando activo: detecta perfil musical y pondera scores por categoria
# Pesos clamp 0.8–1.2. Perfil estable 1.5s antes de cambiar.
# ================================================================
import os

ENABLE_MIL_LITE = int(os.environ.get("ENABLE_MIL_LITE", "0"))

MILLite = None

if ENABLE_MIL_LITE:
    try:
        from .mil_lite import MILLite  # noqa: F811
        print("[MIL-Lite] Music Intelligence Lite ACTIVADO")
    except Exception as e:
        print(f"[MIL-Lite] Error al importar: {e} — sistema continua sin MIL-Lite")
        MILLite = None
