// 日志屏（v5.0.0：v3.2.8 日志屏原生等价）
plugins {
    id("panboost.android.library")
    id("panboost.android.library.compose")
    id("panboost.hilt")
}

android {
    namespace = "org.panboost.feature.logs"
}

dependencies {
    implementation(project(":core:logging"))

    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.hilt.navigation.compose)

    testImplementation(libs.junit)
}
