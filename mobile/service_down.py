#!/usr/bin/env python3
"""PanBoost 前台服务入口（p4a service）。

spec 配置 services = Download:service_down.py:foreground 后，p4a 生成
前台 Service：下载期间进程持通知常驻，Android 12+ 不会冻结本应用，
网络与下载线程持续可用（App 退后台/锁屏不断流）。

服务本身不执行下载（下载线程在 Kivy 主进程里跑，引擎实时落盘），
只做保活心跳。
"""
import time

INTERVAL = 3600

if __name__ == "__main__":
    while True:
        time.sleep(INTERVAL)
