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
    for cls in ("MainScreen", "AccountsScreen", "HistoryScreen"):
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
    assert names == {"main", "accounts", "history"}, f"屏幕缺失: {names}"

    need = {
        "main": {"url_input", "cookie_input", "threads_spinner",
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

    for meth in ("on_go", "go", "save_account", "del_account",
                 "refresh_accounts", "refresh_history", "rerun",
                 "clear_history", "on_rec_toggle"):
        assert hasattr(m.PanBoostApp, meth), f"缺少方法 {meth}"

    spinner = root.get_screen("main").ids.threads_spinner
    from kivy.uix.spinner import SpinnerOption
    assert issubclass(spinner.option_cls, SpinnerOption), \
        f"option_cls 非法: {spinner.option_cls}"
    vals = [str(v) for v in spinner.values]
    assert "512" in vals and "1024" in vals, f"线程选项缺失: {vals}"
    spinner._build_dropdown()
    opts = [w for w in spinner._dropdown.children
            if isinstance(w, SpinnerOption)]
    assert len(opts) == len(vals), \
        f"下拉构建失败: {len(opts)}/{len(vals)}"

    print("check_kv: OK")


if __name__ == "__main__":
    main()
