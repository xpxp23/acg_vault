/* ==========================================================================
 * ACG Vault v3.3.0 — Save Snapshot Visual Diff & WebDAV Conflict Resolver Composable
 * Exposes window.AcgSaveDiffModule.create(ctx)
 * ========================================================================== */
(function () {
  'use strict';
  if (window.AcgSaveDiffModule) return;

  function create(ctx) {
    const { ref, reactive, computed, nextTick } = Vue;
    const { selectedGame, selectedGameSave, showToast, askConfirm, refreshIcons } = ctx;

    const showSaveDiffPanel = ref(false);
    const isLoadingSaveDiff = ref(false);
    const isResolvingConflict = ref(false);
    const saveConflictReport = ref(null);
    const saveDiffResult = ref(null);
    const saveDiffLeftSource = ref('local');
    const saveDiffRightSource = ref('latest_backup');
    const saveDiffSlotChoices = reactive({});

    const saveDiffSourceOptions = computed(function () {
      const opts = [
        { id: 'local', label: '📍 当前本地实时存档 (Save 目录)' },
        { id: 'latest_backup', label: '⏱️ 最近一份快照备份 (Latest Snapshot)' }
      ];
      const seen = { local: true, latest_backup: true };
      const localBaks = (saveConflictReport.value && saveConflictReport.value.local_backups) ||
                        (selectedGameSave.value && selectedGameSave.value.backups) || [];
      localBaks.forEach(function (b) {
        const sid = 'backup:' + b.filename;
        if (!seen[sid]) {
          seen[sid] = true;
          opts.push({
            id: sid,
            label: '📦 本地快照: ' + b.filename + ' (' + (b.created_at || b.size_kb + 'KB') + ')'
          });
        }
      });
      const remoteBaks = (saveConflictReport.value && saveConflictReport.value.remote_backups) || [];
      remoteBaks.forEach(function (rb) {
        const sid = 'webdav:' + rb.filename;
        if (!seen[sid]) {
          seen[sid] = true;
          opts.push({
            id: sid,
            label: '☁️ WebDAV 云端: ' + rb.filename + (rb.is_downloaded ? ' [已缓存]' : ' [仅在云端]')
          });
        }
      });
      return opts;
    });

    function initSlotChoicesFromDiff(diffObj) {
      Object.keys(saveDiffSlotChoices).forEach(function (k) { delete saveDiffSlotChoices[k]; });
      if (!diffObj || !Array.isArray(diffObj.slots)) return;
      diffObj.slots.forEach(function (s) {
        if (s.status === 'only_right') {
          saveDiffSlotChoices[s.rel_path] = 'right';
        } else if (s.status === 'only_left') {
          saveDiffSlotChoices[s.rel_path] = 'left';
        } else if (s.newer_side === 'right') {
          saveDiffSlotChoices[s.rel_path] = 'right';
        } else {
          saveDiffSlotChoices[s.rel_path] = 'left';
        }
      });
    }

    async function openSaveDiffPanel(game, preferredRightSource) {
      const g = game || selectedGame.value;
      if (!g) return;
      showSaveDiffPanel.value = true;
      isLoadingSaveDiff.value = true;
      saveDiffLeftSource.value = 'local';
      saveDiffRightSource.value = preferredRightSource || 'latest_backup';
      try {
        const res = await fetch('/api/games/' + g.id + '/saves/conflicts');
        const data = await res.json();
        if (data && data.success) {
          saveConflictReport.value = data;
          if (preferredRightSource) {
            saveDiffRightSource.value = preferredRightSource;
            await runSaveSourceComparison();
          } else if (data.diff && data.diff.success) {
            saveDiffResult.value = data.diff;
            if (data.diff.right_source && data.diff.right_source.id) {
              saveDiffRightSource.value = data.diff.right_source.id;
            }
            initSlotChoicesFromDiff(data.diff);
          } else {
            await runSaveSourceComparison();
          }
        } else {
          showToast((data && data.message) || '读取存档对比信息失败', 'warning');
        }
      } catch (err) {
        showToast('存档对比检查异常: ' + err, 'error');
      } finally {
        isLoadingSaveDiff.value = false;
        nextTick(function () { refreshIcons(); });
      }
    }

    async function runSaveSourceComparison() {
      const g = selectedGame.value;
      if (!g) return;
      isLoadingSaveDiff.value = true;
      try {
        const res = await fetch('/api/games/' + g.id + '/saves/diff', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            left_source: saveDiffLeftSource.value || 'local',
            right_source: saveDiffRightSource.value || 'latest_backup'
          })
        });
        const data = await res.json();
        if (data && data.success) {
          saveDiffResult.value = data;
          initSlotChoicesFromDiff(data);
        } else {
          showToast((data && data.message) || '存档对比失败', 'warning');
        }
      } catch (err) {
        showToast('对比请求异常: ' + err, 'error');
      } finally {
        isLoadingSaveDiff.value = false;
        nextTick(function () { refreshIcons(); });
      }
    }

    async function resolveSaveConflictAction(strategy) {
      const g = selectedGame.value;
      if (!g) return;

      const labelMap = {
        keep_local: '以当前本地实时存档为准（备份本地并推送云端）',
        use_snapshot: '使用右侧快照覆盖恢复（覆盖前自动保护备份当前本地存档）',
        keep_both: '双分支同时保留（拉取云端快照并同时创建本地新快照）',
        slot_merge: '按各槽位勾选方案智能合并写入（合并前自动保护备份）'
      };

      const ok = await askConfirm({
        title: '执行存档冲突仲裁与合并',
        message: '即将执行策略：【' + (labelMap[strategy] || strategy) + '】。\n系统将在操作前自动为当前实时存档创建防坏档保护快照，确定继续吗？',
        confirmText: '确认执行仲裁',
        cancelText: '取消',
        variant: strategy === 'use_snapshot' ? 'warning' : 'primary'
      });
      if (!ok) return;

      isResolvingConflict.value = true;
      try {
        const res = await fetch('/api/games/' + g.id + '/saves/resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            strategy: strategy,
            snapshot_filename: saveDiffRightSource.value || '',
            slot_choices: Object.assign({}, saveDiffSlotChoices)
          })
        });
        const data = await res.json();
        if (data && data.success) {
          if (data.save_status) {
            selectedGameSave.value = data.save_status;
          }
          showToast(data.message || '存档仲裁与合并已完成！', 'success', 3800);
          await openSaveDiffPanel(g, saveDiffRightSource.value);
        } else {
          showToast((data && data.message) || '仲裁执行失败', 'error');
        }
      } catch (err) {
        showToast('仲裁执行异常: ' + err, 'error');
      } finally {
        isResolvingConflict.value = false;
        nextTick(function () { refreshIcons(); });
      }
    }

    return {
      showSaveDiffPanel: showSaveDiffPanel,
      isLoadingSaveDiff: isLoadingSaveDiff,
      isResolvingConflict: isResolvingConflict,
      saveConflictReport: saveConflictReport,
      saveDiffResult: saveDiffResult,
      saveDiffLeftSource: saveDiffLeftSource,
      saveDiffRightSource: saveDiffRightSource,
      saveDiffSlotChoices: saveDiffSlotChoices,
      saveDiffSourceOptions: saveDiffSourceOptions,
      openSaveDiffPanel: openSaveDiffPanel,
      runSaveSourceComparison: runSaveSourceComparison,
      resolveSaveConflictAction: resolveSaveConflictAction
    };
  }

  window.AcgSaveDiffModule = { create: create };
})();
