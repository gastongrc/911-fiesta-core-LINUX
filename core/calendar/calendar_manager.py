# core/calendar/calendar_manager.py
"""
CalendarManager v6.4 - Gestor completo del calendario inteligente.

Funcionalidades:
- Polling cada 60 segundos para resolver horarios
- GO manual para forzar modo inmediatamente (con delay opcional)
- Override temporal con duracion configurable
- Alertas previas (5 minutos) con reconfirmacion
- Persistencia de schedule
- Integracion con permisos canonicos

El CalendarManager es GOBERNADOR PASIVO:
- Decide modos y permisos
- NO ejecuta cues
- NO modifica logica musical
- NO bloquea el engine

MODOS CANONICOS:
clima_1, clima_2, clima_3, clima_4, teatro, artista,
boliche_inicio, boliche_desarrollo, boliche_fin, apagado
"""

import threading
import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, List
from enum import Enum
from dataclasses import dataclass

from .calendar_state import (
    CalendarState, CalendarSource, ScheduleBlock,
    PermissionState, OverrideInfo
)
from .calendar_resolver import CalendarResolver
from .calendar_rules import (
    get_permissions, get_available_climates, normalize_mode,
    get_energy_level, get_disabled_states, is_state_allowed,
    CANONICAL_MODES
)


class OverrideType(Enum):
    """Tipos de override"""
    NONE = "none"
    TEMPORARY = "temporary"    # Override temporal con duracion
    PERMANENT = "permanent"    # Override hasta nuevo GO o reset
    UNTIL_NEXT = "until_next"  # Override hasta proximo cambio programado


@dataclass
class OverrideState:
    """Estado del override activo"""
    active: bool = False
    type: OverrideType = OverrideType.NONE
    mode: str = "apagado"
    original_mode: str = "apagado"
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active": self.active,
            "type": self.type.value,
            "mode": self.mode,
            "original_mode": self.original_mode,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "reason": self.reason,
            "remaining_seconds": self._remaining_seconds()
        }

    def _remaining_seconds(self) -> int:
        if not self.active or not self.expires_at:
            return -1
        remaining = (self.expires_at - datetime.now()).total_seconds()
        return max(0, int(remaining))


@dataclass
class UpcomingAlert:
    """Alerta de cambio proximo"""
    mode: str
    change_at: datetime
    minutes_before: int  # 5 minutos (unico umbral)
    acknowledged: bool = False  # Usuario confirmo el cambio

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "change_at": self.change_at.isoformat(),
            "minutes_before": self.minutes_before,
            "seconds_until": max(0, int((self.change_at - datetime.now()).total_seconds())),
            "acknowledged": self.acknowledged
        }


@dataclass
class PendingGo:
    """GO programado con delay"""
    mode: str
    execute_at: datetime
    source: CalendarSource

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "execute_at": self.execute_at.isoformat(),
            "seconds_until": max(0, int((self.execute_at - datetime.now()).total_seconds()))
        }


