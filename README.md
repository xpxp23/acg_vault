# 🎮 ACG Vault v3.1.1 (本地 ACG 游戏资产、手柄大屏模式、AI 攻略、游戏内穿透悬浮伴侣、可视化改档、手柄化 RPG Maker 与数据馆藏中心)

一款专为本地 ACG / Galgame / 同人游戏爱好者打造的殿堂级全功能游戏库管理系统。基于 **FastAPI + SQLite (WAL) + Vue 3 + PyWebView 原生桌面封装** 架构，提供本地游戏目录增量极速扫描、DLsite / Bangumi / Steam / VNDB 四源元数据与竖版海报智能刮削、多源日/英标签自动汉化归一、OpenAI 兼容大模型（DeepSeek / Qwen / Ollama）智能语义清洗与工程解包全结局攻略生成、**手柄化 10 英尺大屏模式**、`Alt+G` 游戏内无边框毛玻璃 + `Alt+T` 鼠标穿透锁定伴侣小窗、`F12` 实机截图 + 官方商店预览图双画廊、RPG Maker 可视化在线改档器（Save Editor）、跨引擎 AppData 存档自动映射 + WebDAV 云端同步、动态智能合集以及一键导出年度/月度馆藏长图的数据馆藏看板。

---

## 🩹 v3.1.1 滚轮钩子崩溃修复

- **现象**：`data/desktop.log` 短时间内涨到 **137MB**，内容是刷屏的 `ctypes.ArgumentError: argument 4: OverflowError: int too long to convert`。
- **根因**：`WH_MOUSE_LL` 回调里 `CallNextHookEx(0, nCode, wParam, lParam)` 没声明 `argtypes`，64 位下 `lParam` 是 8 字节，ctypes 按 C int 转换溢出 → **每个鼠标事件抛一次异常**并写一条 traceback。
- **修复**：给 `SetWindowsHookExW` / `CallNextHookEx` / `GetCursorPos` / `GetWindowRect` 全部声明 `argtypes/restype`（`LRESULT = c_ssize_t`），回调内部再包一层 try/except；滚轮转发按 40ms 合并，避免高频 `evaluate_js` 冲掉 pywebview 的回调表（会报 `win_get_state.<id> is not a function`）。
- **兜底**：`data/desktop.log` 改为 `_CappedLogStream`，超过 8MB 自动截断，任何循环刷屏都不会再写爆磁盘。

---

## 🎨 v3.1.0 强调色自定义 + 伴侣窗几何修复

### 强调色模板
- 设置 → 外观 新增 5 个色板：**任天堂红 / 靛蓝（原色）/ 翡翠绿 / 琥珀金 / 紫罗兰**，夜间与日间同时生效。
- 实现：`theme-accent.css` 定义整套 `--ax-50…950`，再把页面里全部 `indigo` 色阶类映射成 `var(--ax-N)`；日间模式走镜像色阶（`600→600` 实心按钮保持、`300→700` 文字压深），夜间走原色阶。存在 `config.json` 的 `ui_accent`。

### 伴侣窗错位 / 点不动
- 根因：`win_set_bounds` 用 `SetWindowPos` 只改宿主窗口，**WebView2 子窗口不会跟着重排**，于是页面停留在旧尺寸 → 内容左移被裁、右侧露出窗口底色，且点击坐标与 DOM 错位（看起来"点不动"）。
- 修复：改走 pywebview 的 `window.move()` + `window.resize()`（WinForms 的 Location/Size），并用 `GetWindowRect - GetClientRect` 动态算出 DWM 边框差值，把「可见尺寸」换算成 `Form.Size`。子窗口随之同步，缩放/显示都不再错位。
- 实测：500×720 → 700×760 直接调用，内容填满无裁切；点击 F9 标签页正常切换。

---

## 🌗 v3.0.0 日间模式（Switch 风格）+ 伴侣窗交互

