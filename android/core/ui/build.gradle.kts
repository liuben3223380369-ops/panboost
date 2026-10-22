// 共享 UI 工具层（v5.4.0：fmtSize 等格式化/语义色的单一定义点）
plugins {
    id("panboost.android.library")
    id("panboost.android.library.compose")
}

android {
    namespace = "org.panboost.core.ui"
}

dependencies {
    testImplementation(libs.junit)
}
