/**
 * Calendar V7 - Control Room Calendar (Glass UI)
 *
 * 3 Tabs:
 * - ESTADO: Clock + mode + modules + day-strip grid
 * - HORARIOS: Editor semanal (7 columnas, cards por día)
 * - CONTROL: GO / +5/+10/+15 / override
 *
 * SAVE: Green badge if changes, gray if synced
 * Style: Glass morphism via control-room.css
 */
import { useEffect, useState } from 'react';
import { getApiBase, apiPost } from '../lib/apiBase';

// Colores por modo
const MODE_COLORS = {
  clima_1: '#1abc9c', clima_2: '#16a085', clima_3: '#2ecc71', clima_4: '#27ae60',
  teatro: '#3498db', artista: '#9b59b6',
  boliche_inicio: '#f39c12', boliche_desarrollo: '#e67e22', boliche_fin: '#e74c3c',
  apagado: '#7f8c8d',
};

const CANONICAL_MODES = [
  'clima_1', 'clima_2', 'clima_3', 'clima_4',
  'boliche_inicio', 'boliche_desarrollo', 'boliche_fin', 'apagado'
];

const EXTRA_ACTIONS = ['vision_haze', 'vision_dj', 'vision_artista'];
const EXTRA_DISPLAY = { vision_haze: 'Haze', vision_dj: 'DJ', vision_artista: 'Artista' };

const DAY_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const DAY_NAMES = {
  monday: 'LUN', tuesday: 'MAR', wednesday: 'MIÉ',
  thursday: 'JUE', friday: 'VIE', saturday: 'SÁB', sunday: 'DOM'
};

