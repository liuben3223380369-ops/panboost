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
          for f in *.apk; do mv "$f" panboost-1.8.3-android.apk; done

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
          printf '%s\\n' 'GitHub Actions 云端自动构建的调试签名 APK（v1.8.3 系统级根治版）。' '真机反馈 v1.8.2 后百度已正常，但其他网盘仍跳"下载网盘APP"界面、手势返回仍无效——抓 SDL 官方源码定位真正根由后本次系统级根治：' '①"手势/返回键无法关闭登录页"——Android 10+ 手势导航的返回手势不产生键盘事件，直接调 Activity.onBackPressed()；SDL 源码里 trap 开启时该函数直接 return（手势被吞，什么都不发生），此前三层键盘拦截全部收不到手势。本次把登录层改为全屏 Dialog 承载：手势/返回键自动取消 Dialog（Android 系统标准行为），不再依赖任何键盘事件，这是唯一系统级可靠路径。' '②"其他网盘仍跳下载App界面"——导航拦截器 shouldOverrideUrlLoading 对服务端 302 重定向无效（Android 官方文档明确），网盘 H5 壳"跳下载App"很多正是 302 落地。本次在 onPageStarted（一切导航必经点，含 302 落地）加装守卫：应用市场类 URL（market://、各应用商店）命中即停止加载，并记录完整导航日志（登录结束后落 nav-*.log，可取回诊断"到底跳去了哪"）。' '百度修复（v1.8.2）、PC 版登录页、桌面 UA、导航守卫等此前修复全部保留。' 'v1.8.0 功能全量包含：分享链接直接下载（蓝奏云/123云盘免登录，夸克网盘需先登录），多文件分享自动批量下载、支持提取码（链接后加 ?code=xxxx）。首页 18 家国内外网盘入口，登录 Cookie 永久保存、下载自动携带；前台服务保活锁屏不断流。' '异常请取应用目录 crash-*.log 与 nav-*.log 反馈。命令行完整功能请用 Termux，见 README。' > "$NOTES_FILE"
          TAG="android-v1.8.3"
          if gh release view "$TAG" -R "$GITHUB_REPOSITORY" > /dev/null 2>&1; then
            gh release upload "$TAG" mobile/bin/*.apk --clobber -R "$GITHUB_REPOSITORY"
          else
            gh release create "$TAG" mobile/bin/*.apk -R "$GITHUB_REPOSITORY" --title "PanBoost Android v1.8.3" --latest --notes-file "$NOTES_FILE"
          fi
'''

out = Path(".github/workflows/android.yml")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(CONTENT, encoding="utf-8")
print("written", out, out.stat().st_size, "bytes")
