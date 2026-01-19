import api from "./axios";

/**
 * Get complete system status
 * @returns {Promise} System status including state, energy, audio, avolites, cue_engine
 */
export const getStatus = () => api.get("/api/v1/status");

/**
 * Get health check
 * @returns {Promise} Health status
 */
export const getHealth = () => api.get("/health");
