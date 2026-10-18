# 🎮 ACG Vault v2.4 (本地 ACG 游戏资产、AI 攻略、游戏内穿透悬浮伴侣、可视化改档与数据馆藏中心)

一款专为本地 ACG / Galgame / 同人游戏爱好者打造的殿堂级全功能游戏库管理系统。基于 **FastAPI + SQLite (WAL) + Vue 3 + PyWebView 原生桌面封装** 架构，提供本地游戏目录增量极速扫描、DLsite / Bangumi / Steam / VNDB 四源元数据与竖版海报智能刮削、多源日/英标签自动汉化归一、OpenAI 兼容大模型（DeepSeek / Qwen / Ollama）智能语义清洗与工程解包全结局攻略生成、`Alt+G` 游戏内无边框毛玻璃 + `Alt+T` 鼠标穿透锁定伴侣小窗、`F12` 实机截图 + 官方商店预览图双画廊、RPG Maker 可视化在线改档器（Save Editor）、跨引擎 AppData 存档自动映射 + WebDAV 云端同步、动态智能合集以及一键导出年度/月度馆藏长图的数据馆藏看板。

---

## ✨ v2.4 重磅升级与深度优化亮点

1. 🎨 **Collector's UI 2.4 视觉降噪与卡片底部「智能信息槽」** (`static/style.css`, `static/index.html`, `static/app.js`)：
   - **左上角一体式毛玻璃胶囊**：彻底重塑卡片左上角徽章，采用圆角毛玻璃胶囊 + 引擎语义色彩编码，并将「攻略 (`📖`) / 随手记 (`📝`)」整合为胶囊内轻量微图标，把封面下半部分 100% 留给角色立绘。
   - **底部动态智能信息槽**：当 `user_rating > 0` 时展示金色星级；未评分（`user_rating === 0`）时自动切换展示前 2 个汉化标签微胶囊（如 `#纯爱 #魔物娘`）或累计游玩时长（`⏱ 6.2h`），告别满屏暗灰空心星。
2. 🪟 **伴侣悬浮窗 (`Alt+G`) 进阶：毛玻璃 + Win32 鼠标穿透锁定 (`Click-Through HUD`)** (`desktop_app.py`, `static/overlay.html`)：
   - 新增 Win32 `WS_EX_LAYERED | WS_EX_TRANSPARENT` 鼠标穿透锁定开关（按钮或全局热键 `Alt+T`）：开启后伴侣窗半透明固定在全屏游戏上方展示全结局 Checklist 与离线可视化 Mermaid 路线图，鼠标点击直接穿透至底层游戏窗口，按 `Alt+G` 或 `Alt+T` 随时解锁交互。
   - 增量状态轮询优化：8 秒轮询仅在 `updated_at` 发生变化时更新攻略 DOM，彻底解决阅读时 `<details>` 剧透折叠框被自动重置的问题。
3. 🛠️ **跨引擎 AppData 存档自动映射 & RPG Maker 可视化存档修改器 (`Save Editor`)** (`core/save_editor.py`, `core/launcher.py`)：
   - **跨引擎存档探测**：除游戏目录内 `save/` 外，自动识别 Unity（`%USERPROFILE%\AppData\LocalLow\<Company>\<Product>`，支持解析 `*_Data/app.info`）、Ren'Py（`%APPDATA%\RenPy\`）与 Kirikiri 存档目录，让退出自动快照与 WebDAV 云同步覆盖全引擎。
   - **RPG Maker 可视化改档面板**：纯 Python 直接解包与重编码 `.rpgsave`（LZString Base64）与 `.rmmzsave`（Zlib/Pako），在详情抽屉提供可视化的「持有金币 / 角色等级与 HP / 核心好感度变量 / 剧情与回想开关」在线修改器，修改前自动创建防坏档备份。
4. ⚡ **全链路性能与逻辑深度修复**：
   - 运行时翻译补丁 (`translation_patch.js` v2.4) 引入 6000 条目 `Map` 缓存，彻底消除 RPG Maker 60fps `drawText` 正则替换掉帧；
   - 扫描器翻译字典校验改为 64KB 切片嗅探，避免大体积 JSON 全量反序列化阻塞；
   - 新增「移出库自动加入扫描忽略名单」与「已归档重复版本一键恢复至主库」闭环管理。

---

## 🚀 启动与使用说明

### 1. 一键启动（桌面应用模式 / 无黑框模式）

- **标准桌面启动**：双击运行 `start.bat`（自动启动 `desktop_app.py`）。
- **无命令行黑框静默启动**：双击运行 `start_desktop.bat`（通过 `pythonw` 启动原生桌面窗口与系统托盘）。
- **纯服务端模式**：运行 `python main.py` 或 `start.bat --server`，随后访问 `http://127.0.0.1:8000`。

```bash
# 安装依赖
pip install -r requirements.txt

# 启动原生桌面端 (支持 Alt+Space 老板键、Alt+G 伴侣小窗与 Alt+T 鼠标穿透锁定)
python desktop_app.py
```
