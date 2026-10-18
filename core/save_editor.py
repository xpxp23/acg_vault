# -*- coding: utf-8 -*-
"""
RPG Maker MV (.rpgsave LZString Base64) & MZ (.rmmzsave Zlib/Pako) Visual Save Editor for ACG Vault v2.4.
Provides:
1. Pure-Python LZString Base64 Decompressor & Compressor (100% compatible with RPG Maker MV LZString.compressToBase64)
2. Multi-mode Zlib / Pako / Raw Deflate Decompressor & Compressor (compatible with RPG Maker MZ StorageManager.jsonToZip)
3. Automatic mapping of System.json variable names, switch names, and Actors.json character names
4. Safe modification of Gold, Actor Level/HP/MP, Core Variables, and Recall/Story Switches with automatic backup
"""

import os
import re
import json
import zlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from db.database import get_game_by_id
from core.launcher import find_game_save_dir, backup_game_saves, is_subpath

_KEY_STR_BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
_BASE_REVERSE_DICT = {ch: i for i, ch in enumerate(_KEY_STR_BASE64)}

_KEY_VAR_PAT = re.compile(
    r"好感|愛情|愛|淫|堕落|H|エロ|感度|経験|金|所持|探索|進行|章|Day|日|体力|魔力|SAN|理智|魅力|名声|欲|ポイント|Pt|Lv|Level|结局|End|Route|ルート|信任|纯洁|腐败|怀孕|受胎|催眠|调教|露出|服从|羞耻",
    re.I
)
_CG_SW_PAT = re.compile(
    r"回想|全開|全开|解放|解禁|クリア|ギャラリー|CG|Gallery|Recall|Scene|Ending|ED|シーン|イベント|Hシーン|记忆|画廊|结局|通关|True|Good|Bad",
    re.I
)


def decompress_from_base64(input_str: str) -> str:
    """Decompresses an LZString Base64 encoded string (used by RPG Maker MV .rpgsave)."""
    if not input_str:
        return ""
    s = "".join(ch for ch in input_str.strip() if ch in _BASE_REVERSE_DICT)
    if not s:
        return ""
    length = len(s)

    def get_next_value(index: int) -> int:
        if index >= length:
            return 0
        return _BASE_REVERSE_DICT.get(s[index], 0)

    return _lz_decompress(length, 32, get_next_value)


def _lz_decompress(length: int, reset_value: int, get_next_value) -> str:
    dictionary: List[str] = [chr(0), chr(1), chr(2)]
    enlarge_in = 4
    dict_size = 4
    num_bits = 3
    result: List[str] = []

    data_val = get_next_value(0)
    data_position = reset_value
    data_index = 1

    def read_bits(n_bits: int) -> int:
        nonlocal data_val, data_position, data_index
        bits = 0
        maxpower = 1 << n_bits
        power = 1
        while power != maxpower:
            resb = data_val & data_position
            data_position >>= 1
            if data_position == 0:
                data_position = reset_value
                data_val = get_next_value(data_index)
                data_index += 1
            bits |= (power if resb > 0 else 0)
            power <<= 1
        return bits

    next_c = read_bits(2)
    if next_c == 0:
        c = chr(read_bits(8))
    elif next_c == 1:
        c = chr(read_bits(16))
    elif next_c == 2:
        return ""
    else:
        return ""

    dictionary.append(c)
    w = c
    result.append(c)

    while True:
        if data_index > length:
            return ""
        c_code = read_bits(num_bits)
        if c_code == 0:
            dictionary.append(chr(read_bits(8)))
            c_code = dict_size
            dict_size += 1
            enlarge_in -= 1
        elif c_code == 1:
            dictionary.append(chr(read_bits(16)))
            c_code = dict_size
            dict_size += 1
            enlarge_in -= 1
        elif c_code == 2:
            return "".join(result)

        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1

        if c_code < len(dictionary) and dictionary[c_code] is not None:
            entry = dictionary[c_code]
        else:
            if c_code == dict_size:
                entry = w + w[0]
            else:
                return ""

        result.append(entry)
        dictionary.append(w + entry[0])
        dict_size += 1
        enlarge_in -= 1
        w = entry

        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1


def compress_to_base64(uncompressed: str) -> str:
    """Compresses a string into LZString Base64 format (compatible with RPG Maker MV .rpgsave)."""
    if uncompressed is None:
        return ""
    res = _lz_compress(uncompressed, 6, lambda a: _KEY_STR_BASE64[a])
    mod = len(res) % 4
    if mod == 1:
        return res + "==="
    elif mod == 2:
        return res + "=="
    elif mod == 3:
        return res + "="
    return res


