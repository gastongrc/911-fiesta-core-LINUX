import { create } from 'zustand';
import { getStatus } from '../api/status';
import { getAnalyzers } from '../api/analyzers';
import { getCueStatus } from '../api/cues';

const useSystemStore = create((set, get) => ({
  // Status data
  status: null,
  analyzers: null,
  cues: null,

  // Loading states
  loading: {
    status: false,
    analyzers: false,
    cues: false,
  },

  // Error states
  errors: {
    status: null,
    analyzers: null,
    cues: null,
  },

  // Last fetch timestamp
  lastFetch: {
    status: null,
    analyzers: null,
    cues: null,
  },

  // Polling control
  polling: {
    status: false,
    analyzers: false,
    cues: false,
  },

  pollingIntervals: {
    status: null,
    analyzers: null,
    cues: null,
  },

  // Actions
  fetchStatus: async () => {
    set((state) => ({
      loading: { ...state.loading, status: true },
      errors: { ...state.errors, status: null },
    }));

    try {
      const response = await getStatus();
      set((state) => ({
        status: response.data,
        loading: { ...state.loading, status: false },
        lastFetch: { ...state.lastFetch, status: Date.now() },
      }));
    } catch (error) {
      set((state) => ({
        loading: { ...state.loading, status: false },
        errors: { ...state.errors, status: error.message },
      }));
    }
  },

  fetchAnalyzers: async () => {
    set((state) => ({
      loading: { ...state.loading, analyzers: true },
      errors: { ...state.errors, analyzers: null },
    }));

    try {
      const response = await getAnalyzers();
      set((state) => ({
        analyzers: response.data,
        loading: { ...state.loading, analyzers: false },
        lastFetch: { ...state.lastFetch, analyzers: Date.now() },
      }));
    } catch (error) {
      set((state) => ({
        loading: { ...state.loading, analyzers: false },
        errors: { ...state.errors, analyzers: error.message },
      }));
    }
  },

  fetchCues: async () => {
    set((state) => ({
      loading: { ...state.loading, cues: true },
      errors: { ...state.errors, cues: null },
    }));

    try {
      const response = await getCueStatus();
      set((state) => ({
        cues: response.data,
        loading: { ...state.loading, cues: false },
        lastFetch: { ...state.lastFetch, cues: Date.now() },
      }));
    } catch (error) {
      set((state) => ({
        loading: { ...state.loading, cues: false },
        errors: { ...state.errors, cues: error.message },
      }));
    }
  },

  // Start polling for a data type
  startPolling: (type, interval = 1000) => {
    const { pollingIntervals, fetchStatus, fetchAnalyzers, fetchCues } = get();

    // Stop existing polling if any
    if (pollingIntervals[type]) {
      clearInterval(pollingIntervals[type]);
    }

    // Map type to fetch function
    const fetchFunctions = {
      status: fetchStatus,
      analyzers: fetchAnalyzers,
      cues: fetchCues,
    };

    const fetchFn = fetchFunctions[type];
    if (!fetchFn) return;

    // Initial fetch
    fetchFn();

    // Start interval
    const intervalId = setInterval(fetchFn, interval);

    set((state) => ({
      polling: { ...state.polling, [type]: true },
      pollingIntervals: { ...state.pollingIntervals, [type]: intervalId },
    }));
  },

  // Stop polling for a data type
  stopPolling: (type) => {
    const { pollingIntervals } = get();

    if (pollingIntervals[type]) {
      clearInterval(pollingIntervals[type]);
      set((state) => ({
        polling: { ...state.polling, [type]: false },
        pollingIntervals: { ...state.pollingIntervals, [type]: null },
      }));
    }
  },

  // Stop all polling
  stopAllPolling: () => {
    const { pollingIntervals } = get();
    Object.keys(pollingIntervals).forEach((type) => {
      if (pollingIntervals[type]) {
        clearInterval(pollingIntervals[type]);
      }
    });
    set({
      polling: { status: false, analyzers: false, cues: false },
      pollingIntervals: { status: null, analyzers: null, cues: null },
    });
  },

  // Clear all data
  clearAll: () => {
    get().stopAllPolling();
    set({
      status: null,
      analyzers: null,
      cues: null,
      errors: { status: null, analyzers: null, cues: null },
      lastFetch: { status: null, analyzers: null, cues: null },
    });
  },
}));

export default useSystemStore;
