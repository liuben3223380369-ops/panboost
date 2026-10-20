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
    assert names == {"home", "download", "accounts", "history", "logs"}, \
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
    assert "setBackgroundColor(0x" not in wsrc, \
        "颜色字面量未经 _jcolor（Java int 溢出，真机静默炸点）"
    assert "setTextColor(0x" not in wsrc, \
        "颜色字面量未经 _jcolor（Java int 溢出，真机静默炸点）"
    assert "def _jcolor" in wsrc, "缺 _jcolor 符号转换"
    assert "opened_evt" in wsrc, "UI 挂载结果未确认回传（fire-and-forget）"
    assert "步骤[" in wsrc, "挂载缺分步自检（失败无法定位步骤）"
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
    assert "setUserAgentString(DESKTOP_UA)" in wsrc, \
        "WebView 未设桌面 UA（移动 UA 被网盘跳下载客户端页）"
    assert "Windows NT" in weblogin.DESKTOP_UA, "桌面 UA 常量异常"
    assert "setUseWideViewPort" in wsrc, "缺宽视口（PC 页无法自适应屏宽）"
    assert hasattr(weblogin, "request_back"), "缺 request_back（返回键）"
    assert hasattr(weblogin, "close_login"), "缺 close_login（✕ 返回）"
    assert "canGoBack" in wsrc, "返回键缺网页后退语义"
    assert "返回首页" in wsrc, "缺 ✕ 返回首页按钮"
    assert hasattr(m.PanBoostApp, "_on_key"), "缺返回键处理方法 _on_key"
    assert "on_keyboard" in msrc, "返回键未绑定 on_keyboard"
    assert "key != 27" in msrc, "未识别 Android 返回键 keycode 27"
    assert "weblogin.request_back()" in msrc, "返回键未接入登录层处理"
    assert m.SHELL_VERSION == "2.0.0", "壳版本未升级到 2.0.0"

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
    assert "setWebViewClient" in wsrc, "未设置 WebViewClient（导航逃逸根因）"
    assert "setOnKeyListener" in wsrc, "WebView 未挂返回键监听（抢焦点）"
    assert "_UrlLoadingCallback" in wsrc, "缺导航回调 Python 实现"
    assert "_BackKeyListener" in wsrc, "缺 WebView 返回键监听实现"
    assert "browser_fallback_url" in wsrc, "intent:// 缺 fallback 解析"
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
    assert "android.app.Dialog" in wsrc, "登录层未改全屏 Dialog 承载"
    assert "setOnCancelListener" in wsrc, "Dialog 未挂取消监听（手势返回）"
    assert "setCancelable(True)" in wsrc, "Dialog 未设可取消"
    assert "dialog.dismiss()" in wsrc, "关闭未走 Dialog.dismiss"
    assert "_CancelListener" in wsrc, "缺 _CancelListener 实现"
    assert "DialogInterface$OnCancelListener" in wsrc, \
        "取消监听接口签名异常"
    assert "onPageStarted" in wsrc and "onPageFinished" in wsrc, \
        "缺导航观测回调实现"
    assert "onPageStarted" in jtxt and "onPageFinished" in jtxt, \
        "Java 桥接类缺 onPageStarted/onPageFinished 转发"
    assert "MARKET_PREFIXES" in wsrc, "缺市场 URL 黑名单（302 落地守卫）"
    assert weblogin.MARKET_PREFIXES[0] == "market://", "黑名单常量异常"
    assert "stopLoading" in wsrc, "onPageStarted 守卫未停载市场 URL"
    assert hasattr(weblogin, "nav_log"), "缺 nav_log 导出（真机诊断）"
    assert "_dump_nav_log" in msrc, "导航日志未落盘（诊断证据缺失）"

    # v1.8.4 真机修复（v1.8.3 反馈"三色弹窗无内容 + 点击闪退"）：
    # ① 闪退：_ClickListener 内联创建未持 Python 强引用——pyjnius
    #    官方文档明确 proxy 只存指针不持引用，GC 后 Java 回调必崩
    # ② 三色弹窗：floating 主题 Dialog 被 AOSP PhoneWindow 强制
    #    setLayout(WRAP_CONTENT, WRAP_CONTENT)，WebView 高度塌陷 0
    assert '"click_cbs"' in wsrc, "按钮点击回调未持强引用（GC 后闪退）"
    assert "click_close, click_done" in wsrc, "两个按钮回调未存元组"
    assert "setLayout(-1, -1)" in wsrc, \
        "Dialog 未显式全屏（floating 主题默认 wrap，WebView 塌陷）"
    assert "onRenderProcessGone" in jtxt, \
        "桥接类缺渲染进程崩溃处理（默认杀整个 App）"
    assert "onRenderGone" in jtxt and "onRenderGone" in wsrc, \
        "渲染崩溃回调未接通 Python 侧"
    assert "_on_ui" in msrc, "登录回调未调度回 Kivy 主线程（线程安全）"
    assert "Clock.schedule_once" in msrc, "缺 Clock 主线程调度"

    # v1.8.5 真机修复（参考 LinkSwift / netdisk-fast-download 调研）：
    # ① 误记已登录：游客 Cookie 非空 ≠ 已登录——_finish 关层前必须
    #    校验 auth_keys 全部命中（未命中 Toast 提示、层保持打开），
    #    record_login 防御性二次校验
    # ② 三色区域没字：show() 后 setLayout 真机仍被 floating 主题
    #    压回——非 floating 全屏主题构造 Dialog 根治；scheme 拦截
    #    后回退重载登录页防空白屏
    assert "Theme_Light_NoActionBar_Fullscreen" in wsrc, \
        "Dialog 未用非 floating 全屏主题构造（wrap 根因仍在）"
    assert "android.R$style" in wsrc, "缺系统主题常量引用"
    assert "LLParams(-1, 0, 1.0)" in wsrc, \
        "WebView 未用 weight 布局（wrap 窗口下 MATCH_PARENT 塌陷 0）"
    idx_add = wsrc.find('_step("WebView入容器"')
    idx_load = wsrc.find('_step("加载登录页"')
    assert 0 < idx_add < idx_load, "loadUrl 必须在 addView 之后（未 attach 不渲染）"
    assert "def _toast" in wsrc, "缺 Toast 提示（凭证校验失败反馈）"
    assert "_fallback_after_block" in wsrc, "缺拦截回退（空白屏根因）"
    assert "_BLOCKED_HTML" in wsrc, "缺拦截说明页（替代空白屏）"
    assert 'f"未检测到{title}的登录凭证' in wsrc, \
        "_finish 缺凭证校验（游客 Cookie 误记账根因）"
    assert "Toast.makeText" in wsrc, "Toast 未实现"
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
    assert "def _set_text" in wsrc, "缺文字三级保险（真机按钮无字根因）"
    assert 'autoclass("java.lang.String")' in wsrc, \
        "文字设置缺 Java String 回退（pyjnius 重载解析失败通道）"
    assert "def _set_text_color" in wsrc, "缺文字颜色双保险"
    assert "Color.rgb" in wsrc, "缺 Color.rgb 回退（int 转换失败通道）"
    assert " · 网页登录" in wsrc, "缺标题栏标题（标准登录页布局）"
    assert "在下方页面登录账号" in wsrc, "缺提示条（操作引导）"
    assert "已完成登录，保存 Cookie" in wsrc, "缺底部完成大按钮文案"
    assert "C_DONE_BG" in wsrc and "C_BAR_BG" in wsrc, "缺集中配色常量"
    assert "getUserAgentString" in wsrc, "缺 UA 读回验证（下载页诊断）"
    assert "setUserAgentString(DESKTOP_UA)" in wsrc, "UA 独立设置缺失"
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
    assert "setWebViewClient(None)" in wsrc, \
        "关闭前未解绑 WebViewClient（飞行回调闪退根因）"
    assert "setOnKeyListener(None)" in wsrc, "关闭前未解绑返回键监听"
    assert "setOnCancelListener(None)" in wsrc, "关闭前未解绑取消监听"
    assert "del rl[:-6]" in wsrc, "退休列表缺上限裁剪"

    # v1.9.2 真机根治："登录完成后点保存没反应"——凭证校验未通过
    # 时仅靠 Toast（部分真机 ROM 静默失败），登录层保持打开且无
    # 任何可见反馈。修复：按钮文字红色提示（三级保险通道）+
    # Toast 双保险 + Cookie 多域合并采集 + 全链路导航日志埋点
    assert "def _merge_cookies" in wsrc, "缺多域 Cookie 合并"
    assert "def _gather_cookies" in wsrc, "缺多域采集（漏关联域 Cookie）"
    assert "def _nudge_button" in wsrc, "缺按钮文字反馈（无反应根因）"
    assert "def _jstr" in wsrc, "缺 Java String 转换（Toast 双保险）"
    assert "_jstr(msg)" in wsrc, "Toast 未走双保险通道"
    assert "C_ERR" in wsrc and "DONE_BTN_TEXT" in wsrc, \
        "缺提示配色/文案常量"
    assert '_STATE["btn_done"]' in wsrc, "保存按钮未入强引用状态"
    assert "cookie_urls=()" in wsrc, "open_login 缺多域参数"
    assert "cookie_urls=" in msrc, "main 未传网盘关联域列表"
    assert '("click"' in wsrc, "缺点击埋点（真机诊断）"
    assert '("check"' in wsrc, "缺校验结果埋点"
    assert "已有Cookie键=" in wsrc, "校验日志缺 Cookie 键名记录"
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
