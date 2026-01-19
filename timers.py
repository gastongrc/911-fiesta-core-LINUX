# timers.py - CORREGIDO para evitar spike de CPU al inicio
# FIX #9: Escalonamiento de starts con delays para distribuir carga inicial

from PySide6.QtCore import QTimer

def setup_timers(owner, *, vu_ms=50, scope_ms=80, status_ms=400, groups_ms=300, mod_ms=40, energy_ms=200, bpm_ms=250):
    """
    Configura y arranca todos los timers con escalonamiento para evitar spike de CPU.
    
    FIX #9: Los timers ahora arrancan con delays incrementales (0ms, 15ms, 30ms, etc.)
    en lugar de todos simultáneamente, distribuyendo la carga inicial.
    """
    
    # Crear todos los timers
    owner.t_vu = QTimer(owner)
    owner.t_vu.timeout.connect(owner._tick_vu)
    owner.t_vu.setInterval(vu_ms)
    
    owner.t_scope = QTimer(owner)
    owner.t_scope.timeout.connect(owner._tick_scope)
    owner.t_scope.setInterval(scope_ms)
    
    owner.t_status = QTimer(owner)
    owner.t_status.timeout.connect(owner._tick_status)
    owner.t_status.setInterval(status_ms)
    
    owner.t_groups = QTimer(owner)
    owner.t_groups.timeout.connect(owner._tick_groups)
    owner.t_groups.setInterval(groups_ms)
    
    owner.t_mod = QTimer(owner)
    owner.t_mod.timeout.connect(owner._tick_modules)
    owner.t_mod.setInterval(mod_ms)
    
    owner.t_energy = QTimer(owner)
    owner.t_energy.timeout.connect(owner._tick_energy)
    owner.t_energy.setInterval(energy_ms)
    
    owner.t_bpm = QTimer(owner)
    owner.t_bpm.timeout.connect(owner._tick_bpm)
    owner.t_bpm.setInterval(bpm_ms)
    
    # Lista de timers en orden de prioridad (más frecuentes primero)
    timers = [
        owner.t_mod,      # 40ms - módulos (más crítico)
        owner.t_vu,       # 50ms - VU meter
        owner.t_scope,    # 80ms - scope
        owner.t_energy,   # 200ms - energy
        owner.t_bpm,      # 250ms - BPM
        owner.t_groups,   # 300ms - groups
        owner.t_status    # 400ms - status (menos crítico)
    ]
    
    # ✅ FIX #9: Arrancar con delays escalonados para distribuir carga
    # Delay de 15ms entre cada timer (total ~105ms para arrancar todos)
    delay_increment = 15  # ms entre cada start
    
    for i, timer in enumerate(timers):
        delay_ms = i * delay_increment
        
        if delay_ms == 0:
            # El primero arranca inmediatamente
            timer.start()
        else:
            # Los demás arrancan con delay usando QTimer.singleShot
            QTimer.singleShot(delay_ms, timer.start)
    
    print(f"[TIMERS] Configurados {len(timers)} timers con escalonamiento de {delay_increment}ms")
    print(f"[TIMERS] Tiempo total de arranque: {(len(timers)-1) * delay_increment}ms")