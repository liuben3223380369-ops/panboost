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
    implementation(libs.kotlinx.coroutines.core)

    testImplementation(libs.junit)
}
