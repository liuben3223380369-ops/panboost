#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1024线程 AIMD 收敛曲线演练：服务器并发上限16，观察客户端自动收敛过程"""
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, '/workspace/panboost')
from test_server import TestServer

data = os.urandom(64 * 1024 * 1024)
srv = TestServer()
srv.set_data(data, conn_limit=16, retry_after=1, delay_per_chunk=0.0006,
             chunk_size=16 * 1024)

samples = []
t0 = time.time()


def sampler():
    while time.time() - t0 < 25:
        samples.append((round(time.time() - t0, 1), srv.concurrent,
                        srv.throttle_count))
        time.sleep(0.5)


threading.Thread(target=sampler, daemon=True).start()
with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "e.bin"
    r = subprocess.run([sys.executable, "/workspace/panboost/panboost.py",
                        "download", srv.url + "/e.bin", "-o", str(out),
                        "-t", "1024", "--min-piece", "32768"],
                       capture_output=True, text=True, timeout=240)
    ok = r.returncode == 0 and out.read_bytes() == data
print(f"结果: rc={r.returncode} 数据{'一致' if ok else '损坏'}")
print(f"服务器并发上限16 | 实测峰值并发={srv.max_concurrent} | 429次数={srv.throttle_count}")
print("\n收敛曲线 (时间s: 并发数[429累计]):")
for t, c, tc in samples[::2]:
    print(f"  {t:5.1f}s: {'█' * min(c, 50)} {c:3d} [{tc}]")
