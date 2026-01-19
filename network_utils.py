# network_utils.py - Sistema de detección de interfaces de red para Avolites
import socket
import subprocess
import platform
import ipaddress
from typing import List, Tuple, Optional

def list_interfaces() -> List[Tuple[str, str, str, bool]]:
    """
    Detecta todas las interfaces de red disponibles.
    
    Returns:
        List[Tuple[str, str, str, bool]]: Lista de tuplas (name, ip, mac, up)
            - name: Nombre de la interfaz (ej: "Ethernet", "WiFi", "eth0")
            - ip: Dirección IPv4 (ej: "192.168.1.100")
            - mac: Dirección MAC (ej: "00:11:22:33:44:55")
            - up: True si la interfaz está activa, False si no
    """
    interfaces = []
    
    try:
        # Intentar detectar con socket (funciona en todos los sistemas)
        test_ips = ["8.8.8.8", "1.1.1.1", "192.168.1.1", "10.0.0.1"]
        
        for test_ip in test_ips:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.settimeout(1.0)
                    s.connect((test_ip, 80))
                    local_ip = s.getsockname()[0]
                    
                    # Verificar si ya existe
                    exists = any(iface[1] == local_ip for iface in interfaces)
                    if not exists and not local_ip.startswith("127."):
                        interfaces.append((f"Auto_{len(interfaces)+1}", local_ip, _guess_mac(local_ip), True))
            except Exception:
                continue
        
        # Detección específica por sistema operativo
        if platform.system() == "Windows":
            interfaces.extend(_detect_windows_interfaces())
        else:
            interfaces.extend(_detect_unix_interfaces())
        
    except Exception as e:
        print(f"[NETWORK] Error detectando interfaces: {e}")
    
    # Si no se detectó nada, devolver interfaz por defecto
    if not interfaces:
        print("[NETWORK] No se detectaron interfaces, creando por defecto...")
        interfaces = [
            ("Ethernet", "192.168.1.100", "00:00:00:00:00:00", False),
            ("WiFi", "10.0.0.100", "00:00:00:00:00:00", False)
        ]
    
    # Eliminar duplicados por IP
    seen_ips = set()
    unique_interfaces = []
    for iface in interfaces:
        name, ip, mac, up = iface
        if ip not in seen_ips:
            seen_ips.add(ip)
            unique_interfaces.append(iface)
    
    print(f"[NETWORK] Detectadas {len(unique_interfaces)} interfaces:")
    for name, ip, mac, up in unique_interfaces:
        status = "UP" if up else "DOWN"
        print(f"[NETWORK]   {name}: {ip} [{mac}] ({status})")
    
    return unique_interfaces


def _detect_windows_interfaces() -> List[Tuple[str, str, str, bool]]:
    """Detecta interfaces en Windows usando ipconfig"""
    interfaces = []
    
    try:
        result = subprocess.run(['ipconfig', '/all'], capture_output=True, text=True, timeout=5, errors='replace')
        if result.returncode == 0:
            interfaces = _parse_ipconfig_output(result.stdout)
    except Exception as e:
        print(f"[NETWORK] Error con ipconfig: {e}")
    
    return interfaces


def _detect_unix_interfaces() -> List[Tuple[str, str, str, bool]]:
    """Detecta interfaces en Linux/Mac usando ifconfig o ip addr"""
    interfaces = []
    
    # Intentar varios comandos
    commands = [
        ['ifconfig', '-a'],
        ['ip', 'addr', 'show'],
        ['hostname', '-I']
    ]
    
    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, errors='replace')
            if result.returncode == 0:
                if cmd[0] == 'hostname':
                    # hostname -I devuelve lista de IPs separadas por espacio
                    ips = result.stdout.strip().split()
                    for i, ip in enumerate(ips):
                        if _is_valid_ip(ip) and not ip.startswith("127."):
                            interfaces.append((f"Unix_{i+1}", ip, _guess_mac(ip), True))
                elif cmd[0] == 'ifconfig':
                    interfaces = _parse_ifconfig_output(result.stdout)
                else:  # ip addr
                    interfaces = _parse_ip_addr_output(result.stdout)
                
                if interfaces:
                    break
        except Exception as e:
            print(f"[NETWORK] Error con {cmd[0]}: {e}")
            continue
    
    return interfaces


