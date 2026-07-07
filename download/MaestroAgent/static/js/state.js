// state.js — minimal reactive state. NOT a framework. Just enough to
// stop re-rendering 500-line HTML strings on every API response.
// Loaded BEFORE surfaces, AFTER utils.js.

class Store {
  constructor(initial = {}) {
    this._state = { ...initial };
    this._listeners = new Map();
  }

  get(key) {
    return key ? this._state[key] : this._state;
  }

  set(key, value) {
    const old = this._state[key];
    if (old === value) return; // skip no-ops
    this._state[key] = value;
    (this._listeners.get(key) || []).forEach(fn => fn(value, old));
    (this._listeners.get('*') || []).forEach(fn => fn(key, value, old));
  }

  setAll(updates) {
    Object.keys(updates).forEach(key => this.set(key, updates[key]));
  }

  subscribe(key, fn) {
    if (!this._listeners.has(key)) this._listeners.set(key, []);
    this._listeners.get(key).push(fn);
    return () => {
      const arr = this._listeners.get(key);
      if (arr) arr.splice(arr.indexOf(fn), 1);
    };
  }
}

// Global store — one per app
const appStore = new Store({
  currentSurface: 'today',
  oemState: null,
  briefing: null,
  laws: [],
  recommendations: [],
  autocompleteResults: [],
  dashboard: null,
  timeline: [],
});
