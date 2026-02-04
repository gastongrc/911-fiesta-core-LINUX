/**
 * Home V7 - Control Room Dashboard (NEON UI)
 *
 * SOLO muestra:
 * - Audio: silence / clipping
 * - Avolites: connected
 * - Cámaras: haze / people / tracking (OK/FAIL)
 * - Sistema: CPU / RAM / energía
 * - Calendario: día, hora BIOS, modo actual, timeline, próximo
 *
 * Estilo: NEON (glow + cards con bordes iluminados)
 */
import { useEffect, useState, useRef, useCallback } from 'react';
import { getApiBase } from '../lib/apiBase';

// Colores por modo
const MODE_COLORS = {
  clima_1: '#1abc9c', clima_2: '#16a085', clima_3: '#2ecc71', clima_4: '#27ae60',
  teatro: '#3498db', artista: '#9b59b6',
  boliche_inicio: '#f39c12', boliche_desarrollo: '#e67e22', boliche_fin: '#e74c3c',
  apagado: '#7f8c8d',
};

const DAY_NAMES = {
  monday: 'LUNES', tuesday: 'MARTES', wednesday: 'MIÉRCOLES',
  thursday: 'JUEVES', friday: 'VIERNES', saturday: 'SÁBADO', sunday: 'DOMINGO',
  lunes: 'LUNES', martes: 'MARTES', miércoles: 'MIÉRCOLES',
  jueves: 'JUEVES', viernes: 'VIERNES', sábado: 'SÁBADO', domingo: 'DOMINGO'
};

// Hook para SSE con fallback a polling y reconexión
function useUnifiedStatus() {
  const [status, setStatus] = useState(null);
  const [connectionType, setConnectionType] = useState('connecting');
  const [error, setError] = useState(null);
  const eventSourceRef = useRef(null);
  const pollingRef = useRef(null);
  const retryDelayRef = useRef(1000);

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    cleanup();
    setConnectionType('polling');

    const poll = async () => {
      try {
        const res = await fetch(`${getApiBase()}/status/unified`);
        if (res.ok) {
          const data = await res.json();
          setStatus(data);
          setError(null);
        } else {
          setError(`HTTP ${res.status}`);
        }
      } catch (e) {
        setError('API offline');
      }
    };

    poll();
    pollingRef.current = setInterval(poll, 1000);
  }, [cleanup]);

  const connectSSE = useCallback(() => {
    cleanup();
    setConnectionType('connecting');

    try {
      const apiBase = getApiBase();
      // Construir URL absoluta para SSE
      const sseUrl = apiBase.startsWith('/')
        ? `${window.location.origin}${apiBase}/stream`
        : `${apiBase}/stream`;

      const es = new EventSource(sseUrl);

      es.onopen = () => {
        setConnectionType('sse');
        setError(null);
        retryDelayRef.current = 1000; // Reset retry delay
      };

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (!data.error) {
            setStatus(data);
            setError(null);
          }
        } catch (e) {}
      };

      es.onerror = () => {
        es.close();
        // Retry con backoff exponencial
        const delay = retryDelayRef.current;
        retryDelayRef.current = Math.min(delay * 2, 10000);

        setTimeout(() => {
          // Intentar SSE de nuevo, si falla mucho pasar a polling
          if (retryDelayRef.current >= 10000) {
            startPolling();
          } else {
            connectSSE();
          }
        }, delay);
      };

      eventSourceRef.current = es;
    } catch (e) {
      startPolling();
    }
  }, [cleanup, startPolling]);

  useEffect(() => {
    connectSSE();
    return cleanup;
  }, [connectSSE, cleanup]);

  return { status, connectionType, error };
}