def _parse_ipconfig_output(output: str) -> List[Tuple[str, str, str, bool]]:
    """Parsea salida de ipconfig /all"""
    interfaces = []
    lines = output.split('\n')
    
    current_adapter = None
    current_mac = "00:00:00:00:00:00"
    current_up = False
    
    for line in lines:
        line_stripped = line.strip()
        
        # Detectar nuevo adaptador
        if "adapter" in line.lower() or "ethernet" in line.lower():
            if ":" in line:
                current_adapter = line.split(":")[0].strip()
                if not current_adapter or len(current_adapter) > 50:
                    current_adapter = f"Adapter_{len(interfaces)+1}"
            current_mac = "00:00:00:00:00:00"
            current_up = False
        
        # Detectar dirección física (MAC)
        elif "physical address" in line.lower() or "dirección física" in line.lower():
            if ":" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    mac = parts[-1].strip()
                    # Limpiar MAC
                    mac = mac.replace("-", ":").upper()
                    if len(mac) == 17:  # Formato XX:XX:XX:XX:XX:XX
                        current_mac = mac
        
        # Detectar IPv4
        elif "IPv4" in line and ":" in line:
            try:
                ip = line.split(':')[-1].strip()
                # Remover "(Preferred)" o similar
                ip = ip.split('(')[0].strip()
                
                if _is_valid_ip(ip) and not ip.startswith("127."):
                    name = current_adapter or f"Windows_{len(interfaces)+1}"
                    # Interfaz está UP si tiene IP válida
                    interfaces.append((name, ip, current_mac, True))
            except Exception:
                continue
    
    return interfaces


def _parse_ifconfig_output(output: str) -> List[Tuple[str, str, str, bool]]:
    """Parsea salida de ifconfig"""
    interfaces = []
    lines = output.split('\n')
    
    current_interface = None
    current_ip = None
    current_mac = "00:00:00:00:00:00"
    current_up = False
    
    for line in lines:
        line_stripped = line.strip()
        
        # Nueva interfaz (no empieza con espacio)
        if line and not line[0].isspace() and ':' in line:
            # Guardar interfaz anterior si tiene IP
            if current_interface and current_ip:
                interfaces.append((current_interface, current_ip, current_mac, current_up))
            
            # Nueva interfaz
            current_interface = line.split(':')[0].strip()
            current_ip = None
            current_mac = "00:00:00:00:00:00"
            current_up = "UP" in line.upper()
        
        # Detectar IP
        elif "inet " in line_stripped and "127." not in line_stripped:
            parts = line_stripped.split()
            for i, part in enumerate(parts):
                if part == "inet" and i + 1 < len(parts):
                    ip_with_mask = parts[i + 1]
                    ip = ip_with_mask.split('/')[0]
                    if _is_valid_ip(ip):
                        current_ip = ip
                    break
        
        # Detectar MAC
        elif "ether " in line_stripped or "hwaddr" in line_stripped.lower():
            parts = line_stripped.split()
            for part in parts:
                if ':' in part and len(part) == 17:  # Formato XX:XX:XX:XX:XX:XX
                    current_mac = part.upper()
                    break
    
    # Guardar última interfaz
    if current_interface and current_ip:
        interfaces.append((current_interface, current_ip, current_mac, current_up))
    
    return interfaces