// Formatea segundos
function formatTime(s) {
  if (s == null || s < 0) return '---';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

// ==================== TAB ESTADO ====================
function TabEstado({ status, schedule, apiOffline, onAuto }) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const tick = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(tick);
  }, []);

  if (apiOffline) {
    return (
      <div className="p-4" style={{ textAlign: 'center' }}>
        <span className="b red">CORE OFFLINE</span>
        <p className="t3 text-sm mt-3">No se puede conectar al CORE</p>
      </div>
    );
  }

  if (!status) return <div className="p-4 t3">Cargando...</div>;

  const isAuto = status.auto !== false;
  const week = schedule?.week || {};

  // Compute current week dates (Monday=0)
  const todayIdx = (now.getDay() + 6) % 7;
  const monday = new Date(now);
  monday.setDate(now.getDate() - todayIdx);

  return (
    <div style={{ flex: 1, padding: '0 28px 28px' }}>
      {/* Top row: Clock + Mode/Next + Modules */}
      <div style={{ display: 'flex', gap: '14px', marginBottom: '20px' }}>
        {/* Clock */}
        <div className="g" style={{ flex: '0 0 280px' }}>
          <div className="green" style={{ fontFamily: 'var(--font-title)', fontSize: '48px', fontWeight: 800 }}>
            {now.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </div>
          <div className="t2 text-sm mt-2">
            {now.toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long' })}
          </div>
        </div>

        {/* Mode + Next Block */}
        <div className="g" style={{ flex: 1 }}>
          <div style={{ display: 'flex', gap: '20px' }}>
            <div style={{ flex: 1 }}>
              <div className="t4 text-sm mb-2">MODE</div>
              <div className="cyan" style={{ fontSize: '22px', fontWeight: 700 }}>
                {status.current_mode || '---'}
              </div>
              <div className="flex items-center gap-2 mt-3">
                <button
                  onClick={() => onAuto(!isAuto)}
                  className={isAuto ? 'key' : 'key-danger'}
                  style={{ padding: '6px 14px', fontSize: '11px' }}
                >
                  {isAuto ? 'AUTO' : 'MANUAL'}
                </button>
                {status.override_active && <span className="b yellow">OVERRIDE</span>}
              </div>
            </div>
            <div style={{ width: '1px', background: 'rgba(255,255,255,0.06)' }} />
            <div style={{ flex: 1 }}>
              <div className="t4 text-sm mb-2">NEXT BLOCK</div>
              <div className="green" style={{ fontSize: '22px', fontWeight: 700 }}>
                {status.next_mode || '---'}
              </div>
              {status.progress != null && (
                <div className="mt-3">
                  <div className="gauge">
                    <div
                      className="gauge-fill"
                      style={{ width: `${Math.min(100, Math.max(5, (status.progress || 0) * 100))}%` }}
                    />
                  </div>
                  <div className="t3 text-sm mt-2">
                    {Math.round((status.progress || 0) * 100)}%
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Modules */}
        <div className="gp" style={{ flex: '0 0 200px' }}>
          <div className="t3 text-sm mb-3">MODULES</div>
          {['audio_engine', 'vision_haze', 'vision_dj', 'cues_clima'].map(mod => {
            const active = status.permissions?.[mod] || false;
            return (
              <div key={mod} className="flex items-center gap-2" style={{ padding: '5px 0' }}>
                <div className={`led-dot${active ? '' : ' off'}`} />
                <span className={`text-sm t2${active ? '' : ' opacity-50'}`}>
                  {mod.replace(/_/g, ' ')}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Day strip grid */}
      <div style={{ display: 'flex', gap: 0, height: '600px' }}>
        {DAY_ORDER.map((day, i) => {
          const date = new Date(monday);
          date.setDate(monday.getDate() + i);
          const isToday = i === todayIdx;
          const blockCount = (week[day] || []).length;

          return (
            <div
              key={day}
              className={`day-strip${isToday ? ' today' : ''}`}
              style={i === DAY_ORDER.length - 1 ? { borderRight: 'none' } : undefined}
            >
              <div style={{ padding: '16px', textAlign: 'center', position: 'relative', zIndex: 1 }}>
                <div
                  className={isToday ? 'green' : 't3'}
                  style={{ fontFamily: 'var(--font-title)', fontSize: '13px', fontWeight: 700 }}
                >
                  {DAY_NAMES[day]}
                </div>
                <div
                  className={isToday ? 'green' : 't4'}
                  style={{ fontFamily: 'var(--font-title)', fontSize: '28px', fontWeight: 800, marginTop: '4px' }}
                >
                  {date.getDate()}
                </div>
                <div className={`b${blockCount === 0 ? ' gray' : ''}`} style={{ marginTop: '6px', fontSize: '9px' }}>
                  {blockCount}
                </div>
                {isToday && <div className="led-dot" style={{ margin: '8px auto 0' }} />}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ==================== TAB HORARIOS ====================
function TabHorarios({ schedule, setSchedule, hasChanges, setHasChanges, onSave, apiOffline, gridRev }) {
  const week = schedule?.week || {};

  const addBlock = (day) => {
    const newBlock = { from: '20:00', to: '22:00', mode: 'clima_1', actions: [] };
    const dayBlocks = [...(week[day] || []), newBlock];
    setSchedule({ week: { ...week, [day]: dayBlocks } });
    setHasChanges(true);
  };

  const updateBlock = (day, idx, field, value) => {
    const dayBlocks = [...(week[day] || [])];
    dayBlocks[idx] = { ...dayBlocks[idx], [field]: value };
    setSchedule({ week: { ...week, [day]: dayBlocks } });
    setHasChanges(true);
  };

  const deleteBlock = (day, idx) => {
    const dayBlocks = [...(week[day] || [])];
    dayBlocks.splice(idx, 1);
    setSchedule({ week: { ...week, [day]: dayBlocks } });
    setHasChanges(true);
  };

  const toggleAction = (day, idx, action) => {
    const dayBlocks = [...(week[day] || [])];
    const block = { ...dayBlocks[idx] };
    const actions = new Set(block.actions || []);
    if (actions.has(action)) {
      actions.delete(action);
    } else {
      if (action === 'vision_dj') actions.delete('vision_artista');
      if (action === 'vision_artista') actions.delete('vision_dj');
      actions.add(action);
    }
    block.actions = Array.from(actions);
    dayBlocks[idx] = block;
    setSchedule({ week: { ...week, [day]: dayBlocks } });
    setHasChanges(true);
  };

  return (
    <div style={{ padding: '16px 28px' }}>
      {/* Header + Save */}
      <div className="flex justify-between items-center mb-4">
        <span className="cyan font-bold text-base">EDITOR DE HORARIOS</span>
        <div className="flex items-center gap-3">
          {hasChanges && <span className="b yellow">CAMBIOS SIN GUARDAR</span>}
          <button
            onClick={onSave}
            disabled={!hasChanges || apiOffline}
            className={hasChanges && !apiOffline ? 'key' : 'key-2'}
            style={{ padding: '8px 20px', fontSize: '12px' }}
          >
            GUARDAR
          </button>
        </div>
      </div>

      {/* API Offline warning */}
      {apiOffline && (
        <div className="gp mb-4" style={{ textAlign: 'center', borderColor: 'rgba(255,82,82,0.3)' }}>
          <span className="red text-sm">API OFFLINE - Edición deshabilitada</span>
        </div>
      )}

      {/* Grid 7 días */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '8px', overflowX: 'auto' }}>
        {DAY_ORDER.map(day => (
          <div key={`${day}-${gridRev}`} className="gp" style={{ minWidth: '140px' }}>
            <div className="t3 font-bold text-sm mb-3" style={{ textAlign: 'center', letterSpacing: '1px' }}>
              {DAY_NAMES[day]}
            </div>
            <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
              {(week[day] || []).map((block, idx) => (
                <div
                  key={idx}
                  className="inset mb-2"
                  style={{ borderColor: `${MODE_COLORS[block.mode] || '#7f8c8d'}60` }}
                >
                  {/* Tiempos */}
                  <div className="flex items-center gap-2 mb-2">
                    <input
                      type="time"
                      value={block.from}
                      onChange={(e) => updateBlock(day, idx, 'from', e.target.value)}
                      style={{ width: '55px', padding: '4px', fontSize: '10px' }}
                    />
                    <span className="t3 text-sm">-</span>
                    <input
                      type="time"
                      value={block.to}
                      onChange={(e) => updateBlock(day, idx, 'to', e.target.value)}
                      style={{ width: '55px', padding: '4px', fontSize: '10px' }}
                    />
                    <button
                      onClick={() => deleteBlock(day, idx)}
                      className="key-danger"
                      style={{ padding: '2px 6px', fontSize: '9px', marginLeft: 'auto' }}
                    >✕</button>
                  </div>

                  {/* Modo */}
                  <select
                    value={block.mode}
                    onChange={(e) => updateBlock(day, idx, 'mode', e.target.value)}
                    style={{ width: '100%', padding: '4px', fontSize: '9px', marginBottom: '6px' }}
                  >
                    {CANONICAL_MODES.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>

                  {/* Extras */}
                  <div className="flex" style={{ flexWrap: 'wrap', gap: '4px' }}>
                    {EXTRA_ACTIONS.map(action => {
                      const active = (block.actions || []).includes(action);
                      return (
                        <button
                          key={action}
                          onClick={() => toggleAction(day, idx, action)}
                          className={active ? 'key' : 'key-2'}
                          style={{ padding: '2px 6px', fontSize: '8px' }}
                        >
                          {EXTRA_DISPLAY[action]}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}

              {/* Agregar */}
              <button
                onClick={() => addBlock(day)}
                className="key w-full"
                style={{ fontSize: '10px', padding: '8px' }}
              >
                + Agregar
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ==================== TAB CONTROL ====================
function TabControl({ status, onGo, onExtend, onOverride, onClearOverride, apiOffline }) {
  const [selectedMode, setSelectedMode] = useState('clima_1');
  const [overrideDuration, setOverrideDuration] = useState(30);

  return (
    <div style={{ padding: '16px 28px' }}>
      {/* API Offline */}
      {apiOffline && (
        <div className="gp mb-4" style={{ textAlign: 'center', borderColor: 'rgba(255,82,82,0.3)' }}>
          <span className="red text-sm">API OFFLINE - Controles deshabilitados</span>
        </div>
      )}

      {/* GO */}
      <div className="g mb-4">
        <div className="t3 font-bold text-sm mb-3" style={{ letterSpacing: '1px' }}>GO — CAMBIAR MODO</div>
        <select
          value={selectedMode}
          onChange={(e) => setSelectedMode(e.target.value)}
          style={{ width: '100%', marginBottom: '12px' }}
        >
          {CANONICAL_MODES.map(m => <option key={m} value={m}>{m}</option>)}
        </select>

        <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
          <button onClick={() => onGo(selectedMode, 0)} disabled={apiOffline} className="key">GO AHORA</button>
          <button onClick={() => onGo(selectedMode, 5)} disabled={apiOffline} className="key-2">+5 min</button>
          <button onClick={() => onGo(selectedMode, 10)} disabled={apiOffline} className="key-2">+10 min</button>
          <button onClick={() => onGo(selectedMode, 15)} disabled={apiOffline} className="key-2">+15 min</button>
        </div>

        {status?.pending_go && (
          <div className="inset mt-3">
            <span className="cyan text-sm font-bold">
              GO PENDIENTE: {status.pending_go.mode} en {formatTime(status.pending_go.seconds_until)}
            </span>
          </div>
        )}
      </div>

      {/* Extend */}
      <div className="g mb-4">
        <div className="t3 font-bold text-sm mb-3" style={{ letterSpacing: '1px' }}>EXTENDER BLOQUE</div>
        <div className="flex gap-2">
          <button onClick={() => onExtend(5)} disabled={apiOffline} className="key-2">+5 min</button>
          <button onClick={() => onExtend(10)} disabled={apiOffline} className="key-2">+10 min</button>
          <button onClick={() => onExtend(15)} disabled={apiOffline} className="key-2">+15 min</button>
        </div>
      </div>

      {/* Override */}
      <div className="g" style={{ borderColor: 'rgba(255,152,0,0.3)' }}>
        <div className="yellow font-bold text-sm mb-3" style={{ letterSpacing: '1px' }}>OVERRIDE TEMPORAL</div>
        <div className="flex items-center gap-2 mb-3">
          <span className="t3 text-sm">Duración:</span>
          <input
            type="number"
            min="5"
            max="120"
            value={overrideDuration}
            onChange={(e) => setOverrideDuration(parseInt(e.target.value) || 30)}
            style={{ width: '60px' }}
          />
          <span className="t3 text-sm">min</span>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => onOverride(selectedMode, overrideDuration)}
            disabled={apiOffline}
            className="key-danger"
          >ACTIVAR OVERRIDE</button>
          {status?.override?.active && (
            <button
              onClick={onClearOverride}
              disabled={apiOffline}
              className="key-danger"
            >LIMPIAR</button>
          )}
        </div>

        {status?.override?.active && (
          <div className="inset mt-3" style={{ borderColor: 'rgba(255,152,0,0.3)' }}>
            <span className="yellow text-sm font-bold">
              OVERRIDE: {status.override.mode} ({formatTime(status.override.remaining_seconds)} restantes)
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ==================== PÁGINA PRINCIPAL ====================
export function Calendar() {
  const [activeTab, setActiveTab] = useState('estado');
  const [status, setStatus] = useState(null);
  const [schedule, setSchedule] = useState({ week: {} });
  const [hasChanges, setHasChanges] = useState(false);
  const [apiOffline, setApiOffline] = useState(false);
  const [lastError, setLastError] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [gridRev, setGridRev] = useState(0); // Force grid re-render after SAVE

  // Fetch week schedule (solo si no hay cambios pendientes)
  const fetchWeek = async (force = false) => {
    if (hasChanges && !force) return; // No pisar ediciones locales
    try {
      const res = await fetch(`${getApiBase()}/calendar/week`);
      if (res.ok) {
        const data = await res.json();
        if (data.error) {
          setLastError(data.error);
        } else {
          setSchedule({ week: data.week || {} });
        }
      }
    } catch (e) {
      // Silenciar errores de polling
    }
  };

  // Cargar status - polling 2s
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch(`${getApiBase()}/calendar/status`);
        if (res.ok) {
          const data = await res.json();
          setStatus(data);
          setApiOffline(!data.core_online);
        } else {
          setApiOffline(true);
        }
      } catch (e) {
        setApiOffline(true);
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  // Cargar schedule al montar
  useEffect(() => {
    fetchWeek(true);
  }, []);

  // Polling de week cada 5s SOLO si no hay cambios pendientes
  useEffect(() => {
    if (hasChanges) return; // No hacer polling si está editando
    const interval = setInterval(() => fetchWeek(), 5000);
    return () => clearInterval(interval);
  }, [hasChanges]);

  // Acciones - retornan success y refetch si OK
  const handleGo = async (mode, delay) => {
    try {
      const res = await apiPost('/calendar/go', { mode, delay_minutes: delay });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setLastError(null);
        } else {
          setLastError(data.error || 'GO_FAILED');
        }
      } else {
        setLastError('HTTP_ERROR');
      }
    } catch (e) {
      setLastError('GO_ERROR');
    }
  };

  const handleExtend = async (minutes) => {
    try {
      const res = await apiPost('/calendar/extend', { minutes });
      if (res.ok) {
        const data = await res.json();
        if (!data.success) setLastError(data.error || 'EXTEND_FAILED');
      }
    } catch (e) {
      setLastError('EXTEND_ERROR');
    }
  };

  const handleOverride = async (mode, duration) => {
    try {
      const res = await apiPost('/calendar/override', { mode, duration_minutes: duration });
      if (res.ok) {
        const data = await res.json();
        if (!data.success) setLastError(data.error || 'OVERRIDE_FAILED');
      }
    } catch (e) {
      setLastError('OVERRIDE_ERROR');
    }
  };

  const handleClearOverride = async () => {
    try {
      const res = await fetch(`${getApiBase()}/calendar/override/stop`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (!data.success) setLastError(data.error || 'STOP_FAILED');
      }
    } catch (e) {
      setLastError('STOP_ERROR');
    }
  };

  const handleAuto = async (enabled) => {
    try {
      const res = await fetch(`${getApiBase()}/calendar/auto?enabled=${enabled}`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (!data.success) setLastError(data.error || 'AUTO_FAILED');
      }
    } catch (e) {
      setLastError('AUTO_ERROR');
    }
  };

  const handleSave = async () => {
    setLastError(null);
    setWarnings([]);
    setSaveSuccess(false);
    try {
      const res = await apiPost('/calendar/save', { week: schedule.week });
      if (res.ok) {
        const data = await res.json();
        console.log('[SAVE] Response:', JSON.stringify(data, null, 2));

        if (data.success) {
          // Validar que week tenga contenido antes de pisar estado
          const weekKeys = Object.keys(data.week || {});
          console.log('[SAVE] week keys:', weekKeys);

          if (data.week && weekKeys.length > 0) {
            // Pisar estado local con week REAL del CORE
            setSchedule({ week: data.week });
            console.log('[SAVE] Estado actualizado con week del CORE');
          } else {
            // week vacío - refetch forzado para obtener datos reales
            console.warn('[SAVE] week vacío en respuesta, haciendo refetch...');
            await fetchWeek(true);
          }

          setHasChanges(false);
          setGridRev(r => r + 1); // Force grid repaint
          setSaveSuccess(true);

          // Mostrar warnings si hay (vienen del CORE)
          if (data.warnings && data.warnings.length > 0) {
            setWarnings(data.warnings);
          }
          // Ocultar banner de éxito después de 3s
          setTimeout(() => setSaveSuccess(false), 3000);
        } else {
          setLastError(data.error || 'SAVE_FAILED');
        }
      } else {
        setLastError('HTTP_ERROR');
      }
    } catch (e) {
      console.error('[SAVE] Error:', e);
      setLastError('SAVE_ERROR');
    }
  };

  return (
    <div className="calendar-contract" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Error Banner */}
      {lastError && (
        <div className="flex items-center justify-between p-3" style={{ background: 'rgba(255,82,82,0.1)', borderBottom: '1px solid var(--red)' }}>
          <span className="red font-bold text-sm">ERROR: {lastError}</span>
          <button
            onClick={() => setLastError(null)}
            className="key-2"
            style={{ padding: '4px 10px', fontSize: '11px' }}
          >✕</button>
        </div>
      )}

      {/* Success Banner */}
      {saveSuccess && (
        <div className="p-3" style={{ background: 'rgba(0,230,118,0.1)', borderBottom: '1px solid var(--green)' }}>
          <span className="green font-bold text-sm">Guardado OK</span>
        </div>
      )}

      {/* Warnings Banner */}
      {warnings.length > 0 && (
        <div className="p-3" style={{ background: 'rgba(255,152,0,0.1)', borderBottom: '1px solid var(--orange)' }}>
          <div className="yellow font-bold text-sm mb-2">SOLAPAMIENTOS DETECTADOS:</div>
          {warnings.map((w, i) => (
            <div key={i} className="yellow text-sm opacity-70" style={{ marginLeft: '12px' }}>• {w}</div>
          ))}
          <button
            onClick={() => setWarnings([])}
            className="key-2 mt-2"
            style={{ padding: '4px 10px', fontSize: '10px' }}
          >Cerrar</button>
        </div>
      )}

      {/* Page Header */}
      <div style={{ padding: '20px 28px' }}>
        <h1 style={{ fontFamily: 'var(--font-title)', fontSize: '24px', fontWeight: 700 }}>Calendar</h1>
      </div>

      {/* Sub Navigation (matches mock sub-nav) */}
      <div className="sub-nav">
        {[
          { key: 'estado', label: 'Estado' },
          { key: 'horarios', label: 'Semana' },
          { key: 'control', label: 'Control' },
        ].map(tab => (
          <div
            key={tab.key}
            className={`sub-tab${activeTab === tab.key ? ' on' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </div>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {activeTab === 'estado' && (
          <TabEstado
            status={status}
            schedule={schedule}
            apiOffline={apiOffline}
            onAuto={handleAuto}
          />
        )}
        {activeTab === 'horarios' && (
          <TabHorarios
            schedule={schedule}
            setSchedule={setSchedule}
            hasChanges={hasChanges}
            setHasChanges={setHasChanges}
            onSave={handleSave}
            apiOffline={apiOffline}
            gridRev={gridRev}
          />
        )}
        {activeTab === 'control' && (
          <TabControl
            status={status}
            onGo={handleGo}
            onExtend={handleExtend}
            onOverride={handleOverride}
            onClearOverride={handleClearOverride}
            apiOffline={apiOffline}
          />
        )}
      </div>
    </div>
  );
}
