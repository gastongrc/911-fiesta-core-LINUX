/**
 * Calendar V7 - Control Room Calendar (Estilo Viejo Industrial)
 *
 * 3 Tabs:
 * - ESTADO: Timeline + acciones activas + permisos derivados
 * - HORARIOS: Editor semanal (7 columnas, cards por día)
 * - CONTROL: GO / +5/+10/+15 / override
 *
 * SAVE: Verde si hay cambios, Gris si sincronizado
 * Estilo: Oscuro, denso, técnico (consola industrial)
 */
import { useEffect, useState } from 'react';

const API_BASE = '/api/v1';

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
  if (s < 0) return '---';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

// ==================== TAB ESTADO ====================
function TabEstado({ status }) {
  if (!status) return <div style={{ color: '#7f8c8d', padding: '20px' }}>Cargando...</div>;

  const modeColor = MODE_COLORS[status.current_mode] || '#7f8c8d';

  return (
    <div style={{ padding: '16px' }}>
      {/* Header: Modo actual */}
      <div style={{
        background: 'linear-gradient(to right, #2c3e50, #1a252f)',
        borderRadius: '8px',
        padding: '16px',
        marginBottom: '16px',
        border: '1px solid #34495e',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ color: '#7f8c8d', fontSize: '10px' }}>MODO ACTUAL</span>
            <div style={{ color: modeColor, fontSize: '24px', fontWeight: 'bold', marginTop: '4px' }}>
              {status.current_mode}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            {status.override?.active && (
              <span style={{
                color: '#e74c3c', fontSize: '10px', fontWeight: 'bold',
                background: 'rgba(231,76,60,0.2)', padding: '4px 8px', borderRadius: '4px',
              }}>OVERRIDE</span>
            )}
            <span style={{
              color: status.auto_mode_enabled ? '#2ecc71' : '#f39c12',
              fontSize: '10px', fontWeight: 'bold',
              background: status.auto_mode_enabled ? 'rgba(46,204,113,0.2)' : 'rgba(243,156,18,0.2)',
              padding: '4px 8px', borderRadius: '4px',
            }}>
              {status.auto_mode_enabled ? 'AUTO' : 'MANUAL'}
            </span>
          </div>
        </div>
      </div>

      {/* Timeline */}
      <div style={{
        background: '#1e272e', borderRadius: '8px', padding: '12px',
        marginBottom: '16px', border: '1px solid #34495e',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ color: '#7f8c8d', fontSize: '10px', fontWeight: 'bold' }}>TIMELINE</span>
          <span style={{ color: '#2ecc71', fontSize: '10px', fontWeight: 'bold' }}>ACTIVO</span>
        </div>
        <div style={{
          background: '#2c3e50', borderRadius: '6px', height: '16px',
          overflow: 'hidden', marginBottom: '8px',
        }}>
          <div style={{
            background: modeColor, height: '100%',
            width: `${Math.min(100, Math.max(5, (status.progress || 0) * 100))}%`,
            transition: 'width 0.3s', borderRadius: '6px',
          }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px' }}>
          <span style={{ color: '#7f8c8d' }}>Progreso: {Math.round((status.progress || 0) * 100)}%</span>
          {status.next_mode && (
            <span style={{ color: '#95a5a6' }}>
              Próximo: <strong style={{ color: '#ecf0f1' }}>{status.next_mode}</strong>
            </span>
          )}
        </div>
      </div>

      {/* Permisos / Módulos activos */}
      <div style={{
        background: '#1e272e', borderRadius: '8px', padding: '12px',
        border: '1px solid #34495e',
      }}>
        <div style={{ marginBottom: '12px' }}>
          <span style={{ color: '#7f8c8d', fontSize: '10px', fontWeight: 'bold' }}>MÓDULOS ACTIVOS</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {['audio_engine', 'vision_haze', 'vision_dj', 'vision_artista', 'cues_clima', 'system_idle'].map(mod => {
            const active = status.permissions?.[mod] || false;
            return (
              <div key={mod} style={{
                background: active ? 'rgba(46,204,113,0.2)' : 'rgba(127,140,141,0.1)',
                border: `1px solid ${active ? '#2ecc71' : '#34495e'}`,
                borderRadius: '6px', padding: '8px 12px',
              }}>
                <div style={{ color: active ? '#2ecc71' : '#7f8c8d', fontSize: '9px', fontWeight: 'bold' }}>
                  {mod.toUpperCase().replace('_', ' ')}
                </div>
                <div style={{ color: active ? '#27ae60' : '#95a5a6', fontSize: '8px' }}>
                  {active ? 'ON' : 'OFF'}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ==================== TAB HORARIOS ====================
function TabHorarios({ schedule, setSchedule, hasChanges, setHasChanges, onSave }) {
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
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: '16px',
      }}>
        <span style={{ color: '#ecf0f1', fontSize: '14px', fontWeight: 'bold' }}>
          EDITOR DE HORARIOS
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {hasChanges && (
            <span style={{ color: '#f39c12', fontSize: '10px', fontWeight: 'bold' }}>
              Cambios sin guardar
            </span>
          )}
          <button
            onClick={onSave}
            disabled={!hasChanges}
            style={{
              background: hasChanges ? '#27ae60' : '#7f8c8d',
              color: 'white', border: 'none', borderRadius: '4px',
              padding: '8px 16px', fontWeight: 'bold', cursor: hasChanges ? 'pointer' : 'default',
            }}
          >
            GUARDAR
          </button>
        </div>
      </div>

      {/* Grid de días */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gap: '8px',
        overflowX: 'auto',
      }}>
        {DAY_ORDER.map(day => (
          <div key={day} style={{
            background: '#1e272e', borderRadius: '8px', border: '1px solid #34495e',
            minWidth: '140px',
          }}>
            {/* Header día */}
            <div style={{
              background: '#2c3e50', padding: '8px',
              borderTopLeftRadius: '8px', borderTopRightRadius: '8px',
              textAlign: 'center',
            }}>
              <span style={{ color: '#ecf0f1', fontSize: '11px', fontWeight: 'bold' }}>
                {DAY_NAMES[day]}
              </span>
            </div>

            {/* Bloques */}
            <div style={{ padding: '8px', maxHeight: '400px', overflowY: 'auto' }}>
              {(week[day] || []).map((block, idx) => (
                <div key={idx} style={{
                  background: `${MODE_COLORS[block.mode] || '#7f8c8d'}15`,
                  border: `1px solid ${MODE_COLORS[block.mode] || '#7f8c8d'}60`,
                  borderRadius: '6px', padding: '8px', marginBottom: '8px',
                }}>
                  {/* Tiempos */}
                  <div style={{ display: 'flex', gap: '4px', marginBottom: '6px' }}>
                    <input
                      type="time"
                      value={block.from}
                      onChange={(e) => updateBlock(day, idx, 'from', e.target.value)}
                      style={{
                        background: '#1e272e', color: '#ecf0f1', border: '1px solid #34495e',
                        borderRadius: '4px', padding: '2px', fontSize: '10px', width: '55px',
                      }}
                    />
                    <span style={{ color: '#7f8c8d', fontSize: '10px' }}>-</span>
                    <input
                      type="time"
                      value={block.to}
                      onChange={(e) => updateBlock(day, idx, 'to', e.target.value)}
                      style={{
                        background: '#1e272e', color: '#ecf0f1', border: '1px solid #34495e',
                        borderRadius: '4px', padding: '2px', fontSize: '10px', width: '55px',
                      }}
                    />
                    <button
                      onClick={() => deleteBlock(day, idx)}
                      style={{
                        background: '#c0392b', color: 'white', border: 'none',
                        borderRadius: '4px', padding: '2px 6px', fontSize: '9px',
                        cursor: 'pointer', marginLeft: 'auto',
                      }}
                    >X</button>
                  </div>

                  {/* Selector modo */}
                  <select
                    value={block.mode}
                    onChange={(e) => updateBlock(day, idx, 'mode', e.target.value)}
                    style={{
                      background: '#1e272e', color: '#ecf0f1', border: '1px solid #34495e',
                      borderRadius: '4px', padding: '4px', fontSize: '9px', width: '100%',
                      marginBottom: '6px',
                    }}
                  >
                    {CANONICAL_MODES.map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>

                  {/* Extras */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                    {EXTRA_ACTIONS.map(action => {
                      const active = (block.actions || []).includes(action);
                      return (
                        <button
                          key={action}
                          onClick={() => toggleAction(day, idx, action)}
                          style={{
                            background: active ? '#2980b9' : '#283747',
                            color: active ? '#ecf0f1' : '#6c7a89',
                            border: 'none', borderRadius: '8px',
                            padding: '2px 6px', fontSize: '8px', cursor: 'pointer',
                          }}
                        >
                          {EXTRA_DISPLAY[action]}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}

              {/* Agregar bloque */}
              <button
                onClick={() => addBlock(day)}
                style={{
                  background: '#27ae60', color: 'white', border: 'none',
                  borderRadius: '4px', padding: '6px', width: '100%',
                  fontWeight: 'bold', fontSize: '10px', cursor: 'pointer',
                }}
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
function TabControl({ status, onGo, onExtend, onOverride, onClearOverride }) {
  const [selectedMode, setSelectedMode] = useState('clima_1');
  const [overrideDuration, setOverrideDuration] = useState(30);

  return (
    <div style={{ padding: '16px' }}>
      {/* GO Section */}
      <div style={{
        background: '#1e272e', borderRadius: '8px', padding: '12px',
        marginBottom: '16px', border: '1px solid #34495e',
      }}>
        <div style={{ marginBottom: '12px' }}>
          <span style={{ color: '#7f8c8d', fontSize: '10px', fontWeight: 'bold' }}>GO - CAMBIAR MODO</span>
        </div>

        {/* Selector modo */}
        <div style={{ marginBottom: '12px' }}>
          <select
            value={selectedMode}
            onChange={(e) => setSelectedMode(e.target.value)}
            style={{
              background: '#2c3e50', color: '#ecf0f1', border: '1px solid #34495e',
              borderRadius: '4px', padding: '8px', width: '100%', fontSize: '12px',
            }}
          >
            {CANONICAL_MODES.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        {/* Botones GO */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            onClick={() => onGo(selectedMode, 0)}
            style={{
              background: '#27ae60', color: 'white', border: 'none',
              borderRadius: '4px', padding: '10px 20px', fontWeight: 'bold',
              cursor: 'pointer', fontSize: '12px',
            }}
          >GO AHORA</button>
          <button onClick={() => onGo(selectedMode, 5)} style={delayBtnStyle}>+5 min</button>
          <button onClick={() => onGo(selectedMode, 10)} style={delayBtnStyle}>+10 min</button>
          <button onClick={() => onGo(selectedMode, 15)} style={delayBtnStyle}>+15 min</button>
        </div>

        {/* Pending GO */}
        {status?.pending_go && (
          <div style={{
            marginTop: '12px', background: 'rgba(52,152,219,0.2)',
            borderRadius: '4px', padding: '8px',
          }}>
            <span style={{ color: '#3498db', fontSize: '10px', fontWeight: 'bold' }}>
              GO PENDIENTE: {status.pending_go.mode} en {formatTime(status.pending_go.seconds_until)}
            </span>
          </div>
        )}
      </div>

      {/* Extend Section */}
      <div style={{
        background: '#1e272e', borderRadius: '8px', padding: '12px',
        marginBottom: '16px', border: '1px solid #34495e',
      }}>
        <div style={{ marginBottom: '12px' }}>
          <span style={{ color: '#7f8c8d', fontSize: '10px', fontWeight: 'bold' }}>
            EXTENDER BLOQUE ACTUAL
          </span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button onClick={() => onExtend(5)} style={extendBtnStyle}>+5 min</button>
          <button onClick={() => onExtend(10)} style={extendBtnStyle}>+10 min</button>
          <button onClick={() => onExtend(15)} style={extendBtnStyle}>+15 min</button>
        </div>
      </div>

      {/* Override Section */}
      <div style={{
        background: '#1e272e', borderRadius: '8px', padding: '12px',
        border: '1px solid #34495e',
      }}>
        <div style={{ marginBottom: '12px' }}>
          <span style={{ color: '#7f8c8d', fontSize: '10px', fontWeight: 'bold' }}>
            OVERRIDE TEMPORAL
          </span>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ color: '#7f8c8d', fontSize: '10px' }}>Duracion:</span>
          <input
            type="number"
            min="5"
            max="120"
            value={overrideDuration}
            onChange={(e) => setOverrideDuration(parseInt(e.target.value) || 30)}
            style={{
              background: '#2c3e50', color: '#ecf0f1', border: '1px solid #34495e',
              borderRadius: '4px', padding: '4px', width: '60px', fontSize: '11px',
            }}
          />
          <span style={{ color: '#7f8c8d', fontSize: '10px' }}>min</span>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={() => onOverride(selectedMode, overrideDuration)}
            style={{
              background: '#e67e22', color: 'white', border: 'none',
              borderRadius: '4px', padding: '8px 16px', fontWeight: 'bold',
              cursor: 'pointer', fontSize: '11px',
            }}
          >ACTIVAR OVERRIDE</button>
          {status?.override?.active && (
            <button
              onClick={onClearOverride}
              style={{
                background: '#c0392b', color: 'white', border: 'none',
                borderRadius: '4px', padding: '8px 16px', fontWeight: 'bold',
                cursor: 'pointer', fontSize: '11px',
              }}
            >LIMPIAR OVERRIDE</button>
          )}
        </div>

        {/* Override info */}
        {status?.override?.active && (
          <div style={{
            marginTop: '12px', background: 'rgba(230,126,34,0.2)',
            borderRadius: '4px', padding: '8px',
          }}>
            <span style={{ color: '#e67e22', fontSize: '10px', fontWeight: 'bold' }}>
              OVERRIDE ACTIVO: {status.override.mode} ({formatTime(status.override.remaining_seconds)} restantes)
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

const delayBtnStyle = {
  background: '#3498db', color: 'white', border: 'none',
  borderRadius: '4px', padding: '8px 12px', cursor: 'pointer', fontSize: '11px',
};

const extendBtnStyle = {
  background: '#9b59b6', color: 'white', border: 'none',
  borderRadius: '4px', padding: '8px 16px', cursor: 'pointer', fontSize: '11px',
};

// ==================== PÁGINA PRINCIPAL ====================
export function Calendar() {
  const [activeTab, setActiveTab] = useState('estado');
  const [status, setStatus] = useState(null);
  const [schedule, setSchedule] = useState({ week: {} });
  const [hasChanges, setHasChanges] = useState(false);

  // Cargar status
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/calendar/status`);
        if (res.ok) setStatus(await res.json());
      } catch (e) {}
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  // Cargar schedule
  useEffect(() => {
    const fetchSchedule = async () => {
      try {
        const res = await fetch(`${API_BASE}/calendar/week`);
        if (res.ok) {
          const data = await res.json();
          setSchedule({ week: data.week || {} });
        }
      } catch (e) {}
    };
    fetchSchedule();
  }, []);

  // Acciones
  const handleGo = async (mode, delay) => {
    try {
      await fetch(`${API_BASE}/calendar/go`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, delay_minutes: delay }),
      });
    } catch (e) {}
  };

  const handleExtend = async (minutes) => {
    try {
      await fetch(`${API_BASE}/calendar/extend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minutes }),
      });
    } catch (e) {}
  };

  const handleOverride = async (mode, duration) => {
    try {
      await fetch(`${API_BASE}/calendar/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, duration_minutes: duration }),
      });
    } catch (e) {}
  };

  const handleClearOverride = async () => {
    try {
      await fetch(`${API_BASE}/calendar/override/stop`, { method: 'POST' });
    } catch (e) {}
  };

  const handleSave = async () => {
    try {
      const res = await fetch(`${API_BASE}/calendar/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ week: schedule.week }),
      });
      if (res.ok) {
        setHasChanges(false);
        alert('Horarios guardados');
      }
    } catch (e) {
      alert('Error al guardar');
    }
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Tabs */}
      <div style={{
        display: 'flex', background: '#2c3e50',
        borderBottom: '1px solid #34495e',
      }}>
        {[
          { key: 'estado', label: 'ESTADO' },
          { key: 'horarios', label: 'HORARIOS' },
          { key: 'control', label: 'CONTROL' },
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              background: activeTab === tab.key ? '#1a1a2e' : 'transparent',
              color: activeTab === tab.key ? '#ecf0f1' : '#bdc3c7',
              border: 'none', padding: '12px 24px',
              cursor: 'pointer', fontSize: '11px', fontWeight: 'bold',
              borderTopLeftRadius: '4px', borderTopRightRadius: '4px',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', background: '#1a1a2e' }}>
        {activeTab === 'estado' && <TabEstado status={status} />}
        {activeTab === 'horarios' && (
          <TabHorarios
            schedule={schedule}
            setSchedule={setSchedule}
            hasChanges={hasChanges}
            setHasChanges={setHasChanges}
            onSave={handleSave}
          />
        )}
        {activeTab === 'control' && (
          <TabControl
            status={status}
            onGo={handleGo}
            onExtend={handleExtend}
            onOverride={handleOverride}
            onClearOverride={handleClearOverride}
          />
        )}
      </div>
    </div>
  );
}
