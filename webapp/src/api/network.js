import api from "./axios";

/**
 * List available network interfaces
 * @returns {Promise} Network interfaces list
 */
export const getNetworkInterfaces = () => api.get("/api/v1/network/interfaces");

/**
 * Set local network interface
 * @param {string} interfaceName - Interface name
 * @returns {Promise} Set interface result
 */
export const setNetworkInterface = (interfaceName) =>
  api.post("/api/v1/network/interface", { interface_name: interfaceName });

/**
 * Set Avolites console target IP and port
 * @param {string} consoleIp - Console IP address
 * @param {number} consolePort - Console port (default 4430)
 * @returns {Promise} Set console result
 */
export const setConsoleTarget = (consoleIp, consolePort = 4430) =>
  api.post("/api/v1/network/console", { console_ip: consoleIp, console_port: consolePort });

/**
 * Ping a host
 * @param {string} host - Host to ping (IP or hostname)
 * @returns {Promise} Ping result with latency
 */
export const pingHost = (host) =>
  api.post("/api/v1/network/ping", { host });
