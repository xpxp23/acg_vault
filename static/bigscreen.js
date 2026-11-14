/*
 * ACG Vault · Big Screen Mode (v3.4.0)
 * 10-foot UI, gamepad & keyboard/mouse auto-sensing for the local ACG library.
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
    search: { d: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.35-4.35' },
    settings: { d: 'M12 15.4a3.4 3.4 0 1 0 0-6.8 3.4 3.4 0 0 0 0 6.8zM19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3.1 14H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.2-2.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 10 3.1V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.7 1.7 0 0 0 20.9 10H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z' },
    gamepad: { d: 'M6.5 8h11a4.5 4.5 0 0 1 4.4 3.6l.5 3a3 3 0 0 1-5.3 2.5L15.6 15H8.4l-1.5 2.1a3 3 0 0 1-5.3-2.5l.5-3A4.5 4.5 0 0 1 6.5 8zM8 11v2.2M6.9 12.1h2.2M15.4 11.4h.01M17.4 13.2h.01' },
    info: { d: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5.2M12 7.8h.01' },
    more: { d: 'M12 12.9a0.9 0.9 0 1 0 0-1.8 0.9 0.9 0 0 0 0 1.8zM19 12.9a0.9 0.9 0 1 0 0-1.8 0.9 0.9 0 0 0 0 1.8zM5 12.9a0.9 0.9 0 1 0 0-1.8 0.9 0.9 0 0 0 0 1.8z' },
    book: { d: 'M4 19.2A2.2 2.2 0 0 1 6.2 17H20M6.2 2H20v20H6.2A2.2 2.2 0 0 1 4 19.8z' },
    monitor: { d: 'M3 5h18v11H3zM8.5 20h7M12 16v4' },
    history: { d: 'M3 12a9 9 0 1 0 2.7-6.4M3 4.5V10h5.5M12 8v4.2l3 1.8' },
    check: { d: 'M20 6.5L9.4 17.2 4 11.8' },
    x: { d: 'M18 6L6 18M6 6l12 12' },
    volume: { d: 'M11 5L6.5 9H3v6h3.5L11 19zM15.4 8.6a4.8 4.8 0 0 1 0 6.8M18 6a8.5 8.5 0 0 1 0 12' },
    maximize: { d: 'M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3' },
    minimize: { d: 'M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3' }
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
  function isTranslated(g) {
    return Boolean(g && (g.is_translated || g.has_translation));
  }
  function gameTitle(g) {
    if (!g) return '未命名作品';
    return g.display_title || g.clean_title || g.folder_name || '未命名作品';
  }
  function gameInitials(g) {
    const t = gameTitle(g).replace(/[\s\-_·•:：/\\]+/g, '');
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

      const searchQuery = ref('');
      const searchFocused = ref(false);
      const searchInputEl = ref(null);
      const activeAlpha = ref('ALL');
      const mainScrollTop = ref(0);

      const layout = ref(LS.get('bs_layout', 'rails'));
      const filter = reactive(Object.assign({
        status: 'all', favorite: false, translated: false, engine: 'all', sort: 'recent'
      }, LS.get('bs_filter', {})));
      const settings = reactive(Object.assign({
        bg: 2, sound: true, volume: 0.3, confirmKey: 'auto', cardConfirm: 'detail',
        coverFit: 'smart', parallax: true, hints: true
      }, LS.get('bs_settings', {})));

      // 横版封面 (DLsite 4:3 / 16:9) 自动识别映射表：gameId -> boolean
      const landscapeMap = reactive({});
      function onCoverImgLoad(ev, g) {
        if (!ev || !ev.target || !g || !g.id) return;
        const nw = Number(ev.target.naturalWidth) || 0;
        const nh = Number(ev.target.naturalHeight) || 0;
        if (nw > 0 && nh > 0) {
          landscapeMap[g.id] = (nw / nh) > 1.04;
        }
      }
      function isSmartLandscape(g) {
        if (!g || !g.id) return false;
        const mode = settings.coverFit || 'smart';
        if (mode === 'cover') return false;
        if (mode === 'contain') return true;
        if (landscapeMap[g.id] !== undefined) return !!landscapeMap[g.id];
        return false;
      }

      // 引擎高刷与无损瘦身状态感知缓存：gameId -> statusObj
      const optStatusMap = reactive({});
      const optBusyMap = reactive({});
      const optTargetFpsMap = reactive({});

      async function refreshOptimizerStatus(gid, force) {
        if (!gid) return null;
        if (!force && optStatusMap[gid] && !optStatusMap[gid]._loading) {
          return optStatusMap[gid];
        }
        try {
          const res = await fetch('/api/games/' + gid + '/optimizer/status', { cache: 'no-store' });
          if (res.ok) {
            const d = await res.json();
            if (d && d.success) {
              optStatusMap[gid] = d;
              if (!optTargetFpsMap[gid]) {
                optTargetFpsMap[gid] = (d.current_target_fps && d.current_target_fps >= 60) ? d.current_target_fps : 120;
              }
              return d;
            }
          }
        } catch (e) { /* ignore */ }
        return null;
      }

      // 大屏云存档冲突快速仲裁与快照时光机状态 (Big Screen Save Time-Machine)
      const saveTime = reactive({
        gameId: null,
        loading: false,
        resolving: false,
        conflictState: 'synced',
        bannerText: '正在检查本地与云端存档状态…',
        summaryText: '',
        strategy: 'slot_merge',
        targetSnapshot: '',
        leftCard: null,
        rightCard: null,
        diffSlots: [],
        snapshots: []
      });

      async function loadSaveTimeMachine(g, autoSwitchOnConflict) {
        if (!g || !g.id) return null;
        saveTime.gameId = g.id;
        saveTime.loading = true;
        try {
          const res = await fetch('/api/games/' + g.id + '/saves/conflicts', { cache: 'no-store' });
          const d = await res.json();
          if (!d || !d.success) {
            saveTime.bannerText = (d && d.message) || '读取存档状态失败';
            saveTime.loading = false;
            return null;
          }
          saveTime.conflictState = d.conflict_state || 'synced';
          saveTime.bannerText = d.conflict_description || '本地存档与最新快照状态已同步';

          const localBaks = d.local_backups || [];
          const remoteBaks = d.remote_backups || [];
          const mergedSnaps = [];
          const seenSnap = {};
          remoteBaks.forEach(function (rb) {
            if (!seenSnap[rb.filename]) {
              seenSnap[rb.filename] = true;
              mergedSnaps.push({
                filename: rb.filename,
                sourceId: rb.source_id || ('webdav:' + rb.filename),
                label: '☁️ 云端 ' + rb.filename.replace(/^game_\d+_/, ''),
                sub: (rb.size_kb || 0) + ' KB · ' + (rb.is_downloaded ? '已缓存到本地' : '仅在 WebDAV 云端'),
                location: 'webdav'
              });
            }
          });
          localBaks.forEach(function (lb) {
            if (!seenSnap[lb.filename]) {
              seenSnap[lb.filename] = true;
              mergedSnaps.push({
                filename: lb.filename,
                sourceId: lb.source_id || ('backup:' + lb.filename),
                label: '📦 本地 ' + lb.filename.replace(/^game_\d+_/, ''),
                sub: (lb.created_at || '') + ' · ' + (lb.size_kb || 0) + ' KB',
                location: 'local'
              });
            }
          });
          saveTime.snapshots = mergedSnaps.slice(0, 12);

          const diff = d.diff;
          if (diff && diff.success) {
            const ls = diff.left_source || {};
            const rs = diff.right_source || {};
            saveTime.targetSnapshot = rs.id || (mergedSnaps[0] ? mergedSnaps[0].sourceId : '');

            let leftTele = null;
            let rightTele = null;
            const slotsArr = diff.slots || [];
            for (let i = 0; i < slotsArr.length; i++) {
              const sl = slotsArr[i];
              if (!leftTele && sl.left && (sl.left.lead_actor || sl.left.gold !== null)) {
                const la = sl.left.lead_actor;
                leftTele = {
                  actor: la ? ((la.name || '主角') + ' Lv.' + (la.level || 1)) : '',
                  gold: sl.left.gold,
                  cgCount: sl.left.cg_switches_on || 0
                };
              }
              if (!rightTele && sl.right && (sl.right.lead_actor || sl.right.gold !== null)) {
                const ra = sl.right.lead_actor;
                rightTele = {
                  actor: ra ? ((ra.name || '主角') + ' Lv.' + (ra.level || 1)) : '',
                  gold: sl.right.gold,
                  cgCount: sl.right.cg_switches_on || 0
                };
              }
            }

            saveTime.leftCard = {
              title: '本地实时存档 (Local)',
              updatedAt: ls.updated_at || '无记录',
              slotCount: ls.slot_count || 0,
              sizeKb: ls.total_size_kb || 0,
              telemetry: leftTele
            };
            saveTime.rightCard = {
              title: rs.label || '云端/最新快照',
              updatedAt: rs.updated_at || '无记录',
              slotCount: rs.slot_count || 0,
              sizeKb: rs.total_size_kb || 0,
              telemetry: rightTele
            };

            const sm = diff.summary || {};
            saveTime.summaryText = '差异槽位：修改 ' + (sm.modified_count || 0) + ' · 本地独有 ' + (sm.only_left_count || 0) + ' · 云端独有 ' + (sm.only_right_count || 0);

            saveTime.diffSlots = slotsArr.filter(function (s) { return s.status !== 'identical'; }).map(function (s) {
              const parts = [];
              if (s.status === 'only_left') parts.push('仅本地存在');
              else if (s.status === 'only_right') parts.push('仅云端/快照存在');
              else {
                parts.push(s.newer_side === 'left' ? '本地较新' : (s.newer_side === 'right' ? '云端较新' : '内容差异'));
              }
              if (s.level_diff) {
                parts.push('Lv.' + s.level_diff.left_lv + ' vs Lv.' + s.level_diff.right_lv);
              }
              if (s.gold_diff) {
                parts.push(s.gold_diff.left + 'G vs ' + s.gold_diff.right + 'G');
              }
              return {
                rel_path: s.rel_path,
                label: s.label,
                status: s.status,
                badge: parts.join(' · ')
              };
            });
          } else {
            saveTime.leftCard = null;
            saveTime.rightCard = null;
            saveTime.diffSlots = [];
            saveTime.summaryText = '共 ' + mergedSnaps.length + ' 份可用历史快照';
          }

          if (saveTime.conflictState === 'remote_ahead') {
            saveTime.strategy = 'use_snapshot';
          } else if (saveTime.conflictState === 'local_ahead') {
            saveTime.strategy = 'keep_local';
          } else {
            saveTime.strategy = 'slot_merge';
          }

          if (autoSwitchOnConflict && (saveTime.conflictState === 'diverged' || saveTime.conflictState === 'remote_ahead')) {
            setSheet('savetime');
            play('error');
            showToast('⚠️ 检测到本地与云端存档存在差异分叉，已为您打开冲突快速仲裁面板', 'error', 4200);
          }
          return d;
        } catch (e) {
          saveTime.bannerText = '检测云存档冲突失败：' + e.message;
          return null;
        } finally {
          saveTime.loading = false;
        }
      }

      // focus.zone: 'grid' | 'hero'
      const focus = reactive({ zone: 'grid', row: 0, col: 0, heroBtn: 0 });
      const gridCols = ref(6);
      const scroller = ref(null);

      const detailGame = ref(null);
      const detailStatus = ref(null);
      const detailLoading = ref(false);
      const detailTextEl = ref(null);
      const detailScreenshots = ref([]);
      const lightboxOpen = ref(false);
      const lightboxIndex = ref(0);

      const sheet = ref(null);
      const sheetIndex = ref(0);

      const reader = ref(null);
      const readerBody = ref(null);
      const readerTocIndex = ref(0);

      const toast = ref(null);
      let toastTimer = null;

      const launching = ref(null);
      const playSession = ref(null);

      const tonightId = ref(null);
      const modes = reactive(LS.get('bs_launch_modes', {}));

      const isFullscreen = ref(false);
      let escConfirmArmedAt = 0;

      const pad = reactive({
        connected: false,
        activeMethod: 'kb_mouse',
        id: '',
        family: 'xbox',
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
          // 将大屏音量 (0.15 / 0.3 / 0.5) 换算为相对于默认 0.3 的增益倍率
          const volScale = Math.max(0.2, (Number(settings.volume) || 0.3) / 0.3);
          window.ACGTheme.playSfx(sfxMap[name] || 'focus', volScale);
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
        const q = (searchQuery.value || '').trim().toLowerCase();
        if (q) {
          list = list.filter(function (g) {
            const hay = [
              gameTitle(g),
              g.original_title || '',
              g.rj_code || '',
              g.circle_name || '',
              parseTags(g).join(' ')
            ].join(' ').toLowerCase();
            return hay.indexOf(q) >= 0;
          });
        }
        if (filter.status !== 'all') list = list.filter(function (g) { return g.play_status === filter.status; });
        if (filter.favorite) list = list.filter(function (g) { return !!g.is_favorite; });
        if (filter.translated) list = list.filter(function (g) { return isTranslated(g); });
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

      const alphaGroups = computed(function () {
        const pool = filteredGames.value;
        if (pool.length < 16) return [];
        const groups = [{ letter: 'ALL', index: 0 }];
        const seen = {};
        for (let i = 0; i < pool.length; i++) {
          const ch = gameTitle(pool[i]).trim().charAt(0).toUpperCase();
          let bucket = '#';
          if (/[A-Z]/.test(ch)) bucket = ch;
          else if (/[0-9]/.test(ch)) bucket = '0-9';
          else if (ch) bucket = '汉/假';
          if (!seen[bucket]) {
            seen[bucket] = true;
            groups.push({ letter: bucket, index: i });
          }
        }
        return groups.slice(0, 16);
      });

      function jumpToAlpha(rowIndex, itemIndex, letter) {
        activeAlpha.value = letter;
        focus.zone = 'grid';
        setFocus(rowIndex, itemIndex);
        scrollFocused();
      }

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
        if (layout.value === 'grid' || searchQuery.value) {
          return [{ key: 'all', title: searchQuery.value ? '搜索结果' : '全部作品', icon: 'grid', type: 'grid', items: pool }];
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

      // 135ms 防抖 Hero 展示与 WebP 缩略图模糊背景，彻底消除长按方向键时的解码掉帧
      const displayHeroGame = ref(null);
      const flip = ref(0);
      const bgStyle = reactive([{}, {}]);
      let heroDebounceTimer = null;

      function applyHeroBackdrop(g) {
        displayHeroGame.value = g;
        if (Number(settings.bg) === 0) return;
        const next = flip.value === 0 ? 1 : 0;
        // 使用轻量 WebP 缩略图渲染 54px 高斯模糊背景，视觉完全一致且纹理开销降低 95%
        const url = g ? (thumbUrl(g) || coverUrl(g)) : '';
        bgStyle[next] = url ? { backgroundImage: 'url("' + url + '")' } : {};
        flip.value = next;
      }

      watch(heroGame, function (g) {
        if (!displayHeroGame.value) {
          applyHeroBackdrop(g);
          return;
        }
        if (heroDebounceTimer) clearTimeout(heroDebounceTimer);
        heroDebounceTimer = setTimeout(function () {
          applyHeroBackdrop(g);
        }, 135);
      }, { immediate: true });

      const heroScrollCollapsed = ref(false);
      const isHeroCompact = computed(function () {
        if (focus.zone === 'hero') return false;
        return focus.row > 0 || heroScrollCollapsed.value;
      });

      function onMainScroll(ev) {
        if (ev && ev.target) {
          const st = ev.target.scrollTop || 0;
          mainScrollTop.value = st;
          if (!heroScrollCollapsed.value && st > 76) {
            heroScrollCollapsed.value = true;
          } else if (heroScrollCollapsed.value && st < 16) {
            heroScrollCollapsed.value = false;
          }
        }
      }

      const sheetGame = computed(function () { return detailGame.value || displayHeroGame.value || heroGame.value || null; });

      const detailBgStyle = computed(function () {
        const g = detailGame.value;
        const url = g ? (thumbUrl(g) || coverUrl(g)) : '';
        return url ? { backgroundImage: 'url("' + url + '")' } : {};
      });

      const detailGallery = computed(function () {
        const g = detailGame.value;
        if (!g) return [];
        const samples = parseList(g.sample_images);
        const shots = (detailScreenshots.value || []).map(function (s) { return s.url || ('/api/gallery/' + g.id + '/' + encodeURIComponent(s.filename)); });
        const all = [];
        const seen = {};
        samples.concat(shots).forEach(function (u) {
          if (u && !seen[u]) {
            seen[u] = true;
            all.push(u);
          }
        });
        return all.slice(0, 16);
      });

      /* -------------------------------------------------------- data load */
      function tickClock() {
        const d = new Date();
        const pad2 = function (n) { return n < 10 ? '0' + n : '' + n; };
        clock.value = pad2(d.getHours()) + ':' + pad2(d.getMinutes());
      }

      async function refreshGames() {
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
              if (c.left < t.left + 28) track.scrollBy({ left: c.left - t.left - 28, behavior: 'smooth' });
              else if (c.right > t.right - 28) track.scrollBy({ left: c.right - t.right + 28, behavior: 'smooth' });
            }
            return;
          }

          if (card.scrollIntoView) {
            card.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
          }
        });
      }

      function focusHeroBtn(idx) {
        focus.zone = 'hero';
        focus.heroBtn = idx;
      }

      function heroBtnCount() {
        const g = displayHeroGame.value || heroGame.value;
        return g && g.has_walkthrough ? 5 : 4;
      }

      function triggerHeroButton() {
        const g = displayHeroGame.value || heroGame.value;
        if (!g) return;
        const hasGuide = !!g.has_walkthrough;
        const idx = focus.heroBtn;
        if (idx === 0) launch(g);
        else if (idx === 1) openDetail(g);
        else if (hasGuide && idx === 2) openReader(g);
        else if (idx === (hasGuide ? 3 : 2)) toggleFavorite(g);
        else openSheet('actions');
      }

      function setFocus(ri, ci) {
        focus.zone = 'grid';
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
        if (focus.zone === 'hero') {
          if (dy > 0) {
            focus.zone = 'grid';
            play('move');
            scrollFocused();
            return;
          }
          if (dx) {
            const maxBtn = heroBtnCount() - 1;
            focus.heroBtn = clamp(focus.heroBtn + dx, 0, maxBtn);
            play('move');
          }
          return;
        }

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
            } else if (dy < 0 && r === 0) {
              focus.zone = 'hero';
              focus.heroBtn = 0;
              play('move');
              return;
            } else {
              r = clamp(r + dy, 0, rs.length - 1);
              c = clamp(c, 0, Math.max(0, rs[r].items.length - 1));
            }
          } else {
            if (dy < 0 && r === 0) {
              focus.zone = 'hero';
              focus.heroBtn = 0;
              play('move');
              return;
            }
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
        focus.zone = 'grid';
        const rs = rows.value;
        if (!rs.length) return;
        focus.row = clamp(focus.row + dir, 0, rs.length - 1);
        focus.col = clamp(focus.col, 0, Math.max(0, rs[focus.row].items.length - 1));
        play('move');
        scrollFocused();
      }

      function pageMove(dir) {
        focus.zone = 'grid';
        const row = currentRow.value;
        if (!row) return;
        if (row.type === 'grid') {
          const next = focus.col + dir * gridCols.value * 2;
          focus.col = clamp(next, 0, row.items.length - 1);
          play('move');
          scrollFocused();
        } else {
          const next = clamp(focus.col + dir * 5, 0, row.items.length - 1);
          if (next !== focus.col) {
            focus.col = next;
            play('move');
            scrollFocused();
          }
        }
      }

      function toggleLayout() {
        layout.value = layout.value === 'grid' ? 'rails' : 'grid';
        LS.set('bs_layout', layout.value);
        focus.zone = 'grid';
        focus.row = 0;
        focus.col = 0;
        play('confirm');
        showToast(layout.value === 'grid' ? '已切换为纯网格' : '已切换为轨道 + 网格', '', 1800);
        nextTick(function () { scrollFocused(); });
      }

      function clearOrBlurSearch() {
        if (searchQuery.value) {
          searchQuery.value = '';
        } else if (searchInputEl.value) {
          searchInputEl.value.blur();
        }
      }

      function blurSearchToGrid() {
        if (searchInputEl.value) searchInputEl.value.blur();
        focus.zone = 'grid';
        focus.row = 0;
        focus.col = 0;
      }

      function toggleThemeQuick() {
        if (window.AcgTheme) {
          window.AcgTheme.toggle();
          showToast(themeResolved.value === 'light' ? '☀ 已切换为 Switch 日间主题' : '🌙 已切换为夜间主题', 'success', 1800);
        }
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
          if (displayHeroGame.value && displayHeroGame.value.id === g.id) {
            displayHeroGame.value = Object.assign({}, displayHeroGame.value, merged);
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
          lightboxOpen.value = false;
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
        try { await refreshGames(); } catch (e) { /* ignore */ }
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
        detailScreenshots.value = [];
        lightboxOpen.value = false;
        lightboxIndex.value = 0;
        play('open');
        nextTick(function () { if (detailTextEl.value) detailTextEl.value.scrollTop = 0; });
        try {
          const [resGame, resShots] = await Promise.all([
            fetch('/api/games/' + g.id, { cache: 'no-store' }),
            fetch('/api/games/' + g.id + '/screenshots', { cache: 'no-store' }).catch(function () { return null; })
          ]);
          if (resGame && resGame.ok) {
            const data = await resGame.json();
            if (data && data.data) detailGame.value = data.data;
            detailStatus.value = data.mtool_status || null;
          }
          if (resShots && resShots.ok) {
            const sdata = await resShots.json();
            detailScreenshots.value = (sdata && sdata.screenshots) || [];
          }
        } catch (e) {
          showToast('读取详情失败，已显示缓存信息', 'error');
        } finally {
          detailLoading.value = false;
        }
      }

      function closeDetail() {
        if (lightboxOpen.value) {
          closeLightbox();
          return;
        }
        if (!detailGame.value) return;
        detailGame.value = null;
        play('back');
        scrollFocused();
      }

      function openLightbox(idx) {
        if (!detailGallery.value.length) return;
        lightboxIndex.value = clamp(idx || 0, 0, detailGallery.value.length - 1);
        lightboxOpen.value = true;
        play('open');
      }

      function closeLightbox() {
        lightboxOpen.value = false;
        play('back');
      }

      function stepLightbox(dir) {
        const len = detailGallery.value.length;
        if (!len) return;
        lightboxIndex.value = (lightboxIndex.value + dir + len) % len;
        play('move');
      }

      function scrollDetail(dir) {
        const el = detailTextEl.value;
        if (!el) return;
        el.scrollBy({ top: dir * 140, behavior: 'smooth' });
      }

      /* -------------------- 交互式攻略阅读器（含章节目录 TOC 与复选框勾选持久化） -------------------- */
      function buildReaderPayload(gameObj, rawMd) {
        const toc = [];
        const checklists = [];
        const lines = String(rawMd || '').split('\n');
        let inCode = false;
        for (let i = 0; i < lines.length; i++) {
          const ln = lines[i];
          if (/^```/.test(ln.trim())) { inCode = !inCode; continue; }
          if (inCode) continue;
          const hm = ln.match(/^(#{1,3})\s+(.+)$/);
          if (hm) {
            toc.push({
              level: hm[1].length,
              text: hm[2].replace(/[*_`~]/g, '').trim(),
              lineIndex: i
            });
          }
          const cm = ln.match(/^(\s*[-*+]\s+\[)([ xX])(\]\s+)(.+)$/);
          if (cm) {
            checklists.push({
              idx: checklists.length,
              lineIndex: i,
              checked: cm[2].toLowerCase() === 'x',
              text: cm[4].trim()
            });
          }
        }

        let cbCounter = 0;
        const mdWithMermaid = rawMd.replace(/```mermaid\s*\n([\s\S]*?)```/gi, function (_m, code) {
          return compileMermaidToVisualHtml(code);
        });
        let html = escapeHtml(mdWithMermaid);
        try {
          if (window.marked) {
            const parsed = window.marked.parse ? window.marked.parse(mdWithMermaid) : window.marked(mdWithMermaid);
            html = sanitizeReaderHtml(parsed);
          }
        } catch (e) {
          html = sanitizeReaderHtml(mdWithMermaid);
        }
        // 将禁用复选框替换为可点击交互复选框
        html = html.replace(/<input([^>]*?)type=["']checkbox["']([^>]*?)>/gi, function (full) {
          const isChecked = /\bchecked\b/i.test(full);
          const idx = cbCounter++;
          return '<input type="checkbox" class="bs-task-cb" data-task-idx="' + idx + '"' + (isChecked ? ' checked' : '') + '>';
        });

        return {
          gameId: gameObj.id,
          title: gameTitle(gameObj),
          rawMd: rawMd,
          meta: Math.round(rawMd.length / 100) / 10 + 'k 字',
          toc: toc,
          checklists: checklists,
          html: html
        };
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
        readerTocIndex.value = 0;
        reader.value = buildReaderPayload(full, rawMd);
        play('open');
        nextTick(function () { if (readerBody.value) readerBody.value.scrollTop = 0; });
      }

      const readerCheckedCount = computed(function () {
        if (!reader.value || !reader.value.checklists) return 0;
        return reader.value.checklists.filter(function (c) { return c.checked; }).length;
      });

      function jumpReaderToc(ti) {
        if (!reader.value || !reader.value.toc || !readerBody.value) return;
        readerTocIndex.value = clamp(ti, 0, reader.value.toc.length - 1);
        const headings = readerBody.value.querySelectorAll('h1, h2, h3');
        if (headings[readerTocIndex.value]) {
          headings[readerTocIndex.value].scrollIntoView({ behavior: 'smooth', block: 'start' });
          play('move');
        }
      }

      async function toggleReaderChecklistAt(taskIdx) {
        if (!reader.value || !reader.value.checklists) return;
        const item = reader.value.checklists[taskIdx];
        if (!item) return;
        const lines = reader.value.rawMd.split('\n');
        const ln = lines[item.lineIndex] || '';
        const nextChecked = !item.checked;
        lines[item.lineIndex] = ln.replace(/^(\s*[-*+]\s+\[)[ xX](\]\s+)/, '$1' + (nextChecked ? 'x' : ' ') + '$2');
        const newMd = lines.join('\n');
        const currentScroll = readerBody.value ? readerBody.value.scrollTop : 0;
        reader.value = buildReaderPayload({ id: reader.value.gameId, display_title: reader.value.title }, newMd);
        nextTick(function () {
          if (readerBody.value) readerBody.value.scrollTop = currentScroll;
        });
        play('confirm');
        try {
          await fetch('/api/games/' + reader.value.gameId + '/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ walkthrough_md: newMd })
          });
          if (detailGame.value && detailGame.value.id === reader.value.gameId) {
            detailGame.value.walkthrough_md = newMd;
          }
        } catch (e) { /* ignore */ }
      }

      function onReaderBodyClick(ev) {
        const t = ev.target;
        if (t && t.classList && t.classList.contains('bs-task-cb')) {
          const idx = Number(t.dataset.taskIdx);
          if (!Number.isNaN(idx)) {
            ev.preventDefault();
            toggleReaderChecklistAt(idx);
          }
        }
      }

      function closeReader() {
        reader.value = null;
        play('back');
      }

      function exitHome() {
        play('back');
        window.location.href = '/';
      }

      async function toggleFullscreen() {
        play('confirm');
        let fs = false;
        if (window.AcgWindow && window.AcgWindow.toggleFullscreen) {
          fs = await window.AcgWindow.toggleFullscreen();
        }
        const activeFs = Boolean(
          (window.AcgWindow && window.AcgWindow.isFullscreen) ||
          document.fullscreenElement ||
          fs
        );
        isFullscreen.value = activeFs;
        showToast(activeFs ? '已进入全屏模式 (按 F11 或双击顶栏可还原)' : '已还原为窗口模式', '', 1800);
        try { window.focus(); } catch (e) {}
      }

      /* -------------------------------------------------------------- sheet */
      const sheetTitle = computed(function () {
        if (sheet.value === 'filter') return '筛选与布局';
        if (sheet.value === 'settings') return '大屏设置';
        if (sheet.value === 'savetime') {
          return sheetGame.value ? '存档时光机与冲突仲裁 · ' + gameTitle(sheetGame.value) : '存档时光机';
        }
        return sheetGame.value ? '操作与生命周期维护 · ' + gameTitle(sheetGame.value) : '操作';
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
            { key: 's_cover_fit', label: '横竖封面比例兼容', value: settings.coverFit || 'smart', options: [['smart', '智能防裁切 (推荐)'], ['cover', '全铺满 (3:4)'], ['contain', '全部完整居中']] },
            { key: 's_parallax', label: '卡片 3D 视差高光动效', value: settings.parallax !== false, options: [[true, '开启'], [false, '关闭']] },
            { key: 's_bg', label: '背景氛围强度', value: settings.bg, options: [[0, '关闭 (省电)'], [1, '柔和'], [2, '强烈']] },
            { key: 's_sound', label: '操作微音效', value: !!settings.sound, options: [[true, '开'], [false, '关']] },
            { key: 's_volume', label: '音效音量', value: Number(settings.volume), options: [[0.15, '低'], [0.3, '中'], [0.5, '高']] },
            { key: 's_card_confirm', label: '卡片确认键行为', value: settings.cardConfirm || 'detail', options: [['detail', '打开详情页'], ['launch', '直接启动游戏']] },
            { key: 's_confirm', label: '手柄确认键位置', value: settings.confirmKey, options: [['auto', '自动识别'], ['xbox', '下方键确认'], ['ps', '右侧键确认']] },
            { key: 's_hints', label: '底部按键提示条', value: !!settings.hints, options: [[true, '显示'], [false, '隐藏']] }
          ];
        }
        const g = sheetGame.value;
        if (!g) return [];

        if (sheet.value === 'savetime') {
          const stRows = [
            {
              key: 'st_strategy',
              label: '⚖️ 冲突仲裁策略',
              value: saveTime.strategy || 'slot_merge',
              options: [
                ['slot_merge', '智能合并最新槽位'],
                ['keep_local', '保留本地并上传'],
                ['use_snapshot', '采用云端/快照覆盖'],
                ['keep_both', '双分支同时保留']
              ]
            },
            {
              key: 'st_execute_resolve',
              label: '⚡ 立即执行所选仲裁并同步',
              action: true,
              disabled: saveTime.resolving || saveTime.loading,
              hint: saveTime.resolving ? '正在执行存档仲裁与云同步…' : ('按 ' + pad.confirm + ' 立即应用上方仲裁方案（自动创建保护备份）')
            },
            {
              key: 'st_create_snapshot',
              label: '📸 立即新建当前存档快照并上传云端',
              action: true,
              disabled: saveTime.resolving,
              hint: '按 ' + pad.confirm + ' 固化当前进度并同步至 WebDAV'
            },
            {
              key: 'st_refresh',
              label: '🔄 重新扫描本地与 WebDAV 云端存档槽位',
              action: true,
              disabled: saveTime.loading,
              hint: '按 ' + pad.confirm + ' 刷新双向差异对比数据'
            }
          ];
          (saveTime.snapshots || []).forEach(function (snap) {
            stRows.push({
              key: 'st_restore:' + snap.sourceId,
              snapObj: snap,
              label: '🕰️ ' + snap.label,
              action: true,
              disabled: saveTime.resolving,
              hint: snap.sub + ' · 按 ' + pad.confirm + ' 一键回滚至此时间点'
            });
          });
          return stRows;
        }

        const statusOpts = STATUS_OPTIONS.filter(function (o) { return o[0] !== 'all'; });
        const optInfo = optStatusMap[g.id] || null;
        const isBusy = !!optBusyMap[g.id];
        const targetFps = optTargetFpsMap[g.id] || 120;
        const canPatchFps = optInfo ? !!optInfo.can_patch_fps : true;
        const fpsPatched = !!(optInfo && optInfo.fps_patched);
        const curFps = (optInfo && optInfo.current_target_fps) || 120;
        const fp = (optInfo && optInfo.footprint) || null;
        const estSaveBytes = fp ? (fp.estimated_savings_bytes || 0) : 0;
        const estSaveStr = fp ? (fp.estimated_savings_str || '0 B') : '检测中…';
        const totalSizeStr = (fp && fp.total_str) || g.folder_size_str || '—';
        const hasSlimBackup = !!(optInfo && optInfo.has_slim_backup);

        const actionRows = [
          { key: 'a_launch', label: '启动方式', value: launchModeFor(g), options: MODE_OPTIONS },
          { key: 'a_fav', label: '收藏', value: !!g.is_favorite, options: [[true, '已收藏'], [false, '未收藏']] },
          { key: 'a_rating', label: '评分', value: g.user_rating || 0, options: [[0, '未评'], [1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5']] },
          { key: 'a_status', label: '状态', value: g.play_status, options: statusOpts }
        ];

        // 状态感知高刷补丁与一键回滚项
        if (canPatchFps) {
          actionRows.push({
            key: 'a_fps_target',
            label: '🎯 高刷补丁目标帧率',
            value: targetFps,
            options: [[60, '60Hz'], [90, '90Hz'], [120, '120Hz'], [144, '144Hz'], [165, '165Hz']]
          });
        }
        actionRows.push({
          key: 'a_fps_boost',
          label: fpsPatched
            ? ('⚡ 高刷补丁：已注入 ' + curFps + 'Hz' + (curFps !== targetFps ? (' → 待更新 ' + targetFps + 'Hz') : ''))
            : ('⚡ 高刷与 4x 快进补丁：' + (canPatchFps ? '未注入' : '当前引擎无需注入')),
          action: true,
          disabled: isBusy || !canPatchFps,
          hint: !canPatchFps
            ? '仅 RPG Maker MV/MZ 与 Unity 引擎支持原生高刷注入'
            : (fpsPatched && curFps === targetFps
                ? ('按 ' + pad.confirm + ' 一键回滚移除高刷补丁，恢复原始脚本')
                : ('按 ' + pad.confirm + ' 注入 ' + targetFps + 'Hz 高刷与 4x 快进补丁'))
        });

        // 状态感知无损体积瘦身与备份回滚项
        actionRows.push({
          key: 'a_slim_game',
          label: fp
            ? (estSaveBytes > 32 * 1024
                ? ('🧹 体积瘦身：可释放 ' + estSaveStr + '（当前 ' + totalSizeStr + '）')
                : ('🧹 体积瘦身：已处于精简状态（当前 ' + totalSizeStr + '）'))
            : '🧹 体积瘦身：正在分析冗余文件与贴图…',
          action: true,
          disabled: isBusy || !optInfo,
          hint: isBusy
            ? '正在后台执行无损压缩与清理，请稍候…'
            : ('按 ' + pad.confirm + ' 清理冗余缓存并无损压缩 PNG 贴图（自动生成回滚备份包）')
        });

        if (hasSlimBackup) {
          actionRows.push({
            key: 'a_slim_rollback',
            label: '⏪ 还原瘦身前原始文件（备份包 ' + (optInfo.backup_size_str || '') + '）',
            action: true,
            disabled: isBusy,
            hint: '按 ' + pad.confirm + ' 从 .acg_optimizer_backup.zip 无损恢复全部原始文件'
          });
        }

        // 云存档同步与时光机冲突仲裁入口
        actionRows.push({
          key: 'a_webdav_sync',
          label: '☁️ WebDAV 云端存档智能同步',
          action: true,
          hint: '按 ' + pad.confirm + ' 自动检测冲突并双向同步（若存在分叉将弹出快速仲裁）'
        });
        actionRows.push({
          key: 'a_open_savetime',
          label: '🕰️ 存档时光机与冲突快速仲裁面板',
          action: true,
          hint: '按 ' + pad.confirm + ' 对比本地 vs 云端槽位详情或回滚历史快照'
        });

        actionRows.push({
          key: 'a_magpie',
          label: 'Magpie 全屏',
          action: true,
          disabled: !magpie.value.installed || !runningMap.value[g.id],
          hint: !magpie.value.installed
            ? '未检测到 Magpie（设置里可指定路径）'
            : (runningMap.value[g.id] ? '按 ' + pad.confirm + ' 让 Magpie 接管全屏' : '游戏启动后才能全屏')
        });
        actionRows.push({
          key: 'a_magpie_preset',
          label: 'Magpie 预设：' + magpiePresetLabel(),
          action: true,
          disabled: !magpie.value.installed || !(magpiePresets.value.presets || []).length,
          hint: '按 ' + pad.confirm + ' 切到下一个缩放预设（会重启 Magpie）'
        });
        actionRows.push({
          key: 'a_theme',
          label: '界面主题：' + (themeResolved.value === 'light' ? '日间 (Switch)' : '夜间'),
          action: true,
          hint: '按 ' + pad.confirm + ' 在 夜间 / 日间 (Switch) 之间切换'
        });
        actionRows.push({
          key: 'a_folder',
          label: '打开游戏目录',
          action: true,
          hint: '按 ' + pad.confirm + ' 在资源管理器中打开'
        });
        actionRows.push({
          key: 'a_guide',
          label: '全结局攻略',
          action: true,
          hint: g.has_walkthrough ? ('按 ' + pad.confirm + ' 阅读') : '该作品暂无攻略',
          disabled: !g.has_walkthrough
        });

        return actionRows;
      });

      function setSheet(name) {
        sheet.value = name;
        sheetIndex.value = 0;
        const g = sheetGame.value;
        if (name === 'actions' && g) {
          refreshOptimizerStatus(g.id, false);
        } else if (name === 'savetime' && g) {
          loadSaveTimeMachine(g, false);
        }
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
          case 's_cover_fit':
            settings.coverFit = val;
            LS.set('bs_settings', settings);
            break;
          case 's_parallax':
            settings.parallax = !!val;
            LS.set('bs_settings', settings);
            break;
          case 's_bg':
            settings.bg = Number(val);
            LS.set('bs_settings', settings);
            if (settings.bg > 0 && heroGame.value) applyHeroBackdrop(heroGame.value);
            break;
          case 's_sound':
            settings.sound = !!val;
            LS.set('bs_settings', settings);
            if (window.ACGTheme && window.ACGTheme.setSfx) window.ACGTheme.setSfx(!!val);
            break;
          case 's_volume':
            settings.volume = Number(val);
            LS.set('bs_settings', settings);
            if (window.ACGTheme && window.ACGTheme.setVolumeScale) {
              window.ACGTheme.setVolumeScale(Math.max(0.2, settings.volume / 0.3));
            }
            break;
          case 's_card_confirm':
            settings.cardConfirm = val;
            LS.set('bs_settings', settings);
            break;
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
          case 'a_fps_target':
            if (g) optTargetFpsMap[g.id] = Number(val);
            break;
          case 'st_strategy':
            saveTime.strategy = val;
            break;
          default: break;
        }
        play('move');
      }

      async function runRowAction(row) {
        const g = sheetGame.value;
        if (!g || row.disabled) return;

        // 存档时光机与冲突快速仲裁面板动作
        if (row.key === 'a_open_savetime') {
          setSheet('savetime');
          play('open');
          return;
        }
        if (row.key === 'st_refresh') {
          showToast('正在重新扫描本地与云端存档槽位…', '', 1600);
          await loadSaveTimeMachine(g, false);
          play('confirm');
          return;
        }
        if (row.key === 'st_create_snapshot') {
          saveTime.resolving = true;
          showToast('正在创建本地存档快照并同步云端…', '', 2000);
          try {
            const res = await fetch('/api/games/' + g.id + '/webdav_sync', { method: 'POST' });
            const d = await res.json();
            showToast(d.message || (d.success ? '已创建快照并同步至云端' : '快照创建完成'), d.success ? 'success' : 'error', 3600);
            play(d.success ? 'confirm' : 'error');
            await loadSaveTimeMachine(g, false);
          } catch (e) {
            showToast('创建快照请求失败：' + e.message, 'error');
          } finally {
            saveTime.resolving = false;
          }
          return;
        }
        if (row.key === 'st_execute_resolve') {
          saveTime.resolving = true;
          const strat = saveTime.strategy || 'slot_merge';
          showToast('正在执行存档仲裁方案…', '', 2200);
          try {
            const res = await fetch('/api/games/' + g.id + '/saves/resolve', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                strategy: strat,
                snapshot_filename: saveTime.targetSnapshot || '',
                slot_choices: null
              })
            });
            const d = await res.json();
            showToast(d.message || (d.success ? '存档仲裁完成' : '仲裁失败'), d.success ? 'success' : 'error', 4200);
            play(d.success ? 'confirm' : 'error');
            await loadSaveTimeMachine(g, false);
          } catch (e) {
            showToast('仲裁请求失败：' + e.message, 'error');
          } finally {
            saveTime.resolving = false;
          }
          return;
        }
        if (row.key && row.key.indexOf('st_restore:') === 0 && row.snapObj) {
          saveTime.resolving = true;
          const snap = row.snapObj;
          showToast('正在回滚至快照：' + snap.filename + '…', '', 2400);
          try {
            const res = await fetch('/api/games/' + g.id + '/saves/resolve', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                strategy: 'use_snapshot',
                snapshot_filename: snap.sourceId || snap.filename
              })
            });
            const d = await res.json();
            showToast(d.message || (d.success ? '已成功恢复至所选快照（恢复前进度已自动备份）' : '快照恢复失败'), d.success ? 'success' : 'error', 4200);
            play(d.success ? 'confirm' : 'error');
            await loadSaveTimeMachine(g, false);
          } catch (e) {
            showToast('回滚快照失败：' + e.message, 'error');
          } finally {
            saveTime.resolving = false;
          }
          return;
        }

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
          toggleThemeQuick();
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
        if (row.key === 'a_fps_boost') {
          const optInfo = optStatusMap[g.id];
          const targetFps = optTargetFpsMap[g.id] || 120;
          const isRollback = !!(optInfo && optInfo.fps_patched && optInfo.current_target_fps === targetFps);
          optBusyMap[g.id] = true;
          try {
            if (isRollback) {
              showToast('正在移除高刷补丁并恢复原始脚本…', '', 1800);
              const res = await fetch('/api/games/' + g.id + '/optimizer/fps_unpatch', { method: 'POST' });
              const d = await res.json();
              if (d && d.status) optStatusMap[g.id] = d.status;
              else await refreshOptimizerStatus(g.id, true);
              showToast(d.message || (d.success ? '已还原原始帧率配置' : '还原失败'), d.success ? 'success' : 'error', 3600);
              play(d.success ? 'confirm' : 'error');
            } else {
              showToast('正在注入 ' + targetFps + 'Hz 高刷与 4x 快进补丁…', '', 1800);
              const res = await fetch('/api/games/' + g.id + '/optimizer/fps_patch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_fps: targetFps, fast_skip_mult: 4, keep_bg_audio: true, gpu_raster: true })
              });
              const d = await res.json();
              if (d && d.status) optStatusMap[g.id] = d.status;
              else await refreshOptimizerStatus(g.id, true);
              showToast(d.message || (d.success ? '高刷补丁已注入' : '注入失败'), d.success ? 'success' : 'error', 3600);
              play(d.success ? 'confirm' : 'error');
            }
          } catch (e) {
            showToast('高刷补丁操作失败：' + e.message, 'error');
          } finally {
            optBusyMap[g.id] = false;
          }
          return;
        }
        if (row.key === 'a_slim_game') {
          optBusyMap[g.id] = true;
          showToast('正在清理冗余缓存并无损压缩 PNG 贴图…', '', 2800);
          try {
            const res = await fetch('/api/games/' + g.id + '/optimizer/slim', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                clean_junk: true,
                compress_images: true,
                image_mode: 'lossless_png',
                create_rollback_backup: true
              })
            });
            const d = await res.json();
            if (d && d.status) {
              optStatusMap[g.id] = d.status;
              if (d.status.footprint && d.status.footprint.total_str) {
                g.folder_size_str = d.status.footprint.total_str;
              }
            } else {
              await refreshOptimizerStatus(g.id, true);
            }
            showToast(d.message || (d.success ? '无损体积瘦身完成' : '瘦身失败'), d.success ? 'success' : 'error', 4200);
            play(d.success ? 'confirm' : 'error');
          } catch (e) {
            showToast('无损瘦身请求失败：' + e.message, 'error');
          } finally {
            optBusyMap[g.id] = false;
          }
          return;
        }
        if (row.key === 'a_slim_rollback') {
          optBusyMap[g.id] = true;
          showToast('正在从备份包无损回滚全部原始文件…', '', 2400);
          try {
            const res = await fetch('/api/games/' + g.id + '/optimizer/rollback', { method: 'POST' });
            const d = await res.json();
            if (d && d.status) {
              optStatusMap[g.id] = d.status;
              if (d.status.footprint && d.status.footprint.total_str) {
                g.folder_size_str = d.status.footprint.total_str;
              }
            } else {
              await refreshOptimizerStatus(g.id, true);
            }
            showToast(d.message || (d.success ? '已成功恢复原始文件' : '回滚失败'), d.success ? 'success' : 'error', 4200);
            play(d.success ? 'confirm' : 'error');
          } catch (e) {
            showToast('回滚瘦身备份失败：' + e.message, 'error');
          } finally {
            optBusyMap[g.id] = false;
          }
          return;
        }
        if (row.key === 'a_webdav_sync') {
          showToast('正在检测云端存档状态与同步…', '', 1800);
          const conflictRes = await loadSaveTimeMachine(g, true);
          if (conflictRes && (conflictRes.conflict_state === 'diverged' || conflictRes.conflict_state === 'remote_ahead')) {
            return;
          }
          try {
            const res = await fetch('/api/games/' + g.id + '/webdav_sync', { method: 'POST' });
            const d = await res.json();
            showToast(d.message || (d.success ? '云同步完成' : '云同步失败'), d.success ? 'success' : 'error', 3600);
            play(d.success ? 'confirm' : 'error');
          } catch (e) { showToast('WebDAV 同步请求失败', 'error'); }
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
        if (name === 'up' || name === 'down') {
          const delta = name === 'up' ? -1 : 1;
          sheetIndex.value = clamp(sheetIndex.value + delta, 0, rowsNow.length - 1);
          play('move');
          nextTick(function () {
            const focusedRow = document.querySelector('.sheet-row.focused');
            if (focusedRow && focusedRow.scrollIntoView) {
              focusedRow.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
          });
        }
        else if (name === 'left') cycleRow(row, -1);
        else if (name === 'right') cycleRow(row, 1);
        else if (name === 'confirm') { if (row.action) runRowAction(row); else cycleRow(row, 1); }
        else if (name === 'cancel' || name === 'start') closeSheet();
        else if (name === 'lb') {
          const tabs = ['filter', 'actions', 'savetime', 'settings'];
          const i = Math.max(0, tabs.indexOf(sheet.value));
          setSheet(tabs[(i - 1 + tabs.length) % tabs.length]);
          play('move');
        } else if (name === 'rb') {
          const tabs = ['filter', 'actions', 'savetime', 'settings'];
          const i = Math.max(0, tabs.indexOf(sheet.value));
          setSheet(tabs[(i + 1) % tabs.length]);
          play('move');
        }
      }

      function handleReader(name) {
        const el = readerBody.value;
        if (name === 'cancel' || name === 'back') { closeReader(); return; }
        if (name === 'lb' && reader.value && reader.value.toc && reader.value.toc.length) {
          jumpReaderToc(readerTocIndex.value - 1);
          return;
        }
        if (name === 'rb' && reader.value && reader.value.toc && reader.value.toc.length) {
          jumpReaderToc(readerTocIndex.value + 1);
          return;
        }
        if (name === 'fav' && reader.value && reader.value.checklists && reader.value.checklists.length) {
          let minLine = 0;
          if (reader.value.toc && reader.value.toc[readerTocIndex.value]) {
            minLine = reader.value.toc[readerTocIndex.value].lineIndex || 0;
          }
          let targetIdx = reader.value.checklists.findIndex(function (c) {
            return !c.checked && c.lineIndex >= minLine;
          });
          if (targetIdx < 0) {
            targetIdx = reader.value.checklists.findIndex(function (c) { return !c.checked; });
          }
          toggleReaderChecklistAt(targetIdx >= 0 ? targetIdx : 0);
          return;
        }
        if (!el) return;
        if (name === 'up') el.scrollBy({ top: -180, behavior: 'smooth' });
        else if (name === 'down') el.scrollBy({ top: 180, behavior: 'smooth' });
        else if (name === 'lt') el.scrollBy({ top: -el.clientHeight * 0.8, behavior: 'smooth' });
        else if (name === 'rt') el.scrollBy({ top: el.clientHeight * 0.8, behavior: 'smooth' });
      }

      function handleDetail(name) {
        const g = detailGame.value;
        if (lightboxOpen.value) {
          if (name === 'cancel' || name === 'back') { closeLightbox(); return; }
          if (name === 'left' || name === 'lb' || name === 'up') { stepLightbox(-1); return; }
          if (name === 'right' || name === 'rb' || name === 'down' || name === 'confirm') { stepLightbox(1); return; }
          return;
        }
        if (name === 'confirm') { launch(g); return; }
        if (name === 'longconfirm') { launch(g, 'native'); return; }
        if (name === 'cancel') { closeDetail(); return; }
        if (name === 'fav') { toggleFavorite(g); return; }
        if (name === 'more') { openSheet('actions'); return; }
        if (name === 'start') { openSheet('filter'); return; }
        if (name === 'lb' && detailGallery.value.length) { openLightbox(0); return; }
        if (name === 'rb' && detailGallery.value.length) { openLightbox(0); return; }
        if (name === 'up') { scrollDetail(-1); return; }
        if (name === 'down') { scrollDetail(1); return; }
        if (name === 'lt') { scrollDetail(-4); return; }
        if (name === 'rt') { scrollDetail(4); return; }
      }

      function handleBrowse(name) {
        const row = currentRow.value;
        if (name === 'confirm') {
          if (focus.zone === 'hero') {
            triggerHeroButton();
            return;
          }
          if (heroGame.value) {
            if (settings.cardConfirm === 'launch') launch(heroGame.value);
            else openDetail(heroGame.value);
          }
          return;
        }
        if (name === 'cancel') {
          if (focus.zone === 'hero') {
            focus.zone = 'grid';
            play('back');
            return;
          }
          if (searchQuery.value) {
            searchQuery.value = '';
            play('back');
            showToast('已清空搜索过滤', '', 1500);
            return;
          }
          const now = Date.now();
          if (now - escConfirmArmedAt < 2500) {
            exitHome();
          } else {
            escConfirmArmedAt = now;
            play('back');
            showToast('再按一次 ' + pad.cancel + '（或长按手柄 ' + pad.cancel + '）退出大屏模式', '', 2400);
          }
          return;
        }
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
      const inputStatusText = computed(function () {
        if (pad.activeMethod === 'gamepad' && pad.connected) {
          const famName = pad.family === 'ps' ? 'DualSense/PS' : (pad.family === 'switch' ? 'Switch Pro' : 'Xbox');
          return famName + ' 手柄操控中';
        }
        if (pad.connected) {
          return '键鼠操控中 (手柄已就绪)';
        }
        return '键鼠操控模式';
      });

      const hints = computed(function () {
        const k = pad;
        if (sheet.value) {
          return [
            { key: '↑↓', label: '选择', tone: '' },
            { key: '←→', label: '调整', tone: '' },
            { key: k.confirm, label: '确认', tone: 'a', act: 'confirm' },
            { key: k.cancel, label: '关闭', tone: 'b', act: 'cancel' },
            { key: k.lb + '/' + k.rb, label: '切换面板', tone: '' }
          ];
        }
        if (reader.value) {
          return [
            { key: '↑↓', label: '滚动', tone: '' },
            { key: k.lb + '/' + k.rb, label: '切换章节', tone: '' },
            { key: k.fav, label: '勾选任务', tone: 'x', act: 'fav' },
            { key: k.lt + '/' + k.rt, label: '翻页', tone: '' },
            { key: k.cancel, label: '返回', tone: 'b', act: 'cancel' }
          ];
        }
        if (detailGame.value) {
          return [
            { key: k.confirm, label: '开始游戏', tone: 'a', act: 'confirm' },
            { key: k.more, label: '更多操作', tone: 'y', act: 'more' },
            { key: k.fav, label: '收藏', tone: 'x', act: 'fav' },
            { key: k.lb + '/' + k.rb, label: '放大预览图', tone: '' },
            { key: k.cancel, label: '返回', tone: 'b', act: 'cancel' }
          ];
        }
        return [
          { key: k.confirm, label: focus.zone === 'hero' ? '执行按钮' : (settings.cardConfirm === 'launch' ? '启动游戏' : '查看详情'), tone: 'a', act: 'confirm' },
          { key: k.fav, label: currentRow.value && currentRow.value.special === 'tonight' ? '换一个' : '收藏', tone: 'x', act: 'fav' },
          { key: k.more, label: '操作面板', tone: 'y', act: 'more' },
          { key: k.lb + '/' + k.rb, label: '切换栏目', tone: '' },
          { key: k.start, label: '筛选', tone: '', act: 'start' },
          { key: k.back, label: '切换布局', tone: '', act: 'back' },
          { key: 'F11', label: isFullscreen.value ? '退出全屏' : '全屏', tone: '' },
          { key: k.cancel, label: '退出大屏', tone: 'b', act: 'cancel' }
        ];
      });

      function clickHint(h) {
        if (!h || !h.act) return;
        onAction(h.act);
      }

      /* ----------------------------------------- Auto-Sense Labels & Gamepad */
      function computeLabels() {
        if (window.AcgDeviceSense) {
          const labels = window.AcgDeviceSense.getPromptLabels(settings.confirmKey);
          pad.activeMethod = labels.mode;
          pad.family = labels.family;
          pad.confirm = labels.confirm;
          pad.cancel = labels.cancel;
          pad.fav = labels.fav;
          pad.more = labels.more;
          pad.start = labels.start;
          pad.back = labels.back;
          pad.lb = labels.lb;
          pad.rb = labels.rb;
          pad.lt = labels.lt;
          pad.rt = labels.rt;
          return;
        }
      }
      computeLabels();

      document.addEventListener('acg-input-device-changed', function (ev) {
        if (ev && ev.detail) {
          pad.connected = !!ev.detail.padConnected;
          pad.id = ev.detail.padId || pad.id;
        }
        computeLabels();
      });

      const PAD_BUTTONS = {
        4: 'lb', 5: 'rb', 6: 'lt', 7: 'rt', 8: 'back', 9: 'start', 10: 'lthumb', 11: 'rthumb'
      };

      function logicalFromButton(i) {
        const confirmRight = settings.confirmKey === 'ps' ||
          (settings.confirmKey === 'auto' && (pad.family === 'ps' || pad.family === 'switch'));
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
      let padRaf = null;

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

      function overlayOpen() { return !!(sheet.value || reader.value || detailGame.value || lightboxOpen.value); }

      function handleButton(i, pressed, gp) {
        const prev = !!held.buttons[i];
        if (pressed === prev) return;
        held.buttons[i] = pressed;
        if (pressed && window.AcgDeviceSense) {
          window.AcgDeviceSense.markGamepadActivity(gp);
        }
        const act = logicalFromButton(i);
        if (!act) return;

        if (!pressed) {
          if (act === 'confirm' && confirmArmed) endConfirmHold();
          if (act === 'cancel' && cancelTimer) {
            clearTimeout(cancelTimer);
            cancelTimer = null;
            if (focus.zone === 'hero') {
              focus.zone = 'grid';
              play('back');
            } else {
              // 每次短按 B 都给出清晰一致的反馈
              showToast('长按 ' + pad.cancel + ' (0.8秒) 退出大屏模式', '', 2200);
            }
          }
          return;
        }

        if (act === 'confirm') {
          if (detailGame.value && !lightboxOpen.value) { startConfirmHold(); return; }
          onAction(act);
          return;
        }
        if (act === 'cancel' && !overlayOpen()) {
          if (cancelTimer) clearTimeout(cancelTimer);
          cancelTimer = setTimeout(function () {
            cancelTimer = null;
            exitHome();
          }, 800);
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
        const dz = 0.52;
        const ax = gp.axes[0] || 0;
        const ay = gp.axes[1] || 0;
        if (Math.abs(ax) < dz && Math.abs(ay) < dz) return null;
        if (Math.abs(ax) > Math.abs(ay)) return ax > 0 ? 'right' : 'left';
        return ay > 0 ? 'down' : 'up';
      }

      // 后端 XInput 实时状态桥接缓存（与设置页共享同一套 XInput1_4.dll 底层引擎，彻底解决 WebView2 失焦或未解锁导致手柄失效的问题）
      const backendXInput = {
        connected: false,
        id: '',
        buttons: [],
        axes: { lx: 0, ly: 0, rx: 0, ry: 0, lt: 0, rt: 0 },
        gameActive: false,
        busy: false
      };

      const XINPUT_W3C_ORDER = [
        'a', 'b', 'x', 'y', 'lb', 'rb', 'lt', 'rt',
        'back', 'start', 'lthumb', 'rthumb', 'up', 'down', 'left', 'right'
      ];

      async function pollBackendXInput() {
        if (playSession.value || document.hidden || backendXInput.busy) return;
        backendXInput.busy = true;
        try {
          let d = null;
          if (window.pywebview && window.pywebview.api && window.pywebview.api.win_get_gamepad) {
            d = await window.pywebview.api.win_get_gamepad();
          } else {
            const r = await fetch('/api/gamepad/ui_state', { cache: 'no-store' });
            if (r.ok) d = await r.json();
          }
          if (d && d.ok !== false) {
            backendXInput.connected = !!d.connected;
            backendXInput.id = d.id || 'XInput Standard Controller';
            backendXInput.buttons = Array.isArray(d.buttons) ? d.buttons : [];
            backendXInput.axes = d.axes || { lx: 0, ly: 0, rx: 0, ry: 0, lt: 0, rt: 0 };
            backendXInput.gameActive = !!d.game_active;
          }
        } catch (e) { /* ignore */ }
        finally {
          backendXInput.busy = false;
        }
      }

      function buildUnifiedGamepad() {
        let browserGp = null;
        if (navigator.getGamepads) {
          try {
            const pads = navigator.getGamepads();
            for (let i = 0; i < pads.length; i++) {
              if (pads[i] && pads[i].connected) { browserGp = pads[i]; break; }
            }
          } catch (e) { /* ignore */ }
        }

        const xConn = backendXInput.connected;
        if (!browserGp && !xConn) return null;

        const xSet = {};
        for (let i = 0; i < backendXInput.buttons.length; i++) {
          xSet[backendXInput.buttons[i]] = true;
        }

        const mergedButtons = [];
        for (let i = 0; i < 16; i++) {
          const bBtn = browserGp && browserGp.buttons && browserGp.buttons[i];
          const bPressed = !!(bBtn && (bBtn.pressed || bBtn.value > 0.5));
          const xName = XINPUT_W3C_ORDER[i];
          const xPressed = !!(xConn && xName && xSet[xName]);
          const isPressed = bPressed || xPressed;
          mergedButtons.push({ pressed: isPressed, value: isPressed ? 1.0 : 0.0 });
        }

        const bAxes = (browserGp && browserGp.axes) || [0, 0, 0, 0];
        const xAxes = xConn
          ? [
              Number(backendXInput.axes.lx) || 0,
              -(Number(backendXInput.axes.ly) || 0),
              Number(backendXInput.axes.rx) || 0,
              -(Number(backendXInput.axes.ry) || 0)
            ]
          : [0, 0, 0, 0];

        const mergedAxes = [0, 0, 0, 0];
        for (let a = 0; a < 4; a++) {
          const ba = Number(bAxes[a]) || 0;
          const xa = Number(xAxes[a]) || 0;
          mergedAxes[a] = Math.abs(ba) >= Math.abs(xa) ? ba : xa;
        }

        return {
          id: (browserGp && browserGp.id) || backendXInput.id || 'XInput Controller',
          connected: true,
          buttons: mergedButtons,
          axes: mergedAxes
        };
      }

      function pollPad() {
        padRaf = requestAnimationFrame(pollPad);
        // 仅当通过大屏启动的游戏正在运行或窗口最小化隐藏时暂停大屏手柄响应（彻底移除导致大屏手柄失灵的 !document.hasFocus() 拦截！）
        if (playSession.value || document.hidden || backendXInput.gameActive) {
          held.buttons = {};
          dirHold.act = null;
          return;
        }
        const gp = buildUnifiedGamepad();
        if (!gp) {
          if (pad.connected) {
            pad.connected = false;
            held.buttons = {};
            dirHold.act = null;
            computeLabels();
          }
          return;
        }
        if (!pad.connected) {
          pad.connected = true;
          pad.id = gp.id || '';
          if (window.AcgDeviceSense) window.AcgDeviceSense.markGamepadActivity(gp);
          computeLabels();
          showToast('手柄已就绪：' + inputStatusText.value, 'success', 2200);
        }

        for (let i = 0; i < gp.buttons.length; i++) {
          const b = gp.buttons[i];
          handleButton(i, !!(b && (b.pressed || b.value > 0.5)), gp);
        }

        const dir = dpadDirection(gp);
        const now = performance.now();
        if (dir !== dirHold.act) {
          dirHold.act = dir;
          if (dir) {
            if (window.AcgDeviceSense) window.AcgDeviceSense.markGamepadActivity(gp);
            onAction(dir);
            dirHold.nextAt = now + 360;
          }
        } else if (dir && now >= dirHold.nextAt) {
          onAction(dir);
          dirHold.nextAt = now + 90;
        }

        if (detailGame.value || reader.value) {
          const ry = gp.axes[3] || 0;
          if (Math.abs(ry) > 0.42) {
            if (window.AcgDeviceSense) window.AcgDeviceSense.markGamepadActivity(gp);
            if (now >= scrollHold.nextAt) {
              const el = reader.value ? readerBody.value : detailTextEl.value;
              if (el) el.scrollBy({ top: (ry > 0 ? 1 : -1) * 110, behavior: 'auto' });
              scrollHold.nextAt = now + 65;
            }
          } else {
            scrollHold.nextAt = 0;
          }
        } else if (!sheet.value && settings.parallax !== false) {
          // 浏览模式下推动手柄右摇杆可实时把玩当前聚焦卡片的 3D 视差倾角与流光折射
          const rx = gp.axes[2] || 0;
          const ry = gp.axes[3] || 0;
          const focusedEl = document.querySelector('.card.is-focused');
          if (focusedEl) {
            if (Math.abs(rx) > 0.15 || Math.abs(ry) > 0.15) {
              focusedEl.style.setProperty('--rx', (-ry * 6.5).toFixed(2) + 'deg');
              focusedEl.style.setProperty('--ry', (rx * 7.5).toFixed(2) + 'deg');
              focusedEl.style.setProperty('--gx', Math.round(((rx + 1) / 2) * 100) + '%');
              focusedEl.style.setProperty('--gy', Math.round(((ry + 1) / 2) * 100) + '%');
            }
          }
        }
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
        if (searchFocused.value) return;
        if (e.key === '/' || (e.ctrlKey && e.code === 'KeyF')) {
          e.preventDefault();
          if (searchInputEl.value) searchInputEl.value.focus();
          return;
        }
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

      function onFullscreenEvent(ev) {
        if (ev && ev.detail && ev.detail.fullscreen !== undefined) {
          isFullscreen.value = !!ev.detail.fullscreen;
        } else {
          isFullscreen.value = !!document.fullscreenElement;
        }
      }

      /* --------------------------------------------------------------- boot */
      watch(function () { return rows.value.map(function (r) { return r.items.length; }).join('|'); }, clampFocus);
      watch(function () { return filter.engine + '|' + filter.status + '|' + filter.sort + '|' + filter.favorite + '|' + filter.translated + '|' + searchQuery.value; }, function () {
        clampFocus();
        if (!tonightGame.value) rerollTonight(true);
      });
      watch(function () { return settings.confirmKey + '|' + pad.family; }, computeLabels);

      onMounted(function () {
        if (window.AcgWindow) {
          window.AcgWindow.mount({
            title: 'ACG Vault v3.4.0 · 大屏模式',
            immersiveBigScreen: true,
            minWidth: 960,
            minHeight: 620
          });
          isFullscreen.value = !!window.AcgWindow.isFullscreen;
        }
        if (window.ACGTheme && window.ACGTheme.setVolumeScale) {
          window.ACGTheme.setVolumeScale(Math.max(0.2, (Number(settings.volume) || 0.3) / 0.3));
        }
        updateCols();
        window.addEventListener('resize', onResize);
        window.addEventListener('keydown', onKeyDown);
        window.addEventListener('acg-fullscreen-changed', onFullscreenEvent);
        document.addEventListener('fullscreenchange', onFullscreenEvent);
        try { window.focus(); } catch (e) {}
        pollBackendXInput();
        const xinputTimer = setInterval(pollBackendXInput, 36);
        window.__bsXinputTimer = xinputTimer;
        runningTimer = setInterval(pollRunning, 2500);
        clockTimer = setInterval(tickClock, 15000);
        padRaf = requestAnimationFrame(pollPad);
        boot();
      });

      onBeforeUnmount(function () {
        window.removeEventListener('resize', onResize);
        window.removeEventListener('keydown', onKeyDown);
        window.removeEventListener('acg-fullscreen-changed', onFullscreenEvent);
        document.removeEventListener('fullscreenchange', onFullscreenEvent);
        if (window.__bsXinputTimer) clearInterval(window.__bsXinputTimer);
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
        filteredGames: filteredGames,
        alphaGroups: alphaGroups,
        activeAlpha: activeAlpha,
        jumpToAlpha: jumpToAlpha,
        searchQuery: searchQuery,
        searchFocused: searchFocused,
        searchInputEl: searchInputEl,
        clearOrBlurSearch: clearOrBlurSearch,
        blurSearchToGrid: blurSearchToGrid,
        clock: clock,
        layout: layout,
        filter: filter,
        settings: settings,
        focus: focus,
        focusHeroBtn: focusHeroBtn,
        gridCols: gridCols,
        scroller: scroller,
        onMainScroll: onMainScroll,
        rows: rows,
        heroGame: heroGame,
        displayHeroGame: displayHeroGame,
        isHeroCompact: isHeroCompact,
        currentRow: currentRow,
        runningMap: runningMap,
        magpie: magpie,
        magpiePresets: magpiePresets,
        themeResolved: themeResolved,
        toggleThemeQuick: toggleThemeQuick,
        flip: flip,
        bgStyle: bgStyle,
        detailGame: detailGame,
        detailStatus: detailStatus,
        detailLoading: detailLoading,
        detailTextEl: detailTextEl,
        detailBgStyle: detailBgStyle,
        detailGallery: detailGallery,
        lightboxOpen: lightboxOpen,
        lightboxIndex: lightboxIndex,
        openLightbox: openLightbox,
        closeLightbox: closeLightbox,
        stepLightbox: stepLightbox,
        sheet: sheet,
        sheetIndex: sheetIndex,
        sheetTitle: sheetTitle,
        sheetRows: sheetRows,
        saveTime: saveTime,
        onCoverImgLoad: onCoverImgLoad,
        isSmartLandscape: isSmartLandscape,
        reader: reader,
        readerBody: readerBody,
        readerTocIndex: readerTocIndex,
        readerCheckedCount: readerCheckedCount,
        jumpReaderToc: jumpReaderToc,
        onReaderBodyClick: onReaderBodyClick,
        toast: toast,
        launching: launching,
        pad: pad,
        inputStatusText: inputStatusText,
        isFullscreen: isFullscreen,
        hints: hints,
        clickHint: clickHint,
        coverUrl: coverUrl,
        thumbUrl: thumbUrl,
        isTranslated: isTranslated,
        gameTitle: gameTitle,
        gameInitials: gameInitials,
        fmtHours: fmtHours,
        parseTags: parseTags,
        voiceActors: voiceActors,
        shortEngine: shortEngine,
        statusLabel: function (s) { return STATUS_LABELS[s] || s || '未玩'; },
        setFocus: setFocus,
        activateCard: function (ri, ci) {
          setFocus(ri, ci);
          const g = rows.value[ri] && rows.value[ri].items[ci];
          if (!g) return;
          if (settings.cardConfirm === 'launch') launch(g);
          else openDetail(g);
        },
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
      favLabel: { type: String, default: 'X' },
      confirmLabel: { type: String, default: 'A' },
      cardAction: { type: String, default: 'detail' },
      isLandscape: { type: Boolean, default: false },
      parallax: { type: Boolean, default: true }
    },
    emits: ['focus', 'activate', 'cover-load'],
    setup: function (props, ctx) {
      const thumb = computed(function () { return thumbUrl(props.game); });
      const title = computed(function () { return gameTitle(props.game); });
      const initials = computed(function () { return gameInitials(props.game); });
      const translated = computed(function () { return isTranslated(props.game); });
      const sub = computed(function () {
        const s = props.game.played_seconds || 0;
        return s > 0 ? '已玩 ' + fmtHours(s) : '尚未开始';
      });
      const tiltStyle = ref({});

      function onCardMove(ev) {
        if (!props.parallax || !ev.currentTarget) return;
        const r = ev.currentTarget.getBoundingClientRect();
        if (!r.width || !r.height) return;
        const nx = ((ev.clientX - r.left) / r.width) * 2 - 1;
        const ny = ((ev.clientY - r.top) / r.height) * 2 - 1;
        tiltStyle.value = {
          '--rx': (-ny * 4.5).toFixed(2) + 'deg',
          '--ry': (nx * 5.5).toFixed(2) + 'deg',
          '--gx': Math.round(((nx + 1) / 2) * 100) + '%',
          '--gy': Math.round(((ny + 1) / 2) * 100) + '%'
        };
      }
      function onCardLeave() {
        tiltStyle.value = {};
      }
      function onImgLoad(ev) {
        ctx.emit('cover-load', ev);
      }

      return {
        thumb: thumb,
        title: title,
        initials: initials,
        translated: translated,
        sub: sub,
        tiltStyle: tiltStyle,
        onCardMove: onCardMove,
        onCardLeave: onCardLeave,
        onImgLoad: onImgLoad
      };
    },
    template:
      '<article class="card" :class="{ \'is-focused\': focused, \'focused\': focused, \'tonight-card\': tonight }" ' +
      ':style="focused ? tiltStyle : null" ' +
      '@mouseenter="$emit(\'focus\')" @mousemove="onCardMove" @mouseleave="onCardLeave" @click="$emit(\'activate\')">' +
        '<div class="card-cover" :class="{ \'is-landscape-smart\': !tonight && isLandscape }">' +
          '<template v-if="thumb">' +
            '<img v-if="!tonight" class="card-cover-ambient" :src="thumb" aria-hidden="true" loading="lazy" decoding="async" draggable="false">' +
            '<img class="card-cover-main" :src="thumb" :alt="title" @load="onImgLoad" loading="lazy" decoding="async" draggable="false">' +
          '</template>' +
          '<div v-else class="hero-fallback">{{ initials }}</div>' +
          '<div class="card-glare" v-if="parallax"></div>' +
          '<div class="card-badges" v-if="!tonight">' +
            '<span class="badge-mini live" v-if="running">● 运行中</span>' +
            '<span class="badge-mini emerald" v-if="translated">汉化</span>' +
            '<span class="badge-mini gold" v-if="game.user_rating">★ {{ game.user_rating }}</span>' +
          '</div>' +
          '<div class="card-focus-pill" v-if="!tonight">' +
            '<span>{{ confirmLabel }} {{ cardAction === \'launch\' ? \'立即启动\' : \'查看详情\' }}</span>' +
          '</div>' +
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
