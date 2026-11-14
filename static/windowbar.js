/*
 * ACG Vault · Frameless Window Chrome & True Fullscreen Bridge (v3.3.0)
 *
 * 在无边框 WebView2 窗口里提供：
 *   - 统一宿主级真全屏桥接（win_set_fullscreen / /api/window/fullscreen + 浏览器回退）及 F11 全局热键；
 *   - 大屏模式下自动消除 30px 双层顶栏（将拖拽与窗口控制无缝融入大屏 .bs-top 顶栏，全屏时彻底隐藏）；
 *   - 桌面主界面与伴侣窗提供标准可拖拽标题栏与八向边缘缩放热区。
 */
(function () {
  'use strict';
  if (window.AcgWindow) return;

  const TB_H = 30;
  const Z = 2147483000;

  const CSS = `
  :root { --acg-tb-h: ${TB_H}px; }
  html.acg-fullscreen,
  html.acg-bigscreen-immersive {
    --acg-tb-h: 0px !important;
  }
  #acg-titlebar {
    position: fixed; top: 0; left: 0; right: 0; height: 30px;
    z-index: ${Z};
    display: flex; align-items: center; gap: 8px;
    padding-left: 12px;
    background: #05070d;
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
    color: #93a1bd;
    font: 500 12px/1 "Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
    letter-spacing: 0.04em;
    user-select: none;
    box-shadow: 0 1px 8px rgba(0, 0, 0, 0.45);
    transition: transform 0.2s cubic-bezier(0.22, 0.61, 0.36, 1), opacity 0.2s ease;
  }
  html.acg-fullscreen #acg-titlebar,
  html.acg-fullscreen .acg-resize-handle {
    display: none !important;
  }
  html.acg-bigscreen-immersive #acg-titlebar {
    display: none !important;
  }
  .acg-tb-main {
    flex: 1; min-width: 0; height: 100%;
    display: flex; align-items: center; gap: 8px;
    cursor: default;
  }
  .acg-tb-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: linear-gradient(135deg, var(--ax-500, #6366f1), #ec4899);
    box-shadow: 0 0 8px rgba(var(--ax-500-rgb, 99, 102, 241), 0.7);
    flex: 0 0 auto;
  }
  .acg-tb-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .acg-tb-controls { display: flex; align-items: stretch; height: 100%; }
  .acg-tb-btn {
    width: 44px; height: 100%;
    display: inline-grid; place-items: center;
    background: transparent; border: 0; margin: 0;
    color: #9fb0c9; cursor: pointer;
    transition: background 0.15s, color 0.15s;
  }
  .acg-tb-btn:hover { background: rgba(148, 163, 184, 0.18); color: #fff; }
  .acg-tb-btn.close:hover { background: #e11d48; color: #fff; }
  .acg-tb-btn svg { width: 12px; height: 12px; }

  html.acg-frameless body { padding-top: var(--acg-tb-h) !important; }
  html.acg-frameless #app { min-height: calc(100vh - var(--acg-tb-h)) !important; }
  html.acg-frameless #app-header { top: var(--acg-tb-h) !important; }
  html.acg-frameless .bs-shell { height: calc(100vh - var(--acg-tb-h)) !important; }
  html.acg-frameless .bs-top { top: 0 !important; }
  html.acg-frameless .bs-detail,
  html.acg-frameless .bs-sheet-mask,
  html.acg-frameless .bs-reader { top: var(--acg-tb-h) !important; }
  html.acg-frameless #overlay-app { height: calc(100vh - var(--acg-tb-h)) !important; }
  html.acg-frameless .fixed.inset-0 { top: var(--acg-tb-h) !important; }
  `;

  const ICONS = {
    min: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14"/></svg>',
    max: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>',
    restore: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="8" width="12" height="12" rx="2"/><path d="M8 8V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/></svg>',
    fs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>',
    exitFs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>'
  };

  const SKIP = 'button, a, input, select, textarea, .no-drag, [data-no-drag], .acg-tb-controls, .bs-pill, .bs-search-box';

  let cssInjected = false;
  let state = null;
  let mounted = false;
  let allowMax = true;
  let isFullscreenState = false;

  function isDesktop() {
    return !!(window.pywebview && window.pywebview.api && window.pywebview.api.win_get_state);
  }
  function api() { return window.pywebview && window.pywebview.api; }

  function injectCss() {
    if (cssInjected) return;
    cssInjected = true;
    const st = document.createElement('style');
    st.id = 'acg-windowbar-style';
    st.textContent = CSS;
    document.head.appendChild(st);
  }

  function applyFullscreenClass(fs) {
    isFullscreenState = Boolean(fs);
    document.documentElement.classList.toggle('acg-fullscreen', isFullscreenState);
    const fsBtn = document.querySelector('#acg-titlebar .acg-tb-btn.fs');
    if (fsBtn) {
      fsBtn.innerHTML = isFullscreenState ? ICONS.exitFs : ICONS.fs;
      fsBtn.title = isFullscreenState ? '退出全屏 (F11)' : '全屏 (F11)';
    }
    window.dispatchEvent(new CustomEvent('acg-fullscreen-changed', {
      detail: { fullscreen: isFullscreenState }
    }));
  }

  async function toggleFullscreen(forceEnable) {
    if (isDesktop() && api().win_set_fullscreen) {
      try {
        const res = await api().win_set_fullscreen(forceEnable === undefined ? null : Boolean(forceEnable));
        if (res && res.ok) {
          applyFullscreenClass(!!res.fullscreen);
          if (res.maximized !== undefined) updateMaximized(!!res.maximized);
          return !!res.fullscreen;
        }
      } catch (e) { /* fall through */ }
    }

    try {
      const r = await fetch('/api/window/fullscreen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enable: forceEnable === undefined ? null : Boolean(forceEnable) })
      });
      if (r.ok) {
        const d = await r.json();
        if (d && d.ok) {
          applyFullscreenClass(!!d.fullscreen);
          if (d.maximized !== undefined) updateMaximized(!!d.maximized);
          return !!d.fullscreen;
        }
      }
    } catch (e) { /* fall through */ }

    try {
      const wantFs = forceEnable !== undefined ? Boolean(forceEnable) : !document.fullscreenElement;
      if (wantFs && !document.fullscreenElement && document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
        applyFullscreenClass(true);
        return true;
      } else if (!wantFs && document.fullscreenElement && document.exitFullscreen) {
        await document.exitFullscreen();
        applyFullscreenClass(false);
        return false;
      }
    } catch (e) { /* ignore */ }
    return isFullscreenState;
  }

  function buildControls(box, options) {
    const wanted = options.buttons || ['min', 'max', 'close'];
    box.innerHTML = '';

    const make = (cls, title, html, onClick) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'acg-tb-btn ' + cls;
      b.title = title;
      b.innerHTML = html;
      b.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        onClick();
      });
      box.appendChild(b);
      return b;
    };

    const themeBtn = make('theme', '切换日间 / 夜间 (Switch 主题)', '<span data-acg-theme-icon>☀</span>', function () {
      if (window.AcgTheme) window.AcgTheme.toggle();
    });
    themeBtn.style.width = '32px';
    if (window.AcgTheme) window.AcgTheme.refreshButtons();

    if (wanted.indexOf('max') >= 0) {
      make('fs', '全屏切换 (F11)', ICONS.fs, function () { toggleFullscreen(); });
    }
    if (wanted.indexOf('min') >= 0) {
      make('min', '最小化', ICONS.min, function () { if (api()) api().win_minimize(); });
    }
    let maxBtn = null;
    if (wanted.indexOf('max') >= 0) {
      maxBtn = make('max', '最大化', ICONS.max, async function () {
        try {
          const isMax = await api().win_toggle_maximize();
          applyFullscreenClass(false);
          maxBtn.innerHTML = isMax ? ICONS.restore : ICONS.max;
          maxBtn.title = isMax ? '还原' : '最大化';
        } catch (e) { /* ignore */ }
      });
    }
    if (wanted.indexOf('close') >= 0) {
      make('close', options.closeTitle || '关闭', ICONS.close, function () { if (api()) api().win_close(); });
    }
    return maxBtn;
  }

  function bindDrag(el) {
    if (!el || el.dataset.acgDragBound === '1') return;
    el.dataset.acgDragBound = '1';

    el.addEventListener('pointerdown', async function (ev) {
      if (ev.button !== 0 || isFullscreenState) return;
      const t = ev.target;
      if (t && t.closest && t.closest(SKIP)) return;
      if (!isDesktop()) return;

      let st = null;
      try { st = await api().win_get_state(); } catch (e) { return; }
      if (!st || !st.ok || !st.frameless || st.fullscreen) return;

      if (st.maximized) {
        let r = null;
        try { r = await api().win_restore_for_drag(ev.screenX, ev.screenY); } catch (e) { r = null; }
        if (!r || !r.ok) return;
        st = { ok: true, x: r.x, y: r.y, width: r.width, height: r.height, maximized: false };
        updateMaximized(false);
      }

      const startX = ev.screenX;
      const startY = ev.screenY;
      const ox = st.x;
      const oy = st.y;
      let nx = ox;
      let ny = oy;
      let raf = null;
      let moved = false;
      let lastScreenY = startY;

      const flush = function () {
        raf = null;
        api().win_move(Math.round(nx), Math.round(ny));
        if (window.__acgReportUnlockChip) window.__acgReportUnlockChip();
      };
      const onMove = function (e) {
        nx = ox + (e.screenX - startX);
        ny = oy + (e.screenY - startY);
        lastScreenY = e.screenY;
        moved = true;
        if (!raf) raf = requestAnimationFrame(flush);
      };
      const onUp = function () {
        el.removeEventListener('pointermove', onMove);
        el.removeEventListener('pointerup', onUp);
        el.removeEventListener('pointercancel', onUp);
        if (raf) { cancelAnimationFrame(raf); flush(); }
        if (moved) {
          api().win_save_bounds();
          if (window.__acgReportUnlockChip) window.__acgReportUnlockChip();
          if (allowMax && lastScreenY <= 4) {
            setTimeout(function () { api().win_toggle_maximize(); }, 30);
          }
        }
      };

      try { el.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
      el.addEventListener('pointermove', onMove);
      el.addEventListener('pointerup', onUp);
      el.addEventListener('pointercancel', onUp);
    });

    el.addEventListener('dblclick', function (ev) {
      if (!allowMax || !isDesktop()) return;
      const t = ev.target;
      if (t && t.closest && t.closest(SKIP)) return;
      if (isFullscreenState) {
        toggleFullscreen(false);
      } else {
        api().win_toggle_maximize();
      }
    });
  }

  const RESIZE_EDGES = [
    { id: 'n', css: 'top:0;left:10px;right:10px;height:5px;cursor:ns-resize' },
    { id: 's', css: 'bottom:0;left:12px;right:12px;height:7px;cursor:ns-resize' },
    { id: 'w', css: 'top:12px;bottom:12px;left:0;width:7px;cursor:ew-resize' },
    { id: 'e', css: 'top:12px;bottom:12px;right:0;width:7px;cursor:ew-resize' },
    { id: 'nw', css: 'top:0;left:0;width:14px;height:14px;cursor:nwse-resize' },
    { id: 'ne', css: 'top:0;right:0;width:14px;height:14px;cursor:nesw-resize' },
    { id: 'sw', css: 'bottom:0;left:0;width:14px;height:14px;cursor:nesw-resize' },
    { id: 'se', css: 'bottom:0;right:0;width:14px;height:14px;cursor:nwse-resize' }
  ];

  function addResizeHandles(options) {
    if (document.querySelector('.acg-resize-handle')) return;
    const minW = options.minWidth || 1024;
    const minH = options.minHeight || 680;

    RESIZE_EDGES.forEach(function (edge) {
      const el = document.createElement('div');
      el.className = 'acg-resize-handle';
      el.dataset.edge = edge.id;
      el.style.cssText = 'position:fixed;z-index:' + (Z + 1) + ';' + edge.css;
      document.body.appendChild(el);

      el.addEventListener('pointerdown', async function (ev) {
        if (ev.button !== 0 || isFullscreenState) return;
        ev.preventDefault();
        ev.stopPropagation();

        let st = null;
        try { st = await api().win_get_state(); } catch (e) { return; }
        if (!st || !st.ok || !st.frameless || st.maximized || st.fullscreen) return;

        const sx = ev.screenX;
        const sy = ev.screenY;
        const x0 = st.x;
        const y0 = st.y;
        const w0 = st.width;
        const h0 = st.height;
        let nx = x0, ny = y0, nw = w0, nh = h0, raf = null;

        const flush = function () {
          raf = null;
          api().win_set_bounds(Math.round(nx), Math.round(ny), Math.round(nw), Math.round(nh));
          if (window.__acgReportUnlockChip) window.__acgReportUnlockChip();
        };
        const onMove = function (e) {
          const dx = e.screenX - sx;
          const dy = e.screenY - sy;
          nx = x0; ny = y0; nw = w0; nh = h0;
          if (edge.id.indexOf('e') >= 0) nw = w0 + dx;
          if (edge.id.indexOf('s') >= 0) nh = h0 + dy;
          if (edge.id.indexOf('w') >= 0) { nw = w0 - dx; nx = x0 + dx; }
          if (edge.id.indexOf('n') >= 0) { nh = h0 - dy; ny = y0 + dy; }

          if (nw < minW) {
            if (edge.id.indexOf('w') >= 0) nx = x0 + (w0 - minW);
            nw = minW;
          }
          if (nh < minH) {
            if (edge.id.indexOf('n') >= 0) ny = y0 + (h0 - minH);
            nh = minH;
          }
          if (!raf) raf = requestAnimationFrame(flush);
        };
        const onUp = function () {
          el.removeEventListener('pointermove', onMove);
          el.removeEventListener('pointerup', onUp);
          el.removeEventListener('pointercancel', onUp);
          if (raf) { cancelAnimationFrame(raf); flush(); }
          api().win_save_bounds();
          if (window.__acgReportUnlockChip) window.__acgReportUnlockChip();
        };

        try { el.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
        el.addEventListener('pointermove', onMove);
        el.addEventListener('pointerup', onUp);
        el.addEventListener('pointercancel', onUp);
      });
    });
  }

  function bindStateSync() {
    const sync = async function () {
      if (!isDesktop()) return;
      try {
        const st = await api().win_get_state();
        if (st && st.ok) {
          updateMaximized(!!st.maximized);
          applyFullscreenClass(!!st.fullscreen);
        }
      } catch (e) { /* ignore */ }
    };
    window.addEventListener('focus', sync);
    window.addEventListener('blur', sync);
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) sync();
    });
  }

  function buildTitlebar(options) {
    const bar = document.createElement('div');
    bar.id = 'acg-titlebar';

    const main = document.createElement('div');
    main.className = 'acg-tb-main';
    main.innerHTML = '<span class="acg-tb-dot"></span>' +
      '<span class="acg-tb-title"></span>';
    main.querySelector('.acg-tb-title').textContent = options.title || 'ACG Vault v3.3.0';
    bar.appendChild(main);

    const ctrl = document.createElement('div');
    ctrl.className = 'acg-tb-controls';
    bar.appendChild(ctrl);

    document.body.insertBefore(bar, document.body.firstChild);
    const maxBtn = buildControls(ctrl, options);
    bindDrag(bar);

    if (maxBtn && state && state.maximized) {
      maxBtn.innerHTML = ICONS.restore;
      maxBtn.title = '还原';
    }
    return bar;
  }

  window.addEventListener('keydown', function (ev) {
    if (ev.key === 'F11' || ev.code === 'F11') {
      ev.preventDefault();
      ev.stopPropagation();
      toggleFullscreen();
    }
  }, true);

  document.addEventListener('fullscreenchange', function () {
    if (!isDesktop()) {
      applyFullscreenClass(!!document.fullscreenElement);
    }
  });

  function mount(options) {
    const opts = options || {};
    allowMax = (opts.buttons || ['min', 'max', 'close']).indexOf('max') >= 0;
    const isBigScreen = Boolean(opts.immersiveBigScreen || /bigscreen/i.test(window.location.pathname));
    if (isBigScreen) {
      document.documentElement.classList.add('acg-bigscreen-immersive');
    }

    let done = false;
    const init = async function () {
      if (done || !isDesktop()) return;
      done = true;
      try { state = await api().win_get_state(); } catch (e) { return; }
      if (!state || !state.ok || !state.frameless) return;
      mounted = true;
      injectCss();
      document.documentElement.classList.add('acg-frameless');
      buildTitlebar(opts);
      addResizeHandles(opts);
      bindStateSync();
      if (state.fullscreen) applyFullscreenClass(true);

      if (isBigScreen) {
        const attachBsTopDrag = function () {
          const bsTop = document.querySelector('.bs-top');
          if (bsTop) bindDrag(bsTop);
        };
        attachBsTopDrag();
        setTimeout(attachBsTopDrag, 400);
        setTimeout(attachBsTopDrag, 1200);
      }
    };

    if (isDesktop()) { init(); return; }
    window.addEventListener('pywebviewready', init, { once: true });
    let tries = 0;
    const timer = setInterval(function () {
      if (isDesktop()) { clearInterval(timer); init(); }
      else if (++tries > 48) clearInterval(timer);
    }, 250);
  }

  function updateMaximized(isMax) {
    if (!mounted) return;
    const btn = document.querySelector('#acg-titlebar .acg-tb-btn.max');
    if (btn) {
      btn.innerHTML = isMax ? ICONS.restore : ICONS.max;
      btn.title = isMax ? '还原' : '最大化';
    }
  }

  window.AcgWindow = {
    mount: mount,
    isDesktop: isDesktop,
    bindDrag: bindDrag,
    updateMaximized: updateMaximized,
    toggleFullscreen: toggleFullscreen,
    get isFullscreen() { return isFullscreenState; }
  };
})();
