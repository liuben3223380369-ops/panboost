// 网盘首页（第 4 周：夸克文件列表 MVI）
plugins {
    id("panboost.android.library")
    id("panboost.android.library.compose")
    id("panboost.hilt")
}

android {
    namespace = "org.panboost.feature.home"
}

dependencies {
    implementation(project(":core:domain"))
    implementation(project(":core:ui"))
    implementation(project(":core:network"))
    implementation(project(":core:data"))

    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.hilt.navigation.compose)

    testImplementation(libs.junit)
}
