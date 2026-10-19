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
          for f in *.apk; do mv "$f" panboost-1.7.2-android.apk; done

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
          printf '%s\\n' 'GitHub Actions 云端自动构建的调试签名 APK（v1.7.2）。' 'v1.7.2：WebView 登录层挂载失败可诊断——挂载分步自检，失败详情（含具体步骤名）显示到账号页状态栏并落 crash-*.log；若登录层仍打不开，请把账号页显示的失败步骤文字或 crash log 反馈给开发者。' 'v1.7.1：修复真机首页网盘卡片点击无反应（颜色参数 Java int 溢出 + UI 线程异常静默丢失）。' 'v1.7.0：浅色界面；首页 18 家国内外网盘入口，登录 Cookie 永久保存、下载自动携带；前台服务保活。' '线程选项至 1024。' '命令行完整功能请用 Termux，见 README 在 Android 手机上使用 章节。' > "$NOTES_FILE"
          TAG="android-v1.7.2"
          if gh release view "$TAG" -R "$GITHUB_REPOSITORY" > /dev/null 2>&1; then
            gh release upload "$TAG" mobile/bin/*.apk --clobber -R "$GITHUB_REPOSITORY"
          else
            gh release create "$TAG" mobile/bin/*.apk -R "$GITHUB_REPOSITORY" --title "PanBoost Android v1.7.2" --latest --notes-file "$NOTES_FILE"
          fi
'''

out = Path(".github/workflows/android.yml")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(CONTENT, encoding="utf-8")
print("written", out, out.stat().st_size, "bytes")
