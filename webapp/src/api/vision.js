/**
 * Vision API Client - Phase 7
 */

const API_BASE = '/vision';

export const visionAPI = {
  // Status
  async getStatus() {
    const response = await fetch(`${API_BASE}/status`);
    if (!response.ok) throw new Error('Failed to get status');
    return response.json();
  },

  // Devices
  async listDevices() {
    const response = await fetch(`${API_BASE}/devices`);
    if (!response.ok) throw new Error('Failed to list devices');
    return response.json();
  },

  // Camera Control
  async startCamera(cameraId, config) {
    const response = await fetch(`${API_BASE}/camera/${cameraId}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
    if (!response.ok) throw new Error('Failed to start camera');
    return response.json();
  },

  async stopCamera(cameraId) {
    const response = await fetch(`${API_BASE}/camera/${cameraId}/stop`, {
      method: 'POST'
    });
    if (!response.ok) throw new Error('Failed to stop camera');
    return response.json();
  },

  // Zones
  async getZones(cameraId, sensor = 'people') {
    const response = await fetch(`${API_BASE}/zones/${cameraId}?sensor=${sensor}`);
    if (!response.ok) throw new Error('Failed to get zones');
    return response.json();
  },

  async setZones(cameraId, sensor, zones) {
    const response = await fetch(`${API_BASE}/zones/${cameraId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sensor, zones })
    });
    if (!response.ok) throw new Error('Failed to set zones');
    return response.json();
  },

  // Detections
  async getDetections(cameraId, sensor = 'people') {
    const response = await fetch(`${API_BASE}/detections/${cameraId}?sensor=${sensor}`);
    if (!response.ok) throw new Error('Failed to get detections');
    return response.json();
  },

  // Frame Stream
  getFrameUrl(cameraId, annotate = false, sensor = 'people') {
    return `${API_BASE}/frame/${cameraId}?annotate=${annotate}&sensor=${sensor}&t=${Date.now()}`;
  }
};
