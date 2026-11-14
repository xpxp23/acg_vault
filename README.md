# 🎮 ACG Vault v3.3.0 (本地 ACG 游戏资产、Switch 日间主题、手柄大屏模式、AI 攻略、游戏内穿透悬浮伴侣、可视化改档与数据馆藏中心)

一款专为本地 ACG / Galgame / 同人游戏爱好者打造的殿堂级全功能游戏库管理系统。基于 **FastAPI + SQLite (WAL) + Vue 3 + PyWebView 原生桌面封装** 架构，提供本地游戏目录增量极速扫描、DLsite / Bangumi / Steam / VNDB 四源元数据与竖版海报智能刮削、多源日/英标签自动汉化归一、OpenAI 兼容大模型（DeepSeek / Qwen / Ollama）智能语义清洗与工程解包全结局攻略生成、**正统 Nintendo Switch (Horizon OS) 日间/夜间双模式 + 5 套高定强调色 + Web Audio 合成微音效引擎**、**手柄化 10 英尺大屏模式**、`Alt+G` 游戏内无边框毛玻璃 + `Alt+T` 鼠标穿透锁定伴侣小窗（支持穿透状态下 60fps 滚轮无感翻页）、`F12` 实机截图 + 官方商店预览图双画廊、RPG Maker 可视化在线改档器（Save Editor）、跨引擎 AppData 存档自动映射 + WebDAV 云端同步、动态智能合集以及一键导出年度/月度馆藏长图的数据馆藏看板。

---

## 🩹 v3.3.0 穿透提示去重

- 锁定穿透时原本会同时出现「常驻蓝色横幅」和「红色操作提示」，内容重复且挤占一行版面。
- 现在只保留红色提示（几秒后自动收起），穿透状态改为在**底部状态栏**显示
  「🔒 已穿透 · 滚轮可翻页 · Alt+G 解锁」，不占额外空间也不丢状态。
- 顺带清理了废弃的 `.hud-lock-banner` 样式。

---

## 🌟 v3.3.0 殿堂级交互重构与全链路痛点根治

### 1. 🎨 强调色引擎重构与 Alpha 透明度通道保留（痛点 1 根治）
- **根因回顾**：旧版 `static/theme-accent.css` 将 `.bg-indigo-500/10` ~ `/40`、`.bg-indigo-600/20` 等半透明微光工具类全部硬编码映射为 `100%` 不透明的 `var(--ax-500)` / `var(--ax-600)`，导致夜间模式下半透明徽章变成刺眼纯色块、日间模式下出现“暗红底配褐红字”的对比度灾难。
- **架构重构**：
  - 为 **任系霓虹红 (`nintendo`)、电光靛蓝 (`indigo`)、赛博翠绿 (`emerald`)、鎏金琥珀 (`amber`)、幻想紫罗兰 (`violet`)** 5 套预设主题色引入完整的 `--ax-300-rgb` / `--ax-400-rgb` / `--ax-500-rgb` / `--ax-600-rgb` / `--ax-950-rgb` 通道；
  - 严格保留 `.bg-indigo-500/10` ~ `/85`、`.bg-indigo-600/20` ~ `/80`、`.border-indigo-500/20` ~ `/60` 的真实 Alpha 透明度阶梯；
  - 接管 `.from-indigo-500` / `.from-indigo-600` / `.to-indigo-500` 渐变变量与发光阴影，使整站按钮、胶囊、焦点环随强调色丝滑联动。

