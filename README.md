# 🎮 ACG Vault v2.3 (本地 ACG 游戏资产、AI 攻略、游戏内悬浮伴侣与数据馆藏中心)

一款专为本地 ACG / Galgame / 同人游戏爱好者打造的殿堂级全功能游戏库管理系统。基于 **FastAPI + SQLite (WAL) + Vue 3 + PyWebView 原生桌面封装** 架构，提供本地游戏目录增量极速扫描、DLsite / Bangumi / Steam / VNDB 四源元数据与竖版海报智能刮削、多源日/英标签自动汉化归一、OpenAI 兼容大模型（DeepSeek / Qwen / Ollama）智能语义清洗与工程解包全结局攻略生成、`Alt+G` 游戏内半透明置顶伴侣小窗、`F12` 实机截图 + 官方商店预览图双画廊、100% 全 CG 回想存档一键注入、游玩退出增量存档快照 + WebDAV 云端同步、动态智能合集以及一键导出年度/月度馆藏长图的数据馆藏看板。

---

## ✨ v2.3 核心特性与升级亮点

1. 🪟 **游戏内悬浮攻略小窗 (`Alt+G` 伴侣模式)** (`desktop_app.py`, `static/overlay.html`)：
   - 依托 PyWebView + Win32 全局热键架构，在全屏游玩时无需切出桌面，按下 `Alt+G` 即可在屏幕边缘呼出半透明置顶（Always-on-Top）的迷你「全结局攻略 & F9 变量速查 & 随手记」伴侣小窗。
   - 支持实时勾选结局 `- [ ]` Checklist、检索 RPG Maker `System.json` 内部开关与变量 ID 编号、调节窗口透明度以及一键抓拍截图/备份存档。
2. 🏷️ **多源标签自动汉化归一词典** (`data/l10n_tags_zh.json`, `db/database.py`)：
   - 内置轻量级日/英/繁中 ACG 标签归一化映射表与噪音清洗词典，刮削入库时自动将 DLsite 日文标签（如 `おっぱい`、`純愛`、`寝取られ`）与 VNDB 英文标签（如 `Pure Love`、`Netorare`）统一映射为标准简体中文标签，并提供全库已有标签一键汉化归一。
3. 🖼️ **详情页「官方商店预览 + 个人实机截图」双画廊体验** (`core/scraper.py`, `static/index.html`)：
   - 刮削 DLsite、Steam、VNDB 时自动缓存 3~4 张官方商店预览图（Sample CG），与玩家游戏内按 `F12` 抓拍的实机截图共同构成双画廊体验。
   - **「个人通关笔记」与「全结局攻略」独立拆分**：将随手记录的个人通关便签（`user_notes`）与长篇结构化全结局攻略（`walkthrough_md`）拆分为独立存储与专属 UI 模块，已有历史笔记平滑无损归入全结局攻略。
4. ☁️ **游玩退出自动增量存档快照 + WebDAV 跨设备云备份** (`core/launcher.py`)：
   - 当监听到游戏进程退出且单次游玩时长 `>= 5 分钟` 时，自动打包生成带时间戳的滚动存档快照（默认保留最近 5 份防坏档）。
   - 支持挂载坚果云 / Alist / Nextcloud 等标准 WebDAV 服务，实现跨设备存档双向同步。
5. 🗂️ **动态智能合集（Smart Collections）与馆藏回顾长图导出** (`db/database.py`, `static/app.js`)：
   - 支持创建基于多维规则（引擎、汉化状态、评分、攻略、标签、游玩时长）的动态智能合集与手动精选合集。
   - 数据馆藏看板新增 **一键导出年度/月度 ACG 游玩总结高清长图 (PNG)**，离线纯前端 Canvas 2x 高分屏渲染。

---

## 🚀 启动与使用说明

### 1. 一键启动（桌面应用模式 / 无黑框模式）

- **标准桌面启动**：双击运行 `start.bat`（自动启动 `desktop_app.py`）。
- **无命令行黑框静默启动**：双击运行 `start_desktop.bat`（通过 `pythonw` 启动原生桌面窗口与系统托盘）。
- **纯服务端模式**：运行 `python main.py` 或 `start.bat --server`，随后访问 `http://127.0.0.1:8000`。

```bash
# 安装依赖
pip install -r requirements.txt

# 启动原生桌面端 (支持 Alt+Space 老板键与 Alt+G 游戏内攻略伴侣小窗)
python desktop_app.py
```
