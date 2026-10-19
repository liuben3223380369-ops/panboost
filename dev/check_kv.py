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
    assert hasattr(weblogin, "open_login") and hasattr(weblogin, "available")
    # 按钮回调必须经 _guard 兜底（异常可见，不静默进 logcat）
    msrc = Path(m.__file__).read_text(encoding="utf-8")
    assert "lambda _b, k=pan" not in msrc and "lambda _b, u=it" not in msrc, \
        "宫格/历史按钮仍有未兜底的裸 lambda 回调"
    assert "_guard" in msrc, "缺 _guard 回调兜底"

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
