import api from "./axios";

/**
 * Get configuration for a specific section
 * @param {string} section - Section name (audio, avolites, state, modules)
 * @returns {Promise} Configuration data
 */
export const getConfig = (section) => api.get(`/api/v1/config/${section}`);

/**
 * Update configuration for a specific section
 * @param {string} section - Section name (avolites, modules)
 * @param {object} data - Configuration data to update
 * @returns {Promise} Update result
 */
export const updateConfig = (section, data) =>
  api.post(`/api/v1/config/${section}`, { data });

/**
 * Get audio configuration
 * @returns {Promise} Audio config
 */
export const getAudioConfig = () => getConfig("audio");

/**
 * Get Avolites configuration
 * @returns {Promise} Avolites config
 */
export const getAvolitesConfig = () => getConfig("avolites");

/**
 * Get StateManager configuration
 * @returns {Promise} State config
 */
export const getStateConfig = () => getConfig("state");

/**
 * Get modules configuration (enabled states)
 * @returns {Promise} Modules config
 */
export const getModulesConfig = () => getConfig("modules");

/**
 * Update Avolites configuration
 * @param {object} data - Avolites config data
 * @returns {Promise} Update result
 */
export const updateAvolitesConfig = (data) => updateConfig("avolites", data);

/**
 * Update modules configuration (enabled states)
 * @param {object} data - Modules config data
 * @returns {Promise} Update result
 */
export const updateModulesConfig = (data) => updateConfig("modules", data);