### 2. ☀️ 正统 Nintendo Switch (Horizon OS) 日间模式与攻略 Markdown 全量重塑（痛点 2 & 3 根治）
- **纯正 Switch Horizon OS 色彩体系**：主画布采用标志性哑光浅灰 `#EBEBEB`，次级工作区采用 `#F2F2F2`，游戏卡片与弹层采用纯净 `#FFFFFF`，分割线采用 `#DCDCDC`，正文采用高对比碳黑 `#2D2D2D`。
- **标志性双环青蓝呼吸焦点框 (`#00C3E3`)**：桌面端卡片悬停（`.game-card:hover` / `.glass-card:hover`）与大屏模式手柄聚焦（`.card.is-focused .card-cover`）时，呈现 Switch 原生风格的内圈 `2px` 纯白间隔 + 外圈 `4px` `#00C3E3` 亮青蓝双环呼吸脉冲边框（`@keyframes switchFocusPulse`）与微弹浮起动效。
- **日间模式攻略 Markdown (`.notes-markdown-body`) 杂志级排版**：
  - **修复加粗文字隐形**：`.notes-markdown-body strong` 设为深邃碳黑 `#111827` 并带微妙青蓝荧光底纹，彻底告别白底白字隐形；
  - **修复剧透折叠块黑底**：`<details>` / `<summary>` 改为清爽纯白卡片配 `#00C3E3` 青蓝左边框与 `#008BA3` 标题；
  - **区分行内代码与多行代码块**：行内 `:not(pre) > code` 采用柔和浅红胶囊，多行 `pre code` 采用 `#F4F6F8` 清爽浅灰面板配深色等宽字体，不再整片变红；
  - **离线 Mermaid 路线图日间适配**：`.mermaid-flow-container` 在日间模式下呈现白底青蓝节点与清晰条件胶囊。
- **大屏模式 (`bigscreen.html`) 日间模式全选择器修复**：精确覆盖 `.bs-root`、`.bs-backdrop .bg-veil`、`.bs-top`、`.brand-title`、`.hero-title`、`.rail-head h2`、`.card-cover`、`.card-caption`、`.bs-hints`、`.hint .key`、`.bs-detail .detail-veil`、`.bs-sheet`、`.bs-reader`、`.reader-body`。
- **内置 Switch Horizon OS 合成微音效引擎 (`ACGTheme.playSfx`)**：基于零外部依赖的 Web Audio API 实时合成 `'focus'`（清脆木琴棘轮声）、`'select'`（双音确认声）、`'back'`（返回声）、`'launch'`（启动三和弦）、`'lock'` / `'unlock'`（伴侣窗锁定/解锁音效），支持在设置中随时开关。

### 3. 🪟 伴侣悬浮窗 (`Alt+G` / `Alt+T`) 穿透锁定、高 DPI 对齐与 60fps 滚轮翻页（痛点 5, 6, 7 根治）
- **痛点 7 修复（穿透锁定后滚轮翻页失效）**：
  - **根因**：`WH_MOUSE_LL` 低级鼠标钩子的 `lParam` 是指向 `MSLLHOOKSTRUCT` 结构体的内存指针，旧代码误将指针地址直接拿来做 `(l_param >> 16) & 0xFFFF` 位移，导致提取出的永远是内存地址随机数而非滚轮增量；且在钩子回调内同步调用 `evaluate_js` 会阻塞 GUI 线程。
  - **修复**：定义标准 `_MSLLHOOKSTRUCT` 结构体，通过 `ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents.mouseData` 准确提取高 16 位有符号滚轮增量；引入 `_wheel_dispatch_worker` 异步派发线程 + `threading.Event`，钩子回调内仅做 O(1) 累加并立即返回 `1`（吞掉滚轮消息防止底层游戏画面缩放），后台线程以 60fps 合并调用 `window.__acgScrollBy(pxDelta)`，支持攻略、清单、F9 透视、游戏截图与随手记全面板顺滑滚动。
- **痛点 6 修复（解锁按钮高 DPI 错位、遮挡与闪烁）**：
  - 锁定/解锁按钮固定为 `78×24px`，移除会导致 `getBoundingClientRect()` 在过渡中途测量失真的宽高 `transition-all`；
  - `reportUnlockChip` 乘上 `window.devicePixelRatio` 换算为物理像素，并在 `desktop_app.py` 中使用 `HWND_TOPMOST` + `SWP_NOACTIVATE` 精确贴合，彻底消除初始 `112×40` 黑块遮挡右上角最小化/关闭按钮的问题。
- **痛点 5 修复（状态横幅与切换逻辑）**：
  - 伴侣窗顶栏下方新增常驻穿透状态横幅（`🔒 鼠标穿透已锁定 · 点击直达下层游戏，滚轮仍可翻页`）并动态展示用户配置的解锁快捷键；
  - 当传入新的 `game_id` 呼出伴侣窗时，自动切换目标游戏并保持伴侣窗开启，不再误关窗口；
  - 新增攻略 Checklist 复选框按 `game_id` 自动持久化至 `localStorage` 与后端数据库双重同步。