// Formatea segundos
function formatTime(s) {
  if (s == null || s < 0) return '---';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

// Panel Neon
function NeonPanel({ title, status, statusType, children }) {
  return (
    <div className="neon-panel">
      <div className="neon-panel-header">
        <span className="neon-panel-title">{title}</span>
        {status && (
          <span className={`neon-badge neon-badge-${statusType || 'info'}`}>
            {status}
          </span>
        )}
      </div>
      <div className="neon-panel-content">
        {children}
      </div>
    </div>
  );
}

// Indicador
function Indicator({ label, value, type }) {
  return (
    <div className="neon-indicator">
      <span className="neon-indicator-label">{label}</span>
      <span className={`neon-indicator-value ${type || ''}`}>{value}</span>
    </div>
  );
}

// Panel Audio
function AudioPanel({ audio }) {
  if (!audio) return null;
  const isOk = !audio.silence && !audio.clipping;
  const statusText = audio.silence ? 'SILENCE' : audio.clipping ? 'CLIPPING' : 'OK';

  return (
    <NeonPanel title="AUDIO" status={statusText} statusType={isOk ? 'ok' : 'error'}>
      <Indicator label="Silence" value={audio.silence ? 'YES' : 'NO'} type={!audio.silence ? 'ok' : 'error'} />
      <Indicator label="Clipping" value={audio.clipping ? 'YES' : 'NO'} type={!audio.clipping ? 'ok' : 'error'} />
      <Indicator label="Device" value={audio.device || '---'} />
    </NeonPanel>
  );
}

// Panel Avolites
function AvolitesPanel({ avolites }) {
  if (!avolites) return null;

  return (
    <NeonPanel
      title="AVOLITES"
      status={avolites.connected ? 'CONNECTED' : 'OFFLINE'}
      statusType={avolites.connected ? 'ok' : 'error'}
    >
      <Indicator label="Status" value={avolites.connected ? 'Online' : 'Offline'} type={avolites.connected ? 'ok' : 'error'} />
      <Indicator label="Console" value={avolites.console_ip || '---'} />
      <Indicator label="Port" value={avolites.port || '---'} />
      {avolites.latency_ms != null && (
        <Indicator label="Latency" value={`${avolites.latency_ms}ms`} type={avolites.latency_ms < 50 ? 'ok' : 'warn'} />
      )}
    </NeonPanel>
  );
}

// Panel Cámaras
function CamerasPanel({ cameras }) {
  const camTypes = ['haze', 'people', 'tracking'];
  const camMap = {};
  (cameras || []).forEach(c => { camMap[c.name] = c; });
  const allOk = camTypes.every(t => camMap[t]?.online);

  return (
    <NeonPanel
      title="CÁMARAS"
      status={allOk ? 'ALL OK' : 'FAIL'}
      statusType={allOk ? 'ok' : 'error'}
    >
      {camTypes.map(type => {
        const cam = camMap[type];
        const online = cam?.online;
        return (
          <Indicator
            key={type}
            label={type.toUpperCase()}
            value={online ? `OK (${cam.fps} fps)` : 'OFFLINE'}
            type={online ? 'ok' : 'error'}
          />
        );
      })}
    </NeonPanel>
  );
}

// Panel Sistema
function SystemPanel({ system }) {
  if (!system) return null;
  const cpuHigh = system.cpu > 80;
  const ramHigh = system.ram > 80;

  return (
    <NeonPanel title="SISTEMA">
      <div style={{ marginBottom: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span className="neon-indicator-label">CPU</span>
          <span className={`neon-indicator-value ${cpuHigh ? 'error' : 'ok'}`}>{system.cpu}%</span>
        </div>
        <div className="neon-progress">
          <div
            className={`neon-progress-bar ${cpuHigh ? 'red' : 'cyan'}`}
            style={{ width: `${Math.min(100, system.cpu)}%` }}
          />
        </div>
      </div>
      <div style={{ marginBottom: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span className="neon-indicator-label">RAM</span>
          <span className={`neon-indicator-value ${ramHigh ? 'error' : 'ok'}`}>{system.ram}%</span>
        </div>
        <div className="neon-progress">
          <div
            className={`neon-progress-bar ${ramHigh ? 'orange' : 'green'}`}
            style={{ width: `${Math.min(100, system.ram)}%` }}
          />
        </div>
      </div>
    </NeonPanel>
  );
}

// Panel Calendario (principal)
function CalendarPanel({ calendar }) {
  if (!calendar) return null;

  const modeColor = MODE_COLORS[calendar.current_mode] || '#7f8c8d';
  const dayName = DAY_NAMES[calendar.day?.toLowerCase()] || calendar.day?.toUpperCase() || '---';

  return (
    <div className="neon-panel" style={{ gridColumn: 'span 2' }}>
      <div className="neon-panel-header">
        <span className="neon-panel-title">CALENDARIO</span>
        <div style={{ display: 'flex', gap: '8px' }}>
          {calendar.override_active && (
            <span className="neon-badge neon-badge-warn">OVERRIDE</span>
          )}
          <span className={`neon-badge ${calendar.auto ? 'neon-badge-ok' : 'neon-badge-warn'}`}>
            {calendar.auto ? 'AUTO' : 'MANUAL'}
          </span>
        </div>
      </div>
      <div className="neon-panel-content">
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <span style={{ color: 'var(--text-normal)', fontSize: '14px', fontWeight: '600' }}>
            {dayName}
          </span>
          <span style={{
            color: 'var(--neon-cyan)',
            fontSize: '28px',
            fontWeight: 'bold',
            fontFamily: 'monospace',
            textShadow: '0 0 10px var(--neon-cyan)',
          }}>
            {calendar.time || '--:--:--'}
          </span>
        </div>

        {/* Modo actual */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '16px',
          padding: '12px',
          background: 'var(--bg-dark)',
          borderRadius: '6px',
          border: `1px solid ${modeColor}40`,
        }}>
          <span style={{ color: 'var(--text-dim)', fontSize: '10px', textTransform: 'uppercase' }}>Modo</span>
          <span style={{
            color: modeColor,
            fontSize: '18px',
            fontWeight: 'bold',
            textShadow: `0 0 15px ${modeColor}`,
          }}>
            {calendar.current_mode}
          </span>
        </div>

        {/* Timeline */}
        <div className="neon-timeline">
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span className="neon-indicator-label">Timeline</span>
            <span className="neon-indicator-value ok">ACTIVO</span>
          </div>
          <div className="neon-progress" style={{ height: '12px', marginBottom: '8px' }}>
            <div
              className="neon-progress-bar"
              style={{
                width: calendar.time_remaining_s > 0
                  ? `${Math.max(5, 100 - (calendar.time_remaining_s / 36))}%`
                  : '0%',
                background: modeColor,
              }}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px' }}>
            <span style={{ color: 'var(--text-dim)' }}>
              Restante: {formatTime(calendar.time_remaining_s)}
            </span>
            {calendar.next_mode && (
              <span style={{ color: 'var(--text-dim)' }}>
                Próximo: <strong style={{ color: 'var(--neon-green)' }}>{calendar.next_mode}</strong>
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Página principal
export function Home() {
  const { status, connectionType, error } = useUnifiedStatus();

  // Loading state
  if (!status && connectionType === 'connecting') {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        gap: '16px',
      }}>
        <div style={{
          width: '50px',
          height: '50px',
          border: '3px solid var(--border-dim)',
          borderTopColor: 'var(--neon-cyan)',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
        }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <p style={{ color: 'var(--neon-cyan)', fontSize: '12px' }}>Conectando al sistema...</p>
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
        marginBottom: '20px',
      }}>
        <h2 style={{
          color: 'var(--neon-cyan)',
          fontSize: '18px',
          fontWeight: 'bold',
          margin: 0,
          textShadow: '0 0 10px var(--neon-cyan)',
          letterSpacing: '2px',
        }}>
          CONTROL ROOM
        </h2>
        <div className="neon-connection">
          <span
            className={`neon-connection-dot ${connectionType === 'sse' || connectionType === 'polling' ? 'online' : 'offline'}`}
          />
          <span style={{ color: connectionType === 'sse' ? 'var(--neon-green)' : 'var(--neon-orange)' }}>
            {connectionType === 'sse' ? 'SSE' : connectionType === 'polling' ? 'POLLING' : 'OFFLINE'}
          </span>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{
          background: 'rgba(255, 68, 68, 0.1)',
          border: '1px solid var(--neon-red)',
          borderRadius: '6px',
          padding: '12px',
          marginBottom: '16px',
          textAlign: 'center',
        }}>
          <span style={{ color: 'var(--neon-red)', fontSize: '12px', fontWeight: 'bold' }}>
            ⚠ API OFFLINE - {error}
          </span>
        </div>
      )}

      {/* Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '12px',
      }}>
        <AudioPanel audio={status?.audio} />
        <AvolitesPanel avolites={status?.avolites} />
        <CamerasPanel cameras={status?.cameras} />
        <SystemPanel system={status?.system} />
        <CalendarPanel calendar={status?.calendar} />
      </div>
    </div>
  );
}
