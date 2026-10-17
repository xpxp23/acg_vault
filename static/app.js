const { createApp, ref, reactive, computed, watch, onMounted, nextTick } = Vue;

createApp({
  setup() {
    const games = ref([]);
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
      translated: 0,
      unscraped: 0,
      tools_count: 0,
      total_size_bytes: 0,
      total_size_str: '0 MB',
      total_played_hours: 0
    });

    const filteredStatusCounts = ref(null);
    const runningGames = ref({}); // game_id -> { pid, exe, mode, elapsed_seconds }
    let runningPollTimer = null;

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

    const refreshIcons = () => {
      nextTick(() => {
        if (window.lucide) {
          window.lucide.createIcons();
        }
      });
    };

    // Custom Glassmorphic Confirmation Dialog (Replaces native window.confirm)
    const confirmDialog = reactive({
      visible: false,
      title: '操作确认',
      message: '',
      confirmText: '确认执行',
      cancelText: '取消',
      variant: 'primary', // 'primary' | 'danger' | 'warning'
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
    const viewMode = ref(localStorage.getItem('acg_view_mode') || 'grid'); // 'grid' | 'list'
    const coverFitMode = ref(localStorage.getItem('acg_cover_fit') || 'smart'); // 'smart' | 'portrait' | 'landscape'
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

    const hasActiveSubFilters = computed(() => {
      return Boolean(
        searchKeyword.value.trim() ||
        favoriteOnly.value ||
        missingOnly.value ||
        showToolsOnly.value ||
        hasNotesOnly.value ||
        unscrapedOnly.value ||
        engineFilter.value !== 'all' ||
        transFilter.value !== 'all'
      );
    });

    // Fullscreen Notes & Walkthrough Workspace states
    const showNotesFullscreen = ref(false);
    const notesFullscreenLayout = ref('split'); // 'split' | 'reader' | 'editor'
    const showNotesToc = ref(true);
    const notesSaveStatus = ref('saved'); // 'saved' | 'saving' | 'dirty'
    const notesTocList = ref([]);
    const tocSearchQuery = ref('');
    const activeHeadingId = ref('');
    const syncScrollEnabled = ref(true);
    const isBrowserFullscreen = ref(false);
    let notesAutoSaveTimer = null;
    let isSyncingLeft = false;
    let isSyncingRight = false;

    const filteredTocList = computed(() => {
      const q = tocSearchQuery.value.trim().toLowerCase();
      if (!q) return notesTocList.value;
      return notesTocList.value.filter(item => item.title.toLowerCase().includes(q));
    });

    // Selected game & details
    const selectedGame = ref(null);
    const selectedGameVariants = ref([]);
    const selectedGameMTool = ref(null);
    const selectedGameSave = ref(null);
    const showSaveBackupsList = ref(false);
    const isBackingUpSave = ref(false);
    const isRestoringSave = ref(false);
    const showRescrapePanel = ref(false);
    const showDangerMenu = ref(false);
    const isScrapingSingle = ref(false);
    const scrapeInputRJ = ref('');
    const scrapeInputKeyword = ref('');
    const scrapePreferredSource = ref('auto');

    const currentGameIndex = computed(() => {
      if (!selectedGame.value || !games.value.length) return -1;
      return games.value.findIndex(g => g.id === selectedGame.value.id);
    });

    const navigateAdjacentGame = (delta) => {
      if (!selectedGame.value || isEditMode.value) return;
      const idx = currentGameIndex.value;
      if (idx === -1) return;
      const targetIdx = idx + delta;
      if (targetIdx >= 0 && targetIdx < games.value.length) {
        openGameDetail(games.value[targetIdx]);
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
      rj_code: ''
    });
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
    const showShortcutModal = ref(false);
    const isTestingProxy = ref(false);

    const configData = ref({
      game_directories: ['E:\\ACG'],
      archive_directory: 'E:\\ACG\\_Archive_Duplicates',
      save_backup_directory: 'E:\\ACG\\_Save_Backups',
      mtool_directory: 'E:\\ACG\\MTool',
      leproc_path: '',
      proxy: '',
      auto_scrape: true,
      scrape_source: 'auto',
      cover_fit_mode: 'smart',
      port: 8000
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

    const setViewMode = (mode) => {
      viewMode.value = mode;
      localStorage.setItem('acg_view_mode', mode);
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
            showToast('游戏已退出，本次游玩时长已自动同步记录', 'info', 2600);
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
      if (!silent) isLoading.value = true;
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
        games.value = data.data || [];
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
        if (!silent) isLoading.value = false;
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
      } finally {
        refreshIcons();
      }
    };

    const fetchConfig = async () => {
      try {
        const res = await fetch('/api/config');
        const data = await res.json();
        configData.value = data;
        if (data.cover_fit_mode && !localStorage.getItem('acg_cover_fit')) {
          coverFitMode.value = data.cover_fit_mode;
        }
      } catch (err) {
        console.error('Failed to load config:', err);
      }
    };

    const saveConfigAction = async () => {
      try {
        configData.value.cover_fit_mode = coverFitMode.value;
        const res = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(configData.value)
        });
        if (res.ok) {
          const saved = await res.json();
          if (saved.data) configData.value = saved.data;
          showSettingsModal.value = false;
          showToast('系统设置已保存！', 'success');
        } else {
          showToast('保存设置失败', 'error');
        }
      } catch (err) {
        showToast('保存设置异常: ' + err, 'error');
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
      try {
        const res = await fetch('/api/config/test_proxy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ proxy: configData.value.proxy })
        });
        const result = await res.json();
        showToast(result.message, result.success ? 'success' : 'warning');
      } catch (err) {
        showToast('测试代理失败: ' + err, 'error');
      } finally {
        isTestingProxy.value = false;
      }
    };

    const toggleFavorite = async (game) => {
      const newFav = game.is_favorite ? 0 : 1;
      game.is_favorite = newFav;
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
      engineFilter.value = 'all';
      transFilter.value = 'all';
      fetchGames();
    };

    let searchTimer = null;
    const debounceSearch = () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        fetchGames();
      }, 240);
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
      editForm.rj_code = game.rj_code || '';
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
        rj_code: editForm.rj_code,
        tags: editTagsString.value,
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
        rj_code: editForm.rj_code,
        tags: editTagsString.value,
        va: editVoiceActorsString.value
      });
      return current !== editFormSnapshot;
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
      if (notesAutoSaveTimer) {
        clearTimeout(notesAutoSaveTimer);
        notesAutoSaveTimer = null;
        saveGameNotes(true);
      }
      selectedGame.value = null;
    };

    const openGameDetail = async (game, silentRefresh = false) => {
      if (!silentRefresh) {
        selectedGame.value = { ...game };
        selectedGameVariants.value = [];
        selectedGameMTool.value = null;
        selectedGameSave.value = null;
        showSaveBackupsList.value = false;
        isEditMode.value = false;
        showDangerMenu.value = false;
        showRescrapePanel.value = !game.cover_url || !game.synopsis;
        scrapeInputRJ.value = game.rj_code || '';
        scrapeInputKeyword.value = game.clean_title || game.folder_name || '';
        scrapePreferredSource.value = configData.value.scrape_source || 'auto';
        populateEditForm(game);
      }

      try {
        const res = await fetch(`/api/games/${game.id}`);
        const data = await res.json();
        if (selectedGame.value && selectedGame.value.id === game.id) {
          selectedGame.value = data.data;
          selectedGameVariants.value = data.variants || [];
          selectedGameMTool.value = data.mtool_status || null;
          selectedGameSave.value = data.save_status || null;
          if (!isEditMode.value) {
            populateEditForm(data.data);
          }
          const idx = games.value.findIndex(g => g.id === game.id);
          if (idx !== -1) games.value[idx] = data.data;
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
          const idx = games.value.findIndex(g => g.id === selectedGame.value.id);
          if (idx !== -1) {
            games.value[idx].cover_url = result.cover_url;
            games.value[idx].banner_url = result.cover_url;
          }
          fetchStats();
          showToast('封面图片上传并更新成功！', 'success');
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
      editForm.rj_code = '';
      editTagsString.value = '';
      editVoiceActorsString.value = '';
      showToast('表单内容已清空，点击保存即可生效', 'info');
    };

    const saveManualEdit = async () => {
      if (!selectedGame.value) return;

      const tagsList = editTagsString.value.split(/[,，]/).map(t => t.trim()).filter(Boolean);
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
        rj_code: editForm.rj_code,
        tags: tagsList,
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
          const idx = games.value.findIndex(g => g.id === selectedGame.value.id);
          if (idx !== -1) games.value[idx] = result.data;
          isEditMode.value = false;
          fetchStats();
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
      const idx = games.value.findIndex(g => g.id === selectedGame.value.id);
      if (idx !== -1) games.value[idx].play_status = status;

      try {
        await fetch(`/api/games/${selectedGame.value.id}/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ play_status: status })
        });
        fetchStats();
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
      const idx = games.value.findIndex(g => g.id === selectedGame.value.id);
      if (idx !== -1) games.value[idx].user_rating = newRating;

      try {
        await fetch(`/api/games/${selectedGame.value.id}/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_rating: newRating })
        });
        showToast(newRating ? `已评分: ${newRating} 星` : '已清除个人评分', 'info', 1600);
      } catch (err) {
        console.error('Update rating error:', err);
        showToast('评分更新失败', 'error');
      }
    };

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

    const sanitizeRenderedHtml = (html) => {
      if (!html) return '';
      return String(html)
        .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
        .replace(/<(iframe|object|embed|form)\b[^>]*>.*?<\/\1>/gis, '')
        .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '');
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
        return '<span class="text-slate-500 italic">暂无通关笔记或攻略，点击上方【快速编辑】、【插入攻略模板】或【全屏攻略工作台】即可编写...</span>';
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
      for (const line of lines) {
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
            normKey
          });
        }
      }
      return toc;
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
        if (!target && id) {
          const decoded = safeDecodeUri(id).replace(/^#+/, '');
          target = allHeadings.find(el => {
            const title = el.getAttribute('data-toc-title') || el.innerText || el.textContent || '';
            return title.includes(decoded) || decoded.includes(title);
          });
        }
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

    const handleNotesContentClick = (event) => {
      const checkbox = event.target.closest('input.notes-interactive-checkbox');
      if (checkbox && selectedGame.value && selectedGame.value.user_notes) {
        const targetIdx = parseInt(checkbox.getAttribute('data-checkbox-idx'), 10);
        if (!isNaN(targetIdx)) {
          let currentMatch = 0;
          selectedGame.value.user_notes = selectedGame.value.user_notes.replace(/^(\s*[-*+]\s+\[)([ xX])(\])/gm, (full, p1, state, p3) => {
            if (currentMatch++ === targetIdx) {
              const nextState = state === ' ' ? 'x' : ' ';
              return `${p1}${nextState}${p3}`;
            }
            return full;
          });
          onNotesInput();
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

    const onEditorScroll = (e) => {
      if (!syncScrollEnabled.value || notesFullscreenLayout.value !== 'split' || isSyncingLeft) return;
      const editor = e.target;
      const preview = document.getElementById('notes-preview-scroll-container');
      if (!editor || !preview) return;

      isSyncingRight = true;
      const maxEditor = editor.scrollHeight - editor.clientHeight;
      const maxPreview = preview.scrollHeight - preview.clientHeight;
      if (maxEditor > 0 && maxPreview > 0) {
        const ratio = editor.scrollTop / maxEditor;
        preview.scrollTop = ratio * maxPreview;
      }
      setTimeout(() => { isSyncingRight = false; }, 40);
    };

    const onPreviewScroll = (e) => {
      const preview = e.target;
      if (!preview) return;

      const headings = Array.from(preview.querySelectorAll('h1, h2, h3, h4'));
      const previewTop = preview.getBoundingClientRect().top;
      let currentId = '';
      for (const h of headings) {
        const offset = h.getBoundingClientRect().top - previewTop;
        if (offset <= 100) {
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

      if (!syncScrollEnabled.value || notesFullscreenLayout.value !== 'split' || isSyncingRight) return;
      const editor = document.getElementById('notes-editor-textarea');
      if (!editor) return;

      isSyncingLeft = true;
      const maxPreview = preview.scrollHeight - preview.clientHeight;
      const maxEditor = editor.scrollHeight - editor.clientHeight;
      if (maxPreview > 0 && maxEditor > 0) {
        const ratio = preview.scrollTop / maxPreview;
        editor.scrollTop = ratio * maxEditor;
      }
      setTimeout(() => { isSyncingLeft = false; }, 40);
    };

    const insertMarkdownSnippet = (type) => {
      if (!selectedGame.value) return;
      const snippets = {
        h2: '\n## 章节标题\n',
        bold: '**重点内容**',
        checklist: '\n- [ ] 结局/CG收集项 1\n- [ ] 结局/CG收集项 2\n',
        table: '\n| 章节/阶段 | 关键选项 / 触发条件 | 好感度/属性变化 | 解锁结局 / 备注 |\n| :--- | :--- | :--- | :--- |\n| 第一章 | 选择「留下来帮忙」 | 好感 +10 | 关键主线分支 |\n| 终章 | 满足好感 ≥ 80 | 触发 True End | 解锁全回想 |\n',
        spoiler: '\n<details>\n<summary>点击展开隐藏剧透 / 作弊密码</summary>\n\n- 全回想开启位置：标题画面右侧隐藏开关\n- 保险箱密码：`1024`\n\n</details>\n',
        template: `# 《${selectedGame.value.display_title || selectedGame.value.clean_title}》全流程全结局攻略\n\n## 一、 核心机制与通关提示\n- **全CG/回想解锁方式**：\n- **关键数值/状态说明**：\n\n## 二、 主线流程与关键分支表\n| 阶段 | 地点 / NPC | 关键行动与选项 | 结果 / 解锁内容 |\n| :--- | :--- | :--- | :--- |\n| 序章 | 初始房间 | 调查书桌获取道具 | 开启主线 |\n| 中盘 | 王都广场 | 夜晚前往酒馆触发支线 | 解锁支线事件 |\n\n## 三、 全结局达成条件 Checklist\n- [ ] **True End (真结局)**：\n- [ ] **Normal End (普通结局)**：\n- [ ] **Bad End / 特殊结局**：\n`
      };
      const textToInsert = snippets[type] || '';
      if (!textToInsert) return;

      const ta = document.getElementById('notes-editor-textarea') || document.getElementById('drawer-notes-textarea');
      const currentVal = selectedGame.value.user_notes || '';
      if (ta) {
        const start = ta.selectionStart ?? currentVal.length;
        const end = ta.selectionEnd ?? currentVal.length;
        selectedGame.value.user_notes = currentVal.slice(0, start) + textToInsert + currentVal.slice(end);
        nextTick(() => {
          ta.focus();
          ta.selectionStart = ta.selectionEnd = start + textToInsert.length;
        });
      } else {
        selectedGame.value.user_notes = currentVal ? (currentVal + '\n' + textToInsert) : textToInsert;
      }
      onNotesInput();
    };

    const saveGameNotes = async (silent = false) => {
      if (!selectedGame.value) return;
      if (notesAutoSaveTimer) {
        clearTimeout(notesAutoSaveTimer);
        notesAutoSaveTimer = null;
      }
      notesSaveStatus.value = 'saving';
      try {
        const notesContent = selectedGame.value.user_notes || '';
        await fetch(`/api/games/${selectedGame.value.id}/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_notes: notesContent })
        });

        const target = games.value.find(g => g.id === selectedGame.value.id);
        if (target) {
          target.user_notes = notesContent;
        }

        notesSaveStatus.value = 'saved';
        fetchStats();
        if (!silent) {
          showToast('攻略笔记已保存', 'success');
        }
      } catch (err) {
        notesSaveStatus.value = 'dirty';
        showToast('保存笔记失败: ' + err, 'error');
      }
    };

    const onNotesInput = () => {
      notesSaveStatus.value = 'dirty';
      notesTocList.value = extractNotesToc(selectedGame.value?.user_notes);
      if (notesAutoSaveTimer) clearTimeout(notesAutoSaveTimer);
      notesAutoSaveTimer = setTimeout(() => {
        saveGameNotes(true);
      }, 1200);
    };

    const openNotesFullscreen = async (game = null) => {
      if (game && (!selectedGame.value || selectedGame.value.id !== game.id)) {
        selectedGame.value = { ...game };
        populateEditForm(game);
        fetch(`/api/games/${game.id}`)
          .then(r => r.json())
          .then(data => {
            if (selectedGame.value && selectedGame.value.id === game.id) {
              selectedGame.value = data.data;
              selectedGameVariants.value = data.variants || [];
              selectedGameMTool.value = data.mtool_status || null;
              selectedGameSave.value = data.save_status || null;
              notesTocList.value = extractNotesToc(selectedGame.value.user_notes);
            }
          })
          .catch(() => {});
      }
      if (!selectedGame.value) return;
      showNotesFullscreen.value = true;
      tocSearchQuery.value = '';
      notesSaveStatus.value = 'saved';
      notesTocList.value = extractNotesToc(selectedGame.value.user_notes);
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
        message: '确定要从备份还原游戏的原版 data 数据并移除注入的静态汉化补丁吗？\n（外挂翻译 JSON 字典文件仍会保留）',
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
      if (selectedGameIds.value.length === games.value.length) {
        selectedGameIds.value = [];
      } else {
        selectedGameIds.value = games.value.map(g => g.id);
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
          fetchStats();
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
          const idx = games.value.findIndex(g => g.id === selectedGame.value.id);
          if (idx !== -1) games.value[idx] = result.data;
          showCandidateModal.value = false;
          fetchStats();
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
          const idx = games.value.findIndex(g => g.id === selectedGame.value.id);
          if (idx !== -1) games.value[idx] = result.data;
          fetchStats();
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

    // Automatic reactive Lucide icon rendering whenever modals, drawers, or sub-panels toggle
    watch(
      [
        stats,
        runningGames,
        selectedGame,
        isEditMode,
        showSaveBackupsList,
        notesEditMode,
        showRescrapePanel,
        showDangerMenu,
        showDuplicateModal,
        showSettingsModal,
        showShortcutModal,
        showCandidateModal,
        showNotesFullscreen,
        notesFullscreenLayout,
        showNotesToc,
        () => confirmDialog.visible
      ],
      () => {
        refreshIcons();
      }
    );

    const handleGlobalKeydown = (e) => {
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

      const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
      const isInputFocused = activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select';

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        if (showNotesFullscreen.value || (selectedGame.value && notesEditMode.value)) {
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
      window.addEventListener('paste', handleGlobalPaste);
      window.addEventListener('keydown', handleGlobalKeydown);
      document.addEventListener('fullscreenchange', () => {
        isBrowserFullscreen.value = Boolean(document.fullscreenElement);
      });
    });

    return {
      games,
      stats,
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
      currentGameIndex,
      navigateAdjacentGame,
      selectedGameVariants,
      selectedGameMTool,
      selectedGameSave,
      showSaveBackupsList,
      isBackingUpSave,
      isRestoringSave,
      openSaveFolderAction,
      openSaveBackupsFolderAction,
      backupSaveAction,
      restoreSaveBackupAction,
      deleteSaveBackupAction,
      showRescrapePanel,
      showDangerMenu,
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
      editTagsString,
      editVoiceActorsString,
      showDuplicateModal,
      duplicateGroups,
      focusedDuplicateGroupId,
      showSettingsModal,
      showShortcutModal,
      isTestingProxy,
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
      notesEditMode,
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
      testProxyAction
    };
  }
}).mount('#app');