### 4. 🖥️ 桌面壳层、多显示器拖拽与性能细节打磨
- **多显示器拖拽还原不跳屏**：`win_restore_for_drag` 改用 `GetSystemMetrics(76/77/78/79)` (`SM_X/Y/CX/CYVIRTUALSCREEN`) 虚拟桌面边界钳制坐标，副屏最大化窗口拖拽还原丝滑跟手。
- **彻底消除 CMD 黑窗**：新增 `start_silent.vbs` 零黑框静默启动脚本，优化 `start.bat` 与 `start_desktop.bat`，并在 `_open_browser_overlay` 中注入 `CREATE_NO_WINDOW` 标志。
- **大屏与主界面细节修复**：修复 `bigscreen.html` 中 `ref="detailTextEl"` 绑定名使详情页手柄上下滚动简介恢复正常；补齐 `windowbar.js` 中大屏各全屏层的顶部无边框标题栏偏移；优化 `app.js` 的 `refreshIcons()`（仅当存在未转换图标时通过 `requestIdleCallback` 渲染）；为 `index.html` 的 `boot-error-box` 增加 `window.__ACG_BOOTED` 挂载守卫。

---

## 🩹 历史版本更新摘要 (v2.4 ~ v3.1.1)

- **v3.1.1**：修复 64 位 Windows 下 `WH_MOUSE_LL` 回调 `argtypes` 缺失导致的 `OverflowError` 日志刷屏问题，引入 `_CappedLogStream` 日志大小上限保护。
- **v3.1.0**：新增 5 套强调色模板初版；修复 `win_set_bounds` 下 WebView2 子窗口未随宿主窗口同步重排的问题。
- **v3.0.0**：引入日间/夜间双主题架构与伴侣窗独立解锁小窗机制。
- **v2.8.0 ~ v2.9.1**：内置 6 套 Magpie 缩放预设一键切换、无边框窗口八向拖拽缩放、最大化拖拽还原、PyInstaller `onedir` 独立应用打包与退出防重入保护。
- **v2.6.0 ~ v2.7.0**：推出手柄优先的 10 英尺大屏模式 (`/bigscreen`)、Magpie 全屏自动接管集成、MTool 软链注入进程柔性追踪计时。
- **v2.4.0 ~ v2.5.0**：推出 XInput → 键盘手柄桥接（专为 RPG Maker MV/MZ/RGSS/WOLF 打造）、MTool 32/64 位 Hook 自动匹配、跨引擎 AppData 存档探测、RPG Maker 可视化在线改档器 (`Save Editor`) 与离线可视化 Mermaid 攻略路线图。

---

## 🚀 启动与使用说明

### 1. 一键启动（零黑框桌面应用模式 / 服务端模式）

- **完全零黑框静默启动（推荐）**：双击运行 `start_silent.vbs` 或 `start_desktop.bat`（自动通过 `wscript` + `pythonw` 启动原生无边框桌面窗口与系统托盘，全程无任何命令行黑框闪烁）。
- **标准桌面启动**：双击运行 `start.bat`。
- **纯服务端模式**：运行 `python main.py` 或 `start.bat --server`，随后访问 `http://127.0.0.1:8000`。

```bash
# 安装依赖
pip install -r requirements.txt

# 启动原生桌面端 (支持 Alt+Space 老板键、Alt+G 伴侣小窗与 Alt+T 鼠标穿透锁定)
python desktop_app.py
```

### 2. 大屏模式（沙发 / 电视 / 手柄）

- 主界面顶栏点击 **「大屏模式」**，或按 **`Alt+B`**，也可直接访问 `http://127.0.0.1:8000/bigscreen`。
- 手柄：`A` 详情 / 详情内启动，`B` 返回（**长按 B 退出大屏**），`X` 收藏，`Y` 操作面板（可一键切换 Switch 日间/夜间主题与 Magpie 预设），`LB/RB` 切栏目，`LT/RT` 整屏翻页，`Start` 筛选与设置，`Back` 切换纯网格。
- 键盘等价：`方向键 / WASD` 移动，`Enter` 确认，`Esc` 返回，`F` 收藏，`R` 更多，`Q/E` 切栏目，`Tab` 筛选，`PageUp/PageDown` 翻页。
