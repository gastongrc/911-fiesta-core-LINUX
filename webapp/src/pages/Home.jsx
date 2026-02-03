/**
 * Home V7 - Control Room Dashboard (Estilo Industrial)
 *
 * SOLO muestra:
 * - Audio: silence / clipping
 * - Avolites: connected
 * - Cámaras: haze / people / tracking (OK/FAIL)
 * - Sistema: CPU / RAM / energía
 * - Calendario: día, hora BIOS, modo actual, timeline, próximo
 *
 * Estilo: Oscuro, denso, técnico (consola industrial)
 */
import { useEffect, useState, useRef } from 'react';

// Colores por modo (del calendario viejo)
const MODE_COLORS = {
  clima_1: '#1abc9c',
  clima_2: '#16a085',
  clima_3: '#2ecc71',
  clima_4: '#27ae60',
  teatro: '#3498db',
  artista: '#9b59b6',
  boliche_inicio: '#f39c12',
  boliche_desarrollo: '#e67e22',
  boliche_fin: '#e74c3c',
  apagado: '#7f8c8d',
};

const DAY_NAMES = {
  monday: 'LUNES', tuesday: 'MARTES', wednesday: 'MIÉRCOLES',
  thursday: 'JUEVES', friday: 'VIERNES', saturday: 'SÁBADO', sunday: 'DOMINGO'
};

