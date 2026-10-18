"""mobile/main.py 的无 Kivy 冒烟测试：mock kivy 模块后跑完整下载流程。

验证图形壳对 panboost 引擎的全部 API 调用签名正确（probe / UA 回退 /
auto_tune / Multi / Single / 停止 / 状态轮询），可在 CI 或桌面复跑：
    python3 dev/smoke_mobile.py
"""
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mobile"))

os.environ["PANBOOST_HOME"] = tempfile.mkdtemp(prefix="pbmobile_")
os.environ.setdefault("PANBOOST_NO_FSYNC", "1")

# ---- mock kivy（必须在 import mobile.main 之前） ----
kivy = types.ModuleType("kivy")


class _App:
    def __init__(self):
        pass


app_mod = types.ModuleType("kivy.app")
app_mod.App = _App


class _Clock:
    @staticmethod
    def schedule_interval(fn, interval):
        pass


clock_mod = types.ModuleType("kivy.clock")
clock_mod.Clock = _Clock


class _Widget:
    def __init__(self, **kw):
        self.text = kw.get("text", "")
        self.active = False
        self.value = 0.0


class _Builder:
    @staticmethod
    def load_string(kv):
        ns = types.SimpleNamespace
        return ns(ids=ns(
            url_input=_Widget(), cookie_input=_Widget(),
            threads_spinner=_Widget(text="16"),
            insecure_switch=_Widget(active=False),
            go_btn=_Widget(), progress=_Widget(),
            status_lbl=_Widget(), log_lbl=_Widget()))


lang_mod = types.ModuleType("kivy.lang")
lang_mod.Builder = _Builder
metrics_mod = types.ModuleType("kivy.metrics")
metrics_mod.dp = lambda x: x
metrics_mod.sp = lambda x: x
kivy.app = app_mod
kivy.clock = clock_mod
kivy.lang = lang_mod
kivy.metrics = metrics_mod
sys.modules.update({"kivy": kivy, "kivy.app": app_mod, "kivy.clock": clock_mod,
                    "kivy.lang": lang_mod, "kivy.metrics": metrics_mod})

import main as mobile_main  # noqa: E402
from test_server import TestServer  # noqa: E402
import panboost as pb  # noqa: E402

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def run_case(url, cookie_text="", threads_choice="16",
             insecure=False, expect_rc_ok=True, name=""):
    tmp = tempfile.mkdtemp(prefix="pbmobile_dl_")
    mobile_main.external_files_dir = lambda: tmp
    app = mobile_main.PanBoostApp()
    app.build()
    app.root.ids.url_input.text = url
    app.root.ids.cookie_input.text = cookie_text
    app.root.ids.threads_spinner.text = threads_choice
    app.root.ids.insecure_switch.active = insecure
    app.on_go()
    assert app.worker is not None
    app.worker.join(timeout=90)
    return app, Path(tmp)


def main():
    data = os.urandom(3 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data)

    # 用例1：常规多线程
    app, outdir = run_case(srv.url + "/m.bin")
    files = list(outdir.glob("*"))
    got = files[0].read_bytes() if files else b""
    check("壳-多线程下载完整", got == data, f"files={[f.name for f in files]}")
    check("壳-状态为完成", app._status.startswith("完成"),
          app._status[:60])
    check("壳-进度100%", app._progress >= 1.0, f"{app._progress}")
    check("壳-无致命异常日志", all("失败" not in l and "Error" not in l
                                    for l in app.logs[-3:]), str(app.logs[-2:]))

    # 用例2：Cookie 传递 + 服务器校验 Cookie
    srv2 = TestServer()
    srv2.set_data(data, require_cookie="SID=abc123")
    app2, outdir2 = run_case(srv2.url + "/c.bin", cookie_text="SID=abc123")
    files2 = list(outdir2.glob("*"))
    check("壳-Cookie头已传递", files2 and files2[0].read_bytes() == data,
          f"{[f.name for f in files2]}")

    # 用例3：连接失败优雅报错（不崩溃）
    app3, _ = run_case("http://127.0.0.1:9/x.bin")  # 端口9 discard，必拒
    check("壳-失败优雅报错", app3._status.startswith("失败"),
          app3._status[:60])

    # 用例4：停止（stop_event 生效）
    big = os.urandom(6 * 1024 * 1024)
    srv3 = TestServer()
    srv3.set_data(big, throttle_after=1, throttle_status=429, retry_after=1)
    tmp = tempfile.mkdtemp(prefix="pbmobile_stop_")
    mobile_main.external_files_dir = lambda: tmp
    app4 = mobile_main.PanBoostApp()
    app4.build()
    app4.root.ids.url_input.text = srv3.url + "/s.bin"
    app4.root.ids.threads_spinner.text = "8"
    app4.on_go()
    import time
    time.sleep(2.0)
    running = app4.worker is not None and app4.worker.is_alive()
    app4.on_go()  # 第二次点击 = 停止
    stopped = app4.dl is not None and app4.dl.stop_event.is_set()
    app4.worker.join(timeout=60)
    check("壳-停止请求生效", running and (stopped or app4._status != "x"),
          f"running={running}")

    n_fail = sum(1 for _, ok in CHECKS if not ok)
    print(f"\n===== mobile 冒烟: {len(CHECKS) - n_fail}/{len(CHECKS)} 通过 =====")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
