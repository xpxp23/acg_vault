# -*- coding: utf-8 -*-
"""
Save Snapshot Visual Diff & WebDAV Cloud Sync Conflict Resolver for ACG Vault v3.3.0.
"""

import io
import os
import re
import json
import time
import shutil
import hashlib
import zipfile
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from config import load_config
from db.database import get_game_by_id
from core.launcher import (
    find_game_save_dir,
    get_game_save_status,
    backup_game_saves,
    restore_game_saves,
    upload_backup_to_webdav,
    _get_webdav_client_and_url,
    is_subpath,
    SAVE_FILE_EXTENSIONS,
    SAVE_BACKUP_EXCLUDED_DIRS,
    MAX_NON_SAVE_BACKUP_FILE_BYTES,
)
from core.save_editor import (
    decompress_from_base64,
    _decode_rmmzsave,
    _load_rpgmaker_schema,
    _extract_and_set_gold,
    _extract_actors_info,
    _extract_variables_array,
    _extract_switches_array,
    _KEY_VAR_PAT,
    _CG_SW_PAT,
)


def _format_slot_label(rel_name: str) -> str:
    stem = Path(rel_name).stem
    low = stem.lower()
    if low in ("global", "common"):
        return "全局/公共回想数据 (Global)"
    if low == "config":
        return "系统配置 (Config)"
    if "auto" in low:
        return f"自动存档 ({stem})"
    m = re.search(r"(\d+)", stem)
    if m:
        return f"存档槽 #{int(m.group(1)):02d} ({Path(rel_name).name})"
    return rel_name


