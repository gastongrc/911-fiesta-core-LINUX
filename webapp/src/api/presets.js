import api from "./axios";

/**
 * List available presets
 * @returns {Promise} List of preset files
 */
export const listPresets = () => api.get("/api/v1/presets");

/**
 * Save current configuration as preset
 * @param {string} filename - Preset filename
 * @param {boolean} overwrite - Allow overwriting existing file
 * @returns {Promise} Save result
 */
export const savePreset = (filename, overwrite = false) =>
  api.post("/api/v1/save", { filename, overwrite });

/**
 * Load preset from file
 * @param {string} filename - Preset filename to load
 * @param {boolean} applyNetwork - Apply network configuration
 * @param {boolean} applyAvolites - Apply Avolites configuration
 * @returns {Promise} Load result
 */
export const loadPreset = (filename, applyNetwork = true, applyAvolites = true) =>
  api.post("/api/v1/load", {
    filename,
    apply_network: applyNetwork,
    apply_avolites: applyAvolites
  });
