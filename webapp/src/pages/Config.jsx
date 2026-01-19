import { useEffect, useState } from 'react';
import {
  getAvolitesConfig,
  getModulesConfig,
  updateAvolitesConfig,
  updateModulesConfig
} from '../api/config';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Settings, Save, ToggleLeft, ToggleRight } from 'lucide-react';

export function Config() {
  const [avolitesConfig, setAvolitesConfig] = useState(null);
  const [modulesConfig, setModulesConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);

  // Avolites form state
  const [cueOffset, setCueOffset] = useState(0);

  useEffect(() => {
    loadConfigs();
  }, []);

  const showMessage = (text, type = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 3000);
  };

  const loadConfigs = async () => {
    setLoading(true);
    try {
      const [avolitesRes, modulesRes] = await Promise.all([
        getAvolitesConfig(),
        getModulesConfig()
      ]);

      setAvolitesConfig(avolitesRes.data.data);
      setModulesConfig(modulesRes.data.data);

      if (avolitesRes.data.data?.cue_offset !== undefined) {
        setCueOffset(avolitesRes.data.data.cue_offset);
      }
    } catch (error) {
      showMessage(`Error loading config: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateAvolitesOffset = async () => {
    setLoading(true);
    try {
      await updateAvolitesConfig({ cue_offset: cueOffset });
      showMessage('Avolites offset updated successfully');
      loadConfigs();
    } catch (error) {
      showMessage(`Error updating offset: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleModule = async (moduleName, currentEnabled) => {
    setLoading(true);
    try {
      await updateModulesConfig({
        [moduleName]: { enabled: !currentEnabled }
      });
      showMessage(`Module ${moduleName} ${!currentEnabled ? 'enabled' : 'disabled'}`);
      loadConfigs();
    } catch (error) {
      showMessage(`Error toggling module: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const modulesByState = modulesConfig ? Object.entries(modulesConfig).reduce((acc, [name, config]) => {
    const state = config.state || 'unknown';
    if (!acc[state]) acc[state] = [];
    acc[state].push({ name, ...config });
    return acc;
  }, {}) : {};

  return (
    <div className="space-y-6">
      {/* Toast Message */}
      {message && (
        <div className="fixed top-4 right-4 z-50 animate-in slide-in-from-top">
          <Card className={`border-l-4 ${
            message.type === 'success' ? 'border-l-green-500' : 'border-l-red-500'
          }`}>
            <CardContent className="p-4">
              <p className="text-sm">{message.text}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Page Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Configuration</h2>
        <p className="text-muted-foreground">System configuration and module control</p>
      </div>

      {/* Avolites Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Avolites Configuration
          </CardTitle>
          <CardDescription>
            Configure Avolites console settings
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading && !avolitesConfig ? (
            <div className="text-center py-4">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
            </div>
          ) : avolitesConfig ? (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-muted-foreground">Console IP</p>
                  <p className="text-lg font-mono">{avolitesConfig.console_ip || 'Not set'}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-sm font-medium text-muted-foreground">Console Port</p>
                  <p className="text-lg font-mono">{avolitesConfig.console_port || '4430'}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-sm font-medium text-muted-foreground">Local IP</p>
                  <p className="text-lg font-mono">{avolitesConfig.local_ip || 'Not set'}</p>
                </div>
              </div>

              <div className="border-t border-border pt-4 mt-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Cue Offset</label>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      className="flex-1 px-3 py-2 bg-background border border-input rounded-md font-mono"
                      value={cueOffset}
                      onChange={(e) => setCueOffset(Number(e.target.value))}
                    />
                    <Button
                      onClick={handleUpdateAvolitesOffset}
                      disabled={loading}
                    >
                      <Save className="h-4 w-4 mr-2" />
                      Update
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    All cue numbers will be offset by this value
                  </p>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No configuration available</p>
          )}
        </CardContent>
      </Card>

      {/* Modules Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ToggleLeft className="h-5 w-5" />
            Module Control
          </CardTitle>
          <CardDescription>
            Enable or disable individual analyzer modules
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && !modulesConfig ? (
            <div className="text-center py-4">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
            </div>
          ) : Object.keys(modulesByState).length === 0 ? (
            <p className="text-sm text-muted-foreground">No modules found</p>
          ) : (
            <div className="space-y-6">
              {Object.entries(modulesByState).map(([state, modules]) => (
                <div key={state} className="space-y-3">
                  <h3 className="text-sm font-semibold text-primary flex items-center gap-2">
                    {state}
                    <Badge variant="secondary">{modules.length}</Badge>
                  </h3>
                  <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                    {modules.map((module) => (
                      <Card
                        key={module.name}
                        className={`cursor-pointer transition-all ${
                          module.enabled
                            ? 'border-primary bg-primary/5'
                            : 'border-border/50 opacity-60'
                        }`}
                        onClick={() => handleToggleModule(module.name, module.enabled)}
                      >
                        <CardContent className="p-4">
                          <div className="flex items-center justify-between">
                            <div className="flex-1">
                              <p className="font-medium text-sm truncate">{module.name}</p>
                              <p className="text-xs text-muted-foreground">{state}</p>
                            </div>
                            <div className="flex-shrink-0 ml-2">
                              {module.enabled ? (
                                <ToggleRight className="h-6 w-6 text-primary" />
                              ) : (
                                <ToggleLeft className="h-6 w-6 text-muted-foreground" />
                              )}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