### 日间模式
- 原来的深色配色 = **夜间模式**；新增 **Switch 风格日间模式**：`#ebebeb` 浅灰画布、纯白圆角卡片、深灰文字、**任天堂红 #e60012** 作为强调色（替换原来的靛蓝）。
- 实现方式是「浅色覆盖层」：`static/theme-light.css` 用 `html[data-theme="light"]` 前缀把用到的 276 个 Tailwind 颜色类**按色阶镜像**（950↔50、300↔700…），并覆盖 `style.css` 的玻璃拟态变量与 `.glass-panel/.glass-card/.drawer-panel` 等自定义组件；大屏模式走它自己的 `:root` 变量。夜间模式零改动。
- 主题存储在 `config.json` 的 `ui_theme`（`auto`/`dark`/`light`），首次默认跟随系统。
- **四个入口**：标题栏右侧 ☀/🌙 按钮、设置 → 外观 三选卡、大屏 Y 面板「界面主题」、伴侣窗标题栏（同一个按钮组件）。
- 首帧前内联脚本先读 localStorage 定色，避免刷新时闪白/闪黑。

### 伴侣窗交互
- **解锁按钮并入「已穿透」位置**：锁定后原来的穿透按钮缩成 40×22 的小锁，视觉上就在原位；由于整窗 `WS_EX_TRANSPARENT` 后自身点不到，实际由一个小窗**精确盖在该位置**接管点击（不透明度跟随面板设置），点一下即解锁。穿透横幅已移除，不再挤占版面。
- **锁定后仍可滚轮浏览**：`WH_MOUSE_LL` 全局钩子只在锁定状态生效，光标落在伴侣窗内时把滚轮换算成 `scrollTop` 转发给页面并**吞掉事件**（避免同时缩放游戏）；光标在窗外原样放行。

---

## 🔧 v2.9.1 伴侣窗内容错位修复

现象：伴侣窗被拉宽后，内容整体向左上偏移，标题栏和左侧文字被裁掉一截（看起来像页面被滚动了）。

根因：`win_set_bounds` 直接对窗体 `SetWindowPos`，但 **WebView2 子窗口的 bounds 没跟着同步**，于是它停在旧尺寸/旧位置，内容相对窗体产生 (-40,-30) 这类偏移。

修复：
1. `win_set_bounds` 末尾再调一次 pywebview 自己的 `window.resize()`，让 WebView2 的 bounds 跟着更新；
2. 每次显示伴侣窗都重新套一遍保存的几何，并做一次 `SWP_FRAMECHANGED + RedrawWindow(ALLCHILDREN)` 强制重排（自愈，不用手动拖一下）；
3. 页面补 `html, body { height:100%; overflow:hidden }`，`#overlay-app` 改 `height:100%`，彻底堵死根滚动。

---

## 🪄 v2.9.0 窗口交互 & 伴侣窗重构

### 窗口
- **八向缩放**：上下左右四条边 + 四个角都能拖动改尺寸（原来只有右下角）。走 `SetWindowPos` 一次设置 x/y/w/h，拖左边/上边时窗口位置同步移动，不会闪。
- **拖到顶部最大化**：把标题栏拖到屏幕上沿松开即最大化，和 Windows 一致。
- 顺手修掉了「创建尺寸 ≠ 可见尺寸」的 16×39 偏差——现在启动时用 `SetWindowPos` 精确还原上次几何，缩放/重启都不会再漂移。
- 窗口句柄改为「标题前缀 + 本进程」匹配并缓存：WebView2 加载完会把窗口标题改成 `<title>`，以前用完整标题 `FindWindow` 会失效。

### 伴侣窗（四处硬伤）
1. **穿透状态不同步**：解锁后横幅/按钮还显示"已穿透"。现在 Python 侧改完状态会 `evaluate_js` 直接推给页面，另有 1.2 秒轮询兜底。
2. **穿透时无法解锁**：整窗 `WS_EX_TRANSPARENT` 后连自己都点不到。新增一个独立的**「🔓 解锁穿透」小窗**（120×36，置顶、不穿透），跟随伴侣窗右上角出现，点一下即解锁。
3. **没有滚动条 / 滚轮无效**：根因是 `#overlay-app` 是 Vue 的挂载容器，写在它身上的 `:class="overlay-shell"` 根本不会被处理——`height:100vh`、flex、`--overlay-alpha` 全部没生效，页面被内容撑到 8300px。现在把壳移进容器内部，并给滚动区补了 `min-height:0`。
4. **透明度无效**：同样因为 CSS 变量没生效，而且窗口本身不透明。改为 Win32 分层窗口 `SetLayeredWindowAttributes`，滑块直接改整窗 alpha（与穿透共用同一套样式，互不覆盖）。

---

