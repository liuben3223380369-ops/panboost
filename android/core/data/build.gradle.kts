// 数据层（第 1 周骨架；第 2 周 MediaStore 写入 + WorkManager Worker）
plugins {
    id("panboost.android.library")
    id("panboost.hilt")
}

android {
    namespace = "org.panboost.core.data"
}

dependencies {
    api(project(":core:domain"))
    api(libs.work.runtime.ktx)

    implementation(libs.androidx.hilt.work)
    ksp(libs.androidx.hilt.compiler)

    testImplementation(libs.junit)
}
