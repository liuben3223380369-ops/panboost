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
          sudo apt-get install -y -q libtool libtool-bin autoconf automake pkg-config

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
          for f in *.apk; do mv "$f" panboost-1.6.0-android.apk; done

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
          printf '%s\\n' 'GitHub Actions 云端自动构建的调试签名 APK。' '安装后输入直链与 Cookie 即可多线程下载（反风控引擎全量生效）。' '文件保存在 Android/data/org.panboost.app/files/ 目录。' '命令行完整功能请用 Termux，见 README 在 Android 手机上使用 章节。' > "$NOTES_FILE"
          TAG="android-v1.6.0"
          if gh release view "$TAG" -R "$GITHUB_REPOSITORY" > /dev/null 2>&1; then
            gh release upload "$TAG" mobile/bin/*.apk --clobber -R "$GITHUB_REPOSITORY"
          else
            gh release create "$TAG" mobile/bin/*.apk -R "$GITHUB_REPOSITORY" --title "PanBoost Android v1.6.0" --prerelease --notes-file "$NOTES_FILE"
          fi
'''

out = Path(".github/workflows/android.yml")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(CONTENT, encoding="utf-8")
print("written", out, out.stat().st_size, "bytes")
