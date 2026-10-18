const { createApp, ref, shallowRef, reactive, computed, watch, onMounted, nextTick } = Vue;

createApp({
  setup() {
    const games = shallowRef([]);
    const visibleLimit = ref(72);

    const stats = ref({
      total: 0,
      unplayed: 0,
      playing: 0,
      completed: 0,
      dropped: 0,
      backlog: 0,
      favorites: 0,
      duplicates: 0,
      missing: 0,
      has_notes: 0,
      has_walkthrough: 0,
      has_user_notes: 0,
      translated: 0,
      unscraped: 0,
      tools_count: 0,
      total_size_bytes: 0,
      total_size_str: '0 MB',
      total_played_hours: 0,
      total_screenshots: 0,
      cg_unlocked_count: 0
    });

    const filteredStatusCounts = ref(null);
    const runningGames = ref({}); // game_id -> { pid, exe, mode, elapsed_seconds }
    let runningPollTimer = null;

    // Smart & Custom Collections State (v2.3)
    const collections = ref([]);
    const activeCollectionId = ref(null);
    const showCollectionModal = ref(false);
    const collectionForm = reactive({
      id: null,
      name: '',
      icon: 'folder-heart',
      color: 'indigo',
      description: '',
      is_smart: true,
      rules: {
        engine: 'all',
        translated_only: false,
        favorite_only: false,
        has_walkthrough: false,
        cg_unlocked_only: false,
        min_rating: 0,
        min_played_hours: 0,
        min_size_gb: 0,
        play_status: 'all',
        tag: '',
        keyword: ''
      },
      game_ids: []
    });

    // Analytics & Timeline State
    const analyticsData = ref(null);
    const isLoadingAnalytics = ref(false);
    const isExportingPoster = ref(false);

    // Toast Notifications System
    const toasts = ref([]);
    let toastSeq = 0;
    const showToast = (message, type = 'success', duration = 2800) => {
      const id = ++toastSeq;
      toasts.value.push({ id, message, type });
      setTimeout(() => {
        toasts.value = toasts.value.filter(t => t.id !== id);
      }, duration);
    };
    const removeToast = (id) => {
      toasts.value = toasts.value.filter(t => t.id !== id);
    };

    // Coalesced RAF Icon Refresh (Prevents full-DOM jitter during frequent state updates)
    let iconRefreshQueued = false;
    const refreshIcons = () => {
      if (iconRefreshQueued) return;
      iconRefreshQueued = true;
      nextTick(() => {
        requestAnimationFrame(() => {
          iconRefreshQueued = false;
          if (window.lucide) {
            window.lucide.createIcons();
          }
        });
      });
    };

    const triggerGamesRef = () => {
      games.value = [...games.value];
    };

    // Strip heavy walkthrough_md before putting a full game object back into the list cache
    const toLightweightListGame = (existingItem, fullData) => {
      const merged = { ...(existingItem || {}), ...(fullData || {}) };
      const wt = merged.walkthrough_md || '';
      const un = merged.user_notes || '';
      merged.has_walkthrough = wt.replace(/[\r\n\u3000\s]+/g, '').length > 0 ? 1 : (merged.has_walkthrough ? 1 : 0);
      merged.has_user_notes = un.replace(/[\r\n\u3000\s]+/g, '').length > 0 ? 1 : (merged.has_user_notes ? 1 : 0);
      merged.has_notes = (merged.has_walkthrough || merged.has_user_notes) ? 1 : 0;
      merged.walkthrough_length = wt.trim().length || merged.walkthrough_length || 0;
      merged.user_notes_length = un.trim().length || merged.user_notes_length || 0;
      merged.user_notes = un.slice(0, 300);
      delete merged.walkthrough_md;
      return merged;
    };

    const updateGameInList = (fullData) => {
      if (!fullData || !fullData.id) return;
      const idx = games.value.findIndex(g => g.id === fullData.id);
      if (idx !== -1) {
        games.value[idx] = toLightweightListGame(games.value[idx], fullData);
        triggerGamesRef();
      }
    };

    // Convert full cover URL to lightweight WebP thumbnail URL for grid/list views
    const getThumbUrl = (coverUrl) => {
      if (!coverUrl) return '';
      if (coverUrl.startsWith('/api/covers/') && !coverUrl.startsWith('/api/covers/thumb/')) {
        const fname = coverUrl.slice('/api/covers/'.length);
        return `/api/covers/thumb/${fname}`;
      }
      return coverUrl;
    };

    // Custom Glassmorphic Confirmation Dialog
    const confirmDialog = reactive({
      visible: false,
      title: '操作确认',
      message: '',
      confirmText: '确认执行',
      cancelText: '取消',
      variant: 'primary',
      resolveFn: null
    });

    const askConfirm = ({
      title = '操作确认',
      message = '',
      confirmText = '确定',
      cancelText = '取消',
      variant = 'primary'
    }) => {
      return new Promise((resolve) => {
        confirmDialog.title = title;
        confirmDialog.message = message;
        confirmDialog.confirmText = confirmText;
        confirmDialog.cancelText = cancelText;
        confirmDialog.variant = variant;
        confirmDialog.resolveFn = resolve;
        confirmDialog.visible = true;
        refreshIcons();
      });
    };

    const resolveConfirmDialog = (accepted) => {
      confirmDialog.visible = false;
      if (confirmDialog.resolveFn) {
        const fn = confirmDialog.resolveFn;
        confirmDialog.resolveFn = null;
        fn(Boolean(accepted));
      }
    };

    const isLoading = ref(true);
    const viewMode = ref(localStorage.getItem('acg_view_mode') || 'grid'); // 'grid' | 'list' | 'analytics'
    const coverFitMode = ref(localStorage.getItem('acg_cover_fit') || 'smart'); // 'smart' | 'portrait' | 'landscape'
    const gridDensity = ref(localStorage.getItem('acg_grid_density') || 'standard'); // 'compact' | 'standard' | 'comfortable'
    const cardHoverStyle = ref(localStorage.getItem('acg_card_hover') || 'minimal'); // 'minimal' | 'classic'
    const notesFontSize = ref(localStorage.getItem('acg_notes_font') || 'md'); // 'sm' | 'md' | 'lg'

    const searchKeyword = ref('');
    const searchInputRef = ref(null);
    const currentStatus = ref('all');
    const favoriteOnly = ref(false);
    const missingOnly = ref(false);
    const showToolsOnly = ref(false);
    const hasNotesOnly = ref(false);
    const unscrapedOnly = ref(false);
    const engineFilter = ref('all');
    const transFilter = ref('all'); // 'all' | 'translated' | 'raw'
    const sortBy = ref(localStorage.getItem('acg_sort_by') || 'downloaded_at');
    const sortOrder = ref(localStorage.getItem('acg_sort_order') || 'desc');

    const activeCollection = computed(() => {
      if (!activeCollectionId.value) return null;
      return collections.value.find(c => c.id === activeCollectionId.value) || null;
    });

    const filteredGames = computed(() => {
      if (!activeCollection.value) return games.value;
      const idSet = new Set(activeCollection.value.game_ids || []);
      return games.value.filter(g => idSet.has(g.id));
    });

    const displayedGames = computed(() => {
      return filteredGames.value.slice(0, visibleLimit.value);
    });

    const loadMoreGames = () => {
      if (visibleLimit.value < filteredGames.value.length) {
        visibleLimit.value += 72;
        refreshIcons();
      }
    };

    const hasActiveSubFilters = computed(() => {
      return Boolean(
        searchKeyword.value.trim() ||
        favoriteOnly.value ||
        missingOnly.value ||
        showToolsOnly.value ||
        hasNotesOnly.value ||
        unscrapedOnly.value ||
        activeCollectionId.value !== null ||
        engineFilter.value !== 'all' ||
        transFilter.value !== 'all'
      );
    });

    // Fullscreen Walkthrough Workspace states (v2.3: exclusively targets walkthrough_md)
    const showNotesFullscreen = ref(false);
    const notesFullscreenLayout = ref('split'); // 'split' | 'reader' | 'editor'
    const showNotesToc = ref(true);
    const notesSaveStatus = ref('saved'); // 'saved' | 'saving' | 'dirty'
    const personalMemoSaveStatus = ref('saved'); // 'saved' | 'saving' | 'dirty'
    const notesTocList = ref([]);
    const debouncedNotesHtml = ref('');
    const tocSearchQuery = ref('');
    const activeHeadingId = ref('');
    const syncScrollEnabled = ref(true);
    const isBrowserFullscreen = ref(false);
    const splitLeftWidthPct = ref(50);
    const isDraggingSplit = ref(false);
    let notesAutoSaveTimer = null;
    let personalMemoTimer = null;
    let notesRenderTimer = null;
    let activeScrollPane = null;
    let scrollLockTimer = null;

    const filteredTocList = computed(() => {
      const q = tocSearchQuery.value.trim().toLowerCase();
      if (!q) return notesTocList.value;
      return notesTocList.value.filter(item => item.title.toLowerCase().includes(q));
    });

    // Selected game & Detail Drawer 3-Tab state
    const selectedGame = ref(null);
    const drawerActiveTab = ref('overview'); // 'overview' | 'walkthrough' | 'engineering'
    const selectedGameVariants = ref([]);
    const selectedGameMTool = ref(null);
    const selectedGameSave = ref(null);
    const selectedGameScreenshots = ref([]);
    const lightboxShot = ref(null);
    const isCapturingScreenshot = ref(false);
    const screenshotFileInput = ref(null);
    const cgSaveFileInput = ref(null);
    const isUnlockingCG = ref(false);
    const isGeneratingGuide = ref(false);
    const isParsingFolderAI = ref(false);
    const isLocalizingTags = ref(false);

    const showSaveBackupsList = ref(false);
    const isBackingUpSave = ref(false);
    const isRestoringSave = ref(false);
    const isSyncingWebDAV = ref(false);

    // RPG Maker Visual Save Editor states (v2.4)
    const showSaveEditorPanel = ref(false);
    const saveEditorData = ref({ supported: false, slots: [] });
    const selectedSaveSlotFile = ref('');
    const saveSlotDetail = ref(null);
    const isLoadingSaveSlot = ref(false);
    const isSavingSaveSlot = ref(false);
    const saveEditorSearchQuery = ref('');
    const saveEditorKeyOnly = ref(false);
    const saveEditorUnlockAllSwitches = ref(false);
    const modifiedSaveVars = ref({});
    const modifiedSaveSwitches = ref({});

    // Ignored Scan Paths & Archived Duplicates states (v2.4)
    const ignoredPathsList = ref([]);
    const archivedGamesList = ref([]);
    const showRescrapePanel = ref(false);
    const showDangerMenu = ref(false);
    const isScrapingSingle = ref(false);
    const scrapeInputRJ = ref('');
    const scrapeInputKeyword = ref('');
    const scrapePreferredSource = ref('auto');

    // Interactive User Tags in Detail Drawer
    const showAddUserTag = ref(false);
    const newUserTagInput = ref('');

    const currentGameIndex = computed(() => {
      if (!selectedGame.value || !filteredGames.value.length) return -1;
      return filteredGames.value.findIndex(g => g.id === selectedGame.value.id);
    });

    const navigateAdjacentGame = (delta) => {
      if (!selectedGame.value || isEditMode.value) return;
      const idx = currentGameIndex.value;
      if (idx === -1) return;
      const targetIdx = idx + delta;
      if (targetIdx >= 0 && targetIdx < filteredGames.value.length) {
        openGameDetail(filteredGames.value[targetIdx]);
      }
    };

    // Manual Edit Mode states & Dirty checking
    const isEditMode = ref(false);
    const isUploadingCover = ref(false);
    const coverFileInput = ref(null);
    let editFormSnapshot = '';

    const editForm = reactive({
      display_title: '',
      original_title: '',
      circle_name: '',
      release_date: '',
      downloaded_at: '',
      cover_url: '',
      executable_path: '',
      synopsis: '',
      user_notes: '',
      rj_code: '',
      has_translation: 0
    });
    const editTagsList = ref([]);
    const editUserTagsList = ref([]);
    const newEditTagInput = ref('');
    const newEditUserTagInput = ref('');
    const editTagsString = ref('');
    const editVoiceActorsString = ref('');

    // Scraper Candidates Picker modal
    const showCandidateModal = ref(false);
    const isSearchingCandidates = ref(false);
    const scraperCandidates = ref([]);

    // Batch management
    const isBatchMode = ref(false);
    const selectedGameIds = ref([]);

    // Modals & background status
    const showDuplicateModal = ref(false);
    const duplicateGroups = ref({});
    const focusedDuplicateGroupId = ref('');
    const showSettingsModal = ref(false);
    const settingsActiveTab = ref('dirs'); // 'dirs' | 'ui' | 'ai' | 'desktop'
    const showShortcutModal = ref(false);
    const isTestingProxy = ref(false);
    const proxyTestResults = ref([]);
    const isTestingLLM = ref(false);
    const isTestingWebDAV = ref(false);

    const configData = ref({
      game_directories: ['E:\\ACG'],
      archive_directory: 'E:\\ACG\\_Archive_Duplicates',
      save_backup_directory: 'E:\\ACG\\_Save_Backups',
      mtool_directory: 'E:\\ACG\\MTool',
      leproc_path: '',
      proxy: '',
      auto_scrape: true,
      scrape_source: 'auto',
      incremental_scan: true,
      auto_localize_tags: true,
      default_view_mode: 'grid',
      cover_fit_mode: 'smart',
      grid_density: 'standard',
      card_hover_style: 'minimal',
      notes_default_layout: 'split',
      notes_default_toc: true,
      notes_sync_scroll: true,
      notes_font_size: 'md',
      clear_batch_on_filter: true,
      port: 8000,
      desktop_mode: 'native',
      minimize_to_tray: true,
      auto_start_windows: false,
      global_boss_hotkey: 'Alt+Space',
      global_overlay_hotkey: 'Alt+G',
      enable_ingame_screenshot: true,
      screenshot_hotkey: 'F12',
      enable_auto_save_backup: true,
      auto_backup_min_minutes: 5,
      auto_backup_max_keep: 5,
      webdav_enabled: false,
      webdav_url: '',
      webdav_root_path: '/ACG_Vault_Saves',
      webdav_username: '',
      webdav_password: '',
      webdav_auto_sync: true,
      llm_enabled: false,
      llm_api_base: 'https://api.deepseek.com/v1',
      llm_api_key: '',
      llm_model: 'deepseek-chat',
      llm_temperature: 0.3,
      llm_auto_translate: true
    });

    const scanState = ref({
      is_running: false,
      progress: 0,
      total: 0,
      current_folder: '',
      status_message: 'Idle'
    });

    const batchScrapeState = ref({
      is_running: false,
      current_index: 0,
      total: 0,
      status_message: 'Idle'
    });

    const statusTabs = [
      { label: '全部', value: 'all', dot: '' },
      { label: '未玩', value: 'unplayed', dot: 'bg-slate-400' },
      { label: '游玩中', value: 'playing', dot: 'bg-amber-400' },
      { label: '已通关', value: 'completed', dot: 'bg-emerald-400' },
      { label: '想玩', value: 'backlog', dot: 'bg-purple-400' },
      { label: '搁置', value: 'dropped', dot: 'bg-rose-500' }
    ];

    const gridColumnsClass = computed(() => {
      const d = gridDensity.value || 'standard';
      if (coverFitMode.value === 'landscape') {
        if (d === 'compact') return 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7 gap-4';
        if (d === 'comfortable') return 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-6';
        return 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-5';
      }
      if (d === 'compact') return 'grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-7 2xl:grid-cols-8 gap-3.5';
      if (d === 'comfortable') return 'grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6';
      return 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7 gap-5';
    });

    const setViewMode = (mode) => {
      viewMode.value = mode;
      localStorage.setItem('acg_view_mode', mode);
      if (mode === 'analytics') {
        fetchAnalytics();
      }
      refreshIcons();
    };

    const cycleCoverFitMode = () => {
      const order = ['smart', 'portrait', 'landscape'];
      const next = order[(order.indexOf(coverFitMode.value) + 1) % order.length];
      coverFitMode.value = next;
      localStorage.setItem('acg_cover_fit', next);
      const labels = {
        smart: '智能模糊自适应 (完整保留横竖立绘)',
        portrait: '3:4 经典竖版海报',
        landscape: '4:3 同人横版海报 (适合 DLsite/Steam)'
      };
      showToast(`封面显示已切换为: ${labels[next]}`, 'info', 2000);
    };

    const cycleGridDensity = () => {
      const order = ['compact', 'standard', 'comfortable'];
      const next = order[(order.indexOf(gridDensity.value) + 1) % order.length];
      gridDensity.value = next;
      localStorage.setItem('acg_grid_density', next);
      const labels = { compact: '紧凑高密墙', standard: '标准平衡', comfortable: '宽松大尺寸海报' };
      showToast(`网格密度已切换为: ${labels[next]}`, 'info', 1800);
    };

    const formatEngineShort = (eng) => {
      if (!eng) return 'PC';
      if (eng.includes('RPG Maker MZ')) return 'RMMZ';
      if (eng.includes('RPG Maker MV')) return 'RMMV';
      if (eng.includes('RPG Maker VX')) return 'RMVX';
      if (eng.includes('RPG Maker XP')) return 'RMXP';
      if (eng.includes('RPG Maker')) return 'RPGM';
      if (eng.includes('Kirikiri')) return 'KRKR';
      if (eng.includes('Unity')) return 'UNITY';
      if (eng.includes('Wolf')) return 'WOLF';
      if (eng.includes('Ren\'Py')) return 'RENPY';
      if (eng.includes('Unreal')) return 'UE';
      if (eng.includes('Godot')) return 'GODOT';
      return eng.slice(0, 7).toUpperCase();
    };

    const getEngineBadgeColor = (eng) => {
      if (!eng) return 'text-slate-200';
      if (eng.includes('RPG Maker MZ')) return 'text-indigo-300';
      if (eng.includes('RPG Maker MV')) return 'text-sky-300';
      if (eng.includes('RPG Maker')) return 'text-purple-300';
      if (eng.includes('Unity')) return 'text-cyan-300';
      if (eng.includes('Kirikiri')) return 'text-pink-300';
      if (eng.includes('Wolf')) return 'text-amber-300';
      if (eng.includes("Ren'Py")) return 'text-rose-300';
      return 'text-slate-200';
    };

    const getCardSmartSlotItems = (game) => {
      if (!game) return { type: 'none', items: [] };
      const playedSec = Number(game.played_seconds || 0);
      const preferPlaytime = sortBy.value === 'play_time' || sortBy.value === 'last_played' || configData.value.card_footer_slot === 'playtime';
      if (preferPlaytime && playedSec >= 60) {
        const label = playedSec >= 3600 ? `${(playedSec / 3600).toFixed(1)}h` : `${Math.floor(playedSec / 60)}m`;
        return { type: 'playtime', label };
      }
      const uTags = Array.isArray(game.user_tags) ? game.user_tags : [];
      const oTags = Array.isArray(game.tags) ? game.tags : [];
      const combined = [];
      for (const ut of uTags) {
        if (ut && combined.length < 2) {
          combined.push({ raw: ut, text: `★ ${ut}`, isUser: true });
        }
      }
      for (const ot of oTags) {
        if (ot && combined.length < 2 && !uTags.includes(ot)) {
          combined.push({ raw: ot, text: `#${ot}`, isUser: false });
        }
      }
      if (combined.length > 0) {
        return { type: 'tags', items: combined };
      }
      if (playedSec >= 60) {
        const label = playedSec >= 3600 ? `${(playedSec / 3600).toFixed(1)}h` : `${Math.floor(playedSec / 60)}m`;
        return { type: 'playtime', label };
      }
      return { type: 'none', items: [] };
    };

    const formatPlayedTime = (seconds) => {
      if (!seconds || seconds < 60) return '尚未记录';
      const mins = Math.floor(seconds / 60);
      if (mins < 60) return `${mins} 分钟`;
      const hrs = (seconds / 3600).toFixed(1);
      return `${hrs} 小时`;
    };

    const formatRunningDuration = (seconds) => {
      const s = Math.max(0, parseInt(seconds || 0, 10));
      const mins = Math.floor(s / 60);
      const rem = s % 60;
      if (mins >= 60) {
        const hrs = Math.floor(mins / 60);
        const rmins = mins % 60;
        return `${hrs}h ${rmins}m`;
      }
      return `${mins}:${String(rem).padStart(2, '0')}`;
    };

    const isGameRunning = (gameId) => {
      return Boolean(runningGames.value && (runningGames.value[gameId] || runningGames.value[String(gameId)]));
    };

    const getGameRunningInfo = (gameId) => {
      if (!runningGames.value) return null;
      return runningGames.value[gameId] || runningGames.value[String(gameId)] || null;
    };

    const hasGameWalkthrough = (game) => {
      if (!game) return false;
      if (game.has_walkthrough !== undefined) return Boolean(game.has_walkthrough);
      if (game.walkthrough_md !== undefined) return Boolean(game.walkthrough_md && game.walkthrough_md.replace(/[\r\n\u3000\s]+/g, '').length > 0);
      return Boolean(game.has_notes);
    };

    const hasPersonalMemo = (game) => {
      if (!game) return false;
      if (game.has_user_notes !== undefined) return Boolean(game.has_user_notes);
      return Boolean(game.user_notes && game.user_notes.replace(/[\r\n\u3000\s]+/g, '').length > 0);
    };

    const startRunningGamesPoll = () => {
      if (runningPollTimer) return;
      runningPollTimer = setInterval(async () => {
        try {
          const res = await fetch('/api/games/running');
          const data = await res.json();
          const prevCount = Object.keys(runningGames.value || {}).length;
          const nextMap = data.running_games || {};
          const nextCount = Object.keys(nextMap).length;
          runningGames.value = nextMap;

          if (prevCount > 0 && nextCount < prevCount) {
            fetchStats();
            fetchGames(true);
            if (selectedGame.value) {
              openGameDetail(selectedGame.value, true);
            }
            showToast('游戏已退出，游玩时长与自动存档快照已同步', 'info', 2800);
          }
          if (nextCount === 0) {
            clearInterval(runningPollTimer);
            runningPollTimer = null;
          }
        } catch (e) {
          clearInterval(runningPollTimer);
          runningPollTimer = null;
        }
      }, 3000);
    };

    const getStatusLabel = (status) => {
      switch (status) {
        case 'unplayed': return '未玩';
        case 'playing': return '游玩中';
        case 'completed': return '已通关';
        case 'dropped': return '搁置';
        case 'backlog': return '想玩';
        default: return '未知';
      }
    };

    const getStatusDotColor = (status) => {
      switch (status) {
        case 'unplayed': return 'bg-slate-400';
        case 'playing': return 'bg-amber-400 animate-pulse';
        case 'completed': return 'bg-emerald-400';
        case 'dropped': return 'bg-rose-500';
        case 'backlog': return 'bg-purple-400';
        default: return 'bg-slate-500';
      }
    };

    const getStatusBadgeClass = (status) => {
      switch (status) {
        case 'unplayed': return 'bg-slate-700 text-white font-bold shadow-sm';
        case 'playing': return 'bg-amber-500 text-black font-bold shadow-sm shadow-amber-500/30';
        case 'completed': return 'bg-emerald-500 text-white font-bold shadow-sm shadow-emerald-500/30';
        case 'dropped': return 'bg-rose-500 text-white font-bold shadow-sm shadow-rose-500/30';
        case 'backlog': return 'bg-purple-500 text-white font-bold shadow-sm shadow-purple-500/30';
        default: return 'bg-slate-700 text-white';
      }
    };

    const getStatusCount = (status) => {
      if (hasActiveSubFilters.value && filteredStatusCounts.value && filteredStatusCounts.value[status] !== undefined) {
        return filteredStatusCounts.value[status];
      }
      if (status === 'all') return stats.value.total;
      return stats.value[status] || 0;
    };

    const fetchGames = async (silent = false) => {
      if (!silent && games.value.length === 0) isLoading.value = true;
      visibleLimit.value = 72;
      localStorage.setItem('acg_sort_by', sortBy.value);
      localStorage.setItem('acg_sort_order', sortOrder.value);
      try {
        const params = new URLSearchParams({
          status: currentStatus.value,
          keyword: searchKeyword.value,
          favorite_only: favoriteOnly.value,
          missing_only: missingOnly.value,
          is_tool: showToolsOnly.value,
          has_notes_only: hasNotesOnly.value,
          unscraped_only: unscrapedOnly.value,
          engine_filter: engineFilter.value,
          trans_filter: transFilter.value,
          sort_by: sortBy.value,
          sort_order: sortOrder.value
        });
        const res = await fetch(`/api/games?${params.toString()}`);
        const data = await res.json();
        const loadedGames = data.data || [];
        games.value = loadedGames;

        if (isBatchMode.value && selectedGameIds.value.length > 0 && configData.value.clear_batch_on_filter !== false) {
          const visibleSet = new Set(loadedGames.map(g => g.id));
          const filteredSelected = selectedGameIds.value.filter(id => visibleSet.has(id));
          if (filteredSelected.length !== selectedGameIds.value.length) {
            selectedGameIds.value = filteredSelected;
          }
        }

        if (data.status_counts) {
          filteredStatusCounts.value = data.status_counts;
        }
        if (data.running_games) {
          runningGames.value = data.running_games;
          if (Object.keys(data.running_games).length > 0) {
            startRunningGamesPoll();
          }
        }
      } catch (err) {
        console.error('Failed to load games:', err);
        if (!silent) showToast('加载游戏库失败: ' + err, 'error');
      } finally {
        isLoading.value = false;
        refreshIcons();
      }
    };

    const fetchStats = async () => {
      try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        stats.value = data;
        if (data.running_games) {
          runningGames.value = data.running_games;
          if (Object.keys(data.running_games).length > 0) {
            startRunningGamesPoll();
          }
        }
      } catch (err) {
        console.error('Failed to load stats:', err);
      }
    };

    const fetchCollections = async () => {
      try {
        const res = await fetch('/api/collections');
        const data = await res.json();
        collections.value = data.collections || [];
      } catch (err) {
        console.error('Failed to load collections:', err);
      }
    };

    const selectCollectionFilter = (col) => {
      if (!col) {
        activeCollectionId.value = null;
        return;
      }
      if (activeCollectionId.value === col.id) {
        activeCollectionId.value = null;
      } else {
        activeCollectionId.value = col.id;
        if (viewMode.value === 'analytics') {
          viewMode.value = 'grid';
        }
      }
      visibleLimit.value = 72;
      refreshIcons();
    };

    const openCreateCollectionModal = () => {
      collectionForm.id = null;
      collectionForm.name = '';
      collectionForm.icon = 'folder-heart';
      collectionForm.color = 'indigo';
      collectionForm.description = '';
      collectionForm.is_smart = true;
      collectionForm.rules = {
        engine: 'all',
        translated_only: false,
        favorite_only: false,
        has_walkthrough: false,
        cg_unlocked_only: false,
        min_rating: 0,
        min_played_hours: 0,
        min_size_gb: 0,
        play_status: 'all',
        tag: '',
        keyword: ''
      };
      collectionForm.game_ids = [];
      showCollectionModal.value = true;
      refreshIcons();
    };

    const openEditCollectionModal = (col) => {
      if (!col) return;
      collectionForm.id = col.id;
      collectionForm.name = col.name || '';
      collectionForm.icon = col.icon || 'folder-heart';
      collectionForm.color = col.color || 'indigo';
      collectionForm.description = col.description || '';
      collectionForm.is_smart = Boolean(col.is_smart);
      collectionForm.rules = {
        engine: col.rules?.engine || 'all',
        translated_only: Boolean(col.rules?.translated_only),
        favorite_only: Boolean(col.rules?.favorite_only),
        has_walkthrough: Boolean(col.rules?.has_walkthrough),
        cg_unlocked_only: Boolean(col.rules?.cg_unlocked_only),
        min_rating: parseInt(col.rules?.min_rating || 0, 10),
        min_played_hours: parseFloat(col.rules?.min_played_hours || 0),
        min_size_gb: parseFloat(col.rules?.min_size_gb || 0),
        play_status: col.rules?.play_status || 'all',
        tag: col.rules?.tag || '',
        keyword: col.rules?.keyword || ''
      };
      collectionForm.game_ids = [...(col.manual_game_ids || [])];
      showCollectionModal.value = true;
      refreshIcons();
    };

    const saveCollectionAction = async () => {
      if (!collectionForm.name.trim()) {
        showToast('请输入合集名称', 'warning');
        return;
      }
      try {
        const res = await fetch('/api/collections', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: collectionForm.id,
            name: collectionForm.name.trim(),
            icon: collectionForm.icon,
            color: collectionForm.color,
            description: collectionForm.description,
            is_smart: collectionForm.is_smart,
            rules: collectionForm.rules,
            game_ids: collectionForm.game_ids
          })
        });
        const data = await res.json();
        if (data.success) {
          collections.value = data.collections || [];
          showCollectionModal.value = false;
          showToast(`合集「${collectionForm.name}」已保存！`, 'success');
        }
      } catch (err) {
        showToast('保存合集失败: ' + err, 'error');
      }
    };

    const deleteCollectionAction = async (col) => {
      if (!col) return;
      const ok = await askConfirm({
        title: '删除馆藏合集',
        message: `确定要删除合集「${col.name}」吗？（不会影响合集内的任何游戏记录）`,
        confirmText: '确认删除',
        cancelText: '取消',
        variant: 'danger'
      });
      if (!ok) return;
      try {
        const res = await fetch(`/api/collections/${col.id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
          collections.value = data.collections || [];
          if (activeCollectionId.value === col.id) {
            activeCollectionId.value = null;
          }
          showCollectionModal.value = false;
          showToast('合集已删除', 'info');
        }
      } catch (err) {
        showToast('删除合集失败: ' + err, 'error');
      }
    };

    const toggleGameInManualCollection = async (col, gameId) => {
      if (!col || col.is_smart || !gameId) return;
      const isPresent = (col.game_ids || []).includes(gameId);
      const action = isPresent ? 'remove' : 'add';
      try {
        const res = await fetch(`/api/collections/${col.id}/games`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ game_ids: [gameId], action })
        });
        const data = await res.json();
        if (data.success) {
          collections.value = data.collections || [];
          showToast(isPresent ? `已从「${col.name}」移除` : `已加入合集「${col.name}」`, 'info', 1600);
        }
      } catch (err) {
        showToast('更新合集失败', 'error');
      }
    };

    const batchAddToCollectionAction = async (colId) => {
      if (!colId || selectedGameIds.value.length === 0) return;
      try {
        const res = await fetch(`/api/collections/${colId}/games`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ game_ids: selectedGameIds.value, action: 'add' })
        });
        const data = await res.json();
        if (data.success) {
          collections.value = data.collections || [];
          showToast(`已将 ${selectedGameIds.value.length} 部游戏加入合集！`, 'success');
        }
      } catch (err) {
        showToast('批量加入合集失败', 'error');
      }
    };

    const fetchAnalytics = async () => {
      isLoadingAnalytics.value = true;
      try {
        const res = await fetch('/api/analytics');
        const data = await res.json();
        analyticsData.value = data;
      } catch (err) {
        showToast('加载数据统计看板失败: ' + err, 'error');
      } finally {
        isLoadingAnalytics.value = false;
        refreshIcons();
      }
    };

    // High-DPI HTML5 Canvas Poster Exporter for Analytics & Timeline (v2.3)
    const exportAnalyticsPosterAction = async () => {
      if (!analyticsData.value) return;
      isExportingPoster.value = true;
      try {
        const d = analyticsData.value;
        const ov = d.overview || {};
        const scale = 2;
        const width = 1280;
        const height = 1660;
        const canvas = document.createElement('canvas');
        canvas.width = width * scale;
        canvas.height = height * scale;
        const ctx = canvas.getContext('2d');
        ctx.scale(scale, scale);

        const drawRoundRect = (x, y, w, h, r, fill, stroke) => {
          ctx.beginPath();
          ctx.moveTo(x + r, y);
          ctx.arcTo(x + w, y, x + w, y + h, r);
          ctx.arcTo(x + w, y + h, x, y + h, r);
          ctx.arcTo(x, y + h, x, y, r);
          ctx.arcTo(x, y, x + w, y, r);
          ctx.closePath();
          if (fill) { ctx.fillStyle = fill; ctx.fill(); }
          if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke(); }
        };

        // Background Gradient
        const bgGrad = ctx.createLinearGradient(0, 0, 0, height);
        bgGrad.addColorStop(0, '#070a14');
        bgGrad.addColorStop(0.5, '#0c1326');
        bgGrad.addColorStop(1, '#070a14');
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, width, height);

        // Ambient Top Glows
        const rad1 = ctx.createRadialGradient(200, 80, 10, 200, 80, 480);
        rad1.addColorStop(0, 'rgba(99, 102, 241, 0.24)');
        rad1.addColorStop(1, 'transparent');
        ctx.fillStyle = rad1;
        ctx.fillRect(0, 0, width, 600);

        const rad2 = ctx.createRadialGradient(1080, 120, 10, 1080, 120, 450);
        rad2.addColorStop(0, 'rgba(236, 72, 153, 0.18)');
        rad2.addColorStop(1, 'transparent');
        ctx.fillStyle = rad2;
        ctx.fillRect(0, 0, width, 600);

        // Header Banner
        drawRoundRect(48, 42, width - 96, 110, 22, 'rgba(19, 27, 46, 0.92)', 'rgba(99, 102, 241, 0.4)');
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 30px "Microsoft YaHei", sans-serif';
        ctx.fillText('🎮 ACG Vault v2.4 · 个人游戏馆藏与通关总结长图', 80, 92);
        ctx.fillStyle = '#94a3b8';
        ctx.font = '15px "Microsoft YaHei", sans-serif';
        const nowStr = new Date().toISOString().slice(0, 10);
        ctx.fillText(`生成日期: ${nowStr}   |   本地 ACG 游戏资产、AI 全结局攻略与数据馆藏中心`, 80, 125);

        // 6 KPI Cards
        const kpis = [
          { label: '馆藏游戏总数', val: `${ov.total || 0} 部`, sub: `精选收藏 ${ov.favorites || 0} 部`, color: '#818cf8' },
          { label: '总资产占用空间', val: ov.total_size_str || '0 GB', sub: '本地高速存储', color: '#22d3ee' },
          { label: '累计游玩时长', val: `${ov.total_played_hours || 0} h`, sub: `珍藏截图 ${ov.total_screenshots || 0} 张`, color: '#fbbf24' },
          { label: '通关达成率', val: `${ov.completion_rate || 0}%`, sub: `已通关 ${ov.completed || 0} 部`, color: '#34d399' },
          { label: '汉化覆盖率', val: `${ov.translation_rate || 0}%`, sub: `已汉化 ${ov.translated || 0} 部`, color: '#2dd4bf' },
          { label: '全结局攻略 & 全CG', val: `${ov.has_walkthrough || ov.has_notes || 0} 篇`, sub: `全CG解锁 ${ov.cg_unlocked_count || 0} 部`, color: '#f472b6' }
        ];
        const kpiW = (width - 96 - 50) / 6;
        kpis.forEach((k, idx) => {
          const kx = 48 + idx * (kpiW + 10);
          const ky = 176;
          drawRoundRect(kx, ky, kpiW, 108, 16, 'rgba(15, 23, 42, 0.9)', 'rgba(71, 85, 105, 0.5)');
          ctx.fillStyle = '#94a3b8';
          ctx.font = '13px "Microsoft YaHei", sans-serif';
          ctx.fillText(k.label, kx + 16, ky + 30);
          ctx.fillStyle = k.color;
          ctx.font = 'bold 24px monospace, "Microsoft YaHei"';
          ctx.fillText(k.val, kx + 16, ky + 66);
          ctx.fillStyle = '#64748b';
          ctx.font = '12px "Microsoft YaHei", sans-serif';
          ctx.fillText(k.sub, kx + 16, ky + 92);
        });

        // Row 1 Left: Play Time Distribution & Engine Breakdown
        drawRoundRect(48, 308, 576, 460, 20, 'rgba(15, 23, 42, 0.88)', 'rgba(51, 65, 85, 0.65)');
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 18px "Microsoft YaHei", sans-serif';
        ctx.fillText('🔥 游玩深度分布 & 驱动引擎占比', 74, 346);

        (d.play_time_buckets || []).forEach((b, i) => {
          const by = 376 + i * 38;
          ctx.fillStyle = '#cbd5e1';
          ctx.font = '13px "Microsoft YaHei", sans-serif';
          ctx.fillText(b.label, 74, by);
          ctx.fillStyle = '#94a3b8';
          ctx.fillText(`${b.count} 部 (${b.percentage}%)`, 480, by);
          drawRoundRect(74, by + 8, 520, 8, 4, '#1e293b', null);
          const fillW = Math.max(8, (b.percentage / 100) * 520);
          drawRoundRect(74, by + 8, fillW, 8, 4, b.color || '#6366f1', null);
        });

        ctx.fillStyle = '#a5b4fc';
        ctx.font = 'bold 15px "Microsoft YaHei", sans-serif';
        ctx.fillText('⚙️ 主流游戏引擎分布 Top 5', 74, 592);
        (d.engine_breakdown || []).slice(0, 5).forEach((eng, i) => {
          const ey = 622 + i * 28;
          ctx.fillStyle = '#e2e8f0';
          ctx.font = '13px "Microsoft YaHei", sans-serif';
          ctx.fillText(`${eng.engine}`, 74, ey);
          ctx.fillStyle = '#94a3b8';
          ctx.fillText(`${eng.count} 部 · ${eng.size_str} · 汉化 ${eng.translated_pct}%`, 340, ey);
        });

        // Row 1 Right: Hall of Fame Top Played Games
        drawRoundRect(648, 308, 584, 460, 20, 'rgba(15, 23, 42, 0.88)', 'rgba(51, 65, 85, 0.65)');
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 18px "Microsoft YaHei", sans-serif';
        ctx.fillText('👑 殿堂级最长游玩排行 Top 8', 674, 346);

        const topPlayed = (d.top_played_games || []).slice(0, 8);
        if (topPlayed.length === 0) {
          ctx.fillStyle = '#64748b';
          ctx.font = '14px "Microsoft YaHei", sans-serif';
          ctx.fillText('暂无游玩时长记录，启动任意游戏即可自动统计', 674, 420);
        } else {
          topPlayed.forEach((g, idx) => {
            const gy = 374 + idx * 46;
            drawRoundRect(674, gy, 532, 38, 10, 'rgba(30, 41, 59, 0.55)', null);
            ctx.fillStyle = idx < 3 ? '#fbbf24' : '#64748b';
            ctx.font = 'bold 14px monospace';
            ctx.fillText(`#${idx + 1}`, 688, gy + 24);
            ctx.fillStyle = '#f1f5f9';
            ctx.font = 'bold 13px "Microsoft YaHei", sans-serif';
            const titleShort = (g.display_title || '').slice(0, 24);
            ctx.fillText(titleShort, 724, gy + 24);
            ctx.fillStyle = '#fbbf24';
            ctx.font = 'bold 13px monospace';
            ctx.fillText(`${g.played_hours}h (${g.play_count}次)`, 1080, gy + 24);
          });
        }

        // Row 2 Left: Top Circles & Popular Tags
        drawRoundRect(48, 792, 576, 420, 20, 'rgba(15, 23, 42, 0.88)', 'rgba(51, 65, 85, 0.65)');
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 18px "Microsoft YaHei", sans-serif';
        ctx.fillText('🏢 最爱同人社团 / 开发商 Top 8', 74, 830);

        (d.top_circles || []).slice(0, 8).forEach((cir, idx) => {
          const cy = 862 + idx * 38;
          ctx.fillStyle = '#e2e8f0';
          ctx.font = '13px "Microsoft YaHei", sans-serif';
          ctx.fillText(`${idx + 1}. ${(cir.name || '').slice(0, 22)}`, 74, cy);
          ctx.fillStyle = '#818cf8';
          ctx.font = 'bold 13px monospace';
          ctx.fillText(`${cir.count} 部 (汉化 ${cir.translated_count} 部)`, 420, cy);
        });

        // Row 2 Right: 12-Month Trend & Popular Tags Cloud
        drawRoundRect(648, 792, 584, 420, 20, 'rgba(15, 23, 42, 0.88)', 'rgba(51, 65, 85, 0.65)');
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 18px "Microsoft YaHei", sans-serif';
        ctx.fillText('📅 近 12 个月入库与游玩活跃趋势', 674, 830);

        const months = d.monthly_activity || [];
        const chartBaseY = 995;
        const chartMaxH = 120;
        const colStep = 520 / Math.max(1, months.length);
        months.forEach((m, idx) => {
          const mx = 682 + idx * colStep;
          const addH = m.added_count > 0 ? Math.max(6, (m.added_pct / 100) * chartMaxH) : 2;
          const playH = m.played_count > 0 ? Math.max(6, (m.played_pct / 100) * chartMaxH) : 2;
          drawRoundRect(mx, chartBaseY - addH, 10, addH, 3, m.added_count > 0 ? '#6366f1' : '#334155', null);
          drawRoundRect(mx + 12, chartBaseY - playH, 10, playH, 3, m.played_count > 0 ? '#10b981' : '#334155', null);
          ctx.fillStyle = '#94a3b8';
          ctx.font = '11px monospace';
          ctx.fillText(m.month.slice(5) + '月', mx - 2, chartBaseY + 18);
        });

        ctx.fillStyle = '#f472b6';
        ctx.font = 'bold 15px "Microsoft YaHei", sans-serif';
        ctx.fillText('🏷️ 核心偏好标签 Top 12', 674, 1055);
        const tagStr = (d.top_tags || []).slice(0, 12).map(t => `#${t.name}(${t.count})`).join('   ');
        ctx.fillStyle = '#cbd5e1';
        ctx.font = '13px "Microsoft YaHei", sans-serif';
        ctx.fillText(tagStr.slice(0, 48), 674, 1090);
        if (tagStr.length > 48) {
          ctx.fillText(tagStr.slice(48, 96), 674, 1118);
        }
        if (tagStr.length > 96) {
          ctx.fillText(tagStr.slice(96, 144), 674, 1146);
        }

        // Row 3: Recent Activity & Walkthrough Timeline
        drawRoundRect(48, 1236, width - 96, 360, 20, 'rgba(15, 23, 42, 0.88)', 'rgba(51, 65, 85, 0.65)');
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 18px "Microsoft YaHei", sans-serif';
        ctx.fillText('⏱️ 最近馆藏动态与攻略修撰时间轴', 74, 1274);

        (d.timeline || []).slice(0, 6).forEach((ev, idx) => {
          const ty = 1306 + idx * 44;
          const badgeColor = ev.type === 'played' ? '#fbbf24' : (ev.type === 'guide' ? '#818cf8' : '#34d399');
          const typeLabel = ev.type === 'played' ? '最近游玩' : (ev.type === 'guide' ? '全结局攻略' : (ev.type === 'note' ? '通关随手记' : '扫描入库'));
          drawRoundRect(74, ty - 16, 1132, 34, 8, 'rgba(30, 41, 59, 0.45)', null);
          ctx.fillStyle = badgeColor;
          ctx.font = 'bold 12px "Microsoft YaHei", sans-serif';
          ctx.fillText(`[${typeLabel}]`, 88, ty + 5);
          ctx.fillStyle = '#f8fafc';
          ctx.font = 'bold 13px "Microsoft YaHei", sans-serif';
          ctx.fillText((ev.title || '').slice(0, 28), 180, ty + 5);
          ctx.fillStyle = '#94a3b8';
          ctx.font = '12px "Microsoft YaHei", sans-serif';
          ctx.fillText(ev.detail || '', 620, ty + 5);
          ctx.fillStyle = '#64748b';
          ctx.font = '12px monospace';
          ctx.fillText(ev.timestamp || '', 1060, ty + 5);
        });

        const dataUrl = canvas.toDataURL('image/png');
        const link = document.createElement('a');
        link.download = `ACG_Vault_馆藏数据总结报告_${nowStr.replace(/-/g, '')}.png`;
        link.href = dataUrl;
        document.body.appendChild(link);
        link.click();
        link.remove();
        showToast('已生成并导出高清馆藏总结长图 (PNG)！', 'success');
      } catch (err) {
        showToast('导出总结长图失败: ' + err, 'error');
      } finally {
        isExportingPoster.value = false;
      }
    };

    const openGameById = async (gameId) => {
      if (!gameId) return;
      const existing = games.value.find(g => g.id === gameId);
      if (existing) {
        openGameDetail(existing);
        return;
      }
      try {
        const res = await fetch(`/api/games/${gameId}`);
        if (res.ok) {
          const data = await res.json();
          if (data.data) {
            openGameDetail(data.data);
          }
        }
      } catch (e) {}
    };

    const openCompanionOverlayAction = async (game = null) => {
      const gid = game?.id || selectedGame.value?.id || '';
      let nativeOpened = false;
      try {
        const q = gid ? `?game_id=${gid}` : '';
        const res = await fetch(`/api/overlay/summon${q}`, { method: 'POST' });
        const d = await res.json();
        if (d && d.success && configData.value.desktop_mode === 'native') {
          nativeOpened = true;
          showToast(d.message || '已呼出游戏内攻略伴侣悬浮窗 (Alt+G)', 'info', 2000);
        }
      } catch (e) {}
      if (!nativeOpened) {
        const popupUrl = `/overlay${gid ? '?game_id=' + gid : ''}`;
        window.open(popupUrl, 'ACGVaultCompanionOverlay', 'width=460,height=740,menubar=no,toolbar=no,location=no,status=no');
      }
    };

    const fetchConfig = async () => {
      try {
        const res = await fetch('/api/config');
        const data = await res.json();
        configData.value = { ...configData.value, ...data };
        if (data.cover_fit_mode && !localStorage.getItem('acg_cover_fit')) {
          coverFitMode.value = data.cover_fit_mode;
        }
        if (data.grid_density && !localStorage.getItem('acg_grid_density')) {
          gridDensity.value = data.grid_density;
        }
        if (data.card_hover_style && !localStorage.getItem('acg_card_hover')) {
          cardHoverStyle.value = data.card_hover_style;
        }
        if (data.notes_font_size && !localStorage.getItem('acg_notes_font')) {
          notesFontSize.value = data.notes_font_size;
        }
        if (data.default_view_mode && !localStorage.getItem('acg_view_mode')) {
          viewMode.value = data.default_view_mode;
          if (viewMode.value === 'analytics') fetchAnalytics();
        }
        if (data.notes_default_layout) {
          notesFullscreenLayout.value = data.notes_default_layout;
        }
        if (data.notes_default_toc !== undefined) {
          showNotesToc.value = Boolean(data.notes_default_toc);
        }
        if (data.notes_sync_scroll !== undefined) {
          syncScrollEnabled.value = Boolean(data.notes_sync_scroll);
        }
      } catch (err) {
        console.error('Failed to load config:', err);
      }
    };

    const saveConfigAction = async () => {
      try {
        coverFitMode.value = configData.value.cover_fit_mode || coverFitMode.value;
        gridDensity.value = configData.value.grid_density || gridDensity.value;
        cardHoverStyle.value = configData.value.card_hover_style || cardHoverStyle.value;
        notesFontSize.value = configData.value.notes_font_size || notesFontSize.value;

        localStorage.setItem('acg_cover_fit', coverFitMode.value);
        localStorage.setItem('acg_grid_density', gridDensity.value);
        localStorage.setItem('acg_card_hover', cardHoverStyle.value);
        localStorage.setItem('acg_notes_font', notesFontSize.value);

        const res = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(configData.value)
        });
        if (res.ok) {
          const saved = await res.json();
          if (saved.data) configData.value = { ...configData.value, ...saved.data };
          showSettingsModal.value = false;
          showToast('系统与个性化设置已保存！', 'success');
        } else {
          showToast('保存设置失败', 'error');
        }
      } catch (err) {
        showToast('保存设置异常: ' + err, 'error');
      }
    };

    const applyLLMPreset = (preset) => {
      const presets = {
        deepseek: { base: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
        qwen: { base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
        siliconflow: { base: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-V3' },
        openai: { base: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
        ollama: { base: 'http://127.0.0.1:11434/v1', model: 'qwen2.5:14b' }
      };
      const p = presets[preset];
      if (p) {
        configData.value.llm_api_base = p.base;
        configData.value.llm_model = p.model;
        configData.value.llm_enabled = true;
        showToast(`已填充 ${preset.toUpperCase()} 接口预设`, 'info', 1800);
      }
    };

    const testLLMConnectionAction = async () => {
      isTestingLLM.value = true;
      try {
        const res = await fetch('/api/config/test_llm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            llm_api_base: configData.value.llm_api_base,
            llm_api_key: configData.value.llm_api_key,
            llm_model: configData.value.llm_model,
            proxy: configData.value.proxy
          })
        });
        const data = await res.json();
        showToast(data.message || '测试完成', data.success ? 'success' : 'warning', 3500);
      } catch (err) {
        showToast('测试 LLM 连接异常: ' + err, 'error');
      } finally {
        isTestingLLM.value = false;
      }
    };

    const testWebDAVAction = async () => {
      isTestingWebDAV.value = true;
      try {
        const res = await fetch('/api/config/test_webdav', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            webdav_url: configData.value.webdav_url,
            webdav_root_path: configData.value.webdav_root_path,
            webdav_username: configData.value.webdav_username,
            webdav_password: configData.value.webdav_password
          })
        });
        const data = await res.json();
        showToast(data.message || 'WebDAV 测试完成', data.success ? 'success' : 'warning', 3500);
      } catch (err) {
        showToast('测试 WebDAV 异常: ' + err, 'error');
      } finally {
        isTestingWebDAV.value = false;
      }
    };

    const localizeAllTagsAction = async () => {
      isLocalizingTags.value = true;
      try {
        const res = await fetch('/api/games/localize_tags', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          await fetchGames(true);
          await fetchCollections();
          if (selectedGame.value) {
            await openGameDetail(selectedGame.value, true);
          }
          showToast(data.message || '标签汉化归一完成！', 'success', 3200);
        }
      } catch (err) {
        showToast('标签汉化归一失败: ' + err, 'error');
      } finally {
        isLocalizingTags.value = false;
      }
    };

    const pickLocalPathAction = async (targetType, index = -1) => {
      let mode = 'folder';
      let filetypes = null;
      let title = '选择文件夹';
      let initialDir = '';

      if (targetType === 'game_dir' && index >= 0) {
        initialDir = configData.value.game_directories[index] || '';
        title = '选择游戏扫描根目录';
      } else if (targetType === 'archive_dir') {
        initialDir = configData.value.archive_directory || '';
        title = '选择重复版本归档隔离目录';
      } else if (targetType === 'save_backup_dir') {
        initialDir = configData.value.save_backup_directory || '';
        title = '选择存档快照备份目录';
      } else if (targetType === 'mtool_dir') {
        initialDir = configData.value.mtool_directory || '';
        title = '选择 MTool 安装根目录';
      } else if (targetType === 'leproc') {
        mode = 'file';
        filetypes = 'exe';
        title = '选择 Locale Emulator (LEProc.exe)';
      } else if (targetType === 'game_exe' && selectedGame.value) {
        mode = 'file';
        filetypes = 'exe';
        initialDir = selectedGame.value.folder_path || '';
        title = '选择游戏主执行程序 (.exe)';
      }

      try {
        const res = await fetch('/api/system/pick_path', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode, title, initial_dir: initialDir, filetypes })
        });
        const data = await res.json();
        if (data.success && data.path) {
          if (targetType === 'game_dir' && index >= 0) {
            configData.value.game_directories[index] = data.path;
          } else if (targetType === 'archive_dir') {
            configData.value.archive_directory = data.path;
          } else if (targetType === 'save_backup_dir') {
            configData.value.save_backup_directory = data.path;
          } else if (targetType === 'mtool_dir') {
            configData.value.mtool_directory = data.path;
          } else if (targetType === 'leproc') {
            configData.value.leproc_path = data.path;
          } else if (targetType === 'game_exe') {
            editForm.executable_path = data.path;
          }
        } else if (data.message && data.message !== '已取消选择') {
          showToast(data.message, 'warning');
        }
      } catch (err) {
        showToast('唤起文件选择器失败，请手动输入路径', 'warning');
      }
    };

    const testProxyAction = async () => {
      isTestingProxy.value = true;
      proxyTestResults.value = [];
      try {
        const res = await fetch('/api/config/test_proxy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ proxy: configData.value.proxy })
        });
        const result = await res.json();
        proxyTestResults.value = result.results || [];
        showToast(result.message, result.all_ok ? 'success' : (result.success ? 'info' : 'warning'), 3500);
      } catch (err) {
        showToast('测试代理失败: ' + err, 'error');
      } finally {
        isTestingProxy.value = false;
      }
    };

    const toggleFavorite = async (game) => {
      const newFav = game.is_favorite ? 0 : 1;
      game.is_favorite = newFav;
      triggerGamesRef();
      if (selectedGame.value && selectedGame.value.id === game.id) {
        selectedGame.value.is_favorite = newFav;
      }
      try {
        await fetch(`/api/games/${game.id}/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ is_favorite: newFav })
        });
        fetchStats();
        fetchCollections();
        showToast(newFav ? '已添加至收藏' : '已取消收藏', 'info', 1600);
      } catch (err) {
        console.error('Update favorite error:', err);
        showToast('更新收藏失败', 'error');
      }
    };

    const toggleSortOrder = () => {
      sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc';
      fetchGames();
    };

    const sortByColumn = (colKey) => {
      if (sortBy.value === colKey) {
        toggleSortOrder();
      } else {
        sortBy.value = colKey;
        sortOrder.value = colKey === 'title' ? 'asc' : 'desc';
        fetchGames();
      }
    };

    const resetFilters = () => {
      searchKeyword.value = '';
      currentStatus.value = 'all';
      favoriteOnly.value = false;
      missingOnly.value = false;
      showToolsOnly.value = false;
      hasNotesOnly.value = false;
      unscrapedOnly.value = false;
      activeCollectionId.value = null;
      engineFilter.value = 'all';
      transFilter.value = 'all';
      if (viewMode.value === 'analytics') {
        viewMode.value = 'grid';
      }
      fetchGames();
    };

    let searchTimer = null;
    const debounceSearch = () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        fetchGames();
      }, 220);
    };

    const populateEditForm = (game) => {
      editForm.display_title = game.display_title || '';
      editForm.original_title = game.original_title || '';
      editForm.circle_name = game.circle_name || '';
      editForm.release_date = game.release_date || '';
      editForm.downloaded_at = game.downloaded_at || '';
      editForm.cover_url = game.cover_url || '';
      editForm.executable_path = game.executable_path || '';
      editForm.synopsis = game.synopsis || '';
      editForm.user_notes = game.user_notes || '';
      editForm.rj_code = game.rj_code || '';
      editForm.has_translation = game.has_translation ? 1 : 0;
      editTagsList.value = [...(game.tags || [])];
      editUserTagsList.value = [...(game.user_tags || [])];
      editTagsString.value = (game.tags || []).join(', ');
      editVoiceActorsString.value = (game.voice_actors || []).join(', ');

      editFormSnapshot = JSON.stringify({
        display_title: editForm.display_title,
        original_title: editForm.original_title,
        circle_name: editForm.circle_name,
        release_date: editForm.release_date,
        downloaded_at: editForm.downloaded_at,
        cover_url: editForm.cover_url,
        executable_path: editForm.executable_path,
        synopsis: editForm.synopsis,
        user_notes: editForm.user_notes,
        rj_code: editForm.rj_code,
        has_translation: editForm.has_translation,
        tags: editTagsList.value,
        user_tags: editUserTagsList.value,
        va: editVoiceActorsString.value
      });
    };

    const isEditDirty = () => {
      const current = JSON.stringify({
        display_title: editForm.display_title,
        original_title: editForm.original_title,
        circle_name: editForm.circle_name,
        release_date: editForm.release_date,
        downloaded_at: editForm.downloaded_at,
        cover_url: editForm.cover_url,
        executable_path: editForm.executable_path,
        synopsis: editForm.synopsis,
        user_notes: editForm.user_notes,
        rj_code: editForm.rj_code,
        has_translation: editForm.has_translation,
        tags: editTagsList.value,
        user_tags: editUserTagsList.value,
        va: editVoiceActorsString.value
      });
      return current !== editFormSnapshot;
    };

    const addEditTagChip = (isUserTag = false) => {
      if (isUserTag) {
        const parts = newEditUserTagInput.value.split(/[,，]/).map(s => s.trim()).filter(Boolean);
        for (const p of parts) {
          if (!editUserTagsList.value.includes(p)) editUserTagsList.value.push(p);
        }
        newEditUserTagInput.value = '';
      } else {
        const parts = newEditTagInput.value.split(/[,，]/).map(s => s.trim()).filter(Boolean);
        for (const p of parts) {
          if (!editTagsList.value.includes(p)) editTagsList.value.push(p);
        }
        newEditTagInput.value = '';
      }
    };

    const removeEditTagChip = (idx, isUserTag = false) => {
      if (isUserTag) editUserTagsList.value.splice(idx, 1);
      else editTagsList.value.splice(idx, 1);
    };

    // Quick User Tag addition/removal directly in Detail Drawer View Mode (Supports comma batching)
    const addQuickUserTag = async () => {
      if (!selectedGame.value) return;
      const rawVal = newUserTagInput.value.trim();
      if (!rawVal) {
        showAddUserTag.value = false;
        return;
      }
      const parts = rawVal.split(/[,，]/).map(s => s.trim().replace(/^[#★\s]+/, '')).filter(Boolean);
      const curr = [...(selectedGame.value.user_tags || [])];
      let addedCount = 0;
      for (const p of parts) {
        if (!curr.includes(p)) {
          curr.push(p);
          addedCount++;
        }
      }
      if (addedCount > 0) {
        selectedGame.value.user_tags = curr;
        const res = await fetch(`/api/games/${selectedGame.value.id}/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_tags: curr })
        });
        const data = await res.json();
        if (data.data) {
          selectedGame.value.tags = data.data.tags || selectedGame.value.tags;
          selectedGame.value.user_tags = data.data.user_tags || curr;
          updateGameInList(data.data);
        }
        fetchCollections();
        showToast(`已添加个人标签: ${parts.join(', ')}`, 'success', 1600);
      }
      newUserTagInput.value = '';
    };

    const removeQuickUserTag = async (tagToRemove) => {
      if (!selectedGame.value) return;
      const curr = (selectedGame.value.user_tags || []).filter(t => t !== tagToRemove);
      selectedGame.value.user_tags = curr;
      const res = await fetch(`/api/games/${selectedGame.value.id}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_tags: curr })
      });
      const data = await res.json();
      if (data.data) {
        updateGameInList(data.data);
      }
      fetchCollections();
    };

    const closeGameDetail = async (fromBackdrop = false) => {
      showDangerMenu.value = false;
      if (isEditMode.value) {
        if (fromBackdrop) {
          showToast('正在编辑资料，点击背景不会关闭。请保存或点击右上角关闭按钮', 'warning', 2200);
          return;
        }
        if (isEditDirty()) {
          const ok = await askConfirm({
            title: '放弃未保存的修改？',
            message: '您有正在编辑且尚未保存的元数据修改，确定要放弃本次修改并退出吗？',
            confirmText: '放弃修改',
            cancelText: '继续编辑',
            variant: 'warning'
          });
          if (!ok) return;
        }
        isEditMode.value = false;
      }
      if (personalMemoTimer) {
        clearTimeout(personalMemoTimer);
        personalMemoTimer = null;
        await savePersonalNoteNow(true);
      }
      if (notesAutoSaveTimer) {
        clearTimeout(notesAutoSaveTimer);
        notesAutoSaveTimer = null;
        await saveGameNotes(true);
      }
      selectedGame.value = null;
    };

    const openGameDetail = async (game, silentRefresh = false, targetTab = null) => {
      if (!silentRefresh) {
        selectedGame.value = { walkthrough_md: '', user_notes: '', sample_images: [], ...game };
        drawerActiveTab.value = targetTab || 'overview';
        selectedGameVariants.value = [];
        selectedGameMTool.value = null;
        selectedGameSave.value = null;
        selectedGameScreenshots.value = [];
        showSaveBackupsList.value = false;
        showSaveEditorPanel.value = false;
        saveEditorData.value = { supported: false, slots: [] };
        saveSlotDetail.value = null;
        isEditMode.value = false;
        showDangerMenu.value = false;
        showAddUserTag.value = false;
        personalMemoSaveStatus.value = 'saved';
        notesSaveStatus.value = 'saved';
        showRescrapePanel.value = !game.cover_url || !game.synopsis;
        scrapeInputRJ.value = game.rj_code || '';
        scrapeInputKeyword.value = game.clean_title || game.folder_name || '';
        scrapePreferredSource.value = configData.value.scrape_source || 'auto';
        populateEditForm(game);
        syncNotesPreviewNow(game.walkthrough_md || '');
      }

      try {
        const res = await fetch(`/api/games/${game.id}`);
        const data = await res.json();
        if (selectedGame.value && selectedGame.value.id === game.id) {
          selectedGame.value = data.data;
          selectedGameVariants.value = data.variants || [];
          selectedGameMTool.value = data.mtool_status || null;
          selectedGameSave.value = data.save_status || null;
          selectedGameScreenshots.value = data.screenshots || [];
          if (!isEditMode.value) {
            populateEditForm(data.data);
          }
          syncNotesPreviewNow(data.data.walkthrough_md || '');
          updateGameInList(data.data);
          fetchSaveEditorSlots(game.id);
        }
      } catch (err) {
        console.error('Failed to get game detail:', err);
      } finally {
        refreshIcons();
      }
    };

    const filterByKeyword = (kw) => {
      if (!kw) return;
      searchKeyword.value = kw.trim();
      currentStatus.value = 'all';
      favoriteOnly.value = false;
      missingOnly.value = false;
      activeCollectionId.value = null;
      if (viewMode.value === 'analytics') {
        viewMode.value = 'grid';
      }
      if (selectedGame.value && !isEditMode.value) {
        selectedGame.value = null;
      }
      fetchGames();
      showToast(`已按关键词筛选: "${kw}"`, 'info');
    };

    const triggerLocalCoverUpload = () => {
      if (coverFileInput.value) {
        coverFileInput.value.click();
      }
    };

    const uploadImageBlob = async (file) => {
      if (!selectedGame.value || !file) return;
      isUploadingCover.value = true;
      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch(`/api/games/${selectedGame.value.id}/upload_cover`, {
          method: 'POST',
          body: formData
        });
        const result = await res.json();
        if (result.success) {
          editForm.cover_url = result.cover_url;
          selectedGame.value.cover_url = result.cover_url;
          selectedGame.value.banner_url = result.cover_url;
          updateGameInList(result.data || selectedGame.value);
          fetchStats();
          showToast('封面图片上传并生成缩略图成功！', 'success');
        } else {
          showToast('上传失败: ' + (result.detail || '未知错误'), 'error');
        }
      } catch (err) {
        showToast('上传图片网络异常: ' + err, 'error');
      } finally {
        isUploadingCover.value = false;
        refreshIcons();
      }
    };

    const handleFileUpload = (e) => {
      const file = e.target.files[0];
      if (file) {
        uploadImageBlob(file);
      }
      if (coverFileInput.value) coverFileInput.value.value = '';
    };

    const pasteClipboardImage = async () => {
      try {
        const items = await navigator.clipboard.read();
        for (const item of items) {
          const imageType = item.types.find(type => type.startsWith('image/'));
          if (imageType) {
            const blob = await item.getType(imageType);
            const file = new File([blob], `pasted_cover_${Date.now()}.${imageType.split('/')[1] || 'jpg'}`, { type: imageType });
            await uploadImageBlob(file);
            return;
          }
        }
        showToast('剪贴板中未检测到图片，请先截图或复制图片', 'warning');
      } catch (err) {
        showToast('无法直接读取剪贴板，请直接按 Ctrl+V 粘贴或选择本地图片', 'warning');
      }
    };

    const handleGlobalPaste = (e) => {
      if (!selectedGame.value || showNotesFullscreen.value) return;
      const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
      if (activeTag === 'textarea' || activeTag === 'input') return;
      if (e.clipboardData && e.clipboardData.items) {
        for (const item of e.clipboardData.items) {
          if (item.type.indexOf('image') !== -1) {
            const file = item.getAsFile();
            if (file) {
              uploadImageBlob(file);
              break;
            }
          }
        }
      }
    };

    // ---------------------------------------------------------
    // Official Sample Previews & In-Game Screenshot Gallery
    // ---------------------------------------------------------
    const openSampleLightbox = (imgUrl, index = 0) => {
      if (!imgUrl) return;
      lightboxShot.value = {
        id: null,
        url: imgUrl,
        caption: `官方商店预览图 #${index + 1}`,
        created_at: 'Official Sample CG',
        isSample: true,
        is_sample: true
      };
    };

    const captureGameScreenshotAction = async (game) => {
      if (!game) return;
      isCapturingScreenshot.value = true;
      try {
        const res = await fetch(`/api/games/${game.id}/screenshots/capture`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          selectedGameScreenshots.value = data.screenshots || [];
          selectedGame.value.screenshot_count = selectedGameScreenshots.value.length;
          fetchStats();
          showToast(data.message || '截图已归档至画廊！', 'success');
        } else {
          showToast(data.message || '截图失败', 'warning');
        }
      } catch (err) {
        showToast('截图异常: ' + err, 'error');
      } finally {
        isCapturingScreenshot.value = false;
        refreshIcons();
      }
    };

    const triggerScreenshotUpload = () => {
      if (screenshotFileInput.value) {
        screenshotFileInput.value.click();
      }
    };

    const handleScreenshotUpload = async (e) => {
      const file = e.target.files[0];
      if (!file || !selectedGame.value) return;
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await fetch(`/api/games/${selectedGame.value.id}/screenshots/upload`, {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (data.success) {
          selectedGameScreenshots.value = data.screenshots || [];
          selectedGame.value.screenshot_count = selectedGameScreenshots.value.length;
          fetchStats();
          showToast('图片已添加至游戏画廊！', 'success');
        } else {
          showToast(data.message || '添加画廊图片失败', 'error');
        }
      } catch (err) {
        showToast('上传画廊图片异常: ' + err, 'error');
      }
      if (screenshotFileInput.value) screenshotFileInput.value.value = '';
    };

    const saveScreenshotCaptionAction = async (shot) => {
      if (!selectedGame.value || !shot || shot.isSample) return;
      try {
        const res = await fetch(`/api/games/${selectedGame.value.id}/screenshots/${shot.id}/caption`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ caption: shot.caption || '' })
        });
        const data = await res.json();
        if (data.success) {
          showToast('截图备注已保存', 'info', 1500);
        }
      } catch (err) {
        showToast('保存备注失败', 'error');
      }
    };

    const deleteScreenshotAction = async (shot) => {
      if (!selectedGame.value || !shot || shot.isSample) return;
      const ok = await askConfirm({
        title: '删除画廊截图',
        message: '确定要从游戏画廊中删除这张截图吗？',
        confirmText: '删除截图',
        cancelText: '取消',
        variant: 'danger'
      });
      if (!ok) return;
      try {
        const res = await fetch(`/api/games/${selectedGame.value.id}/screenshots/${shot.id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
          selectedGameScreenshots.value = data.screenshots || [];
          selectedGame.value.screenshot_count = selectedGameScreenshots.value.length;
          if (lightboxShot.value && lightboxShot.value.id === shot.id) {
            lightboxShot.value = null;
          }
          fetchStats();
          showToast('截图已删除', 'info', 1600);
        }
      } catch (err) {
        showToast('删除截图失败: ' + err, 'error');
      }
    };

    const unlockAllCGAction = async (game) => {
      if (!game) return;
      const ok = await askConfirm({
        title: '⚡ 一键注入 100% 全 CG / 全回想解锁补丁',
        message: '系统将自动执行以下安全操作：\n\n1. 自动为您备份当前存档快照；\n2. 扫描游戏 System.json 中的全部回想/CG/画廊开关并注入非破坏性解锁插件；\n3. 启动游戏后将自动激活回想屋，且在游戏内随时按【F8】可一键全开回想与注入 999,999 金币（按 Shift+F8 强开全开关）！',
        confirmText: '立即注入解锁',
        cancelText: '取消',
        variant: 'primary'
      });
      if (!ok) return;

      isUnlockingCG.value = true;
      try {
        const res = await fetch(`/api/games/${game.id}/unlock_cg`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          selectedGame.value.cg_unlocked = 1;
          if (data.save_status) selectedGameSave.value = data.save_status;
          updateGameInList(selectedGame.value);
          fetchStats();
          fetchCollections();
          showToast(data.message, 'success', 4200);
        } else {
          showToast(data.message || '解锁失败', 'warning', 3500);
        }
      } catch (err) {
        showToast('全CG解锁异常: ' + err, 'error');
      } finally {
        isUnlockingCG.value = false;
      }
    };

    const triggerCGSaveImport = () => {
      if (cgSaveFileInput.value) {
        cgSaveFileInput.value.click();
      }
    };

    const handleCGSaveImport = async (e) => {
      const file = e.target.files[0];
      if (!file || !selectedGame.value) return;
      isUnlockingCG.value = true;
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await fetch(`/api/games/${selectedGame.value.id}/import_cg_save`, {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (data.success) {
          selectedGame.value.cg_unlocked = 1;
          if (data.save_status) selectedGameSave.value = data.save_status;
          updateGameInList(selectedGame.value);
          fetchStats();
          fetchCollections();
          showToast(data.message || '全 CG 存档包已成功合入！', 'success', 3500);
        } else {
          showToast(data.message || '导入全CG存档失败', 'error');
        }
      } catch (err) {
        showToast('导入全CG存档异常: ' + err, 'error');
      } finally {
        isUnlockingCG.value = false;
        if (cgSaveFileInput.value) cgSaveFileInput.value.value = '';
      }
    };

    // ---------------------------------------------------------
    // AI Folder Semantic Parser & RPG Maker Walkthrough Generator
    // ---------------------------------------------------------
    const aiParseFolderAction = async (game) => {
      if (!game) return;
      isParsingFolderAI.value = true;
      try {
        const res = await fetch(`/api/games/${game.id}/ai_parse_folder`, { method: 'POST' });
        const data = await res.json();
        if (data.success && data.data) {
          selectedGame.value = data.data;
          populateEditForm(data.data);
          scrapeInputRJ.value = data.data.rj_code || scrapeInputRJ.value;
          scrapeInputKeyword.value = data.parsed?.clean_title || data.data.display_title || scrapeInputKeyword.value;
          updateGameInList(data.data);
          showToast(data.message || 'AI 语义解析完成！', 'success');
        } else {
          showToast(data.message || '解析未发现新字段', 'warning');
        }
      } catch (err) {
        showToast('AI 语义解析异常: ' + err, 'error');
      } finally {
        isParsingFolderAI.value = false;
      }
    };

    const generateAIWalkthroughAction = async (game) => {
      if (!game) return;
      const hasExisting = Boolean(game.walkthrough_md && game.walkthrough_md.trim().length > 20);
      let overwrite = true;
      if (hasExisting) {
        const ok = await askConfirm({
          title: '✨ AI 逆向解包生成全结局攻略',
          message: '检测到当前游戏已有全结局攻略内容（您的「个人通关笔记」随手记完全独立不受影响）。\n\n点击【生成并追加】将保留现有攻略并附在下方；若需重新生成覆盖请先清空旧攻略。',
          confirmText: '生成并追加',
          cancelText: '取消',
          variant: 'primary'
        });
        if (!ok) return;
        overwrite = false;
      }

      isGeneratingGuide.value = true;
      try {
        const res = await fetch(`/api/games/${game.id}/generate_guide`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ use_llm: true, overwrite })
        });
        const data = await res.json();
        if (data.success) {
          selectedGame.value.walkthrough_md = data.walkthrough_md;
          selectedGame.value.has_walkthrough = 1;
          selectedGame.value.has_notes = 1;
          syncNotesPreviewNow(data.walkthrough_md);
          updateGameInList(data.data || selectedGame.value);
          drawerActiveTab.value = 'walkthrough';
          fetchStats();
          fetchCollections();
          showToast(data.message || '全结局攻略生成成功！', 'success', 3500);
        } else {
          showToast(data.message || '生成攻略失败', 'error');
        }
      } catch (err) {
        showToast('生成攻略发生异常: ' + err, 'error');
      } finally {
        isGeneratingGuide.value = false;
        refreshIcons();
      }
    };

    const clearAllEditFields = async () => {
      const ok = await askConfirm({
        title: '清空当前编辑字段',
        message: '确定要一键清空当前表单中的封面图片、标题、社团、简介与标签等内容吗？（清空后需点击“保存修改”才会写入数据库）',
        confirmText: '确认清空',
        cancelText: '取消',
        variant: 'warning'
      });
      if (!ok) return;
      editForm.display_title = '';
      editForm.original_title = '';
      editForm.circle_name = '';
      editForm.release_date = '';
      editForm.cover_url = '';
      editForm.synopsis = '';
      editForm.user_notes = '';
      editForm.rj_code = '';
      editTagsList.value = [];
      editUserTagsList.value = [];
      editTagsString.value = '';
      editVoiceActorsString.value = '';
      showToast('表单内容已清空，点击保存即可生效', 'info');
    };

    const saveManualEdit = async () => {
      if (!selectedGame.value) return;

      if (newEditTagInput.value.trim()) addEditTagChip(false);
      if (newEditUserTagInput.value.trim()) addEditTagChip(true);

      const vaList = editVoiceActorsString.value.split(/[,，]/).map(v => v.trim()).filter(Boolean);

      const payload = {
        display_title: editForm.display_title || (selectedGame.value ? selectedGame.value.clean_title : ''),
        original_title: editForm.original_title,
        circle_name: editForm.circle_name,
        release_date: editForm.release_date,
        downloaded_at: editForm.downloaded_at,
        cover_url: editForm.cover_url,
        executable_path: editForm.executable_path,
        synopsis: editForm.synopsis,
        user_notes: editForm.user_notes,
        rj_code: editForm.rj_code,
        has_translation: editForm.has_translation ? 1 : 0,
        tags: editTagsList.value,
        user_tags: editUserTagsList.value,
        voice_actors: vaList
      };

      try {
        const res = await fetch(`/api/games/${selectedGame.value.id}/manual_update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (res.ok && result.success) {
          selectedGame.value = result.data;
          populateEditForm(result.data);
          updateGameInList(result.data);
          isEditMode.value = false;
          fetchStats();
          fetchCollections();
          showToast('元数据修改已保存！', 'success');
        } else {
          showToast(result.detail || '保存失败', 'error');
        }
      } catch (err) {
        showToast('保存修改异常: ' + err, 'error');
      }
      refreshIcons();
    };

    const updateGameStatus = async (status) => {
      if (!selectedGame.value) return;
      selectedGame.value.play_status = status;
      updateGameInList(selectedGame.value);

      try {
        await fetch(`/api/games/${selectedGame.value.id}/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ play_status: status })
        });
        fetchStats();
        fetchCollections();
        showToast(`状态已设为: ${getStatusLabel(status)}`, 'info', 1600);
      } catch (err) {
        console.error('Update status error:', err);
        showToast('状态更新失败', 'error');
      }
    };

    const updateGameRating = async (rating) => {
      if (!selectedGame.value) return;
      const newRating = selectedGame.value.user_rating === rating ? 0 : rating;
      selectedGame.value.user_rating = newRating;
      updateGameInList(selectedGame.value);

      try {
        await fetch(`/api/games/${selectedGame.value.id}/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_rating: newRating })
        });
        fetchCollections();
        showToast(newRating ? `已评分: ${newRating} 星` : '已清除个人评分', 'info', 1600);
      } catch (err) {
        console.error('Update rating error:', err);
        showToast('评分更新失败', 'error');
      }
    };

    // ---------------------------------------------------------
    // 1. Personal Clearance Sticky Memo (user_notes)
    // ---------------------------------------------------------
    const savePersonalNoteNow = async (silent = true) => {
      if (!selectedGame.value) return;
      if (personalMemoTimer) {
        clearTimeout(personalMemoTimer);
        personalMemoTimer = null;
      }
      personalMemoSaveStatus.value = 'saving';
      try {
        const memoText = selectedGame.value.user_notes || '';
        const res = await fetch(`/api/games/${selectedGame.value.id}/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_notes: memoText })
        });
        const data = await res.json();
        if (data.data) {
          selectedGame.value.has_user_notes = data.data.has_user_notes;
          selectedGame.value.has_notes = data.data.has_notes;
          updateGameInList(data.data);
        }
        personalMemoSaveStatus.value = 'saved';
        fetchStats();
        if (!silent) {
          showToast('个人通关笔记已保存', 'success', 1500);
        }
      } catch (err) {
        personalMemoSaveStatus.value = 'dirty';
      }
    };

    const onPersonalNoteInput = () => {
      personalMemoSaveStatus.value = 'dirty';
      if (personalMemoTimer) clearTimeout(personalMemoTimer);
      personalMemoTimer = setTimeout(() => {
        savePersonalNoteNow(true);
      }, 650);
    };

    const appendPersonalMemoSnippet = (snippetText) => {
      if (!selectedGame.value) return;
      const curr = (selectedGame.value.user_notes || '').trim();
      selectedGame.value.user_notes = curr ? `${curr}\n${snippetText}` : snippetText;
      onPersonalNoteInput();
    };

    // ---------------------------------------------------------
    // 2. Full-Ending Walkthrough Engine (walkthrough_md) + Offline Mermaid Renderer
    // ---------------------------------------------------------
    const notesEditMode = ref(false);
    let markedConfigured = false;
    let headingCounterMap = {};

    const escapeHtmlAttr = (str) => {
      return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    };

    // Offline Zero-Dependency Mermaid Flowchart Parser -> Visual Step Diagram HTML
    const compileMermaidToVisualHtml = (code) => {
      const lines = String(code || '').split('\n').map(l => l.trim()).filter(Boolean);
      let subgraphTitle = '剧情分支与路线流程图';
      const nodeLabels = {};
      const edges = [];

      const parseNodeToken = (tok) => {
        if (!tok) return '';
        const m = tok.match(/^([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^)]+)\)|\{([^}]+)\})?$/);
        if (m) {
          const id = m[1];
          const label = (m[2] || m[3] || m[4] || '').trim();
          if (label) nodeLabels[id] = label;
          return nodeLabels[id] || id;
        }
        return tok.replace(/[\[\]{}()]/g, '').trim();
      };

      for (const line of lines) {
        if (/^(flowchart|graph)\b/i.test(line) || line === 'end') continue;
        const subMatch = line.match(/^subgraph\s+(.+)$/i);
        if (subMatch) {
          subgraphTitle = subMatch[1].trim();
          continue;
        }
        const edgeMatch = line.match(/^(.+?)\s*(?:-->|---|==>)\s*(?:\|([^|]+)\|\s*)?(.+)$/);
        if (edgeMatch) {
          const leftRaw = edgeMatch[1].trim();
          const cond = (edgeMatch[2] || '').trim();
          const rightRaw = edgeMatch[3].trim();
          const leftParts = leftRaw.split(/\s*&\s*/).map(parseNodeToken);
          const rightParts = rightRaw.split(/\s*&\s*/).map(parseNodeToken);
          edges.push({
            from: leftParts.join(' + '),
            cond,
            to: rightParts.join(' / ')
          });
        }
      }

      if (edges.length === 0) {
        return `<pre><code>${escapeHtmlAttr(code)}</code></pre>`;
      }

      const edgeHtml = edges.map(e => {
        const condBadge = e.cond ? `<span class="mermaid-edge-label">${escapeHtmlAttr(e.cond)}</span><span class="mermaid-arrow">→</span>` : `<span class="mermaid-arrow">⟶</span>`;
        return `<div class="mermaid-edge-row"><span class="mermaid-node-pill">${escapeHtmlAttr(e.from)}</span>${condBadge}<span class="mermaid-node-pill">${escapeHtmlAttr(e.to)}</span></div>`;
      }).join('');

      return `<div class="mermaid-flow-container"><div class="mermaid-flow-title"><span>🗺️ ${escapeHtmlAttr(subgraphTitle)}</span></div><div class="mermaid-flow-steps">${edgeHtml}</div></div>`;
    };

    const sanitizeRenderedHtml = (html) => {
      if (!html) return '';
      try {
        const parser = new DOMParser();
        const doc = parser.parseFromString(String(html), 'text/html');
        const forbiddenTags = ['script', 'iframe', 'object', 'embed', 'form', 'style', 'svg', 'math', 'base', 'meta', 'link'];
        doc.querySelectorAll(forbiddenTags.join(',')).forEach(el => el.remove());

        const allEls = doc.body.querySelectorAll('*');
        for (const el of allEls) {
          for (const attr of Array.from(el.attributes)) {
            const nameLow = attr.name.toLowerCase();
            const valLow = (attr.value || '').trim().toLowerCase();
            if (nameLow.startsWith('on') || nameLow === 'srcdoc') {
              el.removeAttribute(attr.name);
            } else if ((nameLow === 'href' || nameLow === 'src' || nameLow === 'action') && /^(javascript|vbscript|data):/i.test(valLow)) {
              el.removeAttribute(attr.name);
            }
          }
        }
        return doc.body.innerHTML;
      } catch (e) {
        return String(html)
          .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
          .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '');
      }
    };

    const safeDecodeUri = (str) => {
      if (!str) return '';
      try {
        return decodeURIComponent(String(str));
      } catch (e) {
        return String(str);
      }
    };

    const normalizeHeadingKey = (str) => {
      if (!str) return '';
      return safeDecodeUri(str)
        .replace(/^#+/, '')
        .toLowerCase()
        .replace(/[^\p{L}\p{N}]+/gu, '')
        .trim();
    };

    const setupMarkedRenderer = () => {
      if (markedConfigured || typeof marked === 'undefined') return;
      try {
        const renderer = new marked.Renderer();

        renderer.heading = function({ tokens, depth, text }) {
          const rawText = text || '';
          const normKey = normalizeHeadingKey(rawText);
          const clean = rawText.trim().replace(/[^\p{L}\p{N}\-_]+/gu, '-').replace(/^-+|-+$/g, '');
          let slug = clean || normKey || `heading-${depth}`;
          if (headingCounterMap[slug] !== undefined) {
            headingCounterMap[slug]++;
            slug = `${slug}-${headingCounterMap[slug]}`;
          } else {
            headingCounterMap[slug] = 0;
          }
          const parsedText = this.parser.parseInline(tokens);
          return `<h${depth} id="${escapeHtmlAttr(slug)}" data-norm-key="${escapeHtmlAttr(normKey)}" data-toc-title="${escapeHtmlAttr(rawText)}" class="notes-heading notes-heading-${depth}">${parsedText}</h${depth}>\n`;
        };

        renderer.code = function({ text, lang }) {
          const language = (lang || '').trim().toLowerCase();
          if (language === 'mermaid') {
            return compileMermaidToVisualHtml(text);
          }
          return `<pre><code class="language-${escapeHtmlAttr(language)}">${escapeHtmlAttr(text)}</code></pre>\n`;
        };

        renderer.link = function({ href, title, tokens }) {
          const parsedText = this.parser.parseInline(tokens);
          const safeHref = String(href || '').trim();
          if (/^(javascript|vbscript|data):/i.test(safeHref)) {
            return `<span>${parsedText}</span>`;
          }
          const titleAttr = title ? ` title="${escapeHtmlAttr(title)}"` : '';
          if (safeHref.startsWith('#')) {
            const anchorName = safeHref.replace(/^#/, '');
            return `<a href="${escapeHtmlAttr(safeHref)}" class="notes-anchor-link" data-anchor="${escapeHtmlAttr(anchorName)}"${titleAttr}>${parsedText}</a>`;
          }
          return `<a href="${escapeHtmlAttr(safeHref)}" target="_blank" rel="noopener noreferrer" class="notes-external-link"${titleAttr}>${parsedText}</a>`;
        };

        marked.use({ renderer, gfm: true, breaks: true });
        markedConfigured = true;
      } catch (e) {
        console.error('Failed to configure marked:', e);
      }
    };

    const renderNotesMarkdown = (text) => {
      if (!text || !text.trim()) {
        return '<span class="text-slate-500 italic">暂无全结局攻略内容，点击上方【✨ AI 解包生成攻略】、【插入攻略模板】或【全屏攻略工作台】即可编写...</span>';
      }
      setupMarkedRenderer();
      if (typeof marked !== 'undefined' && marked.parse) {
        try {
          headingCounterMap = {};
          const rawHtml = sanitizeRenderedHtml(marked.parse(text));
          let boxIdx = 0;
          return rawHtml.replace(/<input([^>]*?)type="checkbox"([^>]*?)>/gi, (match) => {
            const isChecked = /checked/i.test(match);
            const idx = boxIdx++;
            return `<input type="checkbox" data-checkbox-idx="${idx}" ${isChecked ? 'checked' : ''} class="notes-interactive-checkbox" />`;
          });
        } catch (e) {
          console.error('Markdown parse error:', e);
        }
      }
      return escapeHtmlAttr(text).replace(/\n/g, '<br/>');
    };

    const extractNotesToc = (text) => {
      if (!text || !text.trim()) return [];
      const lines = text.split('\n');
      const toc = [];
      const headingCount = {};
      let inCodeFence = false;
      for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
        const line = lines[lineIdx];
        if (/^\s*(```|~~~)/.test(line)) {
          inCodeFence = !inCodeFence;
          continue;
        }
        if (inCodeFence) continue;
        const match = line.match(/^(#{1,4})\s+(.+)$/);
        if (match) {
          const level = match[1].length;
          const rawTitle = match[2].trim();
          const normKey = normalizeHeadingKey(rawTitle);
          const clean = rawTitle.replace(/[^\p{L}\p{N}\-_]+/gu, '-').replace(/^-+|-+$/g, '');
          let slug = clean || normKey || `heading-${level}`;
          if (headingCount[slug] !== undefined) {
            headingCount[slug]++;
            slug = `${slug}-${headingCount[slug]}`;
          } else {
            headingCount[slug] = 0;
          }
          toc.push({
            level,
            title: rawTitle,
            id: slug,
            normKey,
            lineIdx,
            lineRatio: lines.length > 1 ? lineIdx / (lines.length - 1) : 0
          });
        }
      }
      return toc;
    };

    const syncNotesPreviewNow = (text) => {
      if (notesRenderTimer) {
        clearTimeout(notesRenderTimer);
        notesRenderTimer = null;
      }
      debouncedNotesHtml.value = renderNotesMarkdown(text);
      notesTocList.value = extractNotesToc(text);
    };

    const scrollToHeading = async (id, tocIndex = -1) => {
      if (!id && tocIndex < 0) return;

      if (showNotesFullscreen.value && notesFullscreenLayout.value === 'editor') {
        notesFullscreenLayout.value = 'split';
        await nextTick();
      }

      let container = null;
      if (showNotesFullscreen.value) {
        container = document.getElementById('notes-preview-scroll-container');
      } else {
        container = document.getElementById('drawer-notes-preview-container') ||
                    document.querySelector('.notes-markdown-body')?.parentElement;
      }
      if (!container) return;

      const targetNorm = normalizeHeadingKey(id);
      const allHeadings = Array.from(container.querySelectorAll('h1, h2, h3, h4, h5, h6'));
      let target = null;

      if (id) {
        const decoded = safeDecodeUri(id).replace(/^#+/, '');
        try {
          target = container.querySelector(`[id="${CSS.escape(decoded)}"]`) ||
                   container.querySelector(`[id="${CSS.escape(id)}"]`);
        } catch (e) {
          target = container.querySelector(`[id="${decoded}"]`) ||
                   container.querySelector(`[id="${id}"]`);
        }
      }

      if (!target && targetNorm) {
        target = allHeadings.find(el => {
          const elNorm = el.getAttribute('data-norm-key') || normalizeHeadingKey(el.innerText || el.textContent);
          return elNorm === targetNorm;
        });
      }

      if (!target && targetNorm) {
        target = allHeadings.find(el => {
          const elNorm = el.getAttribute('data-norm-key') || normalizeHeadingKey(el.innerText || el.textContent);
          return elNorm && (elNorm.includes(targetNorm) || targetNorm.includes(elNorm));
        });
      }

      if (!target && tocIndex >= 0 && tocIndex < allHeadings.length) {
        target = allHeadings[tocIndex];
      }

      if (target) {
        activeHeadingId.value = target.id || id;
        const targetRect = target.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        const currentScrollTop = container.scrollTop;
        const relativeTop = targetRect.top - containerRect.top + currentScrollTop;
        const finalTop = Math.max(0, relativeTop - 48);

        container.scrollTo({
          top: finalTop,
          behavior: 'smooth'
        });

        target.classList.remove('heading-highlight-flash');
        void target.offsetWidth;
        target.classList.add('heading-highlight-flash');
        setTimeout(() => target.classList.remove('heading-highlight-flash'), 1800);
      }
    };

    // Code-Block-Aware Interactive Checkbox Toggle in walkthrough_md
    const handleNotesContentClick = (event) => {
      const checkbox = event.target.closest('input.notes-interactive-checkbox');
      if (checkbox && selectedGame.value && selectedGame.value.walkthrough_md) {
        const targetIdx = parseInt(checkbox.getAttribute('data-checkbox-idx'), 10);
        if (!isNaN(targetIdx)) {
          const lines = selectedGame.value.walkthrough_md.split('\n');
          let inFence = false;
          let currentMatch = 0;
          for (let i = 0; i < lines.length; i++) {
            if (/^\s*(```|~~~)/.test(lines[i])) {
              inFence = !inFence;
              continue;
            }
            if (inFence) continue;
            if (/^\s*[-*+]\s+\[([ xX])\]/.test(lines[i])) {
              if (currentMatch === targetIdx) {
                lines[i] = lines[i].replace(/^(\s*[-*+]\s+\[)([ xX])(\])/, (m, p1, st, p3) => {
                  return `${p1}${st === ' ' ? 'x' : ' '}${p3}`;
                });
                break;
              }
              currentMatch++;
            }
          }
          selectedGame.value.walkthrough_md = lines.join('\n');
          syncNotesPreviewNow(selectedGame.value.walkthrough_md);
          onNotesInput(true);
          return;
        }
      }

      const anchor = event.target.closest('a');
      if (!anchor) return;
      const href = anchor.getAttribute('href');
      if (!href) return;

      if (href.startsWith('#')) {
        event.preventDefault();
        const id = href.replace(/^#+/, '');
        scrollToHeading(id);
      }
    };

    // Piecewise Heading-Anchor Interpolated Scroll Synchronization (Anti-Jitter)
    const _lockScrollSource = (sourceName) => {
      activeScrollPane = sourceName;
      if (scrollLockTimer) clearTimeout(scrollLockTimer);
      scrollLockTimer = setTimeout(() => {
        activeScrollPane = null;
      }, 150);
    };

    const onEditorScroll = (e) => {
      if (!syncScrollEnabled.value || notesFullscreenLayout.value !== 'split') return;
      if (activeScrollPane && activeScrollPane !== 'editor') return;
      _lockScrollSource('editor');

      const editor = e.target;
      const preview = document.getElementById('notes-preview-scroll-container');
      if (!editor || !preview) return;

      const maxEditor = editor.scrollHeight - editor.clientHeight;
      const maxPreview = preview.scrollHeight - preview.clientHeight;
      if (maxEditor <= 0 || maxPreview <= 0) return;

      const editorRatio = editor.scrollTop / maxEditor;
      const toc = notesTocList.value;
      const headingEls = Array.from(preview.querySelectorAll('h1, h2, h3, h4'));

      if (toc.length >= 2 && headingEls.length === toc.length) {
        const previewRectTop = preview.getBoundingClientRect().top;
        const points = [{ r: 0, y: 0 }];
        for (let i = 0; i < toc.length; i++) {
          const y = Math.max(0, headingEls[i].getBoundingClientRect().top - previewRectTop + preview.scrollTop - 32);
          points.push({ r: toc[i].lineRatio, y });
        }
        points.push({ r: 1, y: maxPreview });

        for (let i = 0; i < points.length - 1; i++) {
          const p0 = points[i];
          const p1 = points[i + 1];
          if (editorRatio >= p0.r && editorRatio <= p1.r) {
            const span = Math.max(0.0001, p1.r - p0.r);
            const localT = (editorRatio - p0.r) / span;
            preview.scrollTop = p0.y + localT * (p1.y - p0.y);
            return;
          }
        }
      }
      preview.scrollTop = editorRatio * maxPreview;
    };

    const onPreviewScroll = (e) => {
      const preview = e.target;
      if (!preview) return;

      const headings = Array.from(preview.querySelectorAll('h1, h2, h3, h4'));
      const previewTop = preview.getBoundingClientRect().top;
      let currentId = '';
      for (const h of headings) {
        const offset = h.getBoundingClientRect().top - previewTop;
        if (offset <= 110) {
          currentId = h.id;
        } else {
          break;
        }
      }
      if (currentId) {
        activeHeadingId.value = currentId;
      } else if (headings.length > 0) {
        activeHeadingId.value = headings[0].id;
      }

      if (!syncScrollEnabled.value || notesFullscreenLayout.value !== 'split') return;
      if (activeScrollPane && activeScrollPane !== 'preview') return;
      _lockScrollSource('preview');

      const editor = document.getElementById('notes-editor-textarea');
      if (!editor) return;

      const maxPreview = preview.scrollHeight - preview.clientHeight;
      const maxEditor = editor.scrollHeight - editor.clientHeight;
      if (maxPreview > 0 && maxEditor > 0) {
        const ratio = preview.scrollTop / maxPreview;
        editor.scrollTop = ratio * maxEditor;
      }
    };

    const startSplitDrag = (e) => {
      e.preventDefault();
      isDraggingSplit.value = true;
      const container = document.getElementById('notes-split-panes-container');
      if (!container) return;

      const onMove = (moveEvent) => {
        if (!isDraggingSplit.value) return;
        const rect = container.getBoundingClientRect();
        if (rect.width <= 0) return;
        const relX = moveEvent.clientX - rect.left;
        const pct = Math.max(25, Math.min(75, (relX / rect.width) * 100));
        splitLeftWidthPct.value = Math.round(pct * 10) / 10;
      };

      const onUp = () => {
        isDraggingSplit.value = false;
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
      };

      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    };

    const insertMarkdownSnippet = (type) => {
      if (!selectedGame.value) return;
      const snippets = {
        h2: '\n## 章节标题\n',
        bold: '**重点内容**',
        checklist: '\n- [ ] 结局/CG收集项 1\n- [ ] 结局/CG收集项 2\n',
        table: '\n| 章节/阶段 | 关键选项 / 触发条件 | 好感度/属性变化 | 解锁结局 / 备注 |\n| :--- | :--- | :--- | :--- |\n| 第一章 | 选择「留下来帮忙」 | 好感 +10 | 关键主线分支 |\n| 终章 | 满足好感 ≥ 80 | 触发 True End | 解锁全回想 |\n',
        spoiler: '\n<details>\n<summary>点击展开隐藏剧透 / 作弊密码</summary>\n\n- 全回想开启位置：标题画面右侧隐藏开关或按 `F8`\n- 保险箱密码：`1024`\n\n</details>\n',
        template: `# 《${selectedGame.value.display_title || selectedGame.value.clean_title}》全流程全结局攻略\n\n## 一、 核心机制与通关提示\n- **全CG/回想解锁方式**：\n- **关键数值/状态说明**：\n\n## 二、 主线流程与关键分支表\n| 阶段 | 地点 / NPC | 关键行动与选项 | 结果 / 解锁内容 |\n| :--- | :--- | :--- | :--- |\n| 序章 | 初始房间 | 调查书桌获取道具 | 开启主线 |\n| 中盘 | 王都广场 | 夜晚前往酒馆触发支线 | 解锁支线事件 |\n\n## 三、 全结局达成条件 Checklist\n- [ ] **True End (真结局)**：\n- [ ] **Normal End (普通结局)**：\n- [ ] **Bad End / 特殊结局**：\n`
      };
      const textToInsert = snippets[type] || '';
      if (!textToInsert) return;

      const ta = document.getElementById('notes-editor-textarea') || document.getElementById('drawer-notes-textarea');
      const currentVal = selectedGame.value.walkthrough_md || '';
      if (ta) {
        const start = ta.selectionStart ?? currentVal.length;
        const end = ta.selectionEnd ?? currentVal.length;
        selectedGame.value.walkthrough_md = currentVal.slice(0, start) + textToInsert + currentVal.slice(end);
        nextTick(() => {
          ta.focus();
          ta.selectionStart = ta.selectionEnd = start + textToInsert.length;
        });
      } else {
        selectedGame.value.walkthrough_md = currentVal ? (currentVal + '\n' + textToInsert) : textToInsert;
      }
      syncNotesPreviewNow(selectedGame.value.walkthrough_md);
      onNotesInput(true);
    };

    const saveGameNotes = async (silent = false) => {
      if (!selectedGame.value) return;
      if (notesAutoSaveTimer) {
        clearTimeout(notesAutoSaveTimer);
        notesAutoSaveTimer = null;
      }
      notesSaveStatus.value = 'saving';
      try {
        const walkthroughContent = selectedGame.value.walkthrough_md || '';
        const memoContent = selectedGame.value.user_notes || '';
        const res = await fetch(`/api/games/${selectedGame.value.id}/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            walkthrough_md: walkthroughContent,
            user_notes: memoContent
          })
        });
        const data = await res.json();
        if (data.data) {
          selectedGame.value.has_walkthrough = data.data.has_walkthrough;
          selectedGame.value.has_user_notes = data.data.has_user_notes;
          selectedGame.value.has_notes = data.data.has_notes;
          updateGameInList(data.data);
        }

        notesSaveStatus.value = 'saved';
        fetchStats();
        fetchCollections();
        if (!silent) {
          showToast('全结局攻略已保存', 'success');
        }
      } catch (err) {
        notesSaveStatus.value = 'dirty';
        showToast('保存攻略失败: ' + err, 'error');
      }
    };

    const onNotesInput = (skipRenderDebounce = false) => {
      notesSaveStatus.value = 'dirty';
      if (!skipRenderDebounce) {
        if (notesRenderTimer) clearTimeout(notesRenderTimer);
        notesRenderTimer = setTimeout(() => {
          const txt = selectedGame.value?.walkthrough_md || '';
          debouncedNotesHtml.value = renderNotesMarkdown(txt);
          notesTocList.value = extractNotesToc(txt);
        }, 150);
      }
      if (notesAutoSaveTimer) clearTimeout(notesAutoSaveTimer);
      notesAutoSaveTimer = setTimeout(() => {
        saveGameNotes(true);
      }, 1200);
    };

    const openNotesFullscreen = async (game = null) => {
      notesFullscreenLayout.value = configData.value.notes_default_layout || 'split';
      showNotesToc.value = configData.value.notes_default_toc !== false;
      syncScrollEnabled.value = configData.value.notes_sync_scroll !== false;

      if (game && (!selectedGame.value || selectedGame.value.id !== game.id)) {
        selectedGame.value = { walkthrough_md: '', user_notes: '', sample_images: [], ...game };
        populateEditForm(game);
        syncNotesPreviewNow(game.walkthrough_md || '');
      }
      if (!selectedGame.value) return;

      showNotesFullscreen.value = true;
      tocSearchQuery.value = '';
      notesSaveStatus.value = 'saved';

      try {
        const r = await fetch(`/api/games/${selectedGame.value.id}`);
        const data = await r.json();
        if (selectedGame.value && data.data && selectedGame.value.id === data.data.id) {
          selectedGame.value = data.data;
          selectedGameVariants.value = data.variants || [];
          selectedGameMTool.value = data.mtool_status || null;
          selectedGameSave.value = data.save_status || null;
          selectedGameScreenshots.value = data.screenshots || [];
          syncNotesPreviewNow(selectedGame.value.walkthrough_md || '');
        }
      } catch (e) {}
      refreshIcons();
    };

    const closeNotesFullscreen = () => {
      if (notesAutoSaveTimer) {
        clearTimeout(notesAutoSaveTimer);
        notesAutoSaveTimer = null;
        saveGameNotes(true);
      }
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {});
      }
      showNotesFullscreen.value = false;
      refreshIcons();
    };

    const toggleBrowserFullscreen = () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().then(() => {
          isBrowserFullscreen.value = true;
        }).catch((err) => {
          console.warn('Request fullscreen error:', err);
        });
      } else {
        document.exitFullscreen().then(() => {
          isBrowserFullscreen.value = false;
        }).catch(() => {});
      }
    };

    const isMToolEngine = (eng) => {
      if (!eng) return false;
      return ['RPG Maker', 'Wolf RPG', 'RGSS'].some(k => eng.includes(k));
    };

    const shouldUseMToolPrimary = (game) => {
      if (!game) return false;
      return Boolean(game.has_translation && isMToolEngine(game.engine_type));
    };

    const isBakingTranslation = ref(false);

    const bakeTranslationAction = async (game) => {
      if (!game) return;
      const ok = await askConfirm({
        title: '一键固化汉化补丁到游戏本体',
        message: '确定要将外挂翻译直接固化到游戏本体吗？\n\n1. 静态翻译数据注入 data/*.json（自动备份原版至 data_original_backup）\n2. 安装通用运行时动态翻译补丁并注入微软雅黑字体\n3. 固化后原生启动即为中文，且随时支持一键无损还原原版！',
        confirmText: '立即固化汉化',
        cancelText: '取消',
        variant: 'primary'
      });
      if (!ok) return;

      isBakingTranslation.value = true;
      try {
        const res = await fetch(`/api/games/${game.id}/bake_translation`, { method: 'POST' });
        const result = await res.json();
        if (result.success) {
          showToast(result.message || '静态固化汉化成功！原生启动即为中文。', 'success');
          if (selectedGame.value && selectedGame.value.id === game.id) {
            openGameDetail(selectedGame.value, true);
          }
        } else {
          showToast(result.message || '固化失败', 'error');
        }
      } catch (err) {
        showToast('固化发生异常: ' + err, 'error');
      } finally {
        isBakingTranslation.value = false;
        refreshIcons();
      }
    };

    const unbakeTranslationAction = async (game) => {
      if (!game) return;
      const ok = await askConfirm({
        title: '还原游戏原版数据',
        message: '确定要从备份还原游戏的原版 data 数据并移除注入的静态汉化补丁吗？\n（原有的外挂翻译 JSON 字典文件仍会保留）',
        confirmText: '还原原版',
        cancelText: '取消',
        variant: 'warning'
      });
      if (!ok) return;

      isBakingTranslation.value = true;
      try {
        const res = await fetch(`/api/games/${game.id}/unbake_translation`, { method: 'POST' });
        const result = await res.json();
        if (result.success) {
          showToast(result.message || '已成功还原原版游戏数据！', 'success');
          if (selectedGame.value && selectedGame.value.id === game.id) {
            openGameDetail(selectedGame.value, true);
          }
        } else {
          showToast(result.message || '还原失败', 'error');
        }
      } catch (err) {
        showToast('还原发生异常: ' + err, 'error');
      } finally {
        isBakingTranslation.value = false;
        refreshIcons();
      }
    };

    const launchGameAction = async (game, mode = null) => {
      if (isGameRunning(game.id)) {
        showToast('该游戏已在运行中，无需重复启动', 'info', 2000);
        return;
      }
      try {
        const res = await fetch(`/api/games/${game.id}/launch`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: mode })
        });
        const data = await res.json();
        if (data.success) {
          game.play_status = 'playing';
          triggerGamesRef();
          if (selectedGame.value && selectedGame.value.id === game.id) {
            selectedGame.value.play_status = 'playing';
          }
          runningGames.value = {
            ...runningGames.value,
            [game.id]: { game_id: game.id, pid: data.pid, mode: data.mode || mode || 'native', elapsed_seconds: 0 }
          };
          startRunningGamesPoll();
          fetchStats();
          showToast(data.message || '游戏正在启动...', 'success', 2000);
        } else if (data.already_running) {
          showToast(data.message || '游戏已在运行中', 'info', 2000);
        } else {
          showToast(data.message || '启动失败', 'error');
        }
      } catch (err) {
        showToast('启动发生异常: ' + err, 'error');
      }
    };

    const launchMToolAction = async (game) => {
      if (isGameRunning(game.id)) {
        showToast('该游戏已在运行中，无需重复启动', 'info', 2000);
        return;
      }
      try {
        const res = await fetch(`/api/games/${game.id}/launch_mtool`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          game.play_status = 'playing';
          triggerGamesRef();
          if (selectedGame.value && selectedGame.value.id === game.id) {
            selectedGame.value.play_status = 'playing';
          }
          runningGames.value = {
            ...runningGames.value,
            [game.id]: { game_id: game.id, pid: data.pid, mode: 'mtool', elapsed_seconds: 0 }
          };
          startRunningGamesPoll();
          fetchStats();
          showToast(data.message || 'MTool 辅助环境已就绪，正在拉起游戏...', 'success', 2500);
        } else {
          showToast(data.message || 'MTool 启动失败', 'error');
        }
      } catch (err) {
        showToast('MTool 启动发生异常: ' + err, 'error');
      }
    };

    const launchLEAction = async (game) => {
      if (isGameRunning(game.id)) {
        showToast('该游戏已在运行中，无需重复启动', 'info', 2000);
        return;
      }
      try {
        const res = await fetch(`/api/games/${game.id}/launch_le`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          game.play_status = 'playing';
          triggerGamesRef();
          if (selectedGame.value && selectedGame.value.id === game.id) {
            selectedGame.value.play_status = 'playing';
          }
          runningGames.value = {
            ...runningGames.value,
            [game.id]: { game_id: game.id, pid: data.pid, mode: 'le', elapsed_seconds: 0 }
          };
          startRunningGamesPoll();
          fetchStats();
          showToast(data.message || '已通过 Locale Emulator 转区启动', 'success', 2500);
        } else {
          showToast(data.message || '转区启动失败', 'warning', 3200);
        }
      } catch (err) {
        showToast('转区启动异常: ' + err, 'error');
      }
    };

    const openSaveFolderAction = async (game) => {
      try {
        const res = await fetch(`/api/games/${game.id}/open_save`, { method: 'POST' });
        const data = await res.json();
        showToast(data.message || '已打开存档目录', data.success ? 'info' : 'warning', 2000);
      } catch (err) {
        showToast('打开存档目录异常: ' + err, 'error');
      }
    };

    const openSaveBackupsFolderAction = async (game) => {
      try {
        const res = await fetch(`/api/games/${game.id}/open_save_backups`, { method: 'POST' });
        const data = await res.json();
        showToast(data.message || '已打开存档备份目录', 'info', 2000);
      } catch (err) {
        showToast('打开备份目录异常: ' + err, 'error');
      }
    };

    const backupSaveAction = async (game) => {
      if (!game) return;
      isBackingUpSave.value = true;
      try {
        const res = await fetch(`/api/games/${game.id}/backup_save`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          if (data.save_status) {
            selectedGameSave.value = data.save_status;
            showSaveBackupsList.value = true;
          }
          showToast(data.message || '存档快照备份成功！', 'success', 2800);
        } else {
          showToast(data.message || '备份存档失败', 'warning');
        }
      } catch (err) {
        showToast('备份存档异常: ' + err, 'error');
      } finally {
        isBackingUpSave.value = false;
        refreshIcons();
      }
    };

    const syncGameWebDAVAction = async (game) => {
      if (!game) return;
      isSyncingWebDAV.value = true;
      try {
        const res = await fetch(`/api/games/${game.id}/webdav_sync`, { method: 'POST' });
        const data = await res.json();
        if (data.save_status) {
          selectedGameSave.value = data.save_status;
          showSaveBackupsList.value = true;
        }
        showToast(data.message || 'WebDAV 云同步完成', data.success ? 'success' : 'warning', 3200);
      } catch (err) {
        showToast('WebDAV 同步异常: ' + err, 'error');
      } finally {
        isSyncingWebDAV.value = false;
        refreshIcons();
      }
    };

    const restoreSaveBackupAction = async (game, backupItem) => {
      if (!game || !backupItem) return;
      const ok = await askConfirm({
        title: '还原存档快照',
        message: `确定要将存档恢复至快照【${backupItem.created_at}】(${backupItem.filename}) 吗？\n这将覆盖游戏目录中同名的当前存档文件。`,
        confirmText: '确认回档',
        cancelText: '取消',
        variant: 'warning'
      });
      if (!ok) return;

      isRestoringSave.value = true;
      try {
        const res = await fetch(`/api/games/${game.id}/restore_save`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: backupItem.filename })
        });
        const data = await res.json();
        if (data.success) {
          if (data.save_status) {
            selectedGameSave.value = data.save_status;
          }
          showToast(data.message || '存档回档成功！', 'success', 2800);
        } else {
          showToast(data.message || '回档失败', 'error');
        }
      } catch (err) {
        showToast('回档异常: ' + err, 'error');
      } finally {
        isRestoringSave.value = false;
      }
    };

    const deleteSaveBackupAction = async (game, backupItem) => {
      if (!game || !backupItem) return;
      const ok = await askConfirm({
        title: '删除存档快照',
        message: `确定要删除备份快照文件【${backupItem.filename}】吗？`,
        confirmText: '删除快照',
        cancelText: '取消',
        variant: 'danger'
      });
      if (!ok) return;

      try {
        const res = await fetch(`/api/games/${game.id}/delete_save_backup`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: backupItem.filename })
        });
        const data = await res.json();
        if (data.success) {
          if (data.save_status) {
            selectedGameSave.value = data.save_status;
          }
          showToast(data.message || '快照已删除', 'info', 2000);
        } else {
          showToast(data.message || '删除快照失败', 'error');
        }
      } catch (err) {
        showToast('删除快照异常: ' + err, 'error');
      }
    };

    // ---------------------------------------------------------
    // RPG Maker Visual Save Editor Actions (v2.4)
    // ---------------------------------------------------------
    const fetchSaveEditorSlots = async (gameId) => {
      if (!gameId) return;
      try {
        const res = await fetch(`/api/games/${gameId}/save_editor/slots`);
        const data = await res.json();
        if (selectedGame.value && selectedGame.value.id === gameId) {
          saveEditorData.value = data || { supported: false, slots: [] };
          if (data.slots && data.slots.length > 0) {
            selectedSaveSlotFile.value = data.slots[0].filename;
          } else {
            selectedSaveSlotFile.value = '';
          }
        }
      } catch (e) {
        saveEditorData.value = { supported: false, slots: [] };
      }
    };

    const inspectSaveSlotAction = async (filename) => {
      if (!selectedGame.value || !filename) return;
      isLoadingSaveSlot.value = true;
      modifiedSaveVars.value = {};
      modifiedSaveSwitches.value = {};
      saveEditorUnlockAllSwitches.value = false;
      try {
        const res = await fetch(`/api/games/${selectedGame.value.id}/save_editor/slot?filename=${encodeURIComponent(filename)}`);
        const data = await res.json();
        if (data.success) {
          saveSlotDetail.value = data;
        } else {
          saveSlotDetail.value = null;
          showToast(data.message || '解析存档失败', 'warning');
        }
      } catch (err) {
        saveSlotDetail.value = null;
        showToast('读取存档槽位失败: ' + err, 'error');
      } finally {
        isLoadingSaveSlot.value = false;
        refreshIcons();
      }
    };

    const toggleSaveEditorPanel = () => {
      showSaveEditorPanel.value = !showSaveEditorPanel.value;
      if (showSaveEditorPanel.value && selectedSaveSlotFile.value && !saveSlotDetail.value) {
        inspectSaveSlotAction(selectedSaveSlotFile.value);
      }
      refreshIcons();
    };

    const markSaveVarModified = (v) => {
      if (!v) return;
      modifiedSaveVars.value[String(v.id)] = Number(v.value || 0);
    };

    const markSaveSwitchModified = (s) => {
      if (!s) return;
      modifiedSaveSwitches.value[String(s.id)] = Boolean(s.value);
    };

    const maxAllActorsInSlot = () => {
      if (!saveSlotDetail.value || !Array.isArray(saveSlotDetail.value.actors)) return;
      saveSlotDetail.value.actors.forEach(act => {
        act.level = Math.max(act.level || 1, 99);
        act.hp = Math.max(act.hp || 1, 9999);
        act.mp = Math.max(act.mp || 1, 9999);
      });
      showToast('已将全员设为 Lv99 / 9999 HP，点击右下角保存即可写入存档', 'info', 2200);
    };

    const filteredSaveVariables = computed(() => {
      const list = saveSlotDetail.value?.variables || [];
      const q = saveEditorSearchQuery.value.trim().toLowerCase();
      return list.filter(v => {
        if (saveEditorKeyOnly.value && !v.is_key) return false;
        if (!q) return true;
        return (v.name || '').toLowerCase().includes(q) || String(v.id).includes(q);
      });
    });

    const filteredSaveSwitches = computed(() => {
      const list = saveSlotDetail.value?.switches || [];
      const q = saveEditorSearchQuery.value.trim().toLowerCase();
      return list.filter(s => {
        if (saveEditorKeyOnly.value && !s.is_cg) return false;
        if (!q) return true;
        return (s.name || '').toLowerCase().includes(q) || String(s.id).includes(q);
      });
    });

    const saveModifiedSlotAction = async () => {
      if (!selectedGame.value || !saveSlotDetail.value || !selectedSaveSlotFile.value) return;
      isSavingSaveSlot.value = true;
      try {
        const payload = {
          filename: selectedSaveSlotFile.value,
          gold: Number(saveSlotDetail.value.gold ?? 0),
          variables: modifiedSaveVars.value,
          switches: modifiedSaveSwitches.value,
          actors: saveSlotDetail.value.actors || [],
          unlock_all_switches: Boolean(saveEditorUnlockAllSwitches.value)
        };
        const res = await fetch(`/api/games/${selectedGame.value.id}/save_editor/slot`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
          showToast(data.message || '存档修改已成功写入！', 'success', 3500);
          const sRes = await fetch(`/api/games/${selectedGame.value.id}/save_status`);
          selectedGameSave.value = await sRes.json();
          await inspectSaveSlotAction(selectedSaveSlotFile.value);
        } else {
          showToast(data.message || '写入存档失败', 'error');
        }
      } catch (err) {
        showToast('写入存档异常: ' + err, 'error');
      } finally {
        isSavingSaveSlot.value = false;
      }
    };

    // ---------------------------------------------------------
    // Ignored Scan Paths & Archived Duplicates Recovery (v2.4)
    // ---------------------------------------------------------
    const fetchExcludedLibraryData = async () => {
      try {
        const res = await fetch('/api/library/excluded');
        const data = await res.json();
        ignoredPathsList.value = data.ignored_paths || [];
        archivedGamesList.value = data.archived_games || [];
      } catch (e) {}
    };

    const restoreIgnoredPathAction = async (folderPath) => {
      if (!folderPath) return;
      try {
        const res = await fetch('/api/library/ignored/remove', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folder_path: folderPath })
        });
        const data = await res.json();
        if (data.success) {
          ignoredPathsList.value = data.ignored_paths || [];
          showToast(data.message || '已恢复扫描权限', 'success');
        }
      } catch (e) {
        showToast('恢复失败: ' + e, 'error');
      }
    };

    const clearIgnoredPathsAction = async () => {
      try {
        const res = await fetch('/api/library/ignored/clear', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          ignoredPathsList.value = [];
          showToast(data.message || '已清空扫描忽略名单', 'success');
        }
      } catch (e) {
        showToast('清空失败: ' + e, 'error');
      }
    };

    const unarchiveGameAction = async (ag) => {
      if (!ag) return;
      try {
        const res = await fetch('/api/duplicates/unarchive', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ game_id: ag.id })
        });
        const data = await res.json();
        if (data.success) {
          archivedGamesList.value = data.archived_games || [];
          showToast(data.message || '已成功恢复至主库', 'success');
          fetchGames();
          fetchStats();
          fetchCollections();
          if (showDuplicateModal.value) openDuplicateModal(focusedDuplicateGroupId.value);
        } else {
          showToast(data.message || '恢复归档失败', 'warning');
        }
      } catch (e) {
        showToast('恢复归档异常: ' + e, 'error');
      }
    };

    const openFolderAction = async (game) => {
      try {
        await fetch(`/api/games/${game.id}/open_folder`, { method: 'POST' });
      } catch (err) {
        console.error('Open folder error:', err);
      }
    };

    const revealAction = async (game) => {
      try {
        await fetch(`/api/games/${game.id}/reveal`, { method: 'POST' });
      } catch (err) {
        console.error('Reveal error:', err);
      }
    };

    const deleteGameAction = async (game, deleteLocal = false) => {
      if (!game) return;
      showDangerMenu.value = false;
      const ok = await askConfirm({
        title: deleteLocal ? '移入系统回收站并移除' : '从游戏库中移出',
        message: deleteLocal
          ? `确定要删除本地游戏文件夹【${game.folder_name}】并将其移入 Windows 系统回收站吗？\n（同时将从游戏库中清除该记录）`
          : `确定要将游戏【${game.display_title || game.folder_name}】从游戏库列表中移出吗？\n（本地硬盘上的游戏文件将完好保留）`,
        confirmText: deleteLocal ? '移入回收站' : '移出游戏库',
        cancelText: '取消',
        variant: deleteLocal ? 'danger' : 'warning'
      });
      if (!ok) return;

      try {
        const res = await fetch(`/api/games/${game.id}/delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ delete_local: deleteLocal })
        });
        const result = await res.json();
        if (res.ok && result.success) {
          showToast(result.message || '游戏已移出游戏库', 'success');
          if (selectedGame.value && selectedGame.value.id === game.id) {
            selectedGame.value = null;
            isEditMode.value = false;
          }
          games.value = games.value.filter(g => g.id !== game.id);
          fetchStats();
          fetchCollections();
        } else {
          showToast(result.detail || '删除失败', 'error');
        }
      } catch (err) {
        showToast('删除异常: ' + err, 'error');
      }
    };

    const cleanupMissingAction = async () => {
      const ok = await askConfirm({
        title: '清理缺失游戏记录',
        message: `确定要一键从游戏库中清理全部 ${stats.value.missing} 部本地目录已不存在的失效游戏记录吗？`,
        confirmText: '一键清理',
        cancelText: '取消',
        variant: 'warning'
      });
      if (!ok) return;

      try {
        const res = await fetch('/api/games/cleanup_missing', { method: 'POST' });
        const result = await res.json();
        if (result.success) {
          showToast(result.message || '清理完成', 'success');
          missingOnly.value = false;
          fetchGames();
          fetchStats();
          fetchCollections();
        } else {
          showToast('清理失败: ' + result.detail, 'error');
        }
      } catch (err) {
        showToast('清理异常: ' + err, 'error');
      }
    };

    const toggleBatchMode = () => {
      isBatchMode.value = !isBatchMode.value;
      if (!isBatchMode.value) {
        selectedGameIds.value = [];
      }
    };

    const toggleGameSelect = (id) => {
      const idx = selectedGameIds.value.indexOf(id);
      if (idx === -1) selectedGameIds.value.push(id);
      else selectedGameIds.value.splice(idx, 1);
    };

    const isGameSelected = (id) => selectedGameIds.value.includes(id);

    const selectAllCurrentGames = () => {
      if (selectedGameIds.value.length === filteredGames.value.length) {
        selectedGameIds.value = [];
      } else {
        selectedGameIds.value = filteredGames.value.map(g => g.id);
      }
    };

    const batchSetPlayStatus = async (status) => {
      if (selectedGameIds.value.length === 0) return;
      try {
        const res = await fetch('/api/games/batch_update_status', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ game_ids: selectedGameIds.value, play_status: status })
        });
        const result = await res.json();
        if (result.success) {
          showToast(result.message || '批量更新成功', 'success');
          const sIds = new Set(selectedGameIds.value);
          games.value.forEach(g => {
            if (sIds.has(g.id)) g.play_status = status;
          });
          triggerGamesRef();
          fetchStats();
          fetchCollections();
        } else {
          showToast('批量更新失败', 'error');
        }
      } catch (err) {
        showToast('批量更新异常: ' + err, 'error');
      }
    };

    const batchDeleteAction = async (deleteLocal = false) => {
      if (selectedGameIds.value.length === 0) return;
      const count = selectedGameIds.value.length;
      const ok = await askConfirm({
        title: deleteLocal ? `批量移入回收站 (${count} 项)` : `批量移出游戏库 (${count} 项)`,
        message: deleteLocal
          ? `确定要将选中的 ${count} 部本地游戏文件夹移入系统回收站并从库中移除吗？`
          : `确定要将选中的 ${count} 部游戏从库中移出吗？（不会删除本地文件夹）`,
        confirmText: deleteLocal ? '批量移入回收站' : '批量移出库',
        cancelText: '取消',
        variant: deleteLocal ? 'danger' : 'warning'
      });
      if (!ok) return;

      try {
        const res = await fetch('/api/games/batch_delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ game_ids: selectedGameIds.value, delete_local: deleteLocal })
        });
        const result = await res.json();
        if (result.success) {
          showToast(result.message || '批量处理成功', 'success');
          selectedGameIds.value = [];
          fetchGames();
          fetchStats();
          fetchCollections();
        } else {
          showToast(result.message || '批量删除失败', 'error');
        }
      } catch (err) {
        showToast('批量删除异常: ' + err, 'error');
      }
    };

    const openCandidatePicker = async () => {
      if (!selectedGame.value) return;
      showCandidateModal.value = true;
      isSearchingCandidates.value = true;
      scraperCandidates.value = [];
      try {
        const res = await fetch(`/api/games/${selectedGame.value.id}/search_candidates`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            keyword: scrapeInputKeyword.value || selectedGame.value.clean_title,
            rj_code: scrapeInputRJ.value || selectedGame.value.rj_code
          })
        });
        const result = await res.json();
        if (result.success && result.candidates && result.candidates.length > 0) {
          scraperCandidates.value = result.candidates;
        } else {
          showToast('未找到匹配候选结果，您可以更换关键词再试', 'warning');
        }
      } catch (err) {
        showToast('检索候选异常: ' + err, 'error');
      } finally {
        isSearchingCandidates.value = false;
      }
    };

    const applySelectedCandidate = async (candidate) => {
      if (!selectedGame.value || !candidate) return;
      try {
        const res = await fetch(`/api/games/${selectedGame.value.id}/apply_candidate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ candidate: candidate })
        });
        const result = await res.json();
        if (result.success) {
          selectedGame.value = result.data;
          populateEditForm(result.data);
          updateGameInList(result.data);
          showCandidateModal.value = false;
          fetchStats();
          fetchCollections();
          showToast(`已采纳来自【${candidate.source_name}】的元数据！`, 'success');
        } else {
          showToast('应用候选数据失败', 'error');
        }
      } catch (err) {
        showToast('应用异常: ' + err, 'error');
      }
    };

    const triggerManualScrape = async () => {
      if (!selectedGame.value) return;
      isScrapingSingle.value = true;
      try {
        const res = await fetch(`/api/games/${selectedGame.value.id}/scrape`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            rj_code: scrapeInputRJ.value,
            search_keyword: scrapeInputKeyword.value,
            preferred_source: scrapePreferredSource.value
          })
        });
        const result = await res.json();
        if (result.success) {
          selectedGame.value = result.data;
          populateEditForm(result.data);
          updateGameInList(result.data);
          fetchStats();
          fetchCollections();
          showToast('元数据抓取并更新成功！', 'success');
        } else {
          showToast(result.message || '未抓取到匹配信息', 'warning');
        }
      } catch (err) {
        showToast('刮削失败: ' + err, 'error');
      } finally {
        isScrapingSingle.value = false;
        refreshIcons();
      }
    };

    const triggerRescan = async () => {
      scanState.value.is_running = true;
      try {
        await fetch('/api/games/scan', { method: 'POST' });
        showToast('后台扫描任务已启动...', 'info', 2000);
        pollScanStatus();
      } catch (err) {
        showToast('启动扫描失败: ' + err, 'error');
        scanState.value.is_running = false;
      }
    };

    const pollScanStatus = () => {
      const timer = setInterval(async () => {
        try {
          const res = await fetch('/api/games/scan/status');
          const data = await res.json();
          scanState.value = data;
          if (!data.is_running) {
            clearInterval(timer);
            fetchGames();
            fetchStats();
            fetchCollections();
            if (viewMode.value === 'analytics') fetchAnalytics();
            refreshIcons();
            showToast(data.status_message || '扫描完成！', 'success');
            setTimeout(async () => {
              const sRes = await fetch('/api/games/batch_scrape/status');
              const sData = await sRes.json();
              if (sData.is_running) {
                batchScrapeState.value = sData;
                pollBatchScrapeStatus();
              }
            }, 600);
          }
        } catch (err) {
          clearInterval(timer);
        }
      }, 800);
    };

    const triggerBatchScrape = async () => {
      batchScrapeState.value.is_running = true;
      try {
        await fetch('/api/games/batch_scrape', { method: 'POST' });
        showToast('一键批量刮削任务已在后台启动...', 'info', 2500);
        pollBatchScrapeStatus();
      } catch (err) {
        showToast('启动批量刮削失败: ' + err, 'error');
        batchScrapeState.value.is_running = false;
      }
    };

    const pollBatchScrapeStatus = () => {
      const timer = setInterval(async () => {
        try {
          const res = await fetch('/api/games/batch_scrape/status');
          const data = await res.json();
          batchScrapeState.value = data;
          if (!data.is_running) {
            clearInterval(timer);
            fetchGames();
            fetchStats();
            fetchCollections();
            if (viewMode.value === 'analytics') fetchAnalytics();
            refreshIcons();
            showToast(data.status_message || '批量刮削已完成！', 'success');
          }
        } catch (err) {
          clearInterval(timer);
        }
      }, 1200);
    };

    const openDuplicateModal = async (focusGroupId = '') => {
      focusedDuplicateGroupId.value = focusGroupId || '';
      fetchExcludedLibraryData();
      try {
        const res = await fetch('/api/duplicates');
        const data = await res.json();
        duplicateGroups.value = data.data || {};
        showDuplicateModal.value = true;
        refreshIcons();
        if (focusGroupId) {
          nextTick(() => {
            const el = document.getElementById(`dup-group-${focusGroupId}`);
            if (el) {
              el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
          });
        }
      } catch (err) {
        showToast('加载查重数据失败: ' + err, 'error');
      }
    };

    const openDuplicateModalForGame = (game) => {
      openDuplicateModal(game && game.duplicate_group_id ? game.duplicate_group_id : '');
    };

    const archiveSingleVariant = async (variant) => {
      const ok = await askConfirm({
        title: '归档隔离重复版本',
        message: `确定要将版本【${variant.folder_name}】安全移动至归档隔离目录 (_Archive_Duplicates) 吗？\n归档后不会再出现在主库和扫描列表中，但文件安全保留。`,
        confirmText: '安全归档',
        cancelText: '取消',
        variant: 'warning'
      });
      if (!ok) return;

      try {
        const res = await fetch('/api/duplicates/archive', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ game_id: variant.id })
        });
        const data = await res.json();
        showToast(data.message || '归档成功', data.success ? 'success' : 'error');
        fetchGames();
        fetchStats();
        fetchCollections();
        if (showDuplicateModal.value) openDuplicateModal(focusedDuplicateGroupId.value);
        if (selectedGame.value && selectedGame.value.id === variant.id) {
          selectedGame.value = null;
        } else if (selectedGame.value) {
          openGameDetail(selectedGame.value, true);
        }
      } catch (err) {
        showToast('归档失败: ' + err, 'error');
      }
    };

    const dismissDuplicateAction = async (variant, targetId = null) => {
      const name = variant.clean_title || variant.folder_name;
      const ok = await askConfirm({
        title: '标记为独立非重复作品',
        message: `确定要将【${name}】移出当前重复分组吗？\n系统将永久记住该规则，后续扫描不再将其误判为重复版本。`,
        confirmText: '并非重复',
        cancelText: '取消',
        variant: 'primary'
      });
      if (!ok) return;

      try {
        const res = await fetch('/api/duplicates/dismiss', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ game_id: variant.id, target_id: targetId })
        });
        const data = await res.json();
        showToast(data.message || '已取消重复关联', 'success');
        await fetchGames();
        await fetchStats();
        if (showDuplicateModal.value) await openDuplicateModal(focusedDuplicateGroupId.value);
        if (selectedGame.value) {
          await openGameDetail(selectedGame.value, true);
        }
      } catch (err) {
        showToast('取消重复失败: ' + err, 'error');
      }
    };

    watch(showSettingsModal, (val) => {
      if (val) fetchExcludedLibraryData();
    });

    watch(
      [
        selectedGame,
        drawerActiveTab,
        isEditMode,
        showSaveBackupsList,
        notesEditMode,
        showRescrapePanel,
        showDangerMenu,
        showDuplicateModal,
        showSettingsModal,
        settingsActiveTab,
        showShortcutModal,
        showCandidateModal,
        showCollectionModal,
        showNotesFullscreen,
        notesFullscreenLayout,
        showNotesToc,
        lightboxShot,
        () => confirmDialog.visible
      ],
      () => {
        refreshIcons();
      }
    );

    const handleGlobalKeydown = (e) => {
      if (lightboxShot.value && e.key === 'Escape') {
        e.preventDefault();
        lightboxShot.value = null;
        return;
      }

      if (confirmDialog.visible) {
        if (e.key === 'Escape') {
          e.preventDefault();
          resolveConfirmDialog(false);
          return;
        }
        if (e.key === 'Enter') {
          e.preventDefault();
          resolveConfirmDialog(true);
          return;
        }
        return;
      }

      if (e.altKey && e.key.toLowerCase() === 'g') {
        e.preventDefault();
        openCompanionOverlayAction();
        return;
      }

      const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
      const isInputFocused = activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select';

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        if (showNotesFullscreen.value || (selectedGame.value && (notesEditMode.value || drawerActiveTab.value === 'walkthrough'))) {
          e.preventDefault();
          saveGameNotes(false);
          return;
        }
      }

      if (((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') || (!isInputFocused && e.key === '/' && !selectedGame.value && !showNotesFullscreen.value)) {
        e.preventDefault();
        if (searchInputRef.value) {
          searchInputRef.value.focus();
          searchInputRef.value.select();
        }
        return;
      }

      if (!isInputFocused && selectedGame.value && !isEditMode.value && !showNotesFullscreen.value && !showCandidateModal.value) {
        if (e.key === 'ArrowLeft') {
          e.preventDefault();
          navigateAdjacentGame(-1);
          return;
        }
        if (e.key === 'ArrowRight') {
          e.preventDefault();
          navigateAdjacentGame(1);
          return;
        }
      }

      if (e.key === 'Escape') {
        if (isInputFocused) {
          document.activeElement.blur();
          return;
        }
        if (showNotesFullscreen.value) {
          e.preventDefault();
          closeNotesFullscreen();
          return;
        }
        if (showCollectionModal.value) {
          e.preventDefault();
          showCollectionModal.value = false;
          return;
        }
        if (showCandidateModal.value) {
          e.preventDefault();
          showCandidateModal.value = false;
          return;
        }
        if (showShortcutModal.value) {
          e.preventDefault();
          showShortcutModal.value = false;
          return;
        }
        if (showDuplicateModal.value) {
          e.preventDefault();
          showDuplicateModal.value = false;
          return;
        }
        if (showSettingsModal.value) {
          e.preventDefault();
          showSettingsModal.value = false;
          return;
        }
        if (selectedGame.value && !isEditMode.value) {
          e.preventDefault();
          closeGameDetail();
          return;
        }
      }
    };

    onMounted(() => {
      fetchConfig();
      fetchGames();
      fetchStats();
      fetchCollections();
      if (viewMode.value === 'analytics') {
        fetchAnalytics();
      }
      window.addEventListener('paste', handleGlobalPaste);
      window.addEventListener('keydown', handleGlobalKeydown);
      document.addEventListener('fullscreenchange', () => {
        isBrowserFullscreen.value = Boolean(document.fullscreenElement);
      });
    });

    return {
      games,
      filteredGames,
      displayedGames,
      visibleLimit,
      loadMoreGames,
      stats,
      collections,
      activeCollectionId,
      activeCollection,
      showCollectionModal,
      collectionForm,
      selectCollectionFilter,
      openCreateCollectionModal,
      openEditCollectionModal,
      saveCollectionAction,
      deleteCollectionAction,
      toggleGameInManualCollection,
      batchAddToCollectionAction,
      analyticsData,
      isLoadingAnalytics,
      isExportingPoster,
      fetchAnalytics,
      exportAnalyticsPosterAction,
      openGameById,
      openCompanionOverlayAction,
      getThumbUrl,
      hasGameWalkthrough,
      hasPersonalMemo,
      runningGames,
      isGameRunning,
      getGameRunningInfo,
      formatRunningDuration,
      confirmDialog,
      resolveConfirmDialog,
      toasts,
      showToast,
      removeToast,
      refreshIcons,
      isLoading,
      viewMode,
      setViewMode,
      coverFitMode,
      cycleCoverFitMode,
      gridDensity,
      cycleGridDensity,
      gridColumnsClass,
      cardHoverStyle,
      notesFontSize,
      searchKeyword,
      searchInputRef,
      currentStatus,
      favoriteOnly,
      missingOnly,
      showToolsOnly,
      hasNotesOnly,
      unscrapedOnly,
      engineFilter,
      transFilter,
      hasActiveSubFilters,
      sortBy,
      sortOrder,
      sortByColumn,
      statusTabs,
      selectedGame,
      drawerActiveTab,
      currentGameIndex,
      navigateAdjacentGame,
      selectedGameVariants,
      selectedGameMTool,
      selectedGameSave,
      selectedGameScreenshots,
      lightboxShot,
      openSampleLightbox,
      isCapturingScreenshot,
      screenshotFileInput,
      cgSaveFileInput,
      isUnlockingCG,
      isGeneratingGuide,
      isParsingFolderAI,
      isLocalizingTags,
      localizeAllTagsAction,
      captureGameScreenshotAction,
      triggerScreenshotUpload,
      handleScreenshotUpload,
      saveScreenshotCaptionAction,
      deleteScreenshotAction,
      unlockAllCGAction,
      triggerCGSaveImport,
      handleCGSaveImport,
      aiParseFolderAction,
      generateAIWalkthroughAction,
      showSaveBackupsList,
      isBackingUpSave,
      isRestoringSave,
      isSyncingWebDAV,
      openSaveFolderAction,
      openSaveBackupsFolderAction,
      backupSaveAction,
      syncGameWebDAVAction,
      restoreSaveBackupAction,
      deleteSaveBackupAction,
      showRescrapePanel,
      showDangerMenu,
      showAddUserTag,
      newUserTagInput,
      addQuickUserTag,
      removeQuickUserTag,
      isMToolEngine,
      shouldUseMToolPrimary,
      isBakingTranslation,
      bakeTranslationAction,
      unbakeTranslationAction,
      launchMToolAction,
      launchLEAction,
      isScrapingSingle,
      scrapeInputRJ,
      scrapeInputKeyword,
      scrapePreferredSource,
      isEditMode,
      isUploadingCover,
      coverFileInput,
      editForm,
      editTagsList,
      editUserTagsList,
      newEditTagInput,
      newEditUserTagInput,
      addEditTagChip,
      removeEditTagChip,
      editTagsString,
      editVoiceActorsString,
      showDuplicateModal,
      duplicateGroups,
      focusedDuplicateGroupId,
      showSettingsModal,
      settingsActiveTab,
      showShortcutModal,
      isTestingProxy,
      proxyTestResults,
      isTestingLLM,
      isTestingWebDAV,
      applyLLMPreset,
      testLLMConnectionAction,
      testWebDAVAction,
      configData,
      pickLocalPathAction,
      scanState,
      batchScrapeState,
      isBatchMode,
      selectedGameIds,
      toggleBatchMode,
      toggleGameSelect,
      isGameSelected,
      selectAllCurrentGames,
      batchSetPlayStatus,
      batchDeleteAction,
      showCandidateModal,
      isSearchingCandidates,
      scraperCandidates,
      openCandidatePicker,
      applySelectedCandidate,
      formatEngineShort,
      formatPlayedTime,
      getStatusLabel,
      getStatusDotColor,
      getStatusBadgeClass,
      getStatusCount,
      fetchGames,
      resetFilters,
      debounceSearch,
      filterByKeyword,
      toggleFavorite,
      toggleSortOrder,
      openGameDetail,
      closeGameDetail,
      triggerLocalCoverUpload,
      handleFileUpload,
      pasteClipboardImage,
      clearAllEditFields,
      saveManualEdit,
      updateGameStatus,
      updateGameRating,
      deleteGameAction,
      cleanupMissingAction,
      personalMemoSaveStatus,
      onPersonalNoteInput,
      savePersonalNoteNow,
      appendPersonalMemoSnippet,
      notesEditMode,
      debouncedNotesHtml,
      renderNotesMarkdown,
      saveGameNotes,
      showNotesFullscreen,
      notesFullscreenLayout,
      showNotesToc,
      notesSaveStatus,
      notesTocList,
      filteredTocList,
      tocSearchQuery,
      activeHeadingId,
      syncScrollEnabled,
      splitLeftWidthPct,
      isDraggingSplit,
      startSplitDrag,
      onEditorScroll,
      onPreviewScroll,
      insertMarkdownSnippet,
      isBrowserFullscreen,
      openNotesFullscreen,
      closeNotesFullscreen,
      toggleBrowserFullscreen,
      scrollToHeading,
      handleNotesContentClick,
      onNotesInput,
      launchGameAction,
      openFolderAction,
      revealAction,
      triggerManualScrape,
      triggerRescan,
      triggerBatchScrape,
      openDuplicateModal,
      openDuplicateModalForGame,
      archiveSingleVariant,
      dismissDuplicateAction,
      saveConfigAction,
      testProxyAction,
      getEngineBadgeColor,
      getCardSmartSlotItems,
      showSaveEditorPanel,
      saveEditorData,
      selectedSaveSlotFile,
      saveSlotDetail,
      isLoadingSaveSlot,
      isSavingSaveSlot,
      saveEditorSearchQuery,
      saveEditorKeyOnly,
      saveEditorUnlockAllSwitches,
      filteredSaveVariables,
      filteredSaveSwitches,
      toggleSaveEditorPanel,
      inspectSaveSlotAction,
      markSaveVarModified,
      markSaveSwitchModified,
      maxAllActorsInSlot,
      saveModifiedSlotAction,
      ignoredPathsList,
      archivedGamesList,
      restoreIgnoredPathAction,
      clearIgnoredPathsAction,
      unarchiveGameAction
    };
  }
}).mount('#app');
