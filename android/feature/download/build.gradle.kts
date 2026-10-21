// 下载功能屏（第 1 周骨架；第 3 周 MVI：UiState+ViewModel+Compose）
plugins {
    id("panboost.android.library")
    id("panboost.android.library.compose")
    id("panboost.hilt")
}

android {
    namespace = "org.panboost.feature.download"
}

dependencies {
    implementation(project(":core:domain"))
    implementation(project(":core:data"))
    implementation(libs.androidx.lifecycle.runtime.compose)
    testImplementation(libs.junit)
}
