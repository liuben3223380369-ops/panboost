# PanBoost

全网盘通用的多线程加速下载工具——原生 Android 版（v4.0）。

> v4.0 起为 **Kotlin + Compose 原生重写**（历史 Python/Kivy 版已
> 按 5 周迁移计划于 v4.0.0 移除）。夸克网盘首发支持，后续版本
> 逐家接入更多网盘。

## 功能

- **分享链接下载**（v5.0.0 三网盘）：粘贴夸克/123云盘/蓝奏云
  分享链接（剪贴板自动填入）→ 解析 → 勾选 → 批量加速下载
- **下载历史/日志**（v5.0.0）：历史 200 条（开关/清空/失败重跑）；
  实时日志 + 按天轮转文件
- **URL 直链下载**（v5.0.0）：粘贴直链 → 8 线程分块 → 实时速率
- **多网盘账号管理**（v4.3.0）：18 网盘账簿（夸克/UC/百度/
  阿里/天翼/移动/迅雷/123/蓝奏/坚果云/Google Drive/Dropbox/
  OneDrive/MEGA/pCloud/Box/Yandex）——WebView 登录自动采集
  Cookie、已登录徽标、手动粘贴 Cookie 兜底、删除账号
- **网盘登录**：原生 WebView 打开官方登录页（支持验证码/短信/
  扫码），登录后自动采集 Cookie——不逆向任何网盘协议加密
- **我的网盘浏览**：原生文件列表（网盘网页版前端自己使用的公开
  Web API + 用户自己的 Cookie），文件夹进出、面包屑导航
- **加速下载**：点文件取直链 → WorkManager 持久化队列下载
  （进程死亡自动续跑）→ 实时进度 → 保存到公共
  `Download/PanBoost`（文件管理器直接可见）
- **任务管理**：进度实时刷新 / 取消 / 重试 / 防重复排队

## 工程架构（NowInAndroid 风格）

```
android/
├── app/                    壳：单 Activity + NavHost（login→home→download）
├── build-logic/            Convention Plugins（application/library/compose/hilt）
├── core/
│   ├── domain/             纯 Kotlin 领域层（模型 + 仓库接口）
│   ├── data/               WorkManager Worker + MediaStore 写入 + 仓库实现
│   └── network/            Retrofit/OkHttp（夸克 Web API + Cookie 拦截器）
└── feature/
    ├── login/              WebView 登录屏（MVI）
    ├── home/               网盘文件列表屏（MVI）
    └── download/           下载进度屏（MVI）
```

- **Version Catalog**（`gradle/libs.versions.toml`）统一版本管理
- **Hilt**（KSP）依赖注入；**WorkManager** + `@HiltWorker` 下载队列
- **Material 3** Compose UI；**MediaStore** 零权限写公共下载目录
  （scoped storage 正统路径——无“所有文件访问”权限要求）

## 构建

```bash
cd android
./gradlew assembleDebug     # 调试 APK
./gradlew assembleRelease   # 发布 APK（需签名配置）
```

要求：JDK 17、Gradle 8.13+、Android SDK 36。

## 功能补齐路线

v3.2（Kivy 版）的完整功能面正按 [ROADMAP.md](ROADMAP.md) 逐项
回补（分享链接解析 / 多网盘 / 账号管理 / 下载历史 / 日志诊断等）。

## 诊断

崩溃报告位于 `/Android/data/org.panboost.app/files/crashes/crash-*.txt`
（文件管理器可直接取回，反馈问题时请附上）。

## 隐私与安全边界

- 登录走网盘官方页面（WebView），App 只采集用户自己的 Cookie
- 浏览/下载用网盘网页版前端自己使用的公开 Web API
- 不逆向、不破解任何网盘协议；请遵守各网盘服务条款

## License

同仓库 LICENSE。