def _parse_rpg_bytes_telemetry(
    raw_bytes: bytes,
    ext: str,
    schema: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    try:
        if ext == ".rpgsave":
            txt = raw_bytes.decode("utf-8", errors="ignore").strip()
            if txt.startswith("{") and txt.endswith("}"):
                obj = json.loads(txt)
            else:
                dec = decompress_from_base64(txt)
                if not dec:
                    return None
                obj = json.loads(dec)
        elif ext == ".rmmzsave":
            dec, _ = _decode_rmmzsave(raw_bytes)
            obj = json.loads(dec)
        else:
            return None

        if not isinstance(obj, dict):
            return None

        sys_vars = schema.get("variables") or []
        sys_switches = schema.get("switches") or []
        sys_actors = schema.get("actors") or []

        gold = _extract_and_set_gold(obj)
        actors = _extract_actors_info(obj, sys_actors)
        lead_actor = actors[0] if actors else None

        raw_vars = _extract_variables_array(obj)
        raw_switches = _extract_switches_array(obj)

        vars_map: Dict[int, Dict[str, Any]] = {}
        max_v = min(2000, max(len(sys_vars), len(raw_vars)))
        for vid in range(1, max_v):
            vname = str(sys_vars[vid] if vid < len(sys_vars) and sys_vars[vid] else "").strip()
            vval = raw_vars[vid] if vid < len(raw_vars) else 0
            if vval is None or isinstance(vval, (dict, list)):
                continue
            if not vname and vval == 0:
                continue
            vars_map[vid] = {
                "id": vid,
                "name": vname or f"变量 #{vid:04d}",
                "value": vval,
                "is_key": bool(vname and _KEY_VAR_PAT.search(vname))
            }

        switches_map: Dict[int, Dict[str, Any]] = {}
        cg_on_count = 0
        total_on_count = 0
        max_s = min(3000, max(len(sys_switches), len(raw_switches)))
        for sid in range(1, max_s):
            sname = str(sys_switches[sid] if sid < len(sys_switches) and sys_switches[sid] else "").strip()
            sval = bool(raw_switches[sid]) if sid < len(raw_switches) and raw_switches[sid] is not None else False
            if sval:
                total_on_count += 1
            is_cg = bool(sname and _CG_SW_PAT.search(sname))
            if is_cg and sval:
                cg_on_count += 1
            if sname or sval:
                switches_map[sid] = {
                    "id": sid,
                    "name": sname or f"开关 #{sid:04d}",
                    "value": sval,
                    "is_cg": is_cg
                }

        sys_block = obj.get("system")
        frames_on_save = 0
        if isinstance(sys_block, dict):
            frames_on_save = int(sys_block.get("_framesOnSave") or 0)

        return {
            "supported": True,
            "gold": gold,
            "lead_actor": lead_actor,
            "actors_count": len(actors),
            "cg_switches_on": cg_on_count,
            "total_switches_on": total_on_count,
            "frames_on_save": frames_on_save,
            "playtime_sec": int(frames_on_save / 60) if frames_on_save > 0 else 0,
            "vars_map": vars_map,
            "switches_map": switches_map,
        }
    except Exception:
        return None


def _load_save_source_slots(
    game_id: int,
    source_spec: str,
    schema: Dict[str, Any]
) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"ok": False, "message": "游戏不存在", "slots": {}}

    cfg = load_config()
    backup_root = Path(cfg.get("save_backup_directory", r"E:\ACG\_Save_Backups"))
    folder_path = game.get("folder_path") or ""

    spec = (source_spec or "local").strip()
    if spec == "latest_backup":
        prefix = f"game_{game_id}_"
        zips = sorted(backup_root.glob(f"{prefix}*.zip"), key=lambda x: x.stat().st_mtime, reverse=True) if backup_root.exists() else []
        if not zips:
            return {
                "ok": True,
                "source_id": "latest_backup",
                "label": "暂无历史备份快照",
                "updated_at": "",
                "mtime": 0.0,
                "slot_count": 0,
                "total_size_kb": 0.0,
                "slots": {}
            }
        spec = f"backup:{zips[0].name}"

    if spec == "local":
        save_dir_str = find_game_save_dir(folder_path, game=game)
        if not save_dir_str or not os.path.exists(save_dir_str):
            return {
                "ok": True,
                "source_id": "local",
                "label": "当前本地实时存档 (Save)",
                "updated_at": "",
                "mtime": 0.0,
                "slot_count": 0,
                "total_size_kb": 0.0,
                "slots": {}
            }
        save_dir = Path(save_dir_str)
        is_root_save = bool(folder_path and os.path.normcase(os.path.normpath(str(save_dir))) == os.path.normcase(os.path.normpath(folder_path)))
        skip_unity_logs = {"player.log", "player-prev.log", "output_log.txt"}
        slots: Dict[str, Dict[str, Any]] = {}
        latest_mtime = 0.0
        total_bytes = 0

        for root, dirs, files in os.walk(save_dir):
            if is_root_save:
                dirs.clear()
            else:
                dirs[:] = [d for d in dirs if d.lower() not in SAVE_BACKUP_EXCLUDED_DIRS]
            for fn in files:
                low = fn.lower()
                if low in skip_unity_logs or low.endswith((".log", ".tmp", ".bak")):
                    continue
                if is_root_save and not (low.startswith("save") and low.endswith(SAVE_FILE_EXTENSIONS)):
                    continue
                fp = Path(root) / fn
                try:
                    st = fp.stat()
                    if st.st_size > MAX_NON_SAVE_BACKUP_FILE_BYTES and not low.endswith(SAVE_FILE_EXTENSIONS):
                        continue
                    raw_bytes = fp.read_bytes()
                except Exception:
                    continue

                rel_name = str(fp.relative_to(save_dir)).replace("\\", "/")
                sha = hashlib.sha256(raw_bytes).hexdigest()[:16]
                ext = fp.suffix.lower()
                stem_low = fp.stem.lower()
                telemetry = None
                if ext in (".rpgsave", ".rmmzsave") and stem_low not in ("config",):
                    telemetry = _parse_rpg_bytes_telemetry(raw_bytes, ext, schema)

                if st.st_mtime > latest_mtime:
                    latest_mtime = st.st_mtime
                total_bytes += st.st_size

                slots[rel_name] = {
                    "rel_path": rel_name,
                    "label": _format_slot_label(rel_name),
                    "size_bytes": st.st_size,
                    "size_kb": round(st.st_size / 1024.0, 1),
                    "mtime": st.st_mtime,
                    "updated_at": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "sha256": sha,
                    "telemetry": telemetry,
                }

        return {
            "ok": True,
            "source_id": "local",
            "label": "当前本地实时存档 (Local Live)",
            "updated_at": datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M:%S") if latest_mtime > 0 else "无记录",
            "mtime": latest_mtime,
            "slot_count": len(slots),
            "total_size_kb": round(total_bytes / 1024.0, 1),
            "slots": slots,
        }

    zip_bytes: Optional[bytes] = None
    zip_mtime = 0.0
    zip_label = spec

    if spec.startswith("backup:"):
        fname = Path(spec[len("backup:"):]).name
        zp = backup_root / fname
        if not zp.is_file():
            return {"ok": False, "message": f"未找到备份快照文件: {fname}", "slots": {}}
        zip_bytes = zp.read_bytes()
        zip_mtime = zp.stat().st_mtime
        zip_label = f"快照: {fname}"
    elif spec.startswith("webdav:"):
        fname = Path(spec[len("webdav:"):]).name
        local_cache = backup_root / fname
        if local_cache.is_file():
            zip_bytes = local_cache.read_bytes()
            zip_mtime = local_cache.stat().st_mtime
        else:
            client, base_url = _get_webdav_client_and_url(cfg)
            try:
                with client:
                    dl_url = f"{base_url}/{urllib.parse.quote(fname)}"
                    resp = client.get(dl_url)
                    if resp.status_code == 200 and resp.content.startswith(b"PK\x03\x04"):
                        zip_bytes = resp.content
                        zip_mtime = time.time()
            except Exception as e:
                return {"ok": False, "message": f"拉取云端快照失败: {str(e)[:60]}", "slots": {}}
        if not zip_bytes:
            return {"ok": False, "message": f"无法读取云端快照: {fname}", "slots": {}}
        zip_label = f"云端快照: {fname}"
    else:
        return {"ok": False, "message": f"不支持的存档对比源: {spec}", "slots": {}}

    slots = {}
    total_bytes = 0
    latest_entry_ts = 0.0
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                rel_name = info.filename.replace("\\", "/")
                raw_bytes = zf.read(info.filename)
                sha = hashlib.sha256(raw_bytes).hexdigest()[:16]
                try:
                    dt = datetime(*info.date_time)
                    entry_ts = dt.timestamp()
                    entry_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    entry_ts = zip_mtime
                    entry_str = datetime.fromtimestamp(zip_mtime).strftime("%Y-%m-%d %H:%M:%S")

                if entry_ts > latest_entry_ts:
                    latest_entry_ts = entry_ts
                total_bytes += info.file_size

                ext = Path(rel_name).suffix.lower()
                stem_low = Path(rel_name).stem.lower()
                telemetry = None
                if ext in (".rpgsave", ".rmmzsave") and stem_low not in ("config",):
                    telemetry = _parse_rpg_bytes_telemetry(raw_bytes, ext, schema)

                slots[rel_name] = {
                    "rel_path": rel_name,
                    "label": _format_slot_label(rel_name),
                    "size_bytes": info.file_size,
                    "size_kb": round(info.file_size / 1024.0, 1),
                    "mtime": entry_ts,
                    "updated_at": entry_str,
                    "sha256": sha,
                    "telemetry": telemetry,
                }
    except Exception as e:
        return {"ok": False, "message": f"解析快照压缩包失败: {str(e)}", "slots": {}}

    eff_mtime = latest_entry_ts or zip_mtime
    return {
        "ok": True,
        "source_id": spec,
        "label": zip_label,
        "updated_at": datetime.fromtimestamp(eff_mtime).strftime("%Y-%m-%d %H:%M:%S") if eff_mtime > 0 else "未知",
        "mtime": eff_mtime,
        "slot_count": len(slots),
        "total_size_kb": round(total_bytes / 1024.0, 1),
        "slots": slots,
    }


