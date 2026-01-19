import { useEffect, useState } from 'react';
import { listPresets, savePreset, loadPreset } from '../api/presets';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Save, Upload, FileText, Trash2, AlertCircle } from 'lucide-react';

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatDate(dateString) {
  try {
    return new Date(dateString).toLocaleString();
  } catch {
    return dateString;
  }
}

export function Presets() {
  const [presets, setPresets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [showLoadDialog, setShowLoadDialog] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState(null);
  const [newPresetName, setNewPresetName] = useState('');
  const [applyNetwork, setApplyNetwork] = useState(true);
  const [applyAvolites, setApplyAvolites] = useState(true);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    loadPresetsList();
  }, []);

  const showMessage = (text, type = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 3000);
  };

  const loadPresetsList = async () => {
    setLoading(true);
    try {
      const response = await listPresets();
      setPresets(response.data.presets || []);
    } catch (error) {
      showMessage(`Error loading presets: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSavePreset = async () => {
    if (!newPresetName) {
      showMessage('Please enter a preset name', 'error');
      return;
    }

    const filename = newPresetName.endsWith('.json')
      ? newPresetName
      : `${newPresetName}.json`;

    setLoading(true);
    try {
      const response = await savePreset(filename, true);
      if (response.data.success) {
        showMessage(`Preset saved: ${filename}`);
        setShowSaveDialog(false);
        setNewPresetName('');
        loadPresetsList();
      }
    } catch (error) {
      showMessage(`Error saving preset: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleLoadPreset = async () => {
    if (!selectedPreset) return;

    setLoading(true);
    try {
      const response = await loadPreset(selectedPreset.path, applyNetwork, applyAvolites);
      if (response.data.success) {
        showMessage(`Preset loaded: ${selectedPreset.name}`);
        setShowLoadDialog(false);
        setSelectedPreset(null);
      }
    } catch (error) {
      showMessage(`Error loading preset: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

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
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Presets</h2>
          <p className="text-muted-foreground">Save and load system configurations</p>
        </div>
        <Button onClick={() => setShowSaveDialog(true)}>
          <Save className="h-4 w-4 mr-2" />
          Save Preset
        </Button>
      </div>

      {/* Presets List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Available Presets
          </CardTitle>
          <CardDescription>
            {presets.length} preset{presets.length !== 1 ? 's' : ''} found
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && presets.length === 0 ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
              <p className="text-sm text-muted-foreground mt-2">Loading presets...</p>
            </div>
          ) : presets.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-muted-foreground">No presets found</p>
              <p className="text-sm text-muted-foreground mt-1">
                Create your first preset by clicking "Save Preset"
              </p>
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {presets.map((preset) => (
                <Card
                  key={preset.path}
                  className="cursor-pointer hover:border-primary/50 transition-all"
                  onClick={() => {
                    setSelectedPreset(preset);
                    setShowLoadDialog(true);
                  }}
                >
                  <CardContent className="p-4">
                    <div className="space-y-2">
                      <div className="flex items-start justify-between">
                        <p className="font-medium truncate flex-1">{preset.name}</p>
                        <Upload className="h-4 w-4 text-muted-foreground flex-shrink-0 ml-2" />
                      </div>
                      <div className="text-xs text-muted-foreground space-y-1">
                        <p>{formatFileSize(preset.size_bytes)}</p>
                        <p>{formatDate(preset.modified)}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Save Preset Dialog */}
      {showSaveDialog && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <Card className="max-w-md w-full">
            <CardHeader>
              <CardTitle>Save Current Configuration</CardTitle>
              <CardDescription>
                Save all current analyzer thresholds, enabled states, and network configuration
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Preset Name</label>
                <input
                  type="text"
                  className="w-full px-3 py-2 bg-background border border-input rounded-md"
                  placeholder="my-preset.json"
                  value={newPresetName}
                  onChange={(e) => setNewPresetName(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSavePreset()}
                  autoFocus
                />
              </div>
              <div className="flex items-center gap-2 p-3 bg-muted rounded-lg">
                <AlertCircle className="h-4 w-4 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">
                  Existing files will be overwritten
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => {
                    setShowSaveDialog(false);
                    setNewPresetName('');
                  }}
                >
                  Cancel
                </Button>
                <Button
                  className="flex-1"
                  onClick={handleSavePreset}
                  disabled={loading || !newPresetName}
                >
                  <Save className="h-4 w-4 mr-2" />
                  Save
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Load Preset Dialog */}
      {showLoadDialog && selectedPreset && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <Card className="max-w-md w-full">
            <CardHeader>
              <CardTitle>Load Preset</CardTitle>
              <CardDescription>
                {selectedPreset.name}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={applyNetwork}
                    onChange={(e) => setApplyNetwork(e.target.checked)}
                    className="w-4 h-4"
                  />
                  <span className="text-sm">Apply network configuration</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={applyAvolites}
                    onChange={(e) => setApplyAvolites(e.target.checked)}
                    className="w-4 h-4"
                  />
                  <span className="text-sm">Apply Avolites configuration</span>
                </label>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => {
                    setShowLoadDialog(false);
                    setSelectedPreset(null);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  className="flex-1"
                  onClick={handleLoadPreset}
                  disabled={loading}
                >
                  <Upload className="h-4 w-4 mr-2" />
                  Load
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
