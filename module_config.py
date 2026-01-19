# module_config.py
"""
Configuración centralizada de módulos para el sistema 911 Fiesta.
Permite habilitar/deshabilitar módulos sin modificar main.py
"""

# Configuración de módulos disponibles
# True = intentar cargar, False = usar placeholder
MODULE_CONFIG = {
    # BAJADA - Todos requeridos (usan _imp estricto)
    "no_hits": True,
    "deep_listener": True,
    "soft_peaks": True,
    "ramp_down": True,
    "high_silence": True,
    "loop_dissolver": True,
    "dynamic_flattener": True,
    "texture_cleaner": True,
    "ambient_confirmator": True,
    
    # BASE_GOLPE - Todos requeridos
    "yes_hits": True,
    "accent_catcher": True,
    "groove_keeper": True,
    "pattern_lock": True,
    "cadence_spotter": True,
    "flow_monitor": True,  # Este sí está en los archivos
    "dynamic_pulse": True,
    "rhythm_highlighter": True,
    
    # ATAQUE - Opcionales (usan _imp_soft)
    "snare_roll": True,      # Cambiar a False si no existe
    "hi_roll": True,         # Cambiar a False si no existe
    "burst_sharpness": True, # Cambiar a False si no existe
    "burst_continuity": True,# Cambiar a False si no existe
    
    # BRAKE - Opcionales
    "energy_cliff": True,       # Cambiar a False si no existe
    "wideband_blackout": True,  # Cambiar a False si no existe
    "rhythm_void": True,        # Cambiar a False si no existe
    
    # ESPECIALES - Opcionales
    "break_spotter": True,    # Cambiar a False si no existe
    "super_analyzer": True,   # Cambiar a False si no existe
}

# Configuración de grupos de módulos
# Define qué módulos van en cada grupo y su orden
MODULE_GROUPS = {
    "BAJADA": [
        "no_hits",
        "deep_listener",
        "soft_peaks",
        "ramp_down",
        "high_silence",
        "break_spotter",  # Opcional, se agrega si existe
        "loop_dissolver",
        "dynamic_flattener",
        "texture_cleaner",
        "ambient_confirmator"
    ],
    
    "BASE_GOLPE": [
        "yes_hits",
        "accent_catcher",
        "groove_keeper",
        "pattern_lock",
        "cadence_spotter",
        "flow_monitor",
        "dynamic_pulse",
        "rhythm_highlighter"
    ],
    
    "ATAQUE": [
        "snare_roll",
        "hi_roll",
        "burst_sharpness",
        "burst_continuity"
    ],
    
    "BRAKE": [
        "energy_cliff",
        "wideband_blackout",
        "rhythm_void",
        "high_silence"  # Reutilizado de BAJADA
    ]
}

# Configuración de thresholds recomendados por módulo
# Útil para presets automáticos según género musical
THRESHOLD_PRESETS = {
    "TECHNO": {
        "BASE_GOLPE": {"min": 40, "max": 80, "match": 60},
        "BAJADA": {"min": 20, "max": 60, "match": 40},
        "ATAQUE": {"min": 70, "max": 95, "match": 85},
        "BRAKE": {"min": 70, "max": 95, "match": 85}
    },
    "HOUSE": {
        "BASE_GOLPE": {"min": 35, "max": 75, "match": 55},
        "BAJADA": {"min": 25, "max": 65, "match": 45},
        "ATAQUE": {"min": 65, "max": 90, "match": 75},
        "BRAKE": {"min": 65, "max": 90, "match": 75}
    },
    "AMBIENT": {
        "BASE_GOLPE": {"min": 20, "max": 50, "match": 35},
        "BAJADA": {"min": 40, "max": 80, "match": 60},
        "ATAQUE": {"min": 80, "max": 100, "match": 90},
        "BRAKE": {"min": 60, "max": 85, "match": 70}
    },
    "DRUM_N_BASS": {
        "BASE_GOLPE": {"min": 45, "max": 85, "match": 65},
        "BAJADA": {"min": 15, "max": 45, "match": 30},
        "ATAQUE": {"min": 60, "max": 85, "match": 70},
        "BRAKE": {"min": 75, "max": 95, "match": 85}
    }
}