def compare_save_sources(
    game_id: int,
    left_source: str = "local",
    right_source: str = "latest_backup"
) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_path = game.get("folder_path") or ""
    schema = _load_rpgmaker_schema(folder_path) if folder_path else {"variables": [], "switches": [], "actors": []}

    left_data = _load_save_source_slots(game_id, left_source, schema)
    if not left_data.get("ok"):
        return {"success": False, "message": left_data.get("message", "读取左侧存档源失败")}

    right_data = _load_save_source_slots(game_id, right_source, schema)
    if not right_data.get("ok"):
        return {"success": False, "message": right_data.get("message", "读取右侧存档源失败")}

    left_slots = left_data["slots"]
    right_slots = right_data["slots"]
    all_keys = sorted(set(left_slots.keys()) | set(right_slots.keys()))

    slot_diffs: List[Dict[str, Any]] = []
    modified_count = 0
    added_count = 0
    removed_count = 0
    identical_count = 0

    for key in all_keys:
        ls = left_slots.get(key)
        rs = right_slots.get(key)

        if ls and not rs:
            status = "only_left"
            removed_count += 1
        elif rs and not ls:
            status = "only_right"
            added_count += 1
        elif ls["sha256"] == rs["sha256"]:
            status = "identical"
            identical_count += 1
        else:
            status = "modified"
            modified_count += 1

        lt = ls.get("telemetry") if ls else None
        rt = rs.get("telemetry") if rs else None

        var_changes: List[Dict[str, Any]] = []
        sw_changes: List[Dict[str, Any]] = []
        gold_diff = None
        level_diff = None
        cg_diff = None

        if lt and rt:
            if lt.get("gold") != rt.get("gold"):
                gold_diff = {
                    "left": lt.get("gold", 0),
                    "right": rt.get("gold", 0),
                    "delta": int(lt.get("gold", 0)) - int(rt.get("gold", 0))
                }
            la = lt.get("lead_actor")
            ra = rt.get("lead_actor")
            if la and ra and (la.get("level") != ra.get("level") or la.get("hp") != ra.get("hp")):
                level_diff = {
                    "name": la.get("name") or ra.get("name") or "主角",
                    "left_lv": la.get("level", 1),
                    "right_lv": ra.get("level", 1),
                    "delta_lv": int(la.get("level", 1)) - int(ra.get("level", 1)),
                }
            if lt.get("cg_switches_on") != rt.get("cg_switches_on"):
                cg_diff = {
                    "left": lt.get("cg_switches_on", 0),
                    "right": rt.get("cg_switches_on", 0),
                    "delta": int(lt.get("cg_switches_on", 0)) - int(rt.get("cg_switches_on", 0)),
                }

            lvars = lt.get("vars_map") or {}
            rvars = rt.get("vars_map") or {}
            for vid in sorted(set(lvars.keys()) | set(rvars.keys())):
                lv_item = lvars.get(vid)
                rv_item = rvars.get(vid)
                lval = lv_item["value"] if lv_item else 0
                rval = rv_item["value"] if rv_item else 0
                if lval != rval:
                    meta_item = lv_item or rv_item
                    delta_num = None
                    if isinstance(lval, (int, float)) and isinstance(rval, (int, float)):
                        delta_num = round(lval - rval, 2)
                    var_changes.append({
                        "id": vid,
                        "name": meta_item["name"],
                        "is_key": meta_item["is_key"],
                        "left_val": lval,
                        "right_val": rval,
                        "delta": delta_num,
                    })
            var_changes.sort(key=lambda x: (0 if x["is_key"] else 1, x["id"]))

            lsw = lt.get("switches_map") or {}
            rsw = rt.get("switches_map") or {}
            for sid in sorted(set(lsw.keys()) | set(rsw.keys())):
                ls_item = lsw.get(sid)
                rs_item = rsw.get(sid)
                lval = bool(ls_item["value"]) if ls_item else False
                rval = bool(rs_item["value"]) if rs_item else False
                if lval != rval:
                    meta_sw = ls_item or rs_item
                    sw_changes.append({
                        "id": sid,
                        "name": meta_sw["name"],
                        "is_cg": meta_sw["is_cg"],
                        "left_val": lval,
                        "right_val": rval,
                    })
            sw_changes.sort(key=lambda x: (0 if x["is_cg"] else 1, x["id"]))

        slot_diffs.append({
            "rel_path": key,
            "label": (ls or rs)["label"],
            "status": status,
            "newer_side": (
                "left" if (ls and rs and ls["mtime"] > rs["mtime"] + 2)
                else ("right" if (ls and rs and rs["mtime"] > ls["mtime"] + 2) else "same")
            ),
            "left": {
                "exists": ls is not None,
                "size_kb": ls["size_kb"] if ls else 0,
                "updated_at": ls["updated_at"] if ls else "—",
                "sha256": ls["sha256"] if ls else "",
                "gold": lt["gold"] if lt else None,
                "lead_actor": lt["lead_actor"] if lt else None,
                "cg_switches_on": lt["cg_switches_on"] if lt else None,
                "playtime_sec": lt["playtime_sec"] if lt else 0,
            } if ls else None,
            "right": {
                "exists": rs is not None,
                "size_kb": rs["size_kb"] if rs else 0,
                "updated_at": rs["updated_at"] if rs else "—",
                "sha256": rs["sha256"] if rs else "",
                "gold": rt["gold"] if rt else None,
                "lead_actor": rt["lead_actor"] if rt else None,
                "cg_switches_on": rt["cg_switches_on"] if rt else None,
                "playtime_sec": rt["playtime_sec"] if rt else 0,
            } if rs else None,
            "gold_diff": gold_diff,
            "level_diff": level_diff,
            "cg_diff": cg_diff,
            "var_changes": var_changes[:24],
            "total_var_changes": len(var_changes),
            "sw_changes": sw_changes[:24],
            "total_sw_changes": len(sw_changes),
        })

    order_map = {"modified": 0, "only_left": 1, "only_right": 2, "identical": 3}
    slot_diffs.sort(key=lambda x: (order_map.get(x["status"], 9), x["rel_path"]))

    return {
        "success": True,
        "game_id": game_id,
        "left_source": {
            "id": left_data["source_id"],
            "label": left_data["label"],
            "updated_at": left_data["updated_at"],
            "mtime": left_data["mtime"],
            "slot_count": left_data["slot_count"],
            "total_size_kb": left_data["total_size_kb"],
        },
        "right_source": {
            "id": right_data["source_id"],
            "label": right_data["label"],
            "updated_at": right_data["updated_at"],
            "mtime": right_data["mtime"],
            "slot_count": right_data["slot_count"],
            "total_size_kb": right_data["total_size_kb"],
        },
        "summary": {
            "total_slots": len(slot_diffs),
            "modified_count": modified_count,
            "only_left_count": removed_count,
            "only_right_count": added_count,
            "identical_count": identical_count,
            "has_differences": (modified_count + removed_count + added_count) > 0,
        },
        "slots": slot_diffs,
    }


