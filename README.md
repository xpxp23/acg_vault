# 🎮 ACG Vault (本地 ACG 游戏资产与元数据管理中心)

一款专为本地 ACG / Galgame / 同人游戏爱好者打造的现代化全功能游戏库管理系统。基于 **FastAPI + SQLite + Web 前端** 架构，提供本地游戏目录深度扫描、DLsite / Bangumi 元数据智能刮削、游戏智能启动与多语言环境转区、RPG Maker MZ 补丁集成以及查重归档功能。

---

## ✨ 核心特性

1. 📂 **智能目录扫描与指纹识别** (`core/scanner.py`)：
   - 深入遍历预设的游戏目录（默认 `E:\ACG`），自动识别游戏主执行程序（`Game.exe`, `*.exe` 等）。
   - 提取 RJ 号（DLsite）、VJ 号或游戏名称，计算哈希并建立本地索引。
2. 🌐 **多源元数据与封面刮削** (`core/scraper.py`, `core/ai_scraper.py`)：
   - 支持从 **DLsite**、**Bangumi (番组计划)** 自动拉取社团名称、发售日期、游戏简介、标签分类与高清海报封面。
   - 内置模糊匹配算法（RapidFuzz）与代理网络穿透支持。
3. 🚀 **一键直启与转区环境调优** (`core/launcher.py`)：
   - 支持直接启动、Locale Emulator 转区启动、MTool 翻译挂钩启动。
   - 自动记录游戏运行时长与上次启动时间。
4. 🧩 **RPG Maker MZ 补丁深度联动** (`core/mz_patcher.py`)：
   - 针对 RM 引擎游戏直接集成翻译注入与补丁管理。
5. 🗃️ **去重与智能归档** (`core/dedup.py`)：
   - 自动检测重复游戏版本，支持一键将旧版或重复副本安全归档至 `_Archive_Duplicates` 隔离目录。

---

## 🛠️ 技术栈与依赖

- **后端引擎**：Python 3.10+, FastAPI, Uvicorn, Pydantic v2
- **存储与异步 I/O**：SQLite, aiosqlite
- **网络与解析**：HTTPX, BeautifulSoup4, RapidFuzz
- **前端交互**：现代化响应式 Web 控制台（静态资源位于 `static/`，支持暗色主题）

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
  "mtool_directory": "E:\\ACG\\MTool",
  "proxy": "",
  "auto_scrape": true,
  "scrape_source": "auto",
  "theme": "dark",
  "port": 8000
}
```

> [!NOTE]
> **端口独立说明**：
> `acg_vault` 独占 **`8000`** 端口（另一应用 `offline_ocr_excel` 已调整为 8080 端口），两者可无缝同时运行。若需自定义端口，可在 `data/config.json` 中将 `"port": 8000` 修改为所需端口。

---

## 📁 项目目录结构

```text
acg_vault/
├── config.py             # 全局配置加载与默认设定
├── main.py               # FastAPI 后端路由与 HTTP API
├── requirements.txt      # Python 依赖清单
├── start.bat             # 一键启动批处理脚本
├── run_batch_scrape.py   # 批量命令行元数据刮削辅助脚本
├── core/                 # 核心功能模块
│   ├── scanner.py        # 游戏目录扫描与 RJ 号提取
│   ├── scraper.py        # DLsite / Bangumi 爬虫与元数据抽取
│   ├── ai_scraper.py     # 智能文本清洗与辅助解析
│   ├── launcher.py       # 游戏进程启动器与转区挂钩
│   ├── mz_patcher.py     # RPG Maker 汉化补丁处理引擎
│   └── dedup.py          # 重复游戏比对与归档
├── data/                 # 运行时用户数据目录（配置、封面缓存、数据库）
│   ├── config.json       # 运行时配置文件
│   ├── acg_vault.db      # SQLite 数据库
│   └── covers/           # 封面海报缓存
└── static/               # 前端单页 WebUI 静态资源
```
