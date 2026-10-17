# 🎮 ACG Vault v2.1 (本地 ACG 游戏资产与攻略管理中心)

一款专为本地 ACG / Galgame / 同人游戏爱好者打造的现代化全功能游戏库管理系统。基于 **FastAPI + SQLite (WAL) + Vue 3 响应式控制台** 架构，提供本地游戏目录深度扫描、DLsite / Bangumi / Steam / VNDB 多源元数据智能刮削、游戏智能启动与多语言环境转区、RPG Maker MV/MZ 补丁固化与一键还原、存档快照备份/恢复以及查重归档功能。

---

## ✨ 核心特性 (v2.1 升级亮点)

1. 📂 **智能目录扫描与指纹识别** (`core/scanner.py`)：
   - 深入遍历预设的游戏目录（默认 `E:\ACG`），自动识别游戏主执行程序（`Game.exe`, `*.exe` 等）与运行引擎。
   - 精准提取 RJ/VJ/BJ 号与清洗后标题，重扫时自动保护用户手动定制的主程序路径与入库时间。
2. 🌐 **四源元数据与封面刮削缓存** (`core/scraper.py`, `core/ai_scraper.py`)：
   - 支持从 **DLsite**、**Bangumi (番组计划)**、**Steam**、**VNDB** 自动拉取社团名称、发售日期、游戏简介、标签分类与高清海报封面。
   - 内置 SQLite `scrape_cache` 本地缓存、图片文件头魔数校验与日文简介自动汉化翻译。
3. 🚀 **一键直启、实时运行监控与转区调优** (`core/launcher.py`)：
   - 支持直接启动、Locale Emulator 转区启动、MTool 翻译挂钩启动。
   - 实时监控游戏运行状态（防多开保护、卡片呼吸态指示），退出后自动精准累计游玩时长。
4. 🧩 **RPG Maker MV/MZ 补丁固化与无损还原** (`core/mz_patcher.py`)：
   - 支持将外挂 JSON 翻译字典静态固化进游戏本体并注入运行时补丁，同时支持一键从备份无损还原原版数据。
5. 💾 **存档快照备份与一键回档** (`core/launcher.py`)：
   - 自动探测本地存档目录，支持创建多份时间戳 `.zip` 快照、查看历史备份清单与一键安全回档。
6. 🗃️ **中日文续作感知查重与安全归档** (`core/dedup.py`)：
   - 智能区分《黑兽1/2》《状態異常Ⅰ/Ⅱ/Ⅲ》等续作与多版本重复副本，支持一键归档至 `_Archive_Duplicates` 隔离目录。

---

## 🛠️ 技术栈与依赖

- **后端引擎**：Python 3.10+, FastAPI, Uvicorn, Pydantic v2
- **存储与并发**：SQLite 3 (WAL 高并发模式)
- **网络与解析**：HTTPX, BeautifulSoup4, RapidFuzz
- **前端交互**：Vue 3 + Tailwind CSS + Lucide Icons + Marked.js（100% 本地离线静态资源，零外部 CDN 依赖）

---

## 🚀 启动与使用说明

### 1. 一键启动

直接双击运行根目录批处理脚本：
```bat
start.bat
```
或通过命令行手动运行：
```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py
```

服务启动后，在浏览器访问控制台：
👉 **`http://127.0.0.1:8000`**

### 2. 核心配置文件说明 (`data/config.json`)

系统启动后会自动在 `data/config.json` 生成/加载配置：

```json
{
  "game_directories": ["E:\\ACG"],
  "archive_directory": "E:\\ACG\\_Archive_Duplicates",
  "save_backup_directory": "E:\\ACG\\_Save_Backups",
  "mtool_directory": "E:\\ACG\\MTool",
  "leproc_path": "",
  "proxy": "",
  "auto_scrape": true,
  "scrape_source": "auto",
  "cover_fit_mode": "smart",
  "theme": "dark",
  "port": 8000
}
```