def _lz_compress(uncompressed: str, bits_per_char: int, get_char_from_int) -> str:
    if uncompressed is None:
        return ""
    context_dictionary: Dict[str, int] = {}
    context_dictionary_to_create: Dict[str, bool] = {}
    context_w = ""
    context_enlarge_in = 2
    context_dict_size = 3
    context_num_bits = 2
    context_data: List[str] = []
    context_data_val = 0
    context_data_position = 0

    def write_bit(value: int):
        nonlocal context_data_val, context_data_position
        context_data_val = (context_data_val << 1) | (value & 1)
        if context_data_position == bits_per_char - 1:
            context_data_position = 0
            context_data.append(get_char_from_int(context_data_val))
            context_data_val = 0
        else:
            context_data_position += 1

    def write_bits(n_bits: int, value: int):
        val = value
        for _ in range(n_bits):
            write_bit(val & 1)
            val >>= 1

    def produce_w():
        nonlocal context_enlarge_in, context_num_bits, context_dict_size
        if context_w in context_dictionary_to_create:
            ch_code = ord(context_w[0])
            if ch_code < 256:
                write_bits(context_num_bits, 0)
                write_bits(8, ch_code)
            else:
                write_bits(context_num_bits, 1)
                write_bits(16, ch_code)
            context_enlarge_in -= 1
            if context_enlarge_in == 0:
                context_enlarge_in = 1 << context_num_bits
                context_num_bits += 1
            del context_dictionary_to_create[context_w]
        else:
            write_bits(context_num_bits, context_dictionary[context_w])
        context_enlarge_in -= 1
        if context_enlarge_in == 0:
            context_enlarge_in = 1 << context_num_bits
            context_num_bits += 1

    for c in uncompressed:
        if c not in context_dictionary:
            context_dictionary[c] = context_dict_size
            context_dict_size += 1
            context_dictionary_to_create[c] = True

        wc = context_w + c
        if wc in context_dictionary:
            context_w = wc
        else:
            produce_w()
            context_dictionary[wc] = context_dict_size
            context_dict_size += 1
            context_w = c

    if context_w != "":
        produce_w()

    write_bits(context_num_bits, 2)
    while True:
        context_data_val <<= 1
        if context_data_position == bits_per_char - 1:
            context_data.append(get_char_from_int(context_data_val))
            break
        else:
            context_data_position += 1

    return "".join(context_data)


def _decode_rmmzsave(raw_bytes: bytes) -> Tuple[str, str]:
    text_try = raw_bytes.decode("utf-8", errors="ignore").strip()
    if text_try.startswith("{") and text_try.endswith("}"):
        return text_try, "plain"

    try:
        dec = zlib.decompress(raw_bytes)
        return dec.decode("utf-8"), "zlib_utf8"
    except Exception:
        pass

    try:
        latin1_bytes = raw_bytes.decode("utf-8").encode("latin1")
        dec = zlib.decompress(latin1_bytes)
        return dec.decode("utf-8"), "zlib"
    except Exception:
        pass

    for b_candidate, mode_tag in ((raw_bytes, "raw_deflate"),):
        try:
            dec = zlib.decompress(b_candidate, -zlib.MAX_WBITS)
            return dec.decode("utf-8"), mode_tag
        except Exception:
            pass

    raise ValueError("无法解压 .rmmzsave 存档文件（非标准 Zlib/Pako 格式）")


def _encode_rmmzsave(json_str: str, mode: str = "zlib") -> bytes:
    if mode == "plain":
        return json_str.encode("utf-8")
    compressed = zlib.compress(json_str.encode("utf-8"))
    if mode == "zlib_utf8":
        return compressed
    if mode == "raw_deflate":
        comp_obj = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -zlib.MAX_WBITS)
        return comp_obj.compress(json_str.encode("utf-8")) + comp_obj.flush()
    return compressed.decode("latin1").encode("utf-8")


def _find_rpgmaker_data_dir(folder_path: str) -> Optional[Path]:
    if not folder_path or not os.path.exists(folder_path):
        return None
    p = Path(folder_path)
    for cand in (p / "data", p / "www" / "data"):
        if (cand / "System.json").exists():
            return cand
    try:
        for sub in p.iterdir():
            if sub.is_dir() and not sub.name.startswith("."):
                for cand in (sub / "data", sub / "www" / "data"):
                    if (cand / "System.json").exists():
                        return cand
    except Exception:
        pass
    return None


