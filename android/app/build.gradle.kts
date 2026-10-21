// 壳工程：convention 插件组合（第 1 周骨架）
plugins {
    id("panboost.android.application")
    id("panboost.android.application.compose")
    id("panboost.hilt")
}

android {
    namespace = "org.panboost.app"
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)

    implementation(project(":core:domain"))
    implementation(project(":core:data"))
    implementation(project(":feature:download"))

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.espresso.core)
}
