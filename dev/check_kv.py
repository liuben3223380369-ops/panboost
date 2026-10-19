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

    names = {s.name for s in root.screens}
    assert names == {"home", "download", "accounts", "history"}, \
        f"屏幕缺失: {names}"

    need = {
        "home": {"pan_grid", "home_status"},
        "download": {"url_input", "cookie_input", "threads_spinner",
                     "insecure_switch", "go_btn", "progress", "status_lbl",
                     "log_lbl"},
        "accounts": {"domain_input", "cookie_input", "accounts_status",
                     "accounts_box"},
        "history": {"history_box", "rec_switch"},
    }
    for scr, ids in need.items():
        got = set(root.get_screen(scr).ids)
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
    assert m.SHELL_VERSION == "1.8.2", "壳版本未升级到 1.8.2"

    # v1.8.2 真机根治：WebViewClient 导航守卫 + WebView 层返回键 +
    # SDL 返回键 trap + 百度 PC 登录页（v1.8.1 桌面 UA 无效的根因：
    # 无 client 时 intent://market:// 导航逃逸到系统；百度 H5 壳有
    # 100ms 延迟强制跳转脚本）
    java_path = ROOT / "mobile" / "java_classes" / "PanWebViewClient.java"
    assert java_path.exists(), "缺 Java 桥接类 PanWebViewClient.java"
    jtxt = java_path.read_text(encoding="utf-8")
    assert "extends WebViewClient" in jtxt, "桥接类未继承 WebViewClient"
    assert jtxt.count("shouldOverrideUrlLoading") >= 2, \
        "桥接类未覆写双签名 shouldOverrideUrlLoading"
    assert "UrlLoadingCallback" in jtxt, "桥接类缺回调接口"
    spec = (ROOT / "mobile" / "buildozer.spec").read_text(encoding="utf-8")
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
    assert "SDL_ANDROID_TRAP_BACK_BUTTON" in msrc, \
        "未开启 SDL 返回键 trap（Kivy 收不到 keycode 27 根因）"
    assert msrc.index("SDL_ANDROID_TRAP_BACK_BUTTON") < msrc.index(
        "import panboost"), "SDL trap 必须在引擎 import 之前设置"
    assert m.PAN_BY_KEY["baidu"]["login"] == \
        "https://passport.baidu.com/v2/?login", "百度未用 PC 统一登录页"

    # 浅色主题断言：页面底色接近白（亮度>0.9）
    r, g, b, _a = m.BG
    assert r > 0.9 and g > 0.9 and b > 0.9, f"非浅色底: {m.BG}"
    kv = m.KV
    assert "rgba: 0.957, 0.965, 0.984, 1" in kv, "缺浅色底绘制"
    assert "RoundedRectangle" in kv, "卡片缺圆角绘制"

    spinner = root.get_screen("download").ids.threads_spinner
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
