/**
 * Calendar V7 - Control Room Calendar Page
 *
 * 3 tabs:
 * 1. Estado - Timeline con progreso, modo actual/próximo
 * 2. Horarios - Editor visual de la semana
 * 3. Control - GO, +5/+10/+15, Override
 */
import { useEffect, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import {
  Calendar as CalendarIcon,
  Clock,
  Play,
  Plus,
  Pause,
  AlertTriangle,
  Check,
  Save,
  RefreshCw
} from 'lucide-react';

// Modos disponibles
const AVAILABLE_MODES = [
  'clima_1', 'clima_2', 'clima_3', 'clima_4',
  'boliche_inicio', 'boliche_desarrollo', 'boliche_fin',
  'apagado', 'extra_1', 'extra_2', 'extra_3'
];

// Colores por modo
const modeColors = {
  clima_1: 'bg-blue-500',
  clima_2: 'bg-cyan-500',
  clima_3: 'bg-teal-500',
  clima_4: 'bg-green-500',
  boliche_inicio: 'bg-purple-500',
  boliche_desarrollo: 'bg-pink-500',
  boliche_fin: 'bg-red-500',
  apagado: 'bg-gray-500',
  extra_1: 'bg-amber-500',
  extra_2: 'bg-orange-500',
  extra_3: 'bg-rose-500',
};

// Días de la semana
const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const DAYS_ES = {
  monday: 'Lunes', tuesday: 'Martes', wednesday: 'Miércoles',
  thursday: 'Jueves', friday: 'Viernes', saturday: 'Sábado', sunday: 'Domingo'
};

// Formatear tiempo
function formatTime(seconds) {
  if (seconds < 0) return '—';
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  const remainMins = mins % 60;
  return `${hours}h ${remainMins}m`;
}

// Hook para cargar estado del calendario
function useCalendarStatus() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/calendar/status');
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (e) {
      console.error('[CALENDAR] status error:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 2000);
    return () => clearInterval(interval);
  }, [refresh]);

  return { status, loading, refresh };
}

// Hook para cargar schedule de la semana
function useCalendarWeek() {
  const [week, setWeek] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/calendar/week');
      if (res.ok) {
        const data = await res.json();
        setWeek(data.week || {});
        setDirty(false);
      }
    } catch (e) {
      console.error('[CALENDAR] week error:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const updateDay = (day, blocks) => {
    setWeek(prev => ({ ...prev, [day]: blocks }));
    setDirty(true);
  };

  const save = async () => {
    try {
      const res = await fetch('/api/v1/calendar/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ week })
      });
      if (res.ok) {
        setDirty(false);
        return true;
      }
    } catch (e) {
      console.error('[CALENDAR] save error:', e);
    }
    return false;
  };

  return { week, loading, dirty, updateDay, save, reload: load };
}

