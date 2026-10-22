# PanBoost 功能补齐路线（ROADMAP）

> 定位纠偏：**换技术栈 ≠ 拆项目**。v3.2.8（Kivy 版）的全部功能面必须在
> 原生栈（Kotlin + Compose）上等价或更强地回归。本表为逐项审计与
> 回补计划；每项完成即划掉。

## 事故记录

- v4.0~v4.3 启动即闪退（2026-10-22 实锤根因）：namespace `org.panboost.app`
  与源码包 `org.panboost` 失配 + Manifest 相对类名 `.MainActivity` →
  解析出不存在的类。修复于 v4.3.1（全限定名 + scripts/verify_apk.py
  启动链门禁——组件类必须在 dex 中逐一校验存在）。

## 审计基线

- 旧版：v3.2.8（Kivy/p4a 终版，commit 46bae60）
- 新版：v4.1.x（原生，模块化架构已就位）

## 差距清单（按用户价值排序）

### P0 —— 核心体验缺失（YunX 式主链路）

| # | v3.2.8 功能 | v4.1.1 现状 | 回补方案 | 状态 |
|---|---|---|---|---|
| 1 | **分享链接解析**（夸克/123/蓝奏三网盘自动分发）→ 勾选批量下载 | ✅ 三网盘 | CompositeShareRepository 分发 | ✅ v5.0.0 |
| 2 | **剪贴板识别**：复制分享链接回 App 自动填入 | ✅ | 进分享屏 LaunchedEffect 检测（不覆盖已输入） | ✅ v4.2.0 |
| 3 | **URL 直链高级下载**：粘贴任意直链 | ✅ 基础（8 线程分块） | UA 回退/挑战 Cookie 后续 | 🟡 v5.0.0 |
| 4 | **网盘多账号管理**：账号页账簿（已登录徽标/删除/重新登录） | ✅ | :feature:accounts（18 网盘宫格/徽标/删除）+ MultiPanCookieStore | ✅ v4.3.0 |
| 5 | **多网盘支持**（v3.2.8 = 18 家） | 🟡 清单/登录/粘贴已通（18 家可登录存 Cookie）；浏览下载仅夸克 | UC/百度等逐家接浏览下载 API（UC 与夸克同源优先） | 待做 |
| 6 | **手动粘贴 Cookie 路径**（WebView 登录失败时的兜底） | ✅ | 账号页粘贴对话框（保存即验证徽标） | ✅ v4.3.0 |

### P1 —— 可靠性与可观测性

| # | 功能 | 现状 | 方案 | 状态 |
|---|---|---|---|---|
| 7 | **全局崩溃捕获**（crash-*.log 可取回） | ❌ | CrashReporter（UncaughtExceptionHandler → 外部私有目录） | ✅ v4.1.1 |
| 8 | **应用日志屏**（app-*.log 按天轮转 + 环形缓冲） | ✅ | :core:logging + :feature:logs（500 条环+7 天轮转） | ✅ v5.0.0 |
| 9 | **下载历史**（永久记录/开关/失败重跑） | ✅ | DownloadHistoryStore（JSON 200 条）+ :feature:history | ✅ v5.0.0 |
| 10 | **实时速度显示**（KB/s / MB/s） | ✅ | Worker SpeedTracker 滑动窗口 | ✅ v5.0.0 |

### P2 —— 引擎能力（Kivy 引擎 panboost.py 对标）

| # | 功能 | 现状 | 方案 | 状态 |
|---|---|---|---|---|
| 11 | **auto 线程数**（实测测速自动选 16~1024） | 固定 8 | 分块探针测速（首 2 块耗时 → 线程数） | 待做 |
| 12 | **拟人化请求头**（PersonaKit：UA/Referer 随机化防风控） | ❌ | OkHttp 拦截器加 persona 变体 | 待做 |
| 13 | **挑战页 Cookie 自动通过**（浏览器验证挑战） | ❌ | 探测 403/挑战页 → WebView 静默过验证 → 重试 | 待做 |
| 14 | **续传控制文件**（.pbctrl 崩溃一致性） | part 文件粒度 | 现方案够用（合并校验大小） | ✅ 等价 |

### P3 —— 体验细节

| # | 功能 | 现状 | 方案 | 状态 |
|---|---|---|---|---|
| 15 | 五屏导航（首页宫格/下载/账号/历史/日志） | ✅ 五 Tab + logs 路由 | M3 NavigationBar | ✅ v5.0.0 |
| 16 | 下载完成通知点击跳转 | 前台通知无内容 Intent | PendingIntent → MainActivity 深链 download 屏 | 待做 |

## 架构不变量（回补时必须守住）

- 零存储权限（MediaStore 正统路径）
- 单 Activity + Compose Navigation
- MVI 单一 UiState + Intent
- 模块边界：feature → domain ← data/network
- 每版 CI 门禁：R8 保真 + 零权限扫描 + assembleRelease
