# -*- coding: utf-8 -*-
"""
RPG Maker MV/MZ Static and Runtime Translation Patcher for ACG Vault.
Bakes external translation dictionary directly into game data and runtime plugins,
and supports one-click restoration (unbake) from original backup.
"""

import os
import sys
import json
import shutil
import time
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, Callable

from db.database import get_game_by_id, manual_update_game_metadata
from core.scanner import is_valid_translation_json

BLACKLIST_KEYS = {
    'characterName', 'faceName', 'battlerName', 'bgm', 'bgs', 'me', 'se',
    'pan', 'pitch', 'volume', 'animationId', 'code', 'indent', 'iconIndex',
    'switchId', 'variableId', 'commonEventId', 'pictureName', 'tilesetNames',
    'meta', 'pluginName', 'name_in_editor', 'sound', 'syntheticName',
    'graphic', 'tilesetId', 'effectName', 'particleName', 'modelName',
    'encryptionKey', 'numberFontFilename', 'mainFontFilename'
}

CHINESE_FALLBACK_FONTS = "Microsoft YaHei, SimHei, PingFang SC, Source Han Sans CN, "

RUNTIME_PLUGIN_CODE = """//=============================================================================
// translation_patch.js
// Universal Runtime In-Memory Translation Patch for RPG Maker MZ/MV
// Hooks DataManager.onLoad, Bitmap.prototype.drawText, Window_Base.prototype.createTextState
//=============================================================================
/*:
 * @target MZ
 * @plugindesc [v2.2.0] Universal Runtime Translation Patch
 * @author ACG Vault
 * @help Translates all text dynamically on display time.
 */

(() => {
    'use strict';
    console.log('[NativeTranslator] Initializing universal translation plugin v2.2...');

    let transDict = {};

    function stripBom(str) {
        if (!str || typeof str !== 'string') return '';
        return str.charCodeAt(0) === 0xFEFF ? str.slice(1) : str;
    }

    function safeReplaceLiteral(source, target, replacement) {
        if (!source || !target) return source;
        return source.split(target).join(replacement);
    }

    function loadDict() {
        try {
            if (typeof require === 'function') {
                const fs = require('fs');
                const path = require('path');
                const baseDir = path.dirname(process.mainModule ? process.mainModule.filename : process.cwd());
                const candidates = [
                    path.join(process.cwd(), '翻译文件.json'),
                    path.join(baseDir, '翻译文件.json'),
                    path.join(process.cwd(), 'www', '翻译文件.json'),
                    path.join(baseDir, 'www', '翻译文件.json'),
                    path.join(process.cwd(), 'translation.json'),
                    path.join(baseDir, 'translation.json'),
                    path.join(process.cwd(), 'www', 'translation.json')
                ];
                for (const p of candidates) {
                    if (fs.existsSync(p)) {
                        const raw = fs.readFileSync(p, 'utf8');
                        transDict = JSON.parse(stripBom(raw));
                        console.log('[NativeTranslator] Loaded ' + Object.keys(transDict).length + ' dictionary entries from ' + p);
                        return;
                    }
                }
            }

            // XHR Fallback (with UTF-8 BOM stripping and multi-path fallback)
            const xhrUrls = ['翻译文件.json', 'translation.json'];
            for (const url of xhrUrls) {
                try {
                    const xhr = new XMLHttpRequest();
                    xhr.open('GET', url, false);
                    xhr.send();
                    if ((xhr.status === 200 || xhr.status === 0) && xhr.responseText) {
                        transDict = JSON.parse(stripBom(xhr.responseText));
                        console.log('[NativeTranslator] Loaded ' + Object.keys(transDict).length + ' dictionary entries via XHR (' + url + ').');
                        return;
                    }
                } catch (innerErr) {}
            }
        } catch (e) {
            console.error('[NativeTranslator] Error loading dictionary:', e);
        }
    }
    loadDict();

    function translateText(str) {
        if (!str || typeof str !== 'string') return str;
        if (transDict[str]) return transDict[str];

        const norm = str.replace(/\\r\\n/g, '\\n');
        if (transDict[norm]) return transDict[norm];

        const trimmed = str.trim();
        if (trimmed && transDict[trimmed]) {
            return safeReplaceLiteral(str, trimmed, transDict[trimmed]);
        }

        if (norm.indexOf('\\n') !== -1) {
            const lines = norm.split('\\n');
            let anyMatched = false;
            const newLines = lines.map(line => {
                const tLine = line.trim();
                if (transDict[line]) {
                    anyMatched = true;
                    return transDict[line];
                }
                if (tLine && transDict[tLine]) {
                    anyMatched = true;
                    return safeReplaceLiteral(line, tLine, transDict[tLine]);
                }
                return line;
            });
            if (anyMatched) {
                const delim = str.indexOf('\\r\\n') !== -1 ? '\\r\\n' : '\\n';
                return newLines.join(delim);
            }
        }
        return str;
    }

    if (typeof Bitmap !== 'undefined' && Bitmap.prototype) {
        const _Bitmap_drawText = Bitmap.prototype.drawText;
        Bitmap.prototype.drawText = function(text, x, y, maxWidth, lineHeight, align) {
            if (typeof text === 'string') {
                arguments[0] = translateText(text);
            }
            return _Bitmap_drawText.apply(this, arguments);
        };

        const _Bitmap_measureTextWidth = Bitmap.prototype.measureTextWidth;
        Bitmap.prototype.measureTextWidth = function(text) {
            if (typeof text === 'string') {
                arguments[0] = translateText(text);
            }
            return _Bitmap_measureTextWidth.apply(this, arguments);
        };
    }

    if (typeof Window_Base !== 'undefined' && Window_Base.prototype) {
        const _Window_Base_createTextState = Window_Base.prototype.createTextState;
        Window_Base.prototype.createTextState = function(text, x, y, width) {
            if (typeof text === 'string') {
                arguments[0] = translateText(text);
            }
            return _Window_Base_createTextState.apply(this, arguments);
        };

        const _Window_Base_drawText = Window_Base.prototype.drawText;
        Window_Base.prototype.drawText = function(text, x, y, maxWidth, align) {
            if (typeof text === 'string') {
                arguments[0] = translateText(text);
            }
            return _Window_Base_drawText.apply(this, arguments);
        };
    }

    if (typeof DataManager !== 'undefined') {
        const skipKeys = ['characterName', 'faceName', 'battlerName', 'bgm', 'bgs', 'me', 'se', 'iconIndex', 'meta', 'animationId', 'pictureName', 'effectName'];
        function deepTranslate(obj) {
            if (!obj) return;
            if (Array.isArray(obj)) {
                for (let i = 0; i < obj.length; i++) {
                    if (typeof obj[i] === 'string') {
                        obj[i] = translateText(obj[i]);
                    } else if (typeof obj[i] === 'object') {
                        deepTranslate(obj[i]);
                    }
                }
            } else if (typeof obj === 'object') {
                if (obj.code && obj.parameters) {
                    const code = obj.code;
                    const p = obj.parameters;
                    if (code === 101 && typeof p[4] === 'string' && p[4]) {
                        p[4] = translateText(p[4]);
                    } else if ((code === 401 || code === 405) && typeof p[0] === 'string') {
                        p[0] = translateText(p[0]);
                    } else if (code === 102 && Array.isArray(p[0])) {
                        for (let i = 0; i < p[0].length; i++) {
                            p[0][i] = translateText(p[0][i]);
                        }
                    } else if (code === 402 && typeof p[1] === 'string') {
                        p[1] = translateText(p[1]);
                    } else if ((code === 320 || code === 324 || code === 325) && typeof p[1] === 'string') {
                        p[1] = translateText(p[1]);
                    } else if (code === 357 && p.length > 3 && typeof p[3] === 'object' && p[3]) {
                        deepTranslate(p[3]);
                    }
                    return;
                }
                for (const key of Object.keys(obj)) {
                    if (skipKeys.indexOf(key) !== -1) continue;
                    if (typeof obj[key] === 'string') {
                        obj[key] = translateText(obj[key]);
                    } else if (typeof obj[key] === 'object') {
                        deepTranslate(obj[key]);
                    }
                }
            }
        }

        const _DataManager_onLoad = DataManager.onLoad;
        DataManager.onLoad = function(object) {
            deepTranslate(object);
            _DataManager_onLoad.call(this, object);
        };
    }

    if (typeof Scene_Boot !== 'undefined' && Scene_Boot.prototype) {
        const _Scene_Boot_start = Scene_Boot.prototype.start;
        Scene_Boot.prototype.start = function() {
            if (typeof $dataSystem !== 'undefined' && $dataSystem) {
                if ($dataSystem.advanced) {
                    $dataSystem.advanced.fallbackFonts = 'Microsoft YaHei, SimHei, PingFang SC, ' + ($dataSystem.advanced.fallbackFonts || 'Verdana, sans-serif');
                }
            }
            if (transDict && document.title && transDict[document.title]) {
                document.title = transDict[document.title];
            }
            _Scene_Boot_start.apply(this, arguments);
        };
    }

    console.log('[NativeTranslator] Universal translation plugin v2.2 active!');
})();
"""