class CalendarManager:
    """
    Gestor central del calendario inteligente v6.4.

    Provee una interfaz completa para:
    - Consultar el modo/clima actual
    - Obtener permisos del modo activo
    - GO manual para cambiar modo (con delay opcional)
    - Override temporal/permanente
    - Alertas de cambios proximos (5 min)
    - Persistencia del schedule
    """

    # Intervalo de polling en segundos
    POLL_INTERVAL = 60

    # Umbral de alerta (5 minutos antes del cambio)
    ALERT_THRESHOLD_MINUTES = 5

    def __init__(self, config_path: Optional[str] = None, system_bridge=None):
        """
        Inicializa el CalendarManager.

        Args:
            config_path: Ruta al archivo calendar.json (opcional)
            system_bridge: Referencia al SystemBridge para aplicar reglas (opcional)
        """
        # Referencia al SystemBridge para aplicar reglas automáticamente
        self._system_bridge = system_bridge

        # Determinar ruta del config
        if config_path is None:
            # Primero intentar config/calendar.json
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(base_dir, "config", "calendar.json")

            # Si no existe, usar el de core/calendar/calendar.json
            if not os.path.exists(config_path):
                config_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "calendar.json"
                )

        self._config_path = config_path

        # Estado interno
        self._state = CalendarState()
        self._state.since = datetime.now()
        self._update_permissions()

        # Override state
        self._override = OverrideState()

        # Alerta activa
        self._active_alert: Optional[UpcomingAlert] = None
        self._fired_alerts: set = set()  # IDs de alertas ya disparadas

        # GO pendiente (con delay)
        self._pending_go: Optional[PendingGo] = None

        # Resolver de horarios
        self._resolver = CalendarResolver(config_path)

        # Threading
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._running = False

        # Callbacks
        self._on_mode_change: Optional[Callable[[str, str, PermissionState], None]] = None
        self._on_alert: Optional[Callable[[UpcomingAlert], None]] = None
        self._on_override_expired: Optional[Callable[[], None]] = None

        # Primera resolucion
        self._resolve_now()

        # Iniciar polling automatico
        self._start_polling()

        print("[CalendarManager] v6.4 Inicializado - polling cada 60s")
        print(f"[CAL_BOOT] app_id={id(self)} cwd={os.getcwd()} cal_abs_path={os.path.abspath(self._config_path)}")

        # Aplicar estado inicial si hay system_bridge
        if self._system_bridge is not None:
            try:
                actions_str = f" + {self._state.current_actions}" if self._state.current_actions else ""
                print(f"[Calendar] initial state → {self._state.current_mode}{actions_str}")
                self._system_bridge.apply_calendar_state(
                    self._state.current_mode,
                    self._state.current_actions
                )
            except Exception as e:
                print(f"[Calendar] error applying initial state: {e}")

    def set_system_bridge(self, system_bridge) -> None:
        """
        Establece el SystemBridge después de la inicialización.

        Args:
            system_bridge: Instancia de SystemBridge
        """
        self._system_bridge = system_bridge
        print("[Calendar] SystemBridge connected")

        # Aplicar estado actual inmediatamente
        if self._system_bridge is not None:
            try:
                actions_str = f" + {self._state.current_actions}" if self._state.current_actions else ""
                print(f"[Calendar] syncing state → {self._state.current_mode}{actions_str}")
                self._system_bridge.apply_calendar_state(
                    self._state.current_mode,
                    self._state.current_actions
                )
            except Exception as e:
                print(f"[Calendar] error syncing state: {e}")

    # ==================== POLLING ====================

    def _start_polling(self) -> None:
        """Inicia el timer de polling"""
        self._running = True
        self._schedule_next_poll()

    def _schedule_next_poll(self) -> None:
        """Programa el proximo poll"""
        if not self._running:
            return

        self._timer = threading.Timer(self.POLL_INTERVAL, self._poll_tick)
        self._timer.daemon = True
        self._timer.start()

    def _poll_tick(self) -> None:
        """Tick del polling - se ejecuta cada 60 segundos"""
        if not self._running:
            return

        try:
            self._check_pending_go()
            self._check_override_expiry()
            self._resolve_now()
            self._check_alerts()
        except Exception as e:
            print(f"[CalendarManager] Error en poll: {e}")

        self._schedule_next_poll()

    def _resolve_now(self) -> None:
        """
        Resuelve el modo actual basado en la hora.
        Respeta overrides activos.

        V6.5 FIX: Cuando NO hay bloque activo, aplica ZZZ (apagado).
        Esto garantiza teardown completo entre bloques.
        """
        now = datetime.now()

        with self._lock:
            # Si hay override activo, no resolver automaticamente
            if self._override.active:
                print(f"[CAL_RESOLVE] skip reason=override_active mode={self._override.mode}")
                self._state.update_progress(now)
                return

            # Resolver modo desde horario
            mode, block, next_change = self._resolver.resolve(now)

            # V6.5 FIX: Si no hay bloque activo, aplicar ZZZ (apagado)
            if mode is None:
                old_mode = self._state.current_mode
                zzz_mode = "apagado"

                # Solo aplicar si realmente cambia a ZZZ
                if old_mode != zzz_mode:
                    self._state.current_mode = zzz_mode
                    self._state.source = CalendarSource.AUTO
                    self._state.since = now
                    self._state.active_block = None
                    self._state.current_actions = []
                    self._update_permissions()

                    # Resetear alertas
                    self._fired_alerts.clear()
                    self._active_alert = None

                    # ===== APLICAR ZZZ VÍA SYSTEM BRIDGE =====
                    if self._system_bridge is not None:
                        try:
                            print(f"[CALENDAR] ZZZ (no active block) - was: {old_mode}")
                            self._system_bridge.apply_calendar_state(zzz_mode, [])
                        except Exception as e:
                            print(f"[Calendar] error applying ZZZ: {e}")

                    # Notificar cambio a ZZZ
                    if self._on_mode_change:
                        try:
                            self._on_mode_change(old_mode, zzz_mode, self._state.permissions)
                        except Exception as e:
                            print(f"[Calendar] error in ZZZ callback: {e}")

                self._state.update_progress(now)
                self._state.next_change_at = next_change
                self._state.next_mode = None
                return

            # Normalizar modo a canonico
            canonical_mode = normalize_mode(mode)

            # Verificar si cambió el modo o las actions
            old_mode = self._state.current_mode
            old_actions = set(self._state.current_actions)
            new_actions = block.actions.copy() if block else []
            new_actions_set = set(new_actions)

            mode_changed = canonical_mode != old_mode
            actions_changed = new_actions_set != old_actions

            # V10: Aplicar si modo O actions cambiaron (enforce Vision)
            if mode_changed or actions_changed:
                self._state.current_mode = canonical_mode
                self._state.source = CalendarSource.AUTO
                self._state.since = now
                self._state.active_block = block
                self._state.current_actions = new_actions
                self._update_permissions()

                if mode_changed:
                    # Resetear alertas disparadas para el nuevo bloque
                    self._fired_alerts.clear()
                    self._active_alert = None

                # ===== APLICAR ESTADO VÍA SYSTEM BRIDGE =====
                # V10: Aplica si modo O actions cambiaron (enforce Vision)
                if self._system_bridge is not None:
                    try:
                        change_reason = "mode" if mode_changed else "actions"
                        actions_str = f" actions={new_actions}" if new_actions else ""
                        print(f"[Calendar] {change_reason} changed → {canonical_mode}{actions_str}")
                        self._system_bridge.apply_calendar_state(
                            canonical_mode,
                            new_actions
                        )
                    except Exception as e:
                        print(f"[Calendar] error applying state: {e}")

                # Notificar cambio (callback legacy para UI)
                if self._on_mode_change and mode_changed:
                    try:
                        self._on_mode_change(old_mode, canonical_mode, self._state.permissions)
                    except Exception as e:
                        print(f"[Calendar] error in callback: {e}")

            # Actualizar info de timeline
            self._state.active_block = block
            self._state.current_actions = new_actions
            self._state.next_change_at = next_change
            self._state.update_progress(now)

            # Calcular proximo modo
            if next_change:
                next_mode, _, _ = self._resolver.resolve(next_change)
                self._state.next_mode = normalize_mode(next_mode) if next_mode else None

    def _update_permissions(self) -> None:
        """Actualiza los permisos basados en el modo actual"""
        perms = get_permissions(self._state.current_mode)
        self._state.permissions = PermissionState.from_dict(perms)

    def _check_pending_go(self) -> None:
        """Verifica si hay un GO pendiente que deba ejecutarse"""
        with self._lock:
            if not self._pending_go:
                return

            if datetime.now() >= self._pending_go.execute_at:
                mode = self._pending_go.mode
                source = self._pending_go.source
                self._pending_go = None
                print(f"[CalendarManager] Ejecutando GO programado: {mode}")

        # Ejecutar fuera del lock
        if mode:
            self.go(mode, source)

    def _check_override_expiry(self) -> None:
        """Verifica si el override temporal expiro"""
        with self._lock:
            if not self._override.active:
                return

            if self._override.type == OverrideType.TEMPORARY:
                if self._override.expires_at and datetime.now() >= self._override.expires_at:
                    print("[CalendarManager] Override temporal expirado")
                    self._clear_override_internal()

                    if self._on_override_expired:
                        try:
                            self._on_override_expired()
                        except Exception as e:
                            print(f"[CalendarManager] Error en callback override: {e}")

    def _check_alerts(self) -> None:
        """Verifica y dispara alertas de cambios proximos (5 min)"""
        with self._lock:
            if not self._state.next_change_at or not self._state.next_mode:
                self._active_alert = None
                return

            now = datetime.now()
            next_change = self._state.next_change_at
            next_mode = self._state.next_mode

            # Solo alerta a 5 minutos
            alert_id = f"{next_change.isoformat()}_5"

            if alert_id in self._fired_alerts:
                return

            alert_time = next_change - timedelta(minutes=self.ALERT_THRESHOLD_MINUTES)
            if now >= alert_time:
                # Crear alerta
                self._active_alert = UpcomingAlert(
                    mode=next_mode,
                    change_at=next_change,
                    minutes_before=self.ALERT_THRESHOLD_MINUTES,
                    acknowledged=False
                )

                self._fired_alerts.add(alert_id)
                print(f"[CalendarManager] ALERTA: Cambio a {next_mode} en 5 min")

                if self._on_alert:
                    try:
                        self._on_alert(self._active_alert)
                    except Exception as e:
                        print(f"[CalendarManager] Error en callback alerta: {e}")

    def stop(self) -> None:
        """Detiene el polling"""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        print("[CalendarManager] Polling detenido")

    # ==================== GO MANUAL ====================

    def go(self, mode: str, source: CalendarSource = CalendarSource.MANUAL,
           delay_minutes: int = 0) -> bool:
        """
        GO manual - Cambia el modo inmediatamente o con delay.

        Esto es un cambio directo, NO un override. El modo automatico
        seguira intentando cambiar segun el horario.

        Args:
            mode: Nombre del modo a establecer
            source: Fuente del cambio
            delay_minutes: Minutos de delay (0, 5, 10, 15)

        Returns:
            True si el cambio fue exitoso o programado
        """
        # Normalizar modo
        canonical_mode = normalize_mode(mode)

        # Si hay delay, programar para despues
        if delay_minutes > 0:
            with self._lock:
                self._pending_go = PendingGo(
                    mode=canonical_mode,
                    execute_at=datetime.now() + timedelta(minutes=delay_minutes),
                    source=source
                )
                print(f"[CalendarManager] GO programado: {canonical_mode} en {delay_minutes} min")
            return True

        # Ejecutar inmediatamente
        with self._lock:
            # Limpiar override si habia uno
            if self._override.active:
                self._clear_override_internal()

            # Cancelar GO pendiente si habia
            self._pending_go = None

            old_mode = self._state.current_mode
            self._state.current_mode = canonical_mode
            self._state.source = source
            self._state.since = datetime.now()
            self._state.active_block = None
            # v6.4: GO manual no tiene acciones paralelas
            self._state.current_actions = []
            self._update_permissions()

            # Limpiar alerta activa
            self._active_alert = None

            # ===== APLICAR ESTADO VÍA SYSTEM BRIDGE =====
            # GO manual no tiene actions
            if self._system_bridge is not None and old_mode != canonical_mode:
                try:
                    print(f"[Calendar] GO → {canonical_mode}")
                    self._system_bridge.apply_calendar_state(
                        canonical_mode,
                        []  # GO manual: sin actions
                    )
                except Exception as e:
                    print(f"[Calendar] error applying GO: {e}")

            if self._on_mode_change and old_mode != canonical_mode:
                try:
                    self._on_mode_change(old_mode, canonical_mode, self._state.permissions)
                except Exception as e:
                    print(f"[Calendar] error in callback: {e}")

        return True

    def cancel_pending_go(self) -> bool:
        """Cancela un GO programado con delay"""
        with self._lock:
            if self._pending_go:
                print(f"[CalendarManager] GO cancelado: {self._pending_go.mode}")
                self._pending_go = None
                return True
            return False

    def get_pending_go(self) -> Optional[Dict[str, Any]]:
        """Obtiene info del GO pendiente"""
        with self._lock:
            if self._pending_go:
                return self._pending_go.to_dict()
            return None

    # ==================== OVERRIDE ====================

    def set_override(
        self,
        mode: str,
        override_type: OverrideType = OverrideType.TEMPORARY,
        duration_minutes: int = 30,
        reason: str = ""
    ) -> bool:
        """
        Establece un override temporal o permanente.

        Durante el override, el calendario NO cambiara automaticamente.

        Args:
            mode: Modo a forzar
            override_type: Tipo de override
            duration_minutes: Duracion en minutos (para TEMPORARY)
            reason: Razon del override (para logging)

        Returns:
            True si se establecio correctamente
        """
        canonical_mode = normalize_mode(mode)
        now = datetime.now()

        with self._lock:
            old_mode = self._state.current_mode

            # Configurar override
            self._override.active = True
            self._override.type = override_type
            self._override.mode = canonical_mode
            self._override.original_mode = old_mode
            self._override.started_at = now
            self._override.reason = reason

            if override_type == OverrideType.TEMPORARY:
                self._override.expires_at = now + timedelta(minutes=duration_minutes)
            else:
                self._override.expires_at = None

            # Aplicar modo
            self._state.current_mode = canonical_mode
            self._state.source = CalendarSource.OVERRIDE
            self._state.since = now
            # v6.4: Override no tiene acciones paralelas
            self._state.current_actions = []
            self._state.override = OverrideInfo(
                mode=canonical_mode,
                original_mode=old_mode,
                started_at=now,
                expires_at=self._override.expires_at,
                reason=reason
            )
            self._update_permissions()

            # ===== APLICAR ESTADO VÍA SYSTEM BRIDGE =====
            # Override no tiene actions
            if self._system_bridge is not None and old_mode != canonical_mode:
                try:
                    reason_str = f" ({reason})" if reason else ""
                    print(f"[Calendar] OVERRIDE → {canonical_mode}{reason_str}")
                    self._system_bridge.apply_calendar_state(
                        canonical_mode,
                        []  # Override: sin actions
                    )
                except Exception as e:
                    print(f"[Calendar] error applying override: {e}")

            if self._on_mode_change and old_mode != canonical_mode:
                try:
                    self._on_mode_change(old_mode, canonical_mode, self._state.permissions)
                except Exception as e:
                    print(f"[Calendar] error in callback: {e}")

        return True

    def clear_override(self) -> None:
        """Limpia el override activo y vuelve al modo automatico"""
        with self._lock:
            if self._override.active:
                print("[CalendarManager] Override limpiado manualmente")
                self._clear_override_internal()
                self._state.override = None

        # Re-resolver inmediatamente
        self._resolve_now()

    def _clear_override_internal(self) -> None:
        """Limpia el override (sin lock)"""
        self._override.active = False
        self._override.type = OverrideType.NONE
        self._override.mode = "apagado"
        self._override.original_mode = "apagado"
        self._override.started_at = None
        self._override.expires_at = None
        self._override.reason = ""

    def get_override_state(self) -> Dict[str, Any]:
        """Obtiene el estado del override"""
        with self._lock:
            return self._override.to_dict()

    def is_override_active(self) -> bool:
        """Verifica si hay un override activo"""
        with self._lock:
            return self._override.active

    # ==================== ALERTAS ====================

    def acknowledge_alert(self) -> bool:
        """Usuario confirma la alerta de cambio proximo"""
        with self._lock:
            if self._active_alert and not self._active_alert.acknowledged:
                self._active_alert.acknowledged = True
                print("[CalendarManager] Alerta confirmada por usuario")
                return True
            return False

    def get_active_alert(self) -> Optional[Dict[str, Any]]:
        """Obtiene la alerta activa si hay una"""
        with self._lock:
            if self._active_alert:
                return self._active_alert.to_dict()
            return None

    def has_pending_alert(self) -> bool:
        """Verifica si hay una alerta pendiente sin confirmar"""
        with self._lock:
            return self._active_alert is not None and not self._active_alert.acknowledged

    # ==================== API PUBLICA ====================

    def get_state(self) -> Dict[str, Any]:
        """
        Obtiene el estado completo del calendario.

        Returns:
            Dict con estado completo incluyendo override y alertas
        """
        with self._lock:
            self._state.update_progress(datetime.now())

            # Calcular tiempo restante hasta proximo cambio
            time_remaining = -1
            next_change_str = None
            if self._state.next_change_at:
                time_remaining = max(0, int((self._state.next_change_at - datetime.now()).total_seconds()))
                next_change_str = self._state.next_change_at.strftime("%H:%M")

            result = {
                **self._state.to_dict(),
                "available_modes": CANONICAL_MODES.copy(),
                "auto_mode_enabled": self._resolver.is_auto_mode_enabled(),
                "override": self._override.to_dict(),
                "next_change_display": next_change_str,
                "time_remaining_display": self._format_time_remaining(time_remaining),
                "is_override": self._override.active,
                "alert": self._active_alert.to_dict() if self._active_alert else None,
                "pending_go": self._pending_go.to_dict() if self._pending_go else None
            }

            return result

    def _format_time_remaining(self, seconds: int) -> str:
        """Formatea segundos restantes para display"""
        if seconds < 0:
            return "---"
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h {mins}m"

    def get_permissions(self) -> Dict[str, Any]:
        """Obtiene los permisos del modo actual"""
        with self._lock:
            return self._state.permissions.to_dict()

    def get_current_mode(self) -> str:
        """Obtiene el modo actual (canonico)"""
        with self._lock:
            return self._state.current_mode

    # Alias para compatibilidad
    def get_current_climate(self) -> str:
        """Alias para compatibilidad"""
        return self.get_current_mode()

    def is_permitted(self, permission: str) -> bool:
        """Verifica si un permiso especifico esta habilitado"""
        with self._lock:
            return getattr(self._state.permissions, permission, False)

    def is_state_allowed(self, state: str) -> bool:
        """Verifica si un estado de CueEngine esta permitido"""
        with self._lock:
            return self._state.is_state_allowed(state)

    def get_energy_level(self) -> Optional[str]:
        """Obtiene el nivel de energia del modo actual"""
        with self._lock:
            return self._state.permissions.energy

    def get_active_block_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene snapshot del bloque activo actual.

        V6.5: Para que la UI pueda destacar el bloque activo en el editor.
        Genera un block_id determinístico basado en day + from + to + mode.

        Returns:
            Dict con: day, from_time, to_time, mode, actions, block_id
            None si no hay bloque activo
        """
        with self._lock:
            block = self._state.active_block
            if not block:
                return None

            # Generar block_id determinístico con pipe separator
            block_id = f"{block.day or 'unknown'}|{block.from_time}|{block.to_time}|{block.mode}"

            return {
                "day": block.day,
                "from_time": block.from_time,
                "to_time": block.to_time,
                "mode": block.mode,
                "actions": block.actions.copy() if block.actions else [],
                "block_id": block_id,
            }

    def set_auto_mode(self, enabled: bool) -> None:
        """Habilita/deshabilita el modo automatico"""
        self._resolver.set_auto_mode(enabled)
        if enabled:
            self.clear_override()

    # ==================== PERSISTENCIA ====================

    def save_schedule(self, schedule: Dict[str, Any]) -> bool:
        """
        Guarda el schedule al archivo y aplica inmediatamente.

        Args:
            schedule: Dict con el schedule en formato {week: {...}}

        Returns:
            True si guardo correctamente
        """
        try:
            # Asegurar que existe el directorio
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)

            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(schedule, f, indent=2, ensure_ascii=False)

            print(f"[CALENDAR] save ok → {self._config_path}")

            # Recargar schedule desde archivo
            self._resolver.reload_schedule()
            print("[CALENDAR] reload ok")

            # Guardar estado previo para comparar
            old_mode = self._state.current_mode
            old_actions = list(self._state.current_actions)

            # Resolver modo actual con nuevo schedule
            self._resolve_now()

            # Log del resultado de resolve
            new_mode = self._state.current_mode
            new_actions = self._state.current_actions
            next_mode = self._state.next_mode
            next_change = self._state.next_change_at

            time_to_next = "---"
            if next_change:
                secs = int((next_change - datetime.now()).total_seconds())
                time_to_next = f"{secs}s" if secs < 60 else f"{secs // 60}m"

            print(f"[CALENDAR] resolved → mode={new_mode}, next={next_mode}, time_to_next={time_to_next}")

            # Log si hubo cambio y se aplicó
            if new_mode != old_mode or set(new_actions) != set(old_actions):
                actions_str = f", actions={new_actions}" if new_actions else ""
                print(f"[CALENDAR] applied → mode={new_mode}{actions_str}")
            else:
                print(f"[CALENDAR] no change (mode={new_mode} already active)")

            return True

        except Exception as e:
            print(f"[CALENDAR] save FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False

    def commit_from_remote(self, week: Dict[str, Any], source: str = "web") -> Dict[str, Any]:
        """
        Commit completo desde web: atomic write + reload + resolve + forced apply.

        A diferencia de save_schedule(), este método:
        - Usa escritura atómica (.tmp + rename)
        - Fuerza apply vía SystemBridge SIEMPRE (incluso si el modo no cambió)
        - Genera req_id para trazabilidad end-to-end
        - Retorna dict con resultado detallado para respuesta HTTP

        Args:
            week: Dict con schedule semanal {monday: [...], ...}
            source: Origen del cambio (default "web")

        Returns:
            Dict con {ok, req_id, applied, mode, actions, reason}
        """
        req_id = uuid.uuid4().hex[:8]
        print(f"[CAL_RECV] req_id={req_id} source={source} days={list(week.keys())}")

        try:
            schedule = {"week": week}

            # --- Atomic write: .tmp + rename ---
            dir_path = os.path.dirname(self._config_path)
            os.makedirs(dir_path, exist_ok=True)

            tmp_fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp", prefix="calendar_", dir=dir_path
            )
            try:
                with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                    json.dump(schedule, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self._config_path)
            except BaseException:
                # Cleanup tmp on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            print(f"[CAL_WRITE_OK] req_id={req_id} path={self._config_path}")

            # --- Reload schedule from disk ---
            self._resolver.reload_schedule()
            print(f"[CAL_RELOAD_OK] req_id={req_id}")

            # --- Resolve NOW ---
            old_mode = self._state.current_mode
            old_actions = list(self._state.current_actions)
            self._resolve_now()
            new_mode = self._state.current_mode
            new_actions = list(self._state.current_actions)

            print(f"[CAL_RESOLVE] req_id={req_id} mode={new_mode} prev={old_mode} actions={new_actions}")

            # --- Forced apply via SystemBridge ---
            applied = False
            reason = "no_bridge"
            has_bridge = self._system_bridge is not None

            if has_bridge:
                try:
                    self._system_bridge.apply_calendar_state(new_mode, new_actions)
                    applied = True
                    if new_mode != old_mode or set(new_actions) != set(old_actions):
                        reason = "changed"
                    else:
                        reason = "forced_reapply"
                except Exception as e:
                    reason = f"apply_error:{e}"
            else:
                reason = "no_bridge"

            print(f"[CAL_APPLY] req_id={req_id} applied={applied} reason={reason} bridge={has_bridge}")

            return {
                "ok": True,
                "req_id": req_id,
                "applied": applied,
                "mode": new_mode,
                "actions": new_actions,
                "reason": reason,
            }

        except Exception as e:
            print(f"[CAL_APPLY] req_id={req_id} applied=false reason=exception:{e} bridge={self._system_bridge is not None}")
            return {
                "ok": False,
                "req_id": req_id,
                "applied": False,
                "mode": self._state.current_mode,
                "actions": list(self._state.current_actions),
                "reason": f"exception:{e}",
            }

    def get_schedule(self) -> Dict[str, Any]:
        """
        Obtiene el schedule actual.

        Returns:
            Dict con el schedule completo
        """
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[CalendarManager] Error leyendo schedule: {e}")

        return {"week": {
            "monday": [], "tuesday": [], "wednesday": [],
            "thursday": [], "friday": [], "saturday": [], "sunday": []
        }}

    def reload_schedule(self) -> bool:
        """Recarga el schedule desde disco"""
        result = self._resolver.reload_schedule()
        if result:
            self._resolve_now()
        return result

    # ==================== CALLBACKS ====================

    def on_mode_change(self, callback: Callable[[str, str, PermissionState], None]) -> None:
        """Registra callback para cambios de modo"""
        self._on_mode_change = callback

    def on_alert(self, callback: Callable[[UpcomingAlert], None]) -> None:
        """Registra callback para alertas de cambios proximos"""
        self._on_alert = callback

    def on_override_expired(self, callback: Callable[[], None]) -> None:
        """Registra callback para cuando expira un override"""
        self._on_override_expired = callback

    # ==================== DEBUG ====================

    def get_schedule_info(self) -> Dict[str, Any]:
        """Obtiene informacion del schedule cargado"""
        return self._resolver.get_schedule_info()

    def force_resolve(self) -> None:
        """Fuerza una resolucion inmediata"""
        self._resolve_now()

    def reapply_active_block(self, mode: str, actions: list) -> bool:
        """
        V9.4: Reaplica el estado del bloque activo con nuevas acciones.

        Llamado cuando el usuario edita el bloque activo en la UI.
        No espera al polling, aplica inmediatamente.

        Args:
            mode: Modo del bloque (debe coincidir con el modo actual)
            actions: Lista de acciones actualizada

        Returns:
            True si se aplicó correctamente
        """
        with self._lock:
            # Verificar que estamos editando el bloque activo
            if not self._state.active_block:
                print(f"[Calendar] reapply_active_block SKIPPED (no active block)")
                return False

            # Actualizar acciones en el estado interno
            self._state.current_actions = actions.copy()

            # Aplicar via SystemBridge
            if self._system_bridge is not None:
                try:
                    print(f"[Calendar] REAPPLY active block → mode={mode} actions={actions}")
                    self._system_bridge.apply_calendar_state(mode, actions)
                    print(f"[Calendar] REAPPLY complete")
                    return True
                except Exception as e:
                    print(f"[Calendar] error in reapply_active_block: {e}")
                    import traceback
                    traceback.print_exc()
                    return False
            else:
                print("[Calendar] reapply_active_block SKIPPED (no system_bridge)")
                return False

    def get_debug_info(self) -> Dict[str, Any]:
        """Obtiene informacion de debug completa"""
        with self._lock:
            return {
                "state": self._state.to_dict(),
                "override": self._override.to_dict(),
                "schedule_info": self._resolver.get_schedule_info(),
                "fired_alerts": list(self._fired_alerts),
                "pending_go": self._pending_go.to_dict() if self._pending_go else None,
                "active_alert": self._active_alert.to_dict() if self._active_alert else None,
                "running": self._running
            }