## 🪟 v2.8.2 窗口行为修复

1. **最大化 → 关闭到托盘 → 从托盘点出来，变成窗口态**：`Window.restore()` 会把 `FormWindowState` 设成 `Normal`，等于把最大化悄悄降级。现在从托盘恢复只在**真最小化**时 `SW_RESTORE`，最大化状态会重新 `SW_MAXIMIZE` 断言回来。
2. **按钮指示与实际状态脱节 / 拖不动**：`win_get_state` 改为直接读 Win32 的 `IsZoomed`，不再依赖内部标志位；前端在 `focus` / `visibilitychange` 时同步按钮图标，外部用 Win+↑ 改变状态也能跟上。
3. **Windows 式拖拽**：最大化时拖动标题栏会先还原成窗口，并让光标保持标题栏上的相对位置，然后无缝继续拖（新增 `win_restore_for_drag`）。
4. **去掉标题栏的啰嗦提示**（"拖动此条移动窗口 · 双击最大化"），只保留彩点 + 标题。

---

## 🩹 v2.8.1 修复

**退出时偶发 .NET 崩溃弹窗**（`Failed to create Python type for ExceptionDispatchInfo` / 「堆栈空间不足」）：

- 根因是**重入递归**：`_clean_shutdown()` 在 `FormClosing` 事件里同步调用 `window.destroy()`，销毁窗口又触发一次 `FormClosing` → 再进 `_clean_shutdown` → 无限递归，栈溢出；pythonnet 在栈溢出后再构造异常类型，就抛出前面那条 `ExceptionDispatchInfo` 错误。
- 修复：退出流程改为**幂等 + 不销毁窗口**——加 `_shutting_down` 重入锁，`FormClosing` 里只置标志位，然后由独立线程延时 `os._exit(0)`；托盘 `stop()` 也放到独立线程（避免在自己的菜单回调里死锁）。
- 实测：`minimize_to_tray=false` 点关闭 → 1.1 秒干净退出、无错误对话框；`minimize_to_tray=true` → 正常隐藏、进程存活、无对话框。

---

## 🎛 v2.8.0 Magpie 预设 & 独立应用化

### Magpie 一键预设

内置 6 套缩放预设，设置页点卡片即切换，详情抽屉与**大屏 Y 面板**也能一键切（手柄按 A 循环）：

| 预设 | 模式 | 适合 |
|---|---|---|
| 动画 / 立绘 | Anime4K | 2D 立绘、动画风，线条干净 |
| 像素 / RPG | Integer Scale 2x | 像素游戏、RPG Maker，整数倍不糊边 |
| 通用锐利 | Lanczos | 传统插值，保留锐利边缘 |
| 3D / 性能 | FSR | 3D 游戏，开销低 |
| 复古 CRT | CRT-Geom | 扫描线 / 曲面，老游戏味道 |
| 兼容捕获 | Desktop Duplication + Lanczos | Graphics Capture 抓不到画面时用 |

实现要点：Magpie **只在启动时读配置**，运行中改文件不生效，退出时还会用内存里的旧配置覆盖（已实测）——所以切换预设 = `taskkill` 等进程真正退出 → 写 `%LOCALAPPDATA%\Magpie\config4\config.json` → 重新 `-st` 拉起；如果切换前正在全屏，会自动对当前游戏重新触发一次。写盘前会留 `.json.bak`。

### 独立应用化

