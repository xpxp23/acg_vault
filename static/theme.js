/* ==========================================================================
   ACG Vault v3.2.0 — 主题与强调色引擎 + Nintendo Switch Horizon OS 合成微音效引擎
   同时暴露 window.ACGTheme 与 window.AcgTheme（向后兼容）
   ========================================================================== */
(function () {
  'use strict';

  const STORAGE_KEY = 'acg_theme';
  const SFX_STORAGE_KEY = 'acg_ui_sfx';
  const root = document.documentElement;
  const media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  const VALID_MODES = ['auto', 'dark', 'light'];
  const VALID_ACCENTS = ['nintendo', 'indigo', 'emerald', 'amber', 'violet'];

  let initialSfx = true;
  try {
    const rawSfx = localStorage.getItem(SFX_STORAGE_KEY);
    if (rawSfx !== null) {
      initialSfx = rawSfx !== 'false' && rawSfx !== '0';
    }
  } catch (e) { /* ignore */ }

  const state = {
    mode: 'auto',
    resolved: 'dark',
    accent: 'nintendo',
    sfx: initialSfx
  };

  // 读取早期本地缓存，保证首帧与状态一致
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && VALID_MODES.indexOf(parsed.mode) >= 0) state.mode = parsed.mode;
      if (parsed && VALID_ACCENTS.indexOf(parsed.accent) >= 0) state.accent = parsed.accent;
    }
  } catch (e) { /* ignore */ }

  function resolve(mode) {
    if (mode === 'light' || mode === 'dark') return mode;
    return media && media.matches ? 'dark' : 'light';
  }

  function paint() {
    state.resolved = resolve(state.mode);
    root.dataset.theme = state.resolved;
    root.dataset.accent = state.accent;
    root.style.colorScheme = state.resolved;
    document.dispatchEvent(new CustomEvent('acg-theme-changed', {
      detail: { resolved: state.resolved, mode: state.mode, accent: state.accent, sfx: state.sfx }
    }));
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
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode: state.mode, accent: state.accent }));
      localStorage.setItem(SFX_STORAGE_KEY, state.sfx ? 'true' : 'false');
    } catch (e) { /* ignore */ }
  }

  // --------------------------------------------------------------------------
  // Nintendo Switch Horizon OS 零依赖 Web Audio 合成微音效引擎
  // --------------------------------------------------------------------------
  let audioCtx = null;

  function getAudioCtx() {
    if (!state.sfx) return null;
    try {
      const rawSfx = localStorage.getItem(SFX_STORAGE_KEY);
      if (rawSfx === 'false' || rawSfx === '0') return null;
    } catch (e) { /* ignore */ }

    if (!audioCtx) {
      try {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return null;
        audioCtx = new AC();
      } catch (e) {
        return null;
      }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume().catch(function () {});
    }
    return audioCtx;
  }

  function synthTone(ac, freq, startOffset, duration, type, peakGain, endFreq) {
    try {
      const t0 = ac.currentTime + (startOffset || 0);
      const osc = ac.createOscillator();
      const gain = ac.createGain();
      osc.type = type || 'sine';
      osc.frequency.setValueAtTime(freq, t0);
      if (endFreq && endFreq !== freq) {
        osc.frequency.exponentialRampToValueAtTime(Math.max(20, endFreq), t0 + duration);
      }
      gain.gain.setValueAtTime(0.0001, t0);
      gain.gain.linearRampToValueAtTime(Math.max(0.0002, peakGain || 0.08), t0 + Math.min(0.006, duration * 0.25));
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
      osc.connect(gain);
      gain.connect(ac.destination);
      osc.start(t0);
      osc.stop(t0 + duration + 0.015);
    } catch (e) { /* ignore */ }
  }

  function playSfx(type) {
    const ac = getAudioCtx();
    if (!ac) return;
    switch (type || 'focus') {
      case 'focus':
      case 'move':
        // Switch 标志性清脆木琴/棘轮移动微音效
        synthTone(ac, 1180, 0, 0.032, 'triangle', 0.065, 1420);
        synthTone(ac, 2360, 0.003, 0.018, 'sine', 0.025, 2600);
        break;
      case 'select':
      case 'confirm':
        // Switch 双音清亮确认音
        synthTone(ac, 784, 0, 0.055, 'sine', 0.085, 880);
        synthTone(ac, 1174.66, 0.045, 0.095, 'triangle', 0.09, 1318.5);
        break;
      case 'back':
      case 'cancel':
        // Switch 柔和双音下行返回音
        synthTone(ac, 659.25, 0, 0.05, 'sine', 0.075, 587.33);
        synthTone(ac, 440, 0.042, 0.085, 'triangle', 0.065, 392);
        break;
      case 'launch':
        // Switch 启动游戏三和弦上行辉光音效
        synthTone(ac, 587.33, 0, 0.07, 'triangle', 0.08, 659.25);
        synthTone(ac, 880, 0.055, 0.08, 'triangle', 0.085, 987.77);
        synthTone(ac, 1174.66, 0.11, 0.18, 'sine', 0.10, 1567.98);
        break;
      case 'lock':
        // 伴侣窗穿透锁定声
        synthTone(ac, 960, 0, 0.04, 'triangle', 0.07, 720);
        synthTone(ac, 640, 0.038, 0.06, 'sine', 0.075, 540);
        break;
      case 'unlock':
        // 伴侣窗穿透解锁声
        synthTone(ac, 640, 0, 0.04, 'sine', 0.07, 880);
        synthTone(ac, 1280, 0.038, 0.07, 'triangle', 0.08, 1480);
        break;
      case 'tab':
        synthTone(ac, 920, 0, 0.036, 'sine', 0.055, 1080);
        break;
      default:
        synthTone(ac, 1046.5, 0, 0.035, 'triangle', 0.06, 1174.66);
        break;
    }
  }

  function setSfx(enabled) {
    state.sfx = Boolean(enabled);
    persistLocal();
    if (state.sfx) playSfx('select');
  }

  function toggleSfx() {
    setSfx(!state.sfx);
    return state.sfx;
  }

  async function setAccent(name) {
    if (!name || VALID_ACCENTS.indexOf(name) < 0) return;
    state.accent = name;
    paint();
    persistLocal();
    playSfx('select');
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
      if (d && d.success && VALID_MODES.indexOf(d.mode) >= 0) {
        state.mode = d.mode;
      }
      if (d && d.success && VALID_ACCENTS.indexOf(d.accent) >= 0) {
        state.accent = d.accent;
      }
    } catch (e) { /* offline: use local cache */ }
    paint();
    persistLocal();
  }

  async function set(mode) {
    if (VALID_MODES.indexOf(mode) < 0) return;
    state.mode = mode;
    paint();
    persistLocal();
    playSfx('select');
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

  const apiObj = {
    get mode() { return state.mode; },
    get resolved() { return state.resolved; },
    get accent() { return state.accent; },
    get sfx() { return state.sfx; },
    set: set,
    setAccent: setAccent,
    setSfx: setSfx,
    toggleSfx: toggleSfx,
    playSfx: playSfx,
    toggle: toggle,
    load: load,
    refreshButtons: updateButtons
  };

  window.AcgTheme = apiObj;
  window.ACGTheme = apiObj;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
