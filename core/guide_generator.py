# -*- coding: utf-8 -*-
"""
RPG Maker MV/MZ Story & Branch AST Unpacker + AI Walkthrough Generator for ACG Vault v2.3.
- Automatically unpacks and inspects System.json, Actors.json, Items.json, CommonEvents.json, MapInfos.json, and Map*.json
- Applies local translation dictionary (翻译文件.json / translation.json) so extracted Japanese switches/choices/dialogs are translated
- Generates a structured, magazine-grade Markdown full-ending walkthrough into `walkthrough_md` (preserving `user_notes` for personal memos)
- Provides real-time F9 Variable & Switch cheat table inspection for the In-Game Companion Overlay (Alt+G)
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import load_config
from db.database import get_game_by_id, update_game_user_state
from core.mz_patcher import find_translation_dict_in_folder, MZPatcher
from core.ai_scraper import call_llm_chat


KEY_SWITCH_PAT = re.compile(
    r"结局|ED|Ending|True|Bad|Normal|好感|堕落|淫乱|怀孕|妊娠|처녀|処女|回想|全開|全开|クリア|解放|事件|イベント|ボス|Boss|路线|Route|章|Stage|Day|フェーズ",
    re.I
)
KEY_VAR_PAT = re.compile(
    r"好感|堕落|淫|感度|経験|经验|次数|回数|金|Gold|HP|MP|日|Day|進行|进度|ポイント|Point|ランク|Rank|Lv|レベル|愛情|欲望|露出|催眠|侵食|敗北",
    re.I
)
ENDING_EVENT_PAT = re.compile(
    r"结局|ED|Ending|エンディング|エピローグ|Epilogue|プロローグ|Prologue|クリア|Clear|真エンド|バッド|ノーマル|回想|全開|敗北|ボス|最終|终章",
    re.I
)


def _find_data_dir(folder_path: str) -> Optional[Path]:
    if not folder_path or not os.path.exists(folder_path):
        return None
    p = Path(folder_path)
    for cand in [p / "data", p / "www" / "data", p / "contents" / "data", p / "contents" / "www" / "data"]:
        if cand.exists() and (cand / "System.json").exists():
            return cand
    for sub in p.iterdir():
        if sub.is_dir() and not sub.name.startswith("."):
            for cand in [sub / "data", sub / "www" / "data"]:
                if cand.exists() and (cand / "System.json").exists():
                    return cand
    return None


def _load_json_safe(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            return json.load(f)
    except Exception:
        return None


def extract_f9_debug_cheats(game_id: int) -> Dict[str, Any]:
    """
    Extracts F9 variables and switches table from RPG Maker System.json (or parses from walkthrough_md)
    for instant lookup inside the In-Game Companion Overlay (Alt+G).
    """
    game = get_game_by_id(game_id)
    if not game:
        return {"supported": False, "variables": [], "switches": []}

    folder_path = game.get("folder_path") or ""
    data_dir = _find_data_dir(folder_path) if folder_path and os.path.exists(folder_path) else None

    if data_dir:
        trans_dict: Dict[str, str] = {}
        trs_path = find_translation_dict_in_folder(folder_path)
        if trs_path and os.path.exists(trs_path):
            try:
                trans_dict = MZPatcher.load_dict(trs_path)
            except Exception:
                trans_dict = {}

        def tr(s: Optional[str]) -> str:
            if not s or not isinstance(s, str):
                return ""
            s_clean = s.strip()
            if not trans_dict:
                return s_clean
            res, _ = MZPatcher.translate_string(s_clean, trans_dict)
            return res.strip()

        sys_data = _load_json_safe(data_dir / "System.json") or {}
        raw_switches = sys_data.get("switches") or []
        raw_vars = sys_data.get("variables") or []

        vars_list = []
        for idx, name in enumerate(raw_vars):
            if idx > 0 and name and str(name).strip():
                t_name = tr(str(name))
                is_key = bool(KEY_VAR_PAT.search(t_name) or KEY_VAR_PAT.search(str(name)))
                vars_list.append({
                    "id": idx,
                    "code": f"Var #{idx:04d}",
                    "name": t_name,
                    "raw_name": str(name).strip(),
                    "is_key": is_key
                })

        sw_list = []
        for idx, name in enumerate(raw_switches):
            if idx > 0 and name and str(name).strip():
                t_name = tr(str(name))
                is_key = bool(KEY_SWITCH_PAT.search(t_name) or KEY_SWITCH_PAT.search(str(name)))
                sw_list.append({
                    "id": idx,
                    "code": f"Sw #{idx:04d}",
                    "name": t_name,
                    "raw_name": str(name).strip(),
                    "is_key": is_key
                })

        vars_list.sort(key=lambda x: (not x["is_key"], x["id"]))
        sw_list.sort(key=lambda x: (not x["is_key"], x["id"]))
        return {
            "supported": True,
            "source": "system_json",
            "variables": vars_list[:80],
            "switches": sw_list[:80]
        }

    # Fallback: parse Var # / Sw # tables from walkthrough_md if game folder isn't RPG Maker or not present
    wt_text = game.get("walkthrough_md") or ""
    vars_fallback = []
    sw_fallback = []
    for m in re.finditer(r"`?Var\s*#?(\d+)`?\s*\|\s*\*\*([^*|]+)\*\*", wt_text, re.I):
        vid = int(m.group(1))
        vars_fallback.append({"id": vid, "code": f"Var #{vid:04d}", "name": m.group(2).strip(), "raw_name": "", "is_key": True})
    for m in re.finditer(r"`?Sw\s*#?(\d+)`?\s*\|\s*\*\*([^*|]+)\*\*", wt_text, re.I):
        sid = int(m.group(1))
        sw_fallback.append({"id": sid, "code": f"Sw #{sid:04d}", "name": m.group(2).strip(), "raw_name": "", "is_key": True})

    return {
        "supported": bool(vars_fallback or sw_fallback),
        "source": "walkthrough_md",
        "variables": vars_fallback,
        "switches": sw_fallback
    }


def inspect_rpgmaker_project(folder_path: str) -> Dict[str, Any]:
    """
    Deeply inspects an RPG Maker MV/MZ game's data/*.json files to extract characters,
    key switches, variables, key items, choice branches, conditional branches, and endings.
    """
    data_dir = _find_data_dir(folder_path)
    if not data_dir:
        return {"supported": False}

    trans_dict: Dict[str, str] = {}
    trs_path = find_translation_dict_in_folder(folder_path)
    if trs_path and os.path.exists(trs_path):
        try:
            trans_dict = MZPatcher.load_dict(trs_path)
        except Exception:
            trans_dict = {}

    def tr(s: Optional[str]) -> str:
        if not s or not isinstance(s, str):
            return ""
        s_clean = s.strip()
        if not trans_dict:
            return s_clean
        res, _ = MZPatcher.translate_string(s_clean, trans_dict)
        return res.strip()

    sys_data = _load_json_safe(data_dir / "System.json") or {}
    actors_data = _load_json_safe(data_dir / "Actors.json") or []
    items_data = _load_json_safe(data_dir / "Items.json") or []
    ces_data = _load_json_safe(data_dir / "CommonEvents.json") or []
    mapinfos_data = _load_json_safe(data_dir / "MapInfos.json") or []

    raw_switches = sys_data.get("switches") or []
    raw_vars = sys_data.get("variables") or []
    sw_map: Dict[int, str] = {}
    var_map: Dict[int, str] = {}
    key_switches: List[Tuple[int, str]] = []
    key_variables: List[Tuple[int, str]] = []

    for idx, name in enumerate(raw_switches):
        if idx > 0 and name and str(name).strip():
            t_name = tr(str(name))
            sw_map[idx] = t_name
            if KEY_SWITCH_PAT.search(t_name) or KEY_SWITCH_PAT.search(str(name)):
                key_switches.append((idx, t_name))

    if len(key_switches) < 6:
        for idx, t_name in list(sw_map.items())[:18]:
            if (idx, t_name) not in key_switches:
                key_switches.append((idx, t_name))

    for idx, name in enumerate(raw_vars):
        if idx > 0 and name and str(name).strip():
            t_name = tr(str(name))
            var_map[idx] = t_name
            if KEY_VAR_PAT.search(t_name) or KEY_VAR_PAT.search(str(name)):
                key_variables.append((idx, t_name))

    if len(key_variables) < 6:
        for idx, t_name in list(var_map.items())[:18]:
            if (idx, t_name) not in key_variables:
                key_variables.append((idx, t_name))

    actors = []
    for a in actors_data:
        if isinstance(a, dict) and a.get("name"):
            actors.append({
                "id": a.get("id"),
                "name": tr(a.get("name")),
                "nickname": tr(a.get("nickname", "")),
                "profile": tr(a.get("profile", "")).replace("\n", " ")
            })

    key_items = []
    for it in items_data:
        if isinstance(it, dict) and it.get("name"):
            if it.get("itypeId") == 2 or any(k in str(it.get("name")) for k in ("鍵", "钥匙", "Key", "证", "書", "石", "戒", "信", "玉")):
                key_items.append({
                    "id": it.get("id"),
                    "name": tr(it.get("name")),
                    "desc": tr(it.get("description", "")).replace("\n", " ")
                })

    def parse_command_list(cmd_list: List[Dict[str, Any]], source_label: str) -> Optional[Dict[str, Any]]:
        if not cmd_list:
            return None
        conds = []
        choices = []
        dialogs = []
        var_changes = []

        for cmd in cmd_list:
            if not isinstance(cmd, dict):
                continue
            code = cmd.get("code")
            params = cmd.get("parameters") or []
            if code == 111 and len(params) >= 2:
                ctype = params[0]
                if ctype == 0 and len(params) >= 3:
                    sw_id = params[1]
                    sw_state = "ON" if params[2] == 0 else "OFF"
                    conds.append(f"开关[{sw_id}:{sw_map.get(sw_id, '未知')}] == {sw_state}")
                elif ctype == 1 and len(params) >= 5:
                    v_id = params[1]
                    op_idx = params[4] if isinstance(params[4], int) and 0 <= params[4] < 6 else 0
                    op_str = ["==", ">=", "<=", ">", "<", "!="][op_idx]
                    val_str = str(params[3]) if params[2] == 0 else f"变量[{params[3]}]"
                    conds.append(f"变量[{v_id}:{var_map.get(v_id, '未知')}] {op_str} {val_str}")
            elif code == 102 and len(params) >= 1 and isinstance(params[0], list):
                opts = [tr(str(o)) for o in params[0] if o]
                if opts:
                    choices.append(" / ".join(opts))
            elif code == 122 and len(params) >= 5:
                v_id = params[0]
                if v_id in var_map and any(KEY_VAR_PAT.search(var_map[v_id]) for _ in [1]):
                    op_map = {0: "=", 1: "+=", 2: "-="}
                    if params[2] in op_map and params[3] == 0:
                        var_changes.append(f"{var_map[v_id]} {op_map[params[2]]} {params[4]}")
            elif code in (401, 405) and len(params) >= 1 and isinstance(params[0], str):
                line = tr(params[0])
                if any(k in line for k in ("结局", "ED", "Ending", "クリア", "条件", "解锁", "回想", "提示", "注意", "密码")):
                    if len(dialogs) < 4:
                        dialogs.append(line[:90])

        if not (conds or choices or dialogs):
            return None
        return {
            "source": source_label,
            "conditions": list(dict.fromkeys(conds))[:5],
            "choices": list(dict.fromkeys(choices))[:4],
            "var_changes": list(dict.fromkeys(var_changes))[:4],
            "key_dialogs": dialogs[:3]
        }

    important_events = []
    for ce in ces_data:
        if not isinstance(ce, dict) or not ce.get("name"):
            continue
        raw_name = str(ce["name"]).strip()
        if not raw_name or raw_name.startswith("//"):
            continue
        t_name = tr(raw_name)
        parsed = parse_command_list(ce.get("list") or [], f"公共事件 CE#{ce.get('id')} 【{t_name}】")
        if parsed and (ENDING_EVENT_PAT.search(t_name) or ENDING_EVENT_PAT.search(raw_name) or parsed["choices"] or parsed["conditions"]):
            important_events.append(parsed)

    map_names: Dict[int, str] = {}
    if isinstance(mapinfos_data, list):
        for m in mapinfos_data:
            if isinstance(m, dict) and m.get("id") and m.get("name"):
                map_names[int(m["id"])] = tr(str(m["name"]))

    map_files = sorted(data_dir.glob("Map*.json"))[:40]
    map_branches = []
    for mf in map_files:
        if mf.name.lower() == "mapinfos.json":
            continue
        m_match = re.match(r"Map(\d+)\.json", mf.name, re.I)
        if not m_match:
            continue
        mid = int(m_match.group(1))
        m_title = map_names.get(mid, mf.stem)
        m_json = _load_json_safe(mf)
        if not isinstance(m_json, dict):
            continue
        for ev in (m_json.get("events") or []):
            if not isinstance(ev, dict):
                continue
            ev_name = tr(str(ev.get("name") or ""))
            for page_idx, page in enumerate(ev.get("pages") or []):
                if not isinstance(page, dict):
                    continue
                parsed = parse_command_list(page.get("list") or [], f"地图【{m_title}】事件「{ev_name}」P{page_idx+1}")
                if parsed and (parsed["choices"] or len(parsed["conditions"]) >= 2 or parsed["key_dialogs"]):
                    map_branches.append(parsed)
                    if len(map_branches) >= 24:
                        break
            if len(map_branches) >= 24:
                break
        if len(map_branches) >= 24:
            break

    return {
        "supported": True,
        "game_title": tr(sys_data.get("gameTitle", "")),
        "total_switches": len(sw_map),
        "total_variables": len(var_map),
        "total_maps": len(map_names),
        "actors": actors[:10],
        "key_switches": key_switches[:30],
        "key_variables": key_variables[:30],
        "key_items": key_items[:20],
        "important_common_events": important_events[:25],
        "map_branches": map_branches[:20],
        "map_names": list(map_names.values())[:25]
    }


def _compile_static_markdown_guide(game: Dict[str, Any], blueprint: Dict[str, Any]) -> str:
    """Deterministically compiles a rich, structured Markdown walkthrough from unpacked AST data."""
    title = game.get("display_title") or game.get("clean_title") or blueprint.get("game_title") or game.get("folder_name")
    rj = game.get("rj_code") or ""
    circle = game.get("circle_name") or "同人社团"
    engine = game.get("engine_type") or "RPG Maker"

    lines = [
        f"# 《{title}》全流程分支、核心数值与全结局攻略",
        "",
        f"> **作品信息**：{f'`{rj}` · ' if rj else ''}开发商：**{circle}** · 驱动引擎：**{engine}**",
        "> **攻略说明**：本攻略由 **ACG Vault v2.3 工程解包引擎** 自动逆向解析游戏内部 `System.json`、`CommonEvents.json` 与地图事件脚本生成，包含精确的内部开关/变量 ID 与分支触发条件。",
        "",
        "## 一、 核心角色与初期设定"
    ]

    actors = blueprint.get("actors") or []
    if actors:
        lines.append("| 角色 ID | 姓名 / 称号 | 角色背景与初始设定 |")
        lines.append("| :--- | :--- | :--- |")
        for a in actors:
            nick = f"（{a['nickname']}）" if a.get("nickname") else ""
            prof = a.get("profile") or "主要登场角色"
            lines.append(f"| `Actor #{a['id']}` | **{a['name']}** {nick} | {prof} |")
    else:
        lines.append(f"- **主要角色**：详见游戏序章剧情介绍（{game.get('synopsis') or '探索推进主线解锁'}）。")

    lines.extend([
        "",
        "## 二、 核心数值变量与阶段开关一览（支持 F9 / Alt+G 速查 / MTool 修改）",
        "在游戏运行中按下 **`F9`**（RPG Maker 原生调试面板）、**`Alt+G`**（ACG Vault 游戏内悬浮攻略小窗）或 **`F8`**（全回想插件），可直接定位以下关键变量与开关："
    ])

    key_vars = blueprint.get("key_variables") or []
    if key_vars:
        lines.append("")
        lines.append("### 1. 关键属性 / 好感度 / 状态变量 (`Variables`)")
        lines.append("| 变量编号 | 内部变量名称 | 影响范围与攻略建议 |")
        lines.append("| :--- | :--- | :--- |")
        for vid, vname in key_vars[:18]:
            hint = "核心路线/结局判定数值" if any(k in vname for k in ("好感", "堕落", "淫", "愛", "Point")) else "流程进度与状态计数"
            lines.append(f"| `Var #{vid:04d}` | **{vname}** | {hint} |")

    key_sws = blueprint.get("key_switches") or []
    if key_sws:
        lines.append("")
        lines.append("### 2. 剧情锁 / 回想 / 结局触发开关 (`Switches`)")
        lines.append("| 开关编号 | 内部开关名称 | 作用说明 |")
        lines.append("| :--- | :--- | :--- |")
        for sid, sname in key_sws[:18]:
            hint = "开启后解锁对应回想/结局分支" if any(k in sname for k in ("回想", "全開", "ED", "结局", "クリア", "解放")) else "关键主线阶段推进标记"
            lines.append(f"| `Sw #{sid:04d}` | **{sname}** | {hint} |")

    map_branches = blueprint.get("map_branches") or []
    ce_branches = blueprint.get("important_common_events") or []
    all_branches = ce_branches + map_branches

    lines.extend([
        "",
        "## 三、 关键剧情分支、选项与触发条件表"
    ])
    if all_branches:
        lines.append("| 触发位置 / 事件源 | 判定前置条件 (`IF`) | 玩家选项 / 数值变化 | 剧情走向与结果 |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for b in all_branches[:22]:
            src = b["source"].replace("|", "/")
            cond_str = "<br>".join(b["conditions"]) if b["conditions"] else "无前置锁 / 主线直达"
            choice_parts = []
            if b["choices"]:
                choice_parts.append("选项: " + "；".join(b["choices"]))
            if b["var_changes"]:
                choice_parts.append("数值: " + "，".join(b["var_changes"]))
            choice_str = "<br>".join(choice_parts) if choice_parts else "自动剧情演出"
            dlg_str = " / ".join(b["key_dialogs"]) if b["key_dialogs"] else "推进阶段事件 / 解锁CG"
            lines.append(f"| {src} | {cond_str} | {choice_str} | {dlg_str} |")
    else:
        lines.append("- 本作流程以探索地图与触发公共事件为主，请参照上方关键变量与开关表推进。")

    key_items = blueprint.get("key_items") or []
    if key_items:
        lines.extend([
            "",
            "## 四、 关键道具与收集品清单 (`Key Items`)",
            "| 道具 ID | 道具名称 | 功能描述与获取提示 |",
            "| :--- | :--- | :--- |"
        ])
        for it in key_items[:15]:
            lines.append(f"| `Item #{it['id']}` | **{it['name']}** | {it['desc'] or '推进主线或开启隐藏区域必需道具'} |")

    lines.extend([
        "",
        "## 五、 全结局与全 CG 回想收集 Checklist",
        "- [ ] **主线通关结局 (True / Clear End)**：满足主线最终阶段条件并完成终章事件",
        "- [ ] **特殊 / 分支结局 (Sub / Bad End)**：在不同好感度/堕落度阈值下触发对应公共事件"
    ])
    for ce in ce_branches[:8]:
        if ENDING_EVENT_PAT.search(ce["source"]):
            cond_note = f"（条件：{' & '.join(ce['conditions'][:2])}）" if ce["conditions"] else ""
            lines.append(f"- [ ] **{ce['source']}** {cond_note}")

    lines.extend([
        "- [ ] **100% 全 CG 回想屋解锁**：",
        "  - 方法 1：在 ACG Vault 游戏详情页点击 **【⚡ 一键全CG解锁】**，进入游戏后按 **`F8`** 即可一键激活全部回想开关与 999,999 金币。",
        "  - 方法 2：在游戏内按 **`F9`** 调出调试菜单，将上方表格中的 `回想/全開/クリア` 开关设为 `ON`。"
    ])

    return "\n".join(lines)


def generate_game_walkthrough(game_id: int, use_llm: bool = True, overwrite: bool = False) -> Dict[str, Any]:
    """
    Generates a comprehensive Markdown walkthrough for game_id into `walkthrough_md`
    (keeping `user_notes` completely untouched for the user's personal clearance notes).
    """
    game = get_game_by_id(game_id)
    if not game:
        return {"success": False, "message": "游戏不存在"}

    folder_path = game.get("folder_path") or ""
    blueprint = inspect_rpgmaker_project(folder_path) if folder_path and os.path.exists(folder_path) else {"supported": False}

    cfg = load_config()
    llm_ready = bool(use_llm and cfg.get("llm_enabled") and (cfg.get("llm_api_key") or "127.0.0.1" in (cfg.get("llm_api_base") or "") or "localhost" in (cfg.get("llm_api_base") or "")))

    generated_md = ""
    used_engine = "ast_compiler"

    if llm_ready:
        title = game.get("display_title") or game.get("clean_title") or game.get("folder_name")
        compact_bp = {
            "title": title,
            "original_title": game.get("original_title"),
            "circle": game.get("circle_name"),
            "engine": game.get("engine_type"),
            "tags": game.get("tags"),
            "synopsis": (game.get("synopsis") or "")[:600],
            "unpacked_data": {
                "actors": blueprint.get("actors", [])[:8],
                "key_variables": blueprint.get("key_variables", [])[:20],
                "key_switches": blueprint.get("key_switches", [])[:20],
                "key_items": blueprint.get("key_items", [])[:15],
                "important_events": blueprint.get("important_common_events", [])[:18],
                "map_branches": blueprint.get("map_branches", [])[:15]
            } if blueprint.get("supported") else "Non-RPGMaker engine"
        }
        prompt = (
            f"请为游戏《{title}》撰写一份结构严谨、排版精美的杂志级 Markdown 全流程与全结局攻略。\n"
            "以下是我们从该游戏工程文件（System.json / CommonEvents.json / Map*.json）中解包提取出的真实内部开关、变量、事件分支与角色数据：\n"
            f"```json\n{json.dumps(compact_bp, ensure_ascii=False, indent=2)}\n```\n"
            "要求：\n"
            "1. 必须包含：一、核心机制与角色设定；二、核心变量与开关表（附带真实编号 Var/Sw ID 及 F8/F9 修改提示）；三、主线流程与关键分支选项表（Markdown 表格）；四、全结局达成条件与全 CG 收集 Checklist（使用 `- [ ]` 交互式复选框）。\n"
            "2. 充分利用解包数据中的真实变量名、开关名、公共事件名和地图名，切勿编造虚假数值。"
        )
        llm_md = call_llm_chat(
            messages=[
                {"role": "system", "content": "你是一位殿堂级 ACG 游戏攻略作者与逆向工程分析师，擅长编写条理清晰、含精确开关变量与分支表格的 Markdown 攻略。"},
                {"role": "user", "content": prompt}
            ],
            cfg=cfg,
            temperature=0.3,
            max_tokens=2800,
            timeout=35.0
        )
        if llm_md and len(llm_md.strip()) > 200:
            generated_md = llm_md.strip()
            used_engine = "llm_plus_ast" if blueprint.get("supported") else "llm"

    if not generated_md:
        if blueprint.get("supported"):
            generated_md = _compile_static_markdown_guide(game, blueprint)
            used_engine = "ast_compiler"
        else:
            title = game.get("display_title") or game.get("clean_title") or game.get("folder_name")
            tags_str = " / ".join(game.get("tags") or ["ACG", game.get("engine_type") or "PC"])
            generated_md = (
                f"# 《{title}》全流程全结局攻略与收集指南\n\n"
                f"> **社团/开发商**：{game.get('circle_name') or '未知'} · **引擎**：{game.get('engine_type') or 'PC'} · **标签**：{tags_str}\n\n"
                f"## 一、 故事背景与核心玩法\n{game.get('synopsis') or '暂无简介，可在游玩过程中补充关键机制说明。'}\n\n"
                "## 二、 关键路线分支与选项表\n"
                "| 章节 / 阶段 | 触发地点 / 场景 | 关键行动与选项 | 结果 / 解锁内容 |\n"
                "| :--- | :--- | :--- | :--- |\n"
                "| 序章 | 初始场景 | 推进基础剧情并保存初始存档 | 开启主线分支 |\n"
                "| 中盘 | 核心探索区 | 完成关键角色互动事件 | 提升好感度 / 推进路线 |\n"
                "| 终章 | 最终决战 / 分支点 | 根据角色数值满足对应阈值 | 进入对应结局 |\n\n"
                "## 三、 全结局与全 CG 收集 Checklist\n"
                "- [ ] **True End (真结局 / 完美结局)**：满足全部核心好感或主线条件\n"
                "- [ ] **Normal End (普通结局)**：常规通关路线\n"
                "- [ ] **Bad / Sub End (特殊分支结局)**：特定条件或战败分支触发\n"
                "- [ ] **全 CG 回想屋 100% 解锁**：可在详情页使用【导入全CG存档】或游戏内回想全开开关\n"
            )
            used_engine = "smart_template"

    existing_wt = (game.get("walkthrough_md") or "").strip()
    if existing_wt and not overwrite:
        final_walkthrough = f"{existing_wt}\n\n---\n\n{generated_md}"
    else:
        final_walkthrough = generated_md

    update_game_user_state(game_id=game_id, walkthrough_md=final_walkthrough)

    engine_labels = {
        "llm_plus_ast": "AI 大模型 + 工程解包 AST 联合生成",
        "llm": "AI 大模型智能生成",
        "ast_compiler": "RPG Maker 工程解包 AST 静态编译",
        "smart_template": "元数据智能结构化生成"
    }
    return {
        "success": True,
        "engine_used": used_engine,
        "unpacked_supported": bool(blueprint.get("supported")),
        "walkthrough_md": final_walkthrough,
        "user_notes": game.get("user_notes") or "",
        "message": f"全结局攻略生成成功（{engine_labels.get(used_engine, used_engine)}，共 {len(generated_md)} 字符）！"
    }
