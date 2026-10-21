// 登录屏（第 4 周：原生 WebView + Cookie 采集）
plugins {
    id("panboost.android.library")
    id("panboost.android.library.compose")
    id("panboost.hilt")
}

android {
    namespace = "org.panboost.feature.login"
}

dependencies {
    implementation(project(":core:network"))

    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.hilt.navigation.compose)

    testImplementation(libs.junit)
}
