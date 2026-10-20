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

      - name: Rename APK
        run: |
          cd mobile/bin
          for f in *.apk; do mv "$f" panboost-1.9.0-android.apk; done

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
          printf '%s\\n' 'GitHub Actions 云端自动构建的调试签名 APK（v1.9.0 登录页 UI 重构版）。' '真机反馈 v1.8.5 三大遗留：UC 打不开、夸克/阿里云盘打开是下载页、登录页顶部三个色块没有文字。' '本次真实联网调研（LinkSwift 油猴脚本 @match 清单 + AList 驱动文档）后根治：' '①登录页 UI 重构——标准登录页布局：深色标题栏（✕ 关闭 + 网盘名·网页登录 标题）、黄色操作提示条、网页区、底部通栏【已完成登录，保存 Cookie】大按钮（蓝底白字高对比）；文字设置三级保险（str 直传 → Java String 对象 → 失败写入导航日志），此前顶部按钮文字在部分真机不显示（只看到色块不知道是什么）。' '②登录地址修正——阿里云盘此前打开的是官网宣传页（含下载客户端引导），改为网页版真实路径 www.alipan.com/drive/；天翼云盘改为 cloud.189.cn/web/；移动云盘改为 yun.139.com（旧门户会跳 APP 引导）；移动 Cookie 域补 139.com。夸克/UC 域名经 LinkSwift 与 AList 双源确认无误。' '③桌面 UA 强化——此前 UA 设置与其他 WebView 配置捆在一起，任一项失败整块被静默跳过，真机仍用移动 UA 被网盘跳到下载页；现在 UA 独立设置并读回验证，结果写入导航日志可诊断。' '首页卡片升级三行：网盘名 + 状态（已登录/Cookie已存·未验证/点击网页登录）+ 域名。' 'v1.8.5 登录凭证校验（防游客 Cookie 误记已登录）、v1.8.4 回调强引用防闪退、v1.8.3 手势返回全部保留。' '异常请取应用目录 crash-*.log 与 nav-*.log 反馈。命令行完整功能请用 Termux，见 README。' > "$NOTES_FILE"
          TAG="android-v1.9.0"
          if gh release view "$TAG" -R "$GITHUB_REPOSITORY" > /dev/null 2>&1; then
            gh release upload "$TAG" mobile/bin/*.apk --clobber -R "$GITHUB_REPOSITORY"
          else
            gh release create "$TAG" mobile/bin/*.apk -R "$GITHUB_REPOSITORY" --title "PanBoost Android v1.9.0" --latest --notes-file "$NOTES_FILE"
          fi
'''

out = Path(".github/workflows/android.yml")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(CONTENT, encoding="utf-8")
print("written", out, out.stat().st_size, "bytes")
