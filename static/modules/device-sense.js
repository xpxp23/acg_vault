/* ==========================================================================
 * ACG Vault v3.4.0 — Global Input Device Auto-Sense Engine (Gamepad <-> KB/Mouse)
 * Seamlessly detects whether the user is actively using a Gamepad (Xbox / DualSense / Switch)
 * or Keyboard & Mouse, updates root data attributes, auto-hides idle mouse cursor in
 * gamepad mode, and provides dynamic prompt keycap labels.
 * ========================================================================== */
(function () {
  'use strict';
  if (window.AcgDeviceSense) return;

  const root = document.documentElement;
  let cursorHideTimer = null;

  const state = {
    activeMethod: 'kb_mouse', // 'gamepad' | 'kb_mouse'
    lastSubDevice: 'mouse',   // 'gamepad' | 'keyboard' | 'mouse'
    padConnected: false,
    padId: '',
    padFamily: 'xbox',        // 'xbox' | 'ps' | 'switch'
    lastPadTimestamp: 0,
    lastMousePos: { x: -1, y: -1 }
  };

  function detectPadFamily(idStr) {
    const s = String(idStr || '');
    if (/pro controller|joy-con|nintendo|057e/i.test(s)) return 'switch';
    if (/dualsense|dualshock|playstation|sony|054c|^wireless controller/i.test(s)) return 'ps';
    return 'xbox';
  }

  function applyRootAttributes() {
    root.dataset.inputMethod = state.activeMethod;
    root.dataset.padFamily = state.padFamily;
    if (state.activeMethod === 'gamepad') {
      root.classList.add('acg-input-gamepad');
      root.classList.remove('acg-input-kbmouse');
    } else {
      root.classList.add('acg-input-kbmouse');
      root.classList.remove('acg-input-gamepad');
      root.classList.remove('acg-cursor-idle');
    }
  }

  function emitChange() {
    applyRootAttributes();
    document.dispatchEvent(new CustomEvent('acg-input-device-changed', {
      detail: {
        activeMethod: state.activeMethod,
        lastSubDevice: state.lastSubDevice,
        padConnected: state.padConnected,
        padId: state.padId,
        padFamily: state.padFamily
      }
    }));
  }

  function scheduleCursorAutoHide() {
    if (cursorHideTimer) clearTimeout(cursorHideTimer);
    root.classList.remove('acg-cursor-idle');
    cursorHideTimer = setTimeout(function () {
      if (state.activeMethod === 'gamepad') {
        root.classList.add('acg-cursor-idle');
      }
    }, 2200);
  }

  function markGamepadActivity(gp) {
    if (gp && gp.id && gp.id !== state.padId) {
      state.padId = gp.id;
      state.padFamily = detectPadFamily(gp.id);
    }
    state.padConnected = true;
    state.lastPadTimestamp = performance.now();
    if (state.activeMethod !== 'gamepad' || state.lastSubDevice !== 'gamepad') {
      state.activeMethod = 'gamepad';
      state.lastSubDevice = 'gamepad';
      root.classList.add('acg-cursor-idle');
      emitChange();
    }
  }

  function markKeyboardActivity(ev) {
    if (ev && (ev.key === 'Shift' || ev.key === 'Control' || ev.key === 'Alt' || ev.key === 'Meta')) return;
    state.lastSubDevice = 'keyboard';
    if (state.activeMethod !== 'kb_mouse') {
      state.activeMethod = 'kb_mouse';
      emitChange();
    }
  }

  function markMouseActivity(ev) {
    // 若刚刚在 350ms 内有手柄按键/摇杆输入，忽略因焦点滚动触发的合成 pointermove
    if (ev && ev.type === 'pointermove' && (performance.now() - state.lastPadTimestamp) < 350) {
      return;
    }
    if (ev && ev.type === 'pointermove') {
      const cx = ev.clientX || 0;
      const cy = ev.clientY || 0;
      if (state.lastMousePos.x < 0) {
        state.lastMousePos.x = cx;
        state.lastMousePos.y = cy;
        return;
      }
      const dx = Math.abs(cx - state.lastMousePos.x);
      const dy = Math.abs(cy - state.lastMousePos.y);
      if (dx < 14 && dy < 14) return;
      state.lastMousePos.x = cx;
      state.lastMousePos.y = cy;
    }
    state.lastSubDevice = 'mouse';
    root.classList.remove('acg-cursor-idle');
    if (state.activeMethod !== 'kb_mouse') {
      state.activeMethod = 'kb_mouse';
      emitChange();
    } else {
      scheduleCursorAutoHide();
    }
  }

  function getPromptLabels(confirmPreference) {
    if (state.activeMethod === 'kb_mouse') {
      return {
        mode: 'kb_mouse',
        family: 'keyboard',
        confirm: 'Enter',
        cancel: 'Esc',
        fav: 'F',
        more: 'R',
        start: 'Tab',
        back: 'Bksp',
        lb: 'Q',
        rb: 'E',
        lt: 'PgUp',
        rt: 'PgDn',
        search: '/'
      };
    }

    const fam = state.padFamily || 'xbox';
    const pref = confirmPreference || 'auto';
    const confirmRight = pref === 'ps' || (pref === 'auto' && (fam === 'ps' || fam === 'switch'));

    if (fam === 'ps') {
      return {
        mode: 'gamepad',
        family: 'ps',
        confirm: confirmRight ? '○' : '✕',
        cancel: confirmRight ? '✕' : '○',
        fav: '□',
        more: '△',
        start: 'OPTIONS',
        back: 'SHARE',
        lb: 'L1',
        rb: 'R1',
        lt: 'L2',
        rt: 'R2',
        search: '△'
      };
    }

    if (fam === 'switch') {
      return {
        mode: 'gamepad',
        family: 'switch',
        confirm: confirmRight ? 'A' : 'B',
        cancel: confirmRight ? 'B' : 'A',
        fav: 'Y',
        more: 'X',
        start: '+',
        back: '-',
        lb: 'L',
        rb: 'R',
        lt: 'ZL',
        rt: 'ZR',
        search: 'X'
      };
    }

    return {
      mode: 'gamepad',
      family: 'xbox',
      confirm: confirmRight ? 'B' : 'A',
      cancel: confirmRight ? 'A' : 'B',
      fav: 'X',
      more: 'Y',
      start: '≡',
      back: '⧉',
      lb: 'LB',
      rb: 'RB',
      lt: 'LT',
      rt: 'RT',
      search: 'Y'
    };
  }

  window.addEventListener('keydown', markKeyboardActivity, { passive: true, capture: true });
  window.addEventListener('pointerdown', markMouseActivity, { passive: true, capture: true });
  window.addEventListener('pointermove', markMouseActivity, { passive: true, capture: true });
  window.addEventListener('wheel', markMouseActivity, { passive: true, capture: true });

  window.addEventListener('gamepadconnected', function (ev) {
    const gp = ev.gamepad;
    state.padConnected = true;
    if (gp && gp.id) {
      state.padId = gp.id;
      state.padFamily = detectPadFamily(gp.id);
    }
    state.activeMethod = 'gamepad';
    state.lastSubDevice = 'gamepad';
    emitChange();
  });

  window.addEventListener('gamepaddisconnected', function () {
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    let anyConn = false;
    for (let i = 0; i < pads.length; i++) {
      if (pads[i] && pads[i].connected) { anyConn = true; break; }
    }
    state.padConnected = anyConn;
    if (!anyConn && state.activeMethod === 'gamepad') {
      state.activeMethod = 'kb_mouse';
      emitChange();
    }
  });

  applyRootAttributes();

  window.AcgDeviceSense = {
    get state() { return state; },
    detectPadFamily: detectPadFamily,
    markGamepadActivity: markGamepadActivity,
    markKeyboardActivity: markKeyboardActivity,
    markMouseActivity: markMouseActivity,
    getPromptLabels: getPromptLabels
  };
})();
