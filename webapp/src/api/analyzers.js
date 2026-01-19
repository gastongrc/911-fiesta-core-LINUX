import api from "./axios";

/**
 * Get all analyzers organized by state
 * @returns {Promise} Analyzers by state, energy detector, and stats
 */
export const getAnalyzers = () => api.get("/api/v1/analyzers");

/**
 * Get only active analyzers
 * @returns {Promise} Active analyzers list
 */
export const getActiveAnalyzers = () => api.get("/api/v1/analyzers/active");

/**
 * Get only matching analyzers
 * @returns {Promise} Matching analyzers list
 */
export const getMatchingAnalyzers = () => api.get("/api/v1/analyzers/matching");
