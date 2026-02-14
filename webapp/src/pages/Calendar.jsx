/**
 * Calendar — Calendar Panel (Glass UI)
 *
 * Matches UI contract: docs/ui-contract/calendar_glass.html
 *
 * Sub-tabs:
 * - Estado: Live header + accordion day-strip grid (1 expanded at a time)
 * - Semana: Accordion editor (1 expanded at a time, sliding door)
 * - Control: GO / Extend / Override (softened glass)
 *
 * Accordion rule: only ONE day can be expanded. Clicking a day closes
 * the previous and opens the new one with a CSS flex transition.
 * Today is always green-highlighted, even when collapsed.
 *
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

const MODE_LABELS = {
  clima_1: 'Clima 1', clima_2: 'Clima 2', clima_3: 'Clima 3', clima_4: 'Clima 4',
  boliche_inicio: 'Boliche Inicio', boliche_desarrollo: 'Boliche Desarrollo',
  boliche_fin: 'Boliche Fin', apagado: 'Apagado',
  teatro: 'Teatro', artista: 'Artista',
};

const EXTRA_ACTIONS = ['vision_haze', 'vision_dj', 'vision_artista'];
const EXTRA_DISPLAY = { vision_haze: 'Haze', vision_dj: 'DJ', vision_artista: 'Artista' };

const DAY_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const DAY_NAMES = {
  monday: 'LUN', tuesday: 'MAR', wednesday: 'MIÉ',
  thursday: 'JUE', friday: 'VIE', saturday: 'SÁB', sunday: 'DOM'
};

const MODULE_LABELS = {
  audio_engine: 'Audio Engine',
  vision_haze: 'Vision Haze',
  vision_dj: 'Vision DJ',
  cues_clima: 'Cues Clima',
  vision_artista: 'Vision Artista',
  bajada: 'Bajada',
  base_golpe: 'Base Golpe',
  ataque: 'Ataque',
  brake: 'Brake',
};

// Formatea segundos
function formatTime(s) {
  if (s == null || s < 0) return '---';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

// Today's day index (Monday=0)
function getTodayIdx() {
  return (new Date().getDay() + 6) % 7;
}

// Inline styles for the content wrapper fade transition
const CONTENT_OPEN = {
  opacity: 1,
  transform: 'translateY(0)',
  transition: 'opacity 0.3s ease 0.12s, transform 0.3s ease 0.12s',
  pointerEvents: 'auto',
};
const CONTENT_CLOSED = {
  opacity: 0,
  transform: 'translateY(6px)',
  transition: 'opacity 0.15s ease, transform 0.15s ease',
  pointerEvents: 'none',
  position: 'absolute',
  width: '100%',
};

// Today green glow for collapsed today strip
const TODAY_COLLAPSED_GLOW = {
  boxShadow: 'inset 0 0 20px rgba(0,230,118,0.06), 0 0 1px rgba(0,230,118,0.3)',
};
const TODAY_EXPANDED_GLOW = {
  boxShadow: 'inset 0 0 30px rgba(0,230,118,0.08), 0 0 2px rgba(0,230,118,0.4)',
};

// ==================== TAB ESTADO ====================
function TabEstado({ status, schedule, apiOffline, onAuto }) {
  const [now, setNow] = useState(new Date());
  const todayIdx = getTodayIdx();
  const [activeDay, setActiveDay] = useState(todayIdx);

  useEffect(() => {
    const tick = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(tick);
  }, []);

  if (apiOffline) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 0' }}>
        <div className="led red" />
        <p className="t3 text-base mt-4">CORE OFFLINE</p>
        <p className="t4 text-sm mt-2">No se puede conectar al sistema</p>
      </div>
    );
  }

  if (!status) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '60px 0' }}>
        <div className="led" />
        <p className="t3 text-sm" style={{ marginLeft: '12px' }}>Cargando...</p>
      </div>
    );
  }

  const isAuto = status.auto !== false;
  const week = schedule?.week || {};
  const modeColor = MODE_COLORS[status.current_mode] || '#7f8c8d';
  const progress = status.progress != null ? Math.min(100, Math.max(0, (status.progress || 0) * 100)) : null;

  // Compute current week dates (Monday=0)
  const monday = new Date(now);
  monday.setDate(now.getDate() - todayIdx);

  return (
    <div style={{ flex: 1, padding: '0 28px 28px' }}>

      {/* ─── HERO HEADER ─── */}
      <div style={{ display: 'flex', gap: '14px', marginBottom: '24px' }}>

        {/* Clock */}
        <div className="g" style={{ flex: '0 0 300px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <div className="green" style={{ fontFamily: 'var(--font-title)', fontSize: '52px', fontWeight: 800, lineHeight: 1 }}>
            {now.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </div>
          <div className="t2 text-sm mt-3" style={{ textTransform: 'capitalize' }}>
            {now.toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long' })}
          </div>
          <div className="flex items-center gap-2 mt-3">
            <button
              onClick={() => onAuto(!isAuto)}
              className={isAuto ? 'key' : 'key-danger'}
              style={{ padding: '5px 12px', fontSize: '10px' }}
            >
              {isAuto ? 'AUTO' : 'MANUAL'}
            </button>
            {status.override_active && <span className="b yellow" style={{ fontSize: '9px' }}>OVERRIDE</span>}
          </div>
        </div>

        {/* Mode + Next Block */}
        <div className="g" style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <div style={{ display: 'flex', gap: '20px' }}>
            <div style={{ flex: 1 }}>
              <div className="t4 text-sm mb-2" style={{ letterSpacing: '1.5px' }}>MODE</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: modeColor }}>
                {status.current_mode || '---'}
              </div>
            </div>
            <div style={{ width: '1px', background: 'rgba(255,255,255,0.06)', alignSelf: 'stretch' }} />
            <div style={{ flex: 1 }}>
              <div className="t4 text-sm mb-2" style={{ letterSpacing: '1.5px' }}>NEXT BLOCK</div>
              <div className="green" style={{ fontSize: '24px', fontWeight: 700 }}>
                {status.next_mode || '---'}
              </div>
              {status.time_remaining_s != null && (
                <div className="t3 mono text-sm mt-2">
                  en {formatTime(status.time_remaining_s)}
                </div>
              )}
            </div>
          </div>
          {progress != null && (
            <div style={{ marginTop: '16px' }}>
              <div className="gauge" style={{ height: '6px' }}>
                <div className="gauge-fill" style={{ width: `${Math.max(3, progress)}%`, background: modeColor }} />
              </div>
              <div className="flex justify-between mt-2">
                <span className="t4 text-sm">{Math.round(progress)}%</span>
                {status.time_remaining_s != null && (
                  <span className="t4 text-sm mono">{formatTime(status.time_remaining_s)}</span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Modules */}
        <div className="gp" style={{ flex: '0 0 200px' }}>
          <div className="t3 text-sm mb-3" style={{ letterSpacing: '1.5px' }}>MODULES</div>
          {['audio_engine', 'vision_haze', 'vision_dj', 'cues_clima'].map(mod => {
            const active = status.permissions?.[mod] || false;
            return (
              <div key={mod} className="flex items-center gap-2" style={{ padding: '5px 0' }}>
                <div className={`led-dot${active ? '' : ' off'}`} />
                <span className={`text-sm t2${active ? '' : ' opacity-50'}`}>
                  {MODULE_LABELS[mod] || mod}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ─── DAY STRIP ACCORDION ─── */}
      <div style={{ display: 'flex', gap: 0, minHeight: '520px', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
        {DAY_ORDER.map((day, i) => {
          const date = new Date(monday);
          date.setDate(monday.getDate() + i);
          const isToday = i === todayIdx;
          const isActive = i === activeDay;
          const blockCount = (week[day] || []).length;
          const blocks = week[day] || [];

          // Build class string
          const cls = [
            'day-strip',
            isToday ? 'today' : '',
            isActive ? 'expanded' : 'collapsed',
          ].filter(Boolean).join(' ');

          // Today glow (always present, stronger when expanded)
          const todayStyle = isToday
            ? (isActive ? TODAY_EXPANDED_GLOW : TODAY_COLLAPSED_GLOW)
            : {};

          return (
            <div
              key={day}
              className={cls}
              onClick={() => !isActive && setActiveDay(i)}
              style={{
                ...todayStyle,
                ...(i === DAY_ORDER.length - 1 ? { borderRight: 'none' } : {}),
              }}
            >
              {/* Day header — always visible */}
              <div style={{ padding: isActive ? '16px 12px' : '16px 6px', textAlign: 'center', position: 'relative', zIndex: 1, flexShrink: 0 }}>
                <div
                  className={isToday ? 'green' : 't3'}
                  style={{
                    fontFamily: 'var(--font-title)',
                    fontSize: isActive ? '13px' : '11px',
                    fontWeight: 700,
                    transition: 'font-size 0.3s ease',
                  }}
                >
                  {isActive ? DAY_NAMES[day] : DAY_NAMES[day].charAt(0)}
                </div>
                <div
                  className={isToday ? 'green' : 't4'}
                  style={{
                    fontFamily: 'var(--font-title)',
                    fontSize: isActive ? '28px' : '18px',
                    fontWeight: 800,
                    marginTop: '4px',
                    transition: 'font-size 0.3s ease',
                  }}
                >
                  {date.getDate()}
                </div>
                <div
                  className={`b${blockCount === 0 ? ' gray' : ''}`}
                  style={{ marginTop: '6px', fontSize: '9px' }}
                >
                  {blockCount}
                </div>
                {isToday && <div className="led-dot" style={{ margin: '8px auto 0' }} />}
              </div>

              {/* Block timeline — rendered always, animated with opacity */}
              <div style={{
                ...(isActive ? CONTENT_OPEN : CONTENT_CLOSED),
                padding: '0 12px 16px',
                zIndex: 1,
                flex: isActive ? 1 : 'none',
                overflow: isActive ? 'auto' : 'hidden',
              }}>
                {blocks.length > 0 ? (
                  <div style={{ borderLeft: '2px solid rgba(0,230,118,0.15)', marginLeft: '8px', paddingLeft: '14px' }}>
                    {blocks.map((block, idx) => {
                      const color = MODE_COLORS[block.mode] || '#7f8c8d';
                      const isCurrent = isToday && status.current_mode === block.mode;
                      return (
                        <div
                          key={idx}
                          className="inset mb-2"
                          style={{
                            borderColor: isCurrent ? `${color}80` : undefined,
                            position: 'relative',
                          }}
                        >
                          <div style={{
                            position: 'absolute',
                            left: '-22px',
                            top: '12px',
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            background: isCurrent ? color : 'rgba(255,255,255,0.15)',
                            boxShadow: isCurrent ? `0 0 8px ${color}` : 'none',
                            transition: 'all 0.3s ease',
                          }} />
                          <div className="flex justify-between mb-1">
                            <span className="mono text-sm" style={{ color }}>{block.from} - {block.to}</span>
                          </div>
                          <div className="text-sm font-semibold" style={{ color }}>
                            {MODE_LABELS[block.mode] || block.mode}
                          </div>
                          {(block.actions || []).length > 0 && (
                            <div className="flex gap-2 mt-2" style={{ flexWrap: 'wrap' }}>
                              {block.actions.map(a => (
                                <span key={a} className="b gray" style={{ fontSize: '8px' }}>
                                  {EXTRA_DISPLAY[a] || a}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="t4 text-sm" style={{ textAlign: 'center', padding: '20px 0' }}>
                    Sin bloques
                  </div>
                )}
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
  const todayIdx = getTodayIdx();
  const [activeDay, setActiveDay] = useState(todayIdx);

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
    <div style={{ padding: '16px 28px', flex: 1, display: 'flex', flexDirection: 'column' }}>

      {/* Header + Save */}
      <div className="flex justify-between items-center mb-4">
        <div>
          <span style={{ fontFamily: 'var(--font-title)', fontSize: '16px', fontWeight: 700 }}>Editor Semanal</span>
        </div>
        <div className="flex items-center gap-3">
          {hasChanges && <span className="b yellow" style={{ fontSize: '9px' }}>SIN GUARDAR</span>}
          <button
            onClick={onSave}
            disabled={!hasChanges || apiOffline}
            className={hasChanges && !apiOffline ? 'key' : 'key-2'}
            style={{ padding: '7px 18px', fontSize: '11px' }}
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

      {/* Day strip accordion editor */}
      <div style={{ display: 'flex', gap: 0, flex: 1, minHeight: 0, borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
        {DAY_ORDER.map((day, i) => {
          const isToday = i === todayIdx;
          const isActive = i === activeDay;
          const blocks = week[day] || [];

          const cls = [
            'day-strip',
            isToday ? 'today' : '',
            isActive ? 'expanded' : 'collapsed',
          ].filter(Boolean).join(' ');

          const todayStyle = isToday
            ? (isActive ? TODAY_EXPANDED_GLOW : TODAY_COLLAPSED_GLOW)
            : {};

          return (
            <div
              key={`${day}-${gridRev}`}
              className={cls}
              onClick={() => !isActive && setActiveDay(i)}
              style={{
                ...todayStyle,
                ...(i === DAY_ORDER.length - 1 ? { borderRight: 'none' } : {}),
              }}
            >
              {/* Day header — always visible */}
              <div style={{ padding: isActive ? '16px 10px' : '16px 6px', textAlign: 'center', position: 'relative', zIndex: 1, flexShrink: 0 }}>
                <div
                  className={isToday ? 'green' : 't3'}
                  style={{
                    fontFamily: 'var(--font-title)',
                    fontSize: isActive ? '13px' : '11px',
                    fontWeight: 700,
                    transition: 'font-size 0.3s ease',
                  }}
                >
                  {isActive ? DAY_NAMES[day] : DAY_NAMES[day].charAt(0)}
                </div>
                {isActive && (
                  <div className={`b${blocks.length === 0 ? ' gray' : ''}`} style={{ marginTop: '6px', fontSize: '9px' }}>
                    {blocks.length}
                  </div>
                )}
                {isToday && <div className="led-dot" style={{ margin: '6px auto 0' }} />}
              </div>

              {/* Block editor — always rendered, opacity animated */}
              <div style={{
                ...(isActive ? CONTENT_OPEN : CONTENT_CLOSED),
                padding: '0 8px 12px',
                zIndex: 1,
                flex: isActive ? 1 : 'none',
                overflowY: isActive ? 'auto' : 'hidden',
              }}>
                {blocks.map((block, idx) => {
                  const color = MODE_COLORS[block.mode] || '#7f8c8d';
                  return (
                    <div
                      key={idx}
                      className="inset mb-2"
                      style={{
                        borderColor: `${color}50`,
                        borderLeft: `3px solid ${color}`,
                      }}
                    >
                      {/* Time inputs */}
                      <div className="flex items-center gap-2 mb-2">
                        <input
                          type="time"
                          value={block.from}
                          onChange={(e) => updateBlock(day, idx, 'from', e.target.value)}
                          style={{ width: '65px', padding: '4px', fontSize: '10px' }}
                        />
                        <span className="t3" style={{ fontSize: '10px' }}>—</span>
                        <input
                          type="time"
                          value={block.to}
                          onChange={(e) => updateBlock(day, idx, 'to', e.target.value)}
                          style={{ width: '65px', padding: '4px', fontSize: '10px' }}
                        />
                        <button
                          onClick={() => deleteBlock(day, idx)}
                          className="key-danger"
                          style={{ padding: '2px 6px', fontSize: '9px', marginLeft: 'auto', opacity: 0.6 }}
                        >✕</button>
                      </div>

                      {/* Mode selector */}
                      <select
                        value={block.mode}
                        onChange={(e) => updateBlock(day, idx, 'mode', e.target.value)}
                        style={{ width: '100%', padding: '4px', fontSize: '10px', marginBottom: '6px' }}
                      >
                        {CANONICAL_MODES.map(m => (
                          <option key={m} value={m}>{MODE_LABELS[m] || m}</option>
                        ))}
                      </select>

                      {/* Extra actions */}
                      <div className="flex" style={{ flexWrap: 'wrap', gap: '4px' }}>
                        {EXTRA_ACTIONS.map(action => {
                          const active = (block.actions || []).includes(action);
                          return (
                            <button
                              key={action}
                              onClick={() => toggleAction(day, idx, action)}
                              className={active ? 'key' : 'key-2'}
                              style={{ padding: '2px 5px', fontSize: '8px' }}
                            >
                              {EXTRA_DISPLAY[action]}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}

                {/* Add block button */}
                <button
                  onClick={() => addBlock(day)}
                  className="key-2 w-full"
                  style={{ fontSize: '10px', padding: '8px', opacity: 0.7 }}
                >
                  + Agregar
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ==================== TAB CONTROL ====================
function TabControl({ status, onGo, onExtend, onOverride, onClearOverride, apiOffline }) {
  const [selectedMode, setSelectedMode] = useState('clima_1');
  const [overrideDuration, setOverrideDuration] = useState(30);

  return (
    <div style={{ padding: '16px 28px', maxWidth: '720px' }}>
      {/* API Offline */}
      {apiOffline && (
        <div className="gp mb-4" style={{ textAlign: 'center', borderColor: 'rgba(255,82,82,0.3)' }}>
          <div className="led red" style={{ margin: '0 auto 8px' }} />
          <span className="red text-sm">API OFFLINE — Controles deshabilitados</span>
        </div>
      )}

      {/* GO */}
      <div className="ctrl-card mb-4">
        <div style={{ fontFamily: 'var(--font-title)', fontSize: '14px', fontWeight: 700, letterSpacing: '1.5px', marginBottom: '16px' }}>
          GO — Cambiar Modo
        </div>
        <select
          value={selectedMode}
          onChange={(e) => setSelectedMode(e.target.value)}
          style={{ width: '100%', marginBottom: '16px' }}
        >
          {CANONICAL_MODES.map(m => <option key={m} value={m}>{MODE_LABELS[m] || m}</option>)}
        </select>

        <div className="flex gap-3" style={{ flexWrap: 'wrap' }}>
          <button onClick={() => onGo(selectedMode, 0)} disabled={apiOffline} className="key" style={{ padding: '10px 20px' }}>
            GO AHORA
          </button>
          <button onClick={() => onGo(selectedMode, 5)} disabled={apiOffline} className="key-2" style={{ padding: '10px 16px' }}>
            +5 min
          </button>
          <button onClick={() => onGo(selectedMode, 10)} disabled={apiOffline} className="key-2" style={{ padding: '10px 16px' }}>
            +10 min
          </button>
          <button onClick={() => onGo(selectedMode, 15)} disabled={apiOffline} className="key-2" style={{ padding: '10px 16px' }}>
            +15 min
          </button>
        </div>

        {status?.pending_go && (
          <div className="inset mt-3">
            <span className="cyan text-sm font-bold">
              GO PENDIENTE: {MODE_LABELS[status.pending_go.mode] || status.pending_go.mode} en {formatTime(status.pending_go.seconds_until)}
            </span>
          </div>
        )}
      </div>

      {/* Extend */}
      <div className="ctrl-card mb-4">
        <div style={{ fontFamily: 'var(--font-title)', fontSize: '14px', fontWeight: 700, letterSpacing: '1.5px', marginBottom: '16px' }}>
          Extender Bloque
        </div>
        <div className="flex gap-3">
          <button onClick={() => onExtend(5)} disabled={apiOffline} className="key-2" style={{ padding: '10px 16px' }}>
            +5 min
          </button>
          <button onClick={() => onExtend(10)} disabled={apiOffline} className="key-2" style={{ padding: '10px 16px' }}>
            +10 min
          </button>
          <button onClick={() => onExtend(15)} disabled={apiOffline} className="key-2" style={{ padding: '10px 16px' }}>
            +15 min
          </button>
        </div>
      </div>

      {/* Override */}
      <div className="ctrl-card" style={{ borderColor: 'rgba(255,152,0,0.15)' }}>
        <div className="flex items-center gap-3 mb-4">
          <div className="led yellow" />
          <div style={{ fontFamily: 'var(--font-title)', fontSize: '14px', fontWeight: 700, letterSpacing: '1.5px' }}>
            Override Temporal
          </div>
        </div>

        <div className="flex items-center gap-3 mb-4">
          <span className="t3 text-sm">Duración</span>
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

        <div className="flex gap-3">
          <button
            onClick={() => onOverride(selectedMode, overrideDuration)}
            disabled={apiOffline}
            className="key-danger"
            style={{ padding: '10px 20px' }}
          >
            Activar Override
          </button>
          {status?.override?.active && (
            <button
              onClick={onClearOverride}
              disabled={apiOffline}
              className="key-2"
              style={{ padding: '10px 20px' }}
            >
              Limpiar
            </button>
          )}
        </div>

        {status?.override?.active && (
          <div className="inset mt-4" style={{ borderColor: 'rgba(255,152,0,0.2)' }}>
            <div className="flex items-center gap-2">
              <div className="led-dot" style={{ background: 'var(--orange)', boxShadow: '0 0 6px var(--orange)' }} />
              <span className="yellow text-sm font-semibold">
                OVERRIDE: {MODE_LABELS[status.override.mode] || status.override.mode} ({formatTime(status.override.remaining_seconds)} restantes)
              </span>
            </div>
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
  const [gridRev, setGridRev] = useState(0);

  const fetchWeek = async (force = false) => {
    if (hasChanges && !force) return;
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
    } catch (e) {}
  };

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

  useEffect(() => {
    fetchWeek(true);
  }, []);

  useEffect(() => {
    if (hasChanges) return;
    const interval = setInterval(() => fetchWeek(), 5000);
    return () => clearInterval(interval);
  }, [hasChanges]);

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
          const weekKeys = Object.keys(data.week || {});
          console.log('[SAVE] week keys:', weekKeys);

          if (data.week && weekKeys.length > 0) {
            setSchedule({ week: data.week });
            console.log('[SAVE] Estado actualizado con week del CORE');
          } else {
            console.warn('[SAVE] week vacío en respuesta, haciendo refetch...');
            await fetchWeek(true);
          }

          setHasChanges(false);
          setGridRev(r => r + 1);
          setSaveSuccess(true);

          if (data.warnings && data.warnings.length > 0) {
            setWarnings(data.warnings);
          }
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

      {saveSuccess && (
        <div className="p-3" style={{ background: 'rgba(0,230,118,0.1)', borderBottom: '1px solid var(--green)' }}>
          <span className="green font-bold text-sm">Guardado OK</span>
        </div>
      )}

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

      <div style={{ padding: '20px 28px' }}>
        <h1 style={{ fontFamily: 'var(--font-title)', fontSize: '24px', fontWeight: 700 }}>Calendar</h1>
      </div>

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

      <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
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