def check_webdav_save_conflicts(game_id: int) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    cfg = load_config()
    backup_root = Path(cfg.get("save_backup_directory", r"E:\ACG\_Save_Backups"))
    backup_root.mkdir(parents=True, exist_ok=True)
    prefix = f"game_{game_id}_"

    local_zips = []
    for bf in sorted(backup_root.glob(f"{prefix}*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = bf.stat()
        local_zips.append({
            "filename": bf.name,
            "source_id": f"backup:{bf.name}",
            "size_kb": round(st.st_size / 1024.0, 1),
            "mtime": st.st_mtime,
            "created_at": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "location": "local_backup",
        })

    remote_zips = []
    webdav_configured = bool(cfg.get("webdav_enabled") and (cfg.get("webdav_url") or "").strip())
    webdav_error = ""

    if webdav_configured:
        client, base_url = _get_webdav_client_and_url(cfg)
        try:
            with client:
                r = client.request("PROPFIND", base_url + "/", headers={"Depth": "1"})
                if r.status_code in (200, 207) and r.text:
                    root_el = ET.fromstring(r.text)
                    for resp_el in root_el.iter():
                        if not resp_el.tag.endswith("response"):
                            continue
                        href_txt = ""
                        size_val = 0
                        last_mod_txt = ""
                        for child in resp_el.iter():
                            if child.tag.endswith("href") and child.text and not href_txt:
                                href_txt = urllib.parse.unquote(child.text.strip())
                            elif child.tag.endswith("getcontentlength") and child.text:
                                try:
                                    size_val = int(child.text.strip())
                                except Exception:
                                    pass
                            elif child.tag.endswith("getlastmodified") and child.text:
                                last_mod_txt = child.text.strip()
                        fname = Path(href_txt.rstrip("/")).name
                        if fname.startswith(prefix) and fname.endswith(".zip"):
                            remote_zips.append({
                                "filename": fname,
                                "source_id": f"webdav:{fname}",
                                "size_kb": round(size_val / 1024.0, 1) if size_val else 0.0,
                                "last_modified": last_mod_txt,
                                "is_downloaded": (backup_root / fname).is_file(),
                                "location": "webdav",
                            })
        except Exception as e:
            webdav_error = str(e)[:80]

    remote_zips.sort(key=lambda x: x["filename"], reverse=True)

    compare_target = "latest_backup"
    if remote_zips:
        compare_target = f"webdav:{remote_zips[0]['filename']}"
    elif local_zips:
        compare_target = f"backup:{local_zips[0]['filename']}"

    diff_res = compare_save_sources(game_id, left_source="local", right_source=compare_target)
    has_diff = bool(diff_res.get("success") and diff_res.get("summary", {}).get("has_differences"))

    conflict_state = "synced"
    conflict_desc = "本地实时存档与最新快照完全一致，无冲突。"
    if has_diff:
        l_mtime = diff_res["left_source"]["mtime"]
        r_mtime = diff_res["right_source"]["mtime"]
        unpulled_remotes = [rz for rz in remote_zips if not rz["is_downloaded"]]
        if unpulled_remotes and l_mtime > 0:
            conflict_state = "diverged"
            conflict_desc = f"检测到云端存在 {len(unpulled_remotes)} 份未拉取快照，且本地实时存档已发生修改，建议对比槽位后仲裁。"
        elif l_mtime > r_mtime + 5:
            conflict_state = "local_ahead"
            conflict_desc = "本地实时存档比最新快照更新，存在尚未固化的新游玩进度。"
        elif r_mtime > l_mtime + 5:
            conflict_state = "remote_ahead"
            conflict_desc = "快照/云端版本比当前本地存档更新（或拥有不同进度分支）。"
        else:
            conflict_state = "diverged"
            conflict_desc = "本地实时存档与快照内容存在差异，请检查下方槽位对比详情。"

    return {
        "success": True,
        "game_id": game_id,
        "webdav_configured": webdav_configured,
        "webdav_error": webdav_error,
        "conflict_state": conflict_state,
        "conflict_description": conflict_desc,
        "local_backups": local_zips[:25],
        "remote_backups": remote_zips[:25],
        "diff": diff_res if diff_res.get("success") else None,
    }


def resolve_save_conflict(
    game_id: int,
    strategy: str,
    snapshot_filename: str = "",
    slot_choices: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    cfg = load_config()
    backup_root = Path(cfg.get("save_backup_directory", r"E:\ACG\_Save_Backups"))
    backup_root.mkdir(parents=True, exist_ok=True)

    clean_snap = snapshot_filename.strip()
    if clean_snap.startswith("backup:"):
        clean_snap = clean_snap[len("backup:"):]
    elif clean_snap.startswith("webdav:"):
        clean_snap = clean_snap[len("webdav:"):]
    clean_snap = Path(clean_snap).name if clean_snap else ""

    def _ensure_snapshot_downloaded(fname: str) -> Optional[Path]:
        if not fname:
            prefix = f"game_{game_id}_"
            zips = sorted(backup_root.glob(f"{prefix}*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
            return zips[0] if zips else None
        target = backup_root / fname
        if target.is_file():
            return target
        client, base_url = _get_webdav_client_and_url(cfg)
        try:
            with client:
                dl_url = f"{base_url}/{urllib.parse.quote(fname)}"
                resp = client.get(dl_url)
                if resp.status_code == 200 and resp.content.startswith(b"PK\x03\x04"):
                    target.write_bytes(resp.content)
                    return target
        except Exception:
            pass
        return None

    if strategy == "keep_local":
        res = backup_game_saves(game_id, label="以本地为准仲裁")
        if not res.get("success"):
            return res
        if cfg.get("webdav_enabled") and (cfg.get("webdav_url") or "").strip() and res.get("zip_path"):
            upload_backup_to_webdav(Path(res["zip_path"]), cfg)
        return {
            "success": True,
            "message": "已将当前本地存档固化为最新权威快照，并同步至云端！",
            "save_status": get_game_save_status(game_id),
        }

    if strategy == "keep_both":
        pulled = _ensure_snapshot_downloaded(clean_snap)
        bak_res = backup_game_saves(game_id, label="双分支保留本地")
        return {
            "success": True,
            "message": (
                f"已保留双方分支：云端快照【{pulled.name if pulled else '无'}】已保存至本地快照库，"
                f"同时当前本地实时存档已备份为【{bak_res.get('filename', '新快照')}】！"
            ),
            "save_status": get_game_save_status(game_id),
        }

    if strategy == "use_snapshot":
        snap_path = _ensure_snapshot_downloaded(clean_snap)
        if not snap_path or not snap_path.is_file():
            return {"success": False, "message": "未找到目标快照文件，无法覆盖还原"}
        try:
            backup_game_saves(game_id, label="仲裁覆盖前保护备份", is_auto=True)
        except Exception:
            pass
        rest_res = restore_game_saves(game_id, snap_path.name)
        return rest_res

    if strategy == "slot_merge":
        snap_path = _ensure_snapshot_downloaded(clean_snap)
        if not snap_path or not snap_path.is_file():
            return {"success": False, "message": "未找到右侧快照压缩包，无法执行按槽位合并"}
        folder_path = game.get("folder_path") or ""
        save_dir_str = find_game_save_dir(folder_path, game=game)
        if not save_dir_str:
            return {"success": False, "message": "未找到游戏本地存档目录"}
        save_dir = Path(save_dir_str).resolve()
        save_dir.mkdir(parents=True, exist_ok=True)

        try:
            backup_game_saves(game_id, label="按槽合并前保护备份", is_auto=True)
        except Exception:
            pass

        choices = slot_choices or {}
        applied_from_right = 0
        kept_from_left = 0
        try:
            with zipfile.ZipFile(snap_path, "r") as zf:
                zip_members = {m.filename.replace("\\", "/"): m for m in zf.infolist() if not m.is_dir()}
                for rel_path, side in choices.items():
                    norm_rel = rel_path.replace("\\", "/")
                    if side == "right" and norm_rel in zip_members:
                        dest = (save_dir / norm_rel).resolve()
                        if not is_subpath(str(dest), str(save_dir)):
                            continue
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(zip_members[norm_rel], "r") as src, open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        applied_from_right += 1
                    else:
                        kept_from_left += 1
        except Exception as e:
            return {"success": False, "message": f"按槽位合并失败: {str(e)}"}

        return {
            "success": True,
            "message": f"按槽位合并完成！已保留 {kept_from_left} 个本地槽位，并从快照合并写入 {applied_from_right} 个槽位（合并前状态已自动备份）。",
            "save_status": get_game_save_status(game_id),
        }

    return {"success": False, "message": f"未知的仲裁策略: {strategy}"}
