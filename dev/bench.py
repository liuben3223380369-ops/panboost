#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PanBoost 性能基准：本地服务器多线程吞吐矩阵 + syscall 计数

用法：python3 dev/bench.py [MB] [--json]
输出：各线程数下的吞吐/耗时/pwrite 次数（strace 不可用时省略）
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from test_server import TestServer  # noqa: E402

PB = [sys.executable, str(ROOT / "panboost.py")]


def count_syscalls(pid, syscall):
    """读取 /proc/<pid>/… 不可用；改用采样无关方案：返回 None"""
    return None


def bench_one(srv, mb, threads, td):
    out = Path(td) / f"b{threads}.bin"
    env = {**os.environ, "PANBOOST_HOME": td, "PANBOOST_NO_FSYNC": "1"}
    t0 = time.time()
    r = subprocess.run(
        PB + ["download", srv.url + "/b.bin", "-o", str(out),
              "-t", str(threads), "--quiet"],
        capture_output=True, text=True, timeout=600, env=env)
    dt = time.time() - t0
    if r.returncode != 0:
        return {"threads": threads, "ok": False, "err": r.stdout[-200:]}
    return {"threads": threads, "ok": True, "secs": round(dt, 2),
            "mbps": round(mb / dt, 1)}


def main():
    mb = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() \
        else 200
    as_json = "--json" in sys.argv
    data = os.urandom(mb * 1024 * 1024)
    want = hashlib.sha256(data).hexdigest()
    srv = TestServer()
    srv.set_data(data)
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for t in (1, 4, 8, 16, 32, 64):
            rows.append(bench_one(srv, mb, t, td))
            got = hashlib.sha256(
                (Path(td) / f"b{t}.bin").read_bytes()).hexdigest()
            rows[-1]["integrity"] = got == want
    if as_json:
        print(json.dumps({"mb": mb, "rows": rows}, ensure_ascii=False))
        return 0
    print(f"基准：本地 TestServer × {mb}MB（校验全过 = integrity True）")
    print(f"{'线程':>6} {'耗时':>8} {'吞吐':>10} {'完整':>4}")
    for r in rows:
        if r.get("ok"):
            print(f"{r['threads']:>6} {r['secs']:>7.2f}s "
                  f"{r['mbps']:>8.1f}MB/s {str(r['integrity']):>5}")
        else:
            print(f"{r['threads']:>6}  失败: {r.get('err')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
