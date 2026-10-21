#!/usr/bin/env python3
"""一次性生成器：写出 GitHub Actions workflow（绕过环境的 yml 写入 bug）"""
from pathlib import Path

CONTENT = '''name: Android APK

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install buildozer
        run: pip install buildozer cython

      - name: Install native build deps
        run: |
          sudo apt-get update -q
          sudo apt-get install -y -q libtool libtool-bin libltdl-dev autoconf automake pkg-config xvfb

      - name: KV sanity check (real Kivy, blocks startup-crash APKs)
        run: |
          pip install kivy
          cp panboost.py mobile/panboost.py
          xvfb-run -a python3 dev/check_kv.py

      - name: Cache buildozer toolchain
        uses: actions/cache@v4
        with:
          path: |
            ~/.buildozer
            mobile/.buildozer
          key: buildozer-${{ runner.os }}-${{ hashFiles('mobile/buildozer.spec') }}

      - name: Prepare Android SDK (Aidl fix)
        run: |
          SDK="$HOME/.buildozer/android/platform/android-sdk"
          mkdir -p "$SDK/cmdline-tools"
          curl -sLo /tmp/ct.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
          unzip -q /tmp/ct.zip -d "$SDK/cmdline-tools"
          mv "$SDK/cmdline-tools/cmdline-tools" "$SDK/cmdline-tools/latest"
          yes | "$SDK/cmdline-tools/latest/bin/sdkmanager" --licenses > /dev/null || true
          "$SDK/cmdline-tools/latest/bin/sdkmanager" "platform-tools" "build-tools;34.0.0" "platforms;android-33" > /dev/null
          mkdir -p "$SDK/tools"
          cp -a "$SDK/cmdline-tools/latest/." "$SDK/tools/"

      - name: Copy engine into mobile
        run: cp panboost.py mobile/panboost.py

      - name: Build debug APK
        run: cd mobile && buildozer -v android debug

      - name: Verify manifest entrypoint is PanMainActivity (v3.2.2 gate)
        run: |
          AAPT="$HOME/.buildozer/android/platform/android-sdk/build-tools/34.0.0/aapt2"
          APK=$(ls mobile/bin/*.apk | head -1)
          "$AAPT" dump xmltree --file AndroidManifest.xml "$APK" > /tmp/manifest.txt 2>&1 || true
          grep -i "org.panboost.PanMainActivity" /tmp/manifest.txt || {
            echo "::error::主入口仍是默认 PythonActivity（p4a.extra_args 的 --android-entrypoint 未生效，登录层返回键将失效）"
            cat /tmp/manifest.txt
            exit 1
          }
          grep -c "android.intent.category.LAUNCHER" /tmp/manifest.txt | grep -v "^0$" || true
          echo "PanMainActivity 主入口校验通过"

      - name: Rename APK
        run: |
          cd mobile/bin
          for f in *.apk; do mv "$f" panboost-3.2.4-android.apk; done

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: panboost-apk
          path: mobile/bin/*.apk

      - name: Publish to Release
        env:
          GH_TOKEN: ${{ github.token }}
          NOTES_FILE: release-notes.txt
        run: |
          printf '%s\\n' 'GitHub Actions 云端自动构建的调试签名 APK（PanBoost v3.2.4 原生网盘列表版）。' 'v3.2.4 修复真机"登录后拉取文件列表失败"（崩溃日志实锤：请求在连接层即失败）——根因：Android 打包环境的 Python 没有系统证书库路径，网盘列表接口的 HTTPS 请求证书验证直接失败；下载引擎一直正常正是因为引擎自带证书库，网盘列表模块此前漏接。本版网盘列表/直链两处请求全部接上证书库（与引擎同一套：优先 certifi、不可用时回退不验证——拉的是用户自己账号的文件列表，与引擎下载同一信任模型）。' 'v3.2.3 修复 v3.2.2 真机点登录页闪退（崩溃日志实锤："Attempt to read from field Looper.mQueue on a null object reference"）——根因是登录层的界面构建此前在 Kivy 的渲染线程上直接执行（创建视图 + 叠加到主界面 + 创建消息调度器），部分机型上该线程取不到系统主消息循环，创建消息调度器时空指针崩溃。本版：登录层全部构建切到系统界面线程执行（消息循环必然存活，构建失败也会经取消回调通知，不会悬空）；消息调度全部改挂界面框架内部的调度通道，自建调度器彻底移除（该崩溃路径根除）。登录层架构与视觉与 v3.2.2 一致（主界面之上叠加的全屏原生页面，主界面全程存活不退场——登录完成后界面必然恢复）。' 'v3.2.2 架构：登录层回归主界面内部（叠加全屏原生视图层，非弹窗非独立页面）——独立页面方案在返回后主界面引擎不恢复（日志停在"打开网页登录"）的结构性缺陷消除；主入口 PanMainActivity 接管系统返回键/手势（网页可后退先退网页，否则关闭登录页）。' 'v3.2.0 重构：登录页从弹窗改为独立原生页面——真机反馈"登录页不能展示信息"（弹窗不出现/网页区空白）根治：网盘登录/浏览改为独立全屏页面（系统级窗口管理，与 Dialog 弹窗的显示时序/主题竞争彻底告别，整体风格更贴近原生手机页面）；登录页内的全部逻辑（Cookie 特征校验、多域采集、登录自动检测、导航拦截、按钮红字提示）移到 Java 侧原生实现，不再经过 Python 桥接（"按钮无字色块"等静默失败通道整体消除）；系统返回键/手势走标准路径（网页可后退先退网页再退出）。文件列表加载失败页去掉"改用网页版"按钮（避免回到 PC 网页触摸误选的坑），只保留"重新加载"。' 'v3.1.1 修复：网盘列表加载失败页新增"重新加载"与错误详情展示。' 'v3.1.0 重构：已登录夸克"我的网盘"从 WebView 网页版改为原生文件列表——网页版是 PC 页面，手机上触摸拖拽被网页解释成选择/点按且无原生滚动（"手指放在文件区就自动选了、根本没有滑动功能"的根因）；原生列表调用网盘网页版前端同款公开 API + 登录 Cookie，原生滚动+轻点选择即 YunX 式体验——文件夹轻点进入、文件轻点勾选、勾选后批量加速下载（最高 1024 线程）到公共 Download/PanBoost；目录面包屑导航；__puus Cookie 自动保活。其他网盘暂保留 WebView 浏览，后续版本逐家接入。' 'v3.0.1 修复：真机"滑动浏览文件列表却误触发选中"——自研 tap 手势（对标 YunX combinedClickable 语义）：按下只记录不消费（滚动优先），抬手按屏幕绝对位移 ≤ 8dp 且按压 ≤ 0.55s 才判定轻点切勾选；滑动/长按绝不触发。' 'v3.0.0 全新体验（对标 YunX 的核心交互）：粘贴分享链接 → App 内直接显示分享里的文件列表 → 勾选要下载的文件（全选/单选，最高 1024 线程加速）→ 下载到公共 Download/PanBoost 目录（文件管理器直接可见）。新增剪贴板识别：复制分享链接回到 App 自动填入。' 'v2.1.0 修复：真机"已登录后点卡片闪退"——已登录卡片直达"我的网盘"；会话总闸：一切迟到回调按会话校验直接忽略；登录检测轮询首轮延迟 3 秒。' 'v2.0.x：五屏界面（首页/下载/账号/历史/日志）底部五 Tab 导航 + 统一日志 app-*.log 按天轮转 + 全局异常钩子（任何未捕获异常不再静默）+ crash-*.log/nav-*.log 完整诊断体系。' 'v1.9.x 全部修复保留：登录完成闪退三层防御、点保存无反应根治（按钮红色反馈+Cookie 多域采集）、登录页标准布局、登录地址实锤修正。' '异常请取应用目录 crash-*.log、nav-*.log 与 app-*.log 反馈。命令行完整功能请用 Termux，见 README。' > "$NOTES_FILE"
          TAG="android-v3.2.4"
          if gh release view "$TAG" -R "$GITHUB_REPOSITORY" > /dev/null 2>&1; then
            gh release upload "$TAG" mobile/bin/*.apk --clobber -R "$GITHUB_REPOSITORY"
          else
            gh release create "$TAG" mobile/bin/*.apk -R "$GITHUB_REPOSITORY" --title "PanBoost Android v3.2.4" --latest --notes-file "$NOTES_FILE"
          fi
'''

out = Path(".github/workflows/android.yml")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(CONTENT, encoding="utf-8")
print("written", out, out.stat().st_size, "bytes")
