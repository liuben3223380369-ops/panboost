// PanBoost Android 原生重构：根设置（第 1 周骨架）
// 模块布局对标现代 Android 官方架构（NIA 风格）：
//   app            壳工程（MainActivity + Compose 入口）
//   :core:domain   纯 Kotlin 领域层（第 2 周填充接口）
//   :core:data     数据层（第 2 周：MediaStore 写入 + 仓库实现）
//   :feature:download 下载功能（第 3 周：MVI + ViewModel）
//   （后续周追加 :feature:login / :feature:home）
pluginManagement {
    includeBuild("build-logic")
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "PanBoost"
include(":app")
include(":core:domain")
include(":core:data")
include(":core:network")
include(":feature:download")
include(":feature:login")
include(":feature:home")
