/* ==========================================================================
 * ACG Vault v3.3.0 — RPG Maker MV/MZ & Unity Framerate Unlock & Slimming Toolbox Composable
 * Exposes window.AcgGameOptimizerModule.create(ctx)
 * ========================================================================== */
(function () {
  'use strict';
  if (window.AcgGameOptimizerModule) return;

  function create(ctx) {
    const { ref, reactive, nextTick } = Vue;
    const { selectedGame, showToast, askConfirm, updateGameInList, refreshIcons } = ctx;

    const showOptimizerPanel = ref(false);
    const isLoadingOptimizer = ref(false);
    const isRunningOptimizer = ref(false);
    const optimizerStatus = ref(null);
    const optimizerForm = reactive({
      target_fps: 120,
      fast_skip_mult: 4,
      keep_bg_audio: true,
      gpu_raster: true,
      clean_junk: true,
      compress_images: true,
      image_mode: 'lossless_png',
      create_rollback_backup: true
    });

    async function fetchOptimizerStatus(gameId) {
      const gid = gameId || (selectedGame.value && selectedGame.value.id);
      if (!gid) return;
      isLoadingOptimizer.value = true;
      try {
        const res = await fetch('/api/games/' + gid + '/optimizer/status');
        const data = await res.json();
        if (data && data.success) {
          optimizerStatus.value = data;
          if (data.current_target_fps && data.current_target_fps >= 60) {
            optimizerForm.target_fps = data.current_target_fps;
          }
        } else {
          optimizerStatus.value = null;
          showToast((data && data.message) || '分析游戏目录失败', 'warning');
        }
      } catch (err) {
        optimizerStatus.value = null;
        showToast('读取游戏优化分析异常: ' + err, 'error');
      } finally {
        isLoadingOptimizer.value = false;
        nextTick(function () { refreshIcons(); });
      }
    }

    function toggleOptimizerPanel(game) {
      const g = game || selectedGame.value;
      if (!g) return;
      showOptimizerPanel.value = !showOptimizerPanel.value;
      if (showOptimizerPanel.value) {
        fetchOptimizerStatus(g.id);
      }
      nextTick(function () { refreshIcons(); });
    }

    async function applyFpsPatchAction() {
      const g = selectedGame.value;
      if (!g) return;
      isRunningOptimizer.value = true;
      try {
        const res = await fetch('/api/games/' + g.id + '/optimizer/fps_patch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_fps: Number(optimizerForm.target_fps || 120),
            fast_skip_mult: Number(optimizerForm.fast_skip_mult || 4),
            keep_bg_audio: Boolean(optimizerForm.keep_bg_audio),
            gpu_raster: Boolean(optimizerForm.gpu_raster)
          })
        });
        const data = await res.json();
        if (data && data.success) {
          if (data.status) optimizerStatus.value = data.status;
          showToast(data.message || '高刷解锁与加速补丁已成功注入！', 'success', 3800);
        } else {
          showToast((data && data.message) || '注入帧率补丁失败', 'error');
        }
      } catch (err) {
        showToast('注入帧率补丁异常: ' + err, 'error');
      } finally {
        isRunningOptimizer.value = false;
        nextTick(function () { refreshIcons(); });
      }
    }

    async function removeFpsPatchAction() {
      const g = selectedGame.value;
      if (!g) return;
      isRunningOptimizer.value = true;
      try {
        const res = await fetch('/api/games/' + g.id + '/optimizer/fps_unpatch', {
          method: 'POST'
        });
        const data = await res.json();
        if (data && data.success) {
          if (data.status) optimizerStatus.value = data.status;
          showToast(data.message || '已移除高刷补丁并恢复原始配置', 'info', 2600);
        } else {
          showToast((data && data.message) || '还原帧率补丁失败', 'error');
        }
      } catch (err) {
        showToast('还原帧率补丁异常: ' + err, 'error');
      } finally {
        isRunningOptimizer.value = false;
        nextTick(function () { refreshIcons(); });
      }
    }

    async function runGameSlimAction() {
      const g = selectedGame.value;
      if (!g) return;
      const ok = await askConfirm({
        title: '执行游戏体积无损瘦身与冗余清理',
        message: '即将对《' + (g.display_title || g.folder_name) + '》执行体积瘦身：\n' +
          (optimizerForm.clean_junk ? '• 清理调试符号 (.pdb)、崩溃转储、DoNotShip 目录与多余语言包\n' : '') +
          (optimizerForm.compress_images ? '• 对大型未加密 PNG 立绘/贴图进行无损重压缩优化\n' : '') +
          (optimizerForm.create_rollback_backup ? '• 自动生成 _acg_optimizer_backup.zip 原始备份，随时支持一键回滚还原！' : '• 注意：当前未勾选保留回滚备份包。'),
        confirmText: '立即开始瘦身',
        cancelText: '取消',
        variant: 'primary'
      });
      if (!ok) return;

      isRunningOptimizer.value = true;
      try {
        const res = await fetch('/api/games/' + g.id + '/optimizer/slim', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            clean_junk: Boolean(optimizerForm.clean_junk),
            compress_images: Boolean(optimizerForm.compress_images),
            image_mode: optimizerForm.image_mode || 'lossless_png',
            create_rollback_backup: Boolean(optimizerForm.create_rollback_backup)
          })
        });
        const data = await res.json();
        if (data && data.success) {
          if (data.status) {
            optimizerStatus.value = data.status;
            if (data.status.footprint && selectedGame.value) {
              selectedGame.value.folder_size_bytes = data.status.footprint.total_bytes;
              selectedGame.value.folder_size_str = data.status.footprint.total_str;
              updateGameInList(selectedGame.value);
            }
          }
          showToast(data.message || '游戏瘦身优化完成！', 'success', 4200);
        } else {
          showToast((data && data.message) || '瘦身执行失败', 'error');
        }
      } catch (err) {
        showToast('瘦身执行异常: ' + err, 'error');
      } finally {
        isRunningOptimizer.value = false;
        nextTick(function () { refreshIcons(); });
      }
    }

    async function rollbackGameSlimAction() {
      const g = selectedGame.value;
      if (!g) return;
      const ok = await askConfirm({
        title: '从瘦身备份包无损回滚原始文件',
        message: '确定要从 _acg_optimizer_backup.zip 恢复全部原始文件并删除备份包吗？',
        confirmText: '确认无损回滚',
        cancelText: '取消',
        variant: 'warning'
      });
      if (!ok) return;

      isRunningOptimizer.value = true;
      try {
        const res = await fetch('/api/games/' + g.id + '/optimizer/rollback', {
          method: 'POST'
        });
        const data = await res.json();
        if (data && data.success) {
          if (data.status) {
            optimizerStatus.value = data.status;
            if (data.status.footprint && selectedGame.value) {
              selectedGame.value.folder_size_bytes = data.status.footprint.total_bytes;
              selectedGame.value.folder_size_str = data.status.footprint.total_str;
              updateGameInList(selectedGame.value);
            }
          }
          showToast(data.message || '已成功回滚全部原始文件！', 'success', 3200);
        } else {
          showToast((data && data.message) || '回滚失败', 'error');
        }
      } catch (err) {
        showToast('回滚异常: ' + err, 'error');
      } finally {
        isRunningOptimizer.value = false;
        nextTick(function () { refreshIcons(); });
      }
    }

    return {
      showOptimizerPanel: showOptimizerPanel,
      isLoadingOptimizer: isLoadingOptimizer,
      isRunningOptimizer: isRunningOptimizer,
      optimizerStatus: optimizerStatus,
      optimizerForm: optimizerForm,
      fetchOptimizerStatus: fetchOptimizerStatus,
      toggleOptimizerPanel: toggleOptimizerPanel,
      applyFpsPatchAction: applyFpsPatchAction,
      removeFpsPatchAction: removeFpsPatchAction,
      runGameSlimAction: runGameSlimAction,
      rollbackGameSlimAction: rollbackGameSlimAction
    };
  }

  window.AcgGameOptimizerModule = { create: create };
})();
