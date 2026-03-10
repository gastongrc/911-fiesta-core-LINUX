/**
 * Analyze — System Monitor (Engine Health)
 *
 * Simplified view showing engine health status.
 * Reads from /api/v1/status/unified (CORE snapshot).
 * Does NOT expose internal analyzer logic.
 *
 * Uses glass design system (control-room.css)
 */
import { useEffect, useState, useRef, useCallback } from 'react';
import { getApiBase } from '../lib/apiBase';

function val(v, fallback = '---') {
  return v != null && v !== '' ? v : fallback;
}

function formatUptime(s) {
  if (s == null || s < 0) return '---';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function LED({ color }) {
  const cls = color === 'off' ? 'led off'
    : color === 'yellow' ? 'led yellow'
    : color === 'red' ? 'led red'
    : 'led';
  return <div className={cls} />;
}

function ledColor(online) {
  if (online === true) return 'green';
  if (online === false) return 'red';
  return 'off';
}

export function Analyze() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const pollingRef = useRef(null);

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`${getApiBase()}/status/unified`);
        if (res.ok) {
          setStatus(await res.json());
          setError(null);
        } else {
          setError(`HTTP ${res.status}`);
        }
      } catch (e) {
        setError('API offline');
      }
    };
    poll();
    pollingRef.current = setInterval(poll, 2000);
    return () => clearInterval(pollingRef.current);
  }, []);

  const s = status || {};
  const sys = s.system || {};
  const audio = s.audio || {};
  const avo = s.avolites || {};
  const vision = s.vision || {};
  const core = s.core || {};

  if (!status && !error) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '16px' }}>
        <div className="led" />
        <p className="t3 text-sm">Conectando al sistema...</p>
      </div>
    );
  }

  return (
    <>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1 style={{ fontFamily: 'var(--font-title)', fontSize: '24px', fontWeight: 700 }}>System Monitor</h1>
          <div className="b gray">Health</div>
        </div>
        <div className="b">
          <div className={`led-dot${!error ? '' : ' off'}`} />
          {!error ? 'LIVE' : 'OFF'}
        </div>
      </div>

      {error && (
        <div className="flex items-center justify-between p-3" style={{ background: 'rgba(255,82,82,0.1)', borderBottom: '1px solid var(--red)' }}>
          <span className="red font-bold text-sm">API OFFLINE — {error}</span>
        </div>
      )}

      <div style={{ flex: 1, padding: '0 28px 28px', overflowY: 'auto' }}>

        {/* Engine Health Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>

          {/* CORE Engine */}
          <div className="g">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold">CORE Engine</h3>
              <LED color={ledColor(core.online !== false)} />
            </div>
            <div className="inset mb-2">
              <div className="flex justify-between mb-2">
                <span className="t3 text-sm">Estado</span>
                <span className={`text-sm ${core.online !== false ? 'green' : 'red'}`}>
                  {core.online !== false ? 'ONLINE' : 'OFFLINE'}
                </span>
              </div>
              {core.last_error && (
                <div className="flex justify-between">
                  <span className="t3 text-sm">Último Error</span>
                  <span className="red mono text-sm">{core.last_error}</span>
                </div>
              )}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginTop: '20px' }}>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">CPU</div>
                <div className="green mono font-bold">{val(sys.cpu, '0')}%</div>
              </div>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">RAM</div>
                <div className="cyan mono font-bold">{val(sys.ram, '0')}%</div>
              </div>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm">Uptime</div>
                <div className="t1 mono font-bold">{formatUptime(sys.uptime_s)}</div>
              </div>
            </div>
          </div>

          {/* Audio Engine */}
          <div className="g">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold">Audio Engine</h3>
              <LED color={audio.device ? (audio.clipping ? 'red' : audio.silence ? 'yellow' : 'green') : 'off'} />
            </div>
            <div className="inset mb-2">
              <div className="flex justify-between mb-2">
                <span className="t3 text-sm">Estado</span>
                <span className={`text-sm ${audio.device ? 'green' : 'red'}`}>
                  {audio.device ? 'ONLINE' : 'OFFLINE'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="t3 text-sm">Dispositivo</span>
                <span className="mono text-sm">{val(audio.device)}</span>
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
          </div>

          {/* Avolites / Consola */}
          <div className="g">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold">Consola Avolites</h3>
              <LED color={ledColor(avo.connected)} />
            </div>
            <div className="inset mb-2">
              <div className="flex justify-between mb-2">
                <span className="t3 text-sm">Estado</span>
                <span className={`text-sm ${avo.connected ? 'green' : 'red'}`}>
                  {avo.connected ? 'ONLINE' : 'OFFLINE'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="t3 text-sm">IP Consola</span>
                <span className="mono text-sm">{val(avo.console_ip)}</span>
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
          </div>

          {/* Vision System */}
          <div className="g">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold">Vision System</h3>
              <LED color={ledColor(vision.online)} />
            </div>
            <div className="inset mb-2">
              <div className="flex justify-between mb-2">
                <span className="t3 text-sm">Estado</span>
                <span className={`text-sm ${vision.online ? 'green' : 'red'}`}>
                  {vision.online ? 'ONLINE' : 'OFFLINE'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="t3 text-sm">Cámaras Activas</span>
                <span className="green mono text-sm">{val(vision.cameras_active, '0')}</span>
              </div>
            </div>
            {(vision.cameras || []).length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: '12px', marginTop: '20px' }}>
                {(vision.cameras || []).map(cam => (
                  <div key={cam.name} className="inset" style={{ textAlign: 'center' }}>
                    <div className="t4 text-sm">{cam.name}</div>
                    <div className={`mono font-bold ${cam.online ? 'green' : 'red'}`}>
                      {cam.online ? `${cam.fps || '---'} fps` : 'OFF'}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Current State — full width */}
          <div className="g" style={{ gridColumn: '1 / -1' }}>
            <h3 className="font-bold mb-3">Estado del Sistema</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px' }}>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm mb-2">State</div>
                <div className="green" style={{ fontSize: '22px', fontWeight: 700 }}>{val(s.state)}</div>
              </div>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm mb-2">Energy</div>
                <div className="cyan" style={{ fontSize: '22px', fontWeight: 700 }}>{val(s.energy)}</div>
              </div>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm mb-2">BPM</div>
                <div className="green" style={{ fontSize: '22px', fontWeight: 700 }}>{val(s.bpm)}</div>
              </div>
              <div className="inset" style={{ textAlign: 'center' }}>
                <div className="t4 text-sm mb-2">Timestamp</div>
                <div className="t1 mono" style={{ fontSize: '14px' }}>{s.ts ? new Date(s.ts * 1000).toLocaleTimeString('es-AR') : '---'}</div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </>
  );
}
