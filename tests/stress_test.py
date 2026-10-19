#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PanBoost 压力测试套件：极端并发 / 混沌故障 / 暴力中断 / 内存泄漏 / 微小块 / 双进程竞争

运行：python3 stress_test.py [场景名 ...]   （缺省全跑）
"""
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from test_server import TestServer

PB = [sys.executable, str(ROOT / "panboost.py")]
ENV_BASE = {"PANBOOST_NO_FSYNC": "1"}


def run_pb(args, timeout, env_extra=None, popen=False):
    env = {**os.environ, **ENV_BASE, **(env_extra or {})}
    if popen:
        return subprocess.Popen(
            PB + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True)
    return subprocess.run(
        PB + list(args), capture_output=True, text=True, timeout=timeout,
        env=env)


def rss_kb(pid):
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return -1


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}" + (f"  ({detail})" if detail else ""))
    return ok


RESULTS = []


def record(name, ok):
    RESULTS.append((name, ok))


# ---------------------------------------------------------------- 场景1
def st1_chaos_1024():
    """1024线程 × 混沌服务器（15%故障率：429/503/RST/截断混合）200MB

    验证：最终完整 + 请求总量有界（无风暴）+ 全程无死锁
    """
    data = os.urandom(200 * 1024 * 1024)
    want = hashlib.sha256(data).hexdigest()
    srv = TestServer()
    srv.set_data(data, fail_prob=0.4, fail_seed=7, chunk_size=128 * 1024,
                 delay_per_chunk=0.0002)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "c.bin"
        env = {"PANBOOST_HOME": td}
        t0 = time.time()
        r = run_pb(["download", srv.url + "/c.bin", "-o", str(out),
                    "-t", "1024", "--min-piece", "1048576",
                    "--retry", "12"], timeout=600, env_extra=env)
        dt = time.time() - t0
        ok_data = (r.returncode == 0 and out.exists()
                   and hashlib.sha256(out.read_bytes()).hexdigest() == want)
        record("ST1-混沌200MB数据完整", check("ST1-混沌200MB数据完整", ok_data,
              r.stdout[-200:] if not ok_data else f"{dt:.0f}s"))
        # 请求有界：理想请求数 ≈ 200块+探测；允许 6 倍损耗
        ideal = 200 + 8
        record("ST1-请求总量有界",
               check("ST1-请求总量有界", srv.req_seq < ideal * 6,
                     f"req={srv.req_seq} (理想≈{ideal}, 上限{ideal*6})"))
        record("ST1-峰值并发不超发",
               check("ST1-峰值并发不超发", srv.max_concurrent <= 1024,
                     f"max_conc={srv.max_concurrent}"))


# ---------------------------------------------------------------- 场景2
def st2_kill9_loop():
    """SIGKILL 暴力循环：下载中反复 kill -9，重启续传直至完成

    验证：任意时刻被杀都不产生损坏，最终字节级正确
    """
    data = os.urandom(400 * 1024 * 1024)
    want = hashlib.sha256(data).hexdigest()
    srv = TestServer()
    srv.set_data(data, chunk_size=128 * 1024, delay_per_chunk=0.015)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "k.bin"
        env = {**os.environ, **ENV_BASE, "PANBOOST_HOME": td}
        kills = 0
        for round_i in range(12):
            proc = subprocess.Popen(
                PB + ["download", srv.url + "/k.bin", "-o", str(out),
                      "-t", "8", "--quiet"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
            # 进度驱动击杀：等待完成比例 >=20% 后暴力 kill -9
            ctrl = Path(str(out) + ".pbctrl")
            deadline = time.time() + 60
            while time.time() < deadline and proc.poll() is None:
                try:
                    import json as _json
                    d = _json.loads(ctrl.read_text())
                    bits = d.get("done_hex", "")
                    if bits and bits.count("1") / len(bits) >= 0.2:
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(0.3)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
                kills += 1
            else:
                break
        # 最后一次允许跑完
        r = run_pb(["download", srv.url + "/k.bin", "-o", str(out),
                    "-t", "8"], timeout=300, env_extra={"PANBOOST_HOME": td})
        ok = (r.returncode == 0
              and hashlib.sha256(out.read_bytes()).hexdigest() == want)
        record("ST2-SIGKILL循环最终完整",
               check("ST2-SIGKILL循环最终完整", ok,
                     f"kills={kills} rc={r.returncode}"
                     if ok else f"kills={kills} {r.stdout[-200:]}"))
        record("ST2-确实发生了多次击杀",
               check("ST2-确实发生了多次击杀", kills >= 3, f"kills={kills}"))


# ---------------------------------------------------------------- 场景3
def st3_memory():
    """内存泄漏检测：250MB 慢速下载，采样进程 RSS 曲线

    验证：峰值 RSS < 300MB；后半程斜率不持续增长（无泄漏）
    """
    data = os.urandom(250 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, chunk_size=64 * 1024, delay_per_chunk=0.0004)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "m.bin"
        proc = run_pb(["download", srv.url + "/m.bin", "-o", str(out),
                       "-t", "32", "--quiet", "--limit", "8M"],
                      timeout=600, popen=True,
                      env_extra={"PANBOOST_HOME": td})
        samples = []
        try:
            while proc.poll() is None:
                samples.append(rss_kb(proc.pid))
                time.sleep(0.5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        rc = proc.returncode
        ok_data = rc == 0 and out.read_bytes() == data
        peak = max(samples) if samples else 0
        # 后半程线性斜率（KB/样本）：> 300KB/0.5s 持续增长视为泄漏
        half = samples[len(samples) // 2:] or samples
        slope = 0
        if len(half) >= 4:
            n = len(half)
            xs = list(range(n))
            mx = sum(xs) / n
            my = sum(half) / n
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, half)) \
                / sum((x - mx) ** 2 for x in xs)
        record("ST3-慢速250MB完整",
               check("ST3-慢速250MB完整", ok_data, f"rc={rc}"))
        record("ST3-峰值RSS<300MB",
               check("ST3-峰值RSS<300MB", 0 < peak < 300 * 1024,
                     f"peak={peak//1024}MB"))
        record("ST3-后半程无持续增长",
               check("ST3-后半程无持续增长", slope < 300,
                     f"slope={slope:.0f}KB/样本"))


# ---------------------------------------------------------------- 场景4
def st4_tiny_blocks():
    """微型块：100MB / 64KB块(1600块) / 64线程 —— 海量块调度开销

    验证：数据完整 + 完成时间合理（块管理 O(n) 不爆炸）
    """
    data = os.urandom(100 * 1024 * 1024)
    want = hashlib.sha256(data).hexdigest()
    srv = TestServer()
    srv.set_data(data, chunk_size=64 * 1024)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "t.bin"
        t0 = time.time()
        r = run_pb(["download", srv.url + "/t.bin", "-o", str(out),
                    "-t", "64", "--min-piece", "65536"], timeout=300,
                   env_extra={"PANBOOST_HOME": td})
        dt = time.time() - t0
        ok = (r.returncode == 0
              and hashlib.sha256(out.read_bytes()).hexdigest() == want)
        record("ST4-1600微小块数据完整",
               check("ST4-1600微小块数据完整", ok,
                     f"{dt:.0f}s" if ok else r.stdout[-200:]))
        record("ST4-微小块完成时间<60s",
               check("ST4-微小块完成时间<60s", ok and dt < 60,
                     f"{dt:.0f}s"))


# ---------------------------------------------------------------- 场景5
def st5_dual_process():
    """双进程竞争：两个不同数据源同时写同一输出文件（静默损坏风险）

    场景：进程A下载源X，1.5s后进程B下载源Y到同一输出——若无互斥保护，
    两进程交错写不同数据 → 静默损坏。期望：文件锁互斥（后到者明确报错）
    或最终文件完整等于其中一方。
    """
    data_x = os.urandom(96 * 1024 * 1024)
    data_y = os.urandom(96 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data_x, chunk_size=128 * 1024,
                 alt_path="/other.bin", alt_data=data_y)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "d.bin"
        env = {**os.environ, **ENV_BASE, "PANBOOST_HOME": td}
        pa = subprocess.Popen(
            PB + ["download", srv.url + "/a.bin", "-o", str(out), "-t", "8",
                  "--limit", "2M"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
        time.sleep(3.0)
        pb = subprocess.Popen(
            PB + ["download", srv.url + "/other.bin", "-o", str(out),
                  "-t", "8", "--limit", "2M"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
        ra, ea = pa.communicate(timeout=300)
        rb, eb = pb.communicate(timeout=300)
        both = (ra or "") + (rb or "") + (ea or "") + (eb or "")
        locked = any(k in both for k in ("锁", "另一个", "占用"))
        if out.exists():
            got = hashlib.sha256(out.read_bytes()).hexdigest()
            intact = got in (hashlib.sha256(data_x).hexdigest(),
                             hashlib.sha256(data_y).hexdigest())
        else:
            intact = False
        record("ST5-双进程不静默损坏",
               check("ST5-双进程不静默损坏", locked or intact,
                     f"locked={locked} intact={intact} "
                     f"rcA={pa.returncode} rcB={pb.returncode}"))


# ---------------------------------------------------------------- 场景6
def st6_rst_storm():
    """RST 风暴：前 40 条数据连接全部被服务器暴力重置

    验证：客户端从 RST 风暴中恢复并完成下载
    """
    data = os.urandom(64 * 1024 * 1024)
    want = hashlib.sha256(data).hexdigest()
    srv = TestServer()
    srv.set_data(data, rst_conns=40, rst_at=64 * 1024,
                 chunk_size=128 * 1024)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "r.bin"
        t0 = time.time()
        r = run_pb(["download", srv.url + "/r.bin", "-o", str(out),
                    "-t", "16", "--retry", "10"], timeout=300,
                   env_extra={"PANBOOST_HOME": td})
        dt = time.time() - t0
        ok = (r.returncode == 0
              and hashlib.sha256(out.read_bytes()).hexdigest() == want)
        record("ST6-RST风暴后完成",
               check("ST6-RST风暴后完成", ok,
                     f"{dt:.0f}s rst={srv.rst_count}"
                     if ok else r.stdout[-200:]))
        record("ST6-确实发生RST",
               check("ST6-确实发生RST", srv.rst_count >= 30,
                     f"rst_count={srv.rst_count}"))


# ---------------------------------------------------------------- 场景7
def st7_limit_stall():
    """全局限速 + 看门狗共存：--limit 4M 下大块慢速传输不被误杀

    验证：限速排队不被 stall 看门狗击杀（数据仍在到手）
    """
    data = os.urandom(48 * 1024 * 1024)
    want = hashlib.sha256(data).hexdigest()
    srv = TestServer()
    srv.set_data(data, chunk_size=128 * 1024, delay_per_chunk=0.001)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "l.bin"
        t0 = time.time()
        r = run_pb(["download", srv.url + "/l.bin", "-o", str(out),
                    "-t", "8", "--limit", "4M", "--stall-timeout", "5"],
                   timeout=300, env_extra={"PANBOOST_HOME": td})
        dt = time.time() - t0
        ok = (r.returncode == 0
              and hashlib.sha256(out.read_bytes()).hexdigest() == want)
        log = Path.home() / ".panboost" / "antifraud.log"
        stall_killed = False
        try:
            if log.exists():
                stall_killed = "stall_killed" in log.read_text()[-2000:]
        except OSError:
            pass
        record("ST7-限速下完整下载",
               check("ST7-限速下完整下载", ok, f"{dt:.0f}s rc={r.returncode}"))
        record("ST7-限速排队不被误杀",
               check("ST7-限速排队不被误杀", ok and not stall_killed,
                     f"stall_killed={stall_killed}"))


# ---------------------------------------------------------------- 场景8
def st8_latency_aware():
    """延迟感知降载：服务器 TTFB 随并发上升（拥塞排队模型）

    验证：客户端在 429 出现之前主动收敛并发（防患于未然，降低封禁概率）
    """
    data = os.urandom(128 * 1024 * 1024)
    want = hashlib.sha256(data).hexdigest()
    srv = TestServer()
    # TTFB 基准 50ms，每 +1 并发 +25ms：8 并发 ≈ 250ms（>2.5 倍基准）
    srv.set_data(data, ttfb_factor=0.5, chunk_size=128 * 1024,
                 delay_per_chunk=0.0002)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "lat.bin"
        t0 = time.time()
        r = run_pb(["download", srv.url + "/lat.bin", "-o", str(out),
                    "-t", "32"], timeout=300,
                   env_extra={"PANBOOST_HOME": td})
        dt = time.time() - t0
        ok = (r.returncode == 0
              and hashlib.sha256(out.read_bytes()).hexdigest() == want)
        record("ST8-拥塞服务器下完整",
               check("ST8-拥塞服务器下完整", ok, f"{dt:.0f}s"))
        # 未触发任何限流的前提下，并发自动收敛在低位（延迟感知生效）
        record("ST8-并发预防性收敛",
               check("ST8-并发预防性收敛",
                     ok and srv.max_concurrent <= 16,
                     f"max_conc={srv.max_concurrent} "
                     f"throttle={srv.throttle_count}"))


# ---------------------------------------------------------------- 场景9
def st9_batch_queue():
    """批量下载队列：--input 5文件（含 1 个 404）+ 同域礼貌间隔 + 汇总

    验证：好文件全部落盘内容正确、坏文件不中断队列、返回码区分部分失败
    """
    files = {}
    for name, size in (("a.bin", 16), ("b.bin", 8), ("c.bin", 12),
                       ("d.bin", 4), ("e.bin", 20)):
        files[name] = os.urandom(size * 1024 * 1024)
    srv = TestServer()

    def set_route(name):
        others = {k: v for k, v in files.items() if k != name}
        # alt 机制单路径限制：直接换 data（服务器无状态切换即可）
        srv.set_data(files[name], chunk_size=128 * 1024)

    # 简化：服务器按路径服务不同文件——test_server 单 data 限制，
    # 这里用"每文件一个独立 TestServer"等价验证批量逻辑
    class Router:
        def __init__(self):
            self.srv = srv
            self.data = files

        def url_for(self, name):
            return srv.url + "/" + name

    rt = Router()

    # test_server 按路径分发：借 redirect 也不行；直接给 handler 加路由
    # ——改用查表：本场景内联多路径支持
    import test_server
    orig_do_get = test_server.TestHandler.do_GET

    def routed_do_get(self):
        name = self.path.lstrip("/")
        if name in files:
            self.server.cfg["data"] = files[name]
            return orig_do_get(self)
        self._reject(404, "not found")
        return None

    test_server.TestHandler.do_GET = routed_do_get
    try:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            outdir = Path(td) / "out"
            lst = Path(td) / "urls.txt"
            urls = [rt.url_for(n) for n in ("a.bin", "b.bin", "c.bin",
                                            "missing.bin", "e.bin")]
            lst.write_text("\n".join(urls) + "\n# 注释行\n")
            t0 = time.time()
            r = run_pb(["download", "--input", str(lst),
                        "-o", str(outdir), "-t", "8"], timeout=300,
                       env_extra={"PANBOOST_HOME": str(home)})
            dt = time.time() - t0
            good_ok = all((outdir / n).read_bytes() == files[n]
                          for n in ("a.bin", "b.bin", "c.bin", "e.bin"))
            record("ST9-批量4文件全部正确",
                   check("ST9-批量4文件全部正确", good_ok,
                         f"{dt:.0f}s"))
            record("ST9-坏文件不中断队列",
                   check("ST9-坏文件不中断队列",
                         good_ok and r.returncode == 2,
                         f"rc={r.returncode}"))
            record("ST9-汇总与失败清单输出",
                   check("ST9-汇总与失败清单输出",
                         "批量汇总" in r.stdout and "missing.bin" in r.stdout,
                         r.stdout[-120:]))
            record("ST9-同域礼貌间隔生效",
                   check("ST9-同域礼貌间隔生效", "礼貌间隔" in r.stdout,
                         ""))
    finally:
        test_server.TestHandler.do_GET = orig_do_get


ALL = {
    "st1": st1_chaos_1024,
    "st2": st2_kill9_loop,
    "st3": st3_memory,
    "st4": st4_tiny_blocks,
    "st5": st5_dual_process,
    "st6": st6_rst_storm,
    "st7": st7_limit_stall,
    "st8": st8_latency_aware,
    "st9": st9_batch_queue,
}


def main():
    import tempfile as _tf
    os.environ.setdefault("PANBOOST_HOME", _tf.mkdtemp(prefix="pbstress_"))
    names = sys.argv[1:] or list(ALL)
    for n in names:
        fn = ALL.get(n)
        if not fn:
            print(f"未知场景: {n}")
            continue
        print(f"\n===== {n}: {fn.__doc__.strip().splitlines()[0]} =====")
        t0 = time.time()
        try:
            fn()
        except Exception as e:
            record(n, check(n, False, f"异常: {type(e).__name__}: {e}"))
        print(f"----- {n} 耗时 {time.time()-t0:.0f}s")
    print("\n" + "=" * 50)
    fails = [k for k, v in RESULTS if not v]
    print(f"压测结果: {len(RESULTS)-len(fails)}/{len(RESULTS)} 通过")
    if fails:
        print("失败项:", ", ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