- **图标**：新增 `static/icon.png` / `icon.ico`（1024 多尺寸），窗口标题栏、任务栏、exe 全部使用；并通过 `SetCurrentProcessExplicitAppUserModelID` 让 Windows 任务栏把它当独立应用而不是 python.exe。
- **不再常驻 CMD**：`start.bat` 改为 `start "" pythonw ...` 后立即退出；若存在 `ACGVault.exe` 则优先启动它。
- **独立可执行文件**：`ACGVault\ACGVault.exe`（PyInstaller **onedir** + windowed，无控制台、**启动零解包**）。程序在 `ACGVault\` 子目录里，数据仍在项目根 `data/`——和源码共用同一份库；把整个 `ACGVault\` 文件夹单独拷走，它就会在自己目录下建 `data/` 变成便携版。
- **重新打包**：双击 `build_exe.bat`（参数已写在脚本里）。onedir 冷启动约 1.3 秒（实测到 API 可用），不像 onefile 每次都要把 56MB 解包到 `%TEMP%`。
- `sys.stdout` 为空的 windowed 环境下会自动把输出重定向到 `data/desktop.log`，避免第一个 print 就崩。

---

## 🖥 v2.7.0 Magpie 全屏集成

把 [Magpie](https://github.com/Blinue/Magpie)（GPLv3 的窗口放大工具）接进馆藏：不支持全屏、或内置全屏很糊的游戏，可以一键用 Anime4K / FSR / Lanczos 放大到全屏。

1. **三个入口**：游戏详情抽屉的「Magpie 全屏」按钮、大屏模式 Y 操作面板、设置页「Magpie 全屏」区块（状态 / 路径 / 自动策略 / 延迟 / 手动测试）。
2. **接入方式**：Magpie 没有"缩放指定窗口"的命令行，但它把全局热键注册在窗口类 `Magpie_Hotkey` 的消息窗口上，而该窗口的 WndProc 处理 `WM_HOTKEY` 时不校验消息来源——`PostMessage(hwnd, WM_HOTKEY, 0, 0)` 等价于按一次「缩放」热键。
3. **安全流程**：按 PID（含子进程）找游戏主窗口 → 强制置前台并**轮询确认**焦点真的在游戏上 → 才投递热键 → 再轮询检测 Magpie 缩放窗口（可见 + 置顶 + 面积 ≥ 80% 屏幕）。找不到热键窗口、或前台不是游戏窗口时一律取消，绝不会把馆藏自己的窗口给缩了。
4. **大屏自动全屏**：大屏模式启动游戏时请求体带 `source=bigscreen`，后端按设置决定是否调度。等待逻辑不是死等：**进程出现 → 游戏窗口出现 → 再等 N 秒**（默认 8s，可调 3–30s），所以 MTool 注入花 20 秒也不会踩空。
5. **设置项**：`magpie_enabled` / `magpie_path`（留空自动探测，含游戏目录同级扫描）/ `magpie_autostart`（需要时 `Magpie.exe -st` 拉起托盘）/ `magpie_auto_scale` / `magpie_auto_scope`（`bigscreen` 或 `always`）/ `magpie_auto_delay`。
6. 只调用本机已安装的 Magpie.exe，不打包、不分发其代码。

---

## 🧩 v2.6.3 修复

1. **全局自定义标题栏**：窗口按钮从页面头部挪进一条**永远置顶**的独立标题栏（z-index 高于攻略全屏层 / 大屏模式 / 伴侣窗），所以任何页面、任何全屏状态下都能拖动、最小化、最大化、关闭；窄窗口（<1100px）也稳定可见。
2. **修复最大化后窗口跑到屏幕外**：WinForms 对 `FormBorderStyle.None` 窗口做 Maximize 时会保留原 Location，导致窗口半屏越界。改为 `ShowWindow(SW_MAXIMIZE / SW_RESTORE)` 交给系统处理，实测还原为 (0,0,1920,1080) 且能正确回到最大化前的尺寸。
3. **修复窗口尺寸每次重启缩水**：pywebview 的创建尺寸与 `GetWindowRect` 的可见尺寸存在 DWM 外框差值，之前把可见尺寸存回配置导致每次启动都小一圈。现在持久化的是「我们请求的尺寸」。
4. **关闭按钮不再报错**：所有窗口 API 用 `_safe_api` 包了一层，异常不再抛回 JS（避免前端弹未处理异常横幅），统一落盘到 `data/desktop_error.log`；`/api/client_log` 也写同一个日志，方便下次直接定位。
5. **补装 `pystray`**：此前这台机器没装托盘库，`minimize_to_tray` 实际不生效，点关闭会直接退出进程——看起来就像「点了关闭就报错/闪退」。现在关闭会正常隐藏到托盘。
6. **伴侣窗点击切换**：已打开时再点「伴侣小窗」（或按 Alt+G）就是关闭，接口返回的提示也会区分「已呼出 / 已关闭」。
7. 大屏模式空库时显示空状态而不是一片空白。

---

## 🛠 v2.6.2 修复

1. **伴侣悬浮窗彻底复活**（这才是它「完全没法用」的真因，两个叠加的坑）：
   - **坑一**：`python desktop_app.py` 启动时本文件是 `__main__`，而 `main.py` 里的 `from desktop_app import show_or_toggle_overlay_window` 会把同一文件**再导入一份全新模块副本**，那份副本的 `_overlay_window` 永远是 `None` —— 所以按 Alt+G 永远走 Edge 回退窗口（没有置顶、每按一次新开一个、穿透作用在错误的 HWND 上），窗口最小化/恢复也一直是假成功。现在启动时把 `desktop_app` 别名指向 `__main__`，全进程只有一份窗口状态。
   - **坑二**：这台机器 **pywebview 根本没装**（只有 pythonnet），整个桌面端一直在跑 Edge `--app` 回退。已装回 `pywebview 6.2.1` 并锁到 requirements。
   - 伴侣窗现在是真的 HUD：`frameless + on_top + hidden` 原生 WebView2 窗口，单例切换、置顶常驻、无边框、可拖动、可调整大小、记忆位置尺寸，`Alt+T` 穿透时 Win32 样式真正落在它自己的 HWND 上。
2. **无边框主窗口**：去掉系统标题栏，顶栏空白处可拖动窗口、双击最大化，右上角自绘「最小化 / 最大化 / 关闭」，右下角有缩放柄，窗口位置与尺寸跨重启记忆。设置页新增「无边框窗口」开关（关闭后重启生效）。
3. **攻略工作台顶栏按钮被挤成竖排**：给「启动游戏 / 伴侣小窗」按钮加 `shrink-0 + whitespace-nowrap`，标题区改为 `flex-1 + truncate`，长日文标题不会再挤压按钮。
4. 大屏模式顶栏与伴侣窗头部同步接入窗口控制；`pywebview.start(private_mode=False, storage_path=...)`，否则 localStorage（大屏设置、攻略布局记忆）每次重启都会丢。

---

## 🔧 v2.6.1 修复

1. **MTool 联动启动终于能正确计时**：MTool 会把游戏软链/复制到 `C:\Users\Public\MTool_Game_Tmp\<hash>\` 并改名成 `MTool_Game.exe` 再注入。旧逻辑只按「游戏目录 + 数据库里的 exe 名」找进程，路径和名字两个条件全不满足，`mtool*.exe` 还在忽略名单里——于是永远抓不到 PID，玩多久都是 0 秒。现改为**解析 `与工具一同启动.bat` 拿到真实注入目标**，再按多名字（`MTool_Game.exe` / 原 exe）+ 多目录（临时软链目录 / 游戏目录 / 工作目录）匹配，并覆盖「复制工具到游戏」模式。同时修掉「等不到进程也硬记 120 秒」的计时污染。
2. **大屏模式向上翻回顶部**：焦点回到第一条轨道时页面滚回顶部，Hero 重新出现，不再把轨道顶到屏幕上沿。
3. **大屏模式补全鼠标退出路径**：顶栏新增「✕ 退出大屏」，底部提示条所有按键提示均可点击，详情页 / 攻略阅读页 / 设置面板都补了可点击的关闭按钮。
4. **攻略全屏默认纯净阅读**：`notes_default_layout` 默认改为 `last`（记住上次使用的布局，首次为纯净阅读），设置页新增「自动（记住上次使用的布局）」选项。

---

## ✨ v2.6 升级亮点

1. 📺 **大屏模式（Big Screen Mode）：手柄优先的 10 英尺影院 UI** (`/bigscreen`, `static/bigscreen.*`)：
   - **独立页面**而非主界面遮罩层，焦点系统、手柄事件与主界面的键盘快捷键、详情抽屉彻底解耦；也能单独开成第二个窗口丢到电视上。
   - **Hero + 横向轨道 + 全部网格**三段式布局：继续游玩 / 今晚玩什么（加权随机，只从没通关的作品里抽）/ 我的收藏 / 最近入库 / 智能合集 / 全部作品。选中项实时驱动全屏高斯模糊背景，并给「背景强度」三档开关（封面画质参差时可以关掉）。
   - **原生 Gamepad API 输入**：`navigator.getGamepads()` 逐帧轮询，Xbox 与 DualShock / DualSense 同时可用（后端 XInput 通道只认 Xbox 兼容设备，PS 手柄会被漏掉，所以这里不走后端）。自动按 `gamepad.id` 切换 ✕○□△ / ABXY 符号，并提供「确认键位置」独立开关（下方键 / 右侧键）。
   - **完整键盘等价物**：方向键 / WASD、Enter、Esc、F、R、Q/E、Tab、Backspace，没有手柄也能全流程操作与调试。
   - **启动即退场**：按 A 启动游戏后窗口自动最小化，轮询到进程退出后自动还原大屏并弹出「本次游玩约 N 分钟」结算提示；长按 A 可用普通模式强制启动一次。
2. ⏱️ **修复 MTool 启动不计游玩时长** (`core/launcher.py`)：
   - 旧实现只给「12×0.4s + 6×1s」两段硬超时，MTool 注入器拉起游戏本体一旦超过 11 秒，会话就在第一轮轮询里被判定结束——玩了 3 小时只入库 11 秒。现改为**柔性等待**（`attach_timeout` 默认 120s）+ 会话状态机（`attaching → running`），注入耗时也计入这一局。
   - 提权进程读不到镜像路径时按**进程名兜底**匹配，避免 MTool 以管理员注入后 `pid=None`；同一根因连带修好了 MTool 模式下手柄转发、F12 截图、`Alt+G` 定位全部失靶的问题。
   - `/api/games/running` 新增 `phase` / `attached` 字段，前端可区分「注入中」与「运行中」。

---

## ✨ v2.5 升级亮点

1. 🎮 **手柄支持（XInput → 键盘桥接，RPG Maker 专项优化）** (`core/gamepad.py`)：
   - RPG Maker MV/MZ 基于 NW.js/Chromium，只监听键盘、完全不认 Gamepad API；XP/VX/VX Ace 的 RGSS 同样只读键盘。本版内置零依赖 XInput 桥接：按引擎自动切换键位（MV/MZ 用 `Z/X/Shift`，RGSS 用 `C/B/Shift`，WOLF 用 `Z/X`），左摇杆带死区、按住即持续移动。
   - **只喂给游戏**：仅当通过本库启动的游戏窗口在前台时才转发按键，切出、退出游戏或关闭开关都会立即松开所有按键，不会在浏览器/聊天窗里乱按方向键。
   - 设置页提供实时输入自检（按键点亮 + 摇杆数值）、死区调节、可视化改键，并可为运行中的单个游戏单独指定方案。
2. 🔧 **MTool 联动启动修复：按位数选 hook + 托管「与工具一同启动.bat」** (`core/mtool_link.py`, `core/launcher.py`)：
   - 旧实现固定注入 `mzHook.dll`（64 位），而 RPG Maker MV 默认 `Game.exe` 是 32 位（本库 81 个 MV 中 76 个），64 位 DLL 注入 32 位进程会**静默失败**——游戏与 MTool 各自启动、互不关联。本版改为读 PE 头判定 32/64 位，再按引擎选 `mzHook32.dll` / `mzHook.dll` / `RGSSHook.dll` / `RGSSHook64.dll` / `wolfHook.dll`。
   - 优先复用 MTool 生成的 `与工具一同启动.bat`；缺失或不一致（旧 MTool 路径、位数不符）时自动重建并保留 `.bak`；同时维护 `Tool/gameLaunchs/<md5(小写完整路径)>` 记录，让 MTool 面板一侧也认得该游戏。
   - 启动后枚举游戏进程模块，校验 hook DLL 是否真的载入，把「已关联 / 未关联」直接回报到界面提示；新增只读诊断接口 `GET /api/games/{id}/mtool_diagnose`。

---

## ✨ v2.4 重大升级与深度优化亮点

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

### 2. 大屏模式（沙发 / 电视 / 手柄）

- 主界面顶栏点击 **「大屏模式」**，或按 **`Alt+B`**，也可直接访问 `http://127.0.0.1:8000/bigscreen`。
- 手柄：`A` 详情 / 详情内启动，`B` 返回（**长按 B 退出大屏**），`X` 收藏，`Y` 操作面板，`LB/RB` 切栏目，`LT/RT` 整屏翻页，`Start` 筛选与设置，`Back` 切换纯网格。
- 键盘等价：`方向键 / WASD` 移动，`Enter` 确认，`Esc` 返回，`F` 收藏，`R` 更多，`Q/E` 切栏目，`Tab` 筛选，`PageUp/PageDown` 翻页。
- 首次连接手柄若未识别，先按一下手柄任意键（Chromium 需要一次用户手势才会暴露设备）。

