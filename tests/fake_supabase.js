// Minimal in-memory stand-in for supabase-js v2, persisted in localStorage so page reloads keep state.
(function () {
  const LS = "fake_sb";
  const load = () => { try { return JSON.parse(localStorage.getItem(LS)); } catch (e) { return null; } };
  const state = load() || { session: null, tables: { items: [], price_history: [], alerts: [], profiles: [] }, seq: 1 };
  const save = () => localStorage.setItem(LS, JSON.stringify(state));
  const listeners = [];
  const auth = {
    signInWithOAuth: async () => ({ data: {}, error: null }),
    signInWithOtp: async ({ email }) => { state.lastOtp = email; save(); return { data: {}, error: null }; },
    signOut: async () => { state.session = null; save(); listeners.forEach((cb) => cb("SIGNED_OUT", null)); return { error: null }; },
    onAuthStateChange: (cb) => { listeners.push(cb); setTimeout(() => cb("INITIAL_SESSION", state.session), 0);
      return { data: { subscription: { unsubscribe() {} } } }; },
  };
  window.__fake = {
    state, save,
    signIn(email) { state.session = { user: { id: "11111111-1111-1111-1111-111111111111", email } }; save(); listeners.forEach((cb) => cb("SIGNED_IN", state.session)); },
    cron(fn) { fn(state.tables, state); save(); },
  };
  function builder(table) {
    const q = { op: "select", filters: [], patch: null, rows: null, single: false, selectAfter: false };
    const b = {
      select() { if (q.op === "insert") q.selectAfter = true; else q.op = "select"; return b; },
      insert(rows) { q.op = "insert"; q.rows = Array.isArray(rows) ? rows : [rows]; return b; },
      update(patch) { q.op = "update"; q.patch = patch; return b; },
      delete() { q.op = "delete"; return b; },
      eq(k, v) { q.filters.push([k, v]); return b; },
      order() { return b; }, limit() { return b; },
      maybeSingle() { q.single = true; return b; },
      then(res, rej) { return Promise.resolve().then(run).then(res, rej); },
    };
    const match = (r) => q.filters.every(([k, v]) => String(r[k]) === String(v));
    function run() {
      const T = state.tables; const t = T[table];
      let data = null, error = null;
      if (q.op === "select") {
        data = t.filter(match).map((r) => ({ ...r }));
        if (table === "items") data.forEach((it) => {
          it.price_history = T.price_history.filter((h) => h.item_id === it.id).sort((a, b) => b.checked_at.localeCompare(a.checked_at));
          it.alerts = T.alerts.filter((a) => a.item_id === it.id).sort((a, b) => b.sent_at.localeCompare(a.sent_at)); });
        data.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
        if (q.single) data = data[0] || null;
      } else if (q.op === "insert") {
        const out = q.rows.map((r) => { const row = { fail_count: 0, last_error: null, sizes_json: null, name: null, image_url: null, store: null, currency: null, ...r };
          if (table !== "profiles") row.id = state.seq++; t.push(row); return row; });
        if (table === "profiles" && q.rows.some((r) => t.filter((x) => x.user_id === r.user_id).length > 1)) { t.pop(); error = { message: "duplicate key value violates unique constraint" }; }
        if (table === "items" && t.length > (state.cap || 100)) { t.pop(); error = { message: "new row violates row-level security policy for table \"items\"" }; }
        data = q.selectAfter && !error ? (q.single ? out[0] : out) : null;
      } else if (q.op === "update") { t.filter(match).forEach((r) => Object.assign(r, q.patch)); }
      else if (q.op === "delete") {
        const gone = t.filter(match); T[table] = t.filter((r) => !match(r));
        if (table === "items") { const ids = new Set(gone.map((r) => r.id)); T.price_history = T.price_history.filter((h) => !ids.has(h.item_id)); T.alerts = T.alerts.filter((a) => !ids.has(a.item_id)); }
      }
      save();
      return { data, error };
    }
    return b;
  }
  window.supabase = { createClient: () => ({ auth, from: builder }) };
})();