// Tab 1: Estado
function StatusTab({ status }) {
  if (!status) return <p className="text-muted-foreground">Loading...</p>;

  const modeColor = modeColors[status.current_mode] || 'bg-gray-500';

  return (
    <div className="space-y-6">
      {/* Estado actual */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Current State
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Modo actual */}
          <div className="flex justify-between items-center">
            <span className="text-muted-foreground">Mode</span>
            <Badge className={`${modeColor} text-white text-lg px-4 py-1`}>
              {status.current_mode}
            </Badge>
          </div>

          {/* Source */}
          <div className="flex justify-between items-center">
            <span className="text-muted-foreground">Source</span>
            <Badge variant={status.override?.active ? 'destructive' : 'default'}>
              {status.override?.active ? 'OVERRIDE' : status.source || 'AUTO'}
            </Badge>
          </div>

          {/* Próximo modo */}
          {status.next_mode && (
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Next Mode</span>
              <div className="flex items-center gap-2">
                <Badge variant="outline">{status.next_mode}</Badge>
                <span className="text-sm text-muted-foreground">
                  in {formatTime(status.time_to_next_s)}
                </span>
              </div>
            </div>
          )}

          {/* Progress bar */}
          {status.progress > 0 && (
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-muted-foreground">Block Progress</span>
                <span>{Math.round(status.progress * 100)}%</span>
              </div>
              <div className="w-full bg-secondary rounded-full h-3">
                <div
                  className={`h-3 rounded-full transition-all ${modeColor}`}
                  style={{ width: `${Math.max(5, status.progress * 100)}%` }}
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Override activo */}
      {status.override?.active && (
        <Card className="border-orange-500">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-orange-500">
              <AlertTriangle className="h-5 w-5" />
              Override Active
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between">
              <span>Mode</span>
              <Badge>{status.override.mode}</Badge>
            </div>
            {status.override.remaining_seconds > 0 && (
              <div className="flex justify-between">
                <span>Remaining</span>
                <span>{formatTime(status.override.remaining_seconds)}</span>
              </div>
            )}
            {status.override.reason && (
              <div className="flex justify-between">
                <span>Reason</span>
                <span className="text-muted-foreground">{status.override.reason}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Alerta pendiente */}
      {status.alert && !status.alert.acknowledged && (
        <Card className="border-yellow-500">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-yellow-500">
              <AlertTriangle className="h-5 w-5" />
              Upcoming Change
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p>
              Changing to <Badge>{status.alert.mode}</Badge> in{' '}
              {formatTime(status.alert.seconds_until)}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// Tab 2: Horarios (Editor simplificado)
function ScheduleTab({ week, dirty, updateDay, save, reload }) {
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    const success = await save();
    setSaving(false);
    if (success) {
      alert('Schedule saved!');
    } else {
      alert('Error saving schedule');
    }
  };

  if (!week) return <p className="text-muted-foreground">Loading...</p>;

  return (
    <div className="space-y-4">
      {/* Header con estado de guardado */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-2">
          {dirty ? (
            <Badge className="bg-red-500">Unsaved changes</Badge>
          ) : (
            <Badge className="bg-green-500">Synced</Badge>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={reload}>
            <RefreshCw className="h-4 w-4 mr-1" /> Reload
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!dirty || saving}
            className="bg-green-600 hover:bg-green-700"
          >
            <Save className="h-4 w-4 mr-1" /> Save
          </Button>
        </div>
      </div>

      {/* Grid de días */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {DAYS.map(day => (
          <Card key={day}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">{DAYS_ES[day]}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(week[day] || []).length === 0 ? (
                  <p className="text-xs text-muted-foreground">No blocks</p>
                ) : (
                  (week[day] || []).map((block, idx) => (
                    <div
                      key={idx}
                      className={`p-2 rounded text-xs ${modeColors[block.mode] || 'bg-gray-500'} text-white`}
                    >
                      <div className="font-medium">{block.mode}</div>
                      <div className="opacity-80">
                        {block.from} - {block.to}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <p className="text-xs text-muted-foreground text-center">
        Full schedule editor coming soon. Use Qt UI for detailed editing.
      </p>
    </div>
  );
}

// Tab 3: Control
function ControlTab({ status, refresh }) {
  const [loading, setLoading] = useState(false);
  const [selectedMode, setSelectedMode] = useState('boliche_desarrollo');
  const [overrideDuration, setOverrideDuration] = useState(30);

  const handleGo = async (mode, delay = 0) => {
    if (!confirm(`Execute GO to ${mode}${delay > 0 ? ` in ${delay} minutes` : ''}?`)) return;

    setLoading(true);
    try {
      const res = await fetch('/api/v1/calendar/go', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, delay_minutes: delay })
      });
      if (res.ok) {
        await refresh();
      }
    } catch (e) {
      console.error('[CALENDAR] go error:', e);
    }
    setLoading(false);
  };

  const handleExtend = async (minutes) => {
    if (!confirm(`Extend current block by ${minutes} minutes?`)) return;

    setLoading(true);
    try {
      const res = await fetch('/api/v1/calendar/extend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minutes })
      });
      if (res.ok) {
        await refresh();
      }
    } catch (e) {
      console.error('[CALENDAR] extend error:', e);
    }
    setLoading(false);
  };

  const handleOverride = async () => {
    if (!confirm(`Activate override: ${selectedMode} for ${overrideDuration} minutes?`)) return;

    setLoading(true);
    try {
      const res = await fetch('/api/v1/calendar/override', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: selectedMode,
          duration_minutes: overrideDuration,
          reason: 'Web Control Room'
        })
      });
      if (res.ok) {
        await refresh();
      }
    } catch (e) {
      console.error('[CALENDAR] override error:', e);
    }
    setLoading(false);
  };

  const handleStopOverride = async () => {
    if (!confirm('Stop override and return to automatic mode?')) return;

    setLoading(true);
    try {
      const res = await fetch('/api/v1/calendar/override/stop', {
        method: 'POST'
      });
      if (res.ok) {
        await refresh();
      }
    } catch (e) {
      console.error('[CALENDAR] stop override error:', e);
    }
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      {/* GO Quick Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Play className="h-5 w-5" />
            GO - Quick Actions
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {AVAILABLE_MODES.slice(0, 8).map(mode => (
              <Button
                key={mode}
                variant="outline"
                size="sm"
                onClick={() => handleGo(mode)}
                disabled={loading}
                className="text-xs"
              >
                {mode}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Extend */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Plus className="h-5 w-5" />
            Extend Current Block
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            {[5, 10, 15, 30].map(mins => (
              <Button
                key={mins}
                variant="outline"
                onClick={() => handleExtend(mins)}
                disabled={loading}
              >
                +{mins}min
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Override */}
      <Card className="border-orange-500">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-orange-500">
            <Pause className="h-5 w-5" />
            Override
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {status?.override?.active ? (
            <div className="space-y-4">
              <div className="p-4 bg-orange-500/10 rounded-lg">
                <p className="font-medium">Override Active</p>
                <p className="text-sm text-muted-foreground">
                  Mode: {status.override.mode} |{' '}
                  Remaining: {formatTime(status.override.remaining_seconds)}
                </p>
              </div>
              <Button
                variant="destructive"
                onClick={handleStopOverride}
                disabled={loading}
                className="w-full"
              >
                Stop Override
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">Mode</label>
                  <select
                    value={selectedMode}
                    onChange={e => setSelectedMode(e.target.value)}
                    className="w-full p-2 rounded border bg-background"
                  >
                    {AVAILABLE_MODES.map(mode => (
                      <option key={mode} value={mode}>{mode}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium mb-2 block">Duration (min)</label>
                  <select
                    value={overrideDuration}
                    onChange={e => setOverrideDuration(Number(e.target.value))}
                    className="w-full p-2 rounded border bg-background"
                  >
                    {[15, 30, 45, 60, 90, 120, 180, 240].map(d => (
                      <option key={d} value={d}>{d} min</option>
                    ))}
                  </select>
                </div>
              </div>
              <Button
                onClick={handleOverride}
                disabled={loading}
                className="w-full bg-orange-600 hover:bg-orange-700"
              >
                Activate Override
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// Página principal
export function Calendar() {
  const [activeTab, setActiveTab] = useState('status');
  const { status, loading: statusLoading, refresh } = useCalendarStatus();
  const weekData = useCalendarWeek();

  const tabs = [
    { id: 'status', label: 'Estado' },
    { id: 'schedule', label: 'Horarios' },
    { id: 'control', label: 'Control' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <CalendarIcon className="h-6 w-6" />
          Calendar
        </h2>
        {status?.override?.active && (
          <Badge className="bg-orange-500">OVERRIDE ACTIVE</Badge>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 font-medium transition-colors ${
              activeTab === tab.id
                ? 'border-b-2 border-primary text-primary'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'status' && <StatusTab status={status} />}
        {activeTab === 'schedule' && (
          <ScheduleTab
            week={weekData.week}
            dirty={weekData.dirty}
            updateDay={weekData.updateDay}
            save={weekData.save}
            reload={weekData.reload}
          />
        )}
        {activeTab === 'control' && <ControlTab status={status} refresh={refresh} />}
      </div>
    </div>
  );
}
