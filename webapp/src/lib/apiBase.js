/**
 * API Base URL - Resolución dinámica para dev/prod/LAN
 *
 * Prioridad:
 * 1. VITE_API_BASE env var (si existe)
 * 2. En dev con proxy: /api/v1 (relativo)
 * 3. En prod/LAN: http://{hostname}:8000/api/v1
 */

export function getApiBase() {
  // 1. Variable de entorno tiene prioridad
  if (import.meta.env.VITE_API_BASE) {
    return import.meta.env.VITE_API_BASE;
  }

  // 2. En desarrollo con proxy de Vite, usar URL relativa
  // El proxy redirige /api -> http://127.0.0.1:8000
  if (import.meta.env.DEV) {
    return '/api/v1';
  }

  // 3. En producción o acceso LAN directo, construir URL absoluta
  const host = window.location.hostname;
  return `http://${host}:8000/api/v1`;
}

/**
 * Obtener URL base para SSE (siempre absoluta en producción)
 * SSE necesita URL absoluta cuando no hay proxy
 */
export function getSSEUrl(endpoint) {
  const base = getApiBase();
  // Si es relativo (dev con proxy), construir URL completa para EventSource
  if (base.startsWith('/')) {
    return `${window.location.origin}${base}${endpoint}`;
  }
  return `${base}${endpoint}`;
}

/**
 * Fetch wrapper con base URL
 */
export async function apiFetch(endpoint, options = {}) {
  const url = `${getApiBase()}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  return response;
}

/**
 * POST helper
 */
export async function apiPost(endpoint, data) {
  return apiFetch(endpoint, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
