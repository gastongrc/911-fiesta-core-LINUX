# ============================================================================
# avolites_config.py v5.1 - TITAN TRANSPORT LEGACY COMPATIBILITY MODE
# ============================================================================
# FIX v5.1 - MODO COMPATIBILIDAD LEGACY:
# - TitanSync DESACTIVADO (consolas antiguas no tienen endpoints)
# - FIRE/KILL SIEMPRE permitidos (sin bloqueo por NOT_READY)
# - Sin health-check obligatorio
# - Solo endpoints clasicos HTTP (FirePlaybackAtLevel, KillPlayback)
# - TitanQueue mantiene garantia OFF atomica
#
# REFACTOR v5.0 previo:
# - TitanQueue para cola asincrona con prioridad KILL > FIRE
# - TitanTransport para envio HTTP con reintentos
# - Backward compatible: mantiene API publica
#
# Controller Titan WebAPI v1 - LEGACY MODE
# - Worker asincrono con cola prioritaria via TitanQueue
# - Sin TitanStateSync (desactivado para consolas legacy)
# - FIRE/KILL siempre se encolan (sin backpressure bloqueante)
# ============================================================================

from __future__ import annotations

import json
import os
import time
import ipaddress
import threading
from typing import Dict, Any, Optional, Callable, List, Set, Tuple, Union
from enum import Enum

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import SSLError, RequestException

# Importar sistema de transporte (TitanSync desactivado para legacy)
from core.transport import (
    TitanTransport,
    TransportConfig,
    TitanQueue,
    QueueConfig,
    # TitanStateSync desactivado - consolas legacy no soportan GetActivePlaybacks
    # TitanStateSync,
    # SyncConfig,
)

# Art-Net DMX transport
from core.transport.dmx_state import DmxState
from core.transport.artnet_engine import ArtNetEngine
from core.transport.cue_output_adapter import CueOutputAdapter

# sACN (E1.31) DMX transport
from core.transport.sacn_engine import SacnEngine

# ===== CONFIGURACION =====
CONFIG_FILE = "avolites_config.json"

DEDUP_WINDOW_MS = 50
FAMILY_COOLDOWN_MS = 120
ZERO_REINFORCE_FRAMES = 2

# Limites de cola (ahora manejados por TitanQueue)
MAX_QUEUE_SIZE = 512


# ===== ESTADOS DE CONEXION =====
class ConnectionState(Enum):
    """Estados de conexion del controlador."""
    NOT_READY = "NOT_READY"  # Sin sesion o sin ping OK
    READY = "READY"          # Sesion establecida y ping OK


class CircuitBreakerState(Enum):
    """Estados del circuit breaker."""
    CLOSED = "CLOSED"        # Funcionando normal
    HALF_OPEN = "HALF_OPEN"  # Probando recuperacion
    OPEN = "OPEN"            # Circuito abierto, bloqueado


# ===== UTILIDADES =====
def safe_decode(data: Any) -> str:
    """
    Decodifica string robustamente, manejando mojibake y encodings mixtos.
    Util para parsear salida de ipconfig en Windows con idioma espanol.
    """
    if isinstance(data, bytes):
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                return data.decode(encoding)
            except (UnicodeDecodeError, AttributeError):
                continue
        return data.decode('utf-8', errors='replace')
    elif isinstance(data, str):
        try:
            return data.encode('utf-8', errors='ignore').decode('utf-8')
        except:
            return data
    else:
        return str(data)


def is_valid_private_ip(ip_str: str) -> bool:
    """
    Valida que una IP sea valida y privada (10.x, 172.16-31.x, 192.168.x.x).
    Rechaza 0.0.0.x y otras IPs invalidas.
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str.strip())
        if ip_obj.version != 4:
            return False
        if ip_str.startswith('0.'):
            return False
        return ip_obj.is_private
    except (ValueError, AttributeError):
        return False


# ===== CONFIGURACION =====
class AvolitesConfig:
    """Gestor de configuracion JSON."""

    @classmethod
    def default_config(cls) -> Dict[str, Any]:
        """Configuracion por defecto."""
        return {
            "console_ip": "192.168.1.20",
            "console_port": 80,
            "endpoint_type": "Titan",
            "auto_detect": False,
            "connect_timeout": 1.2,
            "read_timeout": 1.0,
            "connection_timeout": 5.0,
            "last_successful_ip": None,
            "local_ip": None,
            "transport": "http",
            "user_number_offset": 169,
            "titanid_mapping": {},
            "discovered_titanids": {},
            "families": {},
            "labels": {}
        }

    def __init__(self):
        self.config_file = CONFIG_FILE
        self.default_config = self.default_config()
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Carga configuracion desde JSON."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                print(f"[AVOLITES] Config cargada desde {self.config_file}")

                merged = {**self.default_config, **cfg}

                console_ip = merged.get("console_ip", "")
                if console_ip and not is_valid_private_ip(console_ip):
                    print(f"[AVOLITES] WARNING: console_ip '{console_ip}' invalida, usando default")
                    merged["console_ip"] = self.default_config["console_ip"]

                return merged

            except Exception as e:
                print(f"[AVOLITES] Error cargando config: {e}")

        print("[AVOLITES] Creando config inicial...")
        return self.default_config.copy()

    def save_config(self) -> bool:
        """Guarda configuracion a JSON."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            print(f"[AVOLITES] Config guardada en {self.config_file}")
            return True
        except Exception as e:
            print(f"[AVOLITES] Error guardando config: {e}")
            return False


# ===== ADAPTER HTTP CON SOURCE IP =====
class FixedSourceHTTPAdapter(HTTPAdapter):
    """HTTPAdapter que fuerza una source IP especifica."""

    def __init__(self, source_ip: str, *args, **kwargs):
        self.source_ip = source_ip
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['source_address'] = (self.source_ip, 0)
        return super().init_poolmanager(*args, **kwargs)


