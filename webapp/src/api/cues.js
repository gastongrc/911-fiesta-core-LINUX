import api from "./axios";

/**
 * Get cue status (active cues and CueEngine status)
 * @returns {Promise} Cue status
 */
export const getCueStatus = () => api.get("/api/v1/cues");

/**
 * Fire a cue manually
 * @param {number} cueNumber - Cue number (1-300)
 * @param {boolean} force - If true, uses fire_cue_manual (bypass READY)
 * @returns {Promise} Fire result
 */
export const fireCue = (cueNumber, force = false) =>
  api.post("/api/v1/cues/fire", { cue_number: cueNumber, force });

/**
 * Kill cues
 * @param {number[]} cueNumbers - Array of cue numbers to kill
 * @param {boolean} force - If true, uses kill_cue_manual
 * @returns {Promise} Kill result
 */
export const killCues = (cueNumbers, force = false) =>
  api.delete("/api/v1/cues/kill", { data: { cue_numbers: cueNumbers, force } });
