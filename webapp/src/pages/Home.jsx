/**
 * Home V7 - Control Room Dashboard
 *
 * 5 bloques obligatorios:
 * 1. Audio Health (silence, clipping, level, device)
 * 2. Avolites (connected, IP, latency)
 * 3. Cámaras (online/offline, fps)
 * 4. Sistema (CPU, RAM, GPU, Temp)
 * 5. Calendario (día, hora, modo actual, próximo, timeline, AUTO/OVERRIDE)
 *
 * Tiempo real: SSE con fallback a polling
 */
import { useEffect, useState, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import {
  Music,
  Radio,
  Camera,
  Cpu,
  Calendar,
  Wifi,
  WifiOff,
  AlertTriangle,
  CheckCircle,
  Clock
} from 'lucide-react';

// Colores por modo de calendario
const modeColors = {
  clima_1: 'bg-blue-500',
  clima_2: 'bg-cyan-500',
  clima_3: 'bg-teal-500',
  clima_4: 'bg-green-500',
  boliche_inicio: 'bg-purple-500',
  boliche_desarrollo: 'bg-pink-500',
  boliche_fin: 'bg-red-500',
  apagado: 'bg-gray-500',
  teatro: 'bg-amber-500',
  artista: 'bg-orange-500',
};

// Formatear tiempo restante
function formatTime(seconds) {
  if (seconds < 0) return '—';
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  const remainMins = mins % 60;
  return `${hours}h ${remainMins}m`;
}

// Hook para SSE con fallback a polling
function useUnifiedStatus() {
  const [status, setStatus] = useState(null);
  const [connectionType, setConnectionType] = useState('none'); // 'sse' | 'polling' | 'none'
  const eventSourceRef = useRef(null);
  const pollingRef = useRef(null);

  useEffect(() => {
    let mounted = true;

    // Intentar SSE primero
    const connectSSE = () => {
      try {
        const es = new EventSource('/api/v1/stream');

        es.onopen = () => {
          if (mounted) {
            console.log('[SSE] connected');
            setConnectionType('sse');
            // Cancelar polling si estaba activo
            if (pollingRef.current) {
              clearInterval(pollingRef.current);
              pollingRef.current = null;
            }
          }
        };

        es.onmessage = (event) => {
          if (mounted) {
            try {
              const data = JSON.parse(event.data);
              setStatus(data);
            } catch (e) {
              console.error('[SSE] parse error:', e);
            }
          }
        };

        es.onerror = (error) => {
          console.warn('[SSE] error, falling back to polling');
          es.close();
          if (mounted) {
            setConnectionType('polling');
            startPolling();
          }
        };

        eventSourceRef.current = es;
      } catch (e) {
        console.warn('[SSE] not available, using polling');
        setConnectionType('polling');
        startPolling();
      }
    };

    // Fallback: polling cada 1s
    const startPolling = () => {
      const poll = async () => {
        try {
          const res = await fetch('/api/v1/status/unified');
          if (res.ok && mounted) {
            const data = await res.json();
            setStatus(data);
          }
        } catch (e) {
          console.error('[POLL] error:', e);
        }
      };

      poll(); // Primera carga inmediata
      pollingRef.current = setInterval(poll, 1000);
    };

    connectSSE();

    return () => {
      mounted = false;
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  return { status, connectionType };
}

// Componente de tarjeta genérica
function StatusCard({ icon: Icon, title, children, badge, className = '' }) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          {title}
        </CardTitle>
        {badge}
      </CardHeader>
      <CardContent>
        {children}
      </CardContent>
    </Card>
  );
}

// Bloque 1: Audio Health
function AudioBlock({ audio }) {
  if (!audio) return null;

  const isHealthy = !audio.silence && !audio.clipping;
  const levelPercent = Math.round((audio.level || 0) * 100);

  return (
    <StatusCard
      icon={Music}
      title="Audio"
      badge={
        isHealthy ? (
          <Badge className="bg-green-500">OK</Badge>
        ) : (
          <Badge className="bg-red-500">
            {audio.silence ? 'SILENCE' : 'CLIPPING'}
          </Badge>
        )
      }
    >
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Device</span>
          <span className="font-medium truncate max-w-[150px]">
            {audio.device || '—'}
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Level</span>
          <span className="font-medium">{levelPercent}%</span>
        </div>
        <div className="w-full bg-secondary rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all ${
              audio.clipping ? 'bg-red-500' : audio.silence ? 'bg-yellow-500' : 'bg-green-500'
            }`}
            style={{ width: `${Math.min(100, levelPercent)}%` }}
          />
        </div>
      </div>
    </StatusCard>
  );
}

// Bloque 2: Avolites
function AvolitesBlock({ avolites }) {
  if (!avolites) return null;

  return (
    <StatusCard
      icon={Radio}
      title="Avolites"
      badge={
        avolites.connected ? (
          <Badge className="bg-green-500 flex items-center gap-1">
            <Wifi className="h-3 w-3" /> Connected
          </Badge>
        ) : (
          <Badge className="bg-red-500 flex items-center gap-1">
            <WifiOff className="h-3 w-3" /> Offline
          </Badge>
        )
      }
    >
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Console IP</span>
          <span className="font-medium">{avolites.console_ip || '—'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Port</span>
          <span className="font-medium">{avolites.port}</span>
        </div>
        {avolites.latency_ms !== null && (
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Latency</span>
            <span className="font-medium">{avolites.latency_ms}ms</span>
          </div>
        )}
      </div>
    </StatusCard>
  );
}

// Bloque 3: Cámaras
function CamerasBlock({ cameras }) {
  if (!cameras || cameras.length === 0) {
    return (
      <StatusCard icon={Camera} title="Cameras">
        <p className="text-sm text-muted-foreground">No cameras configured</p>
      </StatusCard>
    );
  }

  const onlineCount = cameras.filter(c => c.online).length;

  return (
    <StatusCard
      icon={Camera}
      title="Cameras"
      badge={
        <Badge className={onlineCount === cameras.length ? 'bg-green-500' : 'bg-yellow-500'}>
          {onlineCount}/{cameras.length} online
        </Badge>
      }
    >
      <div className="space-y-2">
        {cameras.map((cam) => (
          <div key={cam.name} className="flex justify-between items-center text-sm">
            <span className="text-muted-foreground capitalize">{cam.name}</span>
            <div className="flex items-center gap-2">
              {cam.online ? (
                <>
                  <span className="text-green-500">{cam.fps} fps</span>
                  <CheckCircle className="h-3 w-3 text-green-500" />
                </>
              ) : (
                <>
                  <span className="text-red-500">offline</span>
                  <AlertTriangle className="h-3 w-3 text-red-500" />
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </StatusCard>
  );
}

// Bloque 4: Sistema
function SystemBlock({ system }) {
  if (!system) return null;

  const metrics = [
    { label: 'CPU', value: system.cpu, color: system.cpu > 80 ? 'bg-red-500' : 'bg-blue-500' },
    { label: 'RAM', value: system.ram, color: system.ram > 80 ? 'bg-red-500' : 'bg-purple-500' },
    { label: 'GPU', value: system.gpu, color: system.gpu > 80 ? 'bg-red-500' : 'bg-green-500' },
  ];

  return (
    <StatusCard icon={Cpu} title="System">
      <div className="space-y-3">
        {metrics.map(({ label, value, color }) => (
          <div key={label}>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-muted-foreground">{label}</span>
              <span className="font-medium">{value}%</span>
            </div>
            <div className="w-full bg-secondary rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full transition-all ${color}`}
                style={{ width: `${Math.min(100, value)}%` }}
              />
            </div>
          </div>
        ))}
        {system.temp > 0 && (
          <div className="flex justify-between text-sm pt-1">
            <span className="text-muted-foreground">Temp</span>
            <span className={`font-medium ${system.temp > 75 ? 'text-red-500' : ''}`}>
              {system.temp}°C
            </span>
          </div>
        )}
      </div>
    </StatusCard>
  );
}

