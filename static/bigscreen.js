/*
 * ACG Vault · Big Screen Mode (v3.2.0)
 * 10-foot UI, gamepad-first browsing for the local ACG library.
 *
 * Input model
 *   - Primary : navigator.getGamepads() polled on rAF (works for Xbox + DualShock/DualSense,
 *               which the backend XInput path cannot see).
 *   - Fallback: full keyboard parity (arrows / WASD, Enter, Esc, F, R, Q/E, Tab, Backspace).
 *   - Symbols : auto-detected from gamepad.id, with an explicit confirm-button-position switch.
 */
(function () {
  'use strict';

  const { createApp, ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } = Vue;

  /* ------------------------------------------------------------------ icons */
  const ICONS = {
    play: { d: 'M8 5v14l11-7z', solid: true },
    pause: { d: 'M7 5h4v14H7zM13 5h4v14h-4z', solid: true },
    clock: { d: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7.4V12l3.1 2' },
    heart: { d: 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 1 0-7.8 7.8l8.8 8.8 8.8-8.8a5.5 5.5 0 0 0 0-7.8z' },
    star: { d: 'M12 3.2l2.9 5.8 6.4.9-4.6 4.5 1.1 6.4-5.8-3.1-5.8 3.1 1.1-6.4L2.7 9.9l6.4-.9z' },
    shuffle: { d: 'M16 3h5v5M21 3l-6.5 6.5M16 21h5v-5M21 21l-6.5-6.5M3 4l5.2 5.2M3 20l5.2-5.2M3.2 4.2h3.2M17.6 19.8h3.2' },
    grid: { d: 'M4 4h6.5v6.5H4zM13.5 4H20v6.5h-6.5zM4 13.5h6.5V20H4zM13.5 13.5H20V20h-6.5z' },
    folder: { d: 'M3 7.2A2.2 2.2 0 0 1 5.2 5h3.4l1.9 2h8.3A2.2 2.2 0 0 1 21 9.2v8.6A2.2 2.2 0 0 1 18.8 20H5.2A2.2 2.2 0 0 1 3 17.8z' },
    filter: { d: 'M3 4h18l-7 8.3V19l-4 2v-8.7z' },
    settings: { d: 'M12 15.4a3.4 3.4 0 1 0 0-6.8 3.4 3.4 0 0 0 0 6.8zM19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3.1 14H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.2-2.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 10 3.1V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.7 1.7 0 0 0 20.9 10H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z' },
    gamepad: { d: 'M6.5 8h11a4.5 4.5 0 0 1 4.4 3.6l.5 3a3 3 0 0 1-5.3 2.5L15.6 15H8.4l-1.5 2.1a3 3 0 0 1-5.3-2.5l.5-3A4.5 4.5 0 0 1 6.5 8zM8 11v2.2M6.9 12.1h2.2M15.4 11.4h.01M17.4 13.2h.01' },
    info: { d: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5.2M12 7.8h.01' },
    more: { d: 'M12 12.9a0.9 0.9 0 1 0 0-1.8 0.9 0.9 0 0 0 0 1.8zM19 12.9a0.9 0.9 0 1 0 0-1.8 0.9 0.9 0 0 0 0 1.8zM5 12.9a0.9 0.9 0 1 0 0-1.8 0.9 0.9 0 0 0 0 1.8z' },
    book: { d: 'M4 19.2A2.2 2.2 0 0 1 6.2 17H20M6.2 2H20v20H6.2A2.2 2.2 0 0 1 4 19.8z' },
    monitor: { d: 'M3 5h18v11H3zM8.5 20h7M12 16v4' },
    history: { d: 'M3 12a9 9 0 1 0 2.7-6.4M3 4.5V10h5.5M12 8v4.2l3 1.8' },
    check: { d: 'M20 6.5L9.4 17.2 4 11.8' },
    x: { d: 'M18 6L6 18M6 6l12 12' },
    volume: { d: 'M11 5L6.5 9H3v6h3.5L11 19zM15.4 8.6a4.8 4.8 0 0 1 0 6.8M18 6a8.5 8.5 0 0 1 0 12' }
  };

  /* ---------------------------------------------------------------- helpers */
  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function compileMermaidToVisualHtml(code) {
    const lines = String(code || '').split('\n').map(function (l) { return l.trim(); }).filter(Boolean);
    let subgraphTitle = '剧情分支与路线流程图';
    const nodeLabels = {};
    const edges = [];

    const parseNodeToken = function (tok) {
      if (!tok) return '';
      const m = tok.match(/^([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^)]+)\)|\{([^}]+)\})?$/);
      if (m) {
        const id = m[1];
        const label = (m[2] || m[3] || m[4] || '').trim().replace(/^"|"$/g, '');
        if (label) nodeLabels[id] = label;
        return nodeLabels[id] || id;
      }
      return tok.replace(/[\[\]{}()"]/g, '').trim();
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (/^(flowchart|graph)\b/i.test(line) || line === 'end') continue;
      const subMatch = line.match(/^subgraph\s+(.+)$/i);
      if (subMatch) {
        subgraphTitle = subMatch[1].trim();
        continue;
      }
      const edgeMatch =
        line.match(/^(.+?)\s*--(?:\|\s*([^|]+?)\s*\|)?-->\s*(.+)$/) ||
        line.match(/^(.+?)\s*(?:-->|---|==>)\s*(?:\|\s*([^|]+?)\s*\|\s*)?(.+)$/);
      if (edgeMatch) {
        const leftRaw = edgeMatch[1].trim();
        const cond = (edgeMatch[2] || '').trim();
        const rightRaw = edgeMatch[3].trim();
        const leftParts = leftRaw.split(/\s*&\s*/).map(parseNodeToken);
        const rightParts = rightRaw.split(/\s*&\s*/).map(parseNodeToken);
        edges.push({
          from: leftParts.join(' + '),
          cond: cond,
          to: rightParts.join(' / ')
        });
      }
    }

    if (edges.length === 0) {
      return '<pre><code>' + escapeHtml(code) + '</code></pre>';
    }

    const edgeHtml = edges.map(function (e) {
      const condBadge = e.cond
        ? '<span class="mermaid-edge-label">' + escapeHtml(e.cond) + '</span><span class="mermaid-arrow">→</span>'
        : '<span class="mermaid-arrow">⟶</span>';
      return '<div class="mermaid-edge-row"><span class="mermaid-node-pill">' + escapeHtml(e.from) + '</span>' +
             condBadge +
             '<span class="mermaid-node-pill">' + escapeHtml(e.to) + '</span></div>';
    }).join('');

    return '<div class="mermaid-flow-container"><div class="mermaid-flow-title"><span>🗺️ ' +
           escapeHtml(subgraphTitle) + '</span></div><div class="mermaid-flow-steps">' +
           edgeHtml + '</div></div>';
  }

  function sanitizeReaderHtml(html) {
    if (!html) return '';
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(String(html), 'text/html');
      const forbidden = ['script', 'iframe', 'object', 'embed', 'form', 'style', 'base', 'meta', 'link'];
      doc.querySelectorAll(forbidden.join(',')).forEach(function (el) { el.remove(); });
      doc.body.querySelectorAll('*').forEach(function (el) {
        Array.from(el.attributes).forEach(function (attr) {
          const nameLow = attr.name.toLowerCase();
          const valLow = (attr.value || '').trim().toLowerCase();
          if (nameLow.indexOf('on') === 0 || nameLow === 'srcdoc') {
            el.removeAttribute(attr.name);
          } else if ((nameLow === 'href' || nameLow === 'src' || nameLow === 'action') && /^(javascript|vbscript|data):/i.test(valLow)) {
            el.removeAttribute(attr.name);
          }
        });
      });
      return doc.body.innerHTML;
    } catch (e) {
      return String(html)
        .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
        .replace(/<(iframe|object|embed|form)\b[^>]*>/gi, '')
        .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '');
    }
  }

  function coverFile(g) {
    const u = (g && g.cover_url) || '';
    return u ? String(u).split('/').pop() : '';
  }
  function coverUrl(g) {
    const f = coverFile(g);
    return f ? '/api/covers/' + encodeURIComponent(f) : '';
  }
  function thumbUrl(g) {
    const f = coverFile(g);
    return f ? '/api/covers/thumb/' + encodeURIComponent(f) : '';
  }
  function gameTitle(g) {
    if (!g) return '未命名作品';
    return g.display_title || g.clean_title || g.folder_name || '未命名作品';
  }
  function gameInitials(g) {
    const t = gameTitle(g).replace(/[\s\-_·]+/g, '');
    return (t.slice(0, 2) || 'AC').toUpperCase();
  }
  function fmtHours(sec) {
    const s = Number(sec) || 0;
    if (s < 60) return '未开始';
    if (s < 3600) return Math.round(s / 60) + ' 分钟';
    return (s / 3600).toFixed(1) + ' 小时';
  }
  function parseTags(g) {
    const t = g && g.tags;
    if (!t) return [];
    if (Array.isArray(t)) return t.filter(Boolean).slice(0, 10);
    const s = String(t).trim();
    if (s.charAt(0) === '[') {
      try {
        const arr = JSON.parse(s);
        return Array.isArray(arr) ? arr.filter(Boolean).slice(0, 10) : [];
      } catch (e) { /* fall through */ }
    }
    return s.split(/[,，、;；|]/).map(function (x) { return x.trim(); }).filter(Boolean).slice(0, 10);
  }
  function parseList(v) {
    if (!v) return [];
    if (Array.isArray(v)) return v.filter(Boolean);
    const s = String(v).trim();
    if (!s || s === '[]') return [];
    if (s.charAt(0) === '[') {
      try {
        const arr = JSON.parse(s);
        return Array.isArray(arr) ? arr.filter(Boolean) : [];
      } catch (e) { /* fall through */ }
    }
    return s.split(/[,，、;；|]/).map(function (x) { return x.trim(); }).filter(Boolean);
  }
  function voiceActors(g) {
    return parseList(g && g.voice_actors).join('、');
  }
  function shortEngine(e) {
    if (!e) return 'PC';
    if (e.indexOf('RPG Maker MV/MZ') >= 0) return 'RPGM MV/MZ';
    if (e.indexOf('RPG Maker MZ') >= 0) return 'RMMZ';
    if (e.indexOf('RPG Maker MV') >= 0) return 'RMMV';
    if (e.indexOf('VX Ace') >= 0) return 'VX Ace';
    if (e.indexOf('RPG Maker VX') >= 0) return 'RMVX';
    if (e.indexOf('RPG Maker XP') >= 0) return 'RMXP';
    if (/rpg maker/i.test(e)) return 'RPGM';
    if (/kirikiri|吉里吉里/i.test(e)) return 'KRKR';
    if (/unity/i.test(e)) return 'Unity';
    if (/wolf/i.test(e)) return 'WOLF';
    if (/ren.?py/i.test(e)) return 'RenPy';
    if (/unreal/i.test(e)) return 'UE';
    if (/godot/i.test(e)) return 'Godot';
    return e.slice(0, 8);
  }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  const LS = {
    get: function (k, d) {
      try {
        const v = localStorage.getItem(k);
        return v === null ? d : JSON.parse(v);
      } catch (e) { return d; }
    },
    set: function (k, v) {
      try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ignore */ }
    }
  };

  const STATUS_LABELS = {
    all: '全部', unplayed: '未玩', playing: '游玩中', completed: '已通关',
    backlog: '想玩', dropped: '搁置', finished: '已完结'
  };
  const STATUS_OPTIONS = [
    ['all', '全部'], ['unplayed', '未玩'], ['playing', '游玩中'],
    ['completed', '已通关'], ['backlog', '想玩'], ['dropped', '搁置'], ['finished', '已完结']
  ];
  const MODE_OPTIONS = [['auto', '自动'], ['native', '普通'], ['mtool', 'MTool'], ['le', 'LE 转区']];
  const MODE_LABELS = { auto: '自动', native: '普通', mtool: 'MTool', le: 'LE 转区' };

  /* ======================================================================= */
  const app = createApp({
    setup: function () {
      /* ------------------------------------------------------------- state */
      const loading = ref(true);
      const loadError = ref('');
      const statusText = ref('正在扫描馆藏…');
      const games = ref([]);
      const collections = ref([]);
      const runningMap = ref({});
      const magpie = ref({ installed: false, running: false });
      const magpiePresets = ref({ presets: [], active: '' });
      const themeResolved = ref(document.documentElement.dataset.theme === 'light' ? 'light' : 'dark');

      document.addEventListener('acg-theme-changed', function (e) {
        const resolved = (e && e.detail && typeof e.detail === 'object') ? e.detail.resolved : (e && e.detail);
        themeResolved.value = resolved === 'light' ? 'light' : 'dark';
      });
      const clock = ref('');

      const layout = ref(LS.get('bs_layout', 'rails'));
      const filter = reactive(Object.assign({
        status: 'all', favorite: false, translated: false, engine: 'all', sort: 'recent'
      }, LS.get('bs_filter', {})));
      const settings = reactive(Object.assign({
        bg: 2, sound: true, volume: 0.3, confirmKey: 'auto', hints: true
      }, LS.get('bs_settings', {})));

      const focus = reactive({ row: 0, col: 0 });
      const gridCols = ref(6);
      const scroller = ref(null);

      const detailGame = ref(null);
      const detailStatus = ref(null);
      const detailLoading = ref(false);
      const detailTextEl = ref(null);

      const sheet = ref(null);
      const sheetIndex = ref(0);

      const reader = ref(null);
      const readerBody = ref(null);

      const toast = ref(null);
      let toastTimer = null;

      const launching = ref(null);
      const playSession = ref(null);

      const tonightId = ref(null);
      const modes = reactive(LS.get('bs_launch_modes', {}));

      const isFullscreen = ref(false);

      const pad = reactive({
        connected: false, id: '', family: 'xbox',
        confirm: 'A', cancel: 'B', fav: 'X', more: 'Y', start: 'START', back: 'BACK',
        axes: [0, 0, 0, 0]
      });

      /* -------------------------------------------------------------- sound */
      let audioCtx = null;
      function ensureAudio() {
        if (!settings.sound) return null;
        if (!audioCtx) {
          try {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;
            audioCtx = new AC();
          } catch (e) { return null; }
        }
        if (audioCtx.state === 'suspended') { audioCtx.resume().catch(function () {}); }
        return audioCtx;
      }
      function beep(freq, dur, type, gain, delay) {
        const ac = ensureAudio();
        if (!ac) return;
        const t0 = ac.currentTime + (delay || 0);
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.type = type || 'sine';
        osc.frequency.setValueAtTime(freq, t0);
        g.gain.setValueAtTime(0.0001, t0);
        g.gain.linearRampToValueAtTime(Math.max(0.0001, settings.volume * (gain || 0.16)), t0 + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
        osc.connect(g);
        g.connect(ac.destination);
        osc.start(t0);
        osc.stop(t0 + dur + 0.03);
      }
      const SOUNDS = {
        move: function () { beep(760, 0.045, 'triangle', 0.08); },
        confirm: function () { beep(620, 0.07, 'sine', 0.15); beep(940, 0.1, 'sine', 0.12, 0.06); },
        back: function () { beep(520, 0.07, 'sine', 0.13); beep(360, 0.1, 'sine', 0.1, 0.06); },
        open: function () { beep(880, 0.08, 'sine', 0.11); },
        launch: function () { beep(587, 0.07, 'triangle', 0.12); beep(880, 0.08, 'triangle', 0.12, 0.06); beep(1174, 0.14, 'sine', 0.14, 0.12); },
        error: function () { beep(220, 0.16, 'sawtooth', 0.12); }
      };
      function play(name) {
        if (!settings.sound) return;
        if (window.ACGTheme && window.ACGTheme.playSfx && name !== 'error') {
          const sfxMap = {
            move: 'focus',
            confirm: 'select',
            back: 'back',
            open: 'select',
            launch: 'launch'
          };
          window.ACGTheme.playSfx(sfxMap[name] || 'focus');
          return;
        }
        (SOUNDS[name] || SOUNDS.move)();
      }

      function showToast(text, type, ms) {
        toast.value = { text: text, type: type || '' };
        if (toastTimer) clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { toast.value = null; }, ms || 3000);
      }

      /* --------------------------------------------------------------- data */
      const gameIndex = computed(function () {
        const m = {};
        for (let i = 0; i < games.value.length; i++) m[games.value[i].id] = games.value[i];
        return m;
      });

      const filteredGames = computed(function () {
        let list = games.value.slice();
        if (filter.status !== 'all') list = list.filter(function (g) { return g.play_status === filter.status; });
        if (filter.favorite) list = list.filter(function (g) { return !!g.is_favorite; });
        if (filter.translated) list = list.filter(function (g) { return !!g.has_translation; });
        if (filter.engine !== 'all') list = list.filter(function (g) { return shortEngine(g.engine_type) === filter.engine; });

        if (filter.sort === 'title') {
          list.sort(function (a, b) { return gameTitle(a).localeCompare(gameTitle(b), 'zh-Hans-CN'); });
        } else if (filter.sort === 'playtime') {
          list.sort(function (a, b) { return (b.played_seconds || 0) - (a.played_seconds || 0); });
        } else if (filter.sort === 'rating') {
          list.sort(function (a, b) {
            return (b.user_rating || 0) - (a.user_rating || 0) || gameTitle(a).localeCompare(gameTitle(b), 'zh-Hans-CN');
          });
        } else {
          list.sort(function (a, b) { return String(b.created_at || '').localeCompare(String(a.created_at || '')); });
        }
        return list;
      });

      const engineOptions = computed(function () {
        const seen = {};
        const out = [['all', '全部']];
        games.value.forEach(function (g) {
          const k = shortEngine(g.engine_type);
          if (!seen[k]) { seen[k] = 1; out.push([k, k]); }
        });
        return out.slice(0, 9);
      });

      async function refreshMagpie() {
        try {
          const res = await fetch('/api/magpie/status', { cache: 'no-store' });
          const d = await res.json();
          if (d && d.success && d.data) magpie.value = d.data;
        } catch (e) { /* ignore */ }
        await refreshMagpiePresets();
      }

      async function refreshMagpiePresets() {
        try {
          const res = await fetch('/api/magpie/presets', { cache: 'no-store' });
          const d = await res.json();
          if (d && d.success && d.data) magpiePresets.value = d.data;
        } catch (e) { /* ignore */ }
      }

      function magpiePresetLabel() {
        const list = magpiePresets.value.presets || [];
        const cur = list.find(function (p) { return p.id === magpiePresets.value.active; });
        return cur ? cur.name : '未检测';
      }

      const tonightPool = computed(function () {
        return filteredGames.value.filter(function (g) {
          return g.play_status === 'unplayed' || g.play_status === 'backlog' || g.play_status === 'dropped';
        });
      });
      const tonightGame = computed(function () {
        return gameIndex.value[tonightId.value] || null;
      });

      function rerollTonight(silent) {
        const pool = tonightPool.value;
        if (!pool.length) {
          tonightId.value = null;
          if (!silent) showToast('没有可抽取的作品（筛选里只剩已通关/游玩中的）', 'error');
          return;
        }
        const weights = pool.map(function (g) {
          let w = 1 + (g.user_rating || 0) * 0.9;
          const h = (g.played_seconds || 0) / 3600;
          if (h > 8) w *= 0.45;
          else if (h < 1) w *= 1.7;
          if (g.play_status === 'backlog') w *= 1.25;
          if (g.is_favorite) w *= 1.2;
          return w;
        });
        const total = weights.reduce(function (a, b) { return a + b; }, 0);
        let r = Math.random() * total;
        let pick = pool[pool.length - 1];
        for (let i = 0; i < pool.length; i++) {
          r -= weights[i];
          if (r <= 0) { pick = pool[i]; break; }
        }
        tonightId.value = pick.id;
        if (!silent) { play('confirm'); showToast('换了一个：' + gameTitle(pick), '', 2200); }
      }

      const rows = computed(function () {
        const pool = filteredGames.value;
        if (!pool.length) return [];
        if (layout.value === 'grid') {
          return [{ key: 'all', title: '全部作品', icon: 'grid', type: 'grid', items: pool }];
        }
        const out = [];

        const cont = pool.filter(function (g) { return !!g.last_played_at; })
          .sort(function (a, b) { return String(b.last_played_at).localeCompare(String(a.last_played_at)); })
          .slice(0, 18);
        if (cont.length) out.push({ key: 'continue', title: '继续游玩', icon: 'history', type: 'rail', items: cont });

        if (tonightGame.value) {
          out.push({ key: 'tonight', title: '今晚玩什么', icon: 'shuffle', type: 'rail', items: [tonightGame.value], special: 'tonight' });
        }

        const fav = pool.filter(function (g) { return !!g.is_favorite; }).slice(0, 18);
        if (fav.length) out.push({ key: 'fav', title: '我的收藏', icon: 'heart', type: 'rail', items: fav });

        const recent = pool.slice()
          .sort(function (a, b) { return String(b.created_at || '').localeCompare(String(a.created_at || '')); })
          .slice(0, 18);
        if (recent.length) out.push({ key: 'recent', title: '最近入库', icon: 'clock', type: 'rail', items: recent });

        collections.value.slice(0, 3).forEach(function (c) {
          const items = (c.game_ids || []).map(function (id) { return gameIndex.value[id]; })
            .filter(Boolean).slice(0, 18);
          if (items.length) {
            out.push({ key: 'col-' + c.id, title: c.name, icon: 'folder', type: 'rail', items: items, collection: c });
          }
        });

        out.push({ key: 'all', title: '全部作品', icon: 'grid', type: 'grid', items: pool });
        return out;
      });

      const currentRow = computed(function () { return rows.value[focus.row] || null; });
      const heroGame = computed(function () {
        const r = currentRow.value;
        if (!r || !r.items.length) return null;
        return r.items[clamp(focus.col, 0, r.items.length - 1)] || null;
      });

      const sheetGame = computed(function () { return detailGame.value || heroGame.value || null; });

      /* ----------------------------------------------------------- backdrop */
      const flip = ref(0);
      const bgStyle = reactive([{}, {}]);
      watch(heroGame, function (g) {
        const next = flip.value === 0 ? 1 : 0;
        const url = g ? coverUrl(g) : '';
        bgStyle[next] = url ? { backgroundImage: 'url("' + url + '")' } : {};
        flip.value = next;
      }, { immediate: true });

      const detailBgStyle = computed(function () {
        const g = detailGame.value;
        const url = g ? coverUrl(g) : '';
        return url ? { backgroundImage: 'url("' + url + '")' } : {};
      });

      /* -------------------------------------------------------- data load */
      function tickClock() {
        const d = new Date();
        const pad2 = function (n) { return n < 10 ? '0' + n : '' + n; };
        clock.value = pad2(d.getHours()) + ':' + pad2(d.getMinutes());
      }

      async function refreshGames(silent) {
        const res = await fetch('/api/games?sort_by=title&sort_order=asc', { cache: 'no-store' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        games.value = data.data || [];
        runningMap.value = data.running_games || {};
      }

      async function refreshCollections() {
        try {
          const res = await fetch('/api/collections', { cache: 'no-store' });
          if (!res.ok) return;
          const data = await res.json();
          collections.value = data.collections || [];
        } catch (e) { /* non-fatal */ }
      }

      async function boot() {
        tickClock();
        statusText.value = '正在读取游戏库…';
        try {
          await refreshGames();
          statusText.value = '正在整理合集…';
          await refreshCollections();
          if (!tonightId.value) rerollTonight(true);
          pollRunning();
          refreshMagpie();
          loading.value = false;
          nextTick(function () { scrollFocused(); });
        } catch (e) {
          loadError.value = e && e.message ? e.message : '未知错误';
          statusText.value = '加载失败：' + loadError.value;
          loading.value = false;
        }
      }

      /* ------------------------------------------------------------- focus */
      function updateCols() {
        const w = window.innerWidth;
        gridCols.value = w >= 3000 ? 8 : w >= 2200 ? 7 : w >= 1600 ? 6 : w >= 1200 ? 5 : 4;
      }

      function scrollFocused() {
        nextTick(function () {
          const card = document.querySelector('.card.is-focused');
          if (!card) return;
          const row = currentRow.value;
          const box = scroller.value;

          if (box && focus.row === 0 && row && row.type === 'rail') {
            if (box.scrollTop > 4) box.scrollTo({ top: 0, behavior: 'smooth' });
            const track = card.parentElement;
            if (track) {
              const c = card.getBoundingClientRect();
              const t = track.getBoundingClientRect();
              if (c.left < t.left + 8) track.scrollBy({ left: c.left - t.left - 8, behavior: 'smooth' });
              else if (c.right > t.right - 8) track.scrollBy({ left: c.right - t.right + 8, behavior: 'smooth' });
            }
            return;
          }

          if (card.scrollIntoView) {
            card.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
          }
        });
      }

      function setFocus(ri, ci) {
        if (focus.row === ri && focus.col === ci) return;
        const r = rows.value[ri];
        if (!r) return;
        focus.row = ri;
        focus.col = clamp(ci, 0, Math.max(0, r.items.length - 1));
        play('move');
      }

      function clampFocus() {
        const rs = rows.value;
        if (!rs.length) { focus.row = 0; focus.col = 0; return; }
        focus.row = clamp(focus.row, 0, rs.length - 1);
        focus.col = clamp(focus.col, 0, Math.max(0, rs[focus.row].items.length - 1));
      }

      function moveFocus(dx, dy) {
        const rs = rows.value;
        if (!rs.length) return;
        let r = focus.row;
        let c = focus.col;
        const row = rs[r];
        if (!row) return;

        if (dy) {
          if (row.type === 'grid') {
            const cols = gridCols.value;
            const next = c + dy * cols;
            if (next >= 0 && next < row.items.length) {
              c = next;
            } else {
              r = clamp(r + dy, 0, rs.length - 1);
              c = clamp(c, 0, Math.max(0, rs[r].items.length - 1));
            }
          } else {
            r = clamp(r + dy, 0, rs.length - 1);
            c = clamp(c, 0, Math.max(0, rs[r].items.length - 1));
          }
        }

        if (dx) {
          if (row.type === 'grid') {
            const cols = gridCols.value;
            const start = Math.floor(c / cols) * cols;
            const end = Math.min(start + cols - 1, row.items.length - 1);
            c = clamp(c + dx, start, end);
          } else {
            c = clamp(c + dx, 0, Math.max(0, row.items.length - 1));
          }
        }

        if (r === focus.row && c === focus.col) return;
        focus.row = r;
        focus.col = c;
        play('move');
        scrollFocused();
      }

      function jumpSection(dir) {
        const rs = rows.value;
        if (!rs.length) return;
        focus.row = clamp(focus.row + dir, 0, rs.length - 1);
        focus.col = clamp(focus.col, 0, Math.max(0, rs[focus.row].items.length - 1));
        play('move');
        scrollFocused();
      }

      function pageMove(dir) {
        const row = currentRow.value;
        if (!row) return;
        if (row.type === 'grid') {
          const next = focus.col + dir * gridCols.value * 2;
          if (next >= 0 && next < row.items.length) {
            focus.col = next;
          } else {
            focus.col = clamp(next, 0, row.items.length - 1);
          }
          play('move');
          scrollFocused();
        } else {
          const next = focus.col + dir * 5;
          if (next >= 0 && next < row.items.length) {
            focus.col = next;
            play('move');
            scrollFocused();
          }
        }
      }

      function toggleLayout() {
        layout.value = layout.value === 'grid' ? 'rails' : 'grid';
        LS.set('bs_layout', layout.value);
        focus.row = 0;
        focus.col = 0;
        play('confirm');
        showToast(layout.value === 'grid' ? '已切换为纯网格' : '已切换为轨道 + 网格', '', 1800);
        nextTick(function () { scrollFocused(); });
      }

      /* ------------------------------------------------------------ actions */
      async function updateGame(g, patch) {
        if (!g) return;
        try {
          const res = await fetch('/api/games/' + g.id + '/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(patch)
          });
          const data = await res.json();
          if (!data.success) { showToast(data.detail || '更新失败', 'error'); return; }
          const merged = data.data || {};
          const i = games.value.findIndex(function (x) { return x.id === g.id; });
          if (i >= 0) games.value[i] = Object.assign({}, games.value[i], merged);
          if (detailGame.value && detailGame.value.id === g.id) {
            detailGame.value = Object.assign({}, detailGame.value, merged);
          }
          play('confirm');
        } catch (e) {
          showToast('更新失败：' + e.message, 'error');
        }
      }

      function toggleFavorite(g) {
        if (!g) return;
        updateGame(g, { is_favorite: g.is_favorite ? 0 : 1 });
      }

      function launchModeFor(g) {
        if (!g) return 'auto';
        const m = modes[g.id];
        return m && MODE_LABELS[m] ? m : 'auto';
      }

      function launchButtonLabel(g) {
        const m = launchModeFor(g);
        return m === 'auto' ? '开始游戏' : '开始游戏 · ' + MODE_LABELS[m];
      }

      function orderLaunchModes(g, mode) {
        modes[g.id] = mode;
        LS.set('bs_launch_modes', modes);
      }

      async function launch(g, overrideMode) {
        if (!g || launching.value) return;
        const mode = overrideMode !== undefined ? overrideMode : launchModeFor(g);
        const startedAt = Date.now();
        launching.value = g.id;
        try {
          const res = await fetch('/api/games/' + g.id + '/launch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode === 'auto' ? null : mode, source: 'bigscreen' })
          });
          const data = await res.json();
          if (!data.success) {
            showToast(data.message || '启动失败', 'error', 4200);
            play('error');
            return;
          }
          const magpieEta = data.magpie_auto && data.magpie_auto.scheduled
            ? ' · ' + data.magpie_auto.delay + 's 后 Magpie 全屏'
            : '';
          showToast((data.message || '已启动') + magpieEta, 'success', 3800);
          play('launch');
          detailGame.value = null;
          playSession.value = { id: g.id, title: gameTitle(g), start: startedAt, sawRunning: false, pidSeen: false };
          try { await fetch('/api/window/minimize', { method: 'POST' }); } catch (e) { /* browser mode */ }
        } catch (e) {
          showToast('启动请求失败：' + e.message, 'error');
          play('error');
        } finally {
          launching.value = null;
        }
      }

      async function endSession(neverStarted) {
        const s = playSession.value;
        playSession.value = null;
        try { await fetch('/api/window/restore', { method: 'POST' }); } catch (e) { /* ignore */ }
        if (!s) return;
        if (neverStarted) {
          showToast('没能确认《' + s.title + '》启动，已返回大屏', 'error', 5000);
        } else {
          const mins = Math.max(1, Math.round((Date.now() - s.start) / 60000));
          showToast('《' + s.title + '》本次游玩约 ' + mins + ' 分钟', 'success', 6000);
        }
        try { await refreshGames(true); } catch (e) { /* ignore */ }
      }

      let runningTimer = null;
      let clockTimer = null;

      async function pollRunning() {
        try {
          const res = await fetch('/api/games/running', { cache: 'no-store' });
          if (!res.ok) return;
          const data = await res.json();
          const map = data.running_games || {};
          runningMap.value = map;
          const s = playSession.value;
          if (s) {
            const info = map[s.id];
            if (info) {
              s.sawRunning = true;
              if (info.pid || info.phase === 'running') s.pidSeen = true;
            } else if (s.sawRunning) {
              endSession(!s.pidSeen);
            } else if (Date.now() - s.start > 30000) {
              endSession(true);
            }
          }
        } catch (e) { /* ignore */ }
      }

      async function openDetail(g) {
        if (!g) return;
        detailGame.value = g;
        detailLoading.value = true;
        detailStatus.value = null;
        play('open');
        nextTick(function () { if (detailTextEl.value) detailTextEl.value.scrollTop = 0; });
        try {
          const res = await fetch('/api/games/' + g.id, { cache: 'no-store' });
          if (!res.ok) throw new Error('HTTP ' + res.status);
          const data = await res.json();
          if (data && data.data) detailGame.value = data.data;
          detailStatus.value = data.mtool_status || null;
        } catch (e) {
          showToast('读取详情失败，已显示缓存信息', 'error');
        } finally {
          detailLoading.value = false;
        }
      }

      function closeDetail() {
        if (!detailGame.value) return;
        detailGame.value = null;
        play('back');
        scrollFocused();
      }

      function scrollDetail(dir) {
        const el = detailTextEl.value;
        if (!el) return;
        el.scrollBy({ top: dir * 140, behavior: 'smooth' });
      }

      async function openReader(g) {
        if (!g) return;
        let full = g;
        if (!full.walkthrough_md) {
          try {
            const res = await fetch('/api/games/' + g.id, { cache: 'no-store' });
            const data = await res.json();
            full = (data && data.data) || g;
          } catch (e) { /* ignore */ }
        }
        const rawMd = full.walkthrough_md || '';
        if (!rawMd.trim()) { showToast('该作品还没有生成攻略', 'error'); return; }
        // 先将 ```mermaid 分支路线图代码块编译为可视化卡片 HTML，再经由 marked + sanitizeReaderHtml 安全渲染
        const md = rawMd.replace(/```mermaid\s*\n([\s\S]*?)```/gi, function (_m, code) {
          return compileMermaidToVisualHtml(code);
        });
        let html = escapeHtml(md);
        try {
          if (window.marked) {
            const parsed = window.marked.parse ? window.marked.parse(md) : window.marked(md);
            html = sanitizeReaderHtml(parsed);
          }
        } catch (e) {
          html = sanitizeReaderHtml(md);
        }
        reader.value = {
          title: gameTitle(g),
          meta: rawMd.length > 0 ? Math.round(rawMd.length / 100) / 10 + 'k 字 · 只读' : '只读',
          html: html
        };
        play('open');
        nextTick(function () { if (readerBody.value) readerBody.value.scrollTop = 0; });
      }

      function closeReader() {
        reader.value = null;
        play('back');
      }

      function exitHome() {
        play('back');
        window.location.href = '/';
      }

      function toggleFullscreen() {
        if (document.fullscreenElement) {
          document.exitFullscreen().catch(function () {});
        } else if (document.documentElement.requestFullscreen) {
          document.documentElement.requestFullscreen().catch(function () {
            showToast('当前窗口不允许全屏，可用 F11', 'error');
          });
        }
      }

      /* -------------------------------------------------------------- sheet */
      const sheetTitle = computed(function () {
        if (sheet.value === 'filter') return '筛选与布局';
        if (sheet.value === 'settings') return '大屏设置';
        return sheetGame.value ? '操作 · ' + gameTitle(sheetGame.value) : '操作';
      });

      const sheetRows = computed(function () {
        if (sheet.value === 'filter') {
          return [
            { key: 'f_status', label: '游玩状态', value: filter.status, options: STATUS_OPTIONS },
            { key: 'f_fav', label: '只看收藏', value: !!filter.favorite, options: [[false, '关'], [true, '开']] },
            { key: 'f_trans', label: '只看汉化', value: !!filter.translated, options: [[false, '关'], [true, '开']] },
            { key: 'f_engine', label: '引擎', value: filter.engine, options: engineOptions.value },
            { key: 'f_sort', label: '排序', value: filter.sort, options: [['recent', '最近入库'], ['title', '标题'], ['playtime', '游玩时长'], ['rating', '评分']] },
            { key: 'f_layout', label: '布局', value: layout.value, options: [['rails', '轨道 + 网格'], ['grid', '纯网格']] }
          ];
        }
        if (sheet.value === 'settings') {
          return [
            { key: 's_bg', label: '背景强度', value: settings.bg, options: [[0, '关闭'], [1, '柔和'], [2, '强烈']] },
            { key: 's_sound', label: '操作音效', value: !!settings.sound, options: [[true, '开'], [false, '关']] },
            { key: 's_volume', label: '音量', value: Number(settings.volume), options: [[0.15, '低'], [0.3, '中'], [0.5, '高']] },
            { key: 's_confirm', label: '确认键位置', value: settings.confirmKey, options: [['auto', '自动识别'], ['xbox', '下方键确认'], ['ps', '右侧键确认']] },
            { key: 's_hints', label: '底部提示条', value: !!settings.hints, options: [[true, '显示'], [false, '隐藏']] }
          ];
        }
        const g = sheetGame.value;
        if (!g) return [];
        const statusOpts = STATUS_OPTIONS.filter(function (o) { return o[0] !== 'all'; });
        return [
          { key: 'a_launch', label: '启动方式', value: launchModeFor(g), options: MODE_OPTIONS },
          { key: 'a_fav', label: '收藏', value: !!g.is_favorite, options: [[true, '已收藏'], [false, '未收藏']] },
          { key: 'a_rating', label: '评分', value: g.user_rating || 0, options: [[0, '未评'], [1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5']] },
          { key: 'a_status', label: '状态', value: g.play_status, options: statusOpts },
          {
            key: 'a_magpie',
            label: 'Magpie 全屏',
            action: true,
            disabled: !magpie.value.installed || !runningMap.value[g.id],
            hint: !magpie.value.installed
              ? '未检测到 Magpie（设置里可指定路径）'
              : (runningMap.value[g.id] ? '按 A 让 Magpie 接管全屏' : '游戏启动后才能全屏')
          },
          {
            key: 'a_theme',
            label: '界面主题：' + (themeResolved.value === 'light' ? '日间 (Switch)' : '夜间'),
            action: true,
            hint: '按 A 在 夜间 / 日间 (Switch) 之间切换'
          },
          {
            key: 'a_magpie_preset',
            label: 'Magpie 预设：' + magpiePresetLabel(),
            action: true,
            disabled: !magpie.value.installed || !(magpiePresets.value.presets || []).length,
            hint: '按 A 切到下一个缩放预设（会重启 Magpie）'
          },
          { key: 'a_folder', label: '打开游戏目录', action: true, hint: '按 A 在资源管理器中打开' },
          { key: 'a_guide', label: '全结局攻略', action: true, hint: g.has_walkthrough ? '按 A 阅读' : '该作品暂无攻略', disabled: !g.has_walkthrough }
        ];
      });

      function setSheet(name) {
        sheet.value = name;
        sheetIndex.value = 0;
      }

      function openSheet(name) {
        setSheet(name || 'filter');
        play('open');
      }

      function closeSheet() {
        sheet.value = null;
        play('back');
      }

      function setRowValue(row, val) {
        const g = sheetGame.value;
        switch (row.key) {
          case 'f_status': filter.status = val; LS.set('bs_filter', filter); break;
          case 'f_fav': filter.favorite = !!val; LS.set('bs_filter', filter); break;
          case 'f_trans': filter.translated = !!val; LS.set('bs_filter', filter); break;
          case 'f_engine': filter.engine = val; LS.set('bs_filter', filter); break;
          case 'f_sort': filter.sort = val; LS.set('bs_filter', filter); break;
          case 'f_layout':
            layout.value = val;
            LS.set('bs_layout', val);
            focus.row = 0; focus.col = 0;
            break;
          case 's_bg': settings.bg = Number(val); LS.set('bs_settings', settings); break;
          case 's_sound':
            settings.sound = !!val;
            LS.set('bs_settings', settings);
            if (window.ACGTheme && window.ACGTheme.setSfx) window.ACGTheme.setSfx(!!val);
            break;
          case 's_volume': settings.volume = Number(val); LS.set('bs_settings', settings); break;
          case 's_confirm':
            settings.confirmKey = val;
            LS.set('bs_settings', settings);
            computeLabels();
            break;
          case 's_hints': settings.hints = !!val; LS.set('bs_settings', settings); break;
          case 'a_launch':
            if (!g) return;
            orderLaunchModes(g, val);
            break;
          case 'a_fav': if (g) updateGame(g, { is_favorite: val ? 1 : 0 }); break;
          case 'a_rating': if (g) updateGame(g, { user_rating: Number(val) }); break;
          case 'a_status': if (g) updateGame(g, { play_status: val }); break;
          default: break;
        }
        play('move');
      }

      async function runRowAction(row) {
        const g = sheetGame.value;
        if (!g || row.disabled) return;
        if (row.key === 'a_magpie') {
          try {
            const res = await fetch('/api/magpie/scale', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ game_id: g.id })
            });
            const d = await res.json();
            showToast(d.message || (d.scaled ? '已用 Magpie 全屏' : 'Magpie 未能缩放'), d.scaled ? 'success' : 'error', 4200);
            refreshMagpie();
          } catch (e) {
            showToast('Magpie 请求失败', 'error');
          }
          return;
        }
        if (row.key === 'a_theme') {
          if (window.AcgTheme) {
            const next = themeResolved.value === 'light' ? 'dark' : 'light';
            await window.AcgTheme.set(next);
            showToast(next === 'light' ? '☀ 已切换到 Switch 日间模式' : '🌙 已切换到夜间模式', 'success', 2000);
          }
          return;
        }
        if (row.key === 'a_magpie_preset') {
          const list = (magpiePresets.value.presets || []).filter(function (p) { return p.available; });
          if (!list.length) { showToast('没有可用的 Magpie 预设', 'error'); return; }
          const idx = list.findIndex(function (p) { return p.id === magpiePresets.value.active; });
          const next = list[(idx + 1) % list.length];
          showToast('切换到：' + next.name, 'info', 1400);
          try {
            const res = await fetch('/api/magpie/preset', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ id: next.id })
            });
            const d = await res.json();
            showToast(d.message || (d.success ? '已切换' : '切换失败'), d.success ? 'success' : 'error', 3600);
            refreshMagpiePresets();
          } catch (e) {
            showToast('切换预设失败', 'error');
          }
          return;
        }
        if (row.key === 'a_folder') {
          try {
            await fetch('/api/games/' + g.id + '/open_folder', { method: 'POST' });
            showToast('已在资源管理器中打开', '', 2000);
          } catch (e) { showToast('打开失败', 'error'); }
        } else if (row.key === 'a_guide') {
          closeSheet();
          openReader(g);
        }
      }

      function cycleRow(row, dir) {
        if (row.action || row.disabled) return;
        const opts = row.options || [];
        if (!opts.length) return;
        let i = -1;
        for (let k = 0; k < opts.length; k++) {
          if (opts[k][0] === row.value) { i = k; break; }
        }
        const next = (i + dir + opts.length) % opts.length;
        setRowValue(row, opts[next][0]);
      }

      function activateRow(row, i) {
        sheetIndex.value = i;
        if (row.action) runRowAction(row);
        else cycleRow(row, 1);
      }

      function handleSheet(name) {
        const rowsNow = sheetRows.value;
        if (!rowsNow.length) { if (name === 'cancel') closeSheet(); return; }
        const row = rowsNow[clamp(sheetIndex.value, 0, rowsNow.length - 1)];
        if (name === 'up') { sheetIndex.value = clamp(sheetIndex.value - 1, 0, rowsNow.length - 1); play('move'); }
        else if (name === 'down') { sheetIndex.value = clamp(sheetIndex.value + 1, 0, rowsNow.length - 1); play('move'); }
        else if (name === 'left') cycleRow(row, -1);
        else if (name === 'right') cycleRow(row, 1);
        else if (name === 'confirm') { if (row.action) runRowAction(row); else cycleRow(row, 1); }
        else if (name === 'cancel' || name === 'start') closeSheet();
        else if (name === 'lb') {
          const tabs = ['filter', 'actions', 'settings'];
          const i = tabs.indexOf(sheet.value);
          setSheet(tabs[(i - 1 + tabs.length) % tabs.length]);
          play('move');
        } else if (name === 'rb') {
          const tabs = ['filter', 'actions', 'settings'];
          const i = tabs.indexOf(sheet.value);
          setSheet(tabs[(i + 1) % tabs.length]);
          play('move');
        }
      }

      function handleReader(name) {
        const el = readerBody.value;
        if (name === 'cancel' || name === 'back') { closeReader(); return; }
        if (!el) return;
        if (name === 'up') el.scrollBy({ top: -180, behavior: 'smooth' });
        else if (name === 'down') el.scrollBy({ top: 180, behavior: 'smooth' });
        else if (name === 'lt') el.scrollBy({ top: -el.clientHeight * 0.8, behavior: 'smooth' });
        else if (name === 'rt') el.scrollBy({ top: el.clientHeight * 0.8, behavior: 'smooth' });
      }

      function handleDetail(name) {
        const g = detailGame.value;
        if (name === 'confirm') { launch(g); return; }
        if (name === 'longconfirm') { launch(g, 'native'); return; }
        if (name === 'cancel') { closeDetail(); return; }
        if (name === 'fav') { toggleFavorite(g); return; }
        if (name === 'more') { openSheet('actions'); return; }
        if (name === 'start') { openSheet('filter'); return; }
        if (name === 'up') { scrollDetail(-1); return; }
        if (name === 'down') { scrollDetail(1); return; }
        if (name === 'lt') { scrollDetail(-4); return; }
        if (name === 'rt') { scrollDetail(4); return; }
      }

      function handleBrowse(name) {
        const row = currentRow.value;
        if (name === 'confirm') { if (heroGame.value) openDetail(heroGame.value); return; }
        if (name === 'cancel') { exitHome(); return; }
        if (name === 'fav') {
          if (row && row.special === 'tonight') { rerollTonight(false); return; }
          toggleFavorite(heroGame.value);
          return;
        }
        if (name === 'more') { openSheet('actions'); return; }
        if (name === 'start') { openSheet('filter'); return; }
        if (name === 'back') { toggleLayout(); return; }
        if (name === 'lb') { jumpSection(-1); return; }
        if (name === 'rb') { jumpSection(1); return; }
        if (name === 'lt') { pageMove(-1); return; }
        if (name === 'rt') { pageMove(1); return; }
        if (name === 'up') { moveFocus(0, -1); return; }
        if (name === 'down') { moveFocus(0, 1); return; }
        if (name === 'left') { moveFocus(-1, 0); return; }
        if (name === 'right') { moveFocus(1, 0); return; }
      }

      function onAction(name) {
        if (sheet.value) { handleSheet(name); return; }
        if (reader.value) { handleReader(name); return; }
        if (detailGame.value) { handleDetail(name); return; }
        handleBrowse(name);
      }

      /* -------------------------------------------------------------- hints */
      const hints = computed(function () {
        const k = { confirm: pad.confirm, cancel: pad.cancel, fav: pad.fav, more: pad.more, start: pad.start };
        if (sheet.value) {
          return [
            { key: '↑↓', label: '选择', tone: '' },
            { key: '←→', label: '调整', tone: '' },
            { key: k.confirm, label: '确认', tone: 'a', act: 'confirm' },
            { key: k.cancel, label: '关闭', tone: 'b', act: 'cancel' },
            { key: 'LB/RB', label: '切换面板', tone: '' }
          ];
        }
        if (reader.value) {
          return [
            { key: '↑↓', label: '滚动', tone: '' },
            { key: 'LT/RT', label: '翻页', tone: '' },
            { key: k.cancel, label: '返回', tone: 'b', act: 'cancel' }
          ];
        }
        if (detailGame.value) {
          return [
            { key: k.confirm, label: '开始游戏', tone: 'a', act: 'confirm' },
            { key: k.more, label: '更多操作', tone: 'y', act: 'more' },
            { key: k.fav, label: '收藏', tone: 'x', act: 'fav' },
            { key: '长按 ' + k.confirm, label: '普通模式启动', tone: 'a', act: 'longconfirm' },
            { key: k.cancel, label: '返回', tone: 'b', act: 'cancel' }
          ];
        }
        return [
          { key: k.confirm, label: '详情', tone: 'a', act: 'confirm' },
          { key: k.fav, label: currentRow.value && currentRow.value.special === 'tonight' ? '换一个' : '收藏', tone: 'x', act: 'fav' },
          { key: k.more, label: '操作', tone: 'y', act: 'more' },
          { key: 'LB/RB', label: '切换栏目', tone: '' },
          { key: k.start, label: '筛选', tone: '', act: 'start' },
          { key: 'Back', label: '切换布局', tone: '', act: 'back' },
          { key: k.cancel, label: '退出大屏', tone: 'b', act: 'cancel' }
        ];
      });

      function clickHint(h) {
        if (!h || !h.act) return;
        onAction(h.act);
      }

      /* ------------------------------------------------------------- gamepad */
      function computeLabels() {
        const family = pad.family;
        const confirmRight = settings.confirmKey === 'ps' ||
          (settings.confirmKey === 'auto' && family === 'ps');
        if (family === 'ps') {
          pad.confirm = confirmRight ? '○' : '✕';
          pad.cancel = confirmRight ? '✕' : '○';
          pad.fav = '□';
          pad.more = '△';
          pad.start = 'OPTIONS';
          pad.back = 'SHARE';
        } else {
          pad.confirm = 'A';
          pad.cancel = 'B';
          pad.fav = 'X';
          pad.more = 'Y';
          pad.start = '≡';
          pad.back = '⧉';
        }
      }
      computeLabels();

      const PAD_BUTTONS = {
        4: 'lb', 5: 'rb', 6: 'lt', 7: 'rt', 8: 'back', 9: 'start', 10: 'lthumb', 11: 'rthumb'
      };

      function logicalFromButton(i) {
        const confirmRight = settings.confirmKey === 'ps' ||
          (settings.confirmKey === 'auto' && pad.family === 'ps');
        if (i === 0) return confirmRight ? 'cancel' : 'confirm';
        if (i === 1) return confirmRight ? 'confirm' : 'cancel';
        if (i === 2) return 'fav';
        if (i === 3) return 'more';
        return PAD_BUTTONS[i] || null;
      }

      const held = { buttons: {} };
      const dirHold = { act: null, nextAt: 0 };
      const scrollHold = { nextAt: 0 };
      let confirmTimer = null;
      let confirmLong = false;
      let confirmArmed = false;
      let cancelTimer = null;
      let cancelHinted = false;
      let padRaf = null;
      let padSeen = false;

      function startConfirmHold() {
        confirmArmed = true;
        confirmLong = false;
        if (confirmTimer) clearTimeout(confirmTimer);
        confirmTimer = setTimeout(function () {
          confirmLong = true;
          onAction('longconfirm');
        }, 680);
      }

      function endConfirmHold() {
        if (!confirmArmed) return;
        confirmArmed = false;
        if (confirmTimer) { clearTimeout(confirmTimer); confirmTimer = null; }
        if (!confirmLong) onAction('confirm');
        confirmLong = false;
      }

      function overlayOpen() { return !!(sheet.value || reader.value || detailGame.value); }

      function handleButton(i, pressed) {
        const prev = !!held.buttons[i];
        if (pressed === prev) return;
        held.buttons[i] = pressed;
        const act = logicalFromButton(i);
        if (!act) return;

        if (!pressed) {
          if (act === 'confirm' && confirmArmed) endConfirmHold();
          if (act === 'cancel' && cancelTimer) {
            clearTimeout(cancelTimer);
            cancelTimer = null;
            if (!cancelHinted) {
              cancelHinted = true;
              showToast('长按 ' + pad.cancel + ' 退出大屏模式', '', 2600);
            }
          }
          return;
        }

        if (act === 'confirm') {
          if (detailGame.value) { startConfirmHold(); return; }
          onAction(act);
          return;
        }
        if (act === 'cancel' && !overlayOpen()) {
          if (cancelTimer) clearTimeout(cancelTimer);
          cancelTimer = setTimeout(function () {
            cancelTimer = null;
            exitHome();
          }, 950);
          return;
        }
        onAction(act);
      }

      function dpadDirection(gp) {
        const b = gp.buttons;
        if (b[12] && b[12].pressed) return 'up';
        if (b[13] && b[13].pressed) return 'down';
        if (b[14] && b[14].pressed) return 'left';
        if (b[15] && b[15].pressed) return 'right';
        const dz = 0.55;
        const ax = gp.axes[0] || 0;
        const ay = gp.axes[1] || 0;
        if (Math.abs(ax) < dz && Math.abs(ay) < dz) return null;
        if (Math.abs(ax) > Math.abs(ay)) return ax > 0 ? 'right' : 'left';
        return ay > 0 ? 'down' : 'up';
      }

      function detectFamily(id) {
        const s = String(id || '');
        if (/dualsense|dualshock|playstation|sony|054c/i.test(s)) return 'ps';
        if (/^wireless controller/i.test(s)) return 'ps';
        return 'xbox';
      }

      function pollPad() {
        padRaf = requestAnimationFrame(pollPad);
        if (!navigator.getGamepads) return;
        const pads = navigator.getGamepads();
        let gp = null;
        for (let i = 0; i < pads.length; i++) {
          if (pads[i] && pads[i].connected) { gp = pads[i]; break; }
        }
        if (!gp) {
          if (pad.connected) {
            pad.connected = false;
            padSeen = false;
            held.buttons = {};
            dirHold.act = null;
          }
          return;
        }
        if (!pad.connected) {
          pad.connected = true;
          padSeen = true;
          pad.id = gp.id || '';
          pad.family = detectFamily(gp.id);
          computeLabels();
          showToast((pad.family === 'ps' ? 'PlayStation' : 'Xbox') + ' 手柄已连接', 'success', 2400);
        }

        for (let i = 0; i < gp.buttons.length; i++) {
          const b = gp.buttons[i];
          handleButton(i, !!(b && (b.pressed || b.value > 0.5)));
        }

        const dir = dpadDirection(gp);
        const now = performance.now();
        if (dir !== dirHold.act) {
          dirHold.act = dir;
          if (dir) { onAction(dir); dirHold.nextAt = now + 380; }
        } else if (dir && now >= dirHold.nextAt) {
          onAction(dir);
          dirHold.nextAt = now + 95;
        }

        if (detailGame.value || reader.value) {
          const ry = gp.axes[3] || 0;
          if (Math.abs(ry) > 0.42) {
            if (now >= scrollHold.nextAt) {
              const el = reader.value ? readerBody.value : detailTextEl.value;
              if (el) el.scrollBy({ top: (ry > 0 ? 1 : -1) * 110, behavior: 'auto' });
              scrollHold.nextAt = now + 70;
            }
          } else {
            scrollHold.nextAt = 0;
          }
        }

        pad.axes = [
          Math.round((gp.axes[0] || 0) * 100) / 100,
          Math.round((gp.axes[1] || 0) * 100) / 100,
          Math.round((gp.axes[2] || 0) * 100) / 100,
          Math.round((gp.axes[3] || 0) * 100) / 100
        ];
      }

      /* ------------------------------------------------------------- keyboard */
      const KEYMAP = {
        ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
        KeyW: 'up', KeyS: 'down', KeyA: 'left', KeyD: 'right',
        Enter: 'confirm', NumpadEnter: 'confirm', Space: 'confirm',
        Escape: 'cancel', Backspace: 'cancel',
        KeyF: 'fav', KeyR: 'more', KeyQ: 'lb', KeyE: 'rb',
        PageUp: 'lt', PageDown: 'rt', Tab: 'start'
      };

      function onKeyDown(e) {
        if (e.altKey && e.code === 'KeyB') { e.preventDefault(); exitHome(); return; }
        const act = KEYMAP[e.code];
        if (!act) return;
        if (e.repeat && act !== 'up' && act !== 'down' && act !== 'left' && act !== 'right') return;
        e.preventDefault();
        onAction(act);
      }

      function onResize() {
        updateCols();
      }

      function onFullscreenChange() {
        isFullscreen.value = !!document.fullscreenElement;
      }

      function onGamepadConnected(ev) {
        pad.connected = true;
        pad.id = (ev.gamepad && ev.gamepad.id) || '';
        pad.family = detectFamily(pad.id);
        computeLabels();
      }

      /* --------------------------------------------------------------- boot */
      watch(function () { return rows.value.map(function (r) { return r.items.length; }).join('|'); }, clampFocus);
      watch(function () { return filter.engine + '|' + filter.status + '|' + filter.sort + '|' + filter.favorite + '|' + filter.translated; }, function () {
        clampFocus();
        if (!tonightGame.value) rerollTonight(true);
      });
      watch(function () { return settings.confirmKey + '|' + pad.family; }, computeLabels);

      onMounted(function () {
        if (window.AcgWindow) {
          window.AcgWindow.mount({
            title: 'ACG Vault v3.2.0 · 大屏模式（手柄 / 方向键可用）',
            minWidth: 900,
            minHeight: 600
          });
        }
        updateCols();
        window.addEventListener('resize', onResize);
        window.addEventListener('keydown', onKeyDown);
        document.addEventListener('fullscreenchange', onFullscreenChange);
        window.addEventListener('gamepadconnected', onGamepadConnected);
        runningTimer = setInterval(pollRunning, 2500);
        clockTimer = setInterval(tickClock, 15000);
        padRaf = requestAnimationFrame(pollPad);
        boot();
      });

      onBeforeUnmount(function () {
        window.removeEventListener('resize', onResize);
        window.removeEventListener('keydown', onKeyDown);
        document.removeEventListener('fullscreenchange', onFullscreenChange);
        window.removeEventListener('gamepadconnected', onGamepadConnected);
        if (runningTimer) clearInterval(runningTimer);
        if (clockTimer) clearInterval(clockTimer);
        if (padRaf) cancelAnimationFrame(padRaf);
      });

      /* ------------------------------------------------------------- expose */
      return {
        loading: loading,
        loadError: loadError,
        statusText: statusText,
        games: games,
        clock: clock,
        layout: layout,
        filter: filter,
        settings: settings,
        focus: focus,
        gridCols: gridCols,
        scroller: scroller,
        rows: rows,
        heroGame: heroGame,
        currentRow: currentRow,
        runningMap: runningMap,
        magpie: magpie,
        magpiePresets: magpiePresets,
        themeResolved: themeResolved,
        flip: flip,
        bgStyle: bgStyle,
        detailGame: detailGame,
        detailStatus: detailStatus,
        detailLoading: detailLoading,
        detailTextEl: detailTextEl,
        detailBgStyle: detailBgStyle,
        sheet: sheet,
        sheetIndex: sheetIndex,
        sheetTitle: sheetTitle,
        sheetRows: sheetRows,
        reader: reader,
        readerBody: readerBody,
        toast: toast,
        launching: launching,
        pad: pad,
        isFullscreen: isFullscreen,
        hints: hints,
        clickHint: clickHint,
        coverUrl: coverUrl,
        thumbUrl: thumbUrl,
        gameTitle: gameTitle,
        gameInitials: gameInitials,
        fmtHours: fmtHours,
        parseTags: parseTags,
        voiceActors: voiceActors,
        shortEngine: shortEngine,
        statusLabel: function (s) { return STATUS_LABELS[s] || s || '未玩'; },
        setFocus: setFocus,
        activateCard: function (ri, ci) { setFocus(ri, ci); openDetail(rows.value[ri] && rows.value[ri].items[ci]); },
        openDetail: openDetail,
        closeDetail: closeDetail,
        openSheet: openSheet,
        closeSheet: closeSheet,
        setSheet: setSheet,
        setRowValue: setRowValue,
        activateRow: activateRow,
        launch: launch,
        launchButtonLabel: launchButtonLabel,
        toggleFavorite: toggleFavorite,
        openReader: openReader,
        closeReader: closeReader,
        exitHome: exitHome,
        toggleFullscreen: toggleFullscreen
      };
    }
  });

  /* -------------------------------------------------------------- components */
  app.component('bs-icon', {
    props: { name: { type: String, default: 'info' }, size: { type: [Number, String], default: 16 } },
    computed: {
      icon: function () { return ICONS[this.name] || ICONS.info; },
      solid: function () { return !!(ICONS[this.name] && ICONS[this.name].solid); }
    },
    template:
      '<svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path :d="icon.d" :fill="solid ? \'currentColor\' : \'none\'" :stroke="solid ? \'none\' : \'currentColor\'"></path>' +
      '</svg>'
  });

  app.component('game-card', {
    props: {
      game: { type: Object, required: true },
      focused: { type: Boolean, default: false },
      running: { type: Boolean, default: false },
      tonight: { type: Boolean, default: false },
      favLabel: { type: String, default: 'X' }
    },
    setup: function (props) {
      const thumb = computed(function () { return thumbUrl(props.game); });
      const title = computed(function () { return gameTitle(props.game); });
      const initials = computed(function () { return gameInitials(props.game); });
      const sub = computed(function () {
        const s = props.game.played_seconds || 0;
        return s > 0 ? '已玩 ' + fmtHours(s) : '尚未开始';
      });
      return { thumb: thumb, title: title, initials: initials, sub: sub };
    },
    template:
      '<article class="card" :class="{ \'is-focused\': focused, \'focused\': focused, \'tonight-card\': tonight }" ' +
      '@mouseenter="$emit(\'focus\')" @click="$emit(\'activate\')">' +
        '<div class="card-cover">' +
          '<img v-if="thumb" :src="thumb" :alt="title" loading="lazy" draggable="false">' +
          '<div v-else class="hero-fallback">{{ initials }}</div>' +
          '<div class="card-badges" v-if="!tonight">' +
            '<span class="badge-mini live" v-if="running">● 运行中</span>' +
            '<span class="badge-mini" v-if="game.has_translation">汉化</span>' +
            '<span class="badge-mini gold" v-if="game.user_rating">★ {{ game.user_rating }}</span>' +
          '</div>' +
          '<div class="card-play" v-if="!tonight"><span><bs-icon name="play"></bs-icon></span></div>' +
          '<template v-if="tonight">' +
            '<div class="tonight-eyebrow">今晚玩什么</div>' +
            '<div class="tonight-body">' +
              '<div class="tonight-title">{{ title }}</div>' +
              '<div class="tonight-sub">{{ sub }} · {{ favLabel }} 换一个</div>' +
            '</div>' +
          '</template>' +
        '</div>' +
        '<div class="card-caption" v-if="!tonight">{{ title }}</div>' +
      '</article>'
  });

  app.mount('#app');
})();
