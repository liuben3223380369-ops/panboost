#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PanBoost 自动化测试：多线程 / 断点续传 / Range降级 / 重定向 / Cookie / 文件名 / Cookie管理"""
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
# HERE 必须排在 ROOT 之前（后 insert 的在最前）——若仓库根存在同名
# 旧残留 test_server.py 会被优先导入（曾致 138/2 假失败）
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from test_server import TestServer

PB = [sys.executable, str(ROOT / "panboost.py")]
PASS = []
FAIL = []


def md5(b):
    return hashlib.md5(b).hexdigest()


def run_pb(*args, env_extra=None, timeout=180):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(PB + list(args), capture_output=True, text=True,
                          timeout=timeout, env=env)


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"[PASS] {name}")
    else:
        FAIL.append(name)
        print(f"[FAIL] {name} {detail}")


def t_multithread():
    data = os.urandom(16 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, delay_per_chunk=0.001)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "file.bin"
        r = run_pb("download", srv.url + "/big.bin", "-o", str(out), "-t", "8")
        ok = r.returncode == 0 and out.read_bytes() == data
        check("多线程下载-数据完整性", ok, r.stdout + r.stderr)
        check("多线程下载-真实并发", srv.max_concurrent >= 4,
              f"max_concurrent={srv.max_concurrent}")