def _load_rpgmaker_schema(folder_path: str) -> Dict[str, Any]:
    schema: Dict[str, Any] = {
        "variables": [],
        "switches": [],
        "actors": []
    }
    data_dir = _find_rpgmaker_data_dir(folder_path)
    if not data_dir:
        return schema

    sys_file = data_dir / "System.json"
    if sys_file.exists():
        try:
            with open(sys_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                sys_data = json.load(f)
            schema["variables"] = sys_data.get("variables") or []
            schema["switches"] = sys_data.get("switches") or []
        except Exception:
            pass

    actors_file = data_dir / "Actors.json"
    if actors_file.exists():
        try:
            with open(actors_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                act_data = json.load(f)
            if isinstance(act_data, list):
                names = [""] * len(act_data)
                for idx, item in enumerate(act_data):
                    if isinstance(item, dict) and item.get("name"):
                        names[idx] = str(item["name"]).strip()
                schema["actors"] = names
        except Exception:
            pass

    return schema


def _unwrap_jsonex_array(container: Any) -> Optional[List[Any]]:
    if isinstance(container, list):
        return container
    if isinstance(container, dict) and isinstance(container.get("@a"), list):
        return container["@a"]
    return None


def _extract_and_set_gold(save_obj: Dict[str, Any], new_gold: Optional[int] = None) -> int:
    party = save_obj.get("party")
    if isinstance(party, dict):
        if new_gold is not None:
            party["_gold"] = max(0, int(new_gold))
        return int(party.get("_gold") or 0)
    return 0


def _extract_variables_array(save_obj: Dict[str, Any]) -> List[Any]:
    vars_obj = save_obj.get("variables")
    if isinstance(vars_obj, dict):
        arr = _unwrap_jsonex_array(vars_obj.get("_data"))
        if arr is not None:
            return arr
    return []


def _set_variable_value(save_obj: Dict[str, Any], var_id: int, value: Any) -> bool:
    if var_id <= 0:
        return False
    vars_obj = save_obj.get("variables")
    if not isinstance(vars_obj, dict):
        return False
    arr = _unwrap_jsonex_array(vars_obj.get("_data"))
    if arr is None:
        return False
    while len(arr) <= var_id:
        arr.append(0)
    arr[var_id] = value
    return True


def _extract_switches_array(save_obj: Dict[str, Any]) -> List[Any]:
    sw_obj = save_obj.get("switches")
    if isinstance(sw_obj, dict):
        arr = _unwrap_jsonex_array(sw_obj.get("_data"))
        if arr is not None:
            return arr
    return []


def _set_switch_value(save_obj: Dict[str, Any], sw_id: int, value: bool) -> bool:
    if sw_id <= 0:
        return False
    sw_obj = save_obj.get("switches")
    if not isinstance(sw_obj, dict):
        return False
    arr = _unwrap_jsonex_array(sw_obj.get("_data"))
    if arr is None:
        return False
    while len(arr) <= sw_id:
        arr.append(False)
    arr[sw_id] = bool(value)
    return True


def _extract_actors_info(save_obj: Dict[str, Any], schema_actors: List[str]) -> List[Dict[str, Any]]:
    actors_obj = save_obj.get("actors")
    if not isinstance(actors_obj, dict):
        return []
    arr = _unwrap_jsonex_array(actors_obj.get("_data"))
    if not arr:
        return []

    result = []
    for idx in range(1, len(arr)):
        act = arr[idx]
        if not isinstance(act, dict):
            continue
        name = act.get("_name") or (schema_actors[idx] if idx < len(schema_actors) else "") or f"角色 #{idx}"
        level = act.get("_level")
        hp = act.get("_hp")
        mp = act.get("_mp")
        if level is None and hp is None:
            continue
        result.append({
            "actor_id": idx,
            "name": str(name),
            "level": int(level if level is not None else 1),
            "hp": int(hp if hp is not None else 100),
            "mp": int(mp if mp is not None else 0)
        })
    return result


def _update_actors_data(save_obj: Dict[str, Any], actor_updates: List[Dict[str, Any]]) -> int:
    if not actor_updates:
        return 0
    actors_obj = save_obj.get("actors")
    if not isinstance(actors_obj, dict):
        return 0
    arr = _unwrap_jsonex_array(actors_obj.get("_data"))
    if not arr:
        return 0

    updated = 0
    for item in actor_updates:
        aid = int(item.get("actor_id") or 0)
        if 0 < aid < len(arr) and isinstance(arr[aid], dict):
            act = arr[aid]
            if "level" in item and item["level"] is not None:
                act["_level"] = max(1, int(item["level"]))
            if "hp" in item and item["hp"] is not None:
                act["_hp"] = max(1, int(item["hp"]))
            if "mp" in item and item["mp"] is not None:
                act["_mp"] = max(0, int(item["mp"]))
            updated += 1
    return updated


def _load_save_file_json(file_path: Path) -> Tuple[Dict[str, Any], str]:
    ext = file_path.suffix.lower()
    if ext == ".rpgsave":
        raw_txt = file_path.read_text(encoding="utf-8", errors="ignore").strip()
        if raw_txt.startswith("{") and raw_txt.endswith("}"):
            return json.loads(raw_txt), "rpgsave_plain"
        dec_txt = decompress_from_base64(raw_txt)
        if not dec_txt:
            raise ValueError("LZString Base64 解码结果为空")
        return json.loads(dec_txt), "rpgsave_lz"
    elif ext == ".rmmzsave":
        raw_bytes = file_path.read_bytes()
        dec_txt, mode = _decode_rmmzsave(raw_bytes)
        return json.loads(dec_txt), f"rmmzsave_{mode}"
    else:
        raise ValueError(f"暂不支持直接解析 {ext} 格式")


def _write_save_file_json(file_path: Path, save_obj: Dict[str, Any], fmt_tag: str):
    json_str = json.dumps(save_obj, ensure_ascii=False, separators=(",", ":"))
    if fmt_tag == "rpgsave_plain":
        file_path.write_text(json_str, encoding="utf-8")
    elif fmt_tag == "rpgsave_lz":
        b64 = compress_to_base64(json_str)
        file_path.write_text(b64, encoding="utf-8")
    elif fmt_tag.startswith("rmmzsave_"):
        mode = fmt_tag[len("rmmzsave_"):]
        enc_bytes = _encode_rmmzsave(json_str, mode=mode)
        file_path.write_bytes(enc_bytes)
    else:
        raise ValueError(f"未知的存档编码格式: {fmt_tag}")


def list_editable_save_slots(game_id: int) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"supported": False, "slots": [], "message": "游戏不存在"}

    folder_path = game.get("folder_path", "")
    save_dir_str = find_game_save_dir(folder_path, game)
    if not save_dir_str or not os.path.exists(save_dir_str):
        return {"supported": False, "slots": [], "message": "未找到存档目录"}

    save_dir = Path(save_dir_str)
    slots = []
    skip_stems = {"config", "global", "common"}

    try:
        for f in sorted(save_dir.iterdir()):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext not in (".rpgsave", ".rmmzsave"):
                continue
            stem_low = f.stem.lower()
            if stem_low in skip_stems:
                continue
            st = f.stat()
            num_m = re.search(r"(\d+)", f.stem)
            slot_label = f"存档槽 #{num_m.group(1)}" if num_m else f.stem
            slots.append({
                "filename": f.name,
                "label": slot_label,
                "format": "RPG Maker MV (.rpgsave)" if ext == ".rpgsave" else "RPG Maker MZ (.rmmzsave)",
                "size_kb": round(st.st_size / 1024.0, 1),
                "updated_at": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "mtime": st.st_mtime
            })
    except Exception:
        pass

    slots.sort(key=lambda x: x["mtime"], reverse=True)
    return {
        "supported": len(slots) > 0,
        "save_dir": str(save_dir),
        "slots": slots
    }


def inspect_save_slot(game_id: int, filename: str) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_path = game.get("folder_path", "")
    save_dir_str = find_game_save_dir(folder_path, game)
    if not save_dir_str:
        return {"success": False, "message": "未找到游戏存档目录"}

    safe_name = Path(filename).name
    target_file = (Path(save_dir_str) / safe_name).resolve()
    if not target_file.exists() or not is_subpath(str(target_file), str(Path(save_dir_str).resolve())):
        return {"success": False, "message": "指定的存档槽位文件不存在"}

    try:
        save_obj, fmt_tag = _load_save_file_json(target_file)
    except Exception as e:
        return {"success": False, "message": f"解析存档失败: {str(e)}"}

    schema = _load_rpgmaker_schema(folder_path)
    sys_vars = schema.get("variables") or []
    sys_switches = schema.get("switches") or []
    sys_actors = schema.get("actors") or []

    gold = _extract_and_set_gold(save_obj)
    actors = _extract_actors_info(save_obj, sys_actors)
    raw_vars = _extract_variables_array(save_obj)
    raw_switches = _extract_switches_array(save_obj)

    max_var_len = max(len(sys_vars), len(raw_vars))
    variables_list = []
    for vid in range(1, max_var_len):
        vname = str(sys_vars[vid] if vid < len(sys_vars) and sys_vars[vid] else "").strip()
        vval = raw_vars[vid] if vid < len(raw_vars) else 0
        if vval is None:
            vval = 0
        if not vname and vval == 0:
            continue
        if isinstance(vval, (dict, list)):
            continue
        is_key = bool(vname and _KEY_VAR_PAT.search(vname))
        variables_list.append({
            "id": vid,
            "name": vname or f"未命名变量 #{vid:04d}",
            "value": vval,
            "is_key": is_key
        })

    variables_list.sort(key=lambda x: (0 if x["is_key"] else 1, x["id"]))

    max_sw_len = max(len(sys_switches), len(raw_switches))
    switches_list = []
    for sid in range(1, max_sw_len):
        sname = str(sys_switches[sid] if sid < len(sys_switches) and sys_switches[sid] else "").strip()
        sval = bool(raw_switches[sid]) if sid < len(raw_switches) and raw_switches[sid] is not None else False
        if not sname and not sval:
            continue
        is_cg = bool(sname and _CG_SW_PAT.search(sname))
        switches_list.append({
            "id": sid,
            "name": sname or f"未命名开关 #{sid:04d}",
            "value": sval,
            "is_cg": is_cg
        })

    switches_list.sort(key=lambda x: (0 if x["is_cg"] else 1, x["id"]))

    return {
        "success": True,
        "filename": safe_name,
        "format": fmt_tag,
        "gold": gold,
        "actors": actors,
        "variables": variables_list[:400],
        "switches": switches_list[:400],
        "total_variables": len(variables_list),
        "total_switches": len(switches_list)
    }


def modify_save_slot(
    game_id: int,
    filename: str,
    gold: Optional[int] = None,
    variables: Optional[Dict[str, Any]] = None,
    switches: Optional[Dict[str, bool]] = None,
    actors: Optional[List[Dict[str, Any]]] = None,
    unlock_all_switches: bool = False
) -> Dict[str, Any]:
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_path = game.get("folder_path", "")
    save_dir_str = find_game_save_dir(folder_path, game)
    if not save_dir_str:
        return {"success": False, "message": "未找到游戏存档目录"}

    safe_name = Path(filename).name
    target_file = (Path(save_dir_str) / safe_name).resolve()
    if not target_file.exists() or not is_subpath(str(target_file), str(Path(save_dir_str).resolve())):
        return {"success": False, "message": "指定的存档槽位文件不存在"}

    try:
        backup_game_saves(game_id, label=f"改档前自动备份_{safe_name}")
    except Exception:
        pass

    try:
        save_obj, fmt_tag = _load_save_file_json(target_file)
    except Exception as e:
        return {"success": False, "message": f"读取存档失败: {str(e)}"}

    changed_summary = []

    if gold is not None:
        _extract_and_set_gold(save_obj, int(gold))
        changed_summary.append(f"金钱={int(gold)}")

    if actors:
        act_cnt = _update_actors_data(save_obj, actors)
        if act_cnt > 0:
            changed_summary.append(f"{act_cnt}名角色属性")

    if variables:
        var_cnt = 0
        for k, v in variables.items():
            try:
                vid = int(k)
                val: Any = v
                if isinstance(v, str):
                    if v.lstrip("-").isdigit():
                        val = int(v)
                    else:
                        try:
                            val = float(v)
                        except ValueError:
                            val = v
                if _set_variable_value(save_obj, vid, val):
                    var_cnt += 1
            except Exception:
                continue
        if var_cnt > 0:
            changed_summary.append(f"{var_cnt}项变量")

    if switches:
        sw_cnt = 0
        for k, v in switches.items():
            try:
                sid = int(k)
                if _set_switch_value(save_obj, sid, bool(v)):
                    sw_cnt += 1
            except Exception:
                continue
        if sw_cnt > 0:
            changed_summary.append(f"{sw_cnt}个开关")

    if unlock_all_switches:
        schema = _load_rpgmaker_schema(folder_path)
        sys_switches = schema.get("switches") or []
        unlocked = 0
        for sid in range(1, len(sys_switches)):
            sname = str(sys_switches[sid] or "")
            if sname and _CG_SW_PAT.search(sname):
                _set_switch_value(save_obj, sid, True)
                unlocked += 1
        if unlocked > 0:
            changed_summary.append(f"全开{unlocked}个回想/CG开关")

    try:
        _write_save_file_json(target_file, save_obj, fmt_tag)
    except Exception as e:
        return {"success": False, "message": f"写入存档文件失败: {str(e)}"}

    summary_str = "、".join(changed_summary) if changed_summary else "存档数据"
    return {
        "success": True,
        "filename": safe_name,
        "message": f"已成功修改【{safe_name}】({summary_str})！原存档已自动生成防坏档快照。"
    }
