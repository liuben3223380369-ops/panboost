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
