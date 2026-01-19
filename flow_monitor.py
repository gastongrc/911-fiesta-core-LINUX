# flow_monitor.py - TAREA 2: Compatibilidad preset + validación NaN
import numpy as np
from base_module import BaseModule
from module_card import ModuleCard
from rhythm_tools import mono, env_onset

class FlowMonitor(BaseModule):
    """
    Monitorea el flujo de energía en la señal de audio.
    TAREA 2: Mapeo de parámetros preset (sens, win_s, gap_ms, hold, smooth, dens_tgt).
    """
    
    name = "FLOW MONITOR"
    
    def __init__(self, config=None):
        super().__init__()
        self.card = ModuleCard(self.name)
        
        # TAREA 2: leer config y mapear parámetros
        cfg = config or {}
        
        # ═══════════════════════════════════════════════════════════════
        # CAPA DE COMPATIBILIDAD DE PARÁMETROS
        # ═══════════════════════════════════════════════════════════════
        
        # 1. thr_env (umbral de envolvente)
        # Prioridad: thr_env > sens
        thr_env = cfg.get('thr_env', None)
        param_source_thr = "classic"
        
        if thr_env is None:
            sens = cfg.get('sens', None)
            if sens is not None:
                # Normalizar si viene en rango 0-100
                thr_env = float(sens) / 100.0 if float(sens) > 1.0 else float(sens)
                param_source_thr = "mapped"
                print(f"[FLOW] Using mapped param: sens→thr_env={thr_env:.3f}")
            else:
                thr_env = 0.30  # Default conservador
                param_source_thr = "default"
        
        # 2. dur_ms (duración de ventana)
        # Prioridad: dur_ms > win_s
        dur_ms = cfg.get('dur_ms', None)
        param_source_dur = "classic"
        
        if dur_ms is None:
            win_s = cfg.get('win_s', None)
            if win_s is not None:
                dur_ms = int(float(win_s) * 1000)
                param_source_dur = "mapped"
                print(f"[FLOW] Using mapped param: win_s→dur_ms={dur_ms}")
            else:
                dur_ms = 1000  # Default conservador
                param_source_dur = "default"
        
        # 3. refractory_ms (tiempo de refractario/gap)
        # Prioridad: refractory_ms > gap_ms
        refractory_ms = cfg.get('refractory_ms', None)
        param_source_ref = "classic"
        
        if refractory_ms is None:
            gap_ms = cfg.get('gap_ms', None)
            if gap_ms is not None:
                refractory_ms = gap_ms
                param_source_ref = "mapped"
                print(f"[FLOW] Using mapped param: gap_ms→refractory_ms={refractory_ms}")
            else:
                refractory_ms = 300  # Default conservador
                param_source_ref = "default"
        
        # 4. hold_ms (tiempo de hold)
        # Prioridad: hold_ms > hold
        hold_ms = cfg.get('hold_ms', None)
        param_source_hold = "classic"
        
        if hold_ms is None:
            hold = cfg.get('hold', None)
            if hold is not None:
                hold_ms = hold
                param_source_hold = "mapped"
                print(f"[FLOW] Using mapped param: hold→hold_ms={hold_ms}")
            else:
                hold_ms = 150  # Default conservador
                param_source_hold = "default"
        
        # 5. smoothing (suavizado)
        # Prioridad: smoothing > smooth
        smoothing = cfg.get('smoothing', None)
        param_source_smooth = "classic"
        
        if smoothing is None:
            smooth = cfg.get('smooth', None)
            if smooth is not None:
                smoothing = smooth
                param_source_smooth = "mapped"
                print(f"[FLOW] Using mapped param: smooth→smoothing={smoothing}")
            else:
                smoothing = 0.50  # Default conservador
                param_source_smooth = "default"
        
        # 6. dens_tgt (solo telemetría)
        dens_tgt = cfg.get('dens_tgt', None)
        
        # ═══════════════════════════════════════════════════════════════
        # SANITIZACIÓN Y CLAMPS (evitar NaN/Inf y valores absurdos)
        # ═══════════════════════════════════════════════════════════════
        
        # Validar y clampear thr_env
        if not np.isfinite(thr_env):
            print(f"[FLOW] Warning: thr_env NaN/Inf detectado, usando default 0.30")
            thr_env = 0.30
        thr_env = float(np.clip(thr_env, 0.0, 1.0))
        if thr_env != cfg.get('thr_env', thr_env) and cfg.get('thr_env') is not None:
            print(f"[FLOW] Warning: thr_env clamped to [{0.0}, {1.0}]")
        
        # Validar y clampear dur_ms
        if not np.isfinite(dur_ms):
            print(f"[FLOW] Warning: dur_ms NaN/Inf detectado, usando default 1000")
            dur_ms = 1000
        dur_ms = int(np.clip(dur_ms, 0, 5000))
        if dur_ms != cfg.get('dur_ms', dur_ms) and cfg.get('dur_ms') is not None:
            print(f"[FLOW] Warning: dur_ms clamped to [0, 5000]")
        
        # Validar y clampear refractory_ms
        if not np.isfinite(refractory_ms):
            print(f"[FLOW] Warning: refractory_ms NaN/Inf detectado, usando default 300")
            refractory_ms = 300
        refractory_ms = int(np.clip(refractory_ms, 0, 5000))
        
        # Validar y clampear hold_ms
        if not np.isfinite(hold_ms):
            print(f"[FLOW] Warning: hold_ms NaN/Inf detectado, usando default 150")
            hold_ms = 150
        hold_ms = int(np.clip(hold_ms, 0, 5000))
        
        # Validar y clampear smoothing
        if not np.isfinite(smoothing):
            print(f"[FLOW] Warning: smoothing NaN/Inf detectado, usando default 0.50")
            smoothing = 0.50
        smoothing = float(np.clip(smoothing, 0.0, 0.99))
        
        # Validar dens_tgt si existe
        if dens_tgt is not None and not np.isfinite(dens_tgt):
            print(f"[FLOW] Warning: dens_tgt NaN/Inf detectado, usando None")
            dens_tgt = None
        
        # Guardar parámetros procesados para telemetría
        self.refractory_ms = refractory_ms
        self.hold_ms = hold_ms
        self.smoothing = smoothing
        self.dens_tgt = dens_tgt
        
        # Guardar source info para telemetría
        self._param_sources = {
            "thr_env": param_source_thr,
            "dur_ms": param_source_dur,
            "refractory_ms": param_source_ref,
            "hold_ms": param_source_hold,
            "smoothing": param_source_smooth
        }
        
        # Configurar sliders con valores mapeados y sanitizados
        self.card.add_slider("thr_env", "Umbral env", 0.10, 0.60, thr_env)
        self.card.add_slider("dur_ms", "Tiempo (ms)", 600, 4000, dur_ms)
    
    def process(self, block, sr):
        """
        Procesa el bloque de audio y calcula el valor de flujo.
        FIX #19: Validación de NaN/Inf en todos los cálculos.
        """
        try:
            # Obtener audio mono y envelope
            x = mono(block)
            env, hop = env_onset(x)
            
            # Validar que tenemos suficientes datos
            if env.size < 5:
                v = 0.0
            else:
                # Calcular ventana de tiempo
                hop_ms = 1000.0 * hop / sr
                win = int(max(5, self.card.get_value("dur_ms") / hop_ms))
                
                # Obtener segmento
                seg = env[-win:]
                
                # Calcular threshold
                threshold = self.card.get_value("thr_env")
                
                # Calcular fracción de valores por encima del threshold
                frac = float(np.mean(seg >= threshold))
                
                # TAREA 2: Validar que frac es un número válido
                if not np.isfinite(frac):
                    frac = 0.0
                    print(f"[FLOW] Warning: NaN/Inf detectado en cálculo, usando 0.0")
                
                # Clip al rango válido
                v = float(np.clip(frac, 0.0, 1.0))
            
            # Actualizar card
            self.card.set_value(v)
            
            # Determinar si el módulo está activo
            lo, hi = self.card.get_thresholds()
            match = self.card.get_match()
            
            # TAREA 2: Validar que todos los valores son finitos antes de comparar
            if np.isfinite(v) and np.isfinite(lo) and np.isfinite(hi) and np.isfinite(match):
                is_active = (lo <= v <= hi) and (int(v * 100) >= match)
            else:
                # Si algún valor es inválido, considerar inactivo
                is_active = False
                print(f"[FLOW] Warning: Valores inválidos detectados (v={v}, lo={lo}, hi={hi}, match={match})")
            
            self.card.set_on(is_active)
            
        except Exception as e:
            # En caso de error, establecer valor seguro
            print(f"[FLOW] Error en process: {e}")
            self.card.set_value(0.0)
            self.card.set_on(False)
    
    def get_status(self):
        """TAREA 2: telemetría con valores efectivos tras mapeo"""
        return {
            "value": self.card.get_value(),
            "is_active": self.card.is_on() if hasattr(self.card, 'is_on') else False,
            "effective_params": {
                "thr_env": self.card.get_value("thr_env"),
                "dur_ms": self.card.get_value("dur_ms"),
                "refractory_ms": self.refractory_ms,
                "hold_ms": self.hold_ms,
                "smoothing": self.smoothing,
                "dens_tgt": self.dens_tgt
            },
            "param_sources": self._param_sources
        }
    
    def reset(self):
        """Reset del módulo"""
        try:
            self.card.set_value(0.0)
            self.card.set_on(False)
        except Exception as e:
            print(f"[FLOW] Error en reset: {e}")