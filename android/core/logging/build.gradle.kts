// 统一日志（v5.0.0：v3.2.8 applog.py 原生等价）
plugins {
    id("panboost.android.library")
    id("panboost.hilt")
}

android {
    namespace = "org.panboost.core.logging"
}

dependencies {
    implementation(libs.kotlinx.coroutines.core)
    testImplementation(libs.junit)
}