// Hook para SSE con fallback a polling
function useUnifiedStatus() {
  const [status, setStatus] = useState(null);
  const [connectionType, setConnectionType] = useState('none');
  const eventSourceRef = useRef(null);
  const pollingRef = useRef(null);

  useEffect(() => {
    let mounted = true;

    const connectSSE = () => {
      try {
        const es = new EventSource('/api/v1/stream');
        es.onopen = () => {
          if (mounted) {
            setConnectionType('sse');
            if (pollingRef.current) {
              clearInterval(pollingRef.current);
              pollingRef.current = null;
            }
          }
        };
        es.onmessage = (event) => {
          if (mounted) {
            try {
              setStatus(JSON.parse(event.data));
            } catch (e) {}
          }
        };
        es.onerror = () => {
          es.close();
          if (mounted) {
            setConnectionType('polling');
            startPolling();
          }
        };
        eventSourceRef.current = es;
      } catch (e) {
        setConnectionType('polling');
        startPolling();
      }
    };

    const startPolling = () => {
      const poll = async () => {
        try {
          const res = await fetch('/api/v1/status/unified');
          if (res.ok && mounted) setStatus(await res.json());
        } catch (e) {}
      };
      poll();
      pollingRef.current = setInterval(poll, 1000);
    };

    connectSSE();

    return () => {
      mounted = false;
      if (eventSourceRef.current) eventSourceRef.current.close();
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  return { status, connectionType };
}

// Formatea segundos a display
function formatTime(seconds) {
  if (seconds < 0) return '---';
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m`;
}

// Panel genérico estilo industrial
function Panel({ title, children, status, statusColor }) {
  return (
    <div style={{
      background: '#1e272e',
      borderRadius: '8px',
      border: '1px solid #34495e',
      padding: '12px',
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '10px',
        borderBottom: '1px solid #34495e',
        paddingBottom: '8px',
      }}>
        <span style={{ color: '#7f8c8d', fontSize: '10px', fontWeight: 'bold', letterSpacing: '1px' }}>
          {title}
        </span>
        {status && (
          <span style={{
            color: statusColor || '#2ecc71',
            fontSize: '10px',
            fontWeight: 'bold',
            background: `${statusColor || '#2ecc71'}20`,
            padding: '2px 8px',
            borderRadius: '4px',
          }}>
            {status}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

// Indicador simple
function Indicator({ label, value, ok }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '4px 0',
    }}>
      <span style={{ color: '#7f8c8d', fontSize: '11px' }}>{label}</span>
      <span style={{
        color: ok === true ? '#2ecc71' : ok === false ? '#e74c3c' : '#ecf0f1',
        fontSize: '11px',
        fontWeight: 'bold',
      }}>
        {value}
      </span>
    </div>
  );
}

// Bloque Audio
function AudioPanel({ audio }) {
  if (!audio) return null;
  const isOk = !audio.silence && !audio.clipping;
  return (
    <Panel
      title="AUDIO"
      status={audio.silence ? 'SILENCE' : audio.clipping ? 'CLIPPING' : 'OK'}
      statusColor={isOk ? '#2ecc71' : '#e74c3c'}
    >
      <Indicator label="Silence" value={audio.silence ? 'YES' : 'NO'} ok={!audio.silence} />
      <Indicator label="Clipping" value={audio.clipping ? 'YES' : 'NO'} ok={!audio.clipping} />
      <Indicator label="Device" value={audio.device || '---'} />
    </Panel>
  );
}

// Bloque Avolites
function AvolitesPanel({ avolites }) {
  if (!avolites) return null;
  return (
    <Panel
      title="AVOLITES"
      status={avolites.connected ? 'CONNECTED' : 'OFFLINE'}
      statusColor={avolites.connected ? '#2ecc71' : '#e74c3c'}
    >
      <Indicator label="Connected" value={avolites.connected ? 'YES' : 'NO'} ok={avolites.connected} />
      <Indicator label="Console IP" value={avolites.console_ip || '---'} />
      <Indicator label="Port" value={avolites.port || '---'} />
      {avolites.latency_ms != null && (
        <Indicator label="Latency" value={`${avolites.latency_ms}ms`} />
      )}
    </Panel>
  );
}

// Bloque Cámaras
function CamerasPanel({ cameras }) {
  const camTypes = ['haze', 'people', 'tracking'];
  const camMap = {};
  (cameras || []).forEach(c => { camMap[c.name] = c; });

  const allOk = camTypes.every(t => camMap[t]?.online);

  return (
    <Panel
      title="CÁMARAS"
      status={allOk ? 'ALL OK' : 'FAIL'}
      statusColor={allOk ? '#2ecc71' : '#e74c3c'}
    >
      {camTypes.map(type => {
        const cam = camMap[type];
        const online = cam?.online;
        return (
          <Indicator
            key={type}
            label={type.toUpperCase()}
            value={online ? `OK (${cam.fps} fps)` : 'FAIL'}
            ok={online}
          />
        );
      })}
    </Panel>
  );
}

// Bloque Sistema
function SystemPanel({ system }) {
  if (!system) return null;
  const cpuHigh = system.cpu > 80;
  const ramHigh = system.ram > 80;

  return (
    <Panel title="SISTEMA">
      <div style={{ marginBottom: '8px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span style={{ color: '#7f8c8d', fontSize: '10px' }}>CPU</span>
          <span style={{ color: cpuHigh ? '#e74c3c' : '#ecf0f1', fontSize: '10px', fontWeight: 'bold' }}>
            {system.cpu}%
          </span>
        </div>
        <div style={{
          background: '#2c3e50',
          borderRadius: '4px',
          height: '6px',
          overflow: 'hidden',
        }}>
          <div style={{
            background: cpuHigh ? '#e74c3c' : '#3498db',
            height: '100%',
            width: `${Math.min(100, system.cpu)}%`,
            transition: 'width 0.3s',
          }} />
        </div>
      </div>
      <div style={{ marginBottom: '8px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span style={{ color: '#7f8c8d', fontSize: '10px' }}>RAM</span>
          <span style={{ color: ramHigh ? '#e74c3c' : '#ecf0f1', fontSize: '10px', fontWeight: 'bold' }}>
            {system.ram}%
          </span>
        </div>
        <div style={{
          background: '#2c3e50',
          borderRadius: '4px',
          height: '6px',
          overflow: 'hidden',
        }}>
          <div style={{
            background: ramHigh ? '#e74c3c' : '#9b59b6',
            height: '100%',
            width: `${Math.min(100, system.ram)}%`,
            transition: 'width 0.3s',
          }} />
        </div>
      </div>
      {system.gpu > 0 && <Indicator label="GPU" value={`${system.gpu}%`} />}
      {system.temp > 0 && <Indicator label="Temp" value={`${system.temp}°C`} ok={system.temp < 75} />}
    </Panel>
  );
}

// Bloque Calendario (principal, más grande)
function CalendarPanel({ calendar }) {
  if (!calendar) return null;

  const modeColor = MODE_COLORS[calendar.current_mode] || '#7f8c8d';
  const dayName = DAY_NAMES[calendar.day?.toLowerCase()] || calendar.day?.toUpperCase() || '---';

  return (
    <div style={{
      background: 'linear-gradient(to bottom, #2c3e50, #1a252f)',
      borderRadius: '10px',
      border: '1px solid #34495e',
      padding: '16px',
      gridColumn: 'span 2',
    }}>
      {/* Header: Día y Hora */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '12px',
      }}>
        <span style={{ color: '#ecf0f1', fontSize: '14px', fontWeight: 'bold' }}>
          {dayName}
        </span>
        <span style={{
          color: '#ecf0f1',
          fontSize: '32px',
          fontWeight: 'bold',
          fontFamily: 'monospace',
        }}>
          {calendar.time || '--:--:--'}
        </span>
      </div>

      {/* Separador */}
      <div style={{ background: '#34495e', height: '1px', marginBottom: '12px' }} />

      {/* Modo actual */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '12px',
      }}>
        <span style={{ color: '#7f8c8d', fontSize: '10px' }}>CALENDARIO</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{
            color: modeColor,
            fontSize: '18px',
            fontWeight: 'bold',
          }}>
            {calendar.current_mode}
          </span>
          {calendar.override_active && (
            <span style={{
              color: '#e74c3c',
              fontSize: '9px',
              fontWeight: 'bold',
              background: 'rgba(231,76,60,0.2)',
              padding: '2px 6px',
              borderRadius: '3px',
            }}>
              OVERRIDE
            </span>
          )}
          <span style={{
            color: calendar.auto ? '#2ecc71' : '#f39c12',
            fontSize: '9px',
            fontWeight: 'bold',
            background: calendar.auto ? 'rgba(46,204,113,0.2)' : 'rgba(243,156,18,0.2)',
            padding: '2px 6px',
            borderRadius: '3px',
          }}>
            {calendar.auto ? 'AUTO' : 'MANUAL'}
          </span>
        </div>
      </div>

      {/* Timeline */}
      <div style={{
        background: '#1e272e',
        borderRadius: '6px',
        padding: '10px',
        border: '1px solid #34495e',
      }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginBottom: '6px',
        }}>
          <span style={{ color: '#7f8c8d', fontSize: '9px' }}>TIMELINE</span>
          <span style={{ color: '#2ecc71', fontSize: '9px', fontWeight: 'bold' }}>ACTIVO</span>
        </div>
        {/* Barra de progreso */}
        <div style={{
          background: '#2c3e50',
          borderRadius: '6px',
          height: '12px',
          overflow: 'hidden',
          marginBottom: '8px',
        }}>
          <div style={{
            background: modeColor,
            height: '100%',
            width: calendar.time_remaining_s > 0
              ? `${Math.max(5, 100 - (calendar.time_remaining_s / 36))}%`
              : '0%',
            transition: 'width 0.3s',
            borderRadius: '6px',
          }} />
        </div>
        {/* Info */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: '10px',
        }}>
          <span style={{ color: '#7f8c8d' }}>
            Restante: {formatTime(calendar.time_remaining_s)}
          </span>
          {calendar.next_mode && (
            <span style={{ color: '#95a5a6' }}>
              Próximo: <strong style={{ color: '#ecf0f1' }}>{calendar.next_mode}</strong> en {formatTime(calendar.time_to_next_s)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// Página principal
export function Home() {
  const { status, connectionType } = useUnifiedStatus();

  if (!status) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        color: '#7f8c8d',
      }}>
        <div style={{
          width: '40px',
          height: '40px',
          border: '3px solid #34495e',
          borderTopColor: '#3498db',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
        }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <p style={{ marginTop: '16px' }}>Conectando al sistema...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '16px' }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '16px',
      }}>
        <h2 style={{ color: '#ecf0f1', fontSize: '18px', fontWeight: 'bold', margin: 0 }}>
          CONTROL ROOM
        </h2>
        <span style={{
          color: connectionType === 'sse' ? '#2ecc71' : connectionType === 'polling' ? '#f39c12' : '#e74c3c',
          fontSize: '10px',
          fontWeight: 'bold',
          background: connectionType === 'sse' ? 'rgba(46,204,113,0.2)' : 'rgba(243,156,18,0.2)',
          padding: '4px 8px',
          borderRadius: '4px',
        }}>
          {connectionType === 'sse' ? '● SSE' : connectionType === 'polling' ? '○ POLLING' : '○ OFFLINE'}
        </span>
      </div>

      {/* Grid de paneles */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '12px',
      }}>
        <AudioPanel audio={status.audio} />
        <AvolitesPanel avolites={status.avolites} />
        <CamerasPanel cameras={status.cameras} />
        <SystemPanel system={status.system} />
        <CalendarPanel calendar={status.calendar} />
      </div>
    </div>
  );
}
