const { createApp, ref, reactive, computed, onMounted, nextTick } = Vue;

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
      total_size_bytes: 0,
      total_size_str: '0 MB',
      total_played_hours: 0
    });

    // Toast Notifications System (Fixed removeToast bug)
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

    const isLoading = ref(true);
    const viewMode = ref(localStorage.getItem('acg_view_mode') || 'grid'); // 'grid' | 'list'
    const coverFitMode = ref(localStorage.getItem('acg_cover_fit') || 'smart'); // 'smart' | 'portrait' | 'landscape'
    const searchKeyword = ref('');
    const currentStatus = ref('all');
    const favoriteOnly = ref(false);
    const missingOnly = ref(false);
    const showToolsOnly = ref(false);
    const hasNotesOnly = ref(false);
    const unscrapedOnly = ref(false);
    const engineFilter = ref('all');
    const transFilter = ref('all'); // 'all' | 'translated' | 'raw'
    const sortBy = ref('downloaded_at');
    const sortOrder = ref('desc');

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
    const isBackingUpSave = ref(false);
    const showRescrapePanel = ref(false);
    const showDangerMenu = ref(false);
    const isScrapingSingle = ref(false);
    const scrapeInputRJ = ref('');
    const scrapeInputKeyword = ref('');
    const scrapePreferredSource = ref('auto');

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
      { label: '全部', value: 'all' },
      { label: '⚪ 未玩', value: 'unplayed' },
      { label: '🟡 游玩中', value: 'playing' },
      { label: '🟢 已通关', value: 'completed' },
      { label: '🟣 想玩', value: 'backlog' },
      { label: '🔴 搁置', value: 'dropped' }
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

    const refreshIcons = () => {
      nextTick(() => {
        if (window.lucide) {
          window.lucide.createIcons();
        }
      });
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
      if (status === 'all') return stats.value.total;
      return stats.value[status] || 0;
    };

    const fetchGames = async () => {
      isLoading.value = true;
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
      } catch (err) {
        console.error('Failed to load games:', err);
        showToast('加载游戏库失败: ' + err, 'error');
      } finally {
        isLoading.value = false;
        refreshIcons();
      }
    };

    const fetchStats = async () => {
      try {
        const res = await fetch('/api/stats');
        stats.value = await res.json();
      } catch (err) {
        console.error('Failed to load stats:', err);
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
          showSettingsModal.value = false;
          showToast('系统设置已保存！', 'success');
        } else {
          showToast('保存设置失败', 'error');
        }
      } catch (err) {
        showToast('保存设置异常: ' + err, 'error');
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
        showToast(newFav ? '已添加至收藏 ❤️' : '已取消收藏', 'info', 1600);
      } catch (err) {
        console.error('Update favorite error:', err);
        showToast('更新收藏失败', 'error');
      }
    };

    const toggleSortOrder = () => {
      sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc';
      fetchGames();
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
      sortBy.value = 'downloaded_at';
      sortOrder.value = 'desc';
      fetchGames();
    };

    let searchTimer = null;
    const debounceSearch = () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        fetchGames();
      }, 260);
    };

    const populateEditForm = (game) => {
      editForm.display_title = game.display_title || '';
      editForm.original_title = game.original_title || '';
      editForm.circle_name = game.circle_name || '';
      editForm.release_date = game.release_date || '';
      editForm.downloaded_at = game.downloaded_at || '';
      editForm.cover_url = game.cover_url || '';
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
        synopsis: editForm.synopsis,
        rj_code: editForm.rj_code,
        tags: editTagsString.value,
        va: editVoiceActorsString.value
      });
      return current !== editFormSnapshot;
    };

    const closeGameDetail = (fromBackdrop = false) => {
      showDangerMenu.value = false;
      if (isEditMode.value) {
        if (fromBackdrop) {
          showToast('正在编辑内容，点击背景不会关闭。请保存或点击 ✖ 退出编辑', 'warning', 2200);
          return;
        }
        if (isEditDirty()) {
          if (!confirm('您有正在编辑且尚未保存的修改，确定要放弃本次修改并关闭吗？')) {
            return;
          }
        }
        isEditMode.value = false;
      }
      selectedGame.value = null;
    };

    const openGameDetail = async (game) => {
      selectedGame.value = { ...game };
      selectedGameVariants.value = [];
      selectedGameMTool.value = null;
      selectedGameSave.value = null;
      isEditMode.value = false;
      showDangerMenu.value = false;
      showRescrapePanel.value = !game.cover_url || !game.synopsis;
      scrapeInputRJ.value = game.rj_code || '';
      scrapeInputKeyword.value = game.clean_title || game.folder_name || '';
      scrapePreferredSource.value = 'auto';
      populateEditForm(game);

      try {
        const res = await fetch(`/api/games/${game.id}`);
        const data = await res.json();
        selectedGame.value = data.data;
        selectedGameVariants.value = data.variants || [];
        selectedGameMTool.value = data.mtool_status || null;
        selectedGameSave.value = data.save_status || null;
        populateEditForm(data.data);
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
          if (idx !== -1) games.value[idx].cover_url = result.cover_url;
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

    const clearAllEditFields = () => {
      if (!confirm('确定要一键清空当前所有封面图片、标题、社团、简介与标签等内容吗？（清空后点击保存生效）')) {
        return;
      }
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
        if (result.success) {
          selectedGame.value = result.data;
          populateEditForm(result.data);
          const idx = games.value.findIndex(g => g.id === selectedGame.value.id);
          if (idx !== -1) games.value[idx] = result.data;
          isEditMode.value = false;
          fetchStats();
          showToast('元数据修改已保存！', 'success');
        } else {
          showToast('保存失败', 'error');
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
        showToast(newRating ? `已评分: ${newRating} 星 ⭐` : '已清除个人评分', 'info', 1600);
      } catch (err) {
        console.error('Update rating error:', err);
        showToast('评分更新失败', 'error');
      }
    };

    const notesEditMode = ref(false);
    let markedConfigured = false;
    let headingCounterMap = {};

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
          return `<h${depth} id="${slug}" data-norm-key="${normKey}" data-toc-title="${rawText}" class="notes-heading notes-heading-${depth}">${parsedText}</h${depth}>\n`;
        };

        renderer.link = function({ href, title, tokens }) {
          const parsedText = this.parser.parseInline(tokens);
          const titleAttr = title ? ` title="${title}"` : '';
          if (href && href.startsWith('#')) {
            const anchorName = href.replace(/^#/, '');
            return `<a href="${href}" class="notes-anchor-link" data-anchor="${anchorName}"${titleAttr}>${parsedText}</a>`;
          }
          return `<a href="${href}" target="_blank" rel="noopener noreferrer" class="notes-external-link"${titleAttr}>${parsedText}</a>`;
        };

        marked.use({ renderer, gfm: true, breaks: true });
        markedConfigured = true;
      } catch (e) {
        console.error('Failed to configure marked:', e);
      }
    };

    const renderNotesMarkdown = (text) => {
      if (!text || !text.trim()) {
        return '<span class="text-slate-500 italic">暂无通关笔记或攻略，点击【编辑笔记】、【✨ 插入攻略模板】或【⛶ 全屏】添加...</span>';
      }
      setupMarkedRenderer();
      if (typeof marked !== 'undefined' && marked.parse) {
        try {
          headingCounterMap = {};
          // Enable interactive checkboxes in rendered HTML so user can click to check/uncheck
          const rawHtml = marked.parse(text);
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
      return text.replace(/\n/g, '<br/>');
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
      // Interactive checkbox toggle in preview mode
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

    // ScrollSpy & Proportional Scroll Sync for Fullscreen Walkthrough
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

      // Update ScrollSpy active heading
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
        spoiler: '\n<details>\n<summary>🔒 点击展开隐藏剧透 / 作弊密码</summary>\n\n- 全回想开启位置：标题画面右侧隐藏开关\n- 保险箱密码：`1024`\n\n</details>\n',
        template: `# 《${selectedGame.value.display_title || selectedGame.value.clean_title}》全流程全结局攻略\n\n## 一、 核心机制与通关提示\n- **全CG/回想解锁方式**：\n- **关键数值/状态说明**：\n\n## 二、 主线流程与关键分支表\n| 阶段 | 地点 / NPC | 关键行动与选项 | 结果 / 解锁内容 |\n| :--- | :--- | :--- | :--- |\n| 序章 | 初始房间 | 调查书桌获取道具 | 开启主线 |\n| 中盘 | 王都广场 | 夜晚前往酒馆触发支线 | 解锁支线事件 |\n\n## 三、 全结局达成条件 Checklist\n- [ ] **True End (真结局)**：\n- [ ] **Normal End (普通结局)**：\n- [ ] **Bad End / 特殊结局**：\n`
      };
      const textToInsert = snippets[type] || '';
      if (!textToInsert) return;

      const ta = document.getElementById('notes-editor-textarea');
      const currentVal = selectedGame.value.user_notes || '';
      if (ta && (notesFullscreenLayout.value === 'split' || notesFullscreenLayout.value === 'editor')) {
        const start = ta.selectionStart || currentVal.length;
        const end = ta.selectionEnd || currentVal.length;
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

    // Fixed openNotesFullscreen bug: ensures full detail (mtool, variants, save_status) is fetched if opened from grid/list
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

    const isBakingTranslation = ref(false);

    const bakeTranslationAction = async (game) => {
      if (!game) return;
      if (!confirm(`确定要将外挂翻译直接固化到游戏本体吗？\n\n【固化内容】\n1. 静态翻译数据注入 data/*.json (自动备份原版)\n2. 安装通用运行时动态翻译补丁\n3. 注入系统微软雅黑中文字体\n\n固化后，无论怎么启动都直接是中文，无需再启动 MTool！`)) {
        return;
      }
      isBakingTranslation.value = true;
      try {
        const res = await fetch(`/api/games/${game.id}/bake_translation`, { method: 'POST' });
        const result = await res.json();
        if (result.success) {
          showToast(result.message || '静态固化汉化成功！原生启动即为中文。', 'success');
          if (selectedGame.value && selectedGame.value.id === game.id) {
            openGameDetail(selectedGame.value);
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

    const launchGameAction = async (game, mode = null) => {
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
          fetchStats();
          showToast(data.message || '游戏正在启动...', 'success', 2000);
        } else {
          showToast(data.message || '启动失败', 'error');
        }
      } catch (err) {
        showToast('启动发生异常: ' + err, 'error');
      }
    };

    const launchMToolAction = async (game) => {
      try {
        const res = await fetch(`/api/games/${game.id}/launch_mtool`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          game.play_status = 'playing';
          if (selectedGame.value && selectedGame.value.id === game.id) {
            selectedGame.value.play_status = 'playing';
          }
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
      try {
        const res = await fetch(`/api/games/${game.id}/launch_le`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          game.play_status = 'playing';
          if (selectedGame.value && selectedGame.value.id === game.id) {
            selectedGame.value.play_status = 'playing';
          }
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

    const backupSaveAction = async (game) => {
      if (!game) return;
      isBackingUpSave.value = true;
      try {
        const res = await fetch(`/api/games/${game.id}/backup_save`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          if (data.save_status) {
            selectedGameSave.value = data.save_status;
          }
          showToast(data.message || '存档快照备份成功！', 'success', 2800);
        } else {
          showToast(data.message || '备份存档失败', 'warning');
        }
      } catch (err) {
        showToast('备份存档异常: ' + err, 'error');
      } finally {
        isBackingUpSave.value = false;
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
      const msg = deleteLocal
        ? `⚠️ 警告：确定要彻底删除本地游戏文件夹【${game.folder_name}】并将其移入回收站吗？\n（此操作将同时从游戏库中清除记录）`
        : `确定要将游戏【${game.display_title || game.folder_name}】从游戏库中移除吗？\n（本地文件将完好保留）`;
      if (!confirm(msg)) return;

      try {
        const res = await fetch(`/api/games/${game.id}/delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ delete_local: deleteLocal })
        });
        const result = await res.json();
        if (result.success) {
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
      if (!confirm('确定要一键从游戏库中清理所有本地文件已不存在的失效游戏吗？')) return;
      try {
        const res = await fetch('/api/games/cleanup_missing', { method: 'POST' });
        const result = await res.json();
        if (result.success) {
          showToast(result.message || '清理完成', 'success');
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
      const msg = deleteLocal
        ? `⚠️ 高危操作：确定要彻底删除选中的 ${count} 部本地游戏文件夹（移入回收站）并从库中移除吗？`
        : `确定要将选中的 ${count} 部游戏从库中移除吗？（不会删除本地文件）`;
      if (!confirm(msg)) return;

      try {
        const res = await fetch('/api/games/batch_delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ game_ids: selectedGameIds.value, delete_local: deleteLocal })
        });
        const result = await res.json();
        if (result.success) {
          showToast(result.message || '批量删除成功', 'success');
          const delIds = new Set(selectedGameIds.value);
          games.value = games.value.filter(g => !delIds.has(g.id));
          selectedGameIds.value = [];
          fetchStats();
        } else {
          showToast('批量删除失败', 'error');
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
            // Check if auto_scrape kicked off in backend
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

    const openDuplicateModal = async () => {
      try {
        const res = await fetch('/api/duplicates');
        const data = await res.json();
        duplicateGroups.value = data.data || {};
        showDuplicateModal.value = true;
        refreshIcons();
      } catch (err) {
        showToast('加载查重数据失败: ' + err, 'error');
      }
    };

    const openDuplicateModalForGame = () => {
      openDuplicateModal();
    };

    const archiveSingleVariant = async (variant) => {
      if (!confirm(`确定要将版本【${variant.folder_name}】安全归档移动到 _Archive_Duplicates 吗？`)) {
        return;
      }
      try {
        const res = await fetch('/api/duplicates/archive', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ game_id: variant.id })
        });
        const data = await res.json();
        showToast(data.message || '归档成功', 'success');
        fetchGames();
        fetchStats();
        if (showDuplicateModal.value) openDuplicateModal();
        if (selectedGame.value && selectedGame.value.id === variant.id) {
          selectedGame.value = null;
        } else if (selectedGame.value) {
          openGameDetail(selectedGame.value);
        }
      } catch (err) {
        showToast('归档失败: ' + err, 'error');
      }
    };

    const dismissDuplicateAction = async (variant, targetId = null) => {
      const name = variant.clean_title || variant.folder_name;
      if (!confirm(`确定要将【${name}】标记为非重复版本（移出当前重复分组）吗？\n标记后系统将永久记住此独立游戏，不再误报为重复。`)) {
        return;
      }
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
        if (showDuplicateModal.value) await openDuplicateModal();
        if (selectedGame.value) {
          await openGameDetail(selectedGame.value);
        }
      } catch (err) {
        showToast('取消重复失败: ' + err, 'error');
      }
    };

    const handleGlobalKeydown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        if (showNotesFullscreen.value) {
          e.preventDefault();
          saveGameNotes(false);
          return;
        }
      }

      if (e.key === 'Escape') {
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
      toasts,
      showToast,
      removeToast,
      isLoading,
      viewMode,
      setViewMode,
      coverFitMode,
      cycleCoverFitMode,
      searchKeyword,
      currentStatus,
      favoriteOnly,
      missingOnly,
      showToolsOnly,
      hasNotesOnly,
      unscrapedOnly,
      engineFilter,
      transFilter,
      sortBy,
      sortOrder,
      statusTabs,
      selectedGame,
      selectedGameVariants,
      selectedGameMTool,
      selectedGameSave,
      isBackingUpSave,
      openSaveFolderAction,
      backupSaveAction,
      showRescrapePanel,
      showDangerMenu,
      isMToolEngine,
      isBakingTranslation,
      bakeTranslationAction,
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
      showSettingsModal,
      showShortcutModal,
      isTestingProxy,
      configData,
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