def _parse_ip_addr_output(output: str) -> List[Tuple[str, str, str, bool]]:
    """Parsea salida de ip addr show"""
    interfaces = []
    lines = output.split('\n')
    
    current_interface = None
    current_ip = None
    current_mac = "00:00:00:00:00:00"
    current_up = False
    
    for line in lines:
        line_stripped = line.strip()
        
        # Nueva interfaz (empieza con número)
        if line and line[0].isdigit() and ':' in line:
            # Guardar interfaz anterior
            if current_interface and current_ip:
                interfaces.append((current_interface, current_ip, current_mac, current_up))
            
            # Parse: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> ..."
            parts = line.split(':')
            if len(parts) >= 2:
                current_interface = parts[1].strip()
            current_ip = None
            current_mac = "00:00:00:00:00:00"
            current_up = "UP" in line.upper()
        
        # Detectar IP
        elif "inet " in line_stripped and "127." not in line_stripped:
            parts = line_stripped.split()
            for i, part in enumerate(parts):
                if part == "inet" and i + 1 < len(parts):
                    ip_with_mask = parts[i + 1]
                    ip = ip_with_mask.split('/')[0]
                    if _is_valid_ip(ip):
                        current_ip = ip
                    break
        
        # Detectar MAC
        elif "link/ether" in line_stripped:
            parts = line_stripped.split()
            for i, part in enumerate(parts):
                if part == "link/ether" and i + 1 < len(parts):
                    mac = parts[i + 1]
                    if ':' in mac and len(mac) == 17:
                        current_mac = mac.upper()
                    break
    
    # Guardar última interfaz
    if current_interface and current_ip:
        interfaces.append((current_interface, current_ip, current_mac, current_up))
    
    return interfaces


def _is_valid_ip(ip: str) -> bool:
    """Valida si es una IP IPv4 válida"""
    try:
        ipaddress.IPv4Address(ip)
        return True
    except:
        return False


def _guess_mac(ip: str) -> str:
    """Intenta adivinar la MAC usando arp (best effort)"""
    try:
        if platform.system() == "Windows":
            cmd = ["arp", "-a", ip]
        else:
            cmd = ["arp", "-n", ip]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2, errors='replace')
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                if ip in line:
                    parts = line.split()
                    for part in parts:
                        # Buscar formato MAC
                        if ':' in part and len(part) == 17:
                            return part.upper()
                        elif '-' in part and len(part) == 17:
                            return part.replace('-', ':').upper()
    except:
        pass
    
    return "00:00:00:00:00:00"


def ping_host(host: str, count: int = 3, timeout_ms: int = 500) -> dict:
    """
    Ejecuta ping a un host y devuelve estadísticas.
    
    Args:
        host: IP o hostname a hacer ping
        count: Número de pings (default: 3)
        timeout_ms: Timeout en milisegundos (default: 500)
    
    Returns:
        dict con keys:
            - success: bool
            - min_ms: float o None
            - avg_ms: float o None
            - max_ms: float o None
            - packet_loss: int (0-count)
            - error: str o None
    """
    try:
        if platform.system().lower() == "windows":
            cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), host]
        else:
            timeout_sec = max(1, timeout_ms // 1000)
            cmd = ["ping", "-c", str(count), "-W", str(timeout_sec), host]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec * count + 2, errors='replace')
        output = result.stdout + result.stderr
        
        if result.returncode == 0:
            # Parsear tiempos
            times = []
            lines = output.split('\n')
            
            for line in lines:
                if 'time=' in line.lower() or 'tiempo=' in line.lower():
                    try:
                        import re
                        match = re.search(r'time[=<]\s*(\d+\.?\d*)', line.lower())
                        if match:
                            times.append(float(match.group(1)))
                    except:
                        pass
            
            if times:
                return {
                    "success": True,
                    "min_ms": min(times),
                    "avg_ms": sum(times) / len(times),
                    "max_ms": max(times),
                    "packet_loss": count - len(times),
                    "error": None
                }
            else:
                return {
                    "success": True,
                    "min_ms": None,
                    "avg_ms": None,
                    "max_ms": None,
                    "packet_loss": 0,
                    "error": None
                }
        else:
            return {
                "success": False,
                "min_ms": None,
                "avg_ms": None,
                "max_ms": None,
                "packet_loss": count,
                "error": "Host unreachable"
            }
            
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "min_ms": None,
            "avg_ms": None,
            "max_ms": None,
            "packet_loss": count,
            "error": "Timeout"
        }
    except Exception as e:
        return {
            "success": False,
            "min_ms": None,
            "avg_ms": None,
            "max_ms": None,
            "packet_loss": count,
            "error": str(e)
        }