def t_resume_sigint():
    data = os.urandom(48 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, delay_per_chunk=0.006, chunk_size=16 * 1024)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "resume.bin"
        proc = subprocess.Popen(
            PB + ["download", srv.url + "/r.bin", "-o", str(out), "-t", "4",
                  "--quiet"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.time() + 20
        while time.time() < deadline:
            if Path(str(out) + ".pbctrl").exists() and out.exists() \
                    and out.stat().st_size == len(data) and srv.total_sent > 1024 * 1024:
                break
            time.sleep(0.1)
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        ctrl_exists = Path(str(out) + ".pbctrl").exists()
        check("断点续传-进度文件已保存", ctrl_exists,
              f"sent={srv.total_sent}")
        sent_before = srv.total_sent
        r = run_pb("download", srv.url + "/r.bin", "-o", str(out), "-t", "4")
        ok = r.returncode == 0 and out.read_bytes() == data
        check("断点续传-重启后数据完整", ok, r.stdout + r.stderr)
        resumed = srv.total_sent - sent_before
        check("断点续传-未重复下载", resumed < len(data) * 0.9,
              f"resumed={resumed} total={len(data)}")
        check("断点续传-完成后清理进度文件",
              not Path(str(out) + ".pbctrl").exists())


def t_resume_kill():
    data = os.urandom(20 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, delay_per_chunk=0.004, chunk_size=32 * 1024)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "kill.bin"
        proc = subprocess.Popen(
            PB + ["download", srv.url + "/k.bin", "-o", str(out), "-t", "4",
                  "--quiet"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.time() + 20
        while time.time() < deadline:
            if out.exists() and out.stat().st_size == len(data) \
                    and srv.total_sent > 1024 * 512:
                time.sleep(0.5)
                break
            time.sleep(0.1)
        proc.kill()
        proc.wait()
        r = run_pb("download", srv.url + "/k.bin", "-o", str(out), "-t", "4")
        ok = r.returncode == 0 and out.read_bytes() == data
        check("硬杀进程后-续传数据完整", ok, r.stdout + r.stderr)


def t_no_range():
    data = os.urandom(4 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, support_range=False)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "single.bin"
        r = run_pb("download", srv.url + "/s.bin", "-o", str(out))
        ok = r.returncode == 0 and out.read_bytes() == data
        check("无Range服务器-单线程降级", ok, r.stdout + r.stderr)
        check("无Range服务器-清理临时文件",
              not Path(str(out) + ".pbpart").exists())


def t_redirect():
    data = os.urandom(8 * 1024 * 1024)
    target = TestServer()
    target.set_data(data)
    src = TestServer()
    src.set_data(b"", redirect_to=target.url + "/real.bin")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "redir.bin"
        r = run_pb("download", src.url + "/jump", "-o", str(out), "-t", "4")
        ok = r.returncode == 0 and out.read_bytes() == data
        check("重定向跟随-多线程下载", ok, r.stdout + r.stderr)


def t_cookie_required():
    data = os.urandom(2 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, require_cookie="BDUSS=test123")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "c.bin"
        r = run_pb("download", srv.url + "/sec.bin", "-o", str(out))
        check("Cookie校验-无Cookie被拒", r.returncode != 0)
        r = run_pb("download", srv.url + "/sec.bin", "-o", str(out),
                   "--cookie", "BDUSS=test123; other=1")
        ok = r.returncode == 0 and out.read_bytes() == data
        check("Cookie校验-携带Cookie成功", ok, r.stdout + r.stderr)


def t_content_disposition():
    data = os.urandom(1024 * 1024)
    srv = TestServer()
    fname = "测试文件_v2.zip"
    from urllib.parse import quote
    srv.set_data(data, extra_headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"})
    with tempfile.TemporaryDirectory() as td:
        r = run_pb("download", srv.url + "/whatever", timeout=60,
                   env_extra={"PANBOOST_HOME": td})
        got = (Path.cwd() / fname)
        ok = r.returncode == 0 and got.exists() and got.read_bytes() == data
        check("Content-Disposition-UTF8文件名", ok, r.stdout + r.stderr)
        if got.exists():
            got.unlink()


def t_cookie_store():
    data = os.urandom(1024 * 1024)
    srv = TestServer()
    srv.set_data(data, require_cookie="BDUSS=store456")
    with tempfile.TemporaryDirectory() as td:
        ck = Path(td) / "cookies.txt"
        ck.write_text(
            "# Netscape HTTP Cookie File\n"
            f".127.0.0.1\tTRUE\t/\tFALSE\t0\tBDUSS\tstore456\n"
            f"127.0.0.1\tFALSE\t/\tFALSE\t0\tSTK\txyz\n",
            encoding="utf-8")
        env = {"PANBOOST_HOME": td}
        r = run_pb("cookie", "import", "127.0.0.1", str(ck), env_extra=env)
        check("Cookie管理-导入cookies.txt", r.returncode == 0, r.stdout + r.stderr)
        r = run_pb("cookie", "list", env_extra=env)
        check("Cookie管理-列表展示",
              "BDUSS=store456" in r.stdout, r.stdout)
        out = Path(td) / "cs.bin"
        r = run_pb("download", srv.url + "/s.bin", "-o", str(out),
                   env_extra=env)
        ok = r.returncode == 0 and out.read_bytes() == data
        check("Cookie管理-自动附加Cookie下载", ok, r.stdout + r.stderr)


def t_probe():
    data = os.urandom(1234567)
    srv = TestServer()
    srv.set_data(data)
    r = run_pb("probe", srv.url + "/p.bin")
    ok = r.returncode == 0 and "Range支持 : 是" in r.stdout \
        and "1.2MB" in r.stdout
    check("probe-探测输出", ok, r.stdout + r.stderr)


def t_empty_and_small():
    with tempfile.TemporaryDirectory() as td:
        srv = TestServer()
        srv.set_data(b"")
        out = Path(td) / "empty.bin"
        r = run_pb("download", srv.url + "/e", "-o", str(out))
        check("边界-空文件", r.returncode == 0 and out.exists()
              and out.stat().st_size == 0, r.stdout + r.stderr)
        srv.set_data(b"hello panboost")
        out2 = Path(td) / "tiny.bin"
        r = run_pb("download", srv.url + "/t", "-o", str(out2), "-t", "8")
        check("边界-小文件(1MB以下)",
              r.returncode == 0 and out2.read_bytes() == b"hello panboost",
              r.stdout + r.stderr)


def t_dynamic_blocks():
    """慢连接场景：动态分块应让快连接抢走大部分块，消除长尾"""
    data = os.urandom(16 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, delay_per_chunk=0.001, slow_conns=3, slow_delay=0.06)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "dyn.bin"
        t0 = time.time()
        r = run_pb("download", srv.url + "/d.bin", "-o", str(out), "-t", "8")
        dt = time.time() - t0
        ok = r.returncode == 0 and out.read_bytes() == data
        check("动态分块-数据完整性", ok, r.stdout[-300:] + r.stderr[-300:])
        check("动态分块-消除慢连接长尾", dt < 1.2,
              f"耗时{dt:.2f}s (固定分片估算~1.9s)")


def t_auto():
    data = os.urandom(96 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, delay_per_chunk=0.001)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "auto.bin"
        r = run_pb("download", srv.url + "/a.bin", "-o", str(out), "--auto",
                   timeout=240)
        ok = r.returncode == 0 and out.read_bytes() == data
        check("auto调优-下载成功", ok, r.stdout[-300:] + r.stderr[-300:])
        check("auto调优-输出测速结果", "[调优]" in r.stdout, r.stdout[:300])


def t_many_threads():
    data = os.urandom(4 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "many.bin"
        r = run_pb("download", srv.url + "/m.bin", "-o", str(out), "-t", "512")
        ok = r.returncode == 0 and out.read_bytes() == data
        check("高线程-512线程数据正确", ok, r.stdout[-300:] + r.stderr[-300:])


def t_anti_throttle_aimd():
    """服务器并发上限32，客户端1024线程 → AIMD自动收敛、完成下载"""
    data = os.urandom(48 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, conn_limit=32, retry_after=1, delay_per_chunk=0.0005,
                 chunk_size=32 * 1024)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "aimd.bin"
        r = run_pb("download", srv.url + "/a.bin", "-o", str(out),
                   "-t", "1024", "--min-piece", "65536", timeout=300)
        ok = r.returncode == 0 and out.read_bytes() == data
        check("反风控-1024线程限流下完成下载", ok,
              r.stdout[-300:] + r.stderr[-300:])
        check("反风控-并发收敛至限制附近",
              srv.max_concurrent <= 48, f"max_concurrent={srv.max_concurrent}")
        check("反风控-有限流事件被处理", srv.throttle_count >= 0)


def t_anti_throttle_smooth_ramp():
    """1024线程下瞬时建连速率受令牌桶约束（峰值≤conn-rate*1.5+8）"""
    data = os.urandom(48 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, delay_per_chunk=0.0008, chunk_size=32 * 1024)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "ramp.bin"
        r = run_pb("download", srv.url + "/r.bin", "-o", str(out),
                   "-t", "1024", "--min-piece", "65536",
                   "--conn-rate", "40", timeout=300)
        ok = r.returncode == 0 and out.read_bytes() == data
        check("平滑爬坡-1024线程数据完整", ok,
              r.stdout[-300:] + r.stderr[-300:])
        peak = srv.new_conn_rate_peak()
        check("平滑爬坡-建连速率受限", peak <= 40 * 1.5 + 8,
              f"峰值建连/秒={peak} (限40)")


def t_anti_throttle_retry_after():
    """服务器 Retry-After=3 → 客户端真实暂停≥3秒后恢复并完成"""
    data = os.urandom(24 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, conn_limit=4, retry_after=3, delay_per_chunk=0.0005,
                 chunk_size=32 * 1024)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "ra.bin"
        t0 = time.time()
        r = run_pb("download", srv.url + "/ra.bin", "-o", str(out),
                   "-t", "64", "--min-piece", "65536", timeout=300)
        dt = time.time() - t0
        ok = r.returncode == 0 and out.read_bytes() == data
        check("RetryAfter-遵守后完成下载", ok,
              r.stdout[-300:] + r.stderr[-300:])
        paused = srv.throttle_count > 0 and dt >= 3.0
        check("RetryAfter-实际暂停≥3秒", paused,
              f"throttle_count={srv.throttle_count} 耗时={dt:.1f}s")


def t_anti_throttle_403_circuit():
    """下载中途触发持续403 → AIMD降速+403连击→三态熔断→半开探测失败→放弃退出

    v1.3：熔断不再永久死亡，OPEN→HALF_OPEN 自动探测恢复；
    连续4轮探测失败才最终放弃。CB_SCALE=0.02 加速冷却演练。
    """
    data = os.urandom(8 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, throttle_after=8, throttle_status=403, retry_after=0)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "fuse.bin"
        t0 = time.time()
        r = run_pb("download", srv.url + "/f.bin", "-o", str(out),
                   "-t", "32", timeout=240,
                   env_extra={"PANBOOST_CB_SCALE": "0.02"})
        dt = time.time() - t0
        check("403熔断-判定失败退出", r.returncode != 0,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("403熔断-输出熔断提示", "探测恢复" in r.stdout or "封禁" in r.stdout,
              r.stdout[-300:])
        check("403熔断-进度已保存可续传",
              Path(str(out) + ".pbctrl").exists())
        check("403熔断-熔断前完成部分下载",
              out.exists() and 0 < out.stat().st_size <= len(data))
        check("403熔断-合理时间内熔断", dt < 60, f"耗时{dt:.0f}s")


# =====================================================================
# v1.3 单元测试（直接 import panboost 模块）
# =====================================================================

def t_unit_circuit_states():
    """三态熔断状态机：CLOSED→OPEN→HALF_OPEN→恢复/放弃"""
    import panboost as pb
    rc = pb.RateController(16)
    for _ in range(9):
        rc.on_throttle(403)
    ok1 = rc.cb_state == pb.RateController.CB_OPEN and rc.streak_403 == 9
    check("单测-熔断-403连击进入OPEN", ok1,
          f"state={rc.cb_state} streak={rc.streak_403}")
    rc.cooldown_until = time.time() - 1
    probe = rc.acquire()
    ok2 = probe is True and rc.cb_state == pb.RateController.CB_HALF
    check("单测-熔断-到期后半开放行单探测者", ok2,
          f"probe={probe} state={rc.cb_state}")
    rc.release(probe_ok=True)
    ok3 = rc.cb_state == pb.RateController.CB_CLOSED and rc.streak_403 == 0
    check("单测-熔断-探测成功恢复CLOSED", ok3,
          f"state={rc.cb_state} streak={rc.streak_403}")

    rc2 = pb.RateController(16)
    for _ in range(9):
        rc2.on_throttle(403)
    rc2.cooldown_until = time.time() - 1
    p = rc2.acquire()
    rc2.on_throttle(403, probe=True)
    rc2.release()
    ok4 = rc2.cb_state == pb.RateController.CB_OPEN and rc2.probe_fails == 1
    check("单测-熔断-探测失败回OPEN计数", ok4,
          f"state={rc2.cb_state} fails={rc2.probe_fails}")
    for _ in range(3):
        rc2.cooldown_until = time.time() - 1
        rc2.acquire()
        rc2.on_throttle(403, probe=True)
        rc2.release()
    check("单测-熔断-连续4轮探测失败才放弃", rc2.give_up,
          f"give_up={rc2.give_up} fails={rc2.probe_fails}")


def t_unit_classify():
    """403语义分类：直链过期 vs 风控封禁"""
    import panboost as pb
    check("单测-403分类-过期特征判定",
          pb.classify_forbidden(b"link has expired, please re-fetch",
                                "text/html") == "expired")
    check("单测-403分类-签名失效判定",
          pb.classify_forbidden(b'{"error":"signature mismatch"}',
                                "application/json") == "expired")
    check("单测-403分类-普通403不当过期",
          pb.classify_forbidden(b"<html>403 Forbidden</html>",
                                "text/html") is None)
    check("单测-403分类-空体不判定",
          pb.classify_forbidden(b"", "text/html") is None)
    check("单测-403分类-二进制体不判定",
          pb.classify_forbidden(b"\x89PNG expired",
                                "application/octet-stream") is None)


def t_unit_shuffled():
    """块乱序：集合守恒且顺序打乱"""
    import panboost as pb
    completed = bytearray(64)
    orders = []
    for _ in range(5):
        blocks = pb.shuffled_blocks(64, completed)
        orders.append(blocks)
        if sorted(blocks) != list(range(64)):
            break
    ok = all(sorted(b) == list(range(64)) for b in orders)
    check("单测-乱序-块集合守恒", ok)
    check("单测-乱序-顺序确实打乱", orders[-1] != list(range(64)),
          str(orders[-1][:8]))
    completed[3] = 1
    blocks = pb.shuffled_blocks(64, completed)
    check("单测-乱序-已完成块被排除", 3 not in blocks and len(blocks) == 63)


def t_unit_risk_store():
    """跨会话域名风控记忆：写入/读取/清除"""
    import panboost as pb
    with tempfile.TemporaryDirectory() as td:
        store = pb.HostRiskStore(Path(td) / "risk.json")
        check("单测-域记忆-初始无冷却", store.cooldown_left("a.com") == 0.0)
        store.note_throttle("a.com", 60)
        left = store.cooldown_left("a.com")
        check("单测-域记忆-写入后冷却生效", 59 <= left <= 60, f"left={left}")
        check("单测-域记忆-其他域不受影响",
              store.cooldown_left("b.com") == 0.0)
        check("单测-域记忆-文件已持久化",
              (Path(td) / "risk.json").exists())
        store.clear("a.com")
        check("单测-域记忆-成功后清除", store.cooldown_left("a.com") == 0.0)


def t_unit_speed_limiter():
    """限速器令牌桶：超额消费必须等待补充"""
    import panboost as pb
    lim = pb.SpeedLimiter(1024 * 1024)  # 1MB/s
    t0 = time.time()
    lim.consume(512 * 1024)   # 桶初始1MB，直接通过
    lim.consume(1024 * 1024)  # 需等待约0.5s补令牌
    dt = time.time() - t0
    check("单测-限速器-超额消费按速率等待", 0.35 <= dt <= 2.0, f"dt={dt:.2f}s")


def t_unit_parse_size():
    import panboost as pb
    cases = {"10M": 10 * 1024 ** 2, "512K": 512 * 1024,
             "1.5G": int(1.5 * 1024 ** 3), "1024": 1024,
             "3m": 3 * 1024 ** 2, "2 MB": 2 * 1024 ** 2}
    ok = all(pb.parse_size(k) == v for k, v in cases.items())
    check("单测-parse_size-各种单位", ok,
          str({k: pb.parse_size(k) for k in cases}))
    check("单测-parse_size-空值None", pb.parse_size("") is None
          and pb.parse_size(None) is None)


def t_unit_ua_pool():
    import panboost as pb
    check("单测-UA池-规模与唯一性",
          len(pb.UA_POOL) >= 6 and len(set(pb.UA_POOL)) == len(pb.UA_POOL))
    rot = pb.UARotator(pb.UA_POOL[0])
    ok_init = rot.current() == pb.UA_POOL[0]
    first = rot.next()
    seq = [first] + [rot.next() for _ in range(len(pb.UA_POOL) - 1)]
    ok_cycle = seq[-1] == pb.UA_POOL[0] and first != pb.UA_POOL[0]
    check("单测-UA轮换-游标循环", ok_init and ok_cycle, str(seq[:3]))


def t_unit_persona():
    import panboost as pb
    pk = pb.PersonaKit(enabled=True)
    chrome = pk.apply({"User-Agent": pb.UA_POOL[0]})
    ff = pk.apply({"User-Agent": "Mozilla/5.0 ... Firefox/132.0"})
    custom = pk.apply({"User-Agent": pb.UA_POOL[0], "Accept": "custom",
                       "Cookie": "a=1"})
    off = pb.PersonaKit(enabled=False).apply({"A": "1"})
    check("单测-拟人化-Chrome头补全",
          "Accept-Language" in chrome and "Sec-Fetch-Site" in chrome
          and chrome.get("Accept-Encoding") == "identity")
    check("单测-拟人化-Firefox不带SecFetch", "Sec-Fetch-Site" not in ff
          and "Accept-Language" in ff)
    check("单测-拟人化-用户显式头优先",
          custom.get("Accept") == "custom" and custom.get("Cookie") == "a=1")
    check("单测-拟人化-可关闭", "Accept-Language" not in off)


# =====================================================================
# v1.3 端到端测试
# =====================================================================

def t_expired_403():
    """403+过期特征体 → 直接判定直链过期（不熔断重试），提示重新获取"""
    data = os.urandom(2 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, reject_skip=1, reject_count=9999, reject_status=403,
                 reject_body="link has expired, please re-fetch")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "exp.bin"
        t0 = time.time()
        r = run_pb("download", srv.url + "/e.bin", "-o", str(out),
                   "-t", "8", timeout=60,
                   env_extra={"PANBOOST_HOME": td})
        dt = time.time() - t0
        check("直链过期-判定失败退出", r.returncode != 0,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("直链过期-输出过期提示", "直链已过期" in r.stdout, r.stdout[-300:])
        check("直链过期-进度已保存", Path(str(out) + ".pbctrl").exists())
        check("直链过期-不做长冷却快速退出", dt < 15, f"耗时{dt:.0f}s")


def t_ua_rotate_worker():
    """下载中途封禁当前UA → worker自动轮换UA继续完成 + --explain 摘要"""
    import panboost as pb
    data = os.urandom(48 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, delay_per_chunk=0.008, chunk_size=16 * 1024)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "ua.bin"
        proc = subprocess.Popen(
            PB + ["download", srv.url + "/u.bin", "-o", str(out),
                  "-t", "8", "--explain"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env={**os.environ, "PANBOOST_HOME": td,
                            "PANBOOST_CB_SCALE": "0.02"})
        time.sleep(1.5)  # 等下载进入worker阶段（约16MB/s，1.5s≈24MB<48MB）
        srv.set_data(data, forbid_uas=[pb.UA_POOL[0]],
                     reject_body="ua denied")
        so, se = proc.communicate(timeout=180)
        ok = proc.returncode == 0 and out.read_bytes() == data
        check("UA轮换-封UA后仍完成下载", ok,
              f"rc={proc.returncode} {so[-300:]}{se[-200:]}")
        uas = {h.get("User-Agent") for h in srv.header_log}
        check("UA轮换-服务器观测到新UA",
              any(u and u != pb.UA_POOL[0] for u in uas), str(list(uas)[:3]))
        check("UA轮换-explain摘要输出", "[风控摘要]" in so
              and "ua_switch" in so, so[-300:])


def t_persona_e2e():
    """拟人化端到端：浏览器头 + 块乱序 + 连接寿命"""
    import panboost as pb
    data = os.urandom(4 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "p.bin"
        r = run_pb("download", srv.url + "/p.bin", "-o", str(out),
                   "-t", "8", "--min-piece", "65536", timeout=120,
                   env_extra={"PANBOOST_HOME": td})
        ok = r.returncode == 0 and out.read_bytes() == data
        check("拟人化-下载完整", ok, r.stdout[-300:])
        hs = srv.header_log
        check("拟人化-请求带浏览器头",
              hs and "Accept-Language" in hs[0]
              and hs[0].get("Accept-Encoding") == "identity"
              and "Accept" in hs[0], str(hs[0] if hs else {}))
        rl = [x for x in srv.range_log if x >= 0]
        check("拟人化-块请求乱序", len(rl) >= 16 and rl != sorted(rl),
              f"前8个start={rl[:8]}")
        # v1.6 字节感知连接寿命：小块不再 6 块即换（HTTPS 握手成本高），
        # 24 块硬上限仍保证单连接寿命有限。单线程 64 块 → 至少 3 条连接。
        base = srv.conn_seq
        out2 = Path(td) / "p2.bin"
        r2 = run_pb("download", srv.url + "/p.bin", "-o", str(out2),
                    "-t", "1", "--min-piece", "65536", timeout=120,
                    env_extra={"PANBOOST_HOME": td})
        ok2 = r2.returncode == 0 and out2.read_bytes() == data
        delta = srv.conn_seq - base
        check("拟人化-连接寿命受限(24块硬上限)",
              ok2 and delta >= 2, f"Δconn={delta}")


def t_speed_limit_e2e():
    """--limit 2M：6MB文件至少约3秒"""
    data = os.urandom(6 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "l.bin"
        t0 = time.time()
        r = run_pb("download", srv.url + "/l.bin", "-o", str(out),
                   "-t", "4", "--limit", "2M", timeout=120,
                   env_extra={"PANBOOST_HOME": td})
        dt = time.time() - t0
        ok = r.returncode == 0 and out.read_bytes() == data
        check("限速-下载完整", ok, r.stdout[-300:])
        # 初始令牌桶预存2MB：6MB 总量只需等待 (6-2)/2 = 2s
        check("限速-实际按2MB/s整形", dt >= 1.8, f"耗时{dt:.1f}s")


def t_host_memory_e2e():
    """跨会话域级记忆：首次失败记录冷却 → 二次运行低并发起步提示"""
    data = os.urandom(2 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, throttle_after=2, throttle_status=403, retry_after=0)
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        out = Path(td) / "m.bin"
        env = {"PANBOOST_HOME": str(home), "PANBOOST_CB_SCALE": "0.02"}
        r1 = run_pb("download", srv.url + "/m.bin", "-o", str(out),
                    "-t", "16", timeout=120, env_extra=env)
        check("域记忆-首次失败退出", r1.returncode != 0)
        check("域记忆-冷却记录已持久化",
              (home / "antifraud.json").exists())
        # 重置服务器计数：让第二次运行能通过 probe（否则探测期即 403 退出）
        srv.set_data(data, throttle_after=2, throttle_status=403, retry_after=0)
        r2 = run_pb("download", srv.url + "/m.bin", "-o", str(out),
                    "-t", "16", timeout=120, env_extra=env)
        check("域记忆-二次运行低并发提示",
              "[记忆]" in r2.stdout and "低并发" in r2.stdout,
              r2.stdout[:300])


def t_unit_challenge():
    """单元：JS cookie 挑战页检测/解析（基于中科大镜像真实样本）"""
    import panboost as pb
    ustc_page = (b'<!DOCTYPE html><html><head><title>Verifying - Mirrors</title>'
                 b'</head><body><h1>Verifying your browser</h1>'
                 b'<p>Additional verification is required.</p>'
                 b'<script>document.cookie = "addr=101.245.88.231; max-age=300";'
                 b'setTimeout(function() {location.reload();}, 2000);</script>'
                 b'</body></html>')
    check("挑战检测-命中中科大样本",
          pb.looks_like_cookie_challenge(200, "text/html; charset=UTF-8", ustc_page))
    check("挑战检测-403挑战页也算",
          pb.looks_like_cookie_challenge(403, "text/html", ustc_page))
    check("挑战检测-二进制响应不算",
          not pb.looks_like_cookie_challenge(
              206, "application/octet-stream", ustc_page))
    check("挑战检测-普通网页不算(无验证词)",
          not pb.looks_like_cookie_challenge(
              200, "text/html",
              b'<html><script>document.cookie = "sid=abc";</script></html>'))
    check("挑战检测-206不算", not pb.looks_like_cookie_challenge(
        206, "text/html", ustc_page))
    ck = pb.parse_challenge_cookie(ustc_page)
    check("挑战解析-cookie提取", ck == ("addr", "101.245.88.231"), str(ck))
    check("挑战解析-等待毫秒", pb.parse_challenge_wait_ms(ustc_page) == 2000)
    h = pb.merge_cookie_header({"Cookie": "SESSID=x"}, "addr", "1.2.3.4")
    check("挑战合并-用户cookie在前", h["Cookie"] == "SESSID=x; addr=1.2.3.4",
          h.get("Cookie"))
    h2 = pb.merge_cookie_header({}, "addr", "1.2.3.4")
    check("挑战合并-无cookie时直接设置", h2["Cookie"] == "addr=1.2.3.4")


class _FakeResp:
    def __init__(self, status, ctype, body):
        self.status = status
        self._ctype = ctype
        self._body = body

    def getheader(self, name, default=None):
        return {"Content-Type": self._ctype}.get(name, default)

    def read(self, n=-1):
        d = self._body[:n] if n and n > 0 else self._body
        self._body = self._body[len(d):]
        return d


def t_unit_challenge_worker():
    """单元：worker 收到挑战页 → 会话cookie写入 + 返回可重试"""
    import panboost as pb
    page = (b'<html><body>Verifying<script>'
            b'document.cookie = "addr=9.9.9.9; max-age=300";'
            b'setTimeout(function(){location.reload();}, 100);</script>'
            b'</body></html>')
    dl = pb.MultiThreadDownloader("http://x/f.bin", "/tmp/_pb_never.bin",
                                  threads=2)
    ok = dl._solve_challenge(0, _FakeResp(200, "text/html", page))
    check("worker挑战-应答成功可重试", ok is True)
    check("worker挑战-cookie已入会话",
          dl.challenge_cookies.get("addr") == "9.9.9.9",
          str(dl.challenge_cookies))
    req = {}
    dl._apply_challenge_cookie(req)
    check("worker挑战-cookie已注入请求头", req.get("Cookie") == "addr=9.9.9.9")
    # 应答上限保护：连续第3次挑战必须抛错而不是无限循环
    dl2 = pb.MultiThreadDownloader("http://x/f.bin", "/tmp/_pb_never2.bin",
                                   threads=2)
    raised = False
    try:
        for _ in range(5):
            dl2._solve_challenge(0, _FakeResp(200, "text/html", page))
    except pb.DownloadError:
        raised = True
    check("worker挑战-应答上限保护触发", raised and dl2._chal_solved == 2,
          f"solved={dl2._chal_solved}")


def t_challenge_e2e():
    """端到端：JS cookie 挑战自动应答（模拟中科大镜像）"""
    import panboost as pb
    data = os.urandom(3 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, challenge={"cookie": "addr=10.1.2.3", "wait_ms": 100})
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "c.bin"
        r = run_pb("download", srv.url + "/c.bin", "-o", str(out),
                   "-t", "4", timeout=120,
                   env_extra={"PANBOOST_HOME": td})
        ok = r.returncode == 0 and out.read_bytes() == data
        check("挑战应答-下载完整", ok, r.stdout[-300:])
        check("挑战应答-确实被挑战过", srv.challenge_count >= 1,
              f"challenge_count={srv.challenge_count}")
        check("挑战应答-通过提示出现",
              "[验证]" in r.stdout and "浏览器验证挑战" in r.stdout,
              r.stdout[:300])
        with_cookie = [h for h in srv.header_log
                       if "addr=10.1.2.3" in (h.get("Cookie") or "")]
        check("挑战应答-后续请求带挑战cookie", len(with_cookie) >= 1,
              f"带cookie请求数={len(with_cookie)}")
        audit = (Path(td) / "antifraud.log").read_text(encoding="utf-8")
        check("挑战应答-审计已记录",
              '"event": "challenge_solved"' in audit, audit[:200])


def t_challenge_forever_e2e():
    """端到端：服务器永远挑战 → 有界失败退出（防死循环）"""
    data = os.urandom(1024 * 1024)
    srv = TestServer()
    srv.set_data(data, challenge={"cookie": "addr=10.1.2.3", "wait_ms": 50},
                 challenge_forever=True)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "f.bin"
        t0 = time.time()
        r = run_pb("download", srv.url + "/f.bin", "-o", str(out),
                   "-t", "2", timeout=60,
                   env_extra={"PANBOOST_HOME": td})
        dt = time.time() - t0
        check("挑战死循环-有界失败退出", r.returncode != 0 and dt < 30,
              f"rc={r.returncode} dt={dt:.1f}s")
        check("挑战死循环-不产出坏文件", not out.exists())


def t_unit_check_disk():
    """单元：磁盘空间预检"""
    import panboost as pb
    ok, free = pb.check_disk_space(tempfile.gettempdir(), 1)
    check("磁盘预检-小需求通过", ok and free > 0, f"free={free}")
    ok2, _ = pb.check_disk_space(tempfile.gettempdir(), 10 ** 15)
    check("磁盘预检-超大需求拒绝", not ok2)


def t_unit_ctrl_v3_roundtrip():
    """单元：ctrl v3 块内断点（parts）存取往返"""
    import panboost as pb
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "f.bin"
        dl = pb.MultiThreadDownloader("http://x/f.bin", out, threads=2)
        dl.size = 4 * 1024 * 1024
        dl.block_size = 1024 * 1024
        dl.nblocks = 4
        dl.completed = bytearray([1, 0, 0, 0])
        dl._block_got = {1: 100, 2: 1048576 - 1}
        d = dl.ctrl_data()
        check("ctrlv3-版本号与parts", d["version"] == 3
              and d["parts"] == {"1": 100, "2": 1048575}, str(d.get("parts")))
        dl.save_ctrl()
        check("ctrlv3-文件已写入", dl.ctrl_path.exists())
        dl2 = pb.MultiThreadDownloader("http://x/f.bin", out, threads=2)
        dl2.size = dl.size
        dl2.block_size = dl.block_size
        dl2.nblocks = dl.nblocks
        dl2.load_ctrl()
        check("ctrlv3-完成位恢复", dl2.completed == bytearray([1, 0, 0, 0]))
        check("ctrlv3-parts恢复", dl2._block_got == {1: 100, 2: 1048575},
              str(dl2._block_got))
        # 非法 parts 条目被忽略
        dl2._block_got = {}
        raw = json.loads(dl.ctrl_path.read_text(encoding="utf-8"))
        raw["parts"] = {"99": 10, "0": 5, "1": -3, "x": "y"}
        dl.ctrl_path.write_text(json.dumps(raw), encoding="utf-8")
        dl2.load_ctrl()
        check("ctrlv3-非法条目被忽略", dl2._block_got == {},
              str(dl2._block_got))


def t_unit_clamp_cap():
    """单元：域级学习值 clamp（当前上限与2倍爬升空间）"""
    import panboost as pb
    rc = pb.RateController(64)
    rc.clamp_cap(4)
    check("学习值clamp-当前上限收敛", rc.cap <= 4, f"cap={rc.cap}")
    check("学习值clamp-保留2倍爬升空间", rc.max_cap == 8,
          f"max_cap={rc.max_cap}")


def t_partial_block_resume_e2e():
    """端到端：CDN 截断响应 → 重试从块内断点继续（Range 起点=已收字节）"""
    data = os.urandom(4 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, truncate_count=2, truncate_at=100 * 1024)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "t.bin"
        # 单块：min_piece 8MB > 4MB → nblocks=1，重试必然同块
        r = run_pb("download", srv.url + "/t.bin", "-o", str(out),
                   "-t", "1", "--min-piece", "8388608", timeout=120,
                   env_extra={"PANBOOST_HOME": td})
        ok = r.returncode == 0 and out.read_bytes() == data
        check("块内续传-下载完整", ok, r.stdout[-300:])
        check("块内续传-截断已发生", srv.truncate_hits == 2,
              f"hits={srv.truncate_hits}")
        rl = srv.range_log
        check("块内续传-重试Range从断点开始",
              len(rl) >= 3 and rl[0] == 0 and rl[1] == 0
              and rl[2] == 100 * 1024, f"range_log前5={rl[:5]}")


def t_stall_watchdog_e2e():
    """端到端：僵尸连接看门狗——3条连接收请求后长期不发数据"""
    data = os.urandom(2 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, stall_conns=3, stall_start=2, stall_secs=30)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "s.bin"
        t0 = time.time()
        r = run_pb("download", srv.url + "/s.bin", "-o", str(out),
                   "-t", "4", "--stall-timeout", "1.5", timeout=120,
                   env_extra={"PANBOOST_HOME": td})
        dt = time.time() - t0
        ok = r.returncode == 0 and out.read_bytes() == data
        check("看门狗-僵尸不拖垮下载", ok, r.stdout[-300:])
        check("看门狗-击杀已记录",
              '"stall_killed"' in (Path(td) / "antifraud.log").read_text())
        check("看门狗-僵尸连接被替换", srv.conn_seq >= 5,
              f"conn_seq={srv.conn_seq}")
        check("看门狗-无需等僵尸苏醒", dt < 25, f"耗时{dt:.1f}s")


def t_global_err_backoff_e2e():
    """端到端：服务器持续截断 → 有界失败 + 全局退避防请求风暴"""
    data = os.urandom(2 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, truncate_count=9999, truncate_at=10 * 1024)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "g.bin"
        r = run_pb("download", srv.url + "/g.bin", "-o", str(out),
                   "-t", "2", "--retry", "3", timeout=180,
                   env_extra={"PANBOOST_HOME": td})
        check("全局退避-有界失败退出", r.returncode != 0)
        check("全局退避-请求风暴受控", srv.req_seq < 100,
              f"req_seq={srv.req_seq}")
        check("全局退避-不产出坏文件", not out.exists()
              or out.read_bytes() != data)


def t_host_profile_e2e():
    """端到端：域级并发学习——限流收敛值持久化，二次运行从学习值起步"""
    data = os.urandom(1024 * 1024)
    srv = TestServer()
    srv.set_data(data, throttle_after=1, throttle_status=429, retry_after=0)
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        out = Path(td) / "cap.bin"
        env = {"PANBOOST_HOME": str(home), "PANBOOST_CB_SCALE": "0.02"}
        r1 = run_pb("download", srv.url + "/c.bin", "-o", str(out),
                    "-t", "16", timeout=120, env_extra=env)
        check("域画像-首次失败退出", r1.returncode != 0)
        db_file = home / "antifraud.json"
        check("域画像-学习库已持久化", db_file.exists())
        db = json.loads(db_file.read_text(encoding="utf-8"))
        rec = list(db.values())[0] if db else {}
        check("域画像-并发学习值已写入", "cap" in rec, str(rec))
        srv.set_data(data, throttle_after=1, throttle_status=429, retry_after=0)
        r2 = run_pb("download", srv.url + "/c.bin", "-o", str(out),
                    "-t", "16", timeout=120, env_extra=env)
        check("域画像-二次运行应用学习值",
              "并发上限" in r2.stdout, r2.stdout[:400])


def t_single_resume_e2e():
    """端到端：单线程模式中断后 .pbpart Range 续传"""
    data = os.urandom(6 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data, delay_per_chunk=0.004, chunk_size=64 * 1024)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "sr.bin"
        part = Path(str(out) + ".pbpart")
        proc = subprocess.Popen(
            PB + ["download", srv.url + "/sr.bin", "-o", str(out),
                  "--single", "--quiet"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.time() + 20
        while time.time() < deadline:
            if part.exists() and part.stat().st_size > 1024 * 1024:
                break
            time.sleep(0.1)
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        check("单线程续传-part已保留", part.exists(),
              f"part_size={part.stat().st_size if part.exists() else 0}")
        part_size = part.stat().st_size if part.exists() else 0
        r2 = run_pb("download", srv.url + "/sr.bin", "-o", str(out),
                    "--single", timeout=120,
                    env_extra={"PANBOOST_HOME": td})
        ok = r2.returncode == 0 and out.read_bytes() == data
        check("单线程续传-数据完整", ok, r2.stdout[-300:])
        check("单线程续传-Range从断点开始",
              srv.range_log and srv.range_log[-1] == part_size,
              f"last_range={srv.range_log[-1] if srv.range_log else None} "
              f"part={part_size}")


CLOUDWAF_PAGE = (
    '<!DOCTYPE html><html style="height:100%;width:100%"><head>'
    '<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />'
    '<meta http-equiv="Server" content="CloudWAF" />'
    '<title>访问被拦截！</title></head>'
    '<body>您的请求疑似攻击行为！如果您是站长，您可以前往WAF控制台进行'
    '误报屏蔽设置，让您的访问不再被拦截。事件ID：20-874ccd7b69f56c38'
    '</body></html>')


def t_unit_waf_block():
    """WAF 拦截页识别（华为云 CloudWAF 真实样本 vs 正常响应不误判）"""
    import panboost as pb
    page = ('<meta http-equiv="Server" content="CloudWAF" />'
            '<title>访问被拦截！</title>您的请求疑似攻击行为！').encode()
    check("单测-WAF-CloudWAF样本命中",
          pb.looks_like_waf_block(418, "text/html; charset=utf-8", page))
    check("单测-WAF-无标记418+html仍判定",
          pb.looks_like_waf_block(418, "text/html", b"teapot"))
    check("单测-WAF-普通404不误判",
          not pb.looks_like_waf_block(404, "text/html", page))
    check("单测-WAF-正常200不误判",
          not pb.looks_like_waf_block(200, "text/html", b"<html>ok</html>"))
    check("单测-WAF-无标记429不误判",
          not pb.looks_like_waf_block(429, "text/plain", b"too many requests"))


def t_waf_block_e2e():
    """端到端：WAF 拦截(418+CloudWAF页) → 明确识别与指引而非模糊报错

    实测场景(2026-10 华为云镜像站)：高并发下载+连接集中中断后，后续
    所有请求返回 418 + CloudWAF 拦截页。礼貌客户端应识别并告知用户
    等待解除，而非无限重试或尝试绕过。
    """
    data = os.urandom(256 * 1024)
    srv = TestServer()
    srv.set_data(data, reject_skip=0, reject_count=999,
                 reject_status=418, reject_body=CLOUDWAF_PAGE,
                 reject_ctype="text/html; charset=utf-8")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "w.bin"
        r = run_pb("download", srv.url + "/w.bin", "-o", str(out), timeout=60)
        ok = r.returncode != 0 and "WAF" in r.stdout and "防火墙" in r.stdout
        check("WAF拦截-识别并给出等待指引", ok, r.stdout[-300:])
        check("WAF拦截-不产出坏文件", not out.exists()
              or out.read_bytes() != data)



# ---------------- v1.8.0 分享链接解析 ----------------
def t_share_resolver_unit():
    import panboost as pb
    check("解析-识别蓝奏分享", pb.find_resolver(
        "https://wwm.lanzou.com/iAbCdE") == "lanzou")
    check("解析-识别123分享", pb.find_resolver(
        "https://www.123pan.com/s/Ab12Cd") == "pan123")
    check("解析-识别夸克分享", pb.find_resolver(
        "https://pan.quark.cn/s/abc123") == "quark")
    check("解析-直链不误判", pb.find_resolver(
        "http://example.com/a.bin") is None)
    k, c = pb._share_key(
        "https://www.123pan.com/s/Ab12Cd?code=9x8k",
        r"123pan\.com/s/([A-Za-z0-9]+)")
    check("解析-分享码与提取码提取", k == "Ab12Cd" and c == "9x8k")
    k2, c2 = pb._share_key("https://pan.quark.cn/s/Qk1#pass1",
                           r"quark\.cn/s/([A-Za-z0-9]+)")
    check("解析-井号提取码", k2 == "Qk1" and c2 == "pass1")


def _mock_123(srv, d1, d2):
    srv.add_path("/dl/a.bin", d1)
    srv.add_path("/dl/b.bin", d2)
    srv.add_json("/api/share/info",
                 {"code": 0, "data": {"ShareKey": "k1", "ShareKeyID": 9}})
    srv.add_json("/api/share/get", {"code": 0, "data": {"InfoList": [
        {"FileId": 1, "FileName": "a.bin", "Size": len(d1),
         "S3KeyTag": "t1", "IsDir": 0},
        {"FileId": 2, "FileName": "b.bin", "Size": len(d2),
         "S3KeyTag": "t2", "IsDir": 0}]}})
    srv.add_json("/api/share/get", {"code": 0, "data": {"InfoList": [
        {"DownloadUrl": f"{srv.url}/dl/a.bin"}]}},
        when_query="S3KeyTag=t1")
    srv.add_json("/api/share/get", {"code": 0, "data": {"InfoList": [
        {"DownloadUrl": f"{srv.url}/dl/b.bin"}]}},
        when_query="S3KeyTag=t2")


def t_share_pan123_e2e():
    import panboost as pb
    d1 = os.urandom(300 * 1024)
    d2 = os.urandom(200 * 1024)
    srv = TestServer()
    _mock_123(srv, d1, d2)
    env = {"PANBOOST_RESOLVER_HOSTS": json.dumps({"pan123": srv.url})}
    outdir = tempfile.mkdtemp(prefix="pb123share_")
    r = run_pb("download", "https://www.123pan.com/s/k1", "-o", outdir, "--single",
               env_extra=env)
    ok = (r.returncode == 0
          and (Path(outdir) / "a.bin").read_bytes() == d1
          and (Path(outdir) / "b.bin").read_bytes() == d2)
    check("解析-123多文件批量下载完整", ok,
          (r.stdout + r.stderr)[-200:])
    srv2 = TestServer()
    srv2.add_path("/dl/only.bin", d1)
    srv2.add_json("/api/share/info",
                  {"code": 0, "data": {"ShareKey": "k2", "ShareKeyID": 8}})
    srv2.add_json("/api/share/get", {"code": 0, "data": {"InfoList": [
        {"FileId": 7, "FileName": "only.bin", "Size": len(d1),
         "S3KeyTag": "tx", "IsDir": 0}]}})
    srv2.add_json("/api/share/get", {"code": 0, "data": {"InfoList": [
        {"DownloadUrl": f"{srv2.url}/dl/only.bin"}]}},
        when_query="S3KeyTag=tx")
    env2 = {"PANBOOST_RESOLVER_HOSTS": json.dumps({"pan123": srv2.url})}
    out = str(Path(tempfile.mkdtemp(prefix="pb123one_")) / "only.bin")
    r2 = run_pb("download", "https://www.123pan.com/s/k2", "-o", out, "--single",
                env_extra=env2)
    check("解析-123单文件直链下载", r2.returncode == 0
          and Path(out).read_bytes() == d1, (r2.stdout + r2.stderr)[-150:])


def t_share_quark_e2e():
    d1 = os.urandom(256 * 1024)
    srv = TestServer()
    srv.add_path("/dl/q1.bin", d1)
    srv.add_json("/1/clouddrive/share/sharepage/token",
                 {"code": 0, "data": {"stoken": "st1"}},
                 method="POST", require_cookie="__puus=")
    srv.add_json("/1/clouddrive/share/sharepage/detail",
                 {"code": 0, "data": {"list": [
                     {"fid": "f1", "file_name": "q1.bin",
                      "size": len(d1), "dir": False},
                     {"fid": "d9", "file_name": "folder", "dir": True}]}})
    srv.add_json("/1/clouddrive/share/sharepage/download",
                 {"code": 0, "data": {
                     "download_url": f"{srv.url}/dl/q1.bin"}},
                 when_query="fid=f1")
    env = {"PANBOOST_RESOLVER_HOSTS": json.dumps({"quark": srv.url})}
    r = run_pb("download", "https://pan.quark.cn/s/Qk1", "-o", "/tmp/never.bin",
               env_extra=env)
    check("解析-夸克未登录友好提示",
          r.returncode == 1 and "夸克分享解析需登录" in r.stdout + r.stderr,
          (r.stdout + r.stderr)[-150:])
    out = str(Path(tempfile.mkdtemp(prefix="pbquark_")) / "q1.bin")
    r2 = run_pb("download", "https://pan.quark.cn/s/Qk1", "-o", out, "--single",
                "--cookie", "__puus=fake123", env_extra=env)
    check("解析-夸克登录后下载完整",
          r2.returncode == 0 and Path(out).read_bytes() == d1,
          (r2.stdout + r2.stderr)[-150:])
    logs = [h for h in srv.header_log
            if h.get("path", "").endswith("/token")]
    check("解析-夸克API请求带Cookie",
          logs and "__puus=fake123" in (logs[-1]["Cookie"] or ""))
    dl = [h for h in srv.header_log
          if h.get("path", "").endswith("/download")]
    check("解析-夸克download请求带Cookie与Referer",
          dl and "__puus=fake123" in (dl[-1]["Cookie"] or "")
          and "quark.cn" in (dl[-1]["Referer"] or ""))


def main():
    # 隔离配置目录：避免测试写入真实 ~/.panboost（antifraud.json/log）
    home = tempfile.mkdtemp(prefix="pbtest_home_")
    os.environ["PANBOOST_HOME"] = home
    # 测试提速：跳过每秒的崩溃一致性 fsync（子进程继承）
    os.environ.setdefault("PANBOOST_NO_FSYNC", "1")
    tests = [t_multithread, t_resume_sigint, t_resume_kill, t_no_range,
             t_redirect, t_cookie_required, t_content_disposition,
             t_cookie_store, t_probe, t_empty_and_small,
             t_dynamic_blocks, t_auto, t_many_threads,
             t_anti_throttle_aimd, t_anti_throttle_smooth_ramp,
             t_anti_throttle_retry_after, t_anti_throttle_403_circuit,
             t_unit_circuit_states, t_unit_classify, t_unit_shuffled,
             t_unit_risk_store, t_unit_speed_limiter, t_unit_parse_size,
             t_unit_ua_pool, t_unit_persona,
             t_expired_403, t_ua_rotate_worker, t_persona_e2e,
             t_speed_limit_e2e, t_host_memory_e2e,
              t_unit_challenge, t_unit_challenge_worker,
              t_challenge_e2e, t_challenge_forever_e2e,
              t_unit_waf_block, t_waf_block_e2e,
              t_unit_check_disk, t_unit_ctrl_v3_roundtrip, t_unit_clamp_cap,
             t_partial_block_resume_e2e, t_stall_watchdog_e2e,
             t_global_err_backoff_e2e, t_host_profile_e2e,
             t_single_resume_e2e,
             t_share_resolver_unit, t_share_pan123_e2e,
             t_share_quark_e2e]
    risk_file = Path(home) / "antifraud.json"
    for t in tests:
        risk_file.unlink(missing_ok=True)  # 每个测试从干净风控记忆开始
        try:
            t()
        except Exception as e:
            FAIL.append(t.__name__)
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n===== 结果: {len(PASS)} 通过 / {len(FAIL)} 失败 =====")
    if FAIL:
        print("失败项:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