def get_module_status():
    """Retorna el estado actual de los módulos"""
    status = {
        "configured": sum(1 for v in MODULE_CONFIG.values() if v),
        "disabled": sum(1 for v in MODULE_CONFIG.values() if not v),
        "total": len(MODULE_CONFIG),
        "details": MODULE_CONFIG.copy()
    }
    return status

def validate_modules():
    """Valida qué módulos están realmente disponibles"""
    import importlib
    import sys
    import os
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    for sub in ("", "analyzers", "analizer"):
        p = os.path.join(BASE_DIR, sub)
        if p not in sys.path and os.path.isdir(p):
            sys.path.insert(0, p)
    
    available = {}
    missing = []
    
    for module_name, enabled in MODULE_CONFIG.items():
        if not enabled:
            available[module_name] = "DISABLED"
            continue
            
        found = False
        for pkg in ("", "analyzers", "analizer"):
            try:
                full = f"{pkg + '.' if pkg else ''}{module_name}"
                importlib.import_module(full)
                available[module_name] = "OK"
                found = True
                break
            except ImportError:
                continue
        
        if not found:
            available[module_name] = "MISSING"
            missing.append(module_name)
    
    return {
        "available": available,
        "missing": missing,
        "summary": {
            "ok": sum(1 for v in available.values() if v == "OK"),
            "missing": len(missing),
            "disabled": sum(1 for v in available.values() if v == "DISABLED")
        }
    }

def apply_genre_preset(genre, state_manager, group_cards):
    """Aplica presets de thresholds según género musical"""
    if genre not in THRESHOLD_PRESETS:
        return False
        
    preset = THRESHOLD_PRESETS[genre]
    
    # Aplicar a los group cards
    if "BAJADA" in preset and "bajada" in group_cards:
        group_cards["bajada"].set_match(preset["BAJADA"]["match"])
    
    if "BASE_GOLPE" in preset and "base_golpe" in group_cards:
        group_cards["base_golpe"].set_match(preset["BASE_GOLPE"]["match"])
    
    if "ATAQUE" in preset and "ataque" in group_cards:
        group_cards["ataque"].set_match(preset["ATAQUE"]["match"])
    
    if "BRAKE" in preset and "brake" in group_cards:
        group_cards["brake"].set_match(preset["BRAKE"]["match"])
    
    # Configurar StateManager según género
    if genre == "TECHNO":
        state_manager.set_ataque_config(threshold=0.75, duration=1.5, min_gap=0.3)
        state_manager.set_brake_config(threshold=0.75, duration=2.0, min_gap=1.0)
    elif genre == "DRUM_N_BASS":
        state_manager.set_ataque_config(threshold=0.70, duration=1.2, min_gap=0.2)
        state_manager.set_brake_config(threshold=0.70, duration=1.5, min_gap=0.8)
    elif genre == "AMBIENT":
        state_manager.set_ataque_config(threshold=0.85, duration=2.0, min_gap=0.5)
        state_manager.set_brake_config(threshold=0.80, duration=3.0, min_gap=1.5)
    
    print(f"[MODULE_CONFIG] Aplicado preset de género: {genre}")
    return True

# Script de validación standalone
if __name__ == "__main__":
    print("=== VALIDACIÓN DE MÓDULOS 911 FIESTA ===\n")
    
    # Verificar estado de configuración
    status = get_module_status()
    print(f"Módulos configurados: {status['configured']}/{status['total']}")
    print(f"Módulos deshabilitados: {status['disabled']}")
    
    # Validar disponibilidad real
    print("\nValidando disponibilidad real...")
    validation = validate_modules()
    
    print(f"\nRESUMEN:")
    print(f"  [OK] Modulos OK: {validation['summary']['ok']}")
    print(f"  [MISSING] Faltantes: {validation['summary']['missing']}")
    print(f"  [DISABLED] Deshabilitados: {validation['summary']['disabled']}")
    
    if validation['missing']:
        print(f"\nMÓDULOS FALTANTES:")
        for module in validation['missing']:
            print(f"  - {module}")
        print("\nRECOMENDACIÓN: Implementar estos módulos o cambiar su configuración a False en MODULE_CONFIG")
    
    print("\nDETALLE POR MÓDULO:")
    for module, status in sorted(validation['available'].items()):
        symbol = "✅" if status == "OK" else "❌" if status == "MISSING" else "🔒"
        print(f"  {symbol} {module:20} -> {status}")
    
    print("\n=== FIN DE VALIDACIÓN ===")