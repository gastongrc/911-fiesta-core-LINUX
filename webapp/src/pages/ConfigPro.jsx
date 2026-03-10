/**
 * ConfigPro — Configuration Panel (glass UI)
 *
 * Matches UI contract:
 * - docs/ui-contract/config_panel_pro.html
 *
 * Tabs: Bajada, Base Golpe, Ataque, Brake, Red/Consola, Calendario
 * Cards: Consola Avolites, Red Local, Transporte, Offset de Cues, Vision Pro
 *
 * Uses glass design system exclusively (control-room.css)
 * Existing config API hooks preserved
 */
import { useEffect, useState } from 'react';
import {
  getAvolitesConfig,
  getModulesConfig,
  updateAvolitesConfig,
  updateModulesConfig,
} from '../api/config';
import { setNetworkInterface } from '../api/network';

const TABS = [
  'Bajada',
  'Base Golpe',
  'Ataque',
  'Brake',
  'Red/Consola',
  'Calendario',
];

export function ConfigPro() {
  const [activeTab, setActiveTab] = useState('Red/Consola');
  const [avolitesConfig, setAvolitesConfig] = useState(null);
  const [modulesConfig, setModulesConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);

  // Form state
  const [consoleIp, setConsoleIp] = useState('');
  const [consolePort, setConsolePort] = useState('');
  const [cueOffset, setCueOffset] = useState(0);
  const [nic, setNic] = useState('eth0');

  useEffect(() => {
    loadConfigs();
  }, []);

  const showMessage = (text, type = 'success') => {
    setMessage({ text, type });
    window.setTimeout(() => setMessage(null), 3000);
  };

  const loadConfigs = async () => {
    setLoading(true);
    try {
      const [avolitesRes, modulesRes] = await Promise.all([
        getAvolitesConfig(),
        getModulesConfig(),
      ]);

      const avoData = avolitesRes.data?.data || {};
      setAvolitesConfig(avoData);
      setModulesConfig(modulesRes.data?.data || {});

      if (avoData.console_ip) setConsoleIp(avoData.console_ip);
      if (avoData.console_port) setConsolePort(String(avoData.console_port));
      if (avoData.cue_offset !== undefined) setCueOffset(avoData.cue_offset);
    } catch (error) {
      showMessage('Error cargando config', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveAvolites = async () => {
    setLoading(true);
    try {
      await updateAvolitesConfig({
        console_ip: consoleIp,
        console_port: parseInt(consolePort) || 4430,
      });
      showMessage('Avolites guardado');
      loadConfigs();
    } catch (error) {
      showMessage('Error guardando Avolites', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveOffset = async () => {
    setLoading(true);
    try {
      await updateAvolitesConfig({ cue_offset: cueOffset });
      showMessage('Offset actualizado');
      loadConfigs();
    } catch (error) {
      showMessage('Error guardando offset', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleModule = async (moduleName, currentEnabled) => {
    setLoading(true);
    try {
      await updateModulesConfig({
        [moduleName]: { enabled: !currentEnabled },
      });
      showMessage(`${moduleName} ${!currentEnabled ? 'activado' : 'desactivado'}`);
      loadConfigs();
    } catch (error) {
      showMessage('Error toggling module', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleApplyNic = async () => {
    setLoading(true);
    try {
      await setNetworkInterface(nic);
      showMessage(`Interfaz ${nic} aplicada`);
      loadConfigs();
    } catch (error) {
      showMessage('Error aplicando interfaz', 'error');
    } finally {
      setLoading(false);
    }
  };

  // Module list for current tab (Bajada, Base Golpe, etc.)
  const renderModuleTab = (tabName) => {
    const modules = modulesConfig ? Object.entries(modulesConfig) : [];
    const tabKey = tabName.toLowerCase().replace(/ /g, '_');

    return (
      <div style={{ padding: '16px 28px' }}>
        <div className="g">
          <h3 className="font-bold mb-4">{tabName} — Módulos</h3>
          {modules.length === 0 ? (
            <div className="t3 text-sm">Sin módulos configurados</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {modules.map(([name, config]) => (
                <div
                  key={name}
                  className="inset flex items-center justify-between"
                  style={{ cursor: 'pointer' }}
                  onClick={() => handleToggleModule(name, config.enabled)}
                >
                  <div className="flex items-center gap-3">
                    <div className={`led-dot${config.enabled ? '' : ' off'}`} />
                    <span className={`text-sm${config.enabled ? '' : ' opacity-50'}`}>{name}</span>
                  </div>
                  <div className={`b${config.enabled ? '' : ' gray'}`}>
                    {config.enabled ? 'ON' : 'OFF'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  };

  // Red/Consola tab — main config panel matching contract
  const renderConfigTab = () => (
    <div style={{ padding: '0 28px 28px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '24px' }}>

        {/* — Consola Avolites — */}
        <div className="g">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold">Consola Avolites</h3>
            <div className={`led${avolitesConfig?.connected ? '' : ' off'}`} />
          </div>
          <div style={{ marginBottom: '16px' }}>
            <label className="t3 text-sm mb-2" style={{ display: 'block' }}>IP Consola</label>
            <input
              type="text"
              placeholder="192.168.1.100"
              value={consoleIp}
              onChange={(e) => setConsoleIp(e.target.value)}
            />
          </div>
          <div style={{ marginBottom: '16px' }}>
            <label className="t3 text-sm mb-2" style={{ display: 'block' }}>Puerto</label>
            <input
              type="number"
              placeholder="4430"
              value={consolePort}
              onChange={(e) => setConsolePort(e.target.value)}
            />
          </div>
          <div className="inset mb-3">
            <div className="flex justify-between">
              <span className="t3 text-sm">Latencia</span>
              <span className="green mono text-sm">{avolitesConfig?.latency_ms || '---'}ms</span>
            </div>
          </div>
          <button className="key w-full" onClick={handleSaveAvolites} disabled={loading}>
            Guardar y Reconectar
          </button>
        </div>

        {/* — Red Local — */}
        <div className="g">
          <h3 className="font-bold mb-4">Red Local</h3>
          <div style={{ marginBottom: '16px' }}>
            <label className="t3 text-sm mb-2" style={{ display: 'block' }}>Interfaz de Red</label>
            <select value={nic} onChange={(e) => setNic(e.target.value)}>
              <option>eth0</option>
              <option>wlan0</option>
            </select>
          </div>
          <div className="inset mb-3">
            <div className="flex justify-between mb-2">
              <span className="t3 text-sm">IP Efectiva</span>
              <span className="mono text-sm">{avolitesConfig?.local_ip || '---'}</span>
            </div>
          </div>
          <button className="key w-full" onClick={handleApplyNic} disabled={loading}>
            {loading ? 'Aplicando...' : 'Aplicar NIC'}
          </button>
        </div>

        {/* — Transporte (read-only, configured via CORE) — */}
        <div className="g">
          <h3 className="font-bold mb-4">Transporte</h3>
          <div className="inset mb-3">
            <div className="flex justify-between mb-2">
              <span className="t3 text-sm">Protocolo</span>
              <span className="mono text-sm">HTTP</span>
            </div>
            <div className="flex justify-between">
              <span className="t3 text-sm">Timeout</span>
              <span className="mono text-sm">{avolitesConfig?.timeout_ms || '5000'}ms</span>
            </div>
          </div>
          <div className="t4 text-sm" style={{ opacity: 0.5 }}>Configurado desde CORE</div>
        </div>

        {/* — Offset de Cues — */}
        <div className="g">
          <h3 className="font-bold mb-4">Offset de Cues</h3>
          <div style={{ marginBottom: '16px' }}>
            <label className="t3 text-sm mb-2" style={{ display: 'block' }}>Offset</label>
            <input
              type="number"
              placeholder="0"
              value={cueOffset}
              onChange={(e) => setCueOffset(Number(e.target.value))}
            />
          </div>
          <div className="inset mb-3">
            <div className="t3 text-sm mb-1">Ejemplo</div>
            <div className="mono text-sm">Cue 1 → Cue {1 + cueOffset}</div>
          </div>
          <button className="key w-full" onClick={handleSaveOffset} disabled={loading}>
            Aplicar Offset
          </button>
        </div>

        {/* — Vision Pro - Cámaras (read-only, configured via Qt UI) — */}
        <div className="g" style={{ gridColumn: '1 / -1' }}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold">Vision Pro - Cámaras</h3>
            <div className="t4 text-sm" style={{ opacity: 0.5 }}>Configurado via Qt UI</div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
            {['HAZE', 'DJ', 'ARTIST'].map(cam => (
              <div key={cam} className="inset">
                <div className="flex items-center justify-between mb-2">
                  <div className="font-semibold">{cam}</div>
                  <div className="b gray">CORE</div>
                </div>
                <div className="t4 text-sm">Cámara gestionada desde el sistema CORE</div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* ═══ HEADER ═══ */}
      <div style={{ padding: '20px 28px' }}>
        <h1 style={{ fontFamily: 'var(--font-title)', fontSize: '24px', fontWeight: 700 }}>Configuration</h1>
      </div>

      {/* ═══ SUCCESS/ERROR BANNER ═══ */}
      {message && (
        <div
          className="p-3"
          style={{
            background: message.type === 'error' ? 'rgba(255,82,82,0.1)' : 'rgba(0,230,118,0.1)',
            borderBottom: `1px solid var(--${message.type === 'error' ? 'red' : 'green'})`,
          }}
        >
          <span className={`${message.type === 'error' ? 'red' : 'green'} font-bold text-sm`}>
            {message.text}
          </span>
        </div>
      )}

      {/* ═══ TABS (matching config_panel_pro.html) ═══ */}
      <div className="tabs">
        {TABS.map(tab => (
          <div
            key={tab}
            className={`tab${activeTab === tab ? ' on' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </div>
        ))}
      </div>

      {/* ═══ CONTENT ═══ */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {activeTab === 'Red/Consola' && renderConfigTab()}
        {activeTab === 'Calendario' && (
          <div style={{ padding: '16px 28px' }}>
            <div className="g">
              <h3 className="font-bold mb-4">Calendario — Configuración</h3>
              <div className="t3 text-sm">
                La configuración del calendario se gestiona desde el panel Calendar.
              </div>
            </div>
          </div>
        )}
        {['Bajada', 'Base Golpe', 'Ataque', 'Brake'].includes(activeTab) && renderModuleTab(activeTab)}
      </div>
    </div>
  );
}