// Bloque 5: Calendario
function CalendarBlock({ calendar }) {
  if (!calendar) return null;

  const modeColor = modeColors[calendar.current_mode] || 'bg-gray-500';

  return (
    <StatusCard
      icon={Calendar}
      title="Calendar"
      badge={
        calendar.override_active ? (
          <Badge className="bg-orange-500">OVERRIDE</Badge>
        ) : calendar.auto ? (
          <Badge className="bg-green-500">AUTO</Badge>
        ) : (
          <Badge className="bg-gray-500">MANUAL</Badge>
        )
      }
      className="md:col-span-2"
    >
      <div className="space-y-3">
        {/* Fecha y hora */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground capitalize">{calendar.day}</span>
          </div>
          <span className="text-lg font-mono">{calendar.time}</span>
        </div>

        {/* Modo actual */}
        <div className="flex justify-between items-center">
          <span className="text-sm text-muted-foreground">Current Mode</span>
          <Badge className={`${modeColor} text-white`}>
            {calendar.current_mode}
          </Badge>
        </div>

        {/* Próximo modo */}
        {calendar.next_mode && (
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Next Mode</span>
            <div className="flex items-center gap-2">
              <Badge variant="outline">
                {calendar.next_mode}
              </Badge>
              <span className="text-xs text-muted-foreground">
                in {formatTime(calendar.time_to_next_s)}
              </span>
            </div>
          </div>
        )}

        {/* Timeline progress */}
        {calendar.time_remaining_s > 0 && (
          <div>
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>Block progress</span>
              <span>{formatTime(calendar.time_remaining_s)} remaining</span>
            </div>
            <div className="w-full bg-secondary rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${modeColor}`}
                style={{
                  width: `${Math.max(5, 100 - (calendar.time_remaining_s / 36))}%`
                }}
              />
            </div>
          </div>
        )}
      </div>
    </StatusCard>
  );
}

// Página principal
export function Home() {
  const { status, connectionType } = useUnifiedStatus();

  if (!status) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Connecting to system...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header con indicador de conexión */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <Badge variant="outline" className="text-xs">
          {connectionType === 'sse' ? '● SSE' : connectionType === 'polling' ? '○ Polling' : '○ Offline'}
        </Badge>
      </div>

      {/* Grid de 5 bloques */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <AudioBlock audio={status.audio} />
        <AvolitesBlock avolites={status.avolites} />
        <CamerasBlock cameras={status.cameras} />
        <SystemBlock system={status.system} />
        <CalendarBlock calendar={status.calendar} />
      </div>
    </div>
  );
}
