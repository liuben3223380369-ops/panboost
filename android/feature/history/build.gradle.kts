// 下载历史屏（v5.0.0：v3.2.8「历史」屏原生等价）
plugins {
    id("panboost.android.library")
    id("panboost.android.library.compose")
    id("panboost.hilt")
}

android {
    namespace = "org.panboost.feature.history"
}

dependencies {
    implementation(project(":core:domain"))
    implementation(project(":core:data"))

    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.hilt.navigation.compose)

    testImplementation(libs.junit)
}
