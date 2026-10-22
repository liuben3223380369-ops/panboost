// 网络层（第 4 周：Retrofit + OkHttp，夸克 Web API）
plugins {
    id("panboost.android.library")
    id("panboost.hilt")
}

android {
    namespace = "org.panboost.core.network"
}

dependencies {
    api(project(":core:domain"))
    api(libs.retrofit)
    implementation(libs.okhttp)
    // v5.2.0：拦截器/仓库打请求日志（日志屏"不记录"的根因——网络层零日志）
    implementation(project(":core:logging"))
    implementation(libs.kotlinx.coroutines.core)

    testImplementation(libs.junit)
    testImplementation(libs.org.json)
}
