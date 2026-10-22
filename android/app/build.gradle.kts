// 壳工程：convention 插件组合（第 1 周骨架）
plugins {
    id("panboost.android.application")
    id("panboost.android.application.compose")
    id("panboost.hilt")
}

android {
    namespace = "org.panboost.app"

    // v4.1.0：release 用 debug 签名（零配置可直接安装；
    // 正式上架签名后续版本接 Play App Signing）
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.hilt.navigation.compose)
    implementation(libs.androidx.hilt.work)

    implementation(project(":core:domain"))
    implementation(project(":core:data"))
    implementation(project(":core:network"))
    implementation(project(":feature:download"))
    implementation(project(":feature:share"))
    implementation(project(":feature:accounts"))
    implementation(project(":feature:history"))
    implementation(project(":feature:logs"))
    implementation(project(":feature:login"))
    implementation(project(":feature:home"))

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.espresso.core)
}
