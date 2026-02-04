/**
 * Calendar V7 - Control Room Calendar (NEON UI)
 *
 * 3 Tabs:
 * - ESTADO: Timeline + acciones activas + permisos
 * - HORARIOS: Editor semanal (7 columnas, cards por día)
 * - CONTROL: GO / +5/+10/+15 / override
 *
 * SAVE: Verde si hay cambios, Gris si sincronizado
 * Estilo: NEON (glow + cards con bordes iluminados)
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
function TabEstado({ status, apiOffline, onAuto }) {
  if (apiOffline) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }}>
        <span className="neon-badge neon-badge-error">CORE OFFLINE</span>
        <p style={{ color: 'var(--text-dim)', marginTop: '12px', fontSize: '12px' }}>
          No se puede conectar al CORE
        </p>
      </div>
    );
  }

  if (!status) return <div style={{ padding: '20px', color: 'var(--text-dim)' }}>Cargando...</div>;

  const modeColor = MODE_COLORS[status.current_mode] || '#7f8c8d';
  const isAuto = status.auto !== false;

  return (
    <div style={{ padding: '16px' }}>
      {/* Modo actual */}
      <div className="neon-panel" style={{ marginBottom: '16px' }}>
        <div className="neon-panel-header">
          <span className="neon-panel-title">MODO ACTUAL</span>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            {status.override_active && <span className="neon-badge neon-badge-warn">OVERRIDE</span>}
            <button
              onClick={() => onAuto(!isAuto)}
              className={`neon-btn ${isAuto ? 'neon-btn-primary' : 'neon-btn-warning'}`}
              style={{ padding: '4px 10px', fontSize: '10px' }}
            >
              {isAuto ? 'AUTO' : 'MANUAL'}
            </button>
          </div>
        </div>
        <div className="neon-panel-content">
          <div style={{
            textAlign: 'center',
            padding: '20px',
            background: 'var(--bg-dark)',
            borderRadius: '6px',
            border: `1px solid ${modeColor}40`,
          }}>
            <span style={{
              color: modeColor,
              fontSize: '28px',
              fontWeight: 'bold',
              textShadow: `0 0 20px ${modeColor}`,
            }}>
              {status.current_mode}
            </span>
          </div>
        </div>
      </div>

      {/* Timeline */}
      <div className="neon-panel" style={{ marginBottom: '16px' }}>
        <div className="neon-panel-header">
          <span className="neon-panel-title">TIMELINE</span>
          <span className="neon-badge neon-badge-ok">ACTIVO</span>
        </div>
        <div className="neon-panel-content">
          <div className="neon-progress" style={{ height: '16px', marginBottom: '12px' }}>
            <div
              className="neon-progress-bar"
              style={{
                width: `${Math.min(100, Math.max(5, (status.progress || 0) * 100))}%`,
                background: modeColor,
              }}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
            <span style={{ color: 'var(--text-dim)' }}>
              Progreso: {Math.round((status.progress || 0) * 100)}%
            </span>
            {status.next_mode && (
              <span style={{ color: 'var(--text-dim)' }}>
                Próximo: <strong style={{ color: 'var(--neon-green)' }}>{status.next_mode}</strong>
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Módulos */}
      <div className="neon-panel">
        <div className="neon-panel-header">
          <span className="neon-panel-title">MÓDULOS</span>
        </div>
        <div className="neon-panel-content">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {['audio_engine', 'vision_haze', 'vision_dj', 'cues_clima'].map(mod => {
              const active = status.permissions?.[mod] || false;
              return (
                <div key={mod} className={`neon-card ${active ? 'active' : ''}`} style={{ padding: '8px 12px' }}>
                  <div style={{ fontSize: '9px', fontWeight: 'bold', color: active ? 'var(--neon-green)' : 'var(--text-dim)' }}>
                    {mod.toUpperCase().replace('_', ' ')}
                  </div>
                  <div style={{ fontSize: '8px', color: active ? 'var(--neon-green)' : 'var(--text-muted)' }}>
                    {active ? 'ON' : 'OFF'}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
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
    <div style={{ padding: '16px' }}>
      {/* Header + Save */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <span style={{ color: 'var(--neon-cyan)', fontSize: '14px', fontWeight: 'bold' }}>
          EDITOR DE HORARIOS
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {hasChanges && (
            <span className="neon-badge neon-badge-warn">CAMBIOS SIN GUARDAR</span>
          )}
          <button
            onClick={onSave}
            disabled={!hasChanges || apiOffline}
            className={`neon-btn ${hasChanges && !apiOffline ? 'neon-btn-primary' : ''}`}
            style={{ opacity: hasChanges && !apiOffline ? 1 : 0.5 }}
          >
            GUARDAR
          </button>
        </div>
      </div>

      {/* API Offline warning */}
      {apiOffline && (
        <div style={{
          background: 'rgba(255, 68, 68, 0.1)',
          border: '1px solid var(--neon-red)',
          borderRadius: '6px',
          padding: '10px',
          marginBottom: '16px',
          textAlign: 'center',
        }}>
          <span style={{ color: 'var(--neon-red)', fontSize: '11px' }}>API OFFLINE - Edición deshabilitada</span>
        </div>
      )}

      {/* Grid 7 días */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gap: '8px',
        overflowX: 'auto',
      }}>
        {DAY_ORDER.map(day => (
          <div key={`${day}-${gridRev}`} className="neon-panel" style={{ minWidth: '140px' }}>
            <div className="neon-panel-header" style={{ justifyContent: 'center' }}>
              <span className="neon-panel-title">{DAY_NAMES[day]}</span>
            </div>
            <div style={{ padding: '8px', maxHeight: '400px', overflowY: 'auto' }}>
              {(week[day] || []).map((block, idx) => (
                <div key={idx} className="neon-card" style={{
                  marginBottom: '8px',
                  borderColor: `${MODE_COLORS[block.mode] || '#7f8c8d'}60`,
                }}>
                  {/* Tiempos */}
                  <div style={{ display: 'flex', gap: '4px', marginBottom: '6px', alignItems: 'center' }}>
                    <input
                      type="time"
                      value={block.from}
                      onChange={(e) => updateBlock(day, idx, 'from', e.target.value)}
                      className="neon-input"
                      style={{ width: '55px', padding: '4px', fontSize: '10px' }}
                    />
                    <span style={{ color: 'var(--text-dim)', fontSize: '10px' }}>-</span>
                    <input
                      type="time"
                      value={block.to}
                      onChange={(e) => updateBlock(day, idx, 'to', e.target.value)}
                      className="neon-input"
                      style={{ width: '55px', padding: '4px', fontSize: '10px' }}
                    />
                    <button
                      onClick={() => deleteBlock(day, idx)}
                      className="neon-btn neon-btn-danger"
                      style={{ padding: '2px 6px', fontSize: '9px', marginLeft: 'auto' }}
                    >✕</button>
                  </div>

                  {/* Modo */}
                  <select
                    value={block.mode}
                    onChange={(e) => updateBlock(day, idx, 'mode', e.target.value)}
                    className="neon-select"
                    style={{ width: '100%', padding: '4px', fontSize: '9px', marginBottom: '6px' }}
                  >
                    {CANONICAL_MODES.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>

                  {/* Extras */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                    {EXTRA_ACTIONS.map(action => {
                      const active = (block.actions || []).includes(action);
                      return (
                        <button
                          key={action}
                          onClick={() => toggleAction(day, idx, action)}
                          className={`neon-btn ${active ? '' : ''}`}
                          style={{
                            padding: '2px 6px',
                            fontSize: '8px',
                            background: active ? 'var(--neon-blue)' : 'transparent',
                            borderColor: active ? 'var(--neon-blue)' : 'var(--border-dim)',
                            color: active ? 'var(--bg-dark)' : 'var(--text-dim)',
                          }}
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
                className="neon-btn neon-btn-primary"
                style={{ width: '100%', fontSize: '10px' }}
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
    <div style={{ padding: '16px' }}>
      {/* API Offline */}
      {apiOffline && (
        <div style={{
          background: 'rgba(255, 68, 68, 0.1)',
          border: '1px solid var(--neon-red)',
          borderRadius: '6px',
          padding: '10px',
          marginBottom: '16px',
          textAlign: 'center',
        }}>
          <span style={{ color: 'var(--neon-red)', fontSize: '11px' }}>API OFFLINE - Controles deshabilitados</span>
        </div>
      )}

      {/* GO */}
      <div className="neon-panel" style={{ marginBottom: '16px' }}>
        <div className="neon-panel-header">
          <span className="neon-panel-title">GO - CAMBIAR MODO</span>
        </div>
        <div className="neon-panel-content">
          <select
            value={selectedMode}
            onChange={(e) => setSelectedMode(e.target.value)}
            className="neon-select"
            style={{ width: '100%', marginBottom: '12px' }}
          >
            {CANONICAL_MODES.map(m => <option key={m} value={m}>{m}</option>)}
          </select>

          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button
              onClick={() => onGo(selectedMode, 0)}
              disabled={apiOffline}
              className="neon-btn neon-btn-primary"
            >GO AHORA</button>
            <button onClick={() => onGo(selectedMode, 5)} disabled={apiOffline} className="neon-btn">+5 min</button>
            <button onClick={() => onGo(selectedMode, 10)} disabled={apiOffline} className="neon-btn">+10 min</button>
            <button onClick={() => onGo(selectedMode, 15)} disabled={apiOffline} className="neon-btn">+15 min</button>
          </div>

          {status?.pending_go && (
            <div style={{
              marginTop: '12px',
              padding: '8px',
              background: 'rgba(0, 255, 255, 0.1)',
              border: '1px solid var(--neon-cyan)',
              borderRadius: '4px',
            }}>
              <span style={{ color: 'var(--neon-cyan)', fontSize: '10px', fontWeight: 'bold' }}>
                GO PENDIENTE: {status.pending_go.mode} en {formatTime(status.pending_go.seconds_until)}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Extend */}
      <div className="neon-panel" style={{ marginBottom: '16px' }}>
        <div className="neon-panel-header">
          <span className="neon-panel-title">EXTENDER BLOQUE</span>
        </div>
        <div className="neon-panel-content">
          <div style={{ display: 'flex', gap: '8px' }}>
            <button onClick={() => onExtend(5)} disabled={apiOffline} className="neon-btn">+5 min</button>
            <button onClick={() => onExtend(10)} disabled={apiOffline} className="neon-btn">+10 min</button>
            <button onClick={() => onExtend(15)} disabled={apiOffline} className="neon-btn">+15 min</button>
          </div>
        </div>
      </div>

      {/* Override */}
      <div className="neon-panel" style={{ borderColor: 'var(--neon-orange)' }}>
        <div className="neon-panel-header">
          <span className="neon-panel-title" style={{ color: 'var(--neon-orange)' }}>OVERRIDE TEMPORAL</span>
        </div>
        <div className="neon-panel-content">
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ color: 'var(--text-dim)', fontSize: '10px' }}>Duración:</span>
            <input
              type="number"
              min="5"
              max="120"
              value={overrideDuration}
              onChange={(e) => setOverrideDuration(parseInt(e.target.value) || 30)}
              className="neon-input"
              style={{ width: '60px' }}
            />
            <span style={{ color: 'var(--text-dim)', fontSize: '10px' }}>min</span>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => onOverride(selectedMode, overrideDuration)}
              disabled={apiOffline}
              className="neon-btn neon-btn-warning"
            >ACTIVAR OVERRIDE</button>
            {status?.override?.active && (
              <button
                onClick={onClearOverride}
                disabled={apiOffline}
                className="neon-btn neon-btn-danger"
              >LIMPIAR</button>
            )}
          </div>

          {status?.override?.active && (
            <div style={{
              marginTop: '12px',
              padding: '8px',
              background: 'rgba(255, 136, 0, 0.1)',
              border: '1px solid var(--neon-orange)',
              borderRadius: '4px',
            }}>
              <span style={{ color: 'var(--neon-orange)', fontSize: '10px', fontWeight: 'bold' }}>
                OVERRIDE: {status.override.mode} ({formatTime(status.override.remaining_seconds)} restantes)
              </span>
            </div>
          )}
        </div>
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
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Error Banner */}
      {lastError && (
        <div style={{
          background: 'rgba(255, 68, 68, 0.15)',
          borderBottom: '1px solid var(--neon-red)',
          padding: '8px 16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <span style={{ color: 'var(--neon-red)', fontSize: '11px', fontWeight: 'bold' }}>
            ERROR: {lastError}
          </span>
          <button
            onClick={() => setLastError(null)}
            style={{ background: 'none', border: 'none', color: 'var(--neon-red)', cursor: 'pointer' }}
          >✕</button>
        </div>
      )}

      {/* Success Banner */}
      {saveSuccess && (
        <div style={{
          background: 'rgba(0, 255, 136, 0.15)',
          borderBottom: '1px solid var(--neon-green)',
          padding: '8px 16px',
        }}>
          <span style={{ color: 'var(--neon-green)', fontSize: '11px', fontWeight: 'bold' }}>
            ✓ Guardado OK
          </span>
        </div>
      )}

      {/* Warnings Banner */}
      {warnings.length > 0 && (
        <div style={{
          background: 'rgba(255, 200, 0, 0.15)',
          borderBottom: '1px solid var(--neon-orange)',
          padding: '8px 16px',
        }}>
          <div style={{ color: 'var(--neon-orange)', fontSize: '11px', fontWeight: 'bold', marginBottom: '4px' }}>
            ⚠ SOLAPAMIENTOS DETECTADOS:
          </div>
          {warnings.map((w, i) => (
            <div key={i} style={{ color: 'var(--neon-orange)', fontSize: '10px', marginLeft: '12px' }}>
              • {w}
            </div>
          ))}
          <button
            onClick={() => setWarnings([])}
            style={{ background: 'none', border: 'none', color: 'var(--neon-orange)', cursor: 'pointer', marginTop: '4px', fontSize: '10px' }}
          >Cerrar</button>
        </div>
      )}

      {/* Tabs */}
      <div className="neon-tabs">
        {[
          { key: 'estado', label: 'ESTADO' },
          { key: 'horarios', label: 'HORARIOS' },
          { key: 'control', label: 'CONTROL' },
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`neon-tab ${activeTab === tab.key ? 'active' : ''}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', background: 'var(--bg-dark)' }}>
        {activeTab === 'estado' && <TabEstado status={status} apiOffline={apiOffline} onAuto={handleAuto} />}
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