class MZPatcher:
    @staticmethod
    def find_game_root(folder_path: str) -> Optional[str]:
        if not folder_path or not os.path.exists(folder_path):
            return None
        if os.path.isdir(os.path.join(folder_path, 'data')):
            return folder_path
        if os.path.isdir(os.path.join(folder_path, 'www', 'data')):
            return os.path.join(folder_path, 'www')
        return None

    @staticmethod
    def load_dict(dict_path: str) -> Dict[str, str]:
        with open(dict_path, 'r', encoding='utf-8-sig') as f:
            raw = json.load(f)
        cleaned = {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(k, str) and isinstance(v, str):
                    cleaned[k] = v
                    if '\r\n' in k:
                        cleaned[k.replace('\r\n', '\n')] = v.replace('\r\n', '\n')
                    elif '\n' in k:
                        cleaned[k.replace('\n', '\r\n')] = v.replace('\n', '\r\n')
        return cleaned

    @staticmethod
    def translate_string(text: str, trans_dict: Dict[str, str]) -> Tuple[str, bool]:
        if not text or not isinstance(text, str):
            return text, False
        if text in trans_dict:
            return trans_dict[text], True

        norm = text.replace('\r\n', '\n')
        if norm in trans_dict:
            res = trans_dict[norm]
            if '\r\n' in text:
                res = res.replace('\n', '\r\n')
            return res, True

        trimmed = text.strip()
        if trimmed and trimmed in trans_dict:
            return text.replace(trimmed, trans_dict[trimmed], 1), True

        if '\n' in norm:
            lines = norm.split('\n')
            any_matched = False
            new_lines = []
            for line in lines:
                if line in trans_dict:
                    new_lines.append(trans_dict[line])
                    any_matched = True
                elif line.strip() and line.strip() in trans_dict:
                    new_lines.append(line.replace(line.strip(), trans_dict[line.strip()], 1))
                    any_matched = True
                else:
                    new_lines.append(line)
            if any_matched:
                delim = '\r\n' if '\r\n' in text else '\n'
                return delim.join(new_lines), True

        return text, False

    def traverse_and_translate(self, obj, trans_dict: Dict[str, str], stats: Dict[str, int]):
        if isinstance(obj, dict):
            if 'code' in obj and 'parameters' in obj:
                code = obj['code']
                params = obj['parameters']
                if code == 101 and len(params) > 4 and isinstance(params[4], str) and params[4]:
                    new_t, matched = self.translate_string(params[4], trans_dict)
                    if matched:
                        params[4] = new_t
                        stats['count'] += 1
                elif code in (401, 405) and len(params) > 0 and isinstance(params[0], str):
                    new_t, matched = self.translate_string(params[0], trans_dict)
                    if matched:
                        params[0] = new_t
                        stats['count'] += 1
                elif code == 102 and len(params) > 0 and isinstance(params[0], list):
                    for idx, c in enumerate(params[0]):
                        if isinstance(c, str):
                            new_t, matched = self.translate_string(c, trans_dict)
                            if matched:
                                params[0][idx] = new_t
                                stats['count'] += 1
                elif code == 402 and len(params) > 1 and isinstance(params[1], str):
                    new_t, matched = self.translate_string(params[1], trans_dict)
                    if matched:
                        params[1] = new_t
                        stats['count'] += 1
                elif code in (320, 324, 325) and len(params) > 1 and isinstance(params[1], str):
                    new_t, matched = self.translate_string(params[1], trans_dict)
                    if matched:
                        params[1] = new_t
                        stats['count'] += 1
                elif code == 357 and len(params) > 3 and isinstance(params[3], dict):
                    self.traverse_and_translate(params[3], trans_dict, stats)
                return

            for k, v in list(obj.items()):
                if k in BLACKLIST_KEYS:
                    continue
                if isinstance(v, str):
                    new_t, matched = self.translate_string(v, trans_dict)
                    if matched:
                        obj[k] = new_t
                        stats['count'] += 1
                elif isinstance(v, (dict, list)):
                    self.traverse_and_translate(v, trans_dict, stats)

        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                if isinstance(item, str):
                    new_t, matched = self.translate_string(item, trans_dict)
                    if matched:
                        obj[idx] = new_t
                        stats['count'] += 1
                elif isinstance(item, (dict, list)):
                    self.traverse_and_translate(item, trans_dict, stats)

    def bake(self, game_folder: str, dict_path: str) -> Dict[str, Any]:
        game_root = self.find_game_root(game_folder)
        if not game_root:
            return {"success": False, "message": "未找到 RPG Maker MV/MZ 的 data 目录"}

        data_dir = os.path.join(game_root, 'data')
        backup_dir = os.path.join(game_root, 'data_original_backup')

        if not os.path.exists(backup_dir):
            shutil.copytree(data_dir, backup_dir)

        trans_dict = self.load_dict(dict_path)
        if not trans_dict:
            return {"success": False, "message": "翻译字典内容为空或格式无效"}

        stats = {'count': 0, 'files': 0}

        for fname in os.listdir(backup_dir):
            if fname.lower().endswith('.json') and not fname.startswith('.'):
                src_path = os.path.join(backup_dir, fname)
                dst_path = os.path.join(data_dir, fname)
                try:
                    with open(src_path, 'r', encoding='utf-8-sig') as f:
                        data = json.load(f)
                    file_stats = {'count': 0}
                    self.traverse_and_translate(data, trans_dict, file_stats)

                    if fname.lower() == 'system.json' and isinstance(data, dict):
                        if 'advanced' in data and isinstance(data['advanced'], dict):
                            orig = data['advanced'].get('fallbackFonts', '')
                            if 'Microsoft YaHei' not in orig:
                                data['advanced']['fallbackFonts'] = CHINESE_FALLBACK_FONTS + orig
                        elif 'fallbackFonts' in data:
                            orig = data.get('fallbackFonts', '')
                            if 'Microsoft YaHei' not in orig:
                                data['fallbackFonts'] = CHINESE_FALLBACK_FONTS + orig

                    with open(dst_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=None, separators=(',', ':'))

                    stats['count'] += file_stats['count']
                    stats['files'] += 1
                except Exception:
                    shutil.copy2(src_path, dst_path)

        copied_dicts = []
        for dest_base in {os.path.abspath(game_root), os.path.abspath(game_folder)}:
            target_dict_dest = os.path.join(dest_base, '翻译文件.json')
            if not os.path.exists(target_dict_dest):
                try:
                    shutil.copy2(dict_path, target_dict_dest)
                    copied_dicts.append(target_dict_dest)
                except Exception:
                    pass

        try:
            with open(os.path.join(backup_dir, '.acg_vault_baked.json'), 'w', encoding='utf-8') as mf:
                json.dump({"copied_dicts": copied_dicts, "source_dict": dict_path}, mf, ensure_ascii=False)
        except Exception:
            pass

        plugins_dir = os.path.join(game_root, 'js', 'plugins')
        os.makedirs(plugins_dir, exist_ok=True)
        patch_js = os.path.join(plugins_dir, 'translation_patch.js')
        with open(patch_js, 'w', encoding='utf-8') as f:
            f.write(RUNTIME_PLUGIN_CODE)

        plugins_file = os.path.join(game_root, 'js', 'plugins.js')
        if os.path.exists(plugins_file):
            plugins_bak = plugins_file + '.original_bak'
            if not os.path.exists(plugins_bak):
                shutil.copy2(plugins_file, plugins_bak)
            with open(plugins_file, 'r', encoding='utf-8-sig') as f:
                code = f.read()
            if '"name":"translation_patch"' not in code:
                idx = code.rfind('];')
                if idx != -1:
                    prefix_check = code[:idx].rstrip()
                    comma = '' if prefix_check.endswith('[') else ','
                    entry = f'{comma}\n{{"name":"translation_patch","status":true,"description":"Universal Runtime Translation Patch","parameters":{{}}}}\n];'
                    new_code = code[:idx] + entry
                    with open(plugins_file, 'w', encoding='utf-8') as f:
                        f.write(new_code)

        return {
            "success": True,
            "replaced_entries": stats['count'],
            "processed_files": stats['files'],
            "message": f"静态固化汉化成功！已将 {stats['count']} 处文本固化到游戏本体并安装 v2.2 动态补丁。"
        }

    def unbake(self, game_folder: str) -> Dict[str, Any]:
        game_root = self.find_game_root(game_folder)
        if not game_root:
            return {"success": False, "message": "未找到 RPG Maker MV/MZ 的游戏根目录"}

        data_dir = os.path.join(game_root, 'data')
        backup_dir = os.path.join(game_root, 'data_original_backup')
        if not os.path.exists(backup_dir):
            return {"success": False, "message": "未检测到原版数据备份目录 (data_original_backup)，无需还原"}

        try:
            marker_file = os.path.join(backup_dir, '.acg_vault_baked.json')
            copied_dicts = []
            if os.path.exists(marker_file):
                try:
                    with open(marker_file, 'r', encoding='utf-8') as mf:
                        copied_dicts = json.load(mf).get("copied_dicts", [])
                except Exception:
                    pass

            for fname in os.listdir(backup_dir):
                if fname.startswith('.'):
                    continue
                src = os.path.join(backup_dir, fname)
                dst = os.path.join(data_dir, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
            shutil.rmtree(backup_dir, ignore_errors=True)

            for cd in copied_dicts:
                if cd and os.path.exists(cd):
                    try:
                        os.remove(cd)
                    except Exception:
                        pass

            plugins_file = os.path.join(game_root, 'js', 'plugins.js')
            plugins_bak = plugins_file + '.original_bak'
            if os.path.exists(plugins_bak):
                shutil.copy2(plugins_bak, plugins_file)
                try:
                    os.remove(plugins_bak)
                except Exception:
                    pass

            patch_js = os.path.join(game_root, 'js', 'plugins', 'translation_patch.js')
            if os.path.exists(patch_js):
                try:
                    os.remove(patch_js)
                except Exception:
                    pass

            return {
                "success": True,
                "message": "已成功从备份还原游戏原版数据并移除注入补丁！"
            }
        except Exception as e:
            return {"success": False, "message": f"还原原版数据失败: {str(e)}"}


def find_translation_dict_in_folder(folder_path: str) -> Optional[str]:
    p = Path(folder_path)
    search_dirs = [p]
    if (p / "www").is_dir():
        search_dirs.append(p / "www")

    for d in search_dirs:
        for cand in ["翻译文件.json", "translation.json", "trs.json"]:
            if (d / cand).exists():
                return str(d / cand)

    if (p / "lastLoadedTrsFile").exists():
        try:
            with open(p / "lastLoadedTrsFile", "r", encoding="utf-8-sig") as f:
                ref = f.read().strip()
                if ref and (p / ref).exists() and is_valid_translation_json(str(p / ref)):
                    return str(p / ref)
        except Exception:
            pass

    for d in search_dirs:
        try:
            for f in os.listdir(d):
                full_p = d / f
                if full_p.is_file() and f.lower().endswith(".json") and is_valid_translation_json(str(full_p)):
                    return str(full_p)
        except Exception:
            pass
    return None


def bake_game_translation(game_id: int) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_path = game.get("folder_path")
    if not folder_path or not os.path.exists(folder_path):
        return {"success": False, "message": "游戏目录不存在"}

    trs_file = find_translation_dict_in_folder(folder_path)
    if not trs_file or not os.path.exists(trs_file):
        return {"success": False, "message": "未在游戏目录中检测到有效的外挂翻译 JSON 字典文件"}

    patcher = MZPatcher()
    res = patcher.bake(folder_path, trs_file)
    if res.get("success"):
        manual_update_game_metadata(game_id, {"has_translation": 1})
    return res


def unbake_game_translation(game_id: int) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_path = game.get("folder_path")
    if not folder_path or not os.path.exists(folder_path):
        return {"success": False, "message": "游戏目录不存在"}

    patcher = MZPatcher()
    res = patcher.unbake(folder_path)
    if res.get("success"):
        remaining_trs = find_translation_dict_in_folder(folder_path)
        has_bat = any((Path(folder_path) / b).exists() for b in ("与工具一同启动.bat", "StartWithTool.bat"))
        manual_update_game_metadata(game_id, {"has_translation": 1 if (remaining_trs or has_bat) else 0})
    return res
