#!/usr/bin/env python3
"""真 Kivy 环境校验：mobile/main.py 的 KV 必须能完整构建。

防"KV 引用了 Python 未定义的自定义类 → FactoryException → APK 打开
即闪退"（v1.6.1 事故）回归。mock 冒烟测不出这类问题，必须用真 Kivy
实例化整棵 Widget 树。需要显示环境（CI 用 xvfb-run）。

用法：
  cp panboost.py mobile/panboost.py
  xvfb-run -a python3 dev/check_kv.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("PANBOOST_HOME", "/tmp/panboost_kv_check")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mobile"))

import main as m  # noqa: E402
from kivy.app import App  # noqa: E402
from kivy.factory import Factory, FactoryException  # noqa: E402


def main():
    for cls in ("MainScreen", "DownloadScreen", "AccountsScreen",
                "HistoryScreen", "CardButton", "CompactOption"):
        try:
            Factory.get(cls)
        except FactoryException:
            raise SystemExit(f"FAIL: Factory 找不到 {cls}（会闪退）")

    class _CheckApp(m.PanBoostApp):
        pass

    app = _CheckApp()
    app.shell_version = "check"
    app.dir_short = "/tmp"
    App._running_app = app

    root = m.Builder.load_string(m.KV)

    names = {s.name for s in root.ids.sm.screens}
    assert names == {"home", "download", "accounts", "history", "logs",
                     "files"}, \
        f"屏幕缺失: {names}"

    need = {
        "home": {"pan_grid", "home_status"},
        "download": {"url_input", "cookie_input", "threads_spinner",
                     "insecure_switch", "go_btn", "progress", "status_lbl",
                     "log_lbl"},
        "accounts": {"domain_input", "cookie_input", "accounts_status",
                     "accounts_box"},
        "history": {"history_box", "rec_switch"},
        "logs": {"logs_lbl", "logs_status"},
        "files": {"files_title", "files_info", "files_box",
                  "files_sel_all", "files_dl_btn"},
    }
    for scr, ids in need.items():
        got = set(root.ids.sm.get_screen(scr).ids)
        miss = ids - got
        assert not miss, f"{scr} 屏缺少组件: {miss}"

    for fn in ("record_login", "remove_login", "load_accounts",
               "save_accounts", "start_keepalive", "stop_keepalive"):
        assert hasattr(m, fn), f"缺少模块函数 {fn}"
    for fn in ("on_go", "go", "pan_login", "_after_login", "save_account",
               "del_account", "refresh_accounts", "refresh_history",
               "rerun", "clear_history", "on_rec_toggle",
               "_build_pan_grid"):
        assert hasattr(m.PanBoostApp, fn), f"缺少 App 方法 {fn}"
    assert len(m.PANS) >= 18, "网盘清单不足 18 家"

    # weblogin 静态门禁：真机"卡片点击无反应"根因（颜色 Java int 溢出
    # + UI 线程异步异常静默丢失）CI 无法运行 WebView，靠静态扫描防回归
    import weblogin
    wsrc = Path(weblogin.__file__).read_text(encoding="utf-8")
    # v3.2.2 主 Activity 内 LoginLayer：UI 全在 Java 侧（颜色/文字
    # 编译期类型保证），Python 侧只启动与收结果——启动失败必须同步抛出
    assert "LoginLayer" in wsrc, "未接入 LoginLayer 登录层"
    assert "登录页启动失败" in wsrc, "start 失败未同步抛出（fire-and-forget）"
    assert 'org/panboost/login/LoginLayer$Callback' in wsrc, \
        "回调接口签名异常"
    assert hasattr(weblogin, "open_login") and hasattr(weblogin, "available")
    # 按钮回调必须经 _guard 兜底（异常可见，不静默进 logcat）
    msrc = Path(m.__file__).read_text(encoding="utf-8")
    assert "lambda _b, k=pan" not in msrc and "lambda _b, u=it" not in msrc, \
        "宫格/历史按钮仍有未兜底的裸 lambda 回调"
    assert "_guard" in msrc, "缺 _guard 回调兜底"
    # WebView 失败必须落 crash log 且详情显示到账号页（v1.7.2 事故：
    # 详情写首页状态栏，用户已跳走看不到）
    assert '_dump_crash("weblogin 打开失败' in msrc, \
        "WebView 失败未落 crash log"
    assert "err_txt[:110]" in msrc, "WebView 失败详情未显示到账号页"
    # v1.8.0 分享链接解析集成
    assert hasattr(m.PanBoostApp, "_run_share"), "缺 _run_share 分享分发"
    assert "find_resolver" in msrc, "下载流程未检测分享链接"
    assert "分享链接" in m.KV, "下载屏未提示支持分享链接"

    # v1.8.1 真机修复：桌面 UA（防 302 到下载App引导页）+ 返回能力
    assert "Windows NT" in weblogin.DESKTOP_UA, "桌面 UA 常量异常"
    assert hasattr(weblogin, "request_back"), "缺 request_back（返回键兼容）"
    assert hasattr(weblogin, "close_login"), "缺 close_login（✕ 返回）"
    assert hasattr(m.PanBoostApp, "_on_key"), "缺返回键处理方法 _on_key"
    assert "on_keyboard" in msrc, "返回键未绑定 on_keyboard"
    assert "key != 27" in msrc, "未识别 Android 返回键 keycode 27"
    assert "weblogin.request_back()" in msrc, "返回键未接入登录层处理"
    assert m.SHELL_VERSION == "3.2.5", "壳版本未升级到 3.2.5"

    # v3.2.5 真机"下载结束即闪退"根治门禁：p4a PythonService
    # onDestroy() 有 Process.killProcess(myPid)——服务与主 App 同
    # 进程，stop_keepalive→stopService→onDestroy 即杀全进程
    # （30s 探测超时+开销≈38 秒闪退）。AndroidService 必须根除，
    # 保活只留 PARTIAL_WAKE_LOCK（纯 JNI 无服务生命周期）
    assert "from android import AndroidService" not in msrc, \
        "仍用 AndroidService（onDestroy 杀全进程的闪退雷源）"
    assert '_KEEPALIVE = {"wl": None}' in msrc, \
        "keepalive 状态仍有 svc 字段（服务路径应已移除）"
    assert 'svc' not in msrc.split("def stop_keepalive")[1].split(
        "def load_accounts")[0].replace("stopService", ""), \
        "stop_keepalive 仍有服务停止路径"
    # v3.2.5 MD3 UI 现代化门禁
    kv = m.KV
    assert "⌂ 首页" in kv and "↓ 下载" in kv, \
        "底部导航缺图标+文字（MD3 NavigationBar）"
    assert "radius: [dp(16)]" in kv, "缺激活胶囊指示器（MD3 pill）"
    assert kv.count("radius: [dp(14)]") >= 1, "卡片未升 MD3 大圆角"


    # v1.8.2 真机根治：WebViewClient 导航守卫 + WebView 层返回键 +
    # SDL 返回键 trap + 百度 PC 登录页（v1.8.1 桌面 UA 无效的根因：
    # 无 client 时 intent://market:// 导航逃逸到系统；百度 H5 壳有
    # 100ms 延迟强制跳转脚本）
    # 注：ROOT 是 str（os.path.dirname），拼路径必须 Path(ROOT)
    java_path = Path(ROOT) / "mobile" / "java_classes" \
        / "PanWebViewClient.java"
    assert java_path.exists(), "缺 Java 桥接类 PanWebViewClient.java"
    jtxt = java_path.read_text(encoding="utf-8")
    assert "extends WebViewClient" in jtxt, "桥接类未继承 WebViewClient"
    assert jtxt.count("shouldOverrideUrlLoading") >= 2, \
        "桥接类未覆写双签名 shouldOverrideUrlLoading"
    assert "UrlLoadingCallback" in jtxt, "桥接类缺回调接口"
    spec = (Path(ROOT) / "mobile" / "buildozer.spec").read_text(
        encoding="utf-8")
    assert "android.add_src" in spec and "PanWebViewClient.java" in spec, \
        "spec 未把 Java 桥接类编入 APK（android.add_src）"
    # v3.2.2 架构门禁（LoginLayer + PanMainActivity）：
    # 真机实锤 v3.2.0/v3.2.1 独立 Activity 返回后 Kivy 主循环永不
    # 恢复（applog 停在"打开网页登录"→纯黑卡住）——登录层必须留在
    # 主 Activity 内（addContentView），主 Activity 从不退场
    assert "LoginLayer.java" in spec, "spec 未编入 LoginLayer"
    assert "PanMainActivity.java" in spec, "spec 未编入 PanMainActivity"
    assert "android.add_activities" not in spec, \
        "应已移除独立 Activity 注册（黑屏死路）"
    assert "android.activity_class_name = org.panboost.PanMainActivity" \
        in spec, "主入口未换 PanMainActivity（pyjnius 配置）"
    assert "p4a.extra_args = --android-entrypoint org.panboost.PanMainActivity" \
        in spec, "manifest 主入口未透传（--android-entrypoint）"
    layer_java = Path(ROOT) / "mobile" / "java_classes" / "LoginLayer.java"
    assert layer_java.exists(), "缺 LoginLayer.java（登录层）"
    lsrc = layer_java.read_text(encoding="utf-8")
    assert "addContentView" in lsrc, \
        "登录层未用 addContentView 叠加（主 Activity 不退场的根基）"
    # v3.2.3 真机崩溃修复门禁（日志实锤：SDL 线程构建 →
    # getMainLooper() null → Handler 构造 NPE）：
    # ①start 必须经 runOnUiThread 在 UI 线程构建
    # ②自建 Handler 必须根除（轮询/按钮恢复全 View.postDelayed）
    assert "act.runOnUiThread" in lsrc, \
        "构建未切 UI 线程（SDL 线程构建是 NPE 崩溃根因）"
    assert "startOnUiThread" in lsrc and "closeOnUiThread" in lsrc, \
        "缺 UI 线程专用的构建/关闭方法"
    assert "new Handler(" not in lsrc, \
        "残留自建 Handler（getMainLooper 返回 null 的崩溃路径）"
    assert "Looper.getMainLooper" not in lsrc, \
        "残留 getMainLooper 调用（SDL 线程上部分 ROM 返回 null）"
    assert "build-fail|" in lsrc, \
        "缺构建失败通知（cb.onLoginCancel，Python 状态机悬空防线）"
    assert "wv.postDelayed(sPollRunnable, 3000)" in lsrc, \
        "轮询未挂 View.postDelayed（UI 框架内部 Handler）"
    assert "handleBack" in lsrc, "缺 handleBack（返回键入口）"
    assert "closeLayer" in lsrc, "缺 closeLayer（关闭路径）"
    assert "about:blank" in lsrc, "关闭序列缺 about:blank 清场"
    pan_java = Path(ROOT) / "mobile" / "java_classes" / "PanMainActivity.java"
    assert pan_java.exists(), "缺 PanMainActivity.java（自定义主入口）"
    psrc = pan_java.read_text(encoding="utf-8")
    assert "extends org.kivy.android.PythonActivity" in psrc, \
        "主入口未继承 PythonActivity（Python 启动链断裂）"
    assert "onBackPressed" in psrc, "主入口未接管返回键"
    assert "LoginLayer.handleBack" in psrc, "返回键未接入登录层"
    assert "Window.canvas.ask_update()" in msrc, \
        "缺 on_resume 强制重绘（黑屏兜底防线）"
    assert "setWebViewClient" in lsrc, "未设置 WebViewClient（导航逃逸根因）"
    assert "setUseWideViewPort" in lsrc, "缺宽视口（PC 页无法自适应屏宽）"
    assert "setUserAgentString" in lsrc, "WebView 未设桌面 UA"
    assert "getUserAgentString" in lsrc, "缺 UA 读回验证（下载页诊断）"
    assert "browser_fallback_url" in wsrc, "intent:// 缺 fallback 解析（规格）"
    assert "_decide_url" in wsrc, "缺导航白名单策略 _decide_url"
    ok1, _ = weblogin._decide_url("https://pan.baidu.com/")
    ok2, _ = weblogin._decide_url("market://details?id=x")
    ok3, _ = weblogin._decide_url("")
    assert not ok1 and ok2 and ok3, "_decide_url 行为异常"
    assert m.PAN_BY_KEY["baidu"]["login"] == \
        "https://passport.baidu.com/v2/?login", "百度未用 PC 统一登录页"

    # v1.8.3 真机根治（SDL 源码实锤）：全屏 Dialog 承载登录层 +
    # onPageStarted 导航观测 + 移除 SDL trap。
    # trap=1 时 SDLActivity.onBackPressed() 直接 return 吞掉手势返回
    # （无反应）；Android 10+ 手势不产生键盘事件，Kivy/OnKeyListener
    # 全收不到——唯一系统级可靠路径是 Dialog（手势/返回键自动
    # cancel → OnCancelListener 关层）
    assert 'os.environ.setdefault("SDL_ANDROID_TRAP' not in msrc, \
        "SDL trap 已废弃（v1.8.3 起吞手势返回，必须移除）"
    # v3.2.0：登录层已从 Dialog 弹窗改独立 Activity（用户反馈
    # "登录页不能展示信息"根治）；返回键/手势由 onBackPressed
    # 系统级处理（canGoBack 先退网页再退出）
    assert 'autoclass("android.app.Dialog")' not in wsrc, "Dialog 弹窗承载应已移除（docstring 历史描述除外）"
    assert "onBackPressed" in psrc and "canGoBack" in lsrc, \
        "缺系统返回键处理（主 Activity 接管 + 层内网页后退）"
    assert "onPageStarted" in lsrc and "onPageFinished" in lsrc, \
        "缺导航观测实现（Java 侧）"
    assert "onPageStarted" in jtxt and "onPageFinished" in jtxt, \
        "Java 桥接类缺 onPageStarted/onPageFinished 转发"
    assert "MARKET_PREFIXES" in wsrc, "缺市场 URL 黑名单（302 落地守卫）"
    assert weblogin.MARKET_PREFIXES[0] == "market://", "黑名单常量异常"
    assert "stopLoading" in lsrc, "onPageStarted 守卫未停载市场 URL"
    assert hasattr(weblogin, "nav_log"), "缺 nav_log 导出（真机诊断）"
    assert "_dump_nav_log" in msrc, "导航日志未落盘（诊断证据缺失）"

    # v1.8.4 真机修复（v1.8.3 反馈"三色弹窗无内容 + 点击闪退"）：
    # ① 闪退：_ClickListener 内联创建未持 Python 强引用——pyjnius
    #    官方文档明确 proxy 只存指针不持引用，GC 后 Java 回调必崩
    # ② 三色弹窗：floating 主题 Dialog 被 AOSP PhoneWindow 强制
    #    setLayout(WRAP_CONTENT, WRAP_CONTENT)，WebView 高度塌陷 0
    assert "onRenderProcessGone" in jtxt, \
        "桥接类缺渲染进程崩溃处理（默认杀整个 App）"
    assert "onRenderGone" in jtxt and "onRenderGone" in lsrc, \
        "渲染崩溃处理未接通（Java 侧自动关闭页面）"
    assert "wv.destroy()" in lsrc, "closeLayer 未销毁 WebView（防泄漏）"
    assert "_on_ui" in msrc, "登录回调未调度回 Kivy 主线程（线程安全）"
    assert "Clock.schedule_once" in msrc, "缺 Clock 主线程调度"

    # v1.8.5 真机修复（参考 LinkSwift / netdisk-fast-download 调研）：
    # ① 误记已登录：游客 Cookie 非空 ≠ 已登录——_finish 关层前必须
    #    校验 auth_keys 全部命中（未命中 Toast 提示、层保持打开），
    #    record_login 防御性二次校验
    # ② 三色区域没字：show() 后 setLayout 真机仍被 floating 主题
    #    压回——非 floating 全屏主题构造 Dialog 根治；scheme 拦截
    #    后回退重载登录页防空白屏
    assert "MATCH_PARENT, 0, 1f" in lsrc, \
        "WebView 未用 weight 布局（剩余高度稳占）"
    assert "fallbackAfterBlock" in lsrc, "缺拦截回退（空白屏根因）"
    assert "BLOCKED_HTML" in lsrc, "缺拦截说明页（替代空白屏）"
    assert "未检测到登录凭证" in lsrc, \
        "缺凭证校验（游客 Cookie 误记账根因，Java 侧）"
    assert "Toast.makeText" in lsrc, "Toast 未实现（Java 侧）"
    assert "checkAuth" in lsrc, "缺特征键校验逻辑（Java 侧）"
    # record_login 防御校验 + verified 语义（keys 命中=True / 空=False）
    assert '"verified": bool(keys)' in msrc, \
        "record_login verified 语义错误（特征命中应 True）"
    assert "Cookie已存·未验证" in msrc, "卡片缺未验证三态显示"
    # 特征键抽查（调研实锤）
    assert m.PAN_BY_KEY["quark"]["auth_keys"] == ["__pus", "__puus"], \
        "夸克特征键错误（nfd 实战白名单：__pus 持久 + __puus 签名）"
    assert m.PAN_BY_KEY["uc"]["auth_keys"] == ["__pus", "__puus"], \
        "UC 特征键错误（与夸克共用 UC_QUARK_COOKIE_KEYS 体系）"
    assert "COOKIE_LOGIN_USER" in m.PAN_BY_KEY["tianyi"]["auth_keys"], \
        "天翼缺 COOKIE_LOGIN_USER 特征"
    assert "ESTSAUTH" in m.PAN_BY_KEY["onedrive"]["auth_keys"], \
        "OneDrive 缺 ESTSAUTH 特征"
    assert "lid" in m.PAN_BY_KEY["dropbox"]["auth_keys"], \
        "Dropbox 缺 lid 特征"

    # v1.9.0 真机修复（"三色块无字 + 夸克/阿里下载页 + UC 打不开"）：
    # ① 文字三级保险 + 标准登录页布局（标题栏/提示条/底部大按钮）
    # ② 登录 URL 实锤修正（LinkSwift @match：阿里 /drive、天翼
    #    /web、移动 yun.139.com）
    # ③ 桌面 UA 独立设置 + getUserAgentString 读回验证（整块配置
    #    被吞是"下载页"根因）
    assert 'autoclass("java.lang.String")' in wsrc, \
        "启动参数缺 Java String 通道（pyjnius 重载解析失败防线）"
    assert " · 网页登录" in lsrc, "缺标题栏标题（标准登录页布局）"
    assert "在下方页面登录账号" in lsrc, "缺提示条（操作引导）"
    assert "已完成登录，保存 Cookie" in lsrc, "缺底部完成大按钮文案"
    # v3.2.0：文字/颜色全在 Java 侧（编译期类型保证，pyjnius
    # setText/setTextColor 多重载静默失败通道整体消除）
    assert "setText(" in lsrc and "setTextColor(" in lsrc, \
        "Java 侧缺文字/颜色设置"
    assert m.PAN_BY_KEY["alipan"]["login"] == \
        "https://www.alipan.com/drive/", "阿里登录页仍是宣传页（非 /drive/）"
    assert m.PAN_BY_KEY["tianyi"]["login"] == \
        "https://cloud.189.cn/web/", "天翼登录页非网页版 /web/ 路径"
    assert m.PAN_BY_KEY["yidong"]["login"] == \
        "https://yun.139.com/", "移动登录页仍是旧门户（跳 APP 引导）"

    # v1.9.1 真机根治："登录完成后直接闪退"——关闭登录层时回调
    # 强引用被立即清空，Python GC 后 Chromium in-flight 导航回调
    # 经 Java 桥调用已回收对象 → SIGSEGV。三层防御：①解绑回调源
    # ②退休列表延迟回收 ③dismiss/removeView 兜底
    assert "def _retire" in wsrc, "缺 _retire（退休列表防 GC 闪退）"
    assert '"retired": []' in wsrc, "缺退休列表字段"
    assert "del rl[:-6]" in wsrc, "退休列表缺上限裁剪"
    # v3.2.2：WebView 回调全在 Java 侧（无跨 JNI 飞行回调窗口），
    # 结果回调对象经 _retire 延迟回收；层关闭幂等通知
    assert "notifyCancel" in lsrc and "closeLayer" in lsrc, \
        "缺关闭兜底取消通知（Python 状态机悬空防线）"
    assert "sFinished" in lsrc, "缺一次性回调幂等保护"

    # v1.9.2 真机根治："登录完成后点保存没反应"——凭证校验未通过
    # 时仅靠 Toast（部分真机 ROM 静默失败），登录层保持打开且无
    # 任何可见反馈。修复：按钮文字红色提示（三级保险通道）+
    # Toast 双保险 + Cookie 多域合并采集 + 全链路导航日志埋点
    assert "def _merge_cookies" in wsrc, "缺多域 Cookie 合并（规格）"
    assert "def _gather_cookies" in wsrc, "缺多域采集（规格）"
    assert "def _jstr" in wsrc, "缺 Java String 转换（启动参数通道）"
    assert "cookie_urls=()" in wsrc, "open_login 缺多域参数"
    assert "cookie_urls=" in msrc, "main 未传网盘关联域列表"
    assert "gatherCookies" in lsrc, "Java 侧缺多域 Cookie 采集"
    assert "NUDGE_TXT" in lsrc, "缺按钮红字反馈（无反应根因，Java 侧）"
    assert "def current_cookies(url):" in wsrc, \
        "current_cookies 定义缺失（v1.9.1 曾被误删致点保存必失败）"

    # v2.0.0 结构与 UI 重构 + 统一错误日志：
    # ①applog 模块（app-*.log 按天轮转 7 天 + ring + 全局异常钩子）
    # ②五屏 UI（新增日志屏）+ 底部导航 5 Tab 高亮
    # ③登录/下载/账号/异常全链路埋点
    applog_path = Path(ROOT) / "mobile" / "applog.py"
    assert applog_path.exists(), "缺统一日志模块 mobile/applog.py"
    asrc = applog_path.read_text(encoding="utf-8")
    for fn in ("def init", "def log", "def info", "def warn", "def error",
               "def tail", "def ring_raw", "def cleanup",
               "def install_hooks"):
        assert fn in asrc, f"applog 缺 {fn}"
    assert "threading.excepthook" in asrc, "applog 缺子线程异常钩子"
    assert "import applog" in msrc, "main 未接入统一日志"
    assert "applog.init" in msrc and "applog.install_hooks" in msrc, \
        "main 缺日志初始化与钩子安装"
    assert msrc.count("applog.") >= 15, "埋点不足（登录/下载/账号/异常）"
    assert "class NavTab" in msrc, "缺底部导航 Tab 类"
    assert "class LogsScreen" in msrc, "缺日志屏类"
    for key in ("tab_home", "tab_download", "tab_accounts",
                "tab_history", "tab_logs"):
        assert key in m.KV, f"底部导航缺 {key}"
    assert "id: sm" in m.KV, "KV 缺 ScreenManager id（root 布局重构）"
    assert "name: 'logs'" in m.KV and "id: logs_lbl" in m.KV, \
        "日志屏未挂载"
    assert hasattr(m.PanBoostApp, "refresh_logs"), "缺 refresh_logs"
    assert hasattr(m.PanBoostApp, "_cur"), "缺 _cur（root 布局适配）"
    assert 'self.root.ids.sm.get_screen(name)' in msrc, \
        "_scr 未适配新 root 结构"
    assert "self.root.current" not in msrc, "残留旧 root.current 直访"
    assert "139.com" in m.PAN_BY_KEY["yidong"]["domains"], \
        "移动 Cookie 域缺 139.com（新域名匹配不到）"

    # v2.0.1 登录完成闪退防御（真机回归修复）：
    # ①on_done/on_cancel 回调线程零工作零 IO（磁盘日志全部挪入
    #   延迟调度——Android UI 线程不被拖在关闭链里，dismiss 后
    #   Chromium 迟到 IPC 窗口不再被撞开）
    # ②_on_ui_later 延迟 0.25s：解绑+dismiss+退休完全落地后才
    #   做任何 Kivy 操作
    # ③_after_login 整体 try 兜底（Clock 回调异常杀主循环=闪退）
    assert hasattr(m, "_on_ui_later"), "缺 _on_ui_later 延迟调度"
    assert "Clock.schedule_once(lambda _dt: fn(), delay)" in msrc, \
        "_on_ui_later 未带延迟参数"
    assert '_dump_crash("_after_login' in msrc, "_after_login 缺兜底"
    assert "_on_ui_later(\n                    lambda: self._after_login" \
        in msrc, "on_done 未走延迟调度"
    assert "def _ui():" in msrc and "_on_ui_later(_ui)" in msrc, \
        "on_cancel 未走延迟调度"
    i_on_done = msrc.find("def on_done(cookie, auto):")
    i_later = msrc.find("_on_ui_later", i_on_done)
    assert i_on_done >= 0 and i_later > i_on_done, "on_done 结构异常"
    seg201 = msrc[i_on_done:i_later]
    assert "applog." not in seg201 and "_dump_nav_log" not in seg201, \
        "on_done 回调线程仍有 IO（v2.0.1 必须零工作）"

    # v2.1.0 已登录直入浏览模式 + 会话竞态总闸：
    # ①已登录卡片 open_browse 带 Cookie 直开网页版文件页（不再
    #   二次打开登录层——poller 首轮特征命中秒关层与 Chromium
    #   启动竞争即真机"已登录点卡片闪退"根因）
    # ②_STATE.session 会话总闸：一切迟到回调按会话校验忽略
    # ③poller 首轮延迟 3s
    wsrc = Path(ROOT).joinpath("mobile", "weblogin.py").read_text(
        encoding="utf-8")
    assert "def open_browse" in wsrc, "weblogin 缺浏览模式"
    assert '"session": 0' in wsrc and '_STATE["session"] += 1' in wsrc, \
        "weblogin 缺会话总闸"
    # v3.2.0：poller 在 Java 侧（Handler postDelayed），首轮 3s
    # 防秒关页与启动渲染竞争的语义在 LoginActivity 落实
    assert "wv.postDelayed(sPollRunnable, 3000)" in lsrc, \
        "poller 缺首轮延迟（渲染竞争防线，View.postDelayed）"
    assert "BROWSE_BTN" in lsrc and "bool(browse)" in wsrc, \
        "浏览模式按钮/分支缺失"
    for p in m.PANS:
        assert p.get("home"), f"{p['key']} 缺 home（网页版文件页）"
    assert hasattr(m.PanBoostApp, "_open_browse"), "缺 _open_browse"
    assert "weblogin.open_browse(" in msrc, "pan_login 未分流浏览模式"
    assert "进入我的网盘" in msrc, "已登录卡片缺入口文案"

    # v3.0.0 YunX 式体验（分享文件列表勾选下载 + 剪贴板 + 公共目录）：
    # ①分享解析不再直接全量下载——先进文件列表屏勾选，
    #   「下载所选」才批量加速（用户核心诉求）
    # ②剪贴板识别：复制分享链接回 App 自动填入
    # ③下载输出优先公共 Download/PanBoost（文件管理器可见）
    assert "class FilesScreen" in msrc, "缺文件列表屏类"
    assert "name: 'files'" in m.KV and "id: files_box" in m.KV, \
        "文件列表屏未挂载"
    assert "id: files_dl_btn" in m.KV and "id: files_sel_all" in m.KV, \
        "文件屏缺操作按钮"
    for fn in ("_show_share_files", "_run_share_batch",
               "start_selected_downloads", "toggle_all_files",
               "_toggle_file", "_on_resume", "download_dir"):
        assert (hasattr(m.PanBoostApp, fn)
                or fn == "download_dir" and "def download_dir" in msrc), \
            f"缺 {fn}"
    assert "def download_dir" in msrc, "缺公共下载目录函数"
    assert "getExternalStoragePublicDirectory" in msrc, \
        "未优先公共 Download 目录"
    assert "Path(download_dir()) / _safe_name" in msrc, \
        "下载输出未走公共目录"
    assert "_on_ui(lambda: self._show_share_files(" in msrc, \
        "分享解析未分流到文件列表屏"
    assert "Clipboard.get" in msrc and "find_resolver(txt)" in msrc, \
        "剪贴板识别缺失"
    assert "on_release: app.toggle_all_files()" in m.KV, \
        "全选按钮未绑定"
    assert "on_release: app.start_selected_downloads()" in m.KV, \
        "下载所选按钮未绑定"

    # v3.0.1 手势修复（真机"触碰就选中"）：滑动与选择分离，
    # 对标 YunX combinedClickable 的 tap 判定——位移超阈值取消
    # 点击、让给 ScrollView 滚动。Kivy Button 的 collide 判定在
    # 滚动时行随内容移动仍命中（误触根因），已弃用
    assert "class FileRow" in msrc, "缺自研 tap 手势行控件"
    assert "<FileRow>:" in m.KV, "FileRow 缺 KV 视觉规则"
    assert "scroll_distance: dp(12)" in m.KV, "滚动阈值未调优"
    assert 'touch.ud["pb_filerow"]' in msrc, "缺 tap 起点记录"
    assert "<= dp(8)" in msrc, "缺 touchSlop 位移阈值判定"
    assert "on_release=self._guard(self._toggle_file" not in msrc, \
        "仍用 Button on_release（滚动误触根因）"
    assert "on_tap=self._guard(self._tap_row" in msrc, \
        "行未接 tap 回调"

    # v3.1.0 原生网盘浏览（夸克 Web API + 原生 FileRow 列表，
    # 根治 WebView PC 网页"一碰就选中、无滑动"）
    assert "import drive" in msrc, "缺网盘浏览 API 层"
    for fn in ("_browse_drive", "_fetch_drive", "_render_drive",
               "_tap_row", "files_back", "_run_drive_batch"):
        assert hasattr(m.PanBoostApp, fn), f"缺 {fn}"
    assert "drive.SUPPORTED" in msrc, "未按网盘分流原生浏览"
    assert "drive.list_files" in msrc, "未调网盘列表 API"
    assert "drive.get_download_url" in msrc, "未调网盘直链 API"
    assert "on_release: app.files_back()" in m.KV, \
        "文件屏返回未绑定 files_back"
    assert "📁" in msrc, "缺文件夹行视觉"
    dsrc = Path(ROOT).joinpath("mobile", "drive.py").read_text(
        encoding="utf-8")
    assert "drive-pc.quark.cn" in dsrc, "drive 层缺夸克 API 端点"
    assert "Set-Cookie" in dsrc, "缺 __puus Cookie 保活合并"
    # v3.2.4 真机"拉取文件列表失败"（连接层即炸）根因：Android 上
    # 无系统 CA bundle 路径，urlopen 默认 HTTPS 验证失败——引擎
    # 自己接了 certifi 所以下载一直正常，drive 层此前漏接
    assert "def _ssl_ctx" in dsrc, "drive 层缺 SSL 上下文（CA 修复）"
    assert "certifi.where()" in dsrc, "未用 certifi CA（Android 无系统 CA）"
    assert "ssl._create_unverified_context" in dsrc, \
        "缺不验证回退（与引擎同一信任模型）"
    assert dsrc.count("context=_ssl_ctx()") == 2, \
        "列表/直链两处请求未全接 SSL 上下文"

    # 浅色主题断言：页面底色接近白（亮度>0.9）
    r, g, b, _a = m.BG
    assert r > 0.9 and g > 0.9 and b > 0.9, f"非浅色底: {m.BG}"
    kv = m.KV
    assert "rgba: 0.957, 0.965, 0.984, 1" in kv, "缺浅色底绘制"
    assert "RoundedRectangle" in kv, "卡片缺圆角绘制"

    spinner = root.ids.sm.get_screen("download").ids.threads_spinner
    from kivy.uix.spinner import SpinnerOption
    assert issubclass(spinner.option_cls, SpinnerOption), \
        f"option_cls 非法: {spinner.option_cls}"
    vals = [str(v) for v in spinner.values]
    assert "512" in vals and "1024" in vals, f"线程选项缺失: {vals}"

    def _walk(w):
        out = []
        for c in w.children:
            out.append(c)
            out.extend(_walk(c))
        return out

    spinner._build_dropdown()
    opts = [w for w in _walk(spinner._dropdown)
            if isinstance(w, SpinnerOption)]
    assert len(opts) == len(vals), \
        f"下拉构建失败: {len(opts)}/{len(vals)}"

    print("check_kv: OK")


if __name__ == "__main__":
    main()
