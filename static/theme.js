/* ACG Vault 主题控制（深色 = 夜间，浅色 = Switch 风格日间） */
(function () {
  const STORAGE_KEY = 'acg_theme';
  const root = document.documentElement;
  const media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  const state = { mode: 'auto', resolved: 'dark', accent: 'nintendo' };

  function resolve(mode) {
    if (mode === 'light' || mode === 'dark') return mode;
    return media && media.matches ? 'dark' : 'light';
  }

  function paint() {
    state.resolved = resolve(state.mode);
    root.dataset.theme = state.resolved;
    root.dataset.accent = state.accent;
    root.style.colorScheme = state.resolved;
    document.dispatchEvent(new CustomEvent('acg-theme-changed', { detail: state.resolved }));
    updateButtons();
  }

  function updateButtons() {
    document.querySelectorAll('[data-acg-theme-icon]').forEach(function (el) {
      el.textContent = state.resolved === 'dark' ? '☀' : '🌙';
    });
    document.querySelectorAll('[data-acg-theme-mode]').forEach(function (el) {
      el.dataset.active = el.dataset.acgThemeMode === state.mode ? 'true' : 'false';
    });
  }

  function persistLocal() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode: state.mode, accent: state.accent })); } catch (e) { /* ignore */ }
  }

  async function setAccent(name) {
    if (!name) return;
    state.accent = name;
    paint();
    persistLocal();
    try {
      await fetch('/api/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accent: name })
      });
    } catch (e) { /* ignore */ }
  }

  async function load() {
    try {
      const res = await fetch('/api/theme', { cache: 'no-store' });
      const d = await res.json();
      if (d && d.success && (d.mode === 'auto' || d.mode === 'dark' || d.mode === 'light')) {
        state.mode = d.mode;
      }
      if (d && d.success && d.accent) {
        state.accent = d.accent;
      }
    } catch (e) { /* offline：用本地缓存 */ }
    paint();
    persistLocal();
  }

  async function set(mode) {
    if (['auto', 'dark', 'light'].indexOf(mode) < 0) return;
    state.mode = mode;
    paint();
    persistLocal();
    try {
      await fetch('/api/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: mode })
      });
    } catch (e) { /* ignore */ }
  }

  function toggle() {
    set(state.resolved === 'dark' ? 'light' : 'dark');
  }

  if (media) {
    const onChange = function () { if (state.mode === 'auto') paint(); };
    if (media.addEventListener) media.addEventListener('change', onChange);
    else if (media.addListener) media.addListener(onChange);
  }

  document.addEventListener('acg-theme-request-toggle', toggle);

  // 标题栏按钮（windowbar 注入）通过它切换
  window.AcgTheme = {
    get mode() { return state.mode; },
    get resolved() { return state.resolved; },
    set: set,
    setAccent: setAccent,
    get accent() { return state.accent; },
    toggle: toggle,
    load: load,
    refreshButtons: updateButtons
  };

  // 早脚本已经根据 localStorage 上过色，这里再和服务器对齐一次
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