# ===== LEGACY: NetworkSelectorWidget (mantenido para compatibilidad) =====
# Este widget ya no se usa en el header, pero se mantiene por si algún
# código externo lo referencia

class NetworkInterface:
    def __init__(self, name: str, ip: str, netmask: str = "255.255.255.0"):
        self.name = name
        self.ip = ip
        self.netmask = netmask
        self.is_preferred = False
        self.is_active = False
        self.avolites_ip = None
        
    def __str__(self):
        status = "🟢" if self.is_active else "🔴"
        preferred = " ⭐" if self.is_preferred else ""
        avolites = f" → {self.avolites_ip}" if self.avolites_ip else ""
        return f"{status} {self.name}: {self.ip}{avolites}{preferred}"
    
    def suggest_avolites_ip(self) -> str:
        try:
            ip_obj = ipaddress.IPv4Address(self.ip)
            if str(ip_obj).startswith("10.0.0."):
                return "10.0.0.1"
            elif str(ip_obj).startswith("192.168."):
                parts = str(ip_obj).split('.')
                return f"192.168.{parts[2]}.1"
            else:
                parts = str(ip_obj).split('.')
                return f"{'.'.join(parts[:3])}.1"
        except:
            return "10.0.0.1"


class NetworkInterfaceDetector:
    def __init__(self):
        self.interfaces: List[NetworkInterface] = []
        self.preferred_networks = ["10.0.0.", "192.168.1.", "192.168.0."]
        
    def detect_interfaces(self) -> List[NetworkInterface]:
        self.interfaces.clear()
        
        # Usar nueva función list_interfaces()
        raw_interfaces = list_interfaces()
        
        for name, ip, mac, up in raw_interfaces:
            interface = NetworkInterface(name, ip)
            interface.is_active = up
            interface.avolites_ip = interface.suggest_avolites_ip()
            self.interfaces.append(interface)
        
        self._mark_preferred_interfaces()
        
        return self.interfaces
    
    def _mark_preferred_interfaces(self):
        # Marcar 10.0.0.x como preferida
        for interface in self.interfaces:
            if interface.ip.startswith("10.0.0."):
                interface.is_preferred = True
                break
        
        # Si no hay 10.0.0.x, marcar la primera de preferred_networks
        if not any(iface.is_preferred for iface in self.interfaces):
            for interface in self.interfaces:
                for preferred in self.preferred_networks:
                    if interface.ip.startswith(preferred):
                        interface.is_preferred = True
                        break
    
    def get_preferred_interface(self) -> Optional[NetworkInterface]:
        # Primero buscar 10.0.0.x
        for interface in self.interfaces:
            if interface.ip.startswith("10.0.0."):
                return interface
        
        # Luego buscar marcada como preferida
        for interface in self.interfaces:
            if interface.is_preferred:
                return interface
        
        # Luego buscar activa
        for interface in self.interfaces:
            if interface.is_active:
                return interface
        
        # Última opción: la primera
        return self.interfaces[0] if self.interfaces else None


# DEPRECADO: NetworkSelectorWidget ya no se usa en el header
# Se mantiene solo para compatibilidad con código legacy
class NetworkSelectorWidget:
    """
    DEPRECADO: Este widget ya no se usa.
    El selector de red ahora está integrado en el panel Red/Consola.
    Se mantiene esta clase vacía para evitar errores de importación.
    """
    def __init__(self, controller=None):
        print("[NETWORK] WARNING: NetworkSelectorWidget está deprecado. Usar panel Red/Consola.")
        pass


__all__ = [
    'list_interfaces',
    'ping_host',
    'NetworkInterface',
    'NetworkInterfaceDetector',
    'NetworkSelectorWidget'
]