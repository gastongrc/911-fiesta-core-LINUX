import { create } from 'zustand';
import { getStatus } from '../api/status';

const useSystemStore = create((set, get) => ({
  status: null,
  loading: { status: false },
  errors: { status: null },
  lastFetch: { status: null },
  polling: { status: false },
  pollingIntervals: { status: null },

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

  startPolling: (type, interval = 1000) => {
    const { pollingIntervals, fetchStatus } = get();
    if (pollingIntervals[type]) clearInterval(pollingIntervals[type]);
    const fetchFunctions = { status: fetchStatus };
    const fetchFn = fetchFunctions[type];
    if (!fetchFn) return;
    fetchFn();
    const intervalId = setInterval(fetchFn, interval);
    set((state) => ({
      polling: { ...state.polling, [type]: true },
      pollingIntervals: { ...state.pollingIntervals, [type]: intervalId },
    }));
  },

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

  stopAllPolling: () => {
    const { pollingIntervals } = get();
    Object.keys(pollingIntervals).forEach((type) => {
      if (pollingIntervals[type]) clearInterval(pollingIntervals[type]);
    });
    set({ polling: { status: false }, pollingIntervals: { status: null } });
  },

  clearAll: () => {
    get().stopAllPolling();
    set({ status: null, errors: { status: null }, lastFetch: { status: null } });
  },
}));

export default useSystemStore;