# ===== CONTROLLER PRINCIPAL =====
class AvolitesController:
    """
    Titan WebAPI v1 controller v5.1 - LEGACY COMPATIBILITY MODE

    Features:
    - TitanQueue: Cola asincrona con prioridad KILL > FIRE
    - TitanTransport: Envio HTTP con reintentos automaticos
    - TitanStateSync: DESACTIVADO (legacy no soporta endpoints modernos)
    - Garantia OFF atomica: ON nunca sin OFF previo
    - FIRE/KILL SIEMPRE permitidos (sin bloqueo NOT_READY)
    - Backward compatible: mantiene API fire_cue/kill_cue
    """

    def __init__(self, verbose: bool = True, auto_connect: bool = False):
        self.verbose = bool(verbose)
        self.config_manager = AvolitesConfig()

        # Estado de conexion - LEGACY MODE: SIEMPRE READY
        # Consolas antiguas no tienen endpoints de health-check
        self.connection_state = ConnectionState.READY  # SIEMPRE READY en modo legacy
        self.cb_state = CircuitBreakerState.CLOSED

        # Cues activos (ahora sincronizado con TitanQueue)
        self._active_cues: Set[int] = set()
        self._active_lock = threading.Lock()

        # Handlers
        self._fire_handlers: List[Callable[[int], None]] = []
        self._kill_handlers: List[Callable[[int], None]] = []

        # Metricas
        self._last_send_ms: Optional[float] = None
        self._last_error_short: Optional[str] = None
        self._last_fire_ts: Optional[float] = None
        self.last_tx: List[Dict[str, Any]] = []
        self._dropped_not_ready: int = 0
        self._dropped_queue_full: int = 0

        # Estado HTTP
        self._last_send_ts: float = 0.0
        self._last_success_ts: float = 0.0
        self._consec_fail: int = 0
        self._sticky_window_s: float = 90.0
        self.is_connected: bool = True  # LEGACY MODE: siempre conectado
        self._status_cache: Dict[str, Any] = {
            "connected": True,  # LEGACY MODE: siempre conectado
            "version": "Legacy Mode",
            "last_ping": 0.0,
        }
        self._last_error: Optional[str] = None

        # Circuit breaker
        self._fail_timestamps: List[float] = []
        self._circuit_open_until: float = 0.0
        self._max_consecutive_fails: int = 5
        self._fail_window: float = 10.0
        self._circuit_break_duration: float = 5.0
        self._cb_half_open_since: float = 0.0

        self._current_target: Optional[Tuple[str, int]] = None

        self.transport: str = self.config_manager.config.get("transport", "http")

        # ===== CREAR SISTEMA DE TRANSPORTE (LEGACY MODE) =====
        self._transport_config = self._create_transport_config()
        self._queue_config = self._create_queue_config()
        # self._sync_config = self._create_sync_config()  # DESACTIVADO en legacy

        # TitanQueue con callbacks
        self._titan_queue = TitanQueue(
            transport_config=self._transport_config,
            queue_config=self._queue_config,
            on_fire_success=self._on_fire_success,
            on_kill_success=self._on_kill_success,
            on_fire_fail=self._on_fire_fail,
            on_kill_fail=self._on_kill_fail,
        )

        # TitanStateSync DESACTIVADO - Consolas legacy no soportan GetActivePlaybacks
        # self._titan_sync = TitanStateSync(...)
        self._titan_sync = None  # Placeholder para compatibilidad

        # ===== ART-NET DMX TRANSPORT =====
        self._dmx_state: Optional[DmxState] = None
        self._artnet_engine: Optional[ArtNetEngine] = None
        self._cue_adapter: Optional[CueOutputAdapter] = None
        self._artnet_active = False

        # ===== sACN (E1.31) DMX TRANSPORT =====
        self._sacn_engine: Optional[SacnEngine] = None
        self._sacn_active = False

        # Iniciar servicios según transporte configurado
        if self.transport == "artnet":
            self._start_artnet()
        elif self.transport == "sacn":
            self._start_sacn()
        else:
            self._titan_queue.start()

        # Session para ping y BPM (operaciones directas)
        self.session: Optional[requests.Session] = None
        self._setup_session()

        # Log user_number mapping samples
        try:
            samples = [1, 10, 28, 41, 42]
            print("[Avo map]", [(x, self._map_user_number(x)) for x in samples])
        except Exception:
            pass

        if self._artnet_active:
            print("[AVOLITES] v5.2 ART-NET MODE - ArtNetEngine activo, TitanQueue inactivo")
        elif self._sacn_active:
            print("[AVOLITES] v5.3 sACN MODE - SacnEngine activo, TitanQueue inactivo")
        else:
            print("[AVOLITES] v5.1 LEGACY MODE - TitanQueue activo, TitanSync desactivado")

        if auto_connect:
            self.connect()

    def _create_transport_config(self) -> TransportConfig:
        """Crea config para TitanTransport."""
        cfg = self.config_manager.config
        return TransportConfig(
            console_ip=cfg.get("console_ip", "192.168.1.20"),
            console_port=cfg.get("console_port", 80),
            transport=cfg.get("transport", "http"),
            connect_timeout=cfg.get("connect_timeout", 1.2),
            read_timeout=cfg.get("read_timeout", 1.0),
            max_retries=3,
            retry_delays=(0.05, 0.1, 0.2),
            user_number_offset=cfg.get("user_number_offset", 169),
        )

    def _create_queue_config(self) -> QueueConfig:
        """Crea config para TitanQueue."""
        return QueueConfig(
            max_queue_size=MAX_QUEUE_SIZE,
            rate_limit_ms=60.0,
            max_retries=3,
            retry_delay_ms=100.0,
            dedup_window_ms=DEDUP_WINDOW_MS,
            kill_block_on_fail=True,
            fire_timeout_ms=5000.0,
        )

    def _create_sync_config(self) -> SyncConfig:
        """Crea config para TitanStateSync."""
        return SyncConfig(
            poll_interval_s=2.0,
            orphan_grace_period_ms=500.0,
            max_kills_per_cycle=10,
            retry_pending_interval_s=1.0,
            auto_kill_orphans=True,
        )

    def _get_local_active_cues(self) -> Set[int]:
        """Callback para TitanStateSync: retorna cues activos locales."""
        with self._active_lock:
            return self._active_cues.copy()

    # ===== CALLBACKS DE TITAN QUEUE =====
    def _on_fire_success(self, cue_id: int):
        """Callback cuando FIRE tiene exito."""
        self._mark_success()
        self._last_fire_ts = time.time()
        self._emit_fire(cue_id)

        if self.verbose:
            print(f"[AvoTX] FIRE C{cue_id} OK")

    def _on_kill_success(self, cue_id: int):
        """Callback cuando KILL tiene exito."""
        self._mark_success()
        self._emit_kill(cue_id)

        if self.verbose:
            print(f"[AvoTX] KILL C{cue_id} OK")

    def _on_fire_fail(self, cue_id: int, error: str):
        """Callback cuando FIRE falla."""
        self._mark_fail()
        self._last_error_short = error[:120]

        if self.verbose:
            print(f"[AvoTX] FIRE C{cue_id} FAIL: {error}")

    def _on_kill_fail(self, cue_id: int, error: str):
        """Callback cuando KILL falla."""
        self._mark_fail()
        self._last_error_short = error[:120]

        if self.verbose:
            print(f"[AvoTX] KILL C{cue_id} FAIL: {error}")

    # ===== PROPIEDAD default_config =====
    @property
    def default_config(self) -> Dict[str, Any]:
        """Propiedad para acceso a default_config."""
        return self.config_manager.default_config

    # ===== HANDLERS =====
    def on_fire(self, cb: Callable[[int], None]):
        if callable(cb):
            self._fire_handlers.append(cb)

    def on_kill(self, cb: Callable[[int], None]):
        if callable(cb):
            self._kill_handlers.append(cb)

    def _emit_fire(self, n: int):
        for cb in list(self._fire_handlers):
            try:
                cb(n)
            except Exception:
                pass

    def _emit_kill(self, n: int):
        for cb in list(self._kill_handlers):
            try:
                cb(n)
            except Exception:
                pass

    # ===== RESOLUCION DE IPs =====
    def _normalize_and_validate_ip(self, ip_str: str) -> Optional[str]:
        """Normaliza y valida una IP."""
        if not ip_str:
            return None

        ip_str = ip_str.strip()

        if any(c.isalpha() and c not in 'abcdefABCDEF:' for c in ip_str):
            return self._resolve_interface_name(ip_str)

        if is_valid_private_ip(ip_str):
            return ip_str
        else:
            if self.verbose:
                print(f"[AVOLITES] IP '{ip_str}' invalida o no privada")
            return None

    def _resolve_interface_name(self, interface_name: str) -> Optional[str]:
        """Resuelve nombre de interfaz Windows a IP."""
        try:
            from network_utils import list_interfaces
            interfaces = list_interfaces()

            search_name = safe_decode(interface_name).lower()

            for iface in interfaces:
                if isinstance(iface, dict):
                    iface_name = safe_decode(iface.get('name', '')).lower()
                    iface_desc = safe_decode(iface.get('description', '')).lower()
                    iface_ip = iface.get('ip', '')
                else:
                    continue

                if search_name in iface_name or search_name in iface_desc:
                    if iface_ip and is_valid_private_ip(iface_ip):
                        if self.verbose:
                            print(f"[AVOLITES] Interfaz '{interface_name}' -> {iface_ip}")
                        return iface_ip

            if self.verbose:
                print(f"[AVOLITES] No se pudo resolver interfaz '{interface_name}'")
            return None

        except ImportError:
            if self.verbose:
                print(f"[AVOLITES] network_utils no disponible")
            return None
        except Exception as e:
            if self.verbose:
                print(f"[AVOLITES] Error resolviendo interfaz '{interface_name}': {e}")
            return None

    def _is_valid_ipv4(self, ip_str: str) -> bool:
        """Valida si es IPv4 valida."""
        try:
            ip_obj = ipaddress.ip_address(ip_str.strip())
            return ip_obj.version == 4 and not ip_str.startswith('0.')
        except ValueError:
            return False

    # ===== ENDPOINTS Y URLS =====
    def _scheme(self) -> str:
        """Determina esquema HTTP/HTTPS."""
        port = int(self.config_manager.config.get("console_port", 80))
        if port == 80:
            return "http"
        elif port in (443, 4430, 4431):
            return "https"
        else:
            return "http"

    def _timeouts(self) -> Tuple[float, float]:
        """Retorna (connect_timeout, read_timeout)."""
        cfg = self.config_manager.config
        return (
            float(cfg.get("connect_timeout", 1.2)),
            float(cfg.get("read_timeout", 1.0))
        )

    def _build_url(self, path: str, *, scheme: Optional[str] = None) -> str:
        """Construye URL completa."""
        ip = self.config_manager.config["console_ip"]
        port = self.config_manager.config["console_port"]
        sc = scheme or self._scheme()
        return f"{sc}://{ip}:{port}{path}"

    def _get_current_target(self) -> Tuple[str, int]:
        """Retorna (console_ip, console_port) actual."""
        return (
            self.config_manager.config["console_ip"],
            self.config_manager.config["console_port"]
        )

    # ===== CIRCUIT BREAKER =====
    def _check_circuit_breaker(self, is_ping: bool = False) -> bool:
        """Verifica circuit breaker."""
        now = time.time()

        if is_ping:
            return False

        self._fail_timestamps = [ts for ts in self._fail_timestamps
                                if now - ts < self._fail_window]

        if self.cb_state == CircuitBreakerState.OPEN:
            if now >= self._circuit_open_until:
                self.cb_state = CircuitBreakerState.HALF_OPEN
                self._cb_half_open_since = now
                if self.verbose:
                    print("[CB] OPEN -> HALF_OPEN")
                return False
            else:
                return True

        if self.cb_state == CircuitBreakerState.HALF_OPEN:
            return False

        if len(self._fail_timestamps) >= self._max_consecutive_fails:
            self.cb_state = CircuitBreakerState.OPEN
            self._circuit_open_until = now + self._circuit_break_duration
            if self.verbose:
                print(f"[CB] CLOSED -> OPEN (bloqueado {self._circuit_break_duration}s)")
            return True

        return False

    def _record_failure(self):
        """Registra fallo."""
        now = time.time()
        self._fail_timestamps.append(now)

    def _record_success(self):
        """Registra exito y cierra circuit breaker."""
        self._fail_timestamps.clear()

        if self.cb_state != CircuitBreakerState.CLOSED:
            old_state = self.cb_state
            self.cb_state = CircuitBreakerState.CLOSED
            if self.verbose:
                print(f"[CB] {old_state.value} -> CLOSED")

    # ===== CONEXION Y PING =====
    def _setup_session(self):
        """Configura sesion HTTP para ping y BPM."""
        local_ip = self.config_manager.config.get('local_ip')

        if self.session:
            try:
                self.session.close()
            except:
                pass

        self.session = requests.Session()

        if local_ip and is_valid_private_ip(local_ip):
            adapter = FixedSourceHTTPAdapter(source_ip=local_ip, max_retries=0)
            self.session.mount('http://', adapter)
            self.session.mount('https://', adapter)
            if self.verbose:
                print(f"[AVOLITES] Session HTTP con IP local: {local_ip}")

        self.session.headers.update({
            "Connection": "keep-alive",
            "User-Agent": "911Fiesta/5.0"
        })

    def _mark_success(self):
        """Marca exito y actualiza estado."""
        self.is_connected = True
        self._status_cache["connected"] = True
        self._last_success_ts = time.time()
        self._consec_fail = 0
        self._last_error = None
        self._last_error_short = None
        self._record_success()

        if self.connection_state != ConnectionState.READY:
            self.connection_state = ConnectionState.READY
            if self.verbose:
                console_ip = self.config_manager.config["console_ip"]
                console_port = self.config_manager.config["console_port"]
                print(f"[AVOLITES] READY on {self._scheme()}://{console_ip}:{console_port}")

    def _mark_fail(self):
        """Marca fallo y actualiza estado."""
        self._consec_fail += 1
        if self._consec_fail >= 2:
            self.is_connected = False
            self._status_cache["connected"] = False
            self.connection_state = ConnectionState.NOT_READY
        self._record_failure()

    def ping(self) -> bool:
        """Ping a la consola."""
        if self.transport != "http":
            if self.verbose:
                print(f"[AVOLITES] Skipping ping for transport: {self.transport}")
            return True

        endpoints = [
            "/titan/get/System/SoftwareVersion",
            "/titan/script/Version",
        ]

        for p in endpoints:
            url = self._build_url(p)
            if self.verbose:
                print(f"[AVOLITES] Ping -> {url}")

            try:
                response = self.session.get(url, timeout=self._timeouts(), verify=False)
                if response.status_code == 200:
                    self._mark_success()
                    txt = (response.text or "").strip().strip('"')
                    self._status_cache.update({"version": txt, "last_ping": time.time()})
                    if self.verbose:
                        print(f"[AVOLITES] Ping OK - \"{txt}\"")
                    return True
            except Exception as e:
                if self.verbose:
                    print(f"[AVOLITES] Ping error: {e}")

        if self.verbose:
            print("[AVOLITES] Ping FAIL")
        self._mark_fail()
        return False

    def connect(self) -> bool:
        """Conecta a la consola."""
        if self.transport != "http":
            self._mark_success()
            return True

        console_ip = self.config_manager.config.get("console_ip", "")
        if not is_valid_private_ip(console_ip):
            if self.verbose:
                print(f"[AVOLITES] console_ip '{console_ip}' invalida")

            default_ip = self.default_config["console_ip"]
            if is_valid_private_ip(default_ip):
                self.config_manager.config["console_ip"] = default_ip
                if self.verbose:
                    print(f"[AVOLITES] Usando console_ip default: {default_ip}")

        if self.ping():
            return True

        self._mark_fail()
        return False

    # ===== SETTERS DINAMICOS (UI) =====
    def set_local_interface(self, iface_hint: Optional[str]) -> bool:
        """Cambia la interfaz de red local."""
        if not iface_hint:
            return False

        try:
            hint_clean = safe_decode(iface_hint).strip()

            if self._is_valid_ipv4(hint_clean):
                if is_valid_private_ip(hint_clean):
                    self.config_manager.config["local_ip"] = hint_clean
                    if self.verbose:
                        print(f"[AVOLITES] Local IP seteada: {hint_clean}")

                    try:
                        self._setup_session()
                        return True
                    except Exception as e:
                        if self.verbose:
                            print(f"[AVOLITES] Error reabriendo sesion: {e}")
                        return False
                else:
                    return False
            else:
                resolved_ip = self._resolve_interface_name(hint_clean)
                if resolved_ip:
                    self.config_manager.config["local_ip"] = resolved_ip
                    try:
                        self._setup_session()
                        return True
                    except Exception as e:
                        if self.verbose:
                            print(f"[AVOLITES] Error reabriendo sesion: {e}")
                        return False
                else:
                    return False

        except Exception as e:
            if self.verbose:
                print(f"[AVOLITES] Error en set_local_interface: {e}")
            return False

    def set_console_ip(self, ip: str, port: Optional[int] = None, transport: Optional[str] = None) -> bool:
        """Cambia el destino Titan en caliente."""
        try:
            ip_clean = ip.strip()
            if not is_valid_private_ip(ip_clean):
                if self.verbose:
                    print(f"[AVOLITES] set_console_ip: IP '{ip_clean}' invalida")
                return False

            old_ip = self.config_manager.config.get("console_ip")
            old_port = self.config_manager.config.get("console_port")

            self.config_manager.config["console_ip"] = ip_clean

            if port is not None:
                self.config_manager.config["console_port"] = int(port)
            elif transport:
                self.config_manager.config["console_port"] = 80 if transport == "http" else 4430

            if transport:
                if transport.lower() in ("http", "https"):
                    self.transport = transport.lower()
                    self.config_manager.config["transport"] = transport.lower()

            new_ip = self.config_manager.config["console_ip"]
            new_port = self.config_manager.config["console_port"]

            if self.verbose:
                print(f"[AVOLITES] Target cambiado: {old_ip}:{old_port} -> {new_ip}:{new_port}")

            # Limpiar circuit breaker
            self._fail_timestamps.clear()
            self.cb_state = CircuitBreakerState.CLOSED
            self._circuit_open_until = 0.0

            # Resetear estado de conexion
            self.connection_state = ConnectionState.NOT_READY
            self.is_connected = False
            self._status_cache["connected"] = False

            # Actualizar config en TitanQueue
            self._titan_queue.update_config(
                console_ip=new_ip,
                console_port=new_port,
                transport=self.transport,
            )

            # Actualizar TitanSync (si esta activo)
            if self._titan_sync:
                self._titan_sync.set_user_number_offset(
                    self.config_manager.config.get("user_number_offset", 169)
                )

            # Reabrir sesion HTTP para ping
            try:
                self._setup_session()
            except Exception as e:
                if self.verbose:
                    print(f"[AVOLITES] Error reabriendo sesion: {e}")

            # Health-check inmediato
            try:
                success = self.ping()
                return success
            except Exception as e:
                if self.verbose:
                    print(f"[AVOLITES] Error en health-check: {e}")
                return False

        except Exception as e:
            if self.verbose:
                print(f"[AVOLITES] Error en set_console_ip: {e}")
            return False

    def set_transport(self, transport: str) -> bool:
        """
        Cambia el transporte (http/https/artnet/sacn).

        Cuando transport='artnet':
          - Detiene TitanQueue (HTTP) y SacnEngine si activo
          - Inicia DmxState + ArtNetEngine + CueOutputAdapter
          - fire_cue/kill_cue se redirigen a DMX

        Cuando transport='sacn':
          - Detiene TitanQueue (HTTP) y ArtNetEngine si activo
          - Inicia DmxState + SacnEngine + CueOutputAdapter
          - fire_cue/kill_cue se redirigen a DMX

        Cuando transport='http' o 'https':
          - Detiene ArtNetEngine/SacnEngine si estaban activos
          - Reactiva TitanQueue (HTTP)
        """
        try:
            mode = transport.lower().strip()

            if mode == "artnet":
                # Cambiar a Art-Net
                self.transport = "artnet"
                self.config_manager.config["transport"] = "artnet"
                self._stop_sacn()
                self._stop_artnet()  # Limpiar si ya estaba
                self._titan_queue.stop()
                self._start_artnet()
                print(f"[AVOLITES] Transport -> ARTNET")
                return True

            elif mode == "sacn":
                # Cambiar a sACN
                self.transport = "sacn"
                self.config_manager.config["transport"] = "sacn"
                self._stop_artnet()
                self._stop_sacn()  # Limpiar si ya estaba
                self._titan_queue.stop()
                self._start_sacn()
                print(f"[AVOLITES] Transport -> sACN")
                return True

            elif mode in ("http", "https"):
                # Cambiar a HTTP
                self._stop_artnet()
                self._stop_sacn()
                self.transport = mode
                self.config_manager.config["transport"] = mode
                self._titan_queue.update_config(transport=mode)
                self._titan_queue.start()

                try:
                    self._setup_session()
                except Exception as e:
                    if self.verbose:
                        print(f"[AVOLITES] Error reabriendo sesion: {e}")

                print(f"[AVOLITES] Transport -> {mode.upper()}")
                return True

            else:
                if self.verbose:
                    print(f"[AVOLITES] Transport desconocido: {mode}")
                return False

        except Exception as e:
            if self.verbose:
                print(f"[AVOLITES] Error en set_transport: {e}")
            return False

    # ===== ART-NET LIFECYCLE =====

    def _start_artnet(self) -> bool:
        """
        Inicia el subsistema Art-Net: DmxState + ArtNetEngine + CueOutputAdapter.
        Lee config de artnet_config.json y cue_map.json.
        """
        try:
            # Paths de config
            base = os.path.dirname(os.path.abspath(__file__))
            cue_map_path = os.path.join(base, "cue_map.json")
            artnet_config_path = os.path.join(base, "artnet_config.json")

            # Cargar cue map
            if os.path.exists(cue_map_path):
                self._dmx_state = DmxState.from_json(cue_map_path)
                print(f"[BOOTSTRAP] DmxState loaded: {len(self._dmx_state.get_cue_map())} cues mapped")
            else:
                self._dmx_state = DmxState()
                print("[BOOTSTRAP] DmxState loaded: empty (no cue_map.json)")

            # Cargar artnet config
            if os.path.exists(artnet_config_path):
                self._artnet_engine = ArtNetEngine.from_json(artnet_config_path, self._dmx_state)
            else:
                self._artnet_engine = ArtNetEngine(
                    self._dmx_state,
                    target_ip="2.255.255.255",
                    universe=0,
                    fps=40,
                )
                print("[BOOTSTRAP] ArtNetEngine using defaults (no artnet_config.json)")

            # Crear adapter
            self._cue_adapter = CueOutputAdapter(self._dmx_state)

            # Iniciar engine
            self._artnet_engine.start()
            self._artnet_active = True

            stats = self._artnet_engine.get_stats()
            print(f"[BOOTSTRAP] ========================================")
            print(f"[BOOTSTRAP] TRANSPORT SELECTED: ARTNET")
            print(f"[BOOTSTRAP] ArtNetEngine STARTED")
            print(f"[BOOTSTRAP]   target: {stats['target_ip']}:{stats['port']}")
            print(f"[BOOTSTRAP]   universe: {stats['universe']}")
            print(f"[BOOTSTRAP]   fps: {stats['configured_fps']}")
            print(f"[BOOTSTRAP]   node: {stats.get('node_name', 'N/A')}")
            print(f"[BOOTSTRAP]   local_ip: {stats.get('local_ip', 'N/A')}")
            print(f"[BOOTSTRAP] ========================================")
            return True

        except Exception as e:
            print(f"[BOOTSTRAP] ArtNet start FAILED: {e}")
            import traceback
            traceback.print_exc()
            self._artnet_active = False
            return False

    def _stop_artnet(self) -> None:
        """Detiene el subsistema Art-Net si está activo."""
        if self._artnet_engine:
            try:
                self._artnet_engine.stop()
            except Exception:
                pass
            self._artnet_engine = None
        if self._artnet_active:
            self._dmx_state = None
            self._cue_adapter = None
        self._artnet_active = False

    # ===== sACN LIFECYCLE =====

    def _start_sacn(self) -> bool:
        """
        Inicia el subsistema sACN: DmxState + SacnEngine + CueOutputAdapter.
        Lee config de sacn section en avolites_config.json.
        """
        try:
            base = os.path.dirname(os.path.abspath(__file__))
            cue_map_path = os.path.join(base, "cue_map.json")

            # Cargar cue map
            if os.path.exists(cue_map_path):
                self._dmx_state = DmxState.from_json(cue_map_path)
                print(f"[BOOTSTRAP] DmxState loaded: {len(self._dmx_state.get_cue_map())} cues mapped")
            else:
                self._dmx_state = DmxState()
                print("[BOOTSTRAP] DmxState loaded: empty (no cue_map.json)")

            # Cargar sACN config desde avolites_config.json
            sacn_config = self.config_manager.config.get("sacn", {})
            self._sacn_engine = SacnEngine.from_config(sacn_config, self._dmx_state)

            # Crear adapter
            self._cue_adapter = CueOutputAdapter(self._dmx_state)

            # Iniciar engine
            self._sacn_engine.start()
            self._sacn_active = True

            stats = self._sacn_engine.get_stats()
            print(f"[BOOTSTRAP] ========================================")
            print(f"[BOOTSTRAP] TRANSPORT SELECTED: sACN")
            print(f"[BOOTSTRAP] SacnEngine STARTED")
            print(f"[BOOTSTRAP]   sACN universe: {stats['universe']}")
            print(f"[BOOTSTRAP]   multicast: {stats['multicast_ip']}:{stats['port']}")
            print(f"[BOOTSTRAP]   priority: {stats['priority']}")
            print(f"[BOOTSTRAP]   fps: {stats['configured_fps']}")
            print(f"[BOOTSTRAP]   source: {stats.get('source_name', 'N/A')}")
            print(f"[BOOTSTRAP] ========================================")
            return True

        except Exception as e:
            print(f"[BOOTSTRAP] sACN start FAILED: {e}")
            import traceback
            traceback.print_exc()
            self._sacn_active = False
            return False

    def _stop_sacn(self) -> None:
        """Detiene el subsistema sACN si está activo."""
        if self._sacn_engine:
            try:
                self._sacn_engine.stop()
            except Exception:
                pass
            self._sacn_engine = None
        if self._sacn_active:
            self._dmx_state = None
            self._cue_adapter = None
        self._sacn_active = False

    def set_console_port(self, port: int) -> bool:
        """Cambia el puerto de la consola."""
        try:
            port_int = int(port)
            self.config_manager.config["console_port"] = port_int

            if self.verbose:
                print(f"[AVOLITES] Puerto -> {port_int}")

            self.connection_state = ConnectionState.NOT_READY
            self.is_connected = False

            self._titan_queue.update_config(console_port=port_int)

            try:
                self._setup_session()
            except Exception as e:
                if self.verbose:
                    print(f"[AVOLITES] Error reabriendo sesion: {e}")

            return True
        except Exception as e:
            if self.verbose:
                print(f"[AVOLITES] Error en set_console_port: {e}")
            return False

    def set_cue_offset(self, offset: int) -> bool:
        """Cambia el offset de cues."""
        try:
            offset_int = int(offset)
            self.config_manager.config["user_number_offset"] = offset_int
            self.config_manager.save_config()

            if self.verbose:
                print(f"[AVOLITES] Cue Offset -> {offset_int}")
                samples = [1, 10, 28, 41, 42]
                mapped = [(x, self._map_user_number(x)) for x in samples]
                print(f"[AVOLITES] Mapeo: {mapped}")

            # Actualizar transport y sync (si esta activo)
            self._titan_queue.update_config(user_number_offset=offset_int)
            if self._titan_sync:
                self._titan_sync.set_user_number_offset(offset_int)

            return True
        except Exception as e:
            if self.verbose:
                print(f"[AVOLITES] Error en set_cue_offset: {e}")
            return False

    # ===== API PUBLICA =====
    def fire_cue(self, cue_id: int) -> bool:
        """
        Dispara un cue.
        DMX toggle-safe: skips pulse if cue already tracked as active.
        Rutas: ARTNET → CueOutputAdapter → DmxState
               HTTP   → TitanQueue → TitanTransport
        """
        with self._active_lock:
            was_active = cue_id in self._active_cues
            self._active_cues.add(cue_id)

        # DMX toggle guard: redundant fire would toggle cue OFF
        if was_active and (self._artnet_active or self._sacn_active):
            print(f"[FIRE] cue={cue_id} → SKIP (DMX toggle-safe: already active)")
            return True

        print(f"[FIRE] cue={cue_id}")
        self._last_fire_ts = time.time()

        if (self._artnet_active or self._sacn_active) and self._cue_adapter:
            return self._cue_adapter.fire(cue_id)

        return self._titan_queue.fire(cue_id)

    def kill_cue(self, cue_id: int) -> bool:
        """
        Mata un cue.
        DMX toggle-safe: skips pulse if cue already tracked as inactive.
        Rutas: ARTNET → CueOutputAdapter → DmxState
               HTTP   → TitanQueue → TitanTransport
        """
        with self._active_lock:
            was_active = cue_id in self._active_cues
            self._active_cues.discard(cue_id)

        # DMX toggle guard: redundant kill would toggle cue ON
        if not was_active and (self._artnet_active or self._sacn_active):
            print(f"[KILL] cue={cue_id} → SKIP (DMX toggle-safe: already inactive)")
            return True

        print(f"[KILL] cue={cue_id}")

        if (self._artnet_active or self._sacn_active) and self._cue_adapter:
            return self._cue_adapter.kill(cue_id)

        return self._titan_queue.kill(cue_id)

    def kill_pool(self, cue_ids: List[int], priority_boost: bool = False) -> bool:
        """Mata multiples cues."""
        if not cue_ids:
            return False

        print(f"[AvolitesBridge] KILL_POOL cues={cue_ids} prio={priority_boost}")

        with self._active_lock:
            for cue_id in cue_ids:
                self._active_cues.discard(cue_id)

        if (self._artnet_active or self._sacn_active) and self._cue_adapter:
            return self._cue_adapter.kill_pool(cue_ids) == len(cue_ids)

        return self._titan_queue.kill_pool(cue_ids, priority_boost=priority_boost) == len(cue_ids)

    # ===== CRITICAL FAST-PATH =====
    # Cues críticos que requieren latencia mínima (<100ms):
    # - C41 (Dimmer): visibilidad del espectáculo
    # - C37-39 (Ataque): impacto musical, sincronización con beat
    # - Primer fire al entrar a estado: transición percibida
    # - Restore crítico de Movimiento
    CRITICAL_CUES = {41, 37, 38, 39}

    def fire_cue_critical(self, cue_id: int) -> bool:
        """
        CRITICAL FAST-PATH: Dispara un cue con latencia mínima.
        En modo ARTNET: fire directo a DmxState (ya es instant).
        En modo HTTP: bypasea cola y rate limit.
        """
        with self._active_lock:
            self._active_cues.add(cue_id)

        self._last_fire_ts = time.time()

        if (self._artnet_active or self._sacn_active) and self._cue_adapter:
            return self._cue_adapter.fire(cue_id)

        # Usar fire_immediate que bypasea cola y rate limit
        return self._titan_queue.fire_immediate(cue_id)

    def is_critical_cue(self, cue_id: int) -> bool:
        """Verifica si un cue es crítico (requiere fast-path)."""
        return cue_id in self.CRITICAL_CUES

    # ===== METODOS MANUALES (BYPASS READY) =====
    def fire_cue_manual(self, cue_id: int) -> bool:
        """
        Dispara un cue ignorando READY (para acciones manuales).
        """
        with self._active_lock:
            self._active_cues.add(cue_id)

        self._last_fire_ts = time.time()

        if (self._artnet_active or self._sacn_active) and self._cue_adapter:
            return self._cue_adapter.fire(cue_id)

        return self._titan_queue.fire(cue_id)

    def kill_cue_manual(self, cue_id: int) -> bool:
        """
        Mata un cue ignorando READY (para acciones manuales).
        """
        with self._active_lock:
            self._active_cues.discard(cue_id)

        if (self._artnet_active or self._sacn_active) and self._cue_adapter:
            return self._cue_adapter.kill(cue_id)

        return self._titan_queue.kill(cue_id, priority_boost=True)

    def kill_pool_manual(self, cue_ids: List[int]) -> bool:
        """
        Mata multiples cues ignorando READY.
        """
        if not cue_ids:
            return False

        with self._active_lock:
            for cue_id in cue_ids:
                self._active_cues.discard(cue_id)

        if (self._artnet_active or self._sacn_active) and self._cue_adapter:
            return self._cue_adapter.kill_pool(cue_ids) == len(cue_ids)

        return self._titan_queue.kill_pool(cue_ids, priority_boost=True) == len(cue_ids)

    def off_now(self, cue_ids: Union[List[int], int]) -> bool:
        """
        OFF instantaneo sin throttle ni respeto a READY state.
        Bypass completo para OFF prioritario.
        """
        if isinstance(cue_ids, int):
            return self.kill_cue_manual(cue_ids)
        elif isinstance(cue_ids, list):
            return self.kill_pool_manual(cue_ids)
        else:
            return False

    def kill_all_cues(self) -> bool:
        """Mata todos los cues activos."""
        with self._active_lock:
            active_cues = list(self._active_cues.copy())
            self._active_cues.clear()

        if (self._artnet_active or self._sacn_active) and self._cue_adapter:
            self._cue_adapter.kill_all()
            return True

        if active_cues:
            return self._titan_queue.kill_pool(active_cues, priority_boost=True) == len(active_cues)
        return True

    def is_active(self, cue_id: int) -> bool:
        """Verifica si un cue esta activo."""
        with self._active_lock:
            return cue_id in self._active_cues

    def get_active_cues(self) -> Set[int]:
        """Retorna set de cues activos."""
        with self._active_lock:
            return set(self._active_cues)

    def get_active_in_pool(self, ids) -> Set[int]:
        """Retorna cues activos dentro de un pool."""
        with self._active_lock:
            return set(i for i in ids if i in self._active_cues)

    # ===== MAPEO DE USER NUMBERS =====
    def _map_user_number(self, n: int) -> int:
        """Mapea user_number logico a TitanID real."""
        try:
            n = int(n)
        except Exception:
            return n

        cfg = getattr(self, "config_manager", None)
        cfg = getattr(cfg, "config", {}) if cfg else getattr(self, "config", {})

        exp = (cfg.get("discovered_titanids") or {})
        m = exp.get(str(n))
        if m is not None:
            try:
                return int(m)
            except Exception:
                pass

        off = int(cfg.get("user_number_offset") or 0)
        return n + off

    # ===== ESTADO Y METRICAS =====
    def get_status(self) -> Dict[str, Any]:
        """Retorna estado completo."""
        with self._active_lock:
            active_cues = list(self._active_cues)

        queue_stats = self._titan_queue.get_stats()
        sync_stats = self._titan_sync.get_stats() if self._titan_sync else {"state": "DISABLED"}

        status = self._status_cache.copy()
        # Art-Net stats si aplica
        artnet_stats = None
        if self._artnet_active and self._artnet_engine:
            artnet_stats = self._artnet_engine.get_stats()
            if self._cue_adapter:
                artnet_stats["adapter"] = self._cue_adapter.get_stats()

        # sACN stats si aplica
        sacn_stats = None
        if self._sacn_active and self._sacn_engine:
            sacn_stats = self._sacn_engine.get_stats()
            if self._cue_adapter:
                sacn_stats["adapter"] = self._cue_adapter.get_stats()

        status.update({
            "connected": self.is_connected,
            "connection_state": self.connection_state.value,
            "circuit_breaker": self.cb_state.value,
            "version": status.get("version"),
            "last_ping": status.get("last_ping", 0.0),
            "active_cues": active_cues,
            "active_count": len(active_cues),
            "last_error": self._last_error,
            "last_error_short": self._last_error_short,
            "last_send_ms": self._last_send_ms,
            "last_fire_ts": self._last_fire_ts,
            "queue_stats": queue_stats,
            "sync_stats": sync_stats,
            "artnet_stats": artnet_stats,
            "artnet_active": self._artnet_active,
            "sacn_stats": sacn_stats,
            "sacn_active": self._sacn_active,
            "dropped_not_ready": self._dropped_not_ready,
            "dropped_queue_full": self._dropped_queue_full,
            "console_ip": self.config_manager.config.get("console_ip"),
            "console_port": self.config_manager.config.get("console_port"),
            "transport": self.transport,
        })

        return status

    def get_last_error(self) -> Optional[str]:
        """Retorna ultimo error."""
        return self._last_error

    def get_queue_stats(self) -> Dict[str, Any]:
        """Retorna estadisticas de TitanQueue."""
        return self._titan_queue.get_stats()

    def get_sync_stats(self) -> Dict[str, Any]:
        """Retorna estadisticas de TitanStateSync. LEGACY: desactivado."""
        if self._titan_sync:
            return self._titan_sync.get_stats()
        return {"state": "DISABLED", "message": "TitanSync desactivado en modo legacy"}

    def force_sync(self) -> Dict[str, Any]:
        """Fuerza sincronizacion inmediata con Titan. LEGACY: no-op."""
        if self._titan_sync:
            return self._titan_sync.force_sync()
        return {"state": "DISABLED", "message": "TitanSync desactivado en modo legacy"}

    # ===== BPM MASTER SYNC =====
    def send_bpm(self, bpm: float) -> bool:
        """
        Envia BPM al Avolites Titan via HTTP GET.
        Este metodo NO encola - hace GET directo para minima latencia.
        """
        if not self.is_connected or bpm is None:
            return False

        try:
            bpm_int = int(round(bpm))
            url = self._build_url(f"/titan/set/Playback/BPM?value={bpm_int}")
            response = self.session.get(url, timeout=(0.5, 0.5), verify=False)

            if response.status_code == 200:
                return True
            else:
                if self.verbose:
                    print(f"[AVOLITES][BPM] Error enviando BPM {bpm_int}: HTTP {response.status_code}")
                return False

        except Exception as e:
            if self.verbose:
                print(f"[AVOLITES][BPM] Excepcion enviando BPM: {e}")
            return False

    def send_tap(self) -> bool:
        """
        Envia TAP tempo al Avolites Titan via HTTP GET.
        Titan usa TAPs sucesivos para calcular BPM internamente.
        Rate-limited externamente por TapBridge.
        """
        if not self.is_connected:
            return False

        try:
            # Titan API: /titan/script/Playback/TapTempo
            url = self._build_url("/titan/script/Playback/TapTempo")
            response = self.session.get(url, timeout=(0.3, 0.3), verify=False)

            if response.status_code == 200:
                return True
            else:
                if self.verbose:
                    print(f"[AVOLITES][TAP] Error enviando TAP: HTTP {response.status_code}")
                return False

        except Exception as e:
            if self.verbose:
                print(f"[AVOLITES][TAP] Excepcion enviando TAP: {e}")
            return False

    def close(self):
        """Cierra el controlador."""
        # Detener servicios
        if self._titan_sync:
            self._titan_sync.stop()
        self._titan_queue.stop()

        with self._active_lock:
            self._active_cues.clear()

        self.is_connected = False
        self._status_cache["connected"] = False
        self._record_success()
        self.connection_state = ConnectionState.NOT_READY

        if self.session:
            try:
                self.session.close()
            except:
                pass

        print("[AVOLITES] Controller cerrado")

    def __del__(self):
        try:
            self.close()
        except:
            pass


__all__ = [
    "AvolitesController",
    "AvolitesConfig",
    "ConnectionState",
    "CircuitBreakerState"
]
