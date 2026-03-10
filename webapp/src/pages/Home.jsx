/**
 * Home — Control Room + Status Dashboard (merged)
 *
 * Matches UI contract:
 * - docs/ui-contract/control_room_glass.html
 * - docs/ui-contract/status_dashboard.html
 *
 * Uses glass design system exclusively (control-room.css)
 * SSE/polling hook preserved for live data
 */
import { useEffect, useState, useRef, useCallback } from 'react';
import { getApiBase, apiPost } from '../lib/apiBase';

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
      const sseUrl = apiBase.startsWith('/')
        ? `${window.location.origin}${apiBase}/stream`
        : `${apiBase}/stream`;

      const es = new EventSource(sseUrl);

      es.onopen = () => {
        setConnectionType('sse');
        setError(null);
        retryDelayRef.current = 1000;
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
        const delay = retryDelayRef.current;
        retryDelayRef.current = Math.min(delay * 2, 10000);

        setTimeout(() => {
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

// Safe value or placeholder
function val(v, fallback = '---') {
  return v != null && v !== '' ? v : fallback;
}

// Format uptime seconds
function formatUptime(s) {
  if (s == null || s < 0) return '---';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

// LED component matching contract (.led, .led.yellow, .led.red, .led.off)
function LED({ color }) {
  const cls = color === 'off' ? 'led off'
    : color === 'yellow' ? 'led yellow'
    : color === 'red' ? 'led red'
    : 'led';
  return <div className={cls} />;
}

// LED state from boolean
function ledColor(online) {
  if (online === true) return 'green';
  if (online === false) return 'red';
  return 'off';
}

export function Home() {
  const { status, connectionType, error } = useUnifiedStatus();
  const [actionLoading, setActionLoading] = useState(null);

  const s = status || {};
  const sys = s.system || {};
  const avo = s.avolites || {};
  const audio = s.audio || {};
  const cal = s.calendar || {};

  const handleReconectar = async () => {
    setActionLoading('reconectar');
    try {
      await apiPost('/config/avolites', { data: { console_ip: avo.console_ip, console_port: avo.console_port || 4430 } });
    } catch (e) {}
    setActionLoading(null);
  };

  const isConnected = connectionType === 'sse' || connectionType === 'polling';

  // Loading state
  if (!status && connectionType === 'connecting') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '16px' }}>
        <div className="led" />
        <p className="t3 text-sm">Conectando al sistema...</p>
      </div>
    );
  }

  return (
    <>
      {/* ═══ HEADER ═══ */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1 style={{ fontFamily: 'var(--font-title)', fontSize: '24px', fontWeight: 700 }}>Control Room</h1>
          <div className="b gray">{val(s.version, 'v---')}</div>
        </div>
        <div className="b">
          <div className={`led-dot${isConnected ? '' : ' off'}`} />
          {connectionType === 'sse' ? 'SSE' : connectionType === 'polling' ? 'POLL' : 'OFF'}
        </div>
      </div>

      {/* ═══ ERROR BANNER ═══ */}
      {error && (
        <div className="flex items-center justify-between p-3" style={{ background: 'rgba(255,82,82,0.1)', borderBottom: '1px solid var(--red)' }}>
          <span className="red font-bold text-sm">API OFFLINE — {error}</span>
        </div>
      )}

      <div style={{ flex: 1, padding: '0 28px 28px', overflowY: 'auto' }}>

        {/* ═══ METRICS BAR (control_room_glass.html) ═══ */}
        <div className="g" style={{ marginBottom: '24px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px' }}>
            <div className="inset">
              <div className="t3 text-sm">CPU</div>
              <div className="green text-xl font-bold mono">{val(sys.cpu, '0')}%</div>
              <div className="gauge mt-2">
                <div className={`gauge-fill${sys.cpu > 80 ? ' warning' : ''}`} style={{ width: `${Math.min(100, sys.cpu || 0)}%` }} />
              </div>
            </div>
            <div className="inset">
              <div className="t3 text-sm">RAM</div>
              <div className="cyan text-xl font-bold mono">{val(sys.ram, '0')}%</div>
              <div className="gauge mt-2">
                <div className={`gauge-fill${sys.ram > 80 ? ' warning' : ''}`} style={{ width: `${Math.min(100, sys.ram || 0)}%` }} />
              </div>
            </div>
            <div className="inset">
              <div className="t3 text-sm">BPM</div>
              <div className="green text-xl font-bold mono">{val(s.bpm, '---')}</div>
            </div>
            <div className="inset">
              <div className="t3 text-sm">Uptime</div>
              <div className="t1 text-xl font-bold mono">{formatUptime(sys.uptime_s)}</div>
            </div>
          </div>
        </div>

        {/* ═══ CARDS GRID (merged control_room + status_dashboard) ═══ */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>

          {/* — Consola Avolites — */}
          <div className="g">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold">Consola Avolites</h3>
              <LED color={ledColor(avo.connected)} />
            </div>
            <div className="inset mb-2">
              <div className="flex justify-between mb-2">
                <span className="t3 text-sm">IP Consola</span>
                <span className="mono text-sm">{val(avo.console_ip)}</span>
              </div>
              <div className="flex justify-between">
                <span className="t3 text-sm">Estado</span>
                <span className={`text-sm ${avo.connected ? 'green' : 'red'}`}>
                  {avo.connected ? 'Conectado' : 'Offline'}
                </span>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginTop: '20px' }}>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">Latencia</div>
                <div className="green mono font-bold">{val(avo.latency_ms, '---')}ms</div>
              </div>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">Uptime</div>
                <div className="green mono font-bold">{val(avo.uptime_pct, '---')}%</div>
              </div>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">Errores</div>
                <div className="green mono font-bold">{val(avo.errors, '0')}</div>
              </div>
            </div>
            <button className="key w-full mt-3" onClick={handleReconectar} disabled={actionLoading === 'reconectar'}>
              {actionLoading === 'reconectar' ? 'Reconectando...' : 'Reconectar'}
            </button>
          </div>

          {/* — Audio Input + Placa de Sonido (merged) — */}
          <div className="g">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold">Placa de Sonido</h3>
              <LED color={audio.device ? (audio.clipping ? 'red' : audio.silence ? 'yellow' : 'green') : 'off'} />
            </div>
            <div className="inset mb-2">
              <div className="flex justify-between mb-2">
                <span className="t3 text-sm">Dispositivo</span>
                <span className="mono text-sm">{val(audio.device)}</span>
              </div>
              <div className="flex justify-between">
                <span className="t3 text-sm">Estado</span>
                <span className={`text-sm ${audio.clipping ? 'red' : audio.silence ? 'yellow' : 'green'}`}>
                  {audio.clipping ? 'CLIPPING' : audio.silence ? 'SILENCE' : 'OK'}
                </span>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginTop: '20px' }}>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">Nivel</div>
                <div className="green mono font-bold">{val(audio.level, '---')}dB</div>
              </div>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">Buffer</div>
                <div className="green mono font-bold">{val(audio.buffer, '---')}</div>
              </div>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">Latencia</div>
                <div className="green mono font-bold">{val(audio.latency_ms, '---')}ms</div>
              </div>
            </div>
            <div className="gauge mt-3">
              <div className={`gauge-fill${audio.clipping ? ' error' : ''}`} style={{ width: `${Math.min(100, Math.max(0, (audio.level_pct || 0)))}%` }} />
            </div>
          </div>

          {/* — Red Local (from status_dashboard) — */}
          <div className="g">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold">Red Local</h3>
              <LED color={ledColor(s.network?.ip != null)} />
            </div>
            <div className="inset mb-2">
              <div className="flex justify-between">
                <span className="t3 text-sm">IP Local</span>
                <span className="mono text-sm">{val(s.network?.ip)}</span>
              </div>
            </div>
            <div className="inset mb-2">
              <div className="flex justify-between">
                <span className="t3 text-sm">Interfaz</span>
                <span className="mono text-sm">{val(s.network?.interface)}</span>
              </div>
            </div>
            <div className="inset">
              <div className="flex justify-between">
                <span className="t3 text-sm">MAC</span>
                <span className="mono text-sm">{val(s.network?.mac)}</span>
              </div>
            </div>
          </div>

          {/* — Clip de Audio (from status_dashboard) — */}
          <div className="g">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold">Clip de Audio</h3>
              <LED color={audio.clipping ? 'red' : 'green'} />
            </div>
            <div className="inset mb-2">
              <div className="flex justify-between">
                <span className="t3 text-sm">Estado</span>
                <span className={`text-sm ${audio.clipping ? 'red' : 'green'}`}>
                  {audio.clipping ? 'CLIPPING' : 'Normal'}
                </span>
              </div>
            </div>
            <div className="inset mb-2">
              <div className="flex justify-between">
                <span className="t3 text-sm">Pico Actual</span>
                <span className="mono text-sm">{val(audio.peak, '---')} dB</span>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginTop: '20px' }}>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">Canal L</div>
                <div className="green mono font-bold">{val(audio.clip_l, '---')}dB</div>
              </div>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">Canal R</div>
                <div className="green mono font-bold">{val(audio.clip_r, '---')}dB</div>
              </div>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">Headroom</div>
                <div className="green mono font-bold">{val(audio.headroom, '---')}dB</div>
              </div>
            </div>
          </div>

          {/* — Transport — */}
          <div className="g">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold">Transport</h3>
              <div className="b">{val(s.transport?.protocol, 'HTTP')}</div>
            </div>
            <div className="inset mb-3">
              <div className="flex justify-between mb-2">
                <span className="t3 text-sm">Mode</span>
                <span className="mono text-sm">{val(s.transport?.mode)}</span>
              </div>
              <div className="flex justify-between">
                <span className="t3 text-sm">Timeout</span>
                <span className="mono text-sm">{val(s.transport?.timeout, '---')}ms</span>
              </div>
            </div>
          </div>

          {/* — Next Block — */}
          <div className="g">
            <h3 className="font-bold mb-3">Next Block</h3>
            <div className="inset mb-3">
              <div className="cyan text-xl font-bold mono mb-2">
                {val(cal.next_time, cal.time_remaining_s != null ? formatUptime(cal.time_remaining_s) : '---')}
              </div>
              <div className="t3 text-sm">{val(cal.next_mode)}</div>
            </div>
            <div className="gauge">
              <div className="gauge-fill" style={{ width: `${Math.min(100, Math.max(0, (cal.progress || 0) * 100))}%` }} />
            </div>
          </div>

          {/* — Modules — */}
          <div className="g">
            <h3 className="font-bold mb-3">Modules</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {[
                { key: 'bajada', label: 'Bajada' },
                { key: 'base_golpe', label: 'Base Golpe' },
                { key: 'ataque', label: 'Ataque' },
                { key: 'brake', label: 'Brake' },
              ].map(mod => {
                const active = s.state === mod.key.toUpperCase() || (s.permissions || {})[mod.key];
                return (
                  <div key={mod.key} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`led-dot${active ? '' : ' off'}`} />
                      <span className={`text-sm${active ? '' : ' opacity-50'}`}>{mod.label}</span>
                    </div>
                    <span className={`b${active ? '' : ' gray'}`}>{active ? 'ON' : 'OFF'}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* — Current State — */}
          <div className="g">
            <h3 className="font-bold mb-3">Current State</h3>
            <div className="inset mb-3" style={{ textAlign: 'center' }}>
              <div className="green" style={{ fontSize: '28px', fontWeight: 700, fontFamily: 'var(--font-title)' }}>
                {val(s.state)}
              </div>
              <div className="t3 text-sm mt-2">Energy: {val(s.energy)}</div>
            </div>
          </div>

          {/* — Last Cue — */}
          <div className="g">
            <h3 className="font-bold mb-3">Last Cue</h3>
            <div className="inset mb-3" style={{ textAlign: 'center' }}>
              <div className="cyan" style={{ fontSize: '28px', fontWeight: 700, fontFamily: 'var(--font-title)' }}>
                {val(s.last_cue)}
              </div>
              <div className="t3 text-sm mt-2">Último cue disparado</div>
            </div>
          </div>

          {/* — Vision Pro — Cámaras (full width, from status_dashboard) — */}
          <div className="g" style={{ gridColumn: '1 / -1' }}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold">Vision Pro - Cámaras</h3>
              <LED color={ledColor(s.vision?.online)} />
            </div>
            <div className="inset mb-3">
              <div className="flex justify-between">
                <span className="t3 text-sm">Cámaras Activas</span>
                <span className="green mono">{val(s.vision?.cameras_active, '0')} / 3</span>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
              {(s.vision?.cameras || []).length > 0
                ? (s.vision.cameras).map(cam => (
                  <div key={cam.name} className="inset">
                    <div className="flex items-center justify-between mb-2">
                      <div className="font-bold">{(cam.name || '').toUpperCase()}</div>
                      <div className={`b${cam.online ? '' : ' gray'}`}>
                        {cam.online ? 'OK' : 'OFF'}
                      </div>
                    </div>
                    <div className="t3 mono text-sm">
                      {cam.online ? `${cam.fps || '---'} fps` : 'No disponible'}
                    </div>
                  </div>
                ))
                : <div className="inset t3 text-sm">Sin cámaras detectadas</div>
              }
            </div>
          </div>

        </div>
      </div>
    </>
  );
}
